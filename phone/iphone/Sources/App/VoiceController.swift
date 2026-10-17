@preconcurrency import AVFoundation
import Observation
import AbstractGatewayClient

@MainActor @Observable final class AudioMeter { var level: Double = 0 }

@MainActor @Observable final class VoiceController {
    let meter = AudioMeter()
    @ObservationIgnored private var meterTimer: Timer?
    private(set) var readingID: String?
    private(set) var recording = false
    private(set) var transcribing = false
    private(set) var speaking = false
    private(set) var paused = false
    private(set) var limitReached = false
    var error: String?
    @ObservationIgnored var onUnauthorized: (() -> Void)?
    @ObservationIgnored private var recorder: AVAudioRecorder?
    @ObservationIgnored private var player: AVAudioPlayer?
    @ObservationIgnored private var playback: Task<Void, Never>?
    @ObservationIgnored private var recordingLimit: Task<Void, Never>?
    @ObservationIgnored private var generation = 0
    @ObservationIgnored private let file = FileManager.default.temporaryDirectory.appending(path: "iphone-voice-\(UUID().uuidString).wav")

    func start() async {
        stop(); error = nil
        let epoch = generation
        guard await AVAudioApplication.requestRecordPermission() else { error = "Microphone access is off. You can enable it in iPhone Settings."; return }
        guard epoch == generation else { return }
        do {
            let audio = AVAudioSession.sharedInstance()
            try audio.setCategory(.record, mode: .measurement); try audio.setActive(true)
            let recorder = try AVAudioRecorder(url: file, settings: [AVFormatIDKey: kAudioFormatLinearPCM, AVSampleRateKey: 16_000,
                AVNumberOfChannelsKey: 1, AVLinearPCMBitDepthKey: 16, AVLinearPCMIsFloatKey: false, AVLinearPCMIsBigEndianKey: false])
            recorder.isMeteringEnabled = true
            self.recorder = recorder
            guard recorder.record(forDuration: 60) else { throw CocoaError(.fileWriteUnknown) }
            recording = true; startMetering()
            recordingLimit = Task {
                try? await Task.sleep(for: .seconds(60))
                guard !Task.isCancelled, epoch == generation, recording else { return }
                recorder.stop(); limitReached = true
            }
        } catch { self.error = "The microphone couldn’t start. You can still type your message."; stop() }
    }
    func finish(client: any GatewayClient, sessionID: String, model: TranscriptionChoice? = nil) async -> String? {
        let epoch = generation
        recordingLimit?.cancel(); recordingLimit = nil
        recorder?.stop(); recorder = nil; stopMetering(); recording = false; transcribing = true
        defer {
            if epoch == generation { transcribing = false }
            if epoch == generation {
                try? FileManager.default.removeItem(at: file)
                try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
            }
        }
        do {
            let data = try Data(contentsOf: file)
            let text = try await client.transcribe(wav: data, sessionId: sessionID, model: model)
            guard epoch == generation else { return nil }
            if text.isEmpty { error = "Nothing heard. Try again, or type your message."; return nil }
            return text
        } catch { if epoch == generation { self.error = error.localizedDescription; if error as? GatewayError == .unauthorized { onUnauthorized?() } }; return nil }
    }
    func read(_ text: String, client: any GatewayClient, scope: SpeechScope, choice: VoiceChoice? = nil, messageID: String? = nil) {
        stop(); error = nil
        let text = SpeechText.plain(text).trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        speaking = true; readingID = messageID; startMetering()
        let epoch = generation
        playback = Task {
            do {
                let audio = AVAudioSession.sharedInstance()
                try audio.setCategory(.playback, mode: .spokenAudio); try audio.setActive(true)
                for try await chunk in client.speech(text: text, scope: scope, voice: { if case .run = scope { choice } else { nil } }()) {
                    try Task.checkCancellation()
                    guard epoch == generation else { return }
                    let player = try AVAudioPlayer(data: chunk); player.isMeteringEnabled = true; self.player = player
                    player.prepareToPlay(); if !paused { player.play() }
                    while player.isPlaying || paused { try await Task.sleep(for: .milliseconds(100)) }
                }
            } catch { if epoch == generation, !(error is CancellationError) { self.error = error.localizedDescription; if error as? GatewayError == .unauthorized { onUnauthorized?() } } }
            if epoch == generation { speaking = false; paused = false; readingID = nil; stopMetering(); player = nil; try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation) }
        }
    }
    private func startMetering() {
        stopMetering()
        meterTimer = Timer.scheduledTimer(withTimeInterval: 0.04, repeats: true) { [weak self] _ in
            Task { @MainActor in
                guard let self else { return }
                let db: Float
                if let recorder = self.recorder, self.recording { recorder.updateMeters(); db = recorder.averagePower(forChannel: 0) }
                else if let player = self.player, player.isPlaying, !self.paused { player.updateMeters(); db = player.averagePower(forChannel: 0) }
                else { db = -160 }
                let target = min(1, max(0, (Double(db) + 55) / 45))
                self.meter.level = target > self.meter.level ? target : self.meter.level * 0.65 + target * 0.35
            }
        }
    }
    private func stopMetering() { meterTimer?.invalidate(); meterTimer = nil; meter.level = 0 }
    func togglePause() { if paused { player?.play(); paused = false } else { player?.pause(); paused = true } }
    func stop() {
        generation += 1; stopMetering(); readingID = nil; playback?.cancel(); playback = nil
        recordingLimit?.cancel(); recordingLimit = nil
        recorder?.stop(); recorder = nil; player?.stop(); player = nil
        recording = false; transcribing = false; speaking = false; paused = false
        limitReached = false
        try? FileManager.default.removeItem(at: file)
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }
}
