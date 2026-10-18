@preconcurrency import AVFoundation
import Observation
import UIKit
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
    func start() throws { guard recorder.record(forDuration: 60) else { throw CocoaError(.fileWriteUnknown) } }
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
    private(set) var preparing = false
    var playbackRate: Float { player?.rate ?? 1 }
    private(set) var speaking = false
    private(set) var paused = false
    var recording: Bool { inputPhase == .recording || inputPhase == .countdown }
    var transcribing: Bool { inputPhase == .transcribing }
    var localPending: Bool { inputPhase == .authorizing || inputPhase == .recording || inputPhase == .countdown || inputPhase == .ready }
    var inputPending: Bool { inputPhase != .idle }
    var error: String?
    @ObservationIgnored var onUnauthorized: (() -> Void)?
    @ObservationIgnored private var turn = VoiceTurn()
    @ObservationIgnored private var envelope = AudioEnvelope()
    @ObservationIgnored private var microphoneEnvelope = MicrophoneEnvelope()
    @ObservationIgnored private var activity = SpeechActivity()
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
    @ObservationIgnored private let isActive: () -> Bool
    @ObservationIgnored private var file: URL?
    @ObservationIgnored private let storage = PhoneTemporaryStorage()

    init(now: @escaping () -> TimeInterval = { ProcessInfo.processInfo.systemUptime },
         permission: @escaping () async -> Bool = { await AVAudioApplication.requestRecordPermission() },
         recordingFactory: @escaping (URL) throws -> any VoiceRecording = { try MicrophoneRecording(url: $0) },
         configureAudio: Bool = true,
         isActive: @escaping () -> Bool = { UIApplication.shared.applicationState == .active }) {
        self.now = now; self.permission = permission; self.recordingFactory = recordingFactory; self.configureAudio = configureAudio
        self.isActive = isActive
        events = AudioSessionEvents { [weak self] in
            guard let self, self.inputPending || self.speaking else { return }
            self.stop(); self.error = "Audio was interrupted. Tap the orb to try again."
        }
    }

    /// A deliberate tap activates capture; subsequent touches cancel synchronously.
    func activate() {
        if inputPending { stop(); return }
        stop(); error = nil
        guard turn.begin() else { return }; publishTurn()
        let epoch = generation
        captureTask = Task {
            let allowed = await permission()
            guard !Task.isCancelled, epoch == generation, turn.phase == .authorizing else { return }
            guard allowed else { stop(); error = "Microphone access is off. You can enable it in iPhone Settings."; return }
            // Permission dismissal can briefly precede activation. Never start under an inactive app.
            for _ in 0..<20 {
                if isActive() { break }
                do { try await Task.sleep(for: .milliseconds(50)) } catch { return }
                guard epoch == generation, turn.phase == .authorizing else { return }
            }
            guard isActive() else { stop(); error = "Tap the orb again when you’re back in the app."; return }
            do {
                if configureAudio {
                    let audio = AVAudioSession.sharedInstance()
                    try audio.setCategory(.record, mode: .measurement); try audio.setActive(true)
                }
                let folder = try storage.makeDirectory(for: .voice)
                let file = folder.appending(path: "recording.wav"); self.file = file
                let capture = try recordingFactory(file)
                try capture.start(); recorder = capture; recordingStarted = now()
                guard turn.recordingStarted(at: recordingStarted) else { stop(); return }
                publishTurn(); startSampling()
            } catch { stop(); self.error = "The microphone couldn’t start. You can still type your message." }
        }
    }

    private func publishTurn() {
        if inputPhase != turn.phase { inputPhase = turn.phase }
        let remaining = turn.secondsRemaining(at: now())
        if secondsRemaining != remaining { secondsRemaining = remaining }
    }

    /// Called by the sampler and deterministic lifecycle tests with the same monotonic clock.
    func sample() {
        if let recorder, recording {
            if now() - recordingStarted >= 60 {
                stop(); error = "One-minute recording limit reached. Please try a shorter message."; return
            }
            let power = recorder.power()
            let speech = power.average.isFinite ? activity.sample(averageDB: power.average) : nil
            meter.level = microphoneEnvelope.sample(averageDB: power.average, peakDB: power.peak, speech: speech ?? false)
            turn.sample(at: now(), speech: speech)
            if turn.phase == .idle {
                stop(); error = "Nothing heard. Tap the orb to try again."; return
            }
            if turn.phase == .ready {
                recorder.stop(); self.recorder = nil; stopSampling(); publishTurn(); deactivateAudio(); return
            }
            if turn.phase == .countdown {
                meter.graceProgress = min(1, max(0, ((turn.deadline ?? now()) - now()) / VoiceTurn.grace))
            } else { meter.graceProgress = 0 }
            publishTurn()
        } else if let player, player.isPlaying, !paused {
            player.updateMeters()
            meter.level = envelope.sample(averageDB: player.averagePower(forChannel: 0), peakDB: player.peakPower(forChannel: 0))
        } else { meter.level = envelope.sample(averageDB: -160, peakDB: -160) }
    }

    func finish(client: any GatewayClient, sessionID: String, model: TranscriptionChoice? = nil) async -> String? {
        guard let file, turn.claimForTranscription() else { return nil }
        let epoch = generation; publishTurn(); stopSampling()
        defer { if epoch == generation { turn.cancel(); publishTurn(); try? storage.discard(file); self.file = nil; deactivateAudio() } }
        do {
            let data = try Data(contentsOf: file)
            try Task.checkCancellation(); guard epoch == generation else { return nil }
            let text = try await client.transcribe(wav: data, sessionId: sessionID, model: model).trimmingCharacters(in: .whitespacesAndNewlines)
            try Task.checkCancellation(); guard epoch == generation else { return nil }
            guard !text.isEmpty else { error = "Nothing heard. Tap the orb to try again."; return nil }
            return text
        } catch {
            if epoch == generation, !(error is CancellationError) { self.error = error.localizedDescription; if error as? GatewayError == .unauthorized { onUnauthorized?() } }
            return nil
        }
    }

    func read(_ text: String, client: any GatewayClient, scope: SpeechScope, choice: VoiceChoice? = nil, speed: Double = 1, messageID: String? = nil) {
        stop(); error = nil
        let text = SpeechText.plain(text).trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        speaking = true; preparing = true; readingID = messageID; startSampling()
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
                    player.enableRate = true; player.rate = Float(PhonePreferences.validSpeed(speed)); preparing = false
                    player.prepareToPlay(); if !paused, !player.play() { throw CocoaError(.fileReadCorruptFile) }
                    while player.isPlaying || paused { try await Task.sleep(for: .milliseconds(30)) }
                }
            } catch { if epoch == generation, !(error is CancellationError) { self.error = error.localizedDescription; if error as? GatewayError == .unauthorized { onUnauthorized?() } } }
            if epoch == generation { speaking = false; preparing = false; paused = false; readingID = nil; stopSampling(); player = nil; deactivateAudio() }
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
    private func stopSampling() { sampler?.cancel(); sampler = nil; envelope.reset(); microphoneEnvelope.reset(); meter.level = 0; meter.graceProgress = 0 }
    private func deactivateAudio() { if configureAudio { try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation) } }
    func togglePause() { if paused { player?.play(); paused = false } else { player?.pause(); paused = true } }
    func stop() {
        generation += 1; stopSampling(); turn.cancel(); activity = SpeechActivity(); publishTurn(); readingID = nil
        captureTask?.cancel(); captureTask = nil; playback?.cancel(); playback = nil
        recorder?.stop(); recorder = nil; player?.stop(); player = nil
        speaking = false; preparing = false; paused = false
        if let file { try? storage.discard(file) }; file = nil; deactivateAudio()
    }
}
