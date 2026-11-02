@preconcurrency import AVFoundation
import Observation
import OSLog
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
final class AudioSessionEvents: @unchecked Sendable {
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

/// The level of the sound going out, measured on the engine's render thread (a tap) and read by
/// the meter's sampler on the main actor.
private final class OutputLevels: @unchecked Sendable {
    private let lock = NSLock()
    private var values: (average: Float, peak: Float) = (-160, -160)
    var current: (average: Float, peak: Float) { lock.withLock { values } }
    func update(_ buffer: AVAudioPCMBuffer) {
        guard let data = buffer.floatChannelData, buffer.frameLength > 0 else { return }
        var sum: Float = 0, peak: Float = 0
        let samples = data[0]
        for i in 0..<Int(buffer.frameLength) { let s = samples[i]; sum += s * s; peak = max(peak, abs(s)) }
        let rms = (sum / Float(buffer.frameLength)).squareRoot()
        let db = { (a: Float) -> Float in a > 0 ? max(-160, 20 * log10(a)) : -160 }
        lock.withLock { values = (db(rms), db(peak)) }
    }
    func reset() { lock.withLock { values = (-160, -160) } }
}

/// Speaking a reply: the text is requested in pieces (`SpeechText.pieces`, about 600 characters,
/// one stream at a time, the next while under `aheadSeconds` of sound waits), so a piece whose
/// stream breaks is requested again while what arrived plays, and a reading that still fails ends
/// with "The voice stopped early" and goes on from that piece when the same message is read again
/// (2026-11-01: one request for ten minutes of audio was lost whole when the link went quiet for
/// 90 s). The sound plays through one AVAudioEngine graph (player node → time pitch → mixer): every
/// streamed chunk is scheduled on the node as it arrives, back to back, sample-contiguous — no gap
/// between the engine's short chunks (an AVAudioPlayer per chunk had an audible cut at each).
@MainActor @Observable final class VoiceController {
    let meter = AudioMeter()
    private(set) var inputPhase: VoiceTurn.Phase = .idle
    private(set) var secondsRemaining = 3
    private(set) var readingID: String?
    private(set) var preparing = false
    var playbackRate: Float { speaking ? pitch.rate : 1 }
    private(set) var speaking = false
    private(set) var paused = false
    var recording: Bool { inputPhase == .recording || inputPhase == .countdown }
    var transcribing: Bool { inputPhase == .transcribing }
    var localPending: Bool { inputPhase == .authorizing || inputPhase == .recording || inputPhase == .countdown || inputPhase == .ready }
    var inputPending: Bool { inputPhase != .idle }
    var error: String?
    /// Seconds of the reading played back so far (tests read it).
    @ObservationIgnored private(set) var playedSeconds: Double = 0
    @ObservationIgnored var onUnauthorized: (() -> Void)?
    @ObservationIgnored private var turn = VoiceTurn()
    @ObservationIgnored private var envelope = AudioEnvelope()
    @ObservationIgnored private var microphoneEnvelope = MicrophoneEnvelope()
    @ObservationIgnored private var activity = SpeechActivity()
    @ObservationIgnored private var sampler: Task<Void, Never>?
    @ObservationIgnored private var captureTask: Task<Void, Never>?
    @ObservationIgnored private var recorder: (any VoiceRecording)?
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

    // The engine graph and what is scheduled on it.
    @ObservationIgnored private let engine = AVAudioEngine()
    @ObservationIgnored private let node = AVAudioPlayerNode()
    @ObservationIgnored private let pitch = AVAudioUnitTimePitch()
    @ObservationIgnored private let levels = OutputLevels()
    @ObservationIgnored private var nodeFormat: AVAudioFormat?
    @ObservationIgnored private var tapInstalled = false
    private struct Scheduled { let id: Int; let piece: Int; let buffer: AVAudioPCMBuffer; let seconds: Double }
    /// Scheduled on the node and not yet played back, in order (the first is the one playing).
    @ObservationIgnored private var inFlight: [Scheduled] = []
    @ObservationIgnored private var nextID = 0
    /// Bumped when the node is reset: completions of buffers scheduled before are ignored.
    @ObservationIgnored private var scheduleEpoch = 0
    /// Frames of buffers fully played back since the node last started from a reset.
    @ObservationIgnored private var playedFramesSinceStart: AVAudioFramePosition = 0
    @ObservationIgnored private var pieces: [String] = []
    @ObservationIgnored private var nextPiece = 0
    @ObservationIgnored private var streamDone = false
    @ObservationIgnored private var stoppedEarly: Error?
    @ObservationIgnored private var readText = ""
    /// A reading that stopped early: `read` of the same message (or text) goes on from `next`.
    @ObservationIgnored private var resumable: (text: String, messageID: String?, pieces: [String], next: Int)?
    @ObservationIgnored private let pieceTarget: Int
    /// Sound waiting to play beyond which the next piece is not requested yet.
    private static let aheadSeconds = 45.0
    /// Requests of one piece after its first failed, 2 s apart.
    private static let retries = 3
    private static let log = Logger(subsystem: "ai.abstractframework.assistant", category: "voice")

    init(now: @escaping () -> TimeInterval = { ProcessInfo.processInfo.systemUptime },
         permission: @escaping () async -> Bool = { await AVAudioApplication.requestRecordPermission() },
         recordingFactory: @escaping (URL) throws -> any VoiceRecording = { try MicrophoneRecording(url: $0) },
         configureAudio: Bool = true,
         isActive: @escaping () -> Bool = { UIApplication.shared.applicationState == .active },
         pieceTarget: Int = 600) {
        self.now = now; self.permission = permission; self.recordingFactory = recordingFactory; self.configureAudio = configureAudio
        self.isActive = isActive; self.pieceTarget = max(1, pieceTarget)
        engine.attach(node); engine.attach(pitch)
        pitch.pitch = 0
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
        } else if speaking, !paused, !inFlight.isEmpty, node.isPlaying {
            let out = levels.current
            meter.level = envelope.sample(averageDB: out.average, peakDB: out.peak)
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

    /// Reads `text` aloud. The same message (or text) read again after "The voice stopped early"
    /// goes on from the piece that was lost, not from the start.
    func read(_ text: String, client: any GatewayClient, scope: SpeechScope, choice: VoiceChoice? = nil, speed: Double = 1, messageID: String? = nil) {
        let plain = SpeechText.plain(text).trimmingCharacters(in: .whitespacesAndNewlines)
        let resume = resumable.flatMap { r in r.text == plain && (messageID == nil || r.messageID == messageID) ? r : nil }
        stop(); error = nil; resumable = nil
        guard !plain.isEmpty else { return }
        pieces = resume?.pieces ?? SpeechText.pieces(plain, target: pieceTarget, cap: pieceTarget * 4 / 3)
        nextPiece = resume?.next ?? 0
        streamDone = false; stoppedEarly = nil; playedSeconds = 0; readText = plain
        pitch.rate = Float(PhonePreferences.validSpeed(speed))
        speaking = true; preparing = true; readingID = messageID; startSampling()
        Self.log.info("reading \(plain.count, privacy: .public) chars in \(self.pieces.count, privacy: .public) pieces from piece \(self.nextPiece + 1, privacy: .public)")
        let epoch = generation
        let voice: VoiceChoice? = { if case .run = scope { choice } else { nil } }()
        playback = Task {
            if configureAudio {
                do {
                    let audio = AVAudioSession.sharedInstance()
                    try audio.setCategory(.playback, mode: .spokenAudio); try audio.setActive(true)
                } catch {
                    guard epoch == generation else { return }
                    self.error = error.localizedDescription; end(epoch); return
                }
            }
            let failure = await readPieces(client: client, scope: scope, voice: voice, epoch: epoch)
            guard epoch == generation else { return }
            streamDone = true; stoppedEarly = failure
            settle(epoch)                                   // nothing scheduled: the reading ends now
        }
    }

    /// Requests the pieces from `nextPiece` on, one stream at a time, the next once less than
    /// `aheadSeconds` of sound waits. A piece whose stream breaks (the link, the gateway) is
    /// requested again up to `retries` times, 2 s apart, while the sound already here plays; its
    /// chunks not yet played are dropped first, so nothing is heard twice.
    /// Returns the error that ended the reading, nil once every piece has arrived.
    private func readPieces(client: any GatewayClient, scope: SpeechScope, voice: VoiceChoice?, epoch: Int) async -> Error? {
        while nextPiece < pieces.count {
            while aheadSeconds() >= Self.aheadSeconds {
                try? await Task.sleep(for: .milliseconds(500))
                if Task.isCancelled || epoch != generation { return nil }
            }
            let i = nextPiece
            var attempt = 0
            while true {
                attempt += 1
                Self.log.info("piece \(i + 1, privacy: .public)/\(self.pieces.count, privacy: .public) started: \(self.pieces[i].count, privacy: .public) chars, try \(attempt, privacy: .public)")
                do {
                    for try await wav in client.speech(text: pieces[i], scope: scope, voice: voice) {
                        try Task.checkCancellation(); guard epoch == generation else { return nil }
                        try enqueue(wav, piece: i, epoch: epoch)
                    }
                    break
                } catch {
                    if Task.isCancelled || error is CancellationError || epoch != generation { return nil }
                    if error is PlaybackFailure { return error }
                    dropUnplayed(piece: i)
                    Self.log.error("piece \(i + 1, privacy: .public) failed on try \(attempt, privacy: .public): \(String(describing: error), privacy: .public)")
                    guard attempt <= Self.retries, LiveGatewayClient.isTransient(error) else { return error }
                    try? await Task.sleep(for: .seconds(2))
                    if Task.isCancelled || epoch != generation { return nil }
                }
            }
            nextPiece = i + 1
        }
        return nil
    }

    /// The sound could not be decoded or the engine could not start: the reading ends with this.
    private struct PlaybackFailure: Error, LocalizedError {
        let why: String
        var errorDescription: String? { why }
    }

    /// A streamed chunk, decoded and scheduled on the node right behind what is already there.
    private func enqueue(_ wav: Data, piece: Int, epoch: Int) throws {
        guard let decoded = Self.pcmBuffer(wav: wav) else { throw PlaybackFailure(why: "This speech could not be played.") }
        if nodeFormat == nil { try startEngine(with: decoded.format) }
        guard let nodeFormat else { return }
        let buffer = try decoded.format == nodeFormat ? decoded : Self.convert(decoded, to: nodeFormat)
        schedule(Scheduled(id: nextID, piece: piece, buffer: buffer, seconds: Double(buffer.frameLength) / nodeFormat.sampleRate))
        nextID += 1
        if !paused, !node.isPlaying { node.play() }
        if preparing { preparing = false }
    }

    /// The graph for this reading, in the first chunk's format; later chunks are converted to it.
    private func startEngine(with format: AVAudioFormat) throws {
        engine.connect(node, to: pitch, format: format)
        engine.connect(pitch, to: engine.mainMixerNode, format: format)
        let levels = levels
        // Called on the engine's own queue: never main-actor isolated.
        pitch.installTap(onBus: 0, bufferSize: 1024, format: nil) { @Sendable buffer, _ in levels.update(buffer) }
        tapInstalled = true
        engine.prepare()
        do { try engine.start() } catch {
            Self.log.error("audio engine did not start: \(String(describing: error), privacy: .public)")
            throw PlaybackFailure(why: "This speech could not be played.")
        }
        nodeFormat = format
        playedFramesSinceStart = 0
    }

    private func schedule(_ s: Scheduled) {
        inFlight.append(s)
        let epoch = scheduleEpoch, id = s.id, frames = AVAudioFramePosition(s.buffer.frameLength)
        node.scheduleBuffer(s.buffer, completionCallbackType: .dataPlayedBack) { @Sendable [weak self] _ in   // the engine's queue
            Task { @MainActor [weak self] in self?.playedBack(id: id, frames: frames, epoch: epoch) }
        }
    }

    private func playedBack(id: Int, frames: AVAudioFramePosition, epoch: Int) {
        guard epoch == scheduleEpoch, let i = inFlight.firstIndex(where: { $0.id == id }) else { return }
        let s = inFlight.remove(at: i)
        playedSeconds += s.seconds
        playedFramesSinceStart += frames
        settle(generation)
    }

    /// Nothing scheduled: the reading waits for the stream, or ends once the stream is over.
    private func settle(_ epoch: Int) {
        guard epoch == generation, speaking else { return }
        let waiting = inFlight.isEmpty && !streamDone
        if preparing != waiting { preparing = waiting }
        if inFlight.isEmpty, streamDone { end(epoch) }
    }

    /// Frames of the playing buffer already rendered (the node's time since it last started).
    private func playheadFrames() -> AVAudioFramePosition {
        guard let nodeTime = node.lastRenderTime, let time = node.playerTime(forNodeTime: nodeTime) else { return 0 }
        return max(0, time.sampleTime - playedFramesSinceStart)
    }

    /// Seconds of sound scheduled and not yet played.
    private func aheadSeconds() -> Double {
        guard let nodeFormat else { return 0 }
        let total = inFlight.reduce(0) { $0 + $1.seconds }
        return max(0, total - Double(playheadFrames()) / nodeFormat.sampleRate) / Double(pitch.rate)
    }

    /// A piece's chunks not yet played (the request is made again: they would be heard twice). The
    /// node is reset and what is kept is scheduled again: the rest of the chunk under way, then the
    /// other pieces' chunks, in order.
    private func dropUnplayed(piece i: Int) {
        guard inFlight.contains(where: { $0.piece == i }) else { return }
        let offset = playheadFrames()
        var keep: [Scheduled] = []
        for (n, s) in inFlight.enumerated() where s.piece != i {
            if n == 0, offset > 0 {
                guard let rest = Self.remainder(of: s.buffer, from: offset), let nodeFormat else { continue }
                keep.append(Scheduled(id: s.id, piece: s.piece, buffer: rest, seconds: Double(rest.frameLength) / nodeFormat.sampleRate))
            } else { keep.append(s) }
        }
        let dropped = inFlight.count - keep.count
        if let first = inFlight.first, first.piece != i, let nodeFormat { playedSeconds += Double(offset) / nodeFormat.sampleRate }   // the part heard
        scheduleEpoch += 1
        node.stop(); node.reset()
        inFlight.removeAll(); playedFramesSinceStart = 0
        for s in keep { schedule(s) }
        if !paused, !keep.isEmpty { node.play() }
        Self.log.info("dropped \(dropped, privacy: .public) unplayed chunks of piece \(i + 1, privacy: .public), \(keep.count, privacy: .public) kept")
    }

    /// The reading is over: what it ended with, in the person's words (the reason is in the log).
    private func end(_ epoch: Int) {
        guard epoch == generation else { return }
        if let failure = stoppedEarly {
            if failure is PlaybackFailure {
                error = failure.localizedDescription
            } else if LiveGatewayClient.isTransient(failure) {
                resumable = (readText, readingID, pieces, nextPiece)
                error = playedSeconds > 0 ? "The voice stopped early. Tap play to continue." : "The voice could not start. Tap play to try again."
                Self.log.error("voice stopped at piece \(self.nextPiece + 1, privacy: .public)/\(self.pieces.count, privacy: .public) after \(self.playedSeconds, format: .fixed(precision: 1), privacy: .public) s: \(String(describing: failure), privacy: .public)")
            } else {
                error = failure.localizedDescription
                if failure as? GatewayError == .unauthorized { onUnauthorized?() }
            }
        }
        speaking = false; preparing = false; paused = false; readingID = nil; stopSampling()
        stopEngine(); deactivateAudio()
    }

    private func stopEngine() {
        scheduleEpoch += 1
        node.stop(); node.reset()
        if tapInstalled { pitch.removeTap(onBus: 0); tapInstalled = false }
        if engine.isRunning { engine.stop() }
        inFlight.removeAll(); nodeFormat = nil; playedFramesSinceStart = 0; levels.reset()
    }

    // MARK: WAV → PCM buffers

    /// A WAV (16-bit PCM or 32-bit float, any channel count) as a Float32 buffer in its own rate.
    private static func pcmBuffer(wav: Data) -> AVAudioPCMBuffer? {
        let bytes = [UInt8](wav)
        guard bytes.count > 44, bytes[0..<4] == [0x52, 0x49, 0x46, 0x46], bytes[8..<12] == [0x57, 0x41, 0x56, 0x45] else { return nil }
        func u16(_ i: Int) -> Int { Int(bytes[i]) | Int(bytes[i + 1]) << 8 }
        func u32(_ i: Int) -> Int { u16(i) | u16(i + 2) << 16 }
        var i = 12, kind = 0, channels = 1, rate = 0, bits = 16
        while i + 8 <= bytes.count {
            let id = String(decoding: bytes[i..<i + 4], as: UTF8.self), len = u32(i + 4)
            if id == "fmt " {
                kind = u16(i + 8); channels = max(1, u16(i + 10)); rate = u32(i + 12); bits = u16(i + 22)
            } else if id == "data" {
                let start = i + 8, end = min(bytes.count, start + len)
                guard rate > 0, let format = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: Double(rate),
                                                           channels: AVAudioChannelCount(channels), interleaved: false) else { return nil }
                let bytesPerSample = bits / 8
                let frames = (end - start) / max(1, channels * bytesPerSample)
                guard frames > 0, let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(frames)),
                      let out = buffer.floatChannelData else { return nil }
                for f in 0..<frames {
                    for c in 0..<channels {
                        let j = start + (f * channels + c) * bytesPerSample
                        if kind == 1 && bits == 16 { out[c][f] = Float(Int16(bitPattern: UInt16(u16(j)))) / 32768 }
                        else if kind == 3 && bits == 32 { out[c][f] = Float(bitPattern: UInt32(u32(j))) }
                        else { return nil }
                    }
                }
                buffer.frameLength = AVAudioFrameCount(frames)
                return buffer
            }
            i += 8 + len + (len & 1)
        }
        return nil
    }

    /// A chunk in another rate or channel count, in the node's format.
    private static func convert(_ buffer: AVAudioPCMBuffer, to format: AVAudioFormat) throws -> AVAudioPCMBuffer {
        guard let converter = AVAudioConverter(from: buffer.format, to: format) else { throw PlaybackFailure(why: "This speech could not be played.") }
        let capacity = AVAudioFrameCount(Double(buffer.frameLength) * format.sampleRate / buffer.format.sampleRate) + 16
        guard let out = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: capacity) else { throw PlaybackFailure(why: "This speech could not be played.") }
        var consumed = false
        var conversionError: NSError?
        let status = converter.convert(to: out, error: &conversionError) { _, outStatus in
            if consumed { outStatus.pointee = .endOfStream; return nil }
            consumed = true; outStatus.pointee = .haveData; return buffer
        }
        guard status != .error, conversionError == nil else { throw PlaybackFailure(why: "This speech could not be played.") }
        return out
    }

    /// The part of a buffer from `frame` on (the chunk under way, scheduled again after a reset).
    private static func remainder(of buffer: AVAudioPCMBuffer, from frame: AVAudioFramePosition) -> AVAudioPCMBuffer? {
        let start = Int(min(max(0, frame), AVAudioFramePosition(buffer.frameLength)))
        let frames = Int(buffer.frameLength) - start
        guard frames > 0, let out = AVAudioPCMBuffer(pcmFormat: buffer.format, frameCapacity: AVAudioFrameCount(frames)),
              let src = buffer.floatChannelData, let dst = out.floatChannelData else { return nil }
        for c in 0..<Int(buffer.format.channelCount) { dst[c].update(from: src[c] + start, count: frames) }
        out.frameLength = AVAudioFrameCount(frames)
        return out
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
    func togglePause() {
        if paused {
            paused = false
            if engine.isRunning, !inFlight.isEmpty { node.play() }
        } else {
            paused = true
            if node.isPlaying { node.pause() }
        }
    }
    func stop() {
        generation += 1; stopSampling(); turn.cancel(); activity = SpeechActivity(); publishTurn(); readingID = nil
        captureTask?.cancel(); captureTask = nil; playback?.cancel(); playback = nil
        recorder?.stop(); recorder = nil
        stopEngine(); pieces.removeAll(); nextPiece = 0
        speaking = false; preparing = false; paused = false
        if let file { try? storage.discard(file) }; file = nil; deactivateAudio()
    }
}
