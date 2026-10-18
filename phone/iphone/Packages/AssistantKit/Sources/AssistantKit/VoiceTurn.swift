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

/// A finite, fast-attack playback envelope that preserves loud syllable dynamics.
public struct AudioEnvelope: Sendable {
    public private(set) var level: Double = 0
    public init() {}
    @discardableResult public mutating func sample(averageDB: Float, peakDB: Float) -> Double {
        let db = max(Double(averageDB), Double(peakDB) - 7)
        // A soft knee preserves loud syllables: a linear dB ramp saturated at -12 dB,
        // making normalized TTS and nearby speech look almost constant.
        let amplitude = db.isFinite ? pow(10, min(0, max(-160, db)) / 20) : 0
        let target = pow(max(0, (amplitude - 0.001) / (amplitude + 0.08)), 0.6)
        level += (target - level) * (target > level ? 0.9 : 0.4)
        return level
    }
    public mutating func reset() { level = 0 }
}

/// Microphone dBFS occupies a much quieter range than mastered playback. Normalize its
/// visible motion to recent speech above the room floor, without changing recorded audio
/// or feeding the normalized value back into speech/silence detection.
public struct MicrophoneEnvelope: Sendable {
    public private(set) var level: Double = 0
    private var noiseFloor: Double = -65
    private var recentPeak: Double = -42
    private var stationaryLow: Double = -160
    private var stationaryHigh: Double = -160
    private var stationarySamples = 0
    public init() {}
    @discardableResult public mutating func sample(averageDB: Float, peakDB: Float, speech: Bool) -> Double {
        guard averageDB.isFinite else { return smooth(0) }
        let average = min(0, max(-160, Double(averageDB)))
        // A stable scalar signal can be room noise even when raw VAD calls it speech.
        // After 1.5 s within 3 dB, let the DISPLAY baseline follow it independently.
        // This may also soften a perfectly sustained vowel; no display adjustment
        // ever feeds back into the recording or the three-second silence detector.
        if stationarySamples == 0 || average < stationaryHigh - 3 || average > stationaryLow + 3 {
            stationaryLow = average; stationaryHigh = average; stationarySamples = 1
        } else {
            stationaryLow = min(stationaryLow, average); stationaryHigh = max(stationaryHigh, average)
            stationarySamples = min(45, stationarySamples + 1)
        }
        // The peak meter may retain a transient, so it cannot raise either the room
        // floor or a quiet frame by more than 3 dB.
        if !speech || stationarySamples >= 45 {
            let room = min(-35, max(-80, average))
            noiseFloor += (room - noiseFloor) * (room < noiseFloor ? 0.2 : 0.12)
        }
        let peak = peakDB.isFinite ? Double(peakDB) : average
        let db = min(average + 3, max(average, peak - 9))
        if db > recentPeak { recentPeak = db }
        else { recentPeak += (db - recentPeak) * 0.016 }
        // A minimum 18 dB span prevents tiny changes in steady room noise from
        // filling the orb. The absolute lower gate keeps digital silence silent.
        let floor = max(-80, noiseFloor + 3)
        let span = max(18, recentPeak - floor)
        let aboveRoom = max(0, average - floor)
        let normalized = max(0, min(1, min(db - floor, aboveRoom + 3) / span))
        return smooth(pow(normalized, 0.75))
    }
    @discardableResult private mutating func smooth(_ target: Double) -> Double {
        level += (target - level) * (target > level ? 0.85 : 0.5)
        return level
    }
    public mutating func reset() { self = MicrophoneEnvelope() }
}
