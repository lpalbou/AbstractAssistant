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

/// What the audio session tells the app: a call or Siri took the audio (and gave it back), the
/// headphones went away, or the audio service was reset.
enum AudioSessionEvent: Sendable, Equatable {
    case interrupted
    case interruptionEnded(shouldResume: Bool)
    case routeLost
    case reset
}

final class AudioSessionEvents: @unchecked Sendable {
    private var tokens: [NSObjectProtocol] = []
    /// `action` sees every event; the one-argument form only the ones that end playback (every one
    /// but the end of an interruption).
    convenience init(action: @escaping @MainActor @Sendable () -> Void) {
        self.init(events: { event in
            if case .interruptionEnded = event { return }
            action()
        })
    }
    init(events action: @escaping @MainActor @Sendable (AudioSessionEvent) -> Void) {
        let center = NotificationCenter.default
        tokens.append(center.addObserver(forName: AVAudioSession.interruptionNotification, object: nil, queue: .main) { note in
            let type = note.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt
            let options = AVAudioSession.InterruptionOptions(rawValue: note.userInfo?[AVAudioSessionInterruptionOptionKey] as? UInt ?? 0)
            if type == AVAudioSession.InterruptionType.began.rawValue { Task { @MainActor in action(.interrupted) } }
            else if type == AVAudioSession.InterruptionType.ended.rawValue { Task { @MainActor in action(.interruptionEnded(shouldResume: options.contains(.shouldResume))) } }
        })
        tokens.append(center.addObserver(forName: AVAudioSession.routeChangeNotification, object: nil, queue: .main) { note in
            let reason = note.userInfo?[AVAudioSessionRouteChangeReasonKey] as? UInt
            guard reason == AVAudioSession.RouteChangeReason.oldDeviceUnavailable.rawValue || reason == AVAudioSession.RouteChangeReason.noSuitableRouteForCategory.rawValue else { return }
            Task { @MainActor in action(.routeLost) }
        })
        tokens.append(center.addObserver(forName: AVAudioSession.mediaServicesWereResetNotification, object: nil, queue: .main) { _ in Task { @MainActor in action(.reset) } })
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
/// stream breaks is requested again while what arrived plays — the retry skipping the seconds of sound
/// already here (`SpeechPieceRetry`) — and a reading that still fails ends with "The voice stopped
/// early" and goes on from that piece when the same message is read again (2026-11-01: one request
/// for ten minutes of audio was lost whole when the link went quiet for 90 s). The sound plays
/// through one AVAudioEngine graph (player node → time pitch → mixer): every streamed chunk is
/// scheduled on the node as it arrives, back to back, sample-contiguous — no gap between the
/// engine's short chunks (an AVAudioPlayer per chunk had an audible cut at each).
///
/// A reading goes on with the iPhone locked or in a pocket (the app's `audio` background mode): the
/// audio session is active only while a reading plays or waits for its sound, so a paused, stopped
/// or finished reading lets the app suspend. A call or Siri pauses it and, when the system says so,
/// it resumes; unplugged headphones pause it. A reading started with a title is the lock screen's
/// Now Playing item, with play/pause.
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
    @ObservationIgnored private let nowPlaying = NowPlaying()
    /// Paused by a call or Siri (not by the person): the end of the interruption resumes it.
    @ObservationIgnored private var pausedByInterruption = false
    /// The app may finish the wait for a reading's first sound in the background (locked right after
    /// a tap): the engine is not running yet, so nothing else keeps the app awake for it.
    @ObservationIgnored private var firstSoundTask: UIBackgroundTaskIdentifier = .invalid

    // The engine graph and what is scheduled on it.
    @ObservationIgnored private let engine = AVAudioEngine()
    @ObservationIgnored private let node = AVAudioPlayerNode()
    @ObservationIgnored private let pitch = AVAudioUnitTimePitch()
    @ObservationIgnored private let levels = OutputLevels()
    @ObservationIgnored private var nodeFormat: AVAudioFormat?
    @ObservationIgnored private var tapInstalled = false
    /// `start`: the frame of the node's timeline where the buffer begins.
    private struct Scheduled { let id: Int; let buffer: AVAudioPCMBuffer; let seconds: Double; let start: AVAudioFramePosition }
    /// Scheduled on the node and not yet played back, in order (the first is the one playing).
    @ObservationIgnored private var inFlight: [Scheduled] = []
    @ObservationIgnored private var nextID = 0
    /// Bumped when the node is reset: completions of buffers scheduled before are ignored.
    @ObservationIgnored private var scheduleEpoch = 0
    /// Where the last scheduled buffer ends on the node's timeline.
    @ObservationIgnored private var scheduledEnd: AVAudioFramePosition = 0
    /// The node's playhead when the reading was paused (a paused engine may report no render time).
    @ObservationIgnored private var pausedAt: AVAudioFramePosition?
    /// The look-ahead waits here, with no timer, until a buffer has played (or the reading stops).
    @ObservationIgnored private var consumed: CheckedContinuation<Void, Never>?
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
        events = AudioSessionEvents(events: { [weak self] event in self?.audioSession(event) })
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

    /// Capture never survives an audio event. A reading pauses for a call, Siri or lost headphones
    /// and resumes when an interruption ends with the system's go-ahead; a reset audio service ends it.
    private func audioSession(_ event: AudioSessionEvent) {
        if inputPending {
            if case .interruptionEnded = event { return }
            stop(); error = "Audio was interrupted. Tap the orb to try again."; return
        }
        guard speaking else { return }
        switch event {
        case .interrupted: PhoneTrace.note("voice: interruption began"); if !paused { pause(); pausedByInterruption = true }
        case .interruptionEnded(let shouldResume):
            PhoneTrace.note("voice: interruption ended (resume: \(shouldResume))")
            if shouldResume, paused, pausedByInterruption { resume() }
        case .routeLost: if !paused { pause() }
        case .reset: stop(); error = "Audio was interrupted. Tap play to try again."
        }
    }

    /// Reads `text` aloud. The same message (or text) read again after "The voice stopped early"
    /// goes on from the piece that was lost, not from the start. `title` (the conversation's) makes
    /// the reading the lock screen's Now Playing item.
    func read(_ text: String, client: any GatewayClient, scope: SpeechScope, choice: VoiceChoice? = nil, speed: Double = 1, messageID: String? = nil, title: String? = nil) {
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
        PhoneTrace.note("voice: reading \(plain.count) chars in \(pieces.count) pieces from piece \(nextPiece + 1)")
        let epoch = generation
        let voice: VoiceChoice? = { if case .run = scope { choice } else { nil } }()
        if configureAudio {
            firstSoundTask = UIApplication.shared.beginBackgroundTask(withName: "first sound") { [weak self] in MainActor.assumeIsolated { self?.endFirstSoundTask() } }
            if let title { nowPlaying.begin(title: title, toggle: { [weak self] in self?.togglePause() }, play: { [weak self] in self?.resume() }, pause: { [weak self] in self?.pause() }) }
        }
        playback = Task {
            if configureAudio {
                do { try activatePlayback() } catch {
                    guard epoch == generation else { return }
                    Self.log.error("the reading could not start: \(String(describing: error), privacy: .public)")
                    self.error = "The reading could not start. Tap play to try again."; end(epoch); return
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
    /// requested again up to `retries` times, 2 s apart, while the sound already here plays on; the
    /// retry's stream skips the seconds of that piece already here (`SpeechPieceRetry`: exact for a
    /// voice rendered the same way each time, within a few words for a sampled or cloned voice).
    /// Returns the error that ended the reading, nil once every piece has arrived.
    private func readPieces(client: any GatewayClient, scope: SpeechScope, voice: VoiceChoice?, epoch: Int) async -> Error? {
        while nextPiece < pieces.count {
            while aheadSeconds() >= Self.aheadSeconds {
                await withCheckedContinuation { consumed = $0 }
                if Task.isCancelled || epoch != generation { return nil }
            }
            let i = nextPiece
            var attempt = 0
            var retry = SpeechPieceRetry()
            while true {
                attempt += 1
                Self.log.info("piece \(i + 1, privacy: .public)/\(self.pieces.count, privacy: .public) started: \(self.pieces[i].count, privacy: .public) chars, try \(attempt, privacy: .public)")
                PhoneTrace.note("voice: piece \(i + 1)/\(pieces.count) try \(attempt), app \(isActive() ? "in front" : "in the background"), \(String(format: "%.1f", playedSeconds)) s played")
                do {
                    for try await raw in client.speech(text: pieces[i], scope: scope, voice: voice) {
                        try Task.checkCancellation(); guard epoch == generation else { return nil }
                        guard let wav = try retry.admit(wav: raw) else { continue }    // sound already here
                        try enqueue(wav)
                    }
                    break
                } catch {
                    if Task.isCancelled || error is CancellationError || epoch != generation { return nil }
                    if error is PlaybackFailure || error is SpeechWAV.Unreadable { return error }
                    retry.requestAgain()
                    Self.log.error("piece \(i + 1, privacy: .public) failed on try \(attempt, privacy: .public) after \(retry.kept, format: .fixed(precision: 2), privacy: .public) s of it: \(String(describing: error), privacy: .public)")
                    PhoneTrace.note("voice: piece \(i + 1) failed on try \(attempt) after \(String(format: "%.2f", retry.kept)) s of it: \(error.localizedDescription)")
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
    private func enqueue(_ wav: Data) throws {
        guard let decoded = Self.pcmBuffer(wav: wav) else { throw PlaybackFailure(why: "This speech could not be played.") }
        if nodeFormat == nil { try startEngine(with: decoded.format) }
        guard let nodeFormat else { return }
        let buffer = try decoded.format == nodeFormat ? decoded : Self.convert(decoded, to: nodeFormat)
        schedule(id: nextID, buffer: buffer)
        nextID += 1
        if !paused, !node.isPlaying { node.play() }
        if preparing { preparing = false; updateNowPlaying() }
    }

    /// The graph for this reading, in the first chunk's format; later chunks are converted to it.
    /// A reading paused before its first sound builds the graph and starts it on `resume()`.
    private func startEngine(with format: AVAudioFormat) throws {
        engine.connect(node, to: pitch, format: format)
        engine.connect(pitch, to: engine.mainMixerNode, format: format)
        let levels = levels
        // Called on the engine's own queue: never main-actor isolated.
        pitch.installTap(onBus: 0, bufferSize: 1024, format: nil) { @Sendable buffer, _ in levels.update(buffer) }
        tapInstalled = true
        engine.prepare()
        nodeFormat = format
        scheduledEnd = 0
        if !paused { try startEngine() }
        endFirstSoundTask()                          // from here the running engine keeps the app awake
    }

    private func startEngine() throws {
        guard !engine.isRunning else { return }
        do { try engine.start() } catch {
            Self.log.error("audio engine did not start: \(String(describing: error), privacy: .public)")
            throw PlaybackFailure(why: "This speech could not be played.")
        }
    }

    /// The buffer goes right behind the last one scheduled, or — the node starved (a stall: its
    /// timeline ran on over silence) — where the node is now: it starts at the node's next render, so
    /// its place on the timeline is known to one render cycle (about 10 ms).
    private func schedule(id: Int, buffer: AVAudioPCMBuffer) {
        guard let nodeFormat else { return }
        let start = max(scheduledEnd, nodeSampleTime() ?? scheduledEnd)
        let frames = AVAudioFramePosition(buffer.frameLength)
        scheduledEnd = start + frames
        inFlight.append(Scheduled(id: id, buffer: buffer, seconds: Double(frames) / nodeFormat.sampleRate, start: start))
        let epoch = scheduleEpoch
        node.scheduleBuffer(buffer, completionCallbackType: .dataPlayedBack) { @Sendable [weak self] _ in   // the engine's queue
            Task { @MainActor [weak self] in self?.playedBack(id: id, epoch: epoch) }
        }
    }

    private func playedBack(id: Int, epoch: Int) {
        guard epoch == scheduleEpoch, let i = inFlight.firstIndex(where: { $0.id == id }) else { return }
        let s = inFlight.remove(at: i)
        playedSeconds += s.seconds
        settle(generation)
        wakeLookAhead()
    }

    private func wakeLookAhead() { consumed?.resume(); consumed = nil }

    /// Nothing scheduled: the reading waits for the stream, or ends once the stream is over.
    private func settle(_ epoch: Int) {
        guard epoch == generation, speaking else { return }
        let waiting = inFlight.isEmpty && !streamDone
        if preparing != waiting { preparing = waiting; updateNowPlaying() }
        if inFlight.isEmpty, streamDone { end(epoch) }
    }

    /// The node's playhead on its timeline (it stops while paused and runs on while starved); nil
    /// before the node first plays.
    private func nodeSampleTime() -> AVAudioFramePosition? {
        guard let nodeTime = node.lastRenderTime, let time = node.playerTime(forNodeTime: nodeTime) else { return pausedAt }
        return time.sampleTime
    }

    /// Frames of the playing buffer (the first in flight) already rendered.
    private func playheadFrames() -> AVAudioFramePosition {
        guard let first = inFlight.first, let now = nodeSampleTime() else { return 0 }
        return min(AVAudioFramePosition(first.buffer.frameLength), max(0, now - first.start))
    }

    /// Seconds of sound scheduled and not yet played, at the reading's speed.
    func aheadSeconds() -> Double {
        guard let nodeFormat else { return 0 }
        let total = inFlight.reduce(0) { $0 + $1.seconds }
        return max(0, total - Double(playheadFrames()) / nodeFormat.sampleRate) / Double(pitch.rate)
    }

    /// Seconds of the reading played so far, inside the buffer under way too (the lock screen's time).
    private var elapsedSeconds: Double {
        guard let nodeFormat else { return playedSeconds }
        return playedSeconds + Double(playheadFrames()) / nodeFormat.sampleRate
    }

    private func updateNowPlaying() { nowPlaying.update(playing: speaking && !paused && !preparing, elapsed: elapsedSeconds, rate: pitch.rate) }

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
        PhoneTrace.note("voice: reading ended after \(String(format: "%.1f", playedSeconds)) s played, app \(isActive() ? "in front" : "in the background")\(error.map { ": " + $0 } ?? "")")
        speaking = false; preparing = false; paused = false; readingID = nil; stopSampling()
        stopEngine(); deactivateAudio(); endReadingTasks()
    }

    private func stopEngine() {
        scheduleEpoch += 1
        node.stop(); node.reset()
        if tapInstalled { pitch.removeTap(onBus: 0); tapInstalled = false }
        if engine.isRunning { engine.stop() }
        inFlight.removeAll(); nodeFormat = nil; scheduledEnd = 0; pausedAt = nil; levels.reset()
        wakeLookAhead()
    }

    /// What only a reading under way holds: the lock screen's item, the first-sound grace.
    private func endReadingTasks() { nowPlaying.end(); endFirstSoundTask(); pausedByInterruption = false }

    private func endFirstSoundTask() {
        guard firstSoundTask != .invalid else { return }
        UIApplication.shared.endBackgroundTask(firstSoundTask); firstSoundTask = .invalid
    }

    private func activatePlayback() throws {
        let audio = AVAudioSession.sharedInstance()
        try audio.setCategory(.playback, mode: .spokenAudio); try audio.setActive(true)
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
    /// The scene left the screen (`false`) or came back: the orb's meter samples only while seen
    /// (a reading goes on in the background without it).
    func scene(visible: Bool) {
        if speaking { PhoneTrace.note("voice: app \(visible ? "back in front" : "in the background") while reading, \(String(format: "%.1f", playedSeconds)) s played") }
        if !visible, !inputPending { stopSampling() }
        else if visible, speaking, sampler == nil { startSampling() }
    }

    func togglePause() { paused ? resume() : pause() }

    /// Holds the reading where it is and gives the audio back: the app may suspend while paused.
    func pause() {
        guard speaking, !paused else { return }
        paused = true; pausedByInterruption = false
        PhoneTrace.note("voice: paused at \(String(format: "%.1f", elapsedSeconds)) s")
        pausedAt = nodeSampleTime()
        if node.isPlaying { node.pause() }
        if engine.isRunning { engine.pause() }
        deactivateAudio()
        updateNowPlaying()
    }

    /// Goes on from the exact sample where `pause()` stopped.
    func resume() {
        guard speaking, paused else { return }
        do {
            if configureAudio { try activatePlayback() }
            if nodeFormat != nil { try startEngine() }
        } catch {
            // Usually another app (a call) still holds the audio: plain words here, the cause in the log.
            Self.log.error("the reading could not resume: \(String(describing: error), privacy: .public)")
            stop(); self.error = "The reading could not resume. Tap play to try again."; return
        }
        paused = false; pausedByInterruption = false
        PhoneTrace.note("voice: resumed at \(String(format: "%.1f", elapsedSeconds)) s")
        if engine.isRunning, !inFlight.isEmpty { node.play() }
        pausedAt = nil
        updateNowPlaying()
    }

    func stop() {
        generation += 1; stopSampling(); turn.cancel(); activity = SpeechActivity(); publishTurn(); readingID = nil
        captureTask?.cancel(); captureTask = nil; playback?.cancel(); playback = nil
        recorder?.stop(); recorder = nil
        stopEngine(); pieces.removeAll(); nextPiece = 0
        speaking = false; preparing = false; paused = false
        if let file { try? storage.discard(file) }; file = nil; deactivateAudio(); endReadingTasks()
    }
}
