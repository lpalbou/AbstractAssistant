import Foundation
import Testing
@testable import AbstractGatewayClient

/// `SpeechPieceRetry` and `SpeechWAV`: a piece whose stream broke after some of its sound arrived is
/// requested again, and the retry's stream skips exactly that sound, so the person hears the piece
/// once — nothing twice, nothing lost (council 2026-11-02, A3).
@Suite struct SpeechRetryTests {
    /// A 16 kHz mono 16-bit WAV of these PCM bytes.
    private func wav(_ pcm: ArraySlice<UInt8>, rate: Int = 16_000, channels: Int = 1, bits: Int = 16, format: Int = 1, extra: [UInt8] = []) -> Data {
        var h: [UInt8] = []
        func u32(_ v: Int) { for k in 0..<4 { h.append(UInt8((v >> (8 * k)) & 0xFF)) } }
        func u16(_ v: Int) { for k in 0..<2 { h.append(UInt8((v >> (8 * k)) & 0xFF)) } }
        let align = channels * bits / 8
        h += Array("RIFF".utf8); u32(36 + extra.count + pcm.count); h += Array("WAVE".utf8)
        h += Array("fmt ".utf8); u32(16); u16(format); u16(channels); u32(rate); u32(rate * align); u16(align); u16(bits)
        h += extra
        h += Array("data".utf8); u32(pcm.count)
        return Data(h + pcm)
    }
    private func pcm(_ wav: Data) -> [UInt8] { Array([UInt8](wav).dropFirst(44)) }
    /// The piece's whole sound (2 s), and that sound cut into chunks of these seconds.
    private let piece = Array([UInt8](SyntheticSpeech.wav(seconds: 2.0, seed: 3)).dropFirst(44))
    private func chunks(_ seconds: [Double], from offset: Double = 0) -> [Data] {
        var at = Int(offset * 16_000) * 2
        return seconds.map { s in
            let end = min(piece.count, at + Int(s * 16_000) * 2)
            defer { at = end }
            return wav(piece[at..<end])
        }
    }

    @Test func aFirstRequestKeepsEverySound() {
        var retry = SpeechPieceRetry()
        #expect(retry.admit(seconds: 1.0) == .keep(trimming: 0))
        #expect(retry.admit(seconds: 0.5) == .keep(trimming: 0))
        #expect(retry.kept == 1.5)
    }

    /// Two of four half-second chunks arrived (and played) before the stream broke: the retry's
    /// first two are dropped, the last two play; the piece's two seconds are kept once.
    @Test func aRetryDropsTheWholeChunksAlreadyHere() {
        var retry = SpeechPieceRetry()
        _ = retry.admit(seconds: 0.5); _ = retry.admit(seconds: 0.5)
        retry.requestAgain()
        #expect([0.5, 0.5, 0.5, 0.5].map { retry.admit(seconds: $0) } == [.drop, .drop, .keep(trimming: 0), .keep(trimming: 0)])
        #expect(abs(retry.kept - 2.0) < 1e-9)
    }

    /// The retry's chunks do not fall on the first request's boundaries: the one across it is trimmed.
    @Test func theChunkAcrossTheBoundaryIsTrimmed() {
        var retry = SpeechPieceRetry()
        _ = retry.admit(seconds: 0.7)
        retry.requestAgain()
        let decisions = [0.5, 0.5, 0.5, 0.5].map { retry.admit(seconds: $0) }
        #expect(decisions.count == 4 && decisions[0] == .drop && decisions[2] == .keep(trimming: 0))
        guard case .keep(let trim) = decisions[1] else { Issue.record("the boundary chunk was not kept"); return }
        #expect(abs(trim - 0.2) < 1e-9)
        #expect(abs(retry.kept - 2.0) < 1e-9)
    }

    /// A retry that breaks too skips, on the next one, everything kept by both.
    @Test func aSecondBreakSkipsWhatBothRequestsKept() {
        var retry = SpeechPieceRetry()
        _ = retry.admit(seconds: 0.5)
        retry.requestAgain()
        #expect(retry.admit(seconds: 0.5) == .drop)
        #expect(retry.admit(seconds: 0.5) == .keep(trimming: 0))
        retry.requestAgain()
        #expect([0.5, 0.5, 0.5, 0.5].map { retry.admit(seconds: $0) } == [.drop, .drop, .keep(trimming: 0), .keep(trimming: 0)])
        #expect(abs(retry.kept - 2.0) < 1e-9)
    }

    /// The whole rule on real WAV bytes: the first request sends 0.7 s and breaks, the second sends
    /// 0.25 s and breaks, the third sends the piece in half seconds. What plays, put end to end, is the
    /// piece's sound exactly once, sample for sample.
    @Test func whatPlaysIsThePieceOnceSampleForSample() throws {
        var retry = SpeechPieceRetry()
        var heard: [UInt8] = []
        func receive(_ attempt: [Data]) throws { for c in attempt { if let kept = try retry.admit(wav: c) { heard += pcm(kept) } } }
        try receive(chunks([0.7]))
        retry.requestAgain()
        try receive(chunks([0.4, 0.55]))                     // breaks after 0.95 s: 0.25 s past what was kept
        retry.requestAgain()
        try receive(chunks([0.5, 0.5, 0.5, 0.5]))
        #expect(heard.count == piece.count)
        #expect(heard == piece, "a sound was heard twice or lost at a seam")
        // Without the skip, the retry's sound plays from the piece's start again.
        var naive: [UInt8] = []
        for c in chunks([0.7]) + chunks([0.5, 0.5, 0.5, 0.5]) { naive += pcm(c) }
        #expect(naive.count > piece.count)
    }

    @Test func aWAVIsMeasuredAndCutOnItsFrames() throws {
        let whole = SyntheticSpeech.wav(seconds: 2.0, seed: 1)
        #expect(SpeechWAV.duration(of: whole) == 2.0)
        let cut = try SpeechWAV.dropping(seconds: 0.75, from: whole)
        #expect(SpeechWAV.duration(of: cut) == 1.25)
        #expect(pcm(cut) == Array(pcm(whole).dropFirst(12_000 * 2)))
        let b = [UInt8](cut)
        func u32(_ i: Int) -> Int { Int(b[i]) | Int(b[i + 1]) << 8 | Int(b[i + 2]) << 16 | Int(b[i + 3]) << 24 }
        #expect(u32(4) == b.count - 8)                       // RIFF size
        #expect(u32(40) == b.count - 44)                     // data size
        // Nothing to cut: the same bytes; everything: an empty data chunk.
        #expect(try SpeechWAV.dropping(seconds: 0, from: whole) == whole)
        #expect(SpeechWAV.duration(of: try SpeechWAV.dropping(seconds: 9, from: whole)) == 0)
    }

    /// A float stereo WAV with a LIST chunk before its data, and one whose data size was never
    /// written (a streamed WAV): measured on their frames all the same.
    @Test func otherLayoutsAreMeasuredToo() {
        let stereo = wav(ArraySlice(Array(repeating: 0, count: 24_000 * 8)), rate: 24_000, channels: 2, bits: 32, format: 3,
                         extra: Array("LIST".utf8) + [4, 0, 0, 0] + Array("INFO".utf8))
        #expect(SpeechWAV.duration(of: stereo) == 1.0)
        var open = [UInt8](SyntheticSpeech.wav(seconds: 0.5, seed: 1))
        open.replaceSubrange(40..<44, with: [0xFF, 0xFF, 0xFF, 0xFF])
        #expect(SpeechWAV.duration(of: Data(open)) == 0.5)
    }

    @Test func aChunkThatIsNoWAVCannotBePlaced() {
        var retry = SpeechPieceRetry()
        #expect(throws: SpeechWAV.Unreadable.self) { try retry.admit(wav: Data("ID3 not a wav".utf8)) }
        #expect(SpeechWAV.duration(of: Data()) == nil)
    }
}
