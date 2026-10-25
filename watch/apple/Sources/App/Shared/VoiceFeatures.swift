import Accelerate
import Foundation

/// What the orb follows in a voice at one moment: how loud it is within its own recent range, and
/// the shape of its spectrum (where its harmonics and formants are).
struct VoiceFeatures: Equatable {
    static let bandCount = 8
    /// 0…1: a syllable reaches 1, a pause falls to 0 (scaled to the voice's last seconds, so a
    /// quiet and a loud speaker both use the whole range).
    var level: Double
    /// 0…1 per band, 100 Hz to 6 kHz on a log scale: each band's energy against the strongest one
    /// now, times `level` (silence draws nothing; a vowel lifts its formant bands).
    var bands: [Double]

    static let silent = VoiceFeatures(level: 0, bands: Array(repeating: 0, count: bandCount))
    /// A loudness alone (previews): the same value in every band.
    static func flat(_ level: Double) -> VoiceFeatures { VoiceFeatures(level: level, bands: Array(repeating: level, count: bandCount)) }

    /// The band value at a position 0…1 across the bands, interpolated.
    func band(at x: Double) -> Double {
        let f = max(0, min(1, x)) * Double(bands.count - 1)
        let i = Int(f), frac = f - Double(i)
        return i + 1 < bands.count ? bands[i] + (bands[i + 1] - bands[i]) * frac : bands[i]
    }
}

/// One analysed frame: loudness and the energy of each band, in dB.
struct VoiceFrame: Sendable {
    var db: Float
    var bandsDB: [Float]
    static let silent = VoiceFrame(db: -100, bandsDB: Array(repeating: -100, count: VoiceFeatures.bandCount))
}

/// FFT analysis of mono samples (Accelerate): loudness and 8 log-spaced band energies per frame.
final class VoiceAnalyzer: @unchecked Sendable {
    let sampleRate: Double
    let size: Int
    private let log2n: vDSP_Length
    private let setup: FFTSetup
    private let window: [Float]
    /// The FFT bins of each band.
    private let bandBins: [Range<Int>]

    init(sampleRate: Double) {
        self.sampleRate = sampleRate
        let n = sampleRate > 24_000 ? 1024 : 512                 // ~23-32 ms either way
        size = n
        log2n = vDSP_Length(log2(Double(n)))
        setup = vDSP_create_fftsetup(vDSP_Length(log2(Double(n))), FFTRadix(kFFTRadix2))!
        window = vDSP.window(ofType: Float.self, usingSequence: .hanningDenormalized, count: n, isHalfWindow: false)
        let edges = (0...VoiceFeatures.bandCount).map { 100 * pow(60.0, Double($0) / Double(VoiceFeatures.bandCount)) }   // 100 Hz … 6 kHz
        let hz = sampleRate / Double(n)
        bandBins = (0..<VoiceFeatures.bandCount).map { b in
            let lo = max(1, Int(edges[b] / hz)), hi = max(lo + 1, min(n / 2, Int(edges[b + 1] / hz)))
            return lo..<hi
        }
    }

    deinit { vDSP_destroy_fftsetup(setup) }

    /// One frame from `size` samples (fewer are zero-padded).
    func analyze(_ samples: ArraySlice<Float>) -> VoiceFrame {
        var x = [Float](repeating: 0, count: size)
        for (i, v) in samples.prefix(size).enumerated() { x[i] = v }
        let rms = vDSP.rootMeanSquare(x)
        x = vDSP.multiply(x, window)
        var re = [Float](repeating: 0, count: size / 2), im = [Float](repeating: 0, count: size / 2)
        var mags = [Float](repeating: 0, count: size / 2)
        re.withUnsafeMutableBufferPointer { rp in
            im.withUnsafeMutableBufferPointer { ip in
                var split = DSPSplitComplex(realp: rp.baseAddress!, imagp: ip.baseAddress!)
                x.withUnsafeBytes { raw in
                    vDSP_ctoz(raw.bindMemory(to: DSPComplex.self).baseAddress!, 2, &split, 1, vDSP_Length(size / 2))
                }
                vDSP_fft_zrip(setup, &split, 1, log2n, FFTDirection(FFT_FORWARD))
                vDSP_zvmags(&split, 1, &mags, 1, vDSP_Length(size / 2))
            }
        }
        let bands = bandBins.map { r -> Float in
            let e = mags[r].reduce(0, +) / Float(r.count)
            return 10 * log10(max(e, 1e-12))
        }
        return VoiceFrame(db: 20 * log10(max(rms, 1e-6)), bandsDB: bands)
    }

    /// A whole WAV (16-bit or 32-bit float PCM, any channel count; the first channel is analysed),
    /// one frame every 1/`fps` s. Empty when the data is not a PCM WAV.
    static func frames(ofWAV data: Data, fps: Double = 60) -> [VoiceFrame] {
        guard let pcm = WAVSamples(data) else { return [] }
        let analyzer = VoiceAnalyzer(sampleRate: pcm.sampleRate)
        let hop = max(1, Int(pcm.sampleRate / fps))
        var out: [VoiceFrame] = []
        out.reserveCapacity(pcm.samples.count / hop + 1)
        var start = 0
        while start < pcm.samples.count {
            guard !Task.isCancelled else { return [] }
            let lo = max(0, start + hop / 2 - analyzer.size / 2)           // centred on the frame's time
            out.append(analyzer.analyze(pcm.samples[lo..<min(pcm.samples.count, lo + analyzer.size)]))
            start += hop
        }
        return out
    }
}

/// The samples of a PCM WAV (first channel, as Float −1…1).
struct WAVSamples {
    let sampleRate: Double
    let samples: [Float]

    init?(_ data: Data) {
        let bytes = [UInt8](data)
        guard bytes.count > 44, bytes[0..<4] == [0x52, 0x49, 0x46, 0x46], bytes[8..<12] == [0x57, 0x41, 0x56, 0x45] else { return nil }
        func u16(_ i: Int) -> Int { Int(bytes[i]) | Int(bytes[i + 1]) << 8 }
        func u32(_ i: Int) -> Int { u16(i) | u16(i + 2) << 16 }
        var i = 12, format = 0, channels = 1, rate = 0, bits = 16
        while i + 8 <= bytes.count {
            let id = String(decoding: bytes[i..<i + 4], as: UTF8.self), len = u32(i + 4)
            if id == "fmt " {
                format = u16(i + 8); channels = max(1, u16(i + 10)); rate = u32(i + 12); bits = u16(i + 22)
            } else if id == "data" {
                let start = i + 8, end = min(bytes.count, start + len)
                guard rate > 0 else { return nil }
                let step = channels * bits / 8
                var out: [Float] = []
                out.reserveCapacity((end - start) / max(1, step))
                var j = start
                if format == 1 && bits == 16 {
                    while j + 2 <= end { out.append(Float(Int16(bitPattern: UInt16(u16(j)))) / 32768); j += step }
                } else if format == 3 && bits == 32 {
                    while j + 4 <= end { out.append(Float(bitPattern: UInt32(u32(j)))); j += step }
                } else { return nil }
                sampleRate = Double(rate); samples = out
                return
            }
            i += 8 + len + (len & 1)
        }
        return nil
    }
}

/// Raw frames → features scaled to the voice's own recent range: the loudness range follows the
/// peaks (up at once, down over ~2 s) and the floor (slowly), so syllables and pauses use 0…1
/// whatever the volume; bands are each band against the strongest one now.
final class VoiceNormalizer {
    private var peak: Float = -30
    private var floor: Float = -60
    private var lastT: Double = 0

    func push(_ f: VoiceFrame, at t: Double) -> VoiceFeatures {
        let dt = lastT == 0 ? 1.0 / 30 : min(0.2, max(0, t - lastT))
        lastT = t
        if f.db > peak { peak = f.db } else { peak += (f.db - peak) * Float(1 - exp(-dt / 2.0)) }
        if f.db < floor { floor += (f.db - floor) * 0.5 } else { floor += (f.db - floor) * Float(1 - exp(-dt / 6.0)) }
        floor = max(floor, peak - 40)                                 // silence never stretches the range
        let span = max(18, peak - floor)                              // never amplify the room's hiss
        let level = Double(max(0, min(1, (f.db - (peak - span)) / span)))
        // Speech loses ~6 dB per octave toward the highs; each band is ~0.74 octave: lift each by
        // 4.5 dB so the upper bands (consonants, brightness) move the shape too.
        let tilted = f.bandsDB.enumerated().map { $0.element + 4.5 * Float($0.offset) }
        let top = tilted.max() ?? -100
        // A band 30 dB under the strongest draws nothing.
        let bands = tilted.map { level * Double(max(0, min(1, 1 + ($0 - top) / 30))) }
        return VoiceFeatures(level: level, bands: bands)
    }
}
