import SwiftUI

// Six robots, each a classic way of picturing a machine that talks, drawn in points in its own
// colour: Lens (a glowing camera eye), Dome (a dome-headed droid with lights), Valet (a
// gilded humanoid head), Retro (a glass-domed robot with a voice grille), Deco (an art-deco
// machine woman with rings of light) and Rover (two binocular eyes on a neck). Each shows the five
// states: at rest, listening, speaking, thinking, and working (tools running). Units as the planet
// (1 = its radius, y down).

/// What the robot is doing now, from the engine and the work.
private struct RobotState {
    let th: Double, listen: Double, speak: Double, loud: Double, level: Double, busy: Double
    let spectrum: VoiceFeatures
    init(_ engine: OrbEngine, _ work: OrbWork) {
        th = engine.thinking
        listen = engine.engagement * (1 - engine.talking)
        speak = engine.engagement * engine.talking
        loud = engine.loud
        level = engine.history.value(secondsAgo: 0.05)
        busy = min(1, Double(work.satellites) + (work.pulses.isEmpty ? 0 : 0.5))
        spectrum = VoiceFeatures(level: engine.loud, bands: engine.bands)
    }
}

/// A turn about the vertical axis (yaw), then a tilt toward the viewer (pitch), then a lean (roll).
private struct Turn3 {
    private let cY: Double, sY: Double, cP: Double, sP: Double, cR: Double, sR: Double
    init(yaw: Double, pitch: Double, roll: Double = 0) {
        cY = cos(yaw); sY = sin(yaw); cP = cos(pitch); sP = sin(pitch); cR = cos(roll); sR = sin(roll)
    }
    func apply(_ x: Double, _ y: Double, _ z: Double) -> (x: Double, y: Double, z: Double) {
        let x1 = x * cY + z * sY, z1 = -x * sY + z * cY
        let y2 = y * cP - z1 * sP, z2 = y * sP + z1 * cP
        return (x1 * cR - y2 * sR, x1 * sR + y2 * cR, z2)
    }
}

@inline(__always) private func bump(_ x: Double, _ width: Double) -> Double { exp(-(x * x) / (width * width)) }

extension OrbCanvas {
    /// Scales a part's point count to the orb's size (a small tile draws fewer).
    private func density(_ box: CGSize) -> Double { Double(pointBudget(box)) / 1820 }

    // MARK: Lens

    /// A camera eye: a brushed metal bezel, layers of dark glass, a red glow and a hot core, a soft
    /// reflection on the glass. Only the core runs white; everything else stays red. It breathes at
    /// rest; speaking, its core and glow swell with the voice and faint red rings ripple out through
    /// the glass; listening, its glow gathers in and brightens with your voice; thinking, the glow
    /// dims and a red arc sweeps round the bezel; working, the bezel's ticks light in turn.
    func drawLens(_ gc: inout GraphicsContext, _ box: CGSize) {
        var d = dotCanvas(box)
        let s = RobotState(engine, work)
        let k = density(box)
        let z = 1.35                                                     // the lens fills the frame
        /// Red, never white: capped below the palette's top (near-white) level.
        func red(_ b: Double) -> Double { min(0.62, b) }
        /// A red point: the work's light on it stays red too.
        func glass(_ x: Double, _ y: Double, _ b: Double, _ dither: Double, _ phase: Double) {
            var sx = x, sy = y
            let light = workEffect(&sx, &sy, phase: phase)
            d.dot(sx, sy, red(b + 0.7 * light) * countdownDim(sx / (z * 0.9), sy / (z * 0.9)), dither)
        }
        let breathe = 0.5 + 0.5 * sin(t * 1.4)
        let core = 0.6 + 0.15 * breathe + 0.9 * s.speak * min(1, 1.4 * s.loud) + 0.3 * s.listen * (0.5 + s.level) + 0.15 * s.busy - 0.3 * s.th
        let tint = Color(hex: 0xff3b30)
        // The glow inside the glass, under the points: wider as it speaks, gathered in as it listens.
        let glowR = d.R * z * (0.5 + 0.14 * s.speak * s.loud - 0.08 * s.listen)
        let pal = OrbPalette.colors(for: look.color ?? tint)
        gc.fill(Path(ellipseIn: CGRect(x: d.cx - glowR, y: d.cy - glowR, width: 2 * glowR, height: 2 * glowR)),
                with: .radialGradient(Gradient(stops: [
                    .init(color: Color(hex: 0xfff3c4).opacity(min(1, 0.85 * core)), location: 0),
                    .init(color: pal[3].opacity(min(1, 0.7 * core)), location: 0.16),
                    .init(color: pal[2].opacity(0.4 * core), location: 0.45),
                    .init(color: pal[0].opacity(0.25 * core), location: 0.75),
                    .init(color: .clear, location: 1)]),
                    center: CGPoint(x: d.cx, y: d.cy), startRadius: 0, endRadius: glowR))
        // The bezel: two rims lit from the upper left, knurled ticks; while it works the ticks light in turn.
        let ticks = 60
        let lit = (t * 18).truncatingRemainder(dividingBy: Double(ticks))
        let rimCount = Int(260 * k) + 20
        for j in 0..<rimCount {
            let a = 2 * Double.pi * Double(j) / Double(rimCount)
            for (r, b) in [(0.86, 0.6), (0.76, 0.45)] {
                let sheen = 0.55 + 0.45 * cos(a + 2.4)
                glass(z * r * cos(a), z * r * sin(a), b * sheen, OrbPoints.hash(j, r), a)
            }
        }
        for j in 0..<ticks {
            let a = 2 * Double.pi * Double(j) / Double(ticks)
            let behind = (lit - Double(j) + Double(ticks)).truncatingRemainder(dividingBy: Double(ticks))
            let run = s.busy * (behind < 8 ? 1 - behind / 8 : 0)
            for q in 0..<4 {
                let r = 0.785 + 0.018 * Double(q)
                glass(z * r * cos(a), z * r * sin(a), 0.26 + 0.5 * run, OrbPoints.hash(j * 4 + q, 9), a)
            }
        }
        // Thinking: a red arc sweeping round the bezel.
        if s.th > 0.02 {
            let a0 = t * 2.2
            for j in 0..<70 {
                let a = a0 + 1.1 * Double(j) / 69
                glass(z * 0.81 * cos(a), z * 0.81 * sin(a), s.th * (0.2 + 0.45 * Double(j) / 69), OrbPoints.hash(j, 17), a)
            }
        }
        // The glass: faint red rings; its words ripple out through them.
        for (n, r) in [0.66, 0.53, 0.4, 0.28].enumerated() {
            let ripple = s.speak * 0.4 * engine.history.value(secondsAgo: r * 0.9)
            let m = max(12, Int(Double(90 + 30 * n) * k * r * 2))
            for j in 0..<m {
                let a = 2 * Double.pi * Double(j) / Double(m)
                glass(z * r * cos(a), z * r * sin(a), 0.12 + ripple, OrbPoints.hash(j * 7 + n, 5), a)
            }
        }
        // The core: a hot centre (the only white), its red rim.
        for j in 0..<Int(80 * k) + 10 {
            let a = 2 * Double.pi * OrbPoints.hash(j, 1), r = 0.085 * OrbPoints.hash(j, 2).squareRoot() * (1 + 0.25 * s.speak * s.loud)
            place(&d, z * r * cos(a), z * r * sin(a), 1.2 * core, OrbPoints.hash(j, 14), phase: a, lum: 1)
        }
        // The reflection: a soft arc on the glass, upper left (red, like the rest of the glass).
        for j in 0..<Int(80 * k) + 10 {
            let f = Double(j) / (80 * k + 10)
            let a = 3.55 + 0.75 * f, r = 0.6 - 0.02 * sin(f * .pi)
            glass(z * r * cos(a), z * r * sin(a), 0.5 * sin(f * .pi), OrbPoints.hash(j, 31), a)
        }
        // The work's rings and satellites are drawn in the same red (no white light over the lens).
        drawWaves(&gc, cx: d.cx, cy: d.cy, R: d.R, pal: pal)
        for b in 0..<5 { gc.fill(d.paths[b], with: .color(pal[b])) }
        drawSatellites(&gc, cx: d.cx, cy: d.cy, R: d.R, px: d.px, pal: Array(pal.prefix(4)) + [pal[3]])
    }

    // MARK: Dome

    /// A small droid: a rounded dome on a barrel body with two side legs, seen from a little above.
    /// The dome carries a large round eye, a small one, blinking panels of lights and a projector.
    /// At rest the dome looks around; speaking, it chatters (quick little turns) and its lights blink
    /// with the voice's bands; listening, it turns to face you and its eye lights with your voice;
    /// thinking, the dome spins and its lights run; working, its projector casts a small hologram.
    func drawDome(_ gc: inout GraphicsContext, _ box: CGSize) {
        var d = dotCanvas(box)
        let s = RobotState(engine, work)
        let k = density(box)
        let sway = 0.55 * sin(t * 0.31) + 0.2 * sin(t * 0.83)
        let chatter = 0.22 * sin(t * 3.3) * s.speak * min(1, 1.5 * s.loud)
        let spin = engine.ringTurn * 2.2
        let domeYaw = (sway + chatter) * (1 - s.listen) * (1 - s.th) + spin * s.th
        let bodyYaw = 0.12 * sin(t * 0.17)
        let pitch = 0.32
        let bodyTurn = Turn3(yaw: bodyYaw, pitch: pitch), domeTurn = Turn3(yaw: bodyYaw + domeYaw, pitch: pitch)
        let oy = -0.15, scale = 1.0
        func put(_ p: (x: Double, y: Double, z: Double), _ b: Double, _ dither: Double, _ phase: Double, lum: Double = 0.7, size: Double = 1) {
            let facing = p.z > 0 ? 1.0 : 0.25
            place(&d, p.x * scale, (p.y + oy) * scale, b * facing, dither, phase: phase, lum: lum, size: size)
        }
        let R = 0.88
        // The dome: a hemisphere, its panels and seams; features fixed on it, turning with it.
        for j in 0..<Int(520 * k) + 40 {
            let u = OrbPoints.hash(j, 1), v = OrbPoints.hash(j, 2)
            let el = asin(u)                                            // 0 at the rim … π/2 at the top
            let az = 2 * Double.pi * v
            // Panels: blocks in a band round the dome (bright), seams between them; the rest sparse.
            let inBand = el > 0.34 && el < 0.86
            let block = inBand && sin(3 * az + 0.6) > 0.35
            let seam = max(bump(el - 0.32, 0.025), bump(el - 0.88, 0.025))
            if !block && seam < 0.3 && OrbPoints.hash(j, 3) < 0.55 { continue }
            let x = R * cos(el) * sin(az), y = -R * sin(el), z = R * cos(el) * cos(az)
            put(domeTurn.apply(x, y, z), 0.16 + 0.5 * seam + (block ? 0.38 : 0), OrbPoints.hash(j, 14), az)
        }
        // The dome's outline as seen (a half ellipse: its rim tilted toward us, and its edge).
        for j in 0..<Int(200 * k) + 20 {
            let a = 2 * Double.pi * Double(j) / (200 * k + 20)
            let rim = bodyTurn.apply(R * sin(a), 0, R * cos(a))
            put((rim.x, rim.y, 1), 0.7, OrbPoints.hash(j, 41), a)
            if a < .pi {
                let edgeY = -R * sin(a) * cos(pitch)
                put((R * cos(a), edgeY + R * 0 , 1), 0.55, OrbPoints.hash(j, 42), a)
            }
        }
        // A point on the dome at elevation `el`, azimuth `az` (0 = its front), pushed out a little.
        func onDome(_ el: Double, _ az: Double, _ out: Double = 1.01) -> (Double, Double, Double) {
            (R * out * cos(el) * sin(az), -R * out * sin(el), R * out * cos(el) * cos(az))
        }
        // The main eye: a dark lens in a bright ring, a glint; it lights with your voice.
        let eyeEl = 0.62, eyeAz = 0.0
        for j in 0..<Int(120 * k) + 16 {
            let a = 2 * Double.pi * Double(j) / (120 * k + 16)
            for (r, b) in [(0.15, 0.95), (0.11, 0.5)] {
                let p = onDome(eyeEl + r * sin(a), eyeAz + r * cos(a) / cos(eyeEl))
                put(domeTurn.apply(p.0, p.1, p.2), b + 0.6 * s.listen * s.level, OrbPoints.hash(j, r), a, lum: 0.9)
            }
        }
        for j in 0..<10 {
            let p = onDome(eyeEl + 0.04 + 0.02 * OrbPoints.hash(j, 1), eyeAz - 0.04 + 0.03 * OrbPoints.hash(j, 2), 1.02)
            put(domeTurn.apply(p.0, p.1, p.2), 1.2, 0.5, 0, lum: 1)
        }
        // The small eye and the projector.
        for j in 0..<30 {
            let a = 2 * Double.pi * Double(j) / 30
            let p = onDome(0.85 + 0.05 * sin(a), 0.55 + 0.05 * cos(a) / cos(0.85))
            put(domeTurn.apply(p.0, p.1, p.2), 0.7, OrbPoints.hash(j, 4), a)
            let q = onDome(0.45 + 0.06 * sin(a), -1.25 + 0.06 * cos(a) / cos(0.45))
            put(domeTurn.apply(q.0, q.1, q.2), 0.55 + 0.6 * s.busy, OrbPoints.hash(j, 6), a)
        }
        // Panels of lights under the eye: each light blinks; with the voice, each column follows a
        // band; thinking, they run in a chase.
        for panel in 0..<2 {
            let az0 = panel == 0 ? -0.42 : 0.36
            for c in 0..<4 {
                for r in 0..<3 {
                    let cell = panel * 12 + c * 3 + r
                    let rate = 1.2 + 6 * s.speak
                    let tick = Int(t * rate)
                    var on = OrbPoints.hash(cell * 101 + tick, 7) < 0.45 ? 1.0 : 0.15
                    if s.speak > 0.05 { on = max(on * (1 - s.speak), s.spectrum.band(at: Double(c) / 3) > 0.3 + 0.2 * Double(r) ? 1 : 0.15) }
                    if s.th > 0.05 { on = max(on * (1 - s.th), Int(t * 10) % 12 == c * 3 + r ? 1 : 0.2) }
                    for q in 0..<4 {
                        let p = onDome(0.32 - 0.07 * Double(r) - 0.02 * Double(q / 2), az0 + 0.08 * Double(c) + 0.025 * Double(q % 2))
                        put(domeTurn.apply(p.0, p.1, p.2), 0.2 + 0.85 * on, OrbPoints.hash(cell * 4 + q, 9), 0, lum: 0.9)
                    }
                }
            }
        }
        // Working: the projector casts a small hologram in front of the dome.
        if s.busy > 0.05 {
            let src = onDome(0.45, -1.25)
            let a = domeTurn.apply(src.0, src.1, src.2)
            let target = (x: -1.15, y: -0.55)
            for j in 0..<50 {
                let f = Double(j) / 49
                put((a.x + (target.x - a.x) * f, a.y + (target.y - a.y) * f + 0.06 * sin(f * 9 + t * 6), 1), s.busy * 0.35, OrbPoints.hash(j, 12), f)
            }
            for j in 0..<40 {
                let ang = 2 * Double.pi * Double(j) / 40 + t
                put((target.x + 0.14 * cos(ang), target.y + 0.14 * sin(ang) * 0.5 - 0.05 * sin(t * 3), 1), s.busy * 0.8, OrbPoints.hash(j, 13), ang)
            }
        }
        // The body: a barrel with a collar, ribs and panel seams; two side legs.
        // The body: its rings, panel seams, two front panels with their details; its sides.
        let fadeBody = { (y: Double) in 1 - smoothstep(1.3, 1.72, y) }
        for ringY in [0.04, 0.5, 0.98, 1.45] {
            for j in 0..<Int(150 * k) + 16 {
                let az = 2 * Double.pi * Double(j) / (150 * k + 16)
                put(bodyTurn.apply(R * sin(az), ringY, R * cos(az)), (ringY == 0.04 ? 0.8 : 0.4) * fadeBody(ringY), OrbPoints.hash(j, ringY), az)
            }
        }
        for c in 0..<12 {
            let az = Double(c) * Double.pi / 6 + 0.26
            for j in 0..<Int(40 * k) + 6 {
                let y = 0.04 + 1.6 * Double(j) / (40 * k + 6)
                put(bodyTurn.apply(R * sin(az), y, R * cos(az)), 0.3 * fadeBody(y), OrbPoints.hash(c * 64 + j, 43), y)
            }
        }
        for (az0, y0, y1) in [(-0.22, 0.14, 0.44), (0.22, 0.6, 0.9)] {
            for j in 0..<Int(60 * k) + 10 {
                let f = Double(j) / (60 * k + 10)
                for (az, y) in [(az0 - 0.2 + 0.4 * f, y0), (az0 - 0.2 + 0.4 * f, y1), (az0 - 0.2, y0 + (y1 - y0) * f), (az0 + 0.2, y0 + (y1 - y0) * f)] {
                    put(bodyTurn.apply(R * 1.005 * sin(az), y, R * 1.005 * cos(az)), 0.6, OrbPoints.hash(j, az + y), f)
                }
            }
            for q in 0..<3 {                                            // vents / buttons on the panel
                let az = az0 - 0.1 + 0.1 * Double(q), y = (y0 + y1) / 2
                for j in 0..<8 {
                    let a = 2 * Double.pi * Double(j) / 8
                    put(bodyTurn.apply(R * 1.01 * sin(az + 0.025 * cos(a)), y + 0.025 * sin(a), R * 1.01 * cos(az + 0.025 * cos(a))), 0.55, 0.5, a)
                }
            }
        }
        for side in [-1.0, 1.0] {                                       // the body's sides as seen
            for j in 0..<Int(70 * k) + 10 {
                let y = 0.04 + 1.6 * Double(j) / (70 * k + 10)
                let p = bodyTurn.apply(side * R, y, 0)
                put((p.x, p.y, 1), 0.55 * fadeBody(y), OrbPoints.hash(j, side + 44), y)
            }
        }
        for side in [-1.0, 1.0] {
            for j in 0..<Int(140 * k) + 10 {
                let f = OrbPoints.hash(j, 1), edge = OrbPoints.hash(j, 2) < 0.5 ? 0.0 : 1.0
                let x = side * (0.98 + 0.2 * edge), y = -0.05 + 1.8 * f
                put(bodyTurn.apply(x, y, 0.1), 0.45 * (1 - smoothstep(1.3, 1.75, y)), OrbPoints.hash(j, 14), f)
            }
            for j in 0..<36 {                                           // the shoulder joint
                let a = 2 * Double.pi * Double(j) / 36
                put(bodyTurn.apply(side * (1.08 + 0.02 * cos(a)), 0.2 + 0.17 * sin(a), 0.17 * cos(a) + 0.1), 0.6, OrbPoints.hash(j, side), a)
            }
        }
        finish(&gc, d, tint: Color(hex: 0x4aa3ff))
    }

    // MARK: Valet

    /// A gilded humanoid robot, head and shoulders: a smooth metal head with round glowing eyes, a
    /// small nose, a slot of a mouth, ear discs, a segmented neck and a collar. Speaking, its eyes and
    /// mouth glow with the voice and it talks with its whole head (bobbing, tilting); listening, it
    /// cocks its head, eyes steady; thinking, it turns aside and looks up, its eyes flickering;
    /// working, a light scans across its eyes.
    func drawValet(_ gc: inout GraphicsContext, _ box: CGSize) {
        var d = dotCanvas(box)
        let s = RobotState(engine, work)
        let k = density(box)
        let yaw = 0.12 * sin(t * 0.27) + 0.35 * s.th + 0.12 * s.speak * sin(t * 1.3)
        let pitch = 0.04 * sin(t * 0.21) - 0.12 * s.th + 0.06 * s.speak * s.loud * sin(t * 5.2)
        let roll = 0.04 * sin(t * 0.19) + 0.2 * s.listen + 0.1 * s.speak * sin(t * 1.7)
        let head = Turn3(yaw: yaw, pitch: pitch, roll: roll)
        let hy = -0.42, hw = 0.56, hh = 0.68, hd = 0.52
        func put(_ x: Double, _ y: Double, _ z: Double, _ b: Double, _ dither: Double, _ phase: Double, lum: Double = 0.7, onHead: Bool = true) {
            let p = onHead ? head.apply(x, y - hy, z) : (x: x, y: y - hy, z: z)
            guard p.z > -0.15 || !onHead else { return }
            let shade = onHead ? 0.3 + 0.7 * smoothstep(-0.2, 0.5, p.z) : 1
            place(&d, p.x * 1.15, (p.y + hy) * 1.15 + 0.05, b * shade, dither, phase: phase, lum: lum)
        }
        // The head's surface: metal, lit from the upper left with a soft highlight.
        for j in 0..<Int(700 * k) + 40 {
            let u = 1 - 2 * OrbPoints.hash(j, 1), a = 2 * Double.pi * OrbPoints.hash(j, 2)
            let r = (1 - u * u).squareRoot()
            let nx = r * cos(a), ny = u, nz = r * sin(a)
            guard nz > -0.2 else { continue }
            let w = ny > 0 ? 1 - 0.25 * ny : 1                         // narrower toward the jaw
            let x = hw * nx * w, y = hy + hh * ny, z = hd * nz
            let light = max(0, -0.5 * nx - 0.45 * ny + 0.74 * nz)
            let sheen = pow(light, 10)
            let seam = max(bump(nx - 0.62, 0.03), bump(nx + 0.62, 0.03), bump(ny + 0.45, 0.03)) * (nz > 0 ? 1 : 0)
            let rim = bump(nz - 0.05, 0.12)                              // the head's outline
            if sheen < 0.2 && seam < 0.3 && rim < 0.3 && OrbPoints.hash(j, 3) < 0.45 { continue }
            put(x, y, z, 0.12 + 0.3 * light + 0.9 * sheen + 0.4 * seam + 0.45 * rim, OrbPoints.hash(j, 14), a)
        }
        func front(_ x: Double, _ y: Double) -> Double {
            let ny = (y - hy) / hh, w = hw * (ny > 0 ? 1 - 0.25 * ny : 1)
            return hd * max(0, 1 - pow(x / w, 2) - ny * ny).squareRoot() + 0.01
        }
        // The eyes: rims and glowing lenses (brighter as it speaks; flickering as it thinks).
        let flicker = 1 - 0.35 * s.th * (0.5 + 0.5 * sin(t * 13))
        let eyeGlow = (0.75 + 0.6 * s.speak * min(1, 1.5 * s.loud) + 0.2 * s.listen) * flicker
        let scan = s.busy * bump(sin(t * 3), 0.25)
        for side in [-1.0, 1.0] {
            let ex = side * 0.21, ey = -0.47
            for j in 0..<Int(80 * k) + 12 {
                let a = 2 * Double.pi * Double(j) / (80 * k + 12)
                put(ex + 0.11 * cos(a), ey + 0.1 * sin(a), front(ex, ey), 0.75, OrbPoints.hash(j, side), a, lum: 0.9)
            }
            for j in 0..<Int(70 * k) + 10 {
                let a = 2 * Double.pi * OrbPoints.hash(j, 1), r = 0.075 * OrbPoints.hash(j, 2).squareRoot()
                let b = eyeGlow * (0.6 + 0.6 * (1 - r / 0.075)) + scan * bump(cos(a) * r - side * 0.03 * sin(t * 3), 0.02)
                put(ex + r * cos(a), ey + r * sin(a), front(ex, ey) + 0.01, b, OrbPoints.hash(j, 14), a, lum: 1)
            }
        }
        // Brow ridge, nose, mouth slot (glowing with the voice, opening a little).
        for j in 0..<Int(60 * k) + 10 {
            let f = 2 * OrbPoints.hash(j, 1) - 1
            put(0.4 * f, -0.62 - 0.03 * (1 - f * f) - 0.02 * s.listen, front(0.4 * f, -0.62) + 0.01, 0.6, OrbPoints.hash(j, 3), f)
        }
        for j in 0..<24 {
            let f = Double(j) / 23
            put(0.006, -0.38 + 0.15 * f, front(0, -0.38) + 0.03 * f + 0.01, 0.55, OrbPoints.hash(j, 4), f)
        }
        let open = 0.012 + 0.03 * s.speak * min(1, 1.5 * s.loud)
        let slot = 0.25 + 0.9 * s.speak * s.loud
        for j in 0..<Int(70 * k) + 10 {
            let f = 2 * OrbPoints.hash(j, 1) - 1, edge = OrbPoints.hash(j, 2) < 0.5 ? -1.0 : 1.0
            put(0.13 * f, -0.13 + edge * open, front(0.13 * f, -0.13), 0.5 + 0.4 * slot, OrbPoints.hash(j, 5), f)
            if j % 2 == 0 { put(0.12 * f, -0.13 + edge * open * OrbPoints.hash(j, 6), front(0, -0.13), slot * 0.6, OrbPoints.hash(j, 7), f) }
        }
        // The ear discs on its sides.
        for side in [-1.0, 1.0] {
            for j in 0..<40 {
                let a = 2 * Double.pi * Double(j) / 40
                for r in [0.12, 0.07] {
                    put(side * (hw + 0.01), -0.42 + r * sin(a), r * cos(a), 0.6, OrbPoints.hash(j, r + side), a)
                }
            }
        }
        // The neck (segmented) and the collar, shoulders.
        for j in 0..<Int(160 * k) + 10 {
            let ring = Double(j % 7), a = 2 * Double.pi * OrbPoints.hash(j, 1)
            put(0.17 * sin(a), 0.16 + 0.05 * ring, 0.17 * cos(a), cos(a) > 0 ? 0.45 : 0.12, OrbPoints.hash(j, 14), a, onHead: false)
        }
        // Shoulders and chest: plated contours, a collar ring, a round plate at the centre.
        for (n, dy) in [0.0, 0.1, 0.22].enumerated() {
            for j in 0..<Int(140 * k) + 16 {
                let x = (2 * Double(j) / (140 * k + 16) - 1) * 1.5
                let top = 0.52 + dy + 0.25 * pow(max(0, abs(x) - 0.25 + dy) / 1.25, 1.4)
                put(x, top, 0, (n == 0 ? 0.7 : 0.35) * (1 - smoothstep(1.2, 1.5, abs(x))), OrbPoints.hash(j, dy), x, onHead: false)
            }
        }
        for j in 0..<Int(80 * k) + 10 {
            let a = Double.pi * Double(j) / (80 * k + 10)
            put(0.32 * cos(a), 0.5 + 0.14 * sin(a), 0, 0.5, OrbPoints.hash(j, 51), a, onHead: false)
        }
        for r in [0.13, 0.08] {
            for j in 0..<36 {
                let a = 2 * Double.pi * Double(j) / 36
                put(r * cos(a), 0.95 + r * sin(a), 0, 0.5 + 0.4 * s.busy * (Int(t * 4) % 2 == 0 ? 1 : 0), OrbPoints.hash(j, r), a, onHead: false)
            }
        }
        finish(&gc, d, tint: Color(hex: 0xf2c14e))
    }

    // MARK: Retro

    /// A robot of the fifties: a glass dome with its works turning inside, antennae with spinning
    /// discs on its sides, a face plate with a grille of lights, a ribbed barrel chest with dials.
    /// Speaking, the grille's columns light with the voice's bands; listening, the discs spin fast
    /// and the works pulse with your voice; thinking, the works spin and the grille runs a chase;
    /// working, the chest's lights blink.
    func drawRetro(_ gc: inout GraphicsContext, _ box: CGSize) {
        var d = dotCanvas(box)
        let s = RobotState(engine, work)
        let k = density(box)
        let lean = 0.05 * sin(t * 0.23)
        func put(_ x: Double, _ y: Double, _ b: Double, _ dither: Double, _ phase: Double, lum: Double = 0.7, size: Double = 1) {
            let c = cos(lean), sn = sin(lean)
            place(&d, x * c - (y - 0.6) * sn, x * sn + (y - 0.6) * c + 0.6 - 0.1, b, dither, phase: phase, lum: lum, size: size)
        }
        // The glass dome: its outline, a rim, reflections.
        let domeW = 0.66, domeTop = -1.25, domeBase = -0.45
        for j in 0..<Int(260 * k) + 20 {
            let a = Double.pi * Double(j) / (260 * k + 20)
            put(-domeW * cos(a), domeBase - (domeBase - domeTop) * sin(a), 0.55, OrbPoints.hash(j, 1), a)
            if a > 0.35 && a < 1.05 {                                     // a reflection, upper left
                put(-domeW * 0.82 * cos(a), domeBase - (domeBase - domeTop) * 0.82 * sin(a), 0.7, OrbPoints.hash(j, 2), a, lum: 1)
            }
        }
        for j in 0..<Int(120 * k) + 10 {
            let f = 2 * OrbPoints.hash(j, 1) - 1
            put(domeW * 1.04 * f, domeBase + 0.02 * OrbPoints.hash(j, 2), 0.75, OrbPoints.hash(j, 3), f)
        }
        // The works inside: two gyro rings turning (fast when thinking), a pulsing core.
        let spin = engine.ringTurn * 3 + t * (0.6 + 2.5 * s.listen * s.level)
        for (n, (r, tilt)) in [(0.22, 0.4), (0.16, -0.9)].enumerated() {
            let ct = cos(tilt + Double(n) * spin * 0.3), st = sin(tilt + Double(n) * spin * 0.3)
            for j in 0..<Int(70 * k) + 12 {
                let a = 2 * Double.pi * Double(j) / (70 * k + 12) + spin * (n == 0 ? 1 : -1.3)
                let x = r * cos(a), y = r * sin(a) * ct, z = r * sin(a) * st
                put(x, -0.82 + y, z > 0 ? 0.7 : 0.25, OrbPoints.hash(j, Double(n)), a)
            }
        }
        for j in 0..<24 {
            let a = 2 * Double.pi * OrbPoints.hash(j, 1), r = 0.05 * OrbPoints.hash(j, 2)
            put(r * cos(a), -0.82 + r * sin(a), 0.6 + 0.8 * s.listen * s.level + 0.5 * s.th, OrbPoints.hash(j, 3), a, lum: 1)
        }
        for side in [-1.0, 1.0] {                                         // pistons
            for j in 0..<20 {
                let f = Double(j) / 19
                put(side * 0.4, -0.55 - 0.3 * f - 0.08 * sin(t * 2.4 + side) * f, 0.35, OrbPoints.hash(j, side), f)
            }
        }
        // The antennae: a rod out from each side of the dome and a spinning disc.
        let discSpin = t * (1.4 + 9 * s.listen + 3 * s.speak + 4 * s.th)
        for side in [-1.0, 1.0] {
            let base = (x: side * 0.62, y: -0.72), tip = (x: side * 0.98, y: -1.0)
            for j in 0..<24 {
                let f = Double(j) / 23
                put(base.x + (tip.x - base.x) * f, base.y + (tip.y - base.y) * f, 0.55, OrbPoints.hash(j, side + 3), f)
            }
            for j in 0..<40 {                                              // the disc, seen edge-on as it turns
                let a = 2 * Double.pi * Double(j) / 40
                put(tip.x + 0.16 * cos(a) * cos(discSpin * side), tip.y + 0.16 * sin(a), 0.6, OrbPoints.hash(j, side + 5), a)
            }
        }
        // The face plate and its grille of lights.
        for j in 0..<Int(140 * k) + 10 {
            let f = Double(j) / (140 * k + 10)
            let a = 2 * Double.pi * f
            put(0.5 * cos(a) * min(1, 1.3 * abs(cos(a)) + 0.4), -0.18 + 0.22 * sin(a), 0.5, OrbPoints.hash(j, 9), a)
        }
        let columns = 7
        for c in 0..<columns {
            let cx = -0.36 + 0.12 * Double(c)
            let voice = s.speak * min(1, 1.6 * s.spectrum.band(at: Double(c) / Double(columns - 1)) + 0.3 * s.loud)
            let chase = s.th * (Int(t * 8) % columns == c ? 1 : 0.1)
            for r in 0..<3 {
                let height = Double(r) / 2
                let on = 0.12 + (voice > height * 0.8 ? 0.9 * voice : 0) + chase + 0.08 * sin(t * 0.8 + Double(c))
                for q in 0..<5 {
                    put(cx + 0.02 * Double(q % 2), -0.27 + 0.1 * Double(r) + 0.02 * Double(q / 2), on, OrbPoints.hash(c * 15 + r * 5 + q, 11), Double(c), lum: 0.9)
                }
            }
        }
        // The collar and the ribbed barrel chest with its dials and lights.
        func chestWidth(_ y: Double) -> Double { 1.0 + 0.25 * sin(min(1, (y - 0.1) / 1.2) * .pi * 0.9) }
        var ribY = 0.14
        var rib = 0
        while ribY < 1.72 {                                              // ribs: front arcs of a barrel
            let w = chestWidth(ribY), fade = 1 - smoothstep(1.3, 1.72, ribY)
            for j in 0..<Int(90 * k) + 12 {
                let f = 2 * Double(j) / (90 * k + 12) - 1
                put(w * f, ribY + 0.05 * (1 - f * f), (rib % 3 == 0 ? 0.5 : 0.25) * fade, OrbPoints.hash(j, ribY), f)
            }
            ribY += 0.09; rib += 1
        }
        for side in [-1.0, 1.0] {                                        // its sides
            for j in 0..<Int(80 * k) + 10 {
                let y = 0.12 + 1.6 * Double(j) / (80 * k + 10)
                put(side * chestWidth(y), y, 0.6 * (1 - smoothstep(1.3, 1.72, y)), OrbPoints.hash(j, side + 61), y)
            }
        }
        for (n, dx) in [-0.3, 0.0, 0.3].enumerated() {
            for j in 0..<24 {
                let a = 2 * Double.pi * Double(j) / 24
                put(dx + 0.08 * cos(a), 0.55 + 0.08 * sin(a), 0.55, OrbPoints.hash(j, Double(n) + 20), a)
            }
            let needle = 0.8 * sin(t * (0.7 + 0.4 * Double(n)) + Double(n)) + 1.2 * s.busy * sin(t * 6 + Double(n))
            for j in 0..<8 { put(dx + 0.01 * Double(j) * sin(needle), 0.55 - 0.01 * Double(j) * cos(needle), 0.7, 0.5, 0) }
            let blink = s.busy > 0.05 ? (Int(t * 5 + Double(n)) % 2 == 0 ? 1.0 : 0.15) : 0.3
            for j in 0..<6 {
                put(dx + 0.025 * cos(Double(j)), 0.78 + 0.025 * sin(Double(j)), 0.2 + 0.9 * blink, OrbPoints.hash(j, Double(n) + 30), 0, lum: 1)
            }
        }
        finish(&gc, d, tint: Color(hex: 0x52e8b4))
    }

    // MARK: Deco

    /// An art-deco machine woman: a long serene metal face (half-closed eyes, a fine nose, small
    /// lips), a crest over the head and rivets at the temples, a tall neck of rings, sculpted
    /// shoulders and a sunburst on the chest. Rings of light pass around her: rising from her chest
    /// as she speaks (brighter with the voice), coming down onto her head as she listens (her eyes
    /// open), sweeping slowly up and down as she thinks; working, the sunburst glows in turn.
    func drawDeco(_ gc: inout GraphicsContext, _ box: CGSize) {
        var d = dotCanvas(box)
        let s = RobotState(engine, work)
        let k = density(box)
        let head = Turn3(yaw: 0.1 * sin(t * 0.21) + 0.06 * s.th, pitch: 0.03 * sin(t * 0.17) - 0.06 * s.th, roll: 0.03 * sin(t * 0.13))
        let hy = -0.6, hw = 0.4, hh = 0.6, hd = 0.42
        func putHead(_ x: Double, _ y: Double, _ z: Double, _ b: Double, _ dither: Double, _ phase: Double, lum: Double = 0.7) {
            let p = head.apply(x, y - hy, z)
            guard p.z > -0.1 else { return }
            place(&d, p.x * 1.2, (p.y + hy) * 1.2 + 0.1, b * (0.35 + 0.65 * smoothstep(-0.1, 0.4, p.z)), dither, phase: phase, lum: lum)
        }
        func put(_ x: Double, _ y: Double, _ b: Double, _ dither: Double, _ phase: Double) {
            place(&d, x * 1.2, y * 1.2 + 0.1, b, dither, phase: phase)
        }
        func front(_ x: Double, _ y: Double) -> Double {
            let ny = (y - hy) / hh, w = hw * (ny > 0 ? 1 - 0.3 * ny : 1)
            return hd * max(0, 1 - pow(x / w, 2) - ny * ny).squareRoot() + 0.01
        }
        // The face: smooth metal, a sheen down its middle.
        for j in 0..<Int(800 * k) + 40 {
            let u = 1 - 2 * OrbPoints.hash(j, 1), a = 2 * Double.pi * OrbPoints.hash(j, 2)
            let r = (1 - u * u).squareRoot()
            let nx = r * cos(a), ny = u, nz = r * sin(a)
            guard nz > -0.1 else { continue }
            let w = ny > 0 ? 1 - 0.3 * ny : 1
            let light = max(0, -0.3 * nx - 0.4 * ny + 0.86 * nz)
            putHead(hw * nx * w, hy + hh * ny, hd * nz, 0.14 + 0.35 * light + 0.6 * pow(light, 12), OrbPoints.hash(j, 14), a)
        }
        // Features: half-closed eyes (opening as she listens), brows, a fine nose, small lips.
        let lid = 0.3 + 0.55 * s.listen + 0.15 * s.speak
        for side in [-1.0, 1.0] {
            let ex = side * 0.15, ey = -0.6
            for j in 0..<Int(50 * k) + 10 {
                let f = 2 * OrbPoints.hash(j, 1) - 1
                let upper = OrbPoints.hash(j, 2) < 0.6
                let y = ey + (upper ? -0.028 * lid : 0.02) * (1 - f * f)
                putHead(ex + 0.085 * f, y, front(ex, ey), upper ? 0.85 : 0.5, OrbPoints.hash(j, 3), f, lum: 0.9)
                if j % 3 == 0 { putHead(ex + 0.1 * f, ey - 0.09 - 0.02 * (1 - f * f) + 0.01 * side * f, front(ex, ey - 0.09), 0.6, OrbPoints.hash(j, 4), f) }
            }
            if lid > 0.45 {
                for j in 0..<10 {
                    let a = 2 * Double.pi * Double(j) / 10
                    putHead(ex + 0.018 * cos(a), ey - 0.004 + 0.016 * sin(a) * lid, front(ex, ey) + 0.01, 0.9 * (lid - 0.4), 0.5, a, lum: 1)
                }
            }
        }
        for j in 0..<24 {
            let f = Double(j) / 23
            putHead(0.004, -0.55 + 0.17 * f, front(0, -0.55) + 0.02 * f, 0.55, OrbPoints.hash(j, 6), f)
        }
        let mouthOpen = 0.02 * s.speak * min(1, 1.5 * s.loud)
        for j in 0..<Int(40 * k) + 8 {
            let f = 2 * OrbPoints.hash(j, 1) - 1, lower = OrbPoints.hash(j, 2) < 0.5
            let y = -0.29 + (lower ? 0.012 + mouthOpen : -0.008 - 0.01 * exp(-pow(f / 0.3, 2))) * (1 - f * f)
            putHead(0.075 * f, y, front(0, -0.29), 0.7 + 0.5 * s.speak * s.loud, OrbPoints.hash(j, 7), f)
        }
        // The crest over the head and the rivets at the temples.
        for j in 0..<Int(90 * k) + 10 {
            let a = -Double.pi / 2 + (Double(j) / (90 * k + 10) - 0.5) * 2.2
            putHead(0, hy + hh * 1.04 * sin(a), hd * 1.04 * cos(a), 0.65, OrbPoints.hash(j, 8), a)
        }
        for side in [-1.0, 1.0] {
            for ring in [0.05, 0.028] {
                for j in 0..<24 {
                    let a = 2 * Double.pi * Double(j) / 24
                    putHead(side * (hw * 0.96), -0.62 + ring * sin(a), ring * cos(a) + 0.05, 0.7, OrbPoints.hash(j, ring + side), a)
                }
            }
        }
        // The neck: rings; the shoulders: sculpted arcs; the chest: a sunburst (glowing in turn as it works).
        for n in 0..<6 {
            let y = -0.02 + 0.07 * Double(n), r = 0.15 + 0.012 * Double(n)
            for j in 0..<36 {
                let a = 2 * Double.pi * Double(j) / 36
                put(r * cos(a), y + 0.02 * sin(a), sin(a) > 0 ? 0.55 : 0.15, OrbPoints.hash(j * 6 + n, 9), a)
            }
        }
        for side in [-1.0, 1.0] {
            for arc in 0..<3 {
                for j in 0..<Int(70 * k) + 10 {
                    let f = Double(j) / (70 * k + 10)
                    let x = side * (0.22 + 1.2 * f), y = 0.42 + 0.06 * Double(arc) + 0.42 * f * f
                    put(x, y, 0.5 - 0.12 * Double(arc), OrbPoints.hash(j, Double(arc) + side), f)
                }
            }
        }
        let rays = 11
        let lit = Int(t * 6) % rays
        for r in 0..<rays {
            let a = Double.pi / 2 + (Double(r) - Double(rays - 1) / 2) * 0.16
            let glow = 0.3 + 0.8 * s.busy * (r == lit ? 1 : 0.15)
            for j in 0..<22 {
                let f = 0.15 + 0.85 * Double(j) / 21
                put(0.9 * f * cos(a), 0.55 + 0.9 * f * sin(a), glow * (1 - 0.5 * f), OrbPoints.hash(r * 22 + j, 10), f)
            }
        }
        // The rings of light around her.
        var rings: [(y: Double, b: Double)] = []
        let rest = (t * 0.15).truncatingRemainder(dividingBy: 1)
        rings.append((1.5 - 3.0 * rest, 0.25 * (1 - s.speak) * (1 - s.listen) * (1 - s.th)))
        for n in 0..<3 {
            let f = (t * 0.45 + Double(n) / 3).truncatingRemainder(dividingBy: 1)
            rings.append((1.4 - 2.6 * f, s.speak * (0.2 + 0.9 * engine.history.value(secondsAgo: f * 1.0))))
            rings.append((-1.2 + 1.0 * f, s.listen * (0.25 + 0.8 * s.level) * (1 - f * 0.6)))
            rings.append((0.2 + 1.1 * sin(t * 0.6 + Double(n) * 2.1), s.th * 0.7))
        }
        for ring in rings where ring.b > 0.02 {
            // Wider around the body than around the head.
            let rx = ring.y > 0.2 ? 1.25 : 0.62
            let m = Int(110 * k) + 20
            for j in 0..<m {
                let a = 2 * Double.pi * Double(j) / Double(m)
                let inFront = sin(a) > 0
                put(rx * cos(a), ring.y + 0.12 * rx * sin(a), ring.b * (inFront ? 1 : 0.35), OrbPoints.hash(j, ring.y), a)
            }
        }
        finish(&gc, d, tint: Color(hex: 0xe8d6a8))
    }

    // MARK: Rover

    /// A little rover: two binocular eyes side by side on a neck over a boxy body. Its eyes do the
    /// talking: speaking, their lenses pulse with the voice and they bob; listening, they lift, lean
    /// in and tilt toward each other, lenses wide; thinking, they look one way then the other and
    /// tilt in turn, their zoom rings turning; working, a light scans across the lenses and a lamp
    /// on the body blinks.
    func drawRover(_ gc: inout GraphicsContext, _ box: CGSize) {
        var d = dotCanvas(box)
        let s = RobotState(engine, work)
        let k = density(box)
        let lift = -0.12 * s.listen + 0.04 * s.speak * min(1, 1.5 * s.loud) * sin(t * 6) + 0.015 * sin(t * 0.9)
        let look = 0.06 * sin(t * 0.35) * (1 - s.th) + s.th * 0.1 * (sin(t * 0.9) > 0 ? 1 : -1)
        let aperture = 0.1 + 0.035 * s.listen - 0.025 * s.speak * min(1, 1.5 * s.loud) + 0.01 * sin(t * 0.7)
        let zoom = engine.ringTurn * 4
        let scan = s.busy > 0.05 ? sin(t * 2.6) : 0
        func put(_ x: Double, _ y: Double, _ b: Double, _ dither: Double, _ phase: Double, lum: Double = 0.7) {
            place(&d, x * 1.15, y * 1.15 + 0.12, b, dither, phase: phase, lum: lum)
        }
        for side in [-1.0, 1.0] {
            // Each eye's own tilt: inward to listen, in turn to think, a little sad at rest.
            let tilt = side * (-0.08 * (1 - s.listen) * (1 - s.th) + 0.22 * s.listen) + s.th * 0.18 * sin(t * 0.9 + side)
            let ex = side * 0.43, ey = -0.6 + lift
            let ct = cos(tilt), st = sin(tilt)
            func eye(_ x: Double, _ y: Double, _ b: Double, _ dither: Double, _ phase: Double, lum: Double = 0.7) {
                put(ex + x * ct - y * st, ey + x * st + y * ct, b, dither, phase, lum: lum)
            }
            // The housing: a rounded barrel, its outline and a little shading; a brow plate on top.
            let hwid = 0.3, hhei = 0.24
            for j in 0..<Int(160 * k) + 16 {
                let a = 2 * Double.pi * Double(j) / (160 * k + 16)
                let c = cos(a), sn = sin(a)
                let x = hwid * (abs(c) > 0 ? copysign(pow(abs(c), 0.5), c) : 0)
                let y = hhei * (abs(sn) > 0 ? copysign(pow(abs(sn), 0.5), sn) : 0)
                eye(x, y, 0.65, OrbPoints.hash(j, side), a)
            }
            for j in 0..<Int(120 * k) + 10 {
                let x = (2 * OrbPoints.hash(j, 1) - 1) * hwid * 0.9, y = (2 * OrbPoints.hash(j, 2) - 1) * hhei * 0.85
                guard x * x + y * y > 0.19 * 0.19 else { continue }
                eye(x, y, 0.1 + 0.1 * OrbPoints.hash(j, 3), OrbPoints.hash(j, 14), x)
            }
            for j in 0..<Int(60 * k) + 8 {
                let f = 2 * OrbPoints.hash(j, 1) - 1
                eye(hwid * 0.95 * f, -hhei - 0.05 - 0.02 * OrbPoints.hash(j, 2), 0.5, OrbPoints.hash(j, 3), f)
            }
            // The lens: rims, a zoom ring that turns as it thinks, the aperture, a glint.
            let lx = look * 0.6, ly = 0.0
            for (r, b) in [(0.19, 0.8), (0.16, 0.4)] {
                for j in 0..<Int(70 * k) + 12 {
                    let a = 2 * Double.pi * Double(j) / (70 * k + 12)
                    let dash = r == 0.16 ? (sin(9 * a + zoom * side) > 0 ? 1.0 : 0.3) : 1
                    eye(lx + r * cos(a), ly + r * sin(a), b * dash, OrbPoints.hash(j, r + side), a)
                }
            }
            for j in 0..<Int(50 * k) + 10 {
                let a = 2 * Double.pi * Double(j) / (50 * k + 10)
                eye(lx + aperture * cos(a), ly + aperture * sin(a), 0.85 + 0.5 * s.speak * s.loud + 0.4 * s.listen * s.level, OrbPoints.hash(j, side + 9), a, lum: 1)
            }
            for j in 0..<16 {
                let a = 2 * Double.pi * OrbPoints.hash(j, 1), r = 0.03 * OrbPoints.hash(j, 2)
                eye(lx + r * cos(a), ly + r * sin(a), 0.5 + 0.6 * s.speak * s.loud, 0.5, a, lum: 1)
                eye(lx - 0.07 + r * 0.6 * cos(a), ly - 0.08 + r * 0.6 * sin(a), 1.1, 0.5, a, lum: 1)
            }
            if s.busy > 0.05 {
                for j in 0..<14 {
                    let f = Double(j) / 13 - 0.5
                    eye(lx + 0.16 * scan, ly + 0.3 * f, s.busy * 0.8 * (1 - abs(f) * 1.6), 0.5, f)
                }
            }
        }
        // The bridge between the eyes, the neck with its joint, the body.
        for j in 0..<30 {
            let f = 2 * OrbPoints.hash(j, 1) - 1
            put(0.13 * f, -0.6 + lift + 0.05 * (OrbPoints.hash(j, 2) - 0.5), 0.5, OrbPoints.hash(j, 3), f)
        }
        for j in 0..<Int(80 * k) + 10 {
            let f = OrbPoints.hash(j, 1), side = OrbPoints.hash(j, 2) < 0.5 ? -1.0 : 1.0
            put(side * 0.05, -0.55 + lift + (0.75 - lift) * f, 0.5, OrbPoints.hash(j, 3), f)
        }
        for j in 0..<30 {
            let a = 2 * Double.pi * Double(j) / 30
            put(0.07 * cos(a), 0.05 + 0.07 * sin(a), 0.6, OrbPoints.hash(j, 4), a)
        }
        // The body: a box (its edges, a top lid, panel seams, rivets), and the treads at its feet.
        let fade = { (y: Double) in 1 - smoothstep(1.45, 1.8, y) }
        for j in 0..<Int(120 * k) + 16 {
            let f = 2 * Double(j) / (120 * k + 16) - 1
            put(0.95 * f, 0.32, 0.7, OrbPoints.hash(j, 71), f)
            put(0.95 * f, 0.4, 0.35, OrbPoints.hash(j, 72), f)
            put(0.95 * f, 0.78, 0.3, OrbPoints.hash(j, 73), f)
        }
        for x in [-0.95, -0.5, 0.5, 0.95] {
            for j in 0..<Int(70 * k) + 10 {
                let y = 0.32 + 1.4 * Double(j) / (70 * k + 10)
                put(x, y, (abs(x) > 0.9 ? 0.65 : 0.3) * fade(y), OrbPoints.hash(j, x + 74), y)
            }
        }
        for (x, y) in [(-0.85, 0.5), (0.85, 0.5), (-0.85, 0.95), (0.85, 0.95), (-0.6, 0.6), (0.6, 0.6)] {
            for j in 0..<8 {
                let a = 2 * Double.pi * Double(j) / 8
                put(x + 0.02 * cos(a), y + 0.02 * sin(a), 0.5, 0.5, a)
            }
        }
        let roll = (t * (0.4 + 2 * s.busy + 1.2 * s.speak * s.loud)).truncatingRemainder(dividingBy: 1)
        for side in [-1.0, 1.0] {                                        // treads: trapezoid track units
            let corners: [(Double, Double)] = [(0.9, 1.0), (1.2, 1.0), (1.42, 1.72), (0.86, 1.72)]
            for j in 0..<Int(140 * k) + 16 {
                let f = Double(j) / (140 * k + 16)
                let edge = Int(f * 4), g = f * 4 - Double(edge)
                let a = corners[edge], b = corners[(edge + 1) % 4]
                let x = side * (a.0 + (b.0 - a.0) * g), y = a.1 + (b.1 - a.1) * g
                let cleat = bump(sin((f + roll * side) * 2 * .pi * 14), 0.3)
                put(x, y, (0.35 + 0.5 * cleat) * fade(y - 0.1), OrbPoints.hash(j, side + 75), f)
            }
            for j in 0..<Int(40 * k) + 6 {                                // its wheel hub
                let a = 2 * Double.pi * Double(j) / (40 * k + 6) + roll * 6 * side
                put(side * (1.12 + 0.09 * cos(a)), 1.4 + 0.09 * sin(a), 0.45, OrbPoints.hash(j, side + 76), a)
            }
        }
        let lamp = s.busy > 0.05 ? (Int(t * 4) % 2 == 0 ? 1.0 : 0.2) : 0.35 + 0.2 * sin(t)
        for j in 0..<20 {
            let a = 2 * Double.pi * OrbPoints.hash(j, 1), r = 0.05 * OrbPoints.hash(j, 2).squareRoot()
            put(-0.7 + r * cos(a), 0.5 + r * sin(a), lamp, 0.5, a, lum: 1)
        }
        finish(&gc, d, tint: Color(hex: 0xffb547))
    }
}
