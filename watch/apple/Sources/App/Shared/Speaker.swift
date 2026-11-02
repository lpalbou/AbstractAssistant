@preconcurrency import AVFoundation
import AbstractGatewayClient
import OSLog
import SwiftUI

/// Reads a text aloud with the gateway's voice: the speech stream's WAV chunks play back to back
/// through a current and a prepared AVAudioPlayer, scheduled on the audio device's clock;
/// optional background analysis lets the orb
/// follow the voice without delaying playback. An answer's recordings (the Assistant's workflow makes
/// them) play after its text, at their own speed.
///
/// The text is requested in pieces (`SpeechText.pieces`, about 600 characters each), one stream at
/// a time, the next while under `aheadSeconds` of audio wait: a piece whose stream breaks is
/// requested again while what arrived plays, the retry skipping the sound already here
/// (`SpeechPieceRetry`), and a reading that still fails goes on from that piece with a tap
/// (2026-11-01: one request for ten minutes of audio was lost whole when the link went quiet for
/// 90 s). The recordings wait for the text: they never play before the rest of a reading that
/// stopped early.
@MainActor
final class Speaker: NSObject, ObservableObject {
    /// `rate`: the speed chosen in Settings → Voice for speech; 1 for a recording. `piece`: the
    /// text piece this sound belongs to (−1 for a recording).
    typealias Chunk = (data: Data, duration: Double, frames: [VoiceFrame], rate: Float, piece: Int)

    enum State: Equatable { case idle, preparing, speaking, paused, finished, failed(String) }

    @Published private(set) var state: State = .idle
    /// Seconds of sound received so far and played so far (for the progress line).
    @Published private(set) var receivedSeconds: Double = 0
    /// Seconds of the text's speech received (the recordings apart).
    private var speechSeconds: Double = 0
    @Published private(set) var playedSeconds: Double = 0

    /// Chunks to play; analysis is optional and may be cached when replaying a chunk.
    private var queue: [Chunk] = []
    /// Wait for a short audio cushion, or the end of the stream. Chunk size depends on the backend:
    /// Supertonic sends sentence-sized pieces, while Qwen commonly sends subsecond PCM pieces.
    /// Set again when the queue runs dry.
    private var buffering = true
    private static let startBuffer = 1.5, refillBuffer = 2.0
    private var refilling = false
    /// Chunks already spoken, in order (rewind reaches back into them), and the one playing now.
    private var history: [Chunk] = []
    /// Seconds of spoken audio kept for rewinds; older chunks are let go (a ten-minute reading
    /// would otherwise hold its every sound).
    private static let historySeconds = 120.0
    private var currentData: Data?
    private var currentRate: Float = 1
    private var currentPiece = -1
    /// The chunk playing, analysed (60 frames per second of audio) for the orb.
    private var frames: [VoiceFrame] = []
    private let normalizer = VoiceNormalizer()
    /// Where the next chunk starts (a rewind into the middle of an earlier chunk).
    private var startAt: TimeInterval = 0
    private var player: AVAudioPlayer?
    /// One piece ahead, already scheduled: a delegate callback is too late to open the next WAV
    /// without a gap (Qwen sends roughly one WAV per second). At most two players are resident.
    private var successor: (player: AVAudioPlayer, chunk: Chunk, startTime: TimeInterval)?
    private var scheduledEnd: TimeInterval = 0
    private var completions: [ObjectIdentifier: Bool] = [:]
    private nonisolated let completionMailbox = PlayerCompletionMailbox()
    private var streamDone = false
    private var task: Task<Void, Never>?
    private var analysisTask: Task<Void, Never>?
    private var analysisWorker: Task<[VoiceFrame], Never>?
    /// This speaker's keep-awake hold (one per speaker: two screens never release each other's).
    private let holder = "speak-" + UUID().uuidString

    /// The text's pieces, the next one to request, and where their voice comes from (kept after a
    /// failure, so the reading can go on from the piece that was lost).
    private var pieces: [String] = []
    private var nextPiece = 0
    private var scope: SpeechScope?
    private var client: (any GatewayClient)?
    /// The error that ended the reading early (a link error: the app coming back resumes by itself).
    private var lastError: Error?
    /// Audio waiting to play beyond which the next piece is not requested yet.
    private static let aheadSeconds = 45.0
    /// The look-ahead waits here, with no timer, until a chunk has played (or the reading stops):
    /// a paused or suspended reading consumes nothing, so it wakes nothing (watch battery rule).
    private var consumed: CheckedContinuation<Void, Never>?
    /// The recordings, downloaded, waiting for the text to finish (`nil`: one could not be fetched).
    private var heldClips: [Data?] = []
    /// Requests of one piece after its first failed, 2 s apart.
    private static let retries = 3
    /// `--piece-chars <n>` (debug builds): smaller pieces, so a short sample answer has several.
    private static let pieceTarget: Int = {
        #if DEBUG
        let args = ProcessInfo.processInfo.arguments
        if let i = args.firstIndex(of: "--piece-chars"), i + 1 < args.count, let n = Int(args[i + 1]), n > 0 { return n }
        #endif
        return 600
    }()

    /// A player dropped with its view (a page replaced under it) lets go of the watch too: a hold
    /// left behind kept every later keep-awake session running its full ten minutes.
    deinit {
        analysisTask?.cancel()
        analysisWorker?.cancel()
        let holder = holder
        Task { @MainActor in RuntimeKeeper.shared.release(holder) }
    }
    /// The one voice playing: starting another stops it.
    private static weak var current: Speaker?
    /// The stream broke after some audio: once what arrived has played, the reading says so.
    private var streamError: String?

    private static let log = Logger(subsystem: "ai.abstractframework.assistant.watchkitapp", category: "speaker")

    /// Every build logs the reading's course (pieces, chunks, retries, how it ended); a debug build
    /// prints it too, so a device launched with its console shows it.
    private func trace(_ s: String) {
        Self.log.info("\(s, privacy: .public)")
        #if DEBUG
        print("speaker \(Date().formatted(date: .omitted, time: .standard)) \(s)")
        #endif
    }

    override init() {
        super.init()
        // The system can stop the player underneath (an interruption, the app suspended with the
        // wrist down, the keep-awake session gone) and says so only through these; the player's
        // "finished" callback never comes for a chunk stopped that way, so the reading would stay
        // "speaking" over silence until a tap. An interruption pauses honestly and resumes when the
        // system says so; the app coming back to the front picks the voice up where it stopped.
        let center = NotificationCenter.default
        center.addObserver(forName: AVAudioSession.interruptionNotification, object: nil, queue: .main) { [weak self] note in
            let type = note.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt
            let options = note.userInfo?[AVAudioSessionInterruptionOptionKey] as? UInt ?? 0
            Task { @MainActor [weak self] in
                guard let self else { return }
                self.trace("interruption \(type == 1 ? "began" : type == 0 ? "ended" : "?"), options \(options)")
                if type == AVAudioSession.InterruptionType.began.rawValue { self.pause() }
                else if type == AVAudioSession.InterruptionType.ended.rawValue,
                        AVAudioSession.InterruptionOptions(rawValue: options).contains(.shouldResume), self.state == .paused { self.resume() }
            }
        }
        center.addObserver(forName: WKApplication.didBecomeActiveNotification, object: nil, queue: .main) { [weak self] _ in
            Task { @MainActor [weak self] in self?.ensurePlaying() }
        }
        #if DEBUG
        center.addObserver(forName: AVAudioSession.routeChangeNotification, object: nil, queue: .main) { note in
            print("speaker route change \(note.userInfo?[AVAudioSessionRouteChangeReasonKey] ?? "?")")
        }
        #endif
    }

    /// The invariant of a reading: while it is speaking, something plays. A player the system
    /// stopped underneath plays on from where it stopped; no player, the next chunk starts. A
    /// reading the link broke while the app was away (its retries spent in the background) goes on.
    private func ensurePlaying() {
        synchronizePlayback()
        if canResume, lastError is URLError { trace("active again: the reading goes on from piece \(nextPiece + 1)"); resumeReading(); return }
        guard state == .speaking else { return }
        guard let p = player else { advanceIfIdle(); return }
        guard !p.isPlaying else { return }
        trace("the voice had stopped at \(String(format: "%.2f", p.currentTime)) s of this chunk: playing on")
        unscheduleSuccessor()
        try? AVAudioSession.sharedInstance().setActive(true)
        RuntimeKeeper.shared.hold(holder)
        if !start(p) { state = .failed("The watch stopped the voice."); stop() }
        else { scheduleSuccessor() }
    }

    var isActive: Bool { state == .preparing || state == .speaking }
    /// Paused mid-sentence: `resume()` continues exactly there.
    var isPaused: Bool { state == .paused }
    private var pausedFromPreparing = false

    /// Holds the voice where it is (the current chunk's position is kept; chunks still arriving wait).
    func pause() {
        synchronizePlayback()
        guard isActive else { return }
        pausedFromPreparing = state == .preparing
        unscheduleSuccessor()
        player?.pause()
        state = .paused
        RuntimeKeeper.shared.release(holder)          // a paused voice never keeps the watch awake
        trace("paused at \(String(format: "%.2f", player?.currentTime ?? 0)) s of this chunk")
    }

    /// Continues from the exact sample where `pause()` stopped.
    func resume() {
        guard state == .paused else { return }
        RuntimeKeeper.shared.hold(holder)
        if let player {
            state = .speaking
            trace("resuming at \(String(format: "%.2f", player.currentTime)) s of this chunk")
            try? AVAudioSession.sharedInstance().setActive(true)    // off since the pause, maybe
            if !start(player) { state = .failed("The watch stopped the voice."); stop() }
            else { scheduleSuccessor() }
        } else {
            state = pausedFromPreparing ? .preparing : .speaking
            advanceIfIdle()
        }
    }

    /// Plays recordings alone (a recording's own row, or its page).
    func play(clips: [MediaItem], client: any GatewayClient) { read("", scope: nil, client: client, clips: clips) }

    func read(_ markdown: String, scope: SpeechScope?, client: any GatewayClient, clips: [MediaItem] = []) {
        // The audio session stays active from one reading to the next (a voice picker's taps follow
        // each other): deactivating it between them could leave the next one silent.
        stop(keepSession: true)
        if let other = Self.current, other !== self { other.stop(keepSession: true) }
        Self.current = self
        // One request per piece of the text; the selected backend determines the streamed audio pieces.
        let spoken = scope == nil ? "" : SpeechText.plain(markdown)
        let clips = clips.filter { $0.kind == .audio }
        guard !spoken.isEmpty || !clips.isEmpty else { state = .failed("Nothing to read in this text."); return }
        pieces = spoken.isEmpty ? [] : SpeechText.pieces(spoken, target: Self.pieceTarget, cap: Self.pieceTarget * 4 / 3)
        nextPiece = 0; self.scope = scope; self.client = client; lastError = nil
        guard activateSession() else { return }
        state = .preparing; streamDone = false; streamError = nil; receivedSeconds = 0; speechSeconds = 0; playedSeconds = 0
        buffering = true; refilling = false
        RuntimeKeeper.shared.hold(holder)
        trace("reading \(spoken.count) chars in \(pieces.count) pieces, \(clips.count) recordings")
        task = Task { [weak self] in
            // The recordings download while the text is spoken and play after it; one that cannot
            // be fetched does not keep the others from playing.
            async let recordings = Self.download(clips, client: client)
            var voiceError: Error?
            if scope != nil, let self, !self.pieces.isEmpty { voiceError = await self.readPieces() }
            guard let self, !Task.isCancelled else { return }
            if !clips.isEmpty, !self.textGoesOn(after: voiceError) { self.awaitingClips = true; self.advanceIfIdle() }
            let fetched = await recordings
            guard !Task.isCancelled else { return }
            self.awaitingClips = false
            self.heldClips = fetched
            self.textEnded(voiceError)
        }
    }

    /// The text stopped early after some of it was spoken: it goes on with a tap, so its
    /// recordings wait for that (they never play before the rest of the text). A voice that never
    /// spoke gives way to them.
    private func textGoesOn(after error: Error?) -> Bool { error != nil && speechSeconds > 0 }

    /// The text has ended (`error`: it stopped early). Its recordings play now unless the text goes
    /// on later (`resumeReading`); what arrived plays, even under the buffer.
    private func textEnded(_ error: Error?) {
        if let error {
            streamError = speechSeconds > 0 ? "The voice stopped early. \(Self.describe(error))" : Self.describe(error)
            lastError = error
            Self.log.error("voice failed after \(self.speechSeconds, format: .fixed(precision: 1), privacy: .public) s at piece \(self.nextPiece + 1, privacy: .public)/\(self.pieces.count, privacy: .public): \(String(describing: error), privacy: .public)")
            trace("voice failed after \(String(format: "%.1f", speechSeconds)) s: \(error)")
        }
        if !textGoesOn(after: error) {
            for data in heldClips.compactMap({ $0 }) { enqueue(data, rate: 1, piece: -1) }
            if heldClips.contains(where: { $0 == nil }), streamError == nil { streamError = "A recording could not be played." }
            heldClips = []
        } else if !heldClips.isEmpty {
            trace("\(heldClips.count) recordings wait for the rest of the text")
        }
        streamDone = true
        advanceIfIdle()
    }

    private func activateSession() -> Bool {
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playback, mode: .spokenAudio, policy: .default, options: [])
            try session.setActive(true)
            return true
        } catch {
            state = .failed("The watch refused audio playback: \(error.localizedDescription)")
            trace("session error \(error)")
            return false
        }
    }

    /// Requests the pieces from `nextPiece` on, one stream at a time, the next once less than
    /// `aheadSeconds` of audio waits. A piece whose stream breaks (the link, the gateway) is
    /// requested again up to `retries` times, 2 s apart, while the audio already here plays on; the
    /// retry's stream skips the seconds of that piece already here (`SpeechPieceRetry`: exact for a
    /// voice rendered the same way each time, within a few words for a sampled or cloned voice).
    /// Returns the error that ended the reading, nil once every piece has arrived.
    private func readPieces() async -> Error? {
        guard let scope, let client else { return nil }
        let voice = VoicePrefs.voice(for: scope)
        while nextPiece < pieces.count {
            while aheadSeconds() >= Self.aheadSeconds {
                await withCheckedContinuation { consumed = $0 }
                if Task.isCancelled { return nil }
            }
            let i = nextPiece
            var attempt = 0
            var retry = SpeechPieceRetry()
            while true {
                attempt += 1
                trace("piece \(i + 1)/\(pieces.count) started: \(pieces[i].count) chars, try \(attempt)")
                do {
                    for try await raw in client.speech(text: pieces[i], scope: scope, voice: voice) {
                        if Task.isCancelled { return nil }
                        let admitted: Data?
                        do { admitted = try retry.admit(wav: raw) } catch {
                            // Not a WAV: no player can play it, and asking again would not change it.
                            state = .failed("This speech could not be played."); stop(); return nil
                        }
                        guard let wav = admitted else { trace("skipped a chunk of piece \(i + 1) already here"); continue }
                        enqueue(wav, piece: i)
                    }
                    break
                } catch {
                    if Task.isCancelled || error is CancellationError { return nil }
                    retry.requestAgain()
                    trace("piece \(i + 1) failed on try \(attempt) after \(String(format: "%.2f", retry.kept)) s of it: \(error)")
                    guard attempt <= Self.retries, LiveGatewayClient.isTransient(error) else { return error }
                    try? await Task.sleep(for: .seconds(2))
                    if Task.isCancelled { return nil }
                }
            }
            nextPiece = i + 1
        }
        trace("every piece arrived, \(String(format: "%.1f", receivedSeconds)) s received")
        return nil
    }

    /// Seconds of sound here and not yet played: the queue, the scheduled piece, the rest of the one playing.
    private func aheadSeconds() -> Double {
        var s = queue.reduce(0) { $0 + $1.duration / Double($1.rate) }
        if let next = successor { s += next.chunk.duration / Double(next.chunk.rate) }
        if let p = player { s += max(0, p.duration - p.currentTime) / Double(max(0.1, currentRate)) }
        return s
    }

    /// Wakes the look-ahead (a chunk has played, or the reading stopped).
    private func wakeLookAhead() { consumed?.resume(); consumed = nil }

    /// A reading that stopped early can go on from the piece that was lost.
    var canResume: Bool {
        if case .failed = state { return nextPiece < pieces.count && scope != nil }
        return false
    }

    /// The line under the orb for a reading that failed, in the person's words (the reason is in the log).
    var failureLine: String {
        guard playedSeconds > 0 else { return "Voice unavailable" }
        return canResume ? "The voice stopped early. Tap the speaker to continue." : "The voice stopped early."
    }

    /// Goes on from the piece whose stream was lost (the voice button's tap on a reading that
    /// stopped early; the app coming back after a link error), then plays the recordings held for it.
    func resumeReading() {
        guard canResume else { return }
        if let other = Self.current, other !== self { other.stop(keepSession: true) }
        Self.current = self
        guard activateSession() else { return }
        state = .preparing; streamDone = false; streamError = nil; lastError = nil
        buffering = true; refilling = false
        RuntimeKeeper.shared.hold(holder)
        trace("resuming the reading from piece \(nextPiece + 1)/\(pieces.count)")
        task = Task { [weak self] in
            guard let self else { return }
            let error = await self.readPieces()
            guard !Task.isCancelled else { return }
            self.textEnded(error)
        }
    }

    /// Audio chunks up to this size are analysed for the orb.
    private static let analysedBytes = 4 * 1024 * 1024
    /// The text has been spoken; its recordings are still downloading (the orb waits, not speaks).
    private var awaitingClips = false

    private static func download(_ clips: [MediaItem], client: any GatewayClient) async -> [Data?] {
        var out: [Data?] = []
        for clip in clips { out.append(try? await MediaStore.shared.data(clip, client: client)) }
        return out
    }

    func stop() { stop(keepSession: false) }

    /// `keepSession`: another reading starts right after (the session stays active for it).
    func stop(keepSession: Bool) {
        task?.cancel(); task = nil
        wakeLookAhead()
        cancelAnalysis()
        successor?.player.stop(); successor = nil
        completions.removeAll()
        _ = completionMailbox.take()
        player?.stop(); player = nil
        scheduledEnd = 0
        queue.removeAll(); history.removeAll(); currentData = nil; startAt = 0
        pieces.removeAll(); nextPiece = 0; lastError = nil; heldClips = []
        if isActive || state == .paused { state = .idle }
        if keepSession { RuntimeKeeper.shared.release(holder) } else { release() }
    }

    /// Something has been spoken that a rewind can go back to.
    var canRewind: Bool { position() > 0.5 || !history.isEmpty }

    /// Goes back `seconds` in what was spoken (into earlier chunks if needed) and goes on from
    /// there; paused stays paused at the new place, a finished reading speaks again from there.
    func rewind(_ seconds: Double = 10) {
        synchronizePlayback()
        unscheduleSuccessor()
        var back = seconds
        if let p = player {
            if p.currentTime >= back {
                p.currentTime -= back
                if state != .paused {
                    scheduledEnd = p.deviceCurrentTime + (p.duration - p.currentTime) / Double(p.rate)
                    scheduleSuccessor()
                }
                trace("rewound within the chunk"); return
            }
            back -= p.currentTime
            p.stop(); player = nil
            if let d = currentData { queue.insert((d, p.duration, frames, currentRate, currentPiece), at: 0) }
        }
        currentData = nil
        var offset: Double = 0
        while let last = history.popLast() {
            playedSeconds -= last.duration
            queue.insert(last, at: 0)
            if last.duration >= back { offset = last.duration - back; break }
            back -= last.duration
        }
        playedSeconds = max(0, playedSeconds)
        startAt = offset
        guard !queue.isEmpty else { return }
        if state == .paused {
            loadNext(play: false)                        // ready at the new place; resume() plays it
            return
        }
        if !isActive {                                   // finished (or stopped early): speak again
            try? AVAudioSession.sharedInstance().setActive(true)
            RuntimeKeeper.shared.hold(holder)
            state = .preparing
        }
        trace("rewound \(seconds) s, starting \(String(format: "%.1f", offset)) s into an earlier chunk")
        advanceIfIdle()
    }

    /// The rewind button: back `seconds` and play from there (paused, a rewind alone would be silent
    /// and look like nothing happened).
    func rewindAndPlay(_ seconds: Double = 10) {
        rewind(seconds)
        if state == .paused { resume() }
    }

    /// Seconds spoken so far, inside the current sentence too.
    func position() -> Double { playedSeconds + (player?.currentTime ?? 0) }

    /// What the orb follows: the analysed frame of the chunk at the player's position (exact, at any
    /// speed), scaled to the voice's recent range; silence while nothing plays.
    func features(at t: Double) -> VoiceFeatures {
        guard let player, player.isPlaying, !frames.isEmpty else { return normalizer.push(.silent, at: t) }
        let i = max(0, min(frames.count - 1, Int(player.currentTime * 60)))
        return normalizer.push(frames[i], at: t)
    }

    private func enqueue(_ wav: Data, rate: Float = Float(VoicePrefs.speed), piece: Int) {
        let duration = (try? AVAudioPlayer(data: wav))?.duration ?? 0
        queue.append((wav, duration, [], rate, piece))
        receivedSeconds += duration
        if piece >= 0 { speechSeconds += duration }
        trace("chunk \(wav.count) bytes (\(String(format: "%.1f", duration)) s, piece \(piece + 1)), received \(String(format: "%.1f", receivedSeconds)) s, played \(String(format: "%.1f", playedSeconds)) s")
        advanceIfIdle()
        scheduleSuccessor()
    }

    private func advanceIfIdle() {
        guard player == nil, state != .paused else { return }
        guard !queue.isEmpty else {
            if !streamDone, playedSeconds > 0 { buffering = true; refilling = true; trace("ran dry, buffering") }
            if !streamDone, awaitingClips, state == .speaking { state = .preparing }
            if streamDone, isActive {
                // Silence never passes for a reading: no sound and no error is a failure with a reason.
                if let why = SpeechSample.failure(receivedSeconds: receivedSeconds, clipsPlayed: playedSeconds > 0, streamError: streamError) {
                    state = .failed(why); trace("ended without playing: \(why)")
                } else { state = .finished; trace("done, played \(String(format: "%.1f", playedSeconds)) s") }
                release()
            }
            return
        }
        if buffering && !streamDone {
            let queued = queue.reduce(0) { $0 + $1.duration / Double($1.rate) }
            guard queued >= (refilling ? Self.refillBuffer : Self.startBuffer) else {
                trace("buffering, \(String(format: "%.1f", queued)) s queued"); return
            }
        }
        buffering = false
        loadNext(play: true)
    }

    /// The next chunk in the player (at `startAt`), playing or held for `resume()`.
    private func loadNext(play: Bool) {
        cancelAnalysis()
        let chunk = queue.removeFirst()
        let next = chunk.data
        do {
            let p = try makePlayer(chunk)
            if startAt > 0 { p.currentTime = min(startAt, max(0, p.duration - 0.05)); startAt = 0 }
            currentData = next
            currentRate = chunk.rate
            currentPiece = chunk.piece
            frames = chunk.frames
            player = p
            if play, !start(p) { throw GatewayError.invalidResponse }
            analyzeIfNeeded(next, player: p)
            guard play else { return }
            trace("playing \(String(format: "%.1f", p.duration)) s, route \(AVAudioSession.sharedInstance().currentRoute.outputs.map(\.portName))")
            if state != .speaking { state = .speaking; WKHaptic.start() }
            scheduleSuccessor()
        } catch {
            state = .failed("This speech could not be played (\(error.localizedDescription)).")
            stop()
        }
    }

    private func makePlayer(_ chunk: Chunk) throws -> AVAudioPlayer {
        let p = try AVAudioPlayer(data: chunk.data)
        p.delegate = self
        p.enableRate = chunk.rate != 1
        p.rate = chunk.rate
        guard p.prepareToPlay() else { throw GatewayError.invalidResponse }
        return p
    }

    /// `play(atTime:)` shares a clock between players. Preparing the successor while this one
    /// plays removes decoder setup and main-thread callback latency from the audible boundary.
    private func start(_ p: AVAudioPlayer) -> Bool {
        let time = p.deviceCurrentTime + 0.03
        guard p.play(atTime: time) else { return false }
        scheduledEnd = time + (p.duration - p.currentTime) / Double(p.rate)
        return true
    }

    private func scheduleSuccessor() {
        guard player != nil, successor == nil, state != .paused, scheduledEnd > 0,
              let chunk = queue.first else { return }
        do {
            let p = try makePlayer(chunk)
            // A late arrival or a delayed delegate cannot schedule in the past: retain its actual
            // start so following pieces never overlap while catching up.
            let time = max(scheduledEnd, p.deviceCurrentTime + 0.03)
            guard p.play(atTime: time) else { throw GatewayError.invalidResponse }
            successor = (p, chunk, time)
            queue.removeFirst()
        } catch {
            state = .failed("This speech could not be played (\(error.localizedDescription)).")
            stop()
        }
    }

    /// A paused or rewound reading owns the queued piece again; it must never start on its old
    /// device-clock deadline while the current piece is held or playing from a different place.
    private func unscheduleSuccessor() {
        guard let next = successor else { return }
        next.player.stop()
        completions.removeValue(forKey: ObjectIdentifier(next.player))
        queue.insert(next.chunk, at: 0)
        successor = nil
    }

    /// The delegate can finish a piece before its main-actor task runs. Controls first consume
    /// actual outcomes recorded by the delegate, so they operate on the piece really playing.
    private func synchronizePlayback() {
        for (ref, success) in completionMailbox.take() {
            let p = ref.player
            guard p === player || p === successor?.player else { continue }
            guard success else {
                state = .failed("The watch could not finish playing this speech.")
                stop(); return
            }
            completions[ObjectIdentifier(p)] = success
        }
        // A 5 ms tail may already have finished too. Consume outcomes in playback order.
        while let current = player,
              let success = completions.removeValue(forKey: ObjectIdentifier(current)) {
            finishedChunk(current, successfully: success)
        }
        scheduleSuccessor()
    }

    /// Analyse only the current chunk, after playback starts. If analysis falls behind, the
    /// orb catches up using the player's current time; obsolete work never delays the next chunk.
    private func analyzeIfNeeded(_ data: Data, player: AVAudioPlayer) {
        guard frames.isEmpty, data.count <= Self.analysedBytes else { return }
        let ref = PlayerRef(player)
        let worker = Task.detached(priority: .utility) { VoiceAnalyzer.frames(ofWAV: data) }
        analysisWorker = worker
        analysisTask = Task { [weak self] in
            let result = await worker.value
            guard !Task.isCancelled, let self, self.player === ref.player else { return }
            self.frames = result
        }
    }

    private func cancelAnalysis() {
        analysisTask?.cancel(); analysisTask = nil
        analysisWorker?.cancel(); analysisWorker = nil
    }

    fileprivate func finishedChunk(_ p: AVAudioPlayer, successfully: Bool) {
        guard p === player else { return }
        completions.removeValue(forKey: ObjectIdentifier(p))
        guard successfully else {
            state = .failed("The watch could not finish playing this speech.")
            stop(); return
        }
        cancelAnalysis()
        playedSeconds += p.duration
        if let d = currentData { history.append((d, p.duration, frames, currentRate, currentPiece)) }
        while history.count > 1, history.reduce(0, { $0 + $1.duration }) > Self.historySeconds { history.removeFirst() }
        currentData = nil
        trace("finished chunk, played \(String(format: "%.1f", playedSeconds)) s")
        player = nil
        if let next = successor {
            successor = nil
            player = next.player
            currentData = next.chunk.data
            currentRate = next.chunk.rate
            currentPiece = next.chunk.piece
            frames = next.chunk.frames
            scheduledEnd = next.startTime + next.player.duration / Double(next.chunk.rate)
            analyzeIfNeeded(next.chunk.data, player: next.player)
        } else {
            scheduledEnd = 0
            advanceIfIdle()
        }
        wakeLookAhead()
    }

    /// Lets go of the watch and, when this is the voice playing, of the audio session (a player
    /// that never spoke, stopped as its row leaves the screen, must not cut another one's voice).
    private func release() {
        RuntimeKeeper.shared.release(holder)
        guard Self.current === self else { return }
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }

    private static func describe(_ error: Error) -> String {
        if case GatewayError.http(let status, let body) = error {
            let detail = (try? JSONSerialization.jsonObject(with: Data(body.utf8)) as? [String: Any])?["detail"] as? String
            return "The gateway's voice failed (\(status)): \(detail ?? body)"
        }
        return "The gateway's voice failed: \(error.localizedDescription)"
    }
}

extension Speaker: AVAudioPlayerDelegate {
    nonisolated func audioPlayerDecodeErrorDidOccur(_ player: AVAudioPlayer, error: Error?) {
        #if DEBUG
        print("speaker decode error \(String(describing: error))")
        #endif
        let ref = PlayerRef(player)
        completionMailbox.record(ref, successfully: false)
        Task { @MainActor in self.synchronizePlayback() }
    }

    nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        #if DEBUG
        if !flag { print("speaker chunk ended UNSUCCESSFULLY") }
        #endif
        let ref = PlayerRef(player)
        completionMailbox.record(ref, successfully: flag)
        Task { @MainActor in self.synchronizePlayback() }
    }
}

private struct PlayerRef: @unchecked Sendable { let player: AVAudioPlayer; init(_ p: AVAudioPlayer) { player = p } }

/// AVAudioPlayer invokes its delegate outside the main actor. Record the real outcome before
/// hopping actors, so a simultaneous tap can drain it without guessing from the device clock.
private final class PlayerCompletionMailbox: @unchecked Sendable {
    private let lock = NSLock()
    private var pending: [(PlayerRef, Bool)] = []

    func record(_ player: PlayerRef, successfully: Bool) {
        lock.withLock { pending.append((player, successfully)) }
    }

    func take() -> [(PlayerRef, Bool)] {
        lock.withLock {
            let values = pending
            pending.removeAll()
            return values
        }
    }
}

import WatchKit
private enum WKHaptic { @MainActor static func start() { WKInterfaceDevice.current().play(.start) } }
