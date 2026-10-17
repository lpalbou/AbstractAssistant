import SwiftUI

/// The assistant's presence: a mass of pixel-size points that swirls continuously, in every
/// state and at every size (after Apple's particle pictures: the Watch pairing cloud, the dotted
/// heart). About 2,400 points on the Ask orb, each with its own place in a sphere (dense near the
/// surface, sparse inside, a few strays outside), so the shape is defined by its density and
/// undefined at its edge. The points turn around a slowly tilting axis at speeds that vary with
/// latitude (the mass shears into a swirl) and drift in a gentle flow; positions are a function of
/// time, so the motion is perfectly continuous.
/// - idle: a slow drift;
/// - listening: a faster swirl; the voice the microphone hears roughens and swells the mass, in
///   rings that travel outward; once you stop, the outer edge dims around the circle as the
///   countdown to sending;
/// - thinking: the mass contracts into a faster, flatter vortex;
/// - speaking: it pulses with the loudness of the voice it plays.
/// No measured sound means no reaction: a missing level is silence, never a fake one.
struct Orb: View {
    enum Mode: Hashable { case idle, listening, thinking, speaking }

    var mode: Mode
    var size: CGFloat = 84
    /// Frames per second while something moves; idle runs slower.
    var fps: Double = 30
    /// Listening and speaking: the loudness now, 0…1 (heard by the microphone, or played).
    var level: (@MainActor () -> Double)? = nil
    /// Listening: 0…1 progress of the silence that sends.
    var countdown: (@MainActor () -> Double)? = nil
    /// When the current mode started (the mass gathers in over 0.4 s).
    var since: Date? = nil

    @State private var history = LoudnessHistory()

    var body: some View {
        let rate = mode == .idle ? max(10, fps * 0.6) : fps
        TimelineView(.animation(minimumInterval: 1 / rate)) { ctx in
            let t = ctx.date.timeIntervalSinceReferenceDate
            let now: Double = (mode == .listening || mode == .speaking) ? (level?() ?? 0) : 0
            let progress: Double = countdown?() ?? 0
            let _ = history.push(now, at: t)
            Canvas { gc, box in draw(in: &gc, box: box, t: t, countdownProgress: progress) }
                .frame(width: size, height: size)
                .drawingGroup()
        }
        .accessibilityLabel(label)
    }

    private var label: String {
        switch mode {
        case .idle: "Assistant ready"
        case .listening: "Listening"
        case .thinking: "Thinking"
        case .speaking: "Speaking"
        }
    }

    private func draw(in gc: inout GraphicsContext, box: CGSize, t: Double, countdownProgress: Double) {
        gc.blendMode = .plusLighter
        let half: Double = Double(min(box.width, box.height)) / 2
        let cx: Double = Double(box.width) / 2, cy: Double = Double(box.height) / 2
        let R: Double = half * 0.86                          // the mass's radius; strays reach the edge
        let gather: Double = since.map { min(1, max(0, (t - $0.timeIntervalSinceReferenceDate) / 0.4)) } ?? 1
        let ease: Double = 1 - pow(1 - gather, 3)
        let voiceNow: Double = history.value(secondsAgo: 0, now: t)

        // Per-mode motion.
        let speed: Double, contract: Double, flatten: Double, turbulence: Double
        switch mode {
        case .idle: speed = 0.14; contract = 1; flatten = 0.8; turbulence = 0.035
        case .listening: speed = 0.24; contract = 1; flatten = 0.8; turbulence = 0.045
        case .thinking: speed = 0.6; contract = 0.8; flatten = 0.45; turbulence = 0.03
        case .speaking: speed = 0.2; contract = 1; flatten = 0.8; turbulence = 0.04
        }
        // The axis leans toward the viewer: the mass turns around the middle of the screen.
        let tilt: Double = 1.18 + 0.1 * sin(t * 0.13)
        let precess: Double = t * 0.05
        let ct = cos(tilt), st = sin(tilt), cp = cos(precess), sp = sin(precess)
        let px: Double = max(0.55, half / 60)              // a pixel-size point (≈ 1 pt on the Ask orb)
        let ringSpeed: Double = 0.9                          // radius units per second

        var buckets = [Path](repeating: Path(), count: 5)
        for p in Self.particles(count: Self.count(forHalf: half)) {
            // Swirl: angular speed varies with latitude (shear) and per particle.
            let lat: Double = p.phi + 0.1 * sin(t * 0.45 + p.phase)
            // A vortex: the inside turns faster than the outside, so trails bend into spiral arms.
            let shear: Double = 1.2 / (0.35 + p.r)
            // A strand: its points trail behind its head along the same path (streams, not noise).
            let a: Double = p.theta + t * speed * shear * p.spin - p.trail * 0.042
            var r: Double = p.r * contract * (1 + 0.05 * sin(t * 0.9 + p.phase * 2))
            if mode == .listening || mode == .speaking {
                // Rings: the loudness from r / speed seconds ago reaches this radius now.
                let loud: Double = history.value(secondsAgo: p.r / ringSpeed, now: t)
                r *= 1 + 0.16 * loud + 0.07 * voiceNow * sin(p.phase * 9 + t * 11)
            }
            r *= 0.2 + 0.8 * ease
            var x: Double = r * sin(lat) * cos(a)
            var y: Double = r * cos(lat) * flatten
            var z: Double = r * sin(lat) * sin(a)
            // A gentle flow field: streamlines through the mass.
            let turb: Double = turbulence * (1 + 3 * voiceNow)
            x += turb * sin(3.1 * y + t * 0.9 + p.phase)
            y += turb * sin(2.7 * z + t * 0.8)
            z += turb * sin(2.9 * x + t * 0.7)
            // Tilt (around x) and a slow precession (around y).
            let y1: Double = y * ct - z * st, z1: Double = y * st + z * ct
            let x2: Double = x * cp + z1 * sp, z2: Double = -x * sp + z1 * cp
            let persp: Double = 1 / (1.9 - 0.35 * z2)       // a little perspective: near is larger
            let sx: Double = cx + x2 * R * persp * 1.9 / 1.9 * 1.0
            let sy: Double = cy + y1 * R * persp * 1.9 / 1.9 * 1.0
            let depth: Double = max(0, min(1, (z2 + 1.1) / 2.2))
            var bright: Double = (0.25 + 0.85 * depth) * p.lum * (half < 45 ? 1.25 : 1) * (mode == .idle ? 0.82 + 0.18 * sin(t * 1.25 + p.phase) : 1)
            if mode == .listening || mode == .speaking { bright = min(1, bright * (0.85 + 0.35 * voiceNow)) }
            // The countdown: the outer edge dims clockwise from the top.
            if countdownProgress > 0 {
                let dx = sx - cx, dy = sy - cy
                if (dx * dx + dy * dy).squareRoot() > R * 0.72 {
                    let angle: Double = (atan2(dx, -dy) + .pi) / (2 * .pi)
                    if angle < countdownProgress { bright *= 0.15 }
                }
            }
            let b: Int = min(4, Int(bright * 5))
            guard b > 0 || bright > 0.08 else { continue }
            let s: Double = px * (b >= 4 ? 1.35 : 1)
            buckets[b].addRect(CGRect(x: sx - s / 2, y: sy - s / 2, width: s, height: s))
        }
        for b in 0..<5 { gc.fill(buckets[b], with: .color(Self.palette[b])) }
    }

    private static let palette: [Color] = [
        Color(hex: 0x4f46e5).opacity(0.35), Color(hex: 0x6366f1).opacity(0.55), Color(hex: 0x38bdf8).opacity(0.7),
        Color(hex: 0x22d3ee).opacity(0.85), Color(hex: 0xc9f6ff).opacity(0.95),
    ]

    /// About one point per 4.5 pt² of the orb's disc: ≈ 2,400 at 104 pt, ≈ 280 at 40 pt.
    private static func count(forHalf h: Double) -> Int { max(160, min(2600, Int(Double.pi * h * h / 3.6))) }

    struct Particle { let theta: Double; let phi: Double; let r: Double; let spin: Double; let phase: Double; let lum: Double; let trail: Double }

    /// Each point's fixed place: uniform directions; radius dense near the surface, thinner
    /// inside, 6% strays beyond it (the soft edge). Seeded, so the mass is the same every launch.
    @MainActor private static var cache: [Int: [Particle]] = [:]
    @MainActor private static func particles(count n: Int) -> [Particle] {
        if let c = cache[n] { return c }
        func hash(_ k: Int, _ salt: Double) -> Double {
            let v = sin(Double(k) * 12.9898 + salt * 78.233) * 43758.5453
            return v - v.rounded(.down)
        }
        // Strands of 16 points: every point of a strand shares its path (direction, radius, speed,
        // phase) and sits a little further behind the head; brightness fades along the trail.
        let length = 24
        let ps = (0..<n).map { k -> Particle in
            let s = k / length, j = k % length
            let u = hash(s, 1), v = hash(s, 2), w = hash(s, 3)
            let phi = acos(1 - 2 * u)
            let r: Double = hash(s, 4) < 0.06 ? 1 + 0.3 * w : pow(w, 0.22)
            let jitter = 0.012 * (hash(k, 8) - 0.5)
            return Particle(theta: 2 * .pi * v, phi: phi + jitter, r: r * (1 + jitter), spin: 0.75 + 0.5 * hash(s, 5),
                            phase: 2 * .pi * hash(s, 6), lum: (0.75 + 0.35 * hash(s, 7)) * pow(1 - Double(j) / Double(length), 1.6),
                            trail: Double(j))
        }
        cache[n] = ps
        return ps
    }
}

/// The last 1.2 s of loudness, 30 samples a second: rises within a frame, falls over ~250 ms.
final class LoudnessHistory {
    private var samples = [Double](repeating: 0, count: 36)
    private var head = 0
    private var lastT: Double = 0
    private var smooth: Double = 0

    @discardableResult
    func push(_ v: Double, at t: Double) -> Bool {
        smooth = v > smooth ? v : smooth * 0.82 + v * 0.18
        let steps = lastT == 0 ? 1 : min(36, max(0, Int((t - lastT) * 30)))
        guard steps > 0 else { samples[head] = smooth; return false }
        for _ in 0..<steps { head = (head + 1) % samples.count; samples[head] = smooth }
        lastT = t
        return true
    }

    func value(secondsAgo s: Double, now t: Double) -> Double {
        let back = min(samples.count - 1, max(0, Int(s * 30)))
        return samples[(head - back + samples.count) % samples.count]
    }
}
