import Foundation

/// How a spoken reading ends, and the one line a voice picker shows for it (operator 2026-10-29:
/// choosing a voice sometimes played nothing, and nothing said why). Pure, so it is tested here.
public enum SpeechSample {
    /// The failure of a reading that ended (`nil`: it played). A stream that ended with no sound and
    /// no error is a failure too: silence must never pass for a sample.
    public static func failure(receivedSeconds: Double, clipsPlayed: Bool, streamError: String?) -> String? {
        if let streamError, !streamError.isEmpty { return streamError }
        if receivedSeconds <= 0, !clipsPlayed { return "The gateway sent no sound for this voice." }
        return nil
    }

    /// The row's one line under a voice whose sample did not play.
    public static func line(_ why: String) -> String {
        let reason = why.trimmingCharacters(in: .whitespacesAndNewlines)
        return reason.isEmpty ? "The sample did not play." : "The sample did not play: \(reason)"
    }
}
