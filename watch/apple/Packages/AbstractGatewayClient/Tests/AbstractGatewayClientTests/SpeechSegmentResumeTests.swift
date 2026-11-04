import Foundation
import Testing
@testable import AbstractGatewayClient

/// `SpeechPieceRetry` with the stream's text segments (AbstractVoice ADR 0009): a retry asks only for
/// the text after the last `segment_end`, and skips only the seconds already here of the segment that
/// did not end. The streams are recorded event lists as the gateway sends them (offsets in Unicode
/// scalars of the requested text).
@Suite struct SpeechSegmentResumeTests {
    private let text = "Bonjour ! Il est 14 h 30 👍🏽. Déjà fini ? Oui, à demain."
    // Segments of `text`: [0, 28) "Bonjour ! Il est 14 h 30 👍🏽.", [28, 40) " Déjà fini ?", [40, 55) the rest.
    private let ends = [28, 40, 55]
    /// One segment's sound (a distinct tone per segment, the same on every request).
    private func sound(_ segment: Int, seconds: Double = 1.0) -> [UInt8] {
        Array([UInt8](SyntheticSpeech.wav(seconds: seconds, seed: segment + 1)).dropFirst(44))
    }
    private func chunk(_ pcm: ArraySlice<UInt8>) -> SpeechPart { .audio(SyntheticSpeech.wav(pcm: pcm)) }
    /// A segment's sound cut in chunks of `seconds`; `upTo` stops early (the stream broke there).
    private func audio(_ segment: Int, chunks seconds: Double, upTo: Double? = nil) -> [SpeechPart] {
        let s = sound(segment), step = Int(seconds * 16_000) * 2, stop = upTo.map { Int($0 * 16_000) * 2 } ?? s.count
        return stride(from: 0, to: min(stop, s.count), by: step).map { chunk(s[$0..<min($0 + step, stop, s.count)]) }
    }
    private func pcm(_ wav: Data) -> [UInt8] { Array([UInt8](wav).dropFirst(44)) }

    /// Plays a recorded stream through the retry; returns the sound that would play.
    private func play(_ parts: [SpeechPart], _ retry: inout SpeechPieceRetry) throws -> [UInt8] {
        var heard: [UInt8] = []
        for part in parts {
            switch part {
            case .segmentEnd(let end): retry.segmentEnded(textEnd: end)
            case .audio(let wav): if let kept = try retry.admit(wav: wav) { heard += pcm(kept) }
            case .identity: break
            }
        }
        return heard
    }

    /// The stream breaks 0.4 s into segment 1. The retry asks for the text after segment 0 only and
    /// skips 0.4 s of its first segment: segment 0 is never voiced twice, and what plays is every
    /// segment once, sample for sample.
    @Test func aBreakInsideASegmentResumesAfterTheLastEndedOne() throws {
        var retry = SpeechPieceRetry()
        #expect(retry.text(of: text) == text)
        var heard = try play(audio(0, chunks: 0.5) + [.segmentEnd(textEnd: ends[0])] + audio(1, chunks: 0.2, upTo: 0.4), &retry)
        retry.requestAgain()
        let rest = try #require(retry.text(of: text))
        #expect(rest == " Déjà fini ? Oui, à demain.", "the retry asks again for a segment that had ended")
        #expect(abs(retry.skipping - 0.4) < 0.001, "the retry skips more than the unfinished segment's sound")
        // The retried stream's offsets index the retried text.
        heard += try play(audio(1, chunks: 0.3) + [.segmentEnd(textEnd: ends[1] - ends[0])]
                          + audio(2, chunks: 0.5) + [.segmentEnd(textEnd: ends[2] - ends[0])], &retry)
        #expect(heard == sound(0) + sound(1) + sound(2), "a sound was heard twice or lost at a seam")
        #expect(retry.text(of: text) == nil)
    }

    /// A sampling voice says segment 1 faster on the retry (0.3 s, not the 0.4 s already here): the skip
    /// stops at its end, so segment 2 plays whole instead of losing its first 0.1 s.
    @Test func theSkipStopsAtTheRetriedSegmentsEnd() throws {
        var retry = SpeechPieceRetry()
        _ = try play(audio(0, chunks: 0.5) + [.segmentEnd(textEnd: ends[0])] + audio(1, chunks: 0.2, upTo: 0.4), &retry)
        retry.requestAgain()
        let shorter = audio(1, chunks: 0.3, upTo: 0.3)
        let heard = try play(shorter + [.segmentEnd(textEnd: ends[1] - ends[0])] + audio(2, chunks: 0.25), &retry)
        #expect(heard == sound(2), "the next segment lost its start, or the retried one replayed")
    }

    /// The stream broke after a segment's end: nothing of the ended text is asked again and nothing
    /// is skipped; after the last segment's end, nothing is left to ask for.
    @Test func aBreakAtASegmentEndIsExact() throws {
        var retry = SpeechPieceRetry()
        _ = try play(audio(0, chunks: 0.5) + [.segmentEnd(textEnd: ends[0])], &retry)
        retry.requestAgain()
        #expect(retry.text(of: text) == " Déjà fini ? Oui, à demain." && retry.skipping == 0)
        _ = try play(audio(1, chunks: 0.5) + [.segmentEnd(textEnd: ends[1] - ends[0])] + audio(2, chunks: 0.5)
                     + [.segmentEnd(textEnd: ends[2] - ends[0])], &retry)
        retry.requestAgain()
        #expect(retry.text(of: text) == nil)
    }

    /// A gateway whose engine reports no segments: the retry asks for the whole piece and skips every
    /// second already here (the rule before segments).
    @Test func noSegmentsMeansTheWholePieceAndEverySecondSkipped() throws {
        var retry = SpeechPieceRetry()
        _ = try play(audio(0, chunks: 0.5, upTo: 0.5), &retry)
        retry.requestAgain()
        #expect(retry.text(of: text) == text && abs(retry.skipping - 0.5) < 0.001)
    }
}
