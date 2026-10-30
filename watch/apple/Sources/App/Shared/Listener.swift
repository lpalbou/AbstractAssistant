@preconcurrency import AVFoundation
import AbstractGatewayClient
import CryptoKit
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
    #if DEBUG
    static let silentForTests = ProcessInfo.processInfo.arguments.contains("--silent-mic")
    #endif
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
                // A session using the microphone mutes haptics by default: the one that says the
                // microphone is open would never be felt.
                try? session.setAllowHapticsAndSystemSoundsDuringRecording(true)
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

    /// Ends the turn now (Send, or a tap on the orb): sends what was said, if anything. Before the
    /// microphone has opened, there is nothing to send and the turn ends with nothing heard.
    func send() {
        if isListening { end(); return }
        guard finish != nil else { return }
        stop(deliver: false, keepCallback: true)
        deliver(.nothingHeard)
    }

    /// Discards the recording.
    func cancel() { stop(deliver: false) }

    private func tick() {
        guard let frame = tap?.latest else { return }
        let db = Double(frame.db)
        let elapsed = Date().timeIntervalSince(startedAt)
        // The first half second sets the room's floor; it then follows the quietest moments slowly.
        if elapsed < 0.5 { floorDB = min(floorDB == -50 ? db : floorDB, db) }
        else if db < floorDB { floorDB = 0.9 * floorDB + 0.1 * db }
        var speaking = elapsed > 0.5 && db > max(floorDB + 12, -48)
        #if DEBUG
        // `--silent-mic` (UI tests that assert "nothing heard"): the simulator records through the
        // Mac's real microphone, so a noise in the room was taken for speech and sent as a question
        // (SendNowUITests failed 5 of 8 on main, 2026-10-29). Debug builds only.
        if Self.silentForTests { speaking = false }
        #endif
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

/// A failed voice question belongs to the conversation where it was recorded. Each
/// conversation keeps at most one recording until it is retried or discarded.
@MainActor enum KeptQuestion {
    private static let key = "ask.keptRecording"
    private static var folder: URL { URL.applicationSupportDirectory.appending(path: "KeptQuestion", directoryHint: .isDirectory) }
    private static var records: [String: [String: String]] {
        get { UserDefaults.standard.dictionary(forKey: key) as? [String: [String: String]] ?? [:] }
        set { UserDefaults.standard.set(newValue, forKey: key) }
    }

    static func connectionKey(gateway: URL, user: String?, tenant: String?, credential: GatewayCredential) -> String {
        var address = URLComponents(url: gateway, resolvingAgainstBaseURL: false) ?? URLComponents()
        address.scheme = address.scheme?.lowercased()
        address.host = address.host?.lowercased()
        address.user = nil; address.password = nil; address.query = nil; address.fragment = nil
        if (address.scheme == "https" && address.port == 443) || (address.scheme == "http" && address.port == 80) { address.port = nil }
        while address.percentEncodedPath.hasSuffix("/") { address.percentEncodedPath.removeLast() }
        func digest(_ bytes: Data) -> String { SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined() }
        let principal: String
        if let user = user?.trimmingCharacters(in: .whitespacesAndNewlines), !user.isEmpty,
           let tenant = tenant?.trimmingCharacters(in: .whitespacesAndNewlines), !tenant.isEmpty {
            principal = "principal:\(tenant.utf8.count):\(tenant)\(user)"
        } else {
            let material: String
            switch credential { case .token(let token): material = token; case .session(let id, _): material = id }
            principal = "credential:" + digest(Data(material.utf8))
        }
        let gatewayIdentity = address.string ?? ""
        return digest(Data("\(gatewayIdentity.utf8.count):\(gatewayIdentity)\(principal)".utf8))
    }

    static func conversationScope(connectionKey: String, sessionId: String, responder: String) -> String {
        "\(connectionKey):chat:\(sessionId.utf8.count):\(sessionId):\(responder)"
    }
    static func automationScope(connectionKey: String, _ id: String) -> String { "\(connectionKey):automation:\(id)" }

    /// Bind an older unscoped recording once, before navigation changes the saved session.
    /// The last saved session is the best available context, not proof of its original owner.
    static func migrateLegacy(sessionId: String?, connectionKey: String) {
        guard let filename = UserDefaults.standard.string(forKey: key) else { return }
        let saved = sessionId?.trimmingCharacters(in: .whitespacesAndNewlines)
        let id = saved.flatMap { $0.isEmpty ? nil : $0 } ?? "watch-recovered-" + UUID().uuidString.lowercased()
        if saved == nil || saved?.isEmpty == true { UserDefaults.standard.set(id, forKey: "ask.session") }
        let storedResponder = UserDefaults.standard.string(forKey: "ask.responder") ?? "assistant"
        let responder = storedResponder.hasPrefix("entity:") ? storedResponder : "assistant"
        records = [conversationScope(connectionKey: connectionKey, sessionId: id, responder: responder): ["filename": filename, "session": id]]
    }

    static func url(for scope: String) -> URL? {
        guard let filename = records[scope]?["filename"] else { return nil }
        let file = folder.appending(path: filename)
        guard FileManager.default.fileExists(atPath: file.path) else {
            var current = records; current.removeValue(forKey: scope); records = current
            return nil
        }
        return file
    }

    static func session(for scope: String) -> String? { records[scope]?["session"] }

    static func keep(_ wav: Data, scope: String, sessionId: String) -> URL? {
        var file = folder.appending(path: "question-\(UUID().uuidString).wav")
        do {
            try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
            try wav.write(to: file, options: .atomic)
        } catch { return nil }
        var values = URLResourceValues(); values.isExcludedFromBackup = true
        try? file.setResourceValues(values)
        let previous = url(for: scope)
        var current = records
        current[scope] = ["filename": file.lastPathComponent, "session": sessionId]
        records = current
        if let previous, previous != file { try? FileManager.default.removeItem(at: previous) }
        return file
    }

    /// A late result must not replace a newer recording created while it was waiting.
    static func keep(_ wav: Data, scope: String, sessionId: String, replacing expected: URL?) -> URL? {
        guard url(for: scope) == expected else { return nil }
        return keep(wav, scope: scope, sessionId: sessionId)
    }

    /// An older request cannot discard a newer recording, or another conversation's.
    static func discard(scope: String, matching file: URL? = nil) {
        guard let existing = url(for: scope), file == nil || existing == file else { return }
        try? FileManager.default.removeItem(at: existing)
        var current = records; current.removeValue(forKey: scope); records = current
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

#if DEBUG
/// A recording for the tests: 16 kHz mono 16-bit WAV of a soft tone (the mock transcribes any
/// audio to its sample question). Debug builds only.
enum SyntheticSpeech {
    static func wav(seconds: Double, seed: Int) -> Data {
        let rate = 16_000, n = Int(seconds * Double(rate))
        var samples = Data(capacity: n * 2)
        let f = 180.0 + Double(seed % 7) * 20
        for i in 0..<n {
            let t = Double(i) / Double(rate)
            let env = min(1, t * 8) * min(1, (seconds - t) * 8)
            let v = Int16(env * 6000 * sin(2 * .pi * f * t) * (0.6 + 0.4 * sin(2 * .pi * 3 * t)))
            samples.append(contentsOf: withUnsafeBytes(of: v.littleEndian) { Array($0) })
        }
        var d = Data()
        func u32(_ v: UInt32) { d.append(contentsOf: withUnsafeBytes(of: v.littleEndian) { Array($0) }) }
        func u16(_ v: UInt16) { d.append(contentsOf: withUnsafeBytes(of: v.littleEndian) { Array($0) }) }
        d.append(contentsOf: Array("RIFF".utf8)); u32(UInt32(36 + samples.count)); d.append(contentsOf: Array("WAVE".utf8))
        d.append(contentsOf: Array("fmt ".utf8)); u32(16); u16(1); u16(1); u32(UInt32(rate)); u32(UInt32(rate * 2)); u16(2); u16(16)
        d.append(contentsOf: Array("data".utf8)); u32(UInt32(samples.count)); d.append(samples)
        return d
    }
}
#endif
