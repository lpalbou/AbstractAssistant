import Foundation

/// Local-only capture policy. Networking is permitted only after `claimForTranscription`.
public struct VoiceTurn: Sendable {
    public enum Phase: Sendable { case idle, authorizing, recording, atLimit, countdown, ready, transcribing }
    public private(set) var phase: Phase = .idle
    public private(set) var deadline: TimeInterval?
    private var startedAt: TimeInterval?
    public static let grace: TimeInterval = 3
    public init() {}
    public var isPending: Bool { phase != .idle }
    public mutating func begin() -> Bool {
        guard phase == .idle else { cancel(); return false }
        phase = .authorizing; return true
    }
    public mutating func recordingStarted(at now: TimeInterval) -> Bool {
        guard phase == .authorizing else { return false }
        startedAt = now; phase = .recording; return true
    }
    /// Holding owns recording, including pauses. Release seals audio and starts a fresh grace.
    public mutating func release(at now: TimeInterval) {
        guard phase == .recording || phase == .atLimit, let startedAt, now - startedAt >= 0.25 else { cancel(); return }
        phase = .countdown; deadline = now + Self.grace
    }
    public mutating func reachedLimit() { if phase == .recording { phase = .atLimit } }
    public func secondsRemaining(at now: TimeInterval) -> Int {
        guard phase == .countdown, let deadline else { return 0 }
        return max(0, min(3, Int(ceil(deadline - now))))
    }
    public mutating func advance(to now: TimeInterval) {
        if phase == .countdown, let deadline, now >= deadline { phase = .ready }
    }
    public mutating func claimForTranscription() -> Bool {
        guard phase == .ready else { return false }; phase = .transcribing; return true
    }
    public mutating func cancel() { phase = .idle; deadline = nil; startedAt = nil }
}

/// A finite, fast-attack envelope shared by microphone and playback meters.
public struct AudioEnvelope: Sendable {
    public private(set) var level: Double = 0
    public init() {}
    @discardableResult public mutating func sample(averageDB: Float, peakDB: Float) -> Double {
        let db = max(Double(averageDB), Double(peakDB) - 7)
        let normalized = db.isFinite ? max(0, min(1, (db + 60) / 48)) : 0
        let target = pow(normalized, 1.4)
        level += (target - level) * (target > level ? 0.85 : 0.24)
        return level
    }
    public mutating func reset() { level = 0 }
}
