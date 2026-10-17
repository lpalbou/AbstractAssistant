@preconcurrency import AVFoundation
import SwiftUI
import WatchKit

/// The microphone, for Ask: records 16 kHz mono WAV with metering, tells speech from the room's
/// noise floor, and ends by itself `silenceToSend` seconds after the person stops speaking (or after
/// `waitForSpeech` seconds when nothing was ever heard).
@MainActor
final class Listener: ObservableObject {
    enum Outcome { case speech(Data), nothingHeard, failed(String) }

    /// Seconds of silence that end a turn (the operator's rule: 3 s, or a tap on the orb).
    static let silenceToSend: TimeInterval = 3
    /// Time to start speaking after the tap before listening gives up.
    static let waitForSpeech: TimeInterval = 5
    static let maxDuration: TimeInterval = 60

    @Published private(set) var isListening = false
    @Published private(set) var heardSpeech = false

    private var recorder: AVAudioRecorder?
    private var loop: Task<Void, Never>?
    private var finish: ((Outcome) -> Void)?
    private var level: Double = 0
    private var floorDB: Double = -50
    private var startedAt = Date()
    /// Bumped by every start/stop: a setup that finishes after Cancel or Back never records.
    private var generation = 0
    private var lastSpeech = Date()
    private let url = FileManager.default.temporaryDirectory.appending(path: "ask.wav")

    /// 0…1 loudness of what the microphone hears, smoothed; read by the orb every frame.
    func currentLevel() -> Double { level }

    /// 0 while you speak, rising to 1 over the silence that sends (the orb draws it as a countdown).
    func sendProgress() -> Double {
        guard isListening, heardSpeech else { return 0 }
        return min(1, max(0, (Date().timeIntervalSince(lastSpeech) - 0.4) / (Self.silenceToSend - 0.4)))
    }

    /// Starts recording; `done` is called once, with the audio, "nothing heard" or the failure.
    func start(done: @escaping (Outcome) -> Void) {
        stop(deliver: false)
        finish = done
        let mine = generation
        Task {
            let allowed = await AVAudioApplication.requestRecordPermission()
            guard mine == generation else { return }          // cancelled while asking
            guard allowed else {
                deliver(.failed("Microphone access is off: Settings → Privacy & Security → Microphone → Assistant."))
                return
            }
            do {
                let session = AVAudioSession.sharedInstance()
                try session.setCategory(.record, mode: .default, options: [])
                try session.setActive(true)
                let settings: [String: Any] = [AVFormatIDKey: kAudioFormatLinearPCM, AVSampleRateKey: 16_000,
                                               AVNumberOfChannelsKey: 1, AVLinearPCMBitDepthKey: 16,
                                               AVLinearPCMIsFloatKey: false, AVLinearPCMIsBigEndianKey: false]
                let r = try AVAudioRecorder(url: url, settings: settings)
                r.isMeteringEnabled = true
                guard r.record() else { throw CocoaError(.fileWriteUnknown) }
                recorder = r
                isListening = true; heardSpeech = false; level = 0; floorDB = -50
                RuntimeKeeper.shared.hold("listen")
                WKInterfaceDevice.current().play(.start)       // the microphone is open
                startedAt = Date(); lastSpeech = Date()
                loop = Task {
                    // Strong until cancelled: stop() and end() cancel it.
                    while !Task.isCancelled {
                        try? await Task.sleep(for: .milliseconds(50))
                        self.tick()
                    }
                }
            } catch {
                deliver(.failed("The microphone could not start: \(error.localizedDescription)"))
            }
        }
    }

    /// Ends the turn now (the orb was tapped): sends what was said, if anything.
    func send() { end() }

    /// Discards the recording.
    func cancel() { stop(deliver: false) }

    private func tick() {
        guard let recorder, recorder.isRecording else { return }
        recorder.updateMeters()
        let db = Double(recorder.averagePower(forChannel: 0))
        let elapsed = Date().timeIntervalSince(startedAt)
        // The first half second sets the room's floor; it then follows the quietest moments slowly.
        if elapsed < 0.5 { floorDB = min(floorDB == -50 ? db : floorDB, db) }
        else if db < floorDB { floorDB = 0.9 * floorDB + 0.1 * db }
        let speaking = elapsed > 0.5 && db > max(floorDB + 12, -48)
        let linear = max(0, min(1, (db - floorDB - 4) / 30))
        level = linear > level ? 0.6 * linear + 0.4 * level : 0.3 * linear + 0.7 * level
        if speaking {
            if !heardSpeech { heardSpeech = true }
            lastSpeech = Date()
        }
        let quiet = Date().timeIntervalSince(lastSpeech)
        if quiet >= (heardSpeech ? Self.silenceToSend : Self.waitForSpeech) || elapsed >= Self.maxDuration { end() }
    }

    private func end() {
        guard isListening else { return }
        let spoke = heardSpeech
        recorder?.stop()
        let data = spoke ? (try? Data(contentsOf: url)) : nil
        stop(deliver: false, keepCallback: true)
        if let data, data.count > 44 { deliver(.speech(data)) } else { deliver(.nothingHeard) }
    }

    private func stop(deliver shouldDeliver: Bool, keepCallback: Bool = false) {
        generation += 1
        loop?.cancel(); loop = nil
        recorder?.stop(); recorder = nil
        if isListening { isListening = false }
        level = 0
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        RuntimeKeeper.shared.release("listen")
        if !shouldDeliver && !keepCallback { finish = nil }
    }

    private func deliver(_ outcome: Outcome) {
        let f = finish; finish = nil
        f?(outcome)
    }
}
