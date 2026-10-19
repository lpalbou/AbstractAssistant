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
        let p = OrbPhases(engine)
        th = p.think; listen = p.listen; speak = p.speak; busy = p.work
        loud = p.loud; level = p.level; spectrum = p.spectrum
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

/// Metal lit from the upper left in front: a matte part and a highlight (`shine`: its strength).
@inline(__always) private func metal(_ nx: Double, _ ny: Double, _ nz: Double, shine: Double = 0.6) -> Double {
    let lx = -0.48, ly = -0.55, lz = 0.68
    let diffuse = max(0, nx * lx + ny * ly + nz * lz)
    let hx = lx, hy = ly, hz = lz + 1, hl = (hx * hx + hy * hy + hz * hz).squareRoot()
    let spec = pow(max(0, (nx * hx + ny * hy + nz * hz) / hl), 22)
    return 0.1 + 0.55 * diffuse + shine * spec
}

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
        paintDots(&gc, d.paths, pal, px: d.px)
        drawSatellites(&gc, cx: d.cx, cy: d.cy, R: d.R, px: d.px, pal: Array(pal.prefix(4)) + [pal[3]])
    }

    // MARK: Dome

    /// A small droid, solid: a domed head of metal panels (a large round eye, a small one, panels of
    /// lights, a projector) on a barrel body with two side legs, seen from a little above. At rest the
    /// dome looks around; listening, it turns to face you and its eye lights with your voice; thinking,
    /// the dome spins and its lights run; working, its projector casts a small hologram; speaking, it
    /// chatters (quick little turns) and its lights blink with the voice's bands.
    func drawDome(_ gc: inout GraphicsContext, _ box: CGSize) {
        var d = dotCanvas(box)
        let s = RobotState(engine, work)
        let k = density(box)
        let sway = 0.55 * sin(t * 0.31) + 0.2 * sin(t * 0.83)
        let chatter = 0.22 * sin(t * 3.3) * s.speak * min(1, 1.5 * s.loud)
        let domeYaw = (sway + chatter) * (1 - s.listen) * (1 - s.th) + engine.ringTurn * 2.2 * s.th
        let bodyYaw = 0.12 * sin(t * 0.17)
        let pitch = 0.3
        let bodyTurn = Turn3(yaw: bodyYaw, pitch: pitch), domeTurn = Turn3(yaw: bodyYaw + domeYaw, pitch: pitch)
        let oy = -0.12
        /// A surface point and its normal, turned; drawn only on the side facing us, lit, nearer larger.
        func surf(_ turn: Turn3, _ x: Double, _ y: Double, _ z: Double, _ nx: Double, _ ny: Double, _ nz: Double,
                  _ tone: Double, _ dither: Double, shine: Double = 0.5) {
            let n = turn.apply(nx, ny, nz)
            guard n.z > -0.02 else { return }
            let p = turn.apply(x, y, z)
            place(&d, p.x, p.y + oy, tone * metal(n.x, n.y, n.z, shine: shine), dither, phase: x, lum: 0.6, size: 0.85 + 0.35 * smoothstep(-1, 1, p.z))
        }
        func light(_ turn: Turn3, _ x: Double, _ y: Double, _ z: Double, _ b: Double, _ dither: Double, size: Double = 1) {
            let p = turn.apply(x, y, z)
            guard p.z > -0.05 else { return }
            place(&d, p.x, p.y + oy, b, dither, phase: x, lum: 1, size: size)
        }
        let R = 0.86
        // The dome: panels of metal, the seams between them left open.
        for j in 0..<Int(1300 * k) + 60 {
            let el = asin(evenPoint(j).0), az = 2 * Double.pi * evenPoint(j).1
            let seamA = abs(el - 0.33) < 0.018 || abs(el - 0.9) < 0.018
            let inBand = el > 0.35 && el < 0.88
            let seamB = inBand && abs(sin(4 * az)) < 0.05
            if seamA || seamB { continue }
            let block = inBand && sin(4 * az + 0.6) > 0.2 && sin(2 * az) > -0.3
            let nx = cos(el) * sin(az), ny = -sin(el), nz = cos(el) * cos(az)
            surf(domeTurn, R * nx, R * ny, R * nz, nx, ny, nz, block ? 1.25 : 0.85, OrbPoints.hash(j, 14), shine: 0.9)
        }
        func onDome(_ el: Double, _ az: Double, _ out: Double = 1.012) -> (Double, Double, Double) {
            (R * out * cos(el) * sin(az), -R * out * sin(el), R * out * cos(el) * cos(az))
        }
        // The main eye: a dark lens in a bright rim, a glint; it lights with your voice.
        let eyeEl = 0.62
        for j in 0..<Int(140 * k) + 20 {
            let a = 2 * Double.pi * Double(j) / (140 * k + 20)
            for (r, b) in [(0.15, 0.9), (0.12, 0.45)] {
                let p = onDome(eyeEl + r * sin(a), r * cos(a) / cos(eyeEl))
                light(domeTurn, p.0, p.1, p.2, b + 0.6 * s.listen * s.level, OrbPoints.hash(j, r))
            }
        }
        for j in 0..<12 {
            let p = onDome(eyeEl + 0.04 + 0.02 * evenPoint(j).0, -0.04 + 0.03 * evenPoint(j).1, 1.02)
            light(domeTurn, p.0, p.1, p.2, 1.2, 0.5)
        }
        for j in 0..<30 {
            let a = 2 * Double.pi * Double(j) / 30
            let p = onDome(0.85 + 0.05 * sin(a), 0.55 + 0.05 * cos(a) / cos(0.85))
            light(domeTurn, p.0, p.1, p.2, 0.7, OrbPoints.hash(j, 4))
            let q = onDome(0.45 + 0.055 * sin(a), -1.25 + 0.055 * cos(a) / cos(0.45))
            light(domeTurn, q.0, q.1, q.2, 0.5 + 0.6 * s.busy, OrbPoints.hash(j, 6))
        }
        // Panels of lights under the eye.
        for panel in 0..<2 {
            let az0 = panel == 0 ? -0.42 : 0.36
            for c in 0..<4 {
                for r in 0..<3 {
                    let cell = panel * 12 + c * 3 + r
                    let tick = Int(t * (1.2 + 6 * s.speak))
                    var on = OrbPoints.hash(cell * 101 + tick, 7) < 0.45 ? 1.0 : 0.15
                    if s.speak > 0.05 { on = max(on * (1 - s.speak), s.spectrum.band(at: Double(c) / 3) > 0.3 + 0.2 * Double(r) ? 1 : 0.15) }
                    if s.th > 0.05 { on = max(on * (1 - s.th), Int(t * 10) % 12 == c * 3 + r ? 1 : 0.2) }
                    for q in 0..<4 {
                        let p = onDome(0.3 - 0.07 * Double(r) - 0.02 * Double(q / 2), az0 + 0.08 * Double(c) + 0.025 * Double(q % 2))
                        light(domeTurn, p.0, p.1, p.2, 0.15 + 0.9 * on, OrbPoints.hash(cell * 4 + q, 9))
                    }
                }
            }
        }
        if s.busy > 0.05 {
            let src = onDome(0.45, -1.25)
            let a = domeTurn.apply(src.0, src.1, src.2)
            let target = (x: -1.15, y: -0.6)
            for j in 0..<60 {
                let f = Double(j) / 59
                let spread = 0.12 * f * sin(Double(j) * 2.3)
                place(&d, a.x + (target.x - a.x) * f, a.y + oy + (target.y - a.y - oy) * f + spread, s.busy * 0.3, OrbPoints.hash(j, 12), phase: f)
            }
            for j in 0..<48 {
                let ang = 2 * Double.pi * Double(j) / 48 + t
                place(&d, target.x + 0.15 * cos(ang), target.y + 0.15 * sin(ang) * 0.45 - 0.05 * sin(t * 3), s.busy * 0.85, OrbPoints.hash(j, 13), phase: ang, lum: 1)
            }
        }
        // The body: a barrel, its seams and grooves left open, two recessed panels in front.
        for j in 0..<Int(1300 * k) + 60 {
            let az = 2 * Double.pi * evenPoint(j).0, y = 0.03 + 1.75 * evenPoint(j).1
            if abs(sin(6 * az)) < 0.04 { continue }                            // vertical seams
            if abs(y - 0.5) < 0.012 || abs(y - 0.98) < 0.012 || abs(y - 1.45) < 0.012 { continue }
            let front = abs(sin(az)) < 0.22
            let recess = front && ((y > 0.14 && y < 0.44 && az > .pi) || (y > 0.6 && y < 0.9 && az < .pi))
            let nx = sin(az), nz = cos(az)
            let fade = 1 - smoothstep(1.3, 1.78, y)
            surf(bodyTurn, R * nx, y, R * nz, nx, 0, nz, (recess ? 0.55 : 1.0) * fade, OrbPoints.hash(j, 14))
        }
        for j in 0..<Int(220 * k) + 20 {                                       // the collar: a bright band
            let az = 2 * Double.pi * Double(j) / (220 * k + 20)
            surf(bodyTurn, R * 1.01 * sin(az), 0.02, R * 1.01 * cos(az), sin(az), 0, cos(az), 1.6, OrbPoints.hash(j, 15), shine: 1.2)
        }
        // Legs: boxes at the sides, their front and outer faces.
        for side in [-1.0, 1.0] {
            for j in 0..<Int(320 * k) + 20 {
                let y = -0.05 + 1.85 * evenPoint(j).0, f = evenPoint(j).1
                let fade = 1 - smoothstep(1.3, 1.8, y)
                if OrbPoints.hash(j, 3) < 0.6 {
                    surf(bodyTurn, side * (1.0 + 0.2 * f), y, 0.14, 0, 0, 1, 0.9 * fade, OrbPoints.hash(j, 14))
                } else {
                    surf(bodyTurn, side * 1.2, y, -0.14 + 0.28 * f, side, 0, 0, 0.9 * fade, OrbPoints.hash(j, 14))
                }
            }
            for j in 0..<Int(160 * k) + 10 {                                   // the shoulder joint: a disc
                let a = 2 * Double.pi * evenPoint(j).0, r = 0.17 * evenPoint(j).1.squareRoot()
                surf(bodyTurn, side * 1.21, 0.2 + r * sin(a), r * cos(a), side, 0, 0.3, 1.2, OrbPoints.hash(j, 15), shine: 0.9)
            }
        }
        finish(&gc, d, tint: Color(hex: 0x5aa8ff))
    }

    // MARK: Valet

    /// A gilded humanoid robot, head and shoulders, solid polished metal: round glowing eyes, a small
    /// nose, a slot of a mouth, ear discs, a ribbed neck, plated shoulders. Listening, it cocks its
    /// head, eyes steady; thinking, it turns aside and looks up, its eyes flickering; working, a light
    /// scans across its eyes; speaking, its eyes and mouth glow with the voice and it talks with its
    /// whole head.
    func drawValet(_ gc: inout GraphicsContext, _ box: CGSize) {
        var d = dotCanvas(box)
        let s = RobotState(engine, work)
        let k = density(box)
        let yaw = 0.12 * sin(t * 0.27) + 0.35 * s.th + 0.12 * s.speak * sin(t * 1.3)
        let pitch = 0.04 * sin(t * 0.21) - 0.12 * s.th + 0.06 * s.speak * s.loud * sin(t * 5.2)
        let roll = 0.04 * sin(t * 0.19) + 0.2 * s.listen + 0.1 * s.speak * sin(t * 1.7)
        let head = Turn3(yaw: yaw, pitch: pitch, roll: roll), body = Turn3(yaw: 0.05 * sin(t * 0.2), pitch: 0.12)
        let hy = -0.42, hw = 0.56, hh = 0.68, hd = 0.52
        let scale = 1.12
        func surf(_ turn: Turn3, _ cy: Double, _ x: Double, _ y: Double, _ z: Double, _ nx: Double, _ ny: Double, _ nz: Double,
                  _ tone: Double, _ dither: Double, shine: Double = 1.1) {
            let n = turn.apply(nx, ny, nz)
            guard n.z > -0.02 else { return }
            let p = turn.apply(x, y - cy, z)
            place(&d, p.x * scale, (p.y + cy) * scale + 0.05, tone * metal(n.x, n.y, n.z, shine: shine), dither, phase: x, lum: 0.7,
                  size: 0.85 + 0.35 * smoothstep(-1, 1, p.z))
        }
        func light(_ x: Double, _ y: Double, _ z: Double, _ b: Double, _ dither: Double, size: Double = 1) {
            let p = head.apply(x, y - hy, z)
            guard p.z > -0.05 else { return }
            place(&d, p.x * scale, (p.y + hy) * scale + 0.05, b, dither, phase: x, lum: 1, size: size)
        }
        func front(_ x: Double, _ y: Double) -> Double {
            let ny = (y - hy) / hh, w = hw * (ny > 0 ? 1 - 0.25 * ny : 1)
            return hd * max(0, 1 - pow(x / w, 2) - ny * ny).squareRoot() + 0.012
        }
        // The head: polished metal (a soft sheen from the upper left), its seams left open.
        for j in 0..<Int(1500 * k) + 60 {
            let u = 1 - 2 * evenPoint(j).0, a = 2 * Double.pi * evenPoint(j).1
            let r = (1 - u * u).squareRoot()
            var nx = r * cos(a), ny = u, nz = r * sin(a)
            if abs(nx - 0.62) < 0.02 || abs(nx + 0.62) < 0.02 || abs(ny + 0.45) < 0.015 { continue }
            let w = ny > 0 ? 1 - 0.25 * ny : 1
            let x = hw * nx * w, y = hy + hh * ny, z = hd * nz
            // Recesses: the eye sockets and the mouth slot are darker.
            let socket = (pow((abs(x) - 0.21) / 0.13, 2) + pow((y + 0.47) / 0.12, 2)) < 1 && nz > 0.4
            let slot = abs(x) < 0.15 && abs(y + 0.13) < 0.04 && nz > 0.4
            if socket || slot { nz *= 0.6 }
            surf(head, hy, x, y, z, nx, ny, nz, socket || slot ? 0.4 : 1, OrbPoints.hash(j, 14))
        }
        // The eyes: lit lenses in rims (brighter as it speaks, flickering as it thinks, scanned as it works).
        let flicker = 1 - 0.35 * s.th * (0.5 + 0.5 * sin(t * 13))
        let eyeGlow = (0.7 + 0.6 * s.speak * min(1, 1.5 * s.loud) + 0.2 * s.listen) * flicker
        let scan = sin(t * 3)
        for side in [-1.0, 1.0] {
            let ex = side * 0.21, ey = -0.47
            for j in 0..<Int(90 * k) + 14 {
                let a = 2 * Double.pi * Double(j) / (90 * k + 14)
                light(ex + 0.105 * cos(a), ey + 0.095 * sin(a), front(ex, ey), 0.7, OrbPoints.hash(j, side))
            }
            for j in 0..<Int(90 * k) + 12 {
                let a = 2 * Double.pi * evenPoint(j).0, r = 0.07 * evenPoint(j).1.squareRoot()
                let x = ex + r * cos(a), y = ey + r * sin(a)
                let b = eyeGlow * (0.55 + 0.6 * (1 - r / 0.07)) + s.busy * exp(-pow((x - ex - 0.05 * scan) / 0.012, 2))
                light(x, y, front(ex, ey) + 0.01, b, OrbPoints.hash(j, 14))
            }
        }
        let open = 0.012 + 0.028 * s.speak * min(1, 1.5 * s.loud)
        for j in 0..<Int(70 * k) + 10 {
            let f = 2 * evenPoint(j).0 - 1
            light(0.13 * f, -0.13 + (evenPoint(j).1 - 0.5) * 2 * open, front(0.13 * f, -0.13), 0.15 + 0.9 * s.speak * s.loud, OrbPoints.hash(j, 5))
        }
        for side in [-1.0, 1.0] {                                              // ear discs
            for j in 0..<Int(120 * k) + 10 {
                let a = 2 * Double.pi * evenPoint(j).0, r = 0.12 * evenPoint(j).1.squareRoot()
                surf(head, hy, side * (hw + 0.012), -0.42 + r * sin(a), r * cos(a), side, 0, 0.25, abs(r - 0.075) < 0.008 ? 0.4 : 1.1, OrbPoints.hash(j, 14))
            }
        }
        // The neck: ribbed (grooves left open).
        for j in 0..<Int(320 * k) + 20 {
            let a = 2 * Double.pi * evenPoint(j).0, y = 0.15 + 0.34 * evenPoint(j).1
            if abs(sin(y * 95)) < 0.25 { continue }
            surf(body, 0, 0.17 * sin(a), y, 0.17 * cos(a), sin(a), 0, cos(a), 0.85, OrbPoints.hash(j, 14))
        }
        // Shoulders and chest: the top of a broad plated shell, a collar, a round plate in the middle.
        for j in 0..<Int(1100 * k) + 40 {
            let u = evenPoint(j).0, a = 2 * Double.pi * evenPoint(j).1
            let el = 0.15 + 1.25 * u                                            // from the side up to the top
            let nx = cos(el) * cos(a), ny = -sin(el), nz = cos(el) * sin(a)
            let x = 1.45 * nx, y = 1.45 + 0.95 * ny, z = 0.6 * nz
            guard y > 0.48, y < 1.9 else { continue }
            if abs(abs(x) - 0.62) < 0.015 { continue }                         // plate seams
            let collar = abs(x) < 0.34 && y < 0.6
            surf(body, 0, x, y, z, nx, ny * 1.4, nz, (collar ? 1.4 : 0.9) * (1 - smoothstep(1.35, 1.85, y)), OrbPoints.hash(j, 14))
        }
        for j in 0..<Int(90 * k) + 10 {
            let a = 2 * Double.pi * evenPoint(j).0, r = 0.11 * evenPoint(j).1.squareRoot()
            let p = body.apply(r * cos(a), 0.95 + r * sin(a), 0.62)
            place(&d, p.x * scale, p.y * scale + 0.05, 0.35 + 0.6 * s.busy * (Int(t * 4) % 2 == 0 ? 1 : 0.3) + 0.3 * s.speak * s.loud,
                  OrbPoints.hash(j, 16), phase: a, lum: 1)
        }
        finish(&gc, d, tint: Color(hex: 0xf0bd52))
    }

    // MARK: Retro

    /// A robot of the fifties, solid: a glass dome (only its rim and reflections show) with its works
    /// turning inside, antennae with discs, a face plate with a grille of lights, a barrel chest with
    /// grooves and dials. Listening, the discs spin fast and the works pulse with your voice; thinking,
    /// the works spin and the grille runs a chase; working, the chest's dials swing and its lights
    /// blink; speaking, the grille's columns light with the voice's bands.
    func drawRetro(_ gc: inout GraphicsContext, _ box: CGSize) {
        var d = dotCanvas(box)
        let s = RobotState(engine, work)
        let k = density(box)
        let turn = Turn3(yaw: 0.12 * sin(t * 0.23), pitch: 0.15)
        let oy = -0.08
        func surf(_ x: Double, _ y: Double, _ z: Double, _ nx: Double, _ ny: Double, _ nz: Double, _ tone: Double, _ dither: Double, shine: Double = 0.7) {
            let n = turn.apply(nx, ny, nz)
            guard n.z > -0.02 else { return }
            let p = turn.apply(x, y, z)
            place(&d, p.x, p.y + oy, tone * metal(n.x, n.y, n.z, shine: shine), dither, phase: x, lum: 0.6, size: 0.85 + 0.35 * smoothstep(-1, 1, p.z))
        }
        func light(_ x: Double, _ y: Double, _ z: Double, _ b: Double, _ dither: Double, size: Double = 1) {
            let p = turn.apply(x, y, z)
            place(&d, p.x, p.y + oy, b, dither, phase: x, lum: 1, size: size)
        }
        // The glass dome: its rim (where glass is seen edge on) and two reflections.
        let dc = (x: 0.0, y: -0.48), dr = 0.64
        for j in 0..<Int(900 * k) + 40 {
            let el = asin(evenPoint(j).0), az = 2 * Double.pi * evenPoint(j).1
            let nx = cos(el) * sin(az), ny = -sin(el), nz = cos(el) * cos(az)
            let n = turn.apply(nx, ny, nz)
            let edge = pow(1 - abs(n.z), 3)
            let reflect = exp(-pow((n.x + 0.45) / 0.12, 2) - pow((n.y + 0.5) / 0.25, 2)) + 0.5 * exp(-pow((n.x - 0.55) / 0.06, 2) - pow((n.y + 0.2) / 0.3, 2))
            let b = 0.55 * edge + 0.9 * reflect
            guard b > 0.06 else { continue }
            light(dc.x + dr * nx, dc.y + dr * ny, dr * nz, b, OrbPoints.hash(j, 14))
        }
        // The works inside: two gyro rings and a core.
        let spin = engine.ringTurn * 3 + t * (0.6 + 2.5 * s.listen * s.level)
        for (n, (r, tilt)) in [(0.22, 0.4), (0.16, -0.9)].enumerated() {
            let ct = cos(tilt + Double(n) * spin * 0.3), st = sin(tilt + Double(n) * spin * 0.3)
            for j in 0..<Int(90 * k) + 14 {
                let a = 2 * Double.pi * Double(j) / (90 * k + 14) + spin * (n == 0 ? 1 : -1.3)
                let z = r * sin(a) * st
                light(r * cos(a), -0.82 + r * sin(a) * ct, z, z > 0 ? 0.75 : 0.25, OrbPoints.hash(j, Double(n)))
            }
        }
        for j in 0..<30 {
            let a = 2 * Double.pi * evenPoint(j).0, r = 0.05 * evenPoint(j).1
            light(r * cos(a), -0.82 + r * sin(a), 0, 0.6 + 0.8 * s.listen * s.level + 0.5 * s.th, OrbPoints.hash(j, 3))
        }
        // The dome's collar: a metal band.
        for j in 0..<Int(260 * k) + 20 {
            let az = 2 * Double.pi * evenPoint(j).0, y = -0.48 + 0.07 * evenPoint(j).1
            surf(0.68 * sin(az), y, 0.68 * cos(az), sin(az), 0, cos(az), 1.2, OrbPoints.hash(j, 14), shine: 1)
        }
        // The antennae: rods and discs.
        let discSpin = t * (1.4 + 9 * s.listen + 3 * s.speak + 4 * s.th)
        for side in [-1.0, 1.0] {
            let base = (x: side * 0.62, y: -0.72), tip = (x: side * 0.98, y: -1.0)
            for j in 0..<30 {
                let f = Double(j) / 29
                surf(base.x + (tip.x - base.x) * f, base.y + (tip.y - base.y) * f, 0, 0, -0.3, 1, 0.9, OrbPoints.hash(j, side + 3))
            }
            for j in 0..<Int(120 * k) + 10 {
                let a = 2 * Double.pi * evenPoint(j).0, r = 0.16 * evenPoint(j).1.squareRoot()
                let c = cos(discSpin * side)
                surf(tip.x + r * cos(a) * c, tip.y + r * sin(a), r * cos(a) * sin(discSpin * side), c, 0, abs(sin(discSpin * side)) + 0.2,
                     abs(r - 0.1) < 0.01 ? 0.4 : 1.0, OrbPoints.hash(j, side + 5))
            }
        }
        // The face plate: a broad shaped plate with its grille of lights.
        for j in 0..<Int(700 * k) + 30 {
            let a = 2 * Double.pi * evenPoint(j).0, r = evenPoint(j).1.squareRoot()
            let x = 0.52 * r * cos(a), y = -0.19 + 0.21 * r * sin(a)
            let nz = (1 - r * r).squareRoot() * 0.8 + 0.2
            if abs(x) < 0.42 && abs(y + 0.19) < 0.13 { continue }             // the grille's recess
            surf(x, y, 0.62 + 0.08 * nz, cos(a) * r * 0.6, sin(a) * r * 0.6, nz, 0.9, OrbPoints.hash(j, 14))
        }
        let columns = 7
        for c in 0..<columns {
            let cx = -0.36 + 0.12 * Double(c)
            let voice = s.speak * min(1, 1.6 * s.spectrum.band(at: Double(c) / Double(columns - 1)) + 0.3 * s.loud)
            let chase = s.th * (Int(t * 8) % columns == c ? 1 : 0.1)
            for r in 0..<3 {
                let on = 0.1 + (voice > Double(r) / 2 * 0.8 ? 0.9 * voice : 0) + chase + 0.06 * sin(t * 0.8 + Double(c))
                for q in 0..<6 {
                    light(cx + 0.022 * Double(q % 2), -0.28 + 0.09 * Double(r) + 0.022 * Double(q / 2), 0.66, on, OrbPoints.hash(c * 18 + r * 6 + q, 11))
                }
            }
        }
        // The chest: a barrel, its grooves left open; three dials and their lamps.
        func chestWidth(_ y: Double) -> Double { 1.0 + 0.25 * sin(min(1, (y - 0.1) / 1.2) * .pi * 0.9) }
        for j in 0..<Int(1500 * k) + 60 {
            let y = 0.12 + 1.65 * evenPoint(j).0, az = Double.pi * (evenPoint(j).1 - 0.5) * 1.15
            if abs(sin(y * 35)) < 0.18 { continue }                             // the grooves
            let w = chestWidth(y)
            let nx = sin(az), nz = cos(az)
            let fade = 1 - smoothstep(1.3, 1.78, y)
            surf(w * nx, y, 0.62 * w * nz, nx, 0, nz, 0.8 * fade, OrbPoints.hash(j, 14))
        }
        for (n, dx) in [-0.3, 0.0, 0.3].enumerated() {
            for j in 0..<30 {
                let a = 2 * Double.pi * Double(j) / 30
                light(dx + 0.085 * cos(a), 0.55 + 0.085 * sin(a), 0.66, 0.55, OrbPoints.hash(j, Double(n) + 20))
            }
            let needle = 0.8 * sin(t * (0.7 + 0.4 * Double(n)) + Double(n)) + 1.4 * s.busy * sin(t * 6 + Double(n))
            for j in 0..<9 { light(dx + 0.009 * Double(j) * sin(needle), 0.55 - 0.009 * Double(j) * cos(needle), 0.67, 0.8, 0.5) }
            let blink = s.busy > 0.05 ? (Int(t * 5 + Double(n)) % 2 == 0 ? 1.0 : 0.15) : 0.3
            for j in 0..<8 {
                let a = Double(j)
                light(dx + 0.025 * cos(a), 0.8 + 0.025 * sin(a), 0.66, 0.2 + 0.9 * blink, OrbPoints.hash(j, Double(n) + 30))
            }
        }
        finish(&gc, d, tint: Color(hex: 0x5be3b4))
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

    /// A little rover, solid: two binocular eyes (boxes with lenses) on a neck over a boxy body on
    /// tracks, seen a little from the side. Its eyes do the talking: listening, they lift, lean in and
    /// tilt toward each other, lenses wide; thinking, they look one way then the other, zoom rings
    /// turning; working, a light scans across the lenses and its tracks roll; speaking, its lenses
    /// pulse with the voice and its eyes bob.
    func drawRover(_ gc: inout GraphicsContext, _ box: CGSize) {
        var d = dotCanvas(box)
        let s = RobotState(engine, work)
        let k = density(box)
        let view = Turn3(yaw: 0.32 + 0.06 * sin(t * 0.2), pitch: 0.16)
        let lift = -0.12 * s.listen + 0.04 * s.speak * min(1, 1.5 * s.loud) * sin(t * 6) + 0.015 * sin(t * 0.9)
        let look = 0.06 * sin(t * 0.35) * (1 - s.th) + s.th * 0.1 * (sin(t * 0.9) > 0 ? 1 : -1)
        let aperture = 0.1 + 0.035 * s.listen - 0.025 * s.speak * min(1, 1.5 * s.loud) + 0.01 * sin(t * 0.7)
        let zoom = engine.ringTurn * 4
        let scan = sin(t * 2.6)
        let sc = 1.05, oy = 0.1
        func surf(_ x: Double, _ y: Double, _ z: Double, _ nx: Double, _ ny: Double, _ nz: Double, _ tone: Double, _ dither: Double, shine: Double = 0.5) {
            let n = view.apply(nx, ny, nz)
            guard n.z > -0.02 else { return }
            let p = view.apply(x, y, z)
            place(&d, p.x * sc, p.y * sc + oy, tone * metal(n.x, n.y, n.z, shine: shine), dither, phase: x, lum: 0.6, size: 0.85 + 0.35 * smoothstep(-1, 1, p.z))
        }
        func light(_ x: Double, _ y: Double, _ z: Double, _ b: Double, _ dither: Double) {
            let p = view.apply(x, y, z)
            place(&d, p.x * sc, p.y * sc + oy, b, dither, phase: x, lum: 1)
        }
        /// Points over a box's three faces we see (front, top, the right side), seams left open.
        func boxSurface(_ cx: Double, _ cy: Double, _ cz: Double, _ w: Double, _ h: Double, _ dpt: Double, _ count: Int, seed: Int,
                        tone: Double, fade: Bool = false, tilt: Double = 0) {
            let ct = cos(tilt), st = sin(tilt)
            for j in 0..<count {
                let f = evenPoint(seed + j).0, g = evenPoint(seed + j).1, face = OrbPoints.hash(seed + j, 3)
                var x: Double, y: Double, z: Double, nx: Double, ny: Double, nz: Double
                if face < 0.55 { x = (f - 0.5) * w; y = (g - 0.5) * h; z = dpt / 2; nx = 0; ny = 0; nz = 1 }
                else if face < 0.8 { x = (f - 0.5) * w; y = -h / 2; z = (g - 0.5) * dpt; nx = 0; ny = -1; nz = 0 }
                else { x = w / 2; y = (f - 0.5) * h; z = (g - 0.5) * dpt; nx = 1; ny = 0; nz = 0 }
                let rx = x * ct - y * st, ry = x * st + y * ct
                let rnx = nx * ct - ny * st, rny = nx * st + ny * ct
                let fadeY = fade ? 1 - smoothstep(1.35, 1.85, cy + ry) : 1
                surf(cx + rx, cy + ry, cz + z, rnx, rny, nz, tone * fadeY, OrbPoints.hash(seed + j, 14))
            }
        }
        for side in [-1.0, 1.0] {
            let tilt = side * (-0.08 * (1 - s.listen) * (1 - s.th) + 0.22 * s.listen) + s.th * 0.18 * sin(t * 0.9 + side)
            let ex = side * 0.43, ey = -0.6 + lift, ez = 0.0
            boxSurface(ex, ey, ez, 0.56, 0.44, 0.42, Int(700 * k) + 40, seed: side > 0 ? 1000 : 3000, tone: 0.75, tilt: tilt)
            let ct = cos(tilt), st = sin(tilt)
            func eye(_ x: Double, _ y: Double, _ b: Double, _ dither: Double) {
                light(ex + x * ct - y * st, ey + x * st + y * ct, ez + 0.215, b, dither)
            }
            // The lens: a dark well in rims, a zoom ring turning as it thinks, the aperture, a glint.
            let lx = look * 0.6
            for (r, b) in [(0.185, 0.85), (0.155, 0.35)] {
                for j in 0..<Int(90 * k) + 14 {
                    let a = 2 * Double.pi * Double(j) / (90 * k + 14)
                    let dash = r == 0.155 ? (sin(9 * a + zoom * side) > 0 ? 1.0 : 0.3) : 1
                    eye(lx + r * cos(a), r * sin(a), b * dash, OrbPoints.hash(j, r + side))
                }
            }
            for j in 0..<Int(60 * k) + 12 {
                let a = 2 * Double.pi * Double(j) / (60 * k + 12)
                eye(lx + aperture * cos(a), aperture * sin(a), 0.8 + 0.5 * s.speak * s.loud + 0.4 * s.listen * s.level, OrbPoints.hash(j, side + 9))
            }
            for j in 0..<16 {
                let a = 2 * Double.pi * evenPoint(j).0, r = 0.03 * evenPoint(j).1
                eye(lx + r * cos(a), r * sin(a), 0.45 + 0.6 * s.speak * s.loud, 0.5)
                eye(lx - 0.07 + r * 0.6 * cos(a), -0.08 + r * 0.6 * sin(a), 1.1, 0.5)
            }
            if s.busy > 0.05 {
                for j in 0..<16 {
                    let f = Double(j) / 15 - 0.5
                    eye(lx + 0.15 * scan, 0.3 * f, s.busy * 0.8 * (1 - abs(f) * 1.6), 0.5)
                }
            }
        }
        // The neck, its joint; the body (a box) with a lamp; the tracks.
        boxSurface(0, -0.2 + lift / 2, 0, 0.1, 0.75 - lift, 0.1, Int(160 * k) + 10, seed: 5000, tone: 0.8)
        boxSurface(0, 1.05, 0, 1.9, 1.45, 1.1, Int(1500 * k) + 60, seed: 6000, tone: 0.7, fade: true)
        let lamp = s.busy > 0.05 ? (Int(t * 4) % 2 == 0 ? 1.0 : 0.2) : 0.3 + 0.15 * sin(t)
        for j in 0..<24 {
            let a = 2 * Double.pi * evenPoint(j).0, r = 0.05 * evenPoint(j).1.squareRoot()
            light(-0.7 + r * cos(a), 0.55 + r * sin(a), 0.56, lamp, 0.5)
        }
        let roll = (t * (0.4 + 2 * s.busy + 1.2 * s.speak * s.loud)).truncatingRemainder(dividingBy: 1)
        for side in [-1.0, 1.0] {
            for j in 0..<Int(600 * k) + 30 {
                let f = evenPoint(j).0, g = evenPoint(j).1
                let y = 1.0 + 0.75 * g
                let half = 0.14 + 0.13 * g
                let x = side * (1.13 + (f - 0.5) * 2 * half)
                let cleat = abs(sin((g * 6 + roll * side) * .pi * 2)) < 0.15
                if cleat { continue }
                surf(x, y, 0.3, 0, 0, 1, 0.75 * (1 - smoothstep(1.4, 1.8, y)), OrbPoints.hash(j, 14 + side))
            }
        }
        finish(&gc, d, tint: Color(hex: 0xffb347))
    }

}
