import Foundation

/// Where the retry of a speech piece picks up (council 2026-11-02, A3: a retry replayed up to ~40 s
/// the person had already heard). When a piece's stream breaks, the sound of that piece that already
/// arrived stays queued and plays on: nothing is cut or dropped. The piece is requested again, and
/// the new stream's first `kept` seconds — the sound already here — are skipped: whole chunks are
/// dropped, the chunk across the boundary is trimmed to the sample. The seam is exact when the
/// gateway voices the same text to the same sound on the retry. A sampling engine (Qwen3-TTS, and
/// cloned voices above all: no seed, and the speaker check may regenerate a segment) voices it with
/// a different length, so the seam lands within a few words of the true one, at worst about a
/// sentence; it never replays the piece. An exact seam needs segment-aware stream offsets from the
/// gateway, which will replace this skip. Pure, so it is tested in this package and shared by the
/// watch and the iPhone.
public struct SpeechPieceRetry: Sendable, Equatable {
    /// Seconds of this piece's sound kept so far (queued to play, playing or played).
    public private(set) var kept: Double = 0
    /// Seconds of the current request's sound still to skip.
    public private(set) var skipping: Double = 0

    public init() {}

    /// The piece's stream broke: the next request's first `kept` seconds are the sound already here.
    public mutating func requestAgain() { skipping = kept }

    public enum Decision: Equatable, Sendable {
        /// The chunk lies inside the sound already kept.
        case drop
        /// The chunk plays, its first `trimming` seconds cut (0: whole).
        case keep(trimming: Double)
    }

    /// A chunk of `seconds` from the current request.
    public mutating func admit(seconds: Double) -> Decision {
        let seconds = max(0, seconds)
        if skipping <= Self.tolerance { skipping = 0; kept += seconds; return .keep(trimming: 0) }
        if seconds <= skipping + Self.tolerance { skipping = max(0, skipping - seconds); return .drop }
        let trim = skipping
        skipping = 0; kept += seconds - trim
        return .keep(trimming: trim)
    }

    /// A streamed WAV chunk from the current request: nil when it is dropped, else the chunk to play
    /// (trimmed at the boundary). Throws for a chunk that is not a PCM WAV (it cannot be measured, so
    /// it cannot be placed: the reading says the speech could not be played).
    public mutating func admit(wav: Data) throws -> Data? {
        guard let seconds = SpeechWAV.duration(of: wav) else { throw SpeechWAV.Unreadable() }
        switch admit(seconds: seconds) {
        case .drop: return nil
        case .keep(let trim): return trim > 0 ? try SpeechWAV.dropping(seconds: trim, from: wav) : wav
        }
    }

    /// Under a tenth of a millisecond (one sample at 16 kHz is 62 µs): rounding, not sound.
    static let tolerance = 0.0001
}

/// The measure and the cut of a RIFF/WAVE chunk (PCM or float, any rate and channel count), on its
/// bytes: the speech stream's chunks are WAVs.
public enum SpeechWAV {
    public struct Unreadable: Error, LocalizedError {
        public var errorDescription: String? { "This speech could not be played." }
    }

    private struct Layout { let rate: Int; let blockAlign: Int; let dataSizeOffset: Int; let dataStart: Int; let dataEnd: Int }

    /// The chunk's sound in seconds; nil when it is not a readable WAV.
    public static func duration(of wav: Data) -> Double? {
        guard let l = layout(wav) else { return nil }
        return Double((l.dataEnd - l.dataStart) / l.blockAlign) / Double(l.rate)
    }

    /// The chunk without its first `seconds` (rounded to a whole frame; at most all of it), its
    /// RIFF and data sizes rewritten.
    public static func dropping(seconds: Double, from wav: Data) throws -> Data {
        guard let l = layout(wav) else { throw Unreadable() }
        let total = (l.dataEnd - l.dataStart) / l.blockAlign
        let frames = min(total, max(0, Int((seconds * Double(l.rate)).rounded())))
        guard frames > 0 else { return wav }
        let bytes = [UInt8](wav)
        var out = Array(bytes[0..<l.dataStart])
        out += bytes[(l.dataStart + frames * l.blockAlign)...]
        func put(_ value: Int, at i: Int) {
            let v = UInt32(clamping: value)
            for k in 0..<4 { out[i + k] = UInt8((v >> (8 * UInt32(k))) & 0xFF) }
        }
        put(l.dataEnd - l.dataStart - frames * l.blockAlign, at: l.dataSizeOffset)
        put(out.count - 8, at: 4)
        return Data(out)
    }

    /// The `fmt ` and `data` chunks' places. A data size past the end (a streamed WAV written before
    /// its length was known) reads as "to the end".
    private static func layout(_ wav: Data) -> Layout? {
        let b = [UInt8](wav)
        guard b.count >= 12, b[0..<4] == [0x52, 0x49, 0x46, 0x46], b[8..<12] == [0x57, 0x41, 0x56, 0x45] else { return nil }
        func u16(_ i: Int) -> Int { Int(b[i]) | Int(b[i + 1]) << 8 }
        func u32(_ i: Int) -> Int { u16(i) | u16(i + 2) << 16 }
        var i = 12, rate = 0, blockAlign = 0
        while i + 8 <= b.count {
            let id = b[i..<i + 4], length = u32(i + 4)
            if id.elementsEqual("fmt ".utf8), i + 24 <= b.count {
                rate = u32(i + 12); blockAlign = u16(i + 20)
            } else if id.elementsEqual("data".utf8) {
                guard rate > 0, blockAlign > 0 else { return nil }
                let start = i + 8
                return Layout(rate: rate, blockAlign: blockAlign, dataSizeOffset: i + 4, dataStart: start,
                              dataEnd: start + min(length, b.count - start))
            }
            i += 8 + length + (length & 1)
        }
        return nil
    }
}
