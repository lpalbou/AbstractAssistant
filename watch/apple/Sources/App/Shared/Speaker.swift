@preconcurrency import AVFoundation
import AbstractGatewayClient
import SwiftUI

/// Reads a text aloud with the gateway's voice (operator 2026-10-29: the watch cut the voice for 2–4 s
/// between segments the gateway had sent with no gap). Every received segment gets its own player and
/// is BOOKED ON THE AUDIO CLOCK the moment it arrives (`AVAudioPlayer.play(atTime:)` on the device
/// clock all players share): exactly where the previous one ends (`SpeechTimeline`), or at once when
/// the voice has run dry. Nothing waits for a "finished" callback to start the next segment, so a busy
/// main thread or a lowered wrist no longer opens a silence. The first start waits for 1.5 s of speech.
/// Each player keeps the speed chosen in Settings → Voice (time-stretched, not pitched); an answer's
/// recordings play after its text, at their own speed. watchOS has no `AVAudioUnitTimePitch`, so the
/// players stay `AVAudioPlayer`s.
@MainActor
final class Speaker: NSObject, ObservableObject {
    /// One received segment: `duration` in content seconds, `rate` its playback speed.
    private struct Chunk {
        let data: Data
        let duration: Double
        var frames: [VoiceFrame]
        let rate: Float
        var wall: Double { duration / Double(rate) }
    }

    /// A booked segment: its player, where it starts on the device clock, and from where in its chunk.
    private struct Booked {
        let index: Int
        let player: AVAudioPlayer
        let wallStart: TimeInterval
        let from: TimeInterval
        let wall: TimeInterval
    }

    enum State: Equatable { case idle, preparing, speaking, paused, finished, failed(String) }

    @Published private(set) var state: State = .idle
    /// Seconds of speech received so far and played so far (for the progress line).
    @Published private(set) var receivedSeconds: Double = 0
    @Published private(set) var playedSeconds: Double = 0
    /// The largest silence between two segments of this reading, in ms (0 when back to back; a
    /// segment that came late counts its lateness). DEBUG builds show it to the UI tests.
    @Published private(set) var maxGapMilliseconds: Double = 0

    private static let startBuffer = 1.5
    /// How far ahead of "now" a segment that can start at once is booked (the player's own lead).
    private static let lead: TimeInterval = 0.05
    /// The timeline's unit: microseconds of wall time on the device clock.
    private static let unit = 1_000_000.0

    /// Every segment of this reading, in order (a rewind reaches back into them).
    private var chunks: [Chunk] = []
    private var booked: [Booked] = []
    /// Received, not booked yet (before the first start).
    private var unbooked: [Int] = []
    private var timeline = SpeechTimeline(sampleRate: Speaker.unit, startBuffer: Speaker.startBuffer)
    /// The device time of the timeline's 0 (set at the first start, and again by a rewind / resume).
    private var clockStart: TimeInterval?
    /// Where this epoch starts in the reading: chunk `epochFirst`, `epochFrom` seconds into it.
    private var epochFirst = 0
    private var epochFrom: TimeInterval = 0
    /// Where the voice stands while paused (content seconds into the reading).
    private var pausedAt: Double?
    private var finishedPlayers = 0
    private var streamDone = false
    private let normalizer = VoiceNormalizer()
    private var task: Task<Void, Never>?
    private var analysisTasks: [Task<Void, Never>] = []
    /// This reading (`stop` starts a new one).
    private var reading = 0
    /// This speaker's keep-awake hold (one per speaker: two screens never release each other's).
    private let holder = "speak-" + UUID().uuidString
    /// The one voice playing: starting another stops it.
    private static weak var current: Speaker?
    /// The stream broke after some audio: once what arrived has played, the reading says so.
    private var streamError: String?
    /// The text has been spoken; its recordings are still downloading (the orb waits, not speaks).
    private var awaitingClips = false
    private var pausedFromPreparing = false
    /// A device clock for the timeline before any player exists (the first booking makes one).
    private var clockPlayer: AVAudioPlayer?

    private func trace(_ s: String) {
        #if DEBUG
        print("speaker \(Date().formatted(date: .omitted, time: .standard)) \(s)")
        #endif
    }

    override init() {
        super.init()
        // The system can stop the players underneath (an interruption, the app suspended with the
        // wrist down): an interruption pauses honestly and resumes when the system says so; the app
        // coming back to the front picks the voice up where it stopped.
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
    }

    deinit {
        let holder = holder
        Task { @MainActor in RuntimeKeeper.shared.release(holder) }
    }

    // MARK: State

    var isActive: Bool { state == .preparing || state == .speaking }
    /// Paused mid-sentence: `resume()` continues exactly there.
    var isPaused: Bool { state == .paused }

    /// The invariant of a reading: while it is speaking, something plays. If the system stopped the
    /// players underneath (nothing plays where the clock says something should), the voice goes on
    /// from where it stands.
    private func ensurePlaying() {
        guard state == .speaking, let now = deviceNow() else { return }
        let due = booked.first { $0.wallStart <= now && now < $0.wallStart + $0.wall }
        guard let due, !due.player.isPlaying else { return }
        trace("the voice had stopped: playing on")
        try? AVAudioSession.sharedInstance().setActive(true)
        RuntimeKeeper.shared.hold(holder)
        rebook(from: position())
    }

    /// Holds the voice where it is (segments still arriving are kept and booked on resume).
    func pause() {
        guard isActive else { return }
        pausedFromPreparing = state == .preparing
        let at = position()
        unbookAll()
        pausedAt = at
        state = .paused
        RuntimeKeeper.shared.release(holder)          // a paused voice never keeps the watch awake
        trace("paused at \(String(format: "%.2f", at)) s")
    }

    /// Continues from where `pause()` stopped.
    func resume() {
        guard state == .paused else { return }
        RuntimeKeeper.shared.hold(holder)
        try? AVAudioSession.sharedInstance().setActive(true)        // off since the pause, maybe
        let at = pausedAt ?? 0
        pausedAt = nil
        if timeline.started || at > 0 {
            state = .speaking
            rebook(from: at)
        } else {
            state = pausedFromPreparing ? .preparing : .speaking
        }
    }

    // MARK: Reading

    /// Plays recordings alone (a recording's own row, or its page).
    func play(clips: [MediaItem], client: any GatewayClient) { read("", scope: nil, client: client, clips: clips) }

    func read(_ markdown: String, scope: SpeechScope?, client: any GatewayClient, clips: [MediaItem] = []) {
        // The audio session stays active from one reading to the next (a voice picker's taps follow
        // each other): deactivating it between them could leave the next one silent.
        stop(keepSession: true)
        if let other = Self.current, other !== self { other.stop(keepSession: true) }
        Self.current = self
        // The whole text in one request: the gateway's voice speaks it in whole sentences, made ahead
        // of playback, in one language for the whole reply (abstractvoice 0.15.2).
        let spoken = scope == nil ? "" : SpeechText.plain(markdown)
        let clips = clips.filter { $0.kind == .audio }
        guard !spoken.isEmpty || !clips.isEmpty else { state = .failed("Nothing to read in this text."); return }
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playback, mode: .spokenAudio, policy: .default, options: [])
            try session.setActive(true)
        } catch {
            state = .failed("The watch refused audio playback: \(error.localizedDescription)")
            trace("session error \(error)")
            return
        }
        state = .preparing; streamDone = false; streamError = nil; receivedSeconds = 0; playedSeconds = 0; maxGapMilliseconds = 0
        let rate = Float(VoicePrefs.speed)
        RuntimeKeeper.shared.hold(holder)
        let mine = reading
        task = Task { [weak self] in
            // The recordings download while the text is spoken; they play after it, even when the
            // voice fails, and one that cannot be fetched does not keep the others from playing.
            async let recordings = Self.download(clips, client: client)
            var voiceError: Error?
            if let scope, !spoken.isEmpty {
                do {
                    for try await wav in client.speech(text: spoken, scope: scope, voice: VoicePrefs.voice(for: scope)) {
                        guard let self, !Task.isCancelled, mine == self.reading else { return }
                        self.receive(wav, rate: rate)
                    }
                } catch { voiceError = error }
            }
            guard let self, !Task.isCancelled, mine == self.reading else { return }
            let spokenSeconds = self.receivedSeconds
            if !clips.isEmpty { self.awaitingClips = true }
            let fetched = await recordings
            guard !Task.isCancelled, mine == self.reading else { return }
            self.awaitingClips = false
            for data in fetched.compactMap({ $0 }) {
                guard !Task.isCancelled else { return }
                self.receive(data, rate: 1)
            }
            if let error = voiceError {
                self.streamError = spokenSeconds > 0 ? "The voice stopped early. \(Self.describe(error))" : Self.describe(error)
                self.trace("voice failed after \(String(format: "%.1f", spokenSeconds)) s: \(error)")
            } else if fetched.contains(where: { $0 == nil }) {
                self.streamError = "A recording could not be played."
            }
            self.streamDone = true
            if self.state != .paused { self.book(self.timeline.finish(rendered: self.rendered())) }   // a short reading under the buffer
            self.finishIfDone()
        }
    }

    private static func download(_ clips: [MediaItem], client: any GatewayClient) async -> [Data?] {
        var out: [Data?] = []
        for clip in clips { out.append(try? await MediaStore.shared.data(clip, client: client)) }
        return out
    }

    func stop() { stop(keepSession: false) }

    /// `keepSession`: another reading starts right after (the session stays active for it).
    func stop(keepSession: Bool) {
        task?.cancel(); task = nil
        analysisTasks.forEach { $0.cancel() }; analysisTasks.removeAll()
        reading += 1
        #if DEBUG
        silenceProbe?.cancel(); silenceProbe = nil
        #endif
        unbookAll()
        chunks.removeAll(); unbooked.removeAll()
        timeline = SpeechTimeline(sampleRate: Self.unit, startBuffer: Self.startBuffer)
        epochFirst = 0; epochFrom = 0; pausedAt = nil
        if isActive || state == .paused { state = .idle }
        if keepSession { RuntimeKeeper.shared.release(holder) } else { release() }
    }

    // MARK: The audio clock

    /// The device clock all players share (nil before any player exists).
    private func deviceNow() -> TimeInterval? {
        (booked.last?.player ?? clockPlayer)?.deviceCurrentTime
    }

    /// Microseconds on the timeline now (0 before the first start).
    private func rendered() -> Int64 {
        guard let start = clockStart, let now = deviceNow() else { return 0 }
        return Int64(max(0, now - start) * Self.unit)
    }

    /// A segment arrived: kept, then booked on the clock at once (or kept for the first start).
    private func receive(_ data: Data, rate: Float) {
        guard let probe = try? AVAudioPlayer(data: data), probe.duration > 0 else {
            trace("a segment could not be decoded (\(data.count) bytes)"); return
        }
        if clockPlayer == nil { clockPlayer = probe }
        let index = chunks.count
        chunks.append(Chunk(data: data, duration: probe.duration, frames: [], rate: rate))
        receivedSeconds += probe.duration
        trace("segment \(data.count) bytes, received \(String(format: "%.1f", receivedSeconds)) s")
        analyze(index)
        unbooked.append(index)
        guard state != .paused else { return }
        book(timeline.receive(frames: Int64(chunks[index].wall * Self.unit), rendered: rendered()))
    }

    /// Books what the timeline says to book now: each segment's player is told when to start on the
    /// device clock, right where the previous one ends (or at once when the voice ran dry).
    private func book(_ bookings: [SpeechTimeline.Booking]) {
        guard !bookings.isEmpty else { return }
        for booking in bookings {
            guard !unbooked.isEmpty else { break }
            let index = unbooked.removeFirst()
            let chunk = chunks[index]
            let from = index == epochFirst ? epochFrom : 0
            guard let player = try? AVAudioPlayer(data: chunk.data) else {
                state = .failed("This speech could not be played."); stop(); return
            }
            player.delegate = self
            player.enableRate = true                           // the speed chosen in Settings → Voice
            player.rate = chunk.rate
            player.prepareToPlay()
            if from > 0 { player.currentTime = min(from, max(0, player.duration - 0.05)) }
            let now = player.deviceCurrentTime
            if clockStart == nil { clockStart = now + Self.lead - Double(booking.start) / Self.unit }
            let at = max((clockStart ?? now) + Double(booking.start) / Self.unit, now + Self.lead)
            if booking.gap > 0 { trace("late segment: \(Int(Double(booking.gap) / Self.unit * 1000)) ms of silence before it") }
            if let prev = booked.last {                        // the silence asked of the device clock
                let silence = at - (prev.wallStart + prev.wall)
                if silence > 0.001 { maxGapMilliseconds = max(maxGapMilliseconds, silence * 1000) }
            }
            guard player.play(atTime: at) else { state = .failed("The watch stopped the voice."); stop(); return }
            booked.append(Booked(index: index, player: player, wallStart: at, from: from, wall: (chunk.duration - from) / Double(chunk.rate)))
        }
        maxGapMilliseconds = max(maxGapMilliseconds, timeline.maxGapMilliseconds)
        #if DEBUG
        startSilenceProbe()
        #endif
        if state != .speaking, state != .paused {
            state = .speaking; WKHaptic.start()
            trace("speaking, route \(AVAudioSession.sharedInstance().currentRoute.outputs.map(\.portName))")
        }
    }

    #if DEBUG
    /// DEBUG: the longest silence actually heard between two segments, from the players themselves:
    /// every 10 ms, each sounding player tells where on the device clock it really started
    /// (`deviceCurrentTime - (currentTime - from) / rate`, the earliest estimate kept, `currentTime`
    /// moving in coarse steps), and the silence is the next one's real start minus this one's real end.
    private var silenceProbe: Task<Void, Never>?
    private func startSilenceProbe() {
        guard silenceProbe == nil else { return }
        let mine = reading
        silenceProbe = Task { [weak self] in
            var starts: [ObjectIdentifier: TimeInterval] = [:]
            while !Task.isCancelled {
                try? await Task.sleep(for: .milliseconds(10))
                guard let self, mine == self.reading else { return }
                // A pause or a rewind books new players: measure again after it.
                guard !self.booked.isEmpty, let now = self.deviceNow() else { starts.removeAll(); continue }
                for b in self.booked where b.player.isPlaying && b.player.currentTime > b.from + 0.0005 {
                    let id = ObjectIdentifier(b.player), start = now - (b.player.currentTime - b.from) / Double(b.player.rate)
                    starts[id] = min(starts[id] ?? start, start)
                }
                var previousEnd: TimeInterval?
                for b in self.booked {
                    guard let start = starts[ObjectIdentifier(b.player)] else { previousEnd = nil; continue }
                    if let end = previousEnd { self.maxGapMilliseconds = max(self.maxGapMilliseconds, (start - end) * 1000) }
                    previousEnd = start + b.wall
                }
            }
        }
    }
    #endif

    /// Stops every booked player (a pause, a rewind, a stop); what was received stays.
    private func unbookAll() {
        for b in booked { b.player.delegate = nil; b.player.stop() }
        booked.removeAll()
        finishedPlayers = 0
        clockStart = nil
    }

    /// Books the reading again from `seconds` into it (a resume, a rewind, the system having stopped it).
    private func rebook(from seconds: Double) {
        unbookAll()
        var index = 0, start = 0.0
        while index < chunks.count - 1, start + chunks[index].duration <= seconds { start += chunks[index].duration; index += 1 }
        epochFirst = index
        epochFrom = max(0, seconds - start)
        playedSeconds = seconds
        timeline = SpeechTimeline(sampleRate: Self.unit, startBuffer: 0)
        unbooked = Array(index..<chunks.count)
        var bookings: [SpeechTimeline.Booking] = []
        for c in unbooked {
            let wall = (chunks[c].duration - (c == index ? epochFrom : 0)) / Double(chunks[c].rate)
            bookings += timeline.receive(frames: Int64(max(0, wall) * Self.unit), rendered: 0)
        }
        // `epochFrom` is in the first booking's player (`book` reads it).
        book(bookings)
    }

    /// A booked segment has been heard (bookkeeping only: the next one is already booked).
    fileprivate func finished(_ player: AVAudioPlayer) {
        guard let b = booked.first(where: { $0.player === player }) else { return }
        finishedPlayers += 1
        playedSeconds += chunks[b.index].duration - b.from
        trace("segment \(b.index) heard, played \(String(format: "%.1f", playedSeconds)) s")
        finishIfDone()
    }

    private func finishIfDone() {
        let allHeard = unbooked.isEmpty && finishedPlayers >= booked.count
        guard streamDone, allHeard, isActive else {
            if !streamDone, awaitingClips, state == .speaking, allHeard { state = .preparing }
            return
        }
        // Silence never passes for a reading: no sound and no error is a failure with a reason.
        if let why = SpeechSample.failure(receivedSeconds: receivedSeconds, clipsPlayed: playedSeconds > 0, streamError: streamError) {
            state = .failed(why); trace("ended without playing: \(why)")
        } else {
            state = .finished
            trace("done, largest gap \(String(format: "%.0f", maxGapMilliseconds)) ms")
        }
        release()
    }

    // MARK: Position, rewind, the orb

    /// Seconds spoken so far, inside the current segment too.
    func position() -> Double {
        if let pausedAt { return pausedAt }
        // Where this epoch starts in the reading, then what its booked players have spoken since.
        let base = chunks.prefix(epochFirst).reduce(0) { $0 + $1.duration } + epochFrom
        guard let now = deviceNow() else { return base }
        var spoken = 0.0
        for b in booked where b.wallStart <= now {
            spoken += min(now - b.wallStart, b.wall) * Double(chunks[b.index].rate)
        }
        return base + spoken
    }

    /// Something has been spoken that a rewind can go back to.
    var canRewind: Bool { position() > 0.5 }

    /// Goes back `seconds` in what was spoken and goes on from there; paused stays paused at the new
    /// place, a finished reading speaks again from there.
    func rewind(_ seconds: Double = 10) {
        guard !chunks.isEmpty else { return }
        let target = max(0, position() - seconds)
        if state == .paused { pausedAt = target; trace("rewound to \(String(format: "%.1f", target)) s (paused)"); return }
        if !isActive {                                    // finished (or stopped early): speak again
            try? AVAudioSession.sharedInstance().setActive(true)
            RuntimeKeeper.shared.hold(holder)
            state = .preparing
        }
        trace("rewound \(seconds) s, to \(String(format: "%.1f", target)) s")
        rebook(from: target)
    }

    /// The rewind button: back `seconds` and play from there (paused, a rewind alone would be silent
    /// and look like nothing happened).
    func rewindAndPlay(_ seconds: Double = 10) {
        rewind(seconds)
        if state == .paused { resume() }
    }

    /// What the orb follows: the analysed frame of the segment playing now, scaled to the voice's
    /// recent range; silence while nothing plays.
    func features(at t: Double) -> VoiceFeatures {
        guard let now = deviceNow(), let b = booked.first(where: { $0.wallStart <= now && now < $0.wallStart + $0.wall }),
              b.player.isPlaying, !chunks[b.index].frames.isEmpty else { return normalizer.push(.silent, at: t) }
        let frames = chunks[b.index].frames
        let into = b.from + (now - b.wallStart) * Double(chunks[b.index].rate)
        return normalizer.push(frames[max(0, min(frames.count - 1, Int(into * 60)))], at: t)
    }

    /// Segments up to this size are analysed for the orb (in the background, never before playback).
    private static let analysedBytes = 4 * 1024 * 1024

    private func analyze(_ index: Int) {
        let data = chunks[index].data
        guard data.count <= Self.analysedBytes else { return }
        let mine = reading
        analysisTasks.append(Task { [weak self] in
            let result = await Task.detached(priority: .utility) { VoiceAnalyzer.frames(ofWAV: data) }.value
            guard !Task.isCancelled, let self, mine == self.reading, index < self.chunks.count else { return }
            self.chunks[index].frames = result
        })
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
    }

    nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        let ref = PlayerRef(player)
        Task { @MainActor in self.finished(ref.player) }
    }
}

private struct PlayerRef: @unchecked Sendable { let player: AVAudioPlayer; init(_ p: AVAudioPlayer) { player = p } }

import WatchKit
private enum WKHaptic { @MainActor static func start() { WKInterfaceDevice.current().play(.start) } }
