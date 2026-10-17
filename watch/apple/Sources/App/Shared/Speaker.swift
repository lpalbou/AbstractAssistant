@preconcurrency import AVFoundation
import AbstractGatewayClient
import SwiftUI

/// Reads a text aloud with the gateway's voice: the speech stream's WAV chunks play back to back
/// through one AVAudioPlayer at a time, metered so the orb can follow the voice.
@MainActor
final class Speaker: NSObject, ObservableObject {
    enum State: Equatable { case idle, preparing, speaking, paused, finished, failed(String) }

    @Published private(set) var state: State = .idle
    /// Seconds of speech received so far and played so far (for the progress line).
    @Published private(set) var receivedSeconds: Double = 0
    @Published private(set) var playedSeconds: Double = 0

    private var queue: [Data] = []
    /// Chunks already spoken, in order (rewind reaches back into them), and the one playing now.
    private var history: [(data: Data, duration: Double)] = []
    private var currentData: Data?
    /// Where the next chunk starts (a rewind into the middle of an earlier chunk).
    private var startAt: TimeInterval = 0
    private var player: AVAudioPlayer?
    private var streamDone = false
    private var task: Task<Void, Never>?
    private var smoothed: Double = 0
    /// This speaker's keep-awake hold (one per speaker: two screens never release each other's).
    private let holder = "speak-" + UUID().uuidString
    /// The one voice playing: starting another stops it.
    private static weak var current: Speaker?
    /// The stream broke after some audio: once what arrived has played, the reading says so.
    private var streamError: String?
    private var peak: Double = 0

    private func trace(_ s: String) {
        #if DEBUG
        print("speaker \(Date().formatted(date: .omitted, time: .standard)) \(s)")
        #endif
    }

    override init() {
        super.init()
        #if DEBUG
        let center = NotificationCenter.default
        center.addObserver(forName: AVAudioSession.interruptionNotification, object: nil, queue: .main) { note in
            let type = note.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt ?? 99
            print("speaker interruption type \(type) (1 began, 0 ended) \(note.userInfo ?? [:])")
        }
        center.addObserver(forName: AVAudioSession.routeChangeNotification, object: nil, queue: .main) { note in
            print("speaker route change \(note.userInfo?[AVAudioSessionRouteChangeReasonKey] ?? "?")")
        }
        #endif
    }

    var isActive: Bool { state == .preparing || state == .speaking }
    /// Paused mid-sentence: `resume()` continues exactly there.
    var isPaused: Bool { state == .paused }
    private var pausedFromPreparing = false

    /// Holds the voice where it is (the current chunk's position is kept; chunks still arriving wait).
    func pause() {
        guard isActive else { return }
        pausedFromPreparing = state == .preparing
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
            player.play()
        } else {
            state = pausedFromPreparing && queue.isEmpty ? .preparing : .speaking
            advanceIfIdle()
        }
    }

    func read(_ markdown: String, scope: SpeechScope, client: any GatewayClient) {
        stop()
        if let other = Self.current, other !== self { other.stop() }
        Self.current = self
        let pieces = SpeechText.segments(markdown)
        guard !pieces.isEmpty else { state = .failed("Nothing to read in this text."); return }
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playback, mode: .spokenAudio, policy: .default, options: [])
            try session.setActive(true)
        } catch {
            state = .failed("The watch refused audio playback: \(error.localizedDescription)")
            trace("session error \(error)")
            return
        }
        state = .preparing; streamDone = false; streamError = nil; receivedSeconds = 0; playedSeconds = 0
        RuntimeKeeper.shared.hold(holder)
        task = Task { [weak self] in
            do {
                // One request per piece, in order: piece n+1 is synthesized while piece n plays.
                for piece in pieces {
                    for try await wav in client.speech(text: piece, scope: scope) {
                        guard let self, !Task.isCancelled else { return }
                        self.enqueue(wav)
                    }
                    guard !Task.isCancelled else { return }
                }
                self?.streamDone = true
                self?.advanceIfIdle()
            } catch {
                guard let self, !Task.isCancelled else { return }
                self.streamDone = true
                self.streamError = Self.describe(error)
                self.trace("stream failed after \(String(format: "%.1f", self.receivedSeconds)) s: \(error)")
                if self.player == nil && self.queue.isEmpty {
                    self.state = .failed(Self.describe(error))
                    self.trace("stream error \(error)")
                    self.release()
                }
            }
        }
    }

    func stop() {
        task?.cancel(); task = nil
        player?.stop(); player = nil
        queue.removeAll(); history.removeAll(); currentData = nil; startAt = 0
        if isActive || state == .paused { state = .idle }
        release()
    }

    /// Something has been spoken that a rewind can go back to.
    var canRewind: Bool { position() > 0.5 || !history.isEmpty }

    /// Goes back `seconds` in what was spoken (into earlier chunks if needed) and goes on from
    /// there; paused stays paused at the new place, a finished reading speaks again from there.
    func rewind(_ seconds: Double = 10) {
        var back = seconds
        if let p = player {
            if p.currentTime >= back { p.currentTime -= back; trace("rewound within the chunk"); return }
            back -= p.currentTime
            p.stop(); player = nil
            if let d = currentData { queue.insert(d, at: 0) }
        }
        currentData = nil
        var offset: Double = 0
        while let last = history.popLast() {
            playedSeconds -= last.duration
            queue.insert(last.data, at: 0)
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

    /// Seconds spoken so far, inside the current sentence too.
    func position() -> Double { playedSeconds + (player?.currentTime ?? 0) }

    /// 0…1 loudness of what is playing now, smoothed; called by the orb every frame.
    func level() -> Double {
        guard let player, player.isPlaying else { smoothed *= 0.85; return smoothed }
        player.updateMeters()
        let db = Double(player.averagePower(forChannel: 0))          // -160…0 dBFS
        let linear = max(0, min(1, (db + 42) / 38))
        peak = max(peak, linear)
        smoothed = linear > smoothed ? 0.55 * linear + 0.45 * smoothed : 0.25 * linear + 0.75 * smoothed
        return smoothed
    }

    private func enqueue(_ wav: Data) {
        queue.append(wav)
        if let p = try? AVAudioPlayer(data: wav) { receivedSeconds += p.duration }
        trace("chunk \(wav.count) bytes, received \(String(format: "%.1f", receivedSeconds)) s")
        advanceIfIdle()
    }

    private func advanceIfIdle() {
        guard player == nil, state != .paused else { return }
        guard !queue.isEmpty else {
            if streamDone, isActive {
                if let why = streamError { state = .failed("The voice stopped early. \(why)"); trace("ended early: \(why)") }
                else { state = .finished; trace("done") }
                release()
            }
            return
        }
        loadNext(play: true)
    }

    /// The next chunk in the player (at `startAt`), playing or held for `resume()`.
    private func loadNext(play: Bool) {
        let next = queue.removeFirst()
        do {
            let p = try AVAudioPlayer(data: next)
            p.isMeteringEnabled = true
            p.delegate = self
            p.prepareToPlay()
            if startAt > 0 { p.currentTime = min(startAt, max(0, p.duration - 0.05)); startAt = 0 }
            currentData = next
            player = p
            guard play else { return }
            guard p.play() else { throw GatewayError.invalidResponse }
            trace("playing \(String(format: "%.1f", p.duration)) s, route \(AVAudioSession.sharedInstance().currentRoute.outputs.map(\.portName))")
            if state != .speaking { state = .speaking; WKHaptic.start() }
        } catch {
            state = .failed("This speech could not be played (\(error.localizedDescription)).")
            stop()
        }
    }

    fileprivate func finishedChunk(_ p: AVAudioPlayer) {
        guard p === player else { return }
        playedSeconds += p.duration
        if let d = currentData { history.append((d, p.duration)) }
        currentData = nil
        trace("finished chunk, played \(String(format: "%.1f", playedSeconds)) s, peak level \(String(format: "%.2f", peak))")
        peak = 0
        player = nil
        advanceIfIdle()
    }

    private func release() {
        RuntimeKeeper.shared.release(holder)
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
        #if DEBUG
        if !flag { print("speaker chunk ended UNSUCCESSFULLY") }
        #endif
        let ref = PlayerRef(player)
        Task { @MainActor in self.finishedChunk(ref.player) }
    }
}

private struct PlayerRef: @unchecked Sendable { let player: AVAudioPlayer; init(_ p: AVAudioPlayer) { player = p } }

import WatchKit
private enum WKHaptic { @MainActor static func start() { WKInterfaceDevice.current().play(.start) } }
