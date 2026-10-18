import SwiftUI

/// The orb's style: how its points answer a voice (Settings → Orb style, and asked once at first
/// launch). Stored by letter so a choice survives renames.
enum OrbDesign: String, CaseIterable, Identifiable {
    case a = "A", b = "B", c = "C", d = "D", e = "E", f = "F"
    var id: String { rawValue }
    var name: String {
        switch self {
        case .a: "Halo"
        case .b: "Vortex"
        case .c: "Nebula"
        case .d: "Rings"
        case .e: "Liquid"
        case .f: "Galaxy"
        }
    }
    var summary: String {
        switch self {
        case .a: "rays of light around it, as long as your voice is loud"
        case .b: "the points swirl out into arms that reach with the voice"
        case .c: "a cloud that breathes outward with the voice"
        case .d: "the points gather on three orbits that pulse with the voice"
        case .e: "its surface ripples in waves with the voice"
        case .f: "a spiral galaxy that turns and spreads its arms with the voice"
        }
    }
    static let storageKey = "orb.design"
    /// Set once the person has chosen (the first-launch question is asked only once).
    static let chosenKey = "orb.chosen"
    static var current: OrbDesign { OrbDesign(rawValue: UserDefaults.standard.string(forKey: storageKey) ?? "") ?? .a }
}

/// The silhouette the points draw (an entity's choice, `appearance.shape` on the gateway).
enum OrbShape: String, CaseIterable, Identifiable {
    case planet, kitty, face, wave
    var id: String { rawValue }
}

/// An orb's look: its colour (nil = the app's cyan and indigo) and shape.
struct OrbLook: Equatable {
    var color: Color? = nil
    var shape: OrbShape = .planet
    static let assistant = OrbLook()
}

/// The assistant's presence: a planet of pixel-size points turning slowly, like the Earth seen from
/// space (a tilted axis, about one turn every fifty seconds, a lit side and a night side, uneven
/// "continents" so the turn reads). When it hears you or speaks, about 85% of the points leave the
/// planet and answer the voice in real time (the design decides how); the other 15% keep turning in
/// place, so it stays the same orb. Thinking turns it faster and draws it in. Positions are functions
/// of time, so every motion is continuous; a missing loudness is silence, never a fake one.
struct Orb: View {
    enum Mode: Hashable { case idle, listening, thinking, speaking }

    var mode: Mode
    var size: CGFloat = 84
    var fps: Double = 30
    /// Listening and speaking: the voice now (loudness in its own range, and its spectrum), at time t.
    var voice: (@MainActor (Double) -> VoiceFeatures)? = nil
    /// Listening: 0…1 progress of the silence that sends.
    var countdown: (@MainActor () -> Double)? = nil
    var since: Date? = nil
    var look: OrbLook = .assistant
    /// nil = the chosen design (Settings → Orb design).
    var design: OrbDesign? = nil
    /// While it works: the pulses of its steps and the tools running now, at time t.
    var work: (@MainActor (Double) -> OrbWork)? = nil

    @State private var engine = OrbEngine()
    @AppStorage(OrbDesign.storageKey) private var storedDesign = OrbDesign.a.rawValue

    var body: some View {
        let rate = mode == .idle ? max(12, fps * 0.6) : fps
        let chosen = design ?? OrbDesign(rawValue: storedDesign) ?? .a
        TimelineView(.animation(minimumInterval: 1 / rate)) { ctx in
            let t = ctx.date.timeIntervalSinceReferenceDate
            let voiced = mode == .listening || mode == .speaking
            let _ = engine.step(t: t, voice: voiced ? (voice?(t) ?? .silent) : .silent, engaged: voiced, thinking: mode == .thinking)
            OrbCanvas(t: t, engine: engine, design: chosen, look: look, countdown: countdown?() ?? 0, work: work?(t) ?? .none)
                .frame(width: size, height: size)
        }
        .accessibilityLabel(label)
    }

    private var label: String {
        switch mode {
        case .idle: "Ready"
        case .listening: "Listening"
        case .thinking: "Thinking"
        case .speaking: "Speaking"
        }
    }
}

/// Frame-to-frame state, all frame-rate independent: a smoothed loudness (rises in ~45 ms, falls
/// in ~200 ms) and its 1.2 s history, how engaged the cloud is (a smoothstep over 0.6 s in, 1 s
/// out), how much it is thinking, and an accumulated swirl phase (never `engagement × time`).
final class OrbEngine {
    let history = LoudnessHistory()
    private(set) var engagement: Double = 0
    private(set) var thinking: Double = 0
    private(set) var swirl: Double = 0
    private(set) var loud: Double = 0
    /// How strongly the voice pulls the cloud, 0…1: the engagement times a loudness that rises in
    /// ~60 ms and falls over ~250 ms (it follows syllables without flickering within one).
    private(set) var signal: Double = 0
    /// The voice's spectrum now (8 bands, 100 Hz–6 kHz), each smoothed over a syllable's attack.
    private(set) var bands = [Double](repeating: 0, count: VoiceFeatures.bandCount)
    private var slow: Double = 0
    private var eLin: Double = 0
    private var tLin: Double = 0
    private var lastT: Double = 0

    @discardableResult
    func step(t: Double, voice: VoiceFeatures, engaged: Bool, thinking isThinking: Bool) -> Bool {
        let dt = lastT == 0 ? 0 : min(0.2, max(0, t - lastT))
        lastT = t
        let level = voice.level
        let tau = level > loud ? 0.025 : 0.09
        if dt > 0 { loud += (level - loud) * (1 - exp(-dt / tau)) } else { loud = level }
        for i in bands.indices {
            let v = i < voice.bands.count ? voice.bands[i] : 0
            bands[i] += (v - bands[i]) * (dt > 0 ? 1 - exp(-dt / (v > bands[i] ? 0.03 : 0.12)) : 1)
        }
        history.push(loud, at: t)
        eLin = min(1, max(0, eLin + (engaged ? dt / 0.6 : -dt / 1.0)))
        engagement = eLin * eLin * (3 - 2 * eLin)
        tLin = min(1, max(0, tLin + (isThinking ? dt / 0.5 : -dt / 0.8)))
        thinking = tLin * tLin * (3 - 2 * tLin)
        if dt > 0 { slow += (loud - slow) * (1 - exp(-dt / (loud > slow ? 0.06 : 0.25))) } else { slow = loud }
        signal = engagement * (0.12 + 0.88 * min(1, slow))
        swirl += dt * engagement * (0.2 + 1.4 * loud)
        return true
    }
}

@inline(__always) private func smoothstep(_ a: Double, _ b: Double, _ x: Double) -> Double {
    let u = min(1, max(0, (x - a) / (b - a)))
    return u * u * (3 - 2 * u)
}

/// One frame of the orb (also used to render the app icon).
struct OrbCanvas: View {
    let t: Double
    let engine: OrbEngine
    let design: OrbDesign
    let look: OrbLook
    var countdown: Double = 0
    /// Its work: each step sends a wave of light across it; each running tool circles it.
    var work: OrbWork = .none
    /// More points than the screen needs (the 1024 px icon).
    var pointScale: Double = 1

    private static let ringTilt: [Double] = [0.35, -0.55, 1.15]

    var body: some View {
        Canvas { gc, box in draw(&gc, box) }
            .drawingGroup()
    }

    private func draw(_ gc: inout GraphicsContext, _ box: CGSize) {
        gc.blendMode = .plusLighter
        let half = Double(min(box.width, box.height)) / 2
        let cx = Double(box.width) / 2, cy = Double(box.height) / 2
        let R = half * 0.46                    // the planet; at full voice the outer points reach the frame
        let e = engine.engagement, th = engine.thinking, hist = engine.history, now = engine.loud
        let spectrum = VoiceFeatures(level: now, bands: engine.bands)
        /// The voice's spectrum at 0…1 across its bands (low → high pitch).
        func band(_ x: Double) -> Double { spectrum.band(at: x) }
        // The turn: the planet spins on a 23° tilted axis (one turn ≈ 50 s, 4× while thinking);
        // a kitty or a face turns its head gently instead; the wave is seen from a fixed pitch.
        let spinning = look.shape == .planet
        let yaw: Double = spinning ? t * (0.125 + 0.4 * th) : (look.shape == .wave ? 0.2 * sin(t * 0.08) : 0.45 * sin(t * 0.25))
        let tilt: Double = look.shape == .planet ? 0.41 : (look.shape == .wave ? 0.6 : 0.12)
        let cY = cos(yaw), sY = sin(yaw), cT = cos(tilt), sT = sin(tilt)
        let sun = (x: -0.55, y: -0.35, z: 0.76)
        let px = max(0.55, half / 95)
        let contract = 1 - 0.08 * th
        let swirlBase = engine.swirl
        var moving = [Path](repeating: Path(), count: 5)

        for p in OrbPoints.points(for: look.shape, count: Int(Double(OrbPoints.count(half: half)) * pointScale)) {
            var px0 = p.x, py0 = p.y, pz0 = p.z
            if look.shape == .wave && !p.feature {
                // Rolling ocean: the surface height is computed now, so the waves travel.
                py0 = 0.18 * sin(4 * p.rad + 2 * p.ang - 1.3 * t) + 0.04 * sin(9 * p.rad - 2.1 * t + p.phase)
            }
            // 1. Turn (y axis), then tilt (x axis); y points down on screen.
            let bx = px0 * cY + pz0 * sY, bz = -px0 * sY + pz0 * cY
            px0 = bx; let y1 = py0 * cT - bz * sT; pz0 = py0 * sT + bz * cT; py0 = y1
            var x = px0 * contract, y = py0 * contract
            let z = pz0
            // 2b. Work: each step sends a ring of light out from the centre (a tool call a quick
            //     bright one, thinking a soft one, media a slow wide wave); a failed tool shivers.
            var workLight = 0.0
            if !work.pulses.isEmpty {
                let r0 = (x * x + y * y).squareRoot()
                var push = 0.0
                for pulse in work.pulses {
                    let fade = max(0, 1 - pulse.age / 1.6)
                    switch pulse.tone {
                    case .failure:
                        let k = pulse.strength * fade * fade
                        x += 0.035 * k * sin(t * 55 + p.phase); y += 0.035 * k * cos(t * 47 + p.phase * 1.3)
                        workLight += 0.3 * k
                    default:
                        let speed = pulse.tone == .media ? 0.85 : (pulse.tone == .thinking ? 1.0 : 1.5)
                        let width = pulse.tone == .media ? 0.24 : (pulse.tone == .thinking ? 0.2 : 0.13)
                        let ring = (r0 - pulse.age * speed) / width
                        let k = exp(-ring * ring) * pulse.strength * fade
                        push += k; workLight += k
                    }
                }
                if r0 > 1e-3 { x += x / r0 * 0.12 * push; y += y / r0 * 0.12 * push }
            }
            // 2. Light: the sun, the night side, depth (the far side fades), a rim.
            let lit = max(0.0, x * sun.x + y * sun.y + z * sun.z)
            var bright = (0.18 + 0.82 * lit) * p.lum
            bright *= 0.2 + 0.8 * smoothstep(-0.25, 0.15, z)
            if p.surface { bright += 0.35 * pow(1 - min(1, abs(z)), 3) * p.lum }
            bright += 1.6 * workLight * (0.45 + 0.55 * p.lum) * smoothstep(-0.4, 0.2, z)
            // 3. The voice. Each style defines where a point goes at full strength (its displacement
            //    D); how far it goes is its participation w, a smoothstep of its mobility m (its
            //    distance from the centre on screen, plus a little chance) against a threshold that
            //    moves inward as the signal s grows: a weak voice moves only the outer band (the
            //    buffer zone), a stronger one draws in more and more points. The anchored sixth
            //    follows at most 15%, so the shape breathes with the voice yet stays.
            if e > 0.001 {
                let r0 = max(1e-3, (x * x + y * y).squareRoot())
                let m = min(1, 0.72 * r0 + 0.28 * p.dither)
                let theta = 1 - 1.05 * engine.signal
                var w = e * smoothstep(theta - 0.2, theta + 0.2, m)
                if p.anchored { w *= 0.15 }
                if w > 0.002 {
                    let sw = swirlBase * (0.15 + 0.35 * p.reach)
                    let cs = cos(sw), sn = sin(sw)
                    let sx = x * cs - y * sn, sy = x * sn + y * cs
                    let r = max(1e-3, (sx * sx + sy * sy).squareRoot())
                    var tx = sx, ty = sy, glow = 0.0
                    switch design {
                    case .a:   // Halo: the voice's spectrum around the circle (low pitches at the top),
                               // mirrored around the vertical (no seam), with its last second as a trail
                        let ang = abs(atan2(sx, -sy)) / .pi
                        let lh = hist.value(secondsAgo: ang * 1.0)
                        let v = min(1.2, 0.4 * lh + 0.8 * band(ang))
                        let d = 0.35 + 1.0 * v * (0.3 + 0.7 * p.reach)
                        tx += sx / r * d; ty += sy / r * d; glow = 0.8 * v
                    case .b:   // Vortex: arms leave the planet's edge; what reaches further trails further around
                        let lh = 0.5 * hist.value(secondsAgo: (1 - min(1, r)) * 0.6) + 0.6 * band(abs(atan2(sy, sx)) / .pi)
                        let ext = (0.25 + 0.9 * lh) * p.reach
                        let rr = 0.85 + 0.25 * r + ext
                        let na = atan2(sy, sx) + ext * 3.2 + swirlBase * 0.5 * p.reach
                        tx = cos(na) * rr; ty = sin(na) * rr; glow = 0.6 * lh
                    case .c:   // Nebula: breathes outward, turbulent with loudness
                        let lh = 0.5 * hist.value(secondsAgo: 0.15 + 0.25 * p.reach) + 0.6 * band(Double(p.band % 8) / 7)
                        let push = (0.35 + 0.9 * lh) * p.reach
                        let amp = 0.08 + 0.3 * now
                        tx += sx * push + amp * sin(p.x * 4.1 + t * 1.3 + p.phase)
                        ty += sy * push + amp * sin(p.y * 3.7 - t * 1.1 + p.phase * 1.7)
                        glow = 0.5 * lh
                    case .d:   // Rings: three tilted orbits that pulse
                        let ring = p.band % 3
                        let lh = 0.5 * hist.value(secondsAgo: Double(ring) * 0.3) + 0.6 * band(Double(ring) / 2)
                        let rr = 1.15 + 0.15 * Double(ring) + 0.4 * lh + 0.05 * (p.dither - 0.5)
                        let a = p.phase + swirlBase * (0.8 + 0.3 * Double(ring)) * (ring == 1 ? -1 : 1) + t * 0.15
                        tx = cos(a) * rr; ty = sin(a) * rr * cos(Self.ringTilt[ring]) * 0.35 + 0.02 * (p.reach - 0.5)
                        glow = 0.7 * lh
                    case .e:   // Liquid: standing waves on the surface, driven by the last second
                        let a = atan2(sy, sx)
                        var wv = 0.0
                        for k in 1...3 {
                            let amp = 0.4 * hist.value(secondsAgo: Double(k) * 0.15) + 0.8 * band(Double(k - 1) / 2)
                            wv += amp * sin(Double(k + 2) * a + Double(k) * t * 0.9) / Double(k)
                        }
                        let d = 0.3 + 1.0 * wv * p.reach + 0.4 * now
                        tx += sx * d; ty += sy * d; glow = 0.6 * now
                    case .f:   // Galaxy: a continuous disc of stars, densest at the core, crowded along two arms
                        let lh = 0.5 * hist.value(secondsAgo: 0.1 + 0.4 * p.reach) + 0.6 * band(0.15)
                        let v = (p.reach - 0.45) / 0.55                         // 0…1, the star's own chance
                        var gr: Double, ga: Double
                        if p.band == 0 {
                            // The bulge: a dense, bright, slightly round core.
                            gr = 0.3 * pow(p.dither, 0.6); ga = p.phase
                            glow = 0.9
                        } else {
                            // The disc: exponential density (scale 0.55), out to ~1.7.
                            gr = min(1.7, -0.55 * log(1 - 0.96 * p.dither)) + 0.08
                            if p.band <= 2 {
                                ga = p.phase                                     // between the arms
                                glow = 0.15
                            } else {
                                // Around one of two log-spiral arms: densest at the arm, thinning
                                // away from it (a soft, wide spread, not a line).
                                let off = (v - 0.5) * (0.35 + 4.4 * (v - 0.5) * (v - 0.5))
                                ga = Double(p.band % 2) * .pi + 2.3 * log(gr + 0.08) + off
                                glow = 0.35 + 0.45 * lh * (1 - abs(off))
                            }
                            gr *= 1 + 0.3 * lh                                    // the arms reach with the voice
                        }
                        // The centre turns faster than the edge.
                        ga -= swirlBase * (0.8 / (0.3 + gr)) + t * 0.04
                        tx = cos(ga) * gr
                        ty = sin(ga) * gr * 0.6 + 0.03 * (p.dither - 0.5)      // seen at a slant, a thin disc
                    }
                    x += (tx - x) * w; y += (ty - y) * w
                    // A moving point lights up as it travels (wherever it came from, even the night
                    // side), so the shape the voice draws is clearly lit.
                    let voiceLight = (0.55 + 0.45 * glow) * (0.75 + 0.25 * p.lum)
                    bright += (max(bright, voiceLight) - bright) * w
                }
            }
            // The countdown: the outer edge dims clockwise from the top, softly.
            if countdown > 0 {
                let r = (x * x + y * y).squareRoot()
                let a = (atan2(x, -y) + .pi) / (2 * .pi)
                bright *= 1 - 0.8 * (1 - smoothstep(countdown - 0.03, countdown + 0.03, a)) * smoothstep(0.8, 1.0, r)
            }
            // Never off screen: beyond 74% of the frame's half a point slows smoothly toward 89%
            // (the voice's reach, 8% under the frame's edge; the resting planet is unchanged).
            let lim = half * 0.97 * 0.92 / R, knee = half * 0.8 * 0.92 / R
            let rr = (x * x + y * y).squareRoot()
            if rr > knee {
                let soft = knee + (lim - knee) * (1 - exp(-(rr - knee) / (lim - knee)))
                x *= soft / rr; y *= soft / rr
            }
            guard bright > 0.03 * p.dither else { continue }
            let b = min(4, max(0, Int(bright * 5 + p.dither - 0.5)))
            moving[b].addRect(CGRect(x: cx + x * R - px / 2, y: cy + y * R - px / 2, width: px, height: px))
        }
        let pal = OrbPalette.colors(for: look.color)
        drawWaves(&gc, cx: cx, cy: cy, R: R, pal: pal)
        for b in 0..<5 { gc.fill(moving[b], with: .color(pal[b])) }
        drawSatellites(&gc, cx: cx, cy: cy, R: R, px: px, pal: pal)
    }

    /// Under the points: each wave's soft ring of light, travelling out with it and fading.
    private func drawWaves(_ gc: inout GraphicsContext, cx: Double, cy: Double, R: Double, pal: [Color]) {
        let waves = work.pulses.filter { $0.tone != .failure }
        guard !waves.isEmpty else { return }
        // A soft ring as a radial gradient (no blur pass: it is drawn every frame).
        let glow = OrbPalette.glow(pal)
        for w in waves {
            let speed = w.tone == .media ? 0.85 : (w.tone == .thinking ? 1.0 : 1.5)
            let r = w.age * speed * 0.92 * R
            guard r > 2 else { continue }
            let fade = max(0, 1 - w.age / 1.6)
            let width = (w.tone == .media ? 0.34 : 0.2) * R
            let alpha = min(0.55, 0.42 * w.strength * fade * (w.tone == .thinking ? 0.5 : 1))
            let outer = r + width
            let inner = max(0, r - width) / outer, mid = r / outer
            let g = Gradient(stops: [.init(color: .clear, location: 0), .init(color: .clear, location: inner),
                                     .init(color: glow.opacity(alpha), location: mid), .init(color: .clear, location: 1)])
            gc.fill(Path(ellipseIn: CGRect(x: cx - outer, y: cy - outer, width: 2 * outer, height: 2 * outer)),
                    with: .radialGradient(g, center: CGPoint(x: cx, y: cy), startRadius: 0, endRadius: outer))
        }
    }

    /// Each tool running now circles the planet on a tilted orbit, a bright point with a fading
    /// trail, dimmed while it passes behind.
    private func drawSatellites(_ gc: inout GraphicsContext, cx: Double, cy: Double, R: Double, px: Double, pal: [Color]) {
        let n = work.satellites
        guard n > 0 else { return }
        let tilt = -0.32, ca = cos(tilt), sa = sin(tilt)
        func spot(_ i: Int, _ k: Int) -> (x: Double, y: Double, behind: Bool) {
            let a = t * 1.7 + 2 * .pi * Double(i) / Double(n) - Double(k) * 0.06
            let ox = cos(a) * 1.3, oy = sin(a) * 1.3 * 0.34
            return (cx + (ox * ca - oy * sa) * R, cy + (ox * sa + oy * ca) * R, sin(a) < -0.15)
        }
        // A glow under each head (a radial gradient), then the trail and the head.
        let glow = OrbPalette.glow(pal)
        for i in 0..<n {
            let s = spot(i, 0), g = px * 6
            let fill = Gradient(colors: [glow.opacity(s.behind ? 0.25 : 0.75), .clear])
            gc.fill(Path(ellipseIn: CGRect(x: s.x - g, y: s.y - g, width: 2 * g, height: 2 * g)),
                    with: .radialGradient(fill, center: CGPoint(x: s.x, y: s.y), startRadius: 0, endRadius: g))
        }
        for i in 0..<n {
            for k in stride(from: 16, through: 0, by: -1) {
                let s = spot(i, k)
                let size = px * (k == 0 ? 4.2 : 2.4 - 0.1 * Double(k))
                let alpha = (k == 0 ? 1 : 0.7 * (1 - Double(k) / 17)) * (s.behind ? 0.3 : 1)
                gc.fill(Path(ellipseIn: CGRect(x: s.x - size / 2, y: s.y - size / 2, width: size, height: size)),
                        with: .color((k == 0 ? pal[4] : pal[3]).opacity(alpha)))
            }
        }
    }
}

enum OrbPalette {
    /// The light of its work: the palette's bright colour at full strength (a dark entity colour
    /// would make a faded one vanish on the ground).
    static func glow(_ pal: [Color]) -> Color { pal[3].opacity(1 / 0.85) }
    /// Five brightness levels: deep, mid, the colour, light, near-white (default: indigo → cyan).
    static func colors(for tint: Color?) -> [Color] {
        guard let tint else {
            return [Color(hex: 0x4338ca).opacity(0.4), Color(hex: 0x6366f1).opacity(0.55), Color(hex: 0x38bdf8).opacity(0.7),
                    Color(hex: 0x22d3ee).opacity(0.85), Color(hex: 0xcffafe).opacity(0.95)]
        }
        return [tint.opacity(0.28), tint.opacity(0.45), tint.opacity(0.65), tint.opacity(0.85), Color.white.opacity(0.85)]
    }
}

/// The fixed point sets, one per shape (seeded: the same orb every launch), in unit coordinates
/// (y down). Each point: position, brightness, whether it is part of the anchored 1/6 (or a feature
/// of the shape: ears, eyes, mouth, which are always anchored), and the per-point parameters.
enum OrbPoints {
    struct P {
        let x: Double; let y: Double; let z: Double; let lum: Double
        let anchored: Bool; let feature: Bool; let surface: Bool
        let reach: Double; let phase: Double; let band: Int; let dither: Double
        let rad: Double; let ang: Double
    }

    /// About one point per 5 pt² of the orb's square: ≈ 2,600 full screen, ≈ 300 on a 40 pt tile.
    /// 30% fewer than the first design (it lagged at times on a Series 11; older watches are slower).
    static func count(half: Double) -> Int { max(154, min(1820, Int(0.7 * 4 * half * half / 5))) }

    @MainActor private static var cache: [Int: [P]] = [:]

    @MainActor static func points(for shape: OrbShape, count n: Int) -> [P] {
        let key = (OrbShape.allCases.firstIndex(of: shape) ?? 0) * 1_000_000 + n
        if let c = cache[key] { return c }
        var out: [P] = []
        out.reserveCapacity(n)
        var k = 0
        while out.count < n && k < n * 4 {
            defer { k += 1 }
            let u = hash(k, 1), v = hash(k, 2), w = hash(k, 3)
            var (x, y, z) = spherePoint(u, v)
            var r = hash(k, 4) < 0.88 ? 1.0 : 0.55 + 0.4 * w        // mostly surface, some depth
            if hash(k, 5) < 0.04 { r = 1.05 + 0.1 * w }               // a thin atmosphere
            // Two or three continents: low-frequency land, thresholded, so the turn reads.
            let land = 0.5 + 0.5 * sin(1.9 * x + 1.0 * sin(1.4 * z)) * cos(1.6 * y + 0.8 * x)
            var lum = smoothstep(0.45, 0.6, land) * 0.75 + 0.25
            var feature = false
            var rad = 0.0, ang = 0.0
            switch shape {
            case .planet: break
            case .kitty:
                if hash(k, 6) < 0.16 {   // two ears above the head
                    let side: Double = hash(k, 7) < 0.5 ? -1 : 1
                    let h = hash(k, 8), spread = (hash(k, 9) - 0.5) * (1 - h)
                    x = side * (0.5 + 0.35 * spread + 0.08 * h); y = -0.78 - 0.55 * h; z = 0.1 * (hash(k, 10) - 0.5)
                    r = 1; lum = 0.95; feature = true
                }
            case .face:
                if z < -0.2 { continue }                                   // the face is its front
                lum = 0.45
                let ex = abs(x) - 0.36, ey = y + 0.22
                if z > 0.35 && ex * ex + ey * ey < 0.022 { continue }      // the eyes stay empty
                if z > 0.35 && abs(ex * ex + ey * ey - 0.03) < 0.012 { lum = 1; feature = true }
                if abs(y - (0.32 - 0.5 * x * x)) < 0.045 && abs(x) < 0.45 && z > 0.4 { lum = 1; feature = true }
            case .wave:
                ang = 2 * Double.pi * u; rad = 0.25 + 0.95 * v.squareRoot()
                x = cos(ang) * rad; z = sin(ang) * rad; y = 0
                r = 1; lum = 0.55 + 0.45 * w
            }
            x *= r; y *= r; z *= r
            out.append(P(x: x, y: y, z: z, lum: lum, anchored: k % 6 == 0, feature: feature,
                         surface: abs(r - 1) < 0.01 && shape != .wave,
                         reach: 0.45 + 0.55 * hash(k, 11), phase: 2 * .pi * hash(k, 12), band: Int(hash(k, 13) * 9),
                         dither: hash(k, 14), rad: rad, ang: ang))
        }
        cache[key] = out
        return out
    }

    private static func spherePoint(_ u: Double, _ v: Double) -> (Double, Double, Double) {
        let zz = 1 - 2 * u, rr = (max(0, 1 - zz * zz)).squareRoot(), a = 2 * Double.pi * v
        return (rr * cos(a), zz, rr * sin(a))
    }

    private static func hash(_ k: Int, _ salt: Double) -> Double {
        let v = sin(Double(k) * 12.9898 + salt * 78.233) * 43758.5453
        return v - v.rounded(.down)
    }
}

/// The last 1.2 s of the smoothed loudness at 30 samples a second, read with linear interpolation
/// (no steps), the newest sample being the current value.
final class LoudnessHistory {
    private var samples = [Double](repeating: 0, count: 40)
    private var head = 0
    private var lastT: Double = 0

    func push(_ v: Double, at t: Double) {
        if lastT == 0 { lastT = t }
        let steps = min(40, Int((t - lastT) * 30))
        if steps > 0 {
            for _ in 0..<steps { head = (head + 1) % samples.count; samples[head] = v }
            lastT += Double(steps) / 30
        } else {
            samples[head] = v
        }
    }

    func value(secondsAgo s: Double) -> Double {
        let f = max(0, min(Double(samples.count - 2), s * 30))
        let i = Int(f), frac = f - Double(i)
        let a = samples[(head - i + samples.count) % samples.count]
        let b = samples[(head - i - 1 + samples.count) % samples.count]
        return a + (b - a) * frac
    }
}

#if DEBUG
/// The app icon is the orb itself: `--render-icon` (simulator) renders the resting planet at
/// 1024 × 1024 on the app's ground into Documents/orb-icon.png.
enum OrbIcon {
    @MainActor static func render() {
        let engine = OrbEngine()
        let art = ZStack {
            Color(hex: 0x05060c)
            // Drawn larger than the icon so the planet fills ~3/4 of the watch's round mask.
            OrbCanvas(t: 812_345_678.0, engine: engine, design: .a, look: .assistant, pointScale: 3.2)
                .frame(width: 1400, height: 1400)
        }
        .frame(width: 1024, height: 1024)
        .clipped()
        let renderer = ImageRenderer(content: art)
        renderer.scale = 1
        guard let image = renderer.uiImage, let data = image.pngData(),
              let dir = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first else { return }
        try? data.write(to: dir.appending(path: "orb-icon.png"))
        print("icon rendered: \(dir.appending(path: "orb-icon.png").path)")
    }

    /// `--render-orb-work` (simulator): the orb at work, frame by frame, into Documents/orb-work-*.png:
    /// a tool pulse travelling out, a media wave, a failure, and three tools running (satellites).
    @MainActor static func renderWork() {
        guard let dir = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first else { return }
        let frames: [(String, OrbWork)] = [
            ("tool-0.15", OrbWork(pulses: [.init(age: 0.15, strength: 1, tone: .tool)], satellites: 1)),
            ("tool-0.45", OrbWork(pulses: [.init(age: 0.45, strength: 1, tone: .tool)], satellites: 1)),
            ("tool-0.8", OrbWork(pulses: [.init(age: 0.8, strength: 1, tone: .tool)], satellites: 1)),
            ("three", OrbWork(pulses: [.init(age: 0.55, strength: 1, tone: .tool), .init(age: 0.37, strength: 1, tone: .tool),
                                       .init(age: 0.19, strength: 1, tone: .tool)], satellites: 3)),
            ("media-0.7", OrbWork(pulses: [.init(age: 0.7, strength: 1.3, tone: .media)])),
            ("failure", OrbWork(pulses: [.init(age: 0.1, strength: 0.9, tone: .failure)])),
            ("rest", .none),
        ]
        for (name, work) in frames {
            let engine = OrbEngine()
            for k in 0..<30 { engine.step(t: 1000 + Double(k) / 30, voice: .silent, engaged: false, thinking: true) }
            let art = ZStack {
                Color(hex: 0x0a0a12)
                OrbCanvas(t: 1001, engine: engine, design: .a, look: .assistant, work: work).frame(width: 396, height: 396)
            }
            .frame(width: 396, height: 396)
            let renderer = ImageRenderer(content: art)
            renderer.scale = 2
            if let data = renderer.uiImage?.pngData() { try? data.write(to: dir.appending(path: "orb-work-\(name).png")) }
        }
        print("orb work rendered: \(dir.path)")
    }
}
#endif
