@preconcurrency import AVFoundation
import SwiftUI
import WatchKit

/// The microphone, for Ask: records 16 kHz mono WAV, analyses the voice as it comes (loudness and
/// spectrum, for the orb), tells speech from the room's noise floor, and ends by itself
/// `silenceToSend` seconds after the person stops speaking (or after `waitForSpeech` seconds when
/// nothing was ever heard).
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

    private var tap: MicTap?
    private let normalizer = VoiceNormalizer()
    private var loop: Task<Void, Never>?
    private var finish: ((Outcome) -> Void)?
    private var floorDB: Double = -50
    private var startedAt = Date()
    /// Bumped by every start/stop: a setup that finishes after Cancel or Back never records.
    private var generation = 0
    private var lastSpeech = Date()
    private let url = FileManager.default.temporaryDirectory.appending(path: "ask.wav")

    /// What the orb follows: the microphone's latest frame, scaled to the voice's recent range.
    func features(at t: Double) -> VoiceFeatures {
        guard isListening, let frame = tap?.latest else { return normalizer.push(.silent, at: t) }
        let f = normalizer.push(frame, at: t)
        #if DEBUG
        peakLevel = max(peakLevel, f.level)
        #endif
        return f
    }
    #if DEBUG
    private var peakLevel = 0.0
    #endif

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
                deliver(.failed("Allow the microphone in Settings."))
                return
            }
            do {
                let session = AVAudioSession.sharedInstance()
                try session.setCategory(.record, mode: .default, options: [])
                try session.setActive(true)
                tap = try MicTap(writingTo: url)
                isListening = true; heardSpeech = false; floorDB = -50
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
                deliver(.failed("The microphone isn't available."))
            }
        }
    }

    /// Ends the turn now (the orb was tapped): sends what was said, if anything.
    func send() { end() }

    /// Discards the recording.
    func cancel() { stop(deliver: false) }

    private func tick() {
        guard let frame = tap?.latest else { return }
        let db = Double(frame.db)
        let elapsed = Date().timeIntervalSince(startedAt)
        // The first half second sets the room's floor; it then follows the quietest moments slowly.
        if elapsed < 0.5 { floorDB = min(floorDB == -50 ? db : floorDB, db) }
        else if db < floorDB { floorDB = 0.9 * floorDB + 0.1 * db }
        let speaking = elapsed > 0.5 && db > max(floorDB + 12, -48)
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
        tap?.stop(); tap = nil                    // closes the file (its WAV header is written then)
        let data = spoke ? (try? Data(contentsOf: url)) : nil
        #if DEBUG
        print("listener: \(spoke ? "speech" : "nothing heard"), wav \(data?.count ?? 0) bytes, peak features level \(String(format: "%.2f", peakLevel))")
        #endif
        stop(deliver: false, keepCallback: true)
        if let data, data.count > 44 { deliver(.speech(data)) } else { deliver(.nothingHeard) }
    }

    private func stop(deliver shouldDeliver: Bool, keepCallback: Bool = false) {
        generation += 1
        loop?.cancel(); loop = nil
        tap?.stop(); tap = nil
        if isListening { isListening = false }
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        RuntimeKeeper.shared.release("listen")
        if !shouldDeliver && !keepCallback { finish = nil }
    }

    private func deliver(_ outcome: Outcome) {
        let f = finish; finish = nil
        f?(outcome)
    }
}

/// The microphone through AVAudioEngine: each buffer is analysed (the latest frame is kept for the
/// listener's speech detection and the orb) and written as 16 kHz mono 16-bit WAV for transcription.
/// The tap runs on the audio thread; `latest` is read from the main actor under a lock.
final class MicTap: @unchecked Sendable {
    private let engine = AVAudioEngine()
    private var file: AVAudioFile?
    private let converter: AVAudioConverter
    private let outFormat: AVAudioFormat
    private let analyzer: VoiceAnalyzer
    private let lock = NSLock()
    private var frame: VoiceFrame?

    var latest: VoiceFrame? { lock.withLock { frame } }

    init(writingTo url: URL) throws {
        let input = engine.inputNode
        let inFormat = input.outputFormat(forBus: 0)
        guard inFormat.sampleRate > 0, inFormat.channelCount > 0,
              let out = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: 16_000, channels: 1, interleaved: true),
              let conv = AVAudioConverter(from: inFormat, to: out) else { throw CocoaError(.fileWriteUnknown) }
        outFormat = out
        converter = conv
        analyzer = VoiceAnalyzer(sampleRate: inFormat.sampleRate)
        try? FileManager.default.removeItem(at: url)
        file = try AVAudioFile(forWriting: url, settings: out.settings, commonFormat: .pcmFormatInt16, interleaved: true)
        input.installTap(onBus: 0, bufferSize: AVAudioFrameCount(analyzer.size), format: inFormat) { [weak self] buffer, _ in
            self?.take(buffer)
        }
        engine.prepare()
        try engine.start()
    }

    private func take(_ buffer: AVAudioPCMBuffer) {
        if let ch = buffer.floatChannelData?[0] {
            let n = Int(buffer.frameLength)
            let f = analyzer.analyze(Array(UnsafeBufferPointer(start: ch, count: n))[...])
            lock.withLock { frame = f }
        }
        let ratio = outFormat.sampleRate / buffer.format.sampleRate
        guard let out = AVAudioPCMBuffer(pcmFormat: outFormat, frameCapacity: AVAudioFrameCount(Double(buffer.frameLength) * ratio) + 32) else { return }
        var fed = false
        var error: NSError?
        converter.convert(to: out, error: &error) { _, status in
            if fed { status.pointee = .noDataNow; return nil }
            fed = true; status.pointee = .haveData; return buffer
        }
        if error == nil, out.frameLength > 0 { lock.withLock { try? file?.write(from: out) } }
    }

    func stop() {
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        lock.withLock { file = nil }
    }
}
