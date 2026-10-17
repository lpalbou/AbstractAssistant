import Foundation

/// Local capture policy. Only confirmed speech followed by three quiet seconds permits networking.
public struct VoiceTurn: Sendable {
    public enum Phase: Sendable { case idle, authorizing, recording, countdown, ready, transcribing }
    public private(set) var phase: Phase = .idle
    public private(set) var deadline: TimeInterval?
    public private(set) var heardSpeech = false
    private var startedAt: TimeInterval = 0
    private var lastSample: TimeInterval = 0
    private var quietDuration: TimeInterval = 0
    private var onsetDuration: TimeInterval = 0
    public static let grace: TimeInterval = 3
    public init() {}
    public mutating func begin() -> Bool {
        guard phase == .idle else { cancel(); return false }
        phase = .authorizing; return true
    }
    public mutating func recordingStarted(at now: TimeInterval) -> Bool {
        guard phase == .authorizing else { return false }
        startedAt = now; lastSample = now; phase = .recording; return true
    }
    public mutating func sample(at now: TimeInterval, speech: Bool?) {
        guard phase == .recording || phase == .countdown else { return }
        let gap = now - lastSample
        let elapsed = gap <= 0.25 ? max(0, min(0.1, gap)) : 0; lastSample = now
        if gap > 0.25 { quietDuration = 0; onsetDuration = 0 } // Unobserved time is never treated as silence.
        guard let speech else { quietDuration = 0; onsetDuration = 0; deadline = nil; phase = .recording; return }
        // Process resumed speech BEFORE checking the deadline, including at the final sample.
        if speech {
            onsetDuration += elapsed; heardSpeech = heardSpeech || onsetDuration >= 0.18
            quietDuration = 0; deadline = nil; phase = .recording
        } else {
            onsetDuration = 0
            if heardSpeech {
                if gap <= 0.25 { quietDuration += elapsed }
                deadline = now + max(0, Self.grace - quietDuration); phase = .recording
                // Ordinary spaces between syllables do not flash a countdown.
                if quietDuration >= 0.4 { phase = .countdown }
                if quietDuration >= Self.grace - 0.000001 { phase = .ready }
            }
        }
        if !heardSpeech && now - startedAt >= 8 { cancel() }
    }
    public func secondsRemaining(at now: TimeInterval) -> Int {
        guard phase == .countdown, let deadline else { return 0 }
        return max(0, min(3, Int(ceil(deadline - now))))
    }
    public mutating func claimForTranscription() -> Bool {
        guard phase == .ready else { return false }; phase = .transcribing; return true
    }
    public mutating func cancel() { self = VoiceTurn() }
}

/// Raw microphone power drives silence detection, independently of the animated envelope.
public struct SpeechActivity: Sendable {
    private var noiseFloor: Double = -65
    private var active = false
    public init() {}
    public mutating func sample(averageDB: Float) -> Bool {
        guard averageDB.isFinite else { active = false; return false }
        let db = Double(averageDB)
        let onset = min(-34, max(-50, noiseFloor + 12))
        active = db >= (active ? onset - 7 : onset)
        if !active { noiseFloor += (max(-80, min(-35, db)) - noiseFloor) * 0.02 }
        return active
    }
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
