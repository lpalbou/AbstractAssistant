@preconcurrency import AVFoundation
import Observation
import AssistantKit
import AbstractGatewayClient

@MainActor @Observable final class AudioMeter {
    var level: Double = 0
    var graceProgress: Double = 0
}

@MainActor protocol VoiceRecording: AnyObject {
    func start() throws
    func stop()
    func power() -> (average: Float, peak: Float)
}

@MainActor private final class MicrophoneRecording: VoiceRecording {
    private let recorder: AVAudioRecorder
    init(url: URL) throws {
        recorder = try AVAudioRecorder(url: url, settings: [AVFormatIDKey: kAudioFormatLinearPCM, AVSampleRateKey: 16_000,
            AVNumberOfChannelsKey: 1, AVLinearPCMBitDepthKey: 16, AVLinearPCMIsFloatKey: false, AVLinearPCMIsBigEndianKey: false])
        recorder.isMeteringEnabled = true
    }
    func start() throws { guard recorder.record() else { throw CocoaError(.fileWriteUnknown) } }
    func stop() { recorder.stop() }
    func power() -> (average: Float, peak: Float) {
        recorder.updateMeters(); return (recorder.averagePower(forChannel: 0), recorder.peakPower(forChannel: 0))
    }
}

/// Deliberate cancellation for calls/Siri, lost headphones or a reset audio service.
private final class AudioSessionEvents: @unchecked Sendable {
    private var tokens: [NSObjectProtocol] = []
    init(action: @escaping @MainActor @Sendable () -> Void) {
        let center = NotificationCenter.default
        tokens.append(center.addObserver(forName: AVAudioSession.interruptionNotification, object: nil, queue: .main) { note in
            guard (note.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt) == AVAudioSession.InterruptionType.began.rawValue else { return }
            Task { @MainActor in action() }
        })
        tokens.append(center.addObserver(forName: AVAudioSession.routeChangeNotification, object: nil, queue: .main) { note in
            let reason = note.userInfo?[AVAudioSessionRouteChangeReasonKey] as? UInt
            guard reason == AVAudioSession.RouteChangeReason.oldDeviceUnavailable.rawValue || reason == AVAudioSession.RouteChangeReason.noSuitableRouteForCategory.rawValue else { return }
            Task { @MainActor in action() }
        })
        tokens.append(center.addObserver(forName: AVAudioSession.mediaServicesWereResetNotification, object: nil, queue: .main) { _ in Task { @MainActor in action() } })
    }
    deinit { for token in tokens { NotificationCenter.default.removeObserver(token) } }
}

@MainActor @Observable final class VoiceController {
    let meter = AudioMeter()
    private(set) var inputPhase: VoiceTurn.Phase = .idle
    private(set) var secondsRemaining = 3
    private(set) var readingID: String?
    private(set) var speaking = false
    private(set) var paused = false
    var recording: Bool { inputPhase == .recording }
    var transcribing: Bool { inputPhase == .transcribing }
    var localPending: Bool { inputPhase == .authorizing || inputPhase == .recording || inputPhase == .atLimit || inputPhase == .countdown || inputPhase == .ready }
    var inputPending: Bool { inputPhase != .idle }
    var error: String?
    @ObservationIgnored var onUnauthorized: (() -> Void)?
    @ObservationIgnored private var turn = VoiceTurn()
    @ObservationIgnored private var envelope = AudioEnvelope()
    @ObservationIgnored private var sampler: Task<Void, Never>?
    @ObservationIgnored private var captureTask: Task<Void, Never>?
    @ObservationIgnored private var recorder: (any VoiceRecording)?
    @ObservationIgnored private var player: AVAudioPlayer?
    @ObservationIgnored private var playback: Task<Void, Never>?
    @ObservationIgnored private var events: AudioSessionEvents?
    @ObservationIgnored private var generation = 0
    @ObservationIgnored private var recordingStarted: TimeInterval = 0
    @ObservationIgnored private let now: () -> TimeInterval
    @ObservationIgnored private let permission: () async -> Bool
    @ObservationIgnored private let recordingFactory: (URL) throws -> any VoiceRecording
    @ObservationIgnored private let configureAudio: Bool
    @ObservationIgnored private let file = FileManager.default.temporaryDirectory.appending(path: "iphone-voice-\(UUID().uuidString).wav")

    init(now: @escaping () -> TimeInterval = { ProcessInfo.processInfo.systemUptime },
         permission: @escaping () async -> Bool = { await AVAudioApplication.requestRecordPermission() },
         recordingFactory: @escaping (URL) throws -> any VoiceRecording = { try MicrophoneRecording(url: $0) },
         configureAudio: Bool = true) {
        self.now = now; self.permission = permission; self.recordingFactory = recordingFactory; self.configureAudio = configureAudio
        events = AudioSessionEvents { [weak self] in
            guard let self, self.inputPending || self.speaking else { return }
            self.stop(); self.error = "Audio was interrupted. Hold the orb to try again."
        }
    }

    /// Called at touch DOWN. A touch during grace cancels immediately and cannot begin a new turn.
    func press() {
        if inputPending { stop(); return }
        stop(); error = nil
        guard turn.begin() else { return }; publishTurn()
        let epoch = generation
        captureTask = Task {
            let allowed = await permission()
            guard !Task.isCancelled, epoch == generation, turn.phase == .authorizing else { return }
            guard allowed else { stop(); error = "Microphone access is off. You can enable it in iPhone Settings."; return }
            do {
                if configureAudio {
                    let audio = AVAudioSession.sharedInstance()
                    try audio.setCategory(.record, mode: .measurement); try audio.setActive(true)
                }
                let capture = try recordingFactory(file)
                try capture.start(); recorder = capture; recordingStarted = now()
                guard turn.recordingStarted(at: recordingStarted) else { stop(); return }
                publishTurn(); startSampling()
            } catch { stop(); self.error = "The microphone couldn’t start. You can still type your message." }
        }
    }

    /// Audio is sealed locally. No upload or STT call is allowed in the three-second grace.
    func release() {
        guard turn.phase == .recording || turn.phase == .atLimit else {
            if turn.phase == .authorizing { stop() }
            return
        }
        recorder?.stop(); recorder = nil; envelope.reset(); meter.level = 0
        turn.release(at: now())
        if turn.phase == .countdown { meter.graceProgress = 1 }
        publishTurn()
        if turn.phase == .idle { stop(); return }
        deactivateAudio()
    }

    private func publishTurn() {
        inputPhase = turn.phase
        secondsRemaining = turn.secondsRemaining(at: now())
    }

    /// Called by the sampler and deterministic lifecycle tests with the same monotonic clock.
    func sample() {
        if let recorder, recording {
            let power = recorder.power()
            meter.level = envelope.sample(averageDB: power.average, peakDB: power.peak)
            if now() - recordingStarted >= 60 {
                recorder.stop(); self.recorder = nil; turn.reachedLimit(); publishTurn(); deactivateAudio()
            }
        } else if let player, player.isPlaying, !paused {
            player.updateMeters()
            meter.level = envelope.sample(averageDB: player.averagePower(forChannel: 0), peakDB: player.peakPower(forChannel: 0))
        } else { meter.level = envelope.sample(averageDB: -160, peakDB: -160) }
        if turn.phase == .countdown {
            meter.graceProgress = min(1, max(0, ((turn.deadline ?? now()) - now()) / VoiceTurn.grace))
            turn.advance(to: now()); publishTurn()
            if turn.phase == .ready { stopSampling() }
        }
    }

    func finish(client: any GatewayClient, sessionID: String, model: TranscriptionChoice? = nil) async -> String? {
        guard turn.claimForTranscription() else { return nil }
        let epoch = generation; publishTurn(); stopSampling()
        defer { if epoch == generation { turn.cancel(); publishTurn(); try? FileManager.default.removeItem(at: file); deactivateAudio() } }
        do {
            let data = try Data(contentsOf: file)
            try Task.checkCancellation(); guard epoch == generation else { return nil }
            let text = try await client.transcribe(wav: data, sessionId: sessionID, model: model).trimmingCharacters(in: .whitespacesAndNewlines)
            try Task.checkCancellation(); guard epoch == generation else { return nil }
            guard !text.isEmpty else { error = "Nothing heard. Hold the orb to try again."; return nil }
            return text
        } catch {
            if epoch == generation, !(error is CancellationError) { self.error = error.localizedDescription; if error as? GatewayError == .unauthorized { onUnauthorized?() } }
            return nil
        }
    }

    func read(_ text: String, client: any GatewayClient, scope: SpeechScope, choice: VoiceChoice? = nil, messageID: String? = nil) {
        stop(); error = nil
        let text = SpeechText.plain(text).trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        speaking = true; readingID = messageID; startSampling()
        let epoch = generation
        playback = Task {
            do {
                if configureAudio {
                    let audio = AVAudioSession.sharedInstance()
                    try audio.setCategory(.playback, mode: .spokenAudio); try audio.setActive(true)
                }
                for try await chunk in client.speech(text: text, scope: scope, voice: { if case .run = scope { choice } else { nil } }()) {
                    try Task.checkCancellation(); guard epoch == generation else { return }
                    let player = try AVAudioPlayer(data: chunk); player.isMeteringEnabled = true; self.player = player
                    player.prepareToPlay(); if !paused, !player.play() { throw CocoaError(.fileReadCorruptFile) }
                    while player.isPlaying || paused { try await Task.sleep(for: .milliseconds(30)) }
                }
            } catch { if epoch == generation, !(error is CancellationError) { self.error = error.localizedDescription; if error as? GatewayError == .unauthorized { onUnauthorized?() } } }
            if epoch == generation { speaking = false; paused = false; readingID = nil; stopSampling(); player = nil; deactivateAudio() }
        }
    }

    private func startSampling() {
        stopSampling(); let epoch = generation
        // Task sleep is independent of run-loop modes: dragging/holding cannot stall the meter.
        sampler = Task { [weak self] in
            while !Task.isCancelled {
                guard let self, self.generation == epoch else { return }; self.sample()
                do { try await Task.sleep(for: .milliseconds(33)) } catch { return }
            }
        }
    }
    private func stopSampling() { sampler?.cancel(); sampler = nil; envelope.reset(); meter.level = 0; meter.graceProgress = 0 }
    private func deactivateAudio() { if configureAudio { try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation) } }
    func togglePause() { if paused { player?.play(); paused = false } else { player?.pause(); paused = true } }
    func stop() {
        generation += 1; stopSampling(); turn.cancel(); publishTurn(); readingID = nil
        captureTask?.cancel(); captureTask = nil; playback?.cancel(); playback = nil
        recorder?.stop(); recorder = nil; player?.stop(); player = nil
        speaking = false; paused = false
        try? FileManager.default.removeItem(at: file); deactivateAudio()
    }
}
