import SwiftUI

// Six robots, each a classic way of picturing a machine that talks, drawn in its own colour:
// Lens (a warm glowing camera eye), Dome (a dome-headed droid with lights), Valet (a gilded
// humanoid head), Retro (a glass-domed robot with a voice grille), Deco (an art-deco machine woman
// with rings of light) and Rover (two binocular eyes on a neck). Each is smooth lit metal (soft
// gradient fills, lit from the upper left) under a fine texture of points, with round warm eyes
// and lamps that glow; each shows the five states: at rest, listening, speaking, thinking, and
// working (tools running). Every motion runs at a fixed pace (a phase changes how much of a motion
// shows, never its speed), so a change of state is a smooth morph. Units as the planet (1 = its
// radius, y down), each robot drawn larger so it fills the frame.

/// What the robot is doing now, from the engine and the work. Shared with OrbMachines.swift, as are
/// `Turn3`, `Ink`, `density`, `robotCanvas` and `robotPalette` (their signatures stay).
struct RobotState {
    let th: Double, listen: Double, speak: Double, loud: Double, level: Double, busy: Double
    let spectrum: VoiceFeatures
    /// The voice's strength while it speaks (0 otherwise).
    var voice: Double { speak * min(1, 1.5 * loud) }
    init(_ engine: OrbEngine, _ work: OrbWork) {
        let p = OrbPhases(engine)
        th = p.think; listen = p.listen; speak = p.speak; busy = p.work
        loud = p.loud; level = p.level; spectrum = p.spectrum
    }
}

/// A turn about the vertical axis (yaw), then a tilt toward the viewer (pitch), then a lean (roll).
struct Turn3 {
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

/// Metal lit from the upper left in front: a matte part and a highlight (`shine`: its strength).
@inline(__always) private func metal(_ nx: Double, _ ny: Double, _ nz: Double, shine: Double = 0.6) -> Double {
    let lx = -0.48, ly = -0.55, lz = 0.68
    let diffuse = max(0, nx * lx + ny * ly + nz * lz)
    let hx = lx, hy = ly, hz = lz + 1, hl = (hx * hx + hy * hy + hz * hz).squareRoot()
    let spec = pow(max(0, (nx * hx + ny * hy + nz * hz) / hl), 22)
    return 0.1 + 0.55 * diffuse + shine * spec
}

@inline(__always) private func fract(_ x: Double) -> Double { x - x.rounded(.down) }

/// A slow, soft blink every few seconds (1 open … 0 shut), at a fixed pace.
@inline(__always) private func blink(_ t: Double, _ period: Double = 5.3) -> Double {
    let f = fract(t / period)
    return 1 - 0.9 * exp(-pow((f - 0.5) / 0.012, 2))
}

/// Smooth light under a robot's points: lit metal, glowing eyes and lamps (a few fills per part).
struct Ink {
    let cx: Double, cy: Double, R: Double, px: Double
    let pal: [Color]
    init(_ d: DotCanvas, _ pal: [Color]) { cx = d.cx; cy = d.cy; R = d.R; px = d.px; self.pal = pal }
    func p(_ x: Double, _ y: Double) -> CGPoint { CGPoint(x: cx + x * R, y: cy + y * R) }
    func circle(_ x: Double, _ y: Double, _ r: Double) -> Path {
        Path(ellipseIn: CGRect(x: cx + (x - r) * R, y: cy + (y - r) * R, width: 2 * r * R, height: 2 * r * R))
    }
    /// An ellipse at (x, y) of radii (rx, ry), its x axis turned by `angle`.
    func oval(_ x: Double, _ y: Double, _ rx: Double, _ ry: Double, angle: Double = 0) -> Path {
        let base = Path(ellipseIn: CGRect(x: -rx * R, y: -ry * R, width: 2 * rx * R, height: 2 * ry * R))
        let move = CGAffineTransform(rotationAngle: angle).concatenating(CGAffineTransform(translationX: cx + x * R, y: cy + y * R))
        return base.applying(move)
    }
    func poly(_ pts: [(Double, Double)], closed: Bool = true) -> Path {
        var path = Path()
        path.addLines(pts.map { p($0.0, $0.1) })
        if closed { path.closeSubpath() }
        return path
    }
    /// Metal lit from the upper left: brightest at `hi`, its light falling off over `reach` to `floor`
    /// (0: it fades out entirely, a body that ends in the dark).
    func metal(_ gc: inout GraphicsContext, _ path: Path, hi: (Double, Double), reach: Double, _ s: Double, floor: Double = 0.3) {
        let g = Gradient(stops: [
            .init(color: pal[4].opacity(0.34 * s), location: 0),
            .init(color: pal[3].opacity(0.3 * s), location: 0.16),
            .init(color: pal[2].opacity(0.22 * s), location: 0.42),
            .init(color: pal[1].opacity(0.15 * s), location: 0.72),
            .init(color: pal[0].opacity(0.22 * floor * s), location: 1)])
        gc.fill(path, with: .radialGradient(g, center: p(hi.0, hi.1), startRadius: 0, endRadius: reach * R))
    }
    /// Flat metal: one face of a box, its light from top to bottom.
    func face(_ gc: inout GraphicsContext, _ path: Path, top: (Double, Double), bottom: (Double, Double), _ light: Double) {
        let g = Gradient(colors: [pal[3].opacity(min(1, 0.5 * light)), pal[2].opacity(min(1, 0.32 * light)), pal[1].opacity(min(1, 0.2 * light))])
        gc.fill(path, with: .linearGradient(g, startPoint: p(top.0, top.1), endPoint: p(bottom.0, bottom.1)))
    }
    func rim(_ gc: inout GraphicsContext, _ path: Path, _ alpha: Double, width: Double = 1) {
        guard alpha > 0.01 else { return }
        gc.stroke(path, with: .color(pal[3].opacity(min(1, alpha))), lineWidth: px * width)
    }
    /// A soft glow: a disc of light fading out.
    func glow(_ gc: inout GraphicsContext, _ x: Double, _ y: Double, _ r: Double, _ color: Color, _ a: Double) {
        guard a > 0.01 else { return }
        let g = Gradient(stops: [.init(color: color.opacity(min(1, a)), location: 0),
                                 .init(color: color.opacity(min(1, a) * 0.3), location: 0.45), .init(color: .clear, location: 1)])
        gc.fill(circle(x, y, r), with: .radialGradient(g, center: p(x, y), startRadius: 0, endRadius: r * R))
    }
    /// A round eye or lamp lit from within: a halo, a warm iris brightest at its centre, a catchlight.
    /// `squash`: its width over its height (turned away), along `angle`; `open`: its lid (1 open).
    func eye(_ gc: inout GraphicsContext, _ x: Double, _ y: Double, _ r: Double, _ b: Double, warm: Color, deep: Color,
             squash: Double = 1, angle: Double = 0, open: Double = 1, halo: Double = 1, catchlight: Double = 1) {
        guard b > 0.01, squash > 0.03 else { return }
        glow(&gc, x, y, r * 2.4, warm, 0.3 * b * halo * squash)
        let iris = Gradient(stops: [
            .init(color: Color.white.opacity(min(1, 0.95 * b)), location: 0),
            .init(color: warm.opacity(min(1, 0.95 * b)), location: 0.36),
            .init(color: deep.opacity(min(1, 0.7 * b)), location: 0.8),
            .init(color: deep.opacity(min(1, 0.4 * b)), location: 1)])
        let path = oval(x, y, r * squash, r * max(0.06, open), angle: angle)
        gc.fill(path, with: .radialGradient(iris, center: p(x, y), startRadius: 0, endRadius: r * R))
        gc.stroke(path, with: .color(warm.opacity(min(1, 0.6 * b))), lineWidth: px * 0.9)
        if catchlight > 0.01, open > 0.5 {
            gc.fill(circle(x - 0.3 * r * squash, y - 0.34 * r * open, 0.19 * r), with: .color(.white.opacity(min(0.85, 0.75 * catchlight))))
        }
    }
    /// A soft ring of light (no hard line): a band of `width` round (x, y) at radius `r`.
    func halo(_ gc: inout GraphicsContext, _ x: Double, _ y: Double, _ r: Double, width: Double, _ color: Color, _ a: Double) {
        guard a > 0.01, r > 0.01 else { return }
        let outer = r + width, inner = max(0, r - width) / outer, mid = r / outer
        let g = Gradient(stops: [.init(color: .clear, location: inner), .init(color: color.opacity(min(1, a)), location: mid),
                                 .init(color: .clear, location: 1)])
        gc.fill(circle(x, y, outer), with: .radialGradient(g, center: p(x, y), startRadius: 0, endRadius: outer * R))
    }
}

extension OrbCanvas {
    /// Scales a part's point count to the orb's size (a small tile draws fewer).
    func density(_ box: CGSize) -> Double { Double(pointBudget(box)) / 1820 }

    /// The robot's canvas: the planet's units scaled by `scale` (a robot fills more of the frame than
    /// the planet), its centre moved down by `dy` (in halves of the frame).
    func robotCanvas(_ box: CGSize, scale: Double, dy: Double = 0) -> DotCanvas {
        let half = Double(min(box.width, box.height)) / 2
        return DotCanvas(cx: Double(box.width) / 2, cy: Double(box.height) / 2 + dy * half, R: half * 0.46 * scale, px: max(0.55, half / 95))
    }

    /// The robot's palette (an entity's colour wins).
    func robotPalette(_ tint: Color) -> [Color] { OrbPalette.colors(for: look.color ?? tint) }

    // MARK: Lens

    /// A camera eye, warm and calm: a brushed metal bezel round deep amber-red glass, a soft glowing
    /// core and a fine iris of light, a reflection on the glass. It breathes at rest; speaking, its
    /// core swells with the voice and soft waves of light leave it; listening, the waves come in and
    /// it brightens with your voice; thinking, the glow dims and a soft light sweeps round the
    /// glass; working, a light runs round the bezel.
    func drawLens(_ gc: inout GraphicsContext, _ box: CGSize) {
        var d = dotCanvas(box)
        let s = RobotState(engine, work)
        let k = density(box)
        let half = Double(min(box.width, box.height)) / 2
        let z = half * 0.86 / d.R                                        // the bezel's outer radius, in units
        let custom = look.color
        let warm = custom ?? Color(hex: 0xffb24d), ember = custom ?? Color(hex: 0xff6a3d), deep = custom ?? Color(hex: 0xc2301f)
        let pal = custom.map { OrbPalette.colors(for: $0) }
            ?? [Color(hex: 0x7a1a12).opacity(0.5), Color(hex: 0xb8321f).opacity(0.62), Color(hex: 0xf06a3a).opacity(0.76),
                Color(hex: 0xffa95a).opacity(0.88), Color(hex: 0xfff0d2)]
        let ink = Ink(d, pal)
        let breathe = 0.5 + 0.5 * sin(t * 1.1)
        let core = 0.72 + 0.1 * breathe + 0.45 * s.voice + 0.35 * s.listen * (0.3 + s.level) + 0.1 * s.busy - 0.32 * s.th
        let glass = 0.86 * z
        // A soft warm presence round the lens.
        ink.halo(&gc, 0, 0, 1.0 * z, width: 0.14 * z, ember, 0.16 * core)
        // The bezel: brushed metal lit from the upper left (its light round the ring, no ticks).
        let lightA = 1.25 * Double.pi
        let bezelStops = (0...18).map { j -> Gradient.Stop in
            let a = 2 * Double.pi * Double(j) / 18
            let lit = 0.5 + 0.5 * cos(a - lightA)
            return .init(color: Color(hex: 0xffe9dc).opacity(0.07 + 0.4 * pow(lit, 2.2)), location: Double(j) / 18)
        }
        let conic = GraphicsContext.Shading.conicGradient(Gradient(stops: bezelStops), center: ink.p(0, 0), angle: .zero)
        gc.stroke(ink.circle(0, 0, 0.925 * z), with: conic, lineWidth: 0.12 * z * d.R)
        gc.stroke(ink.circle(0, 0, 0.99 * z), with: conic, lineWidth: d.px * 1.1)
        gc.stroke(ink.circle(0, 0, 0.862 * z), with: conic, lineWidth: d.px * 0.9)
        // Working: a light running round the bezel.
        if s.busy > 0.01 {
            let head = fract(t * 0.45)
            let stops: [Gradient.Stop] = [.init(color: .clear, location: 0), .init(color: .clear, location: max(0, head - 0.16)),
                                          .init(color: warm.opacity(0.7 * s.busy), location: head), .init(color: .clear, location: min(1, head + 0.01))]
            gc.stroke(ink.circle(0, 0, 0.925 * z), with: .conicGradient(Gradient(stops: stops), center: ink.p(0, 0), angle: .zero),
                      lineWidth: 0.1 * z * d.R)
        }
        // The glass: deep red round a soft warm core (wider as it speaks, gathered in as it listens).
        let spread = 0.92 + 0.16 * s.voice - 0.1 * s.listen + 0.04 * breathe - 0.08 * s.th
        let glassStops: [Gradient.Stop] = [
            .init(color: Color(hex: 0xfff4dc).opacity(min(1, 0.95 * core)), location: 0),
            .init(color: warm.opacity(min(1, 0.9 * core)), location: 0.1 * spread),
            .init(color: ember.opacity(min(1, 0.7 * core)), location: 0.26 * spread),
            .init(color: deep.opacity(min(1, 0.48 * core)), location: 0.52 * spread),
            .init(color: deep.opacity(0.2 + 0.08 * core), location: 0.82),
            .init(color: deep.opacity(0.12), location: 1)]
        gc.fill(ink.circle(0, 0, glass), with: .radialGradient(Gradient(stops: glassStops), center: ink.p(0, 0), startRadius: 0, endRadius: glass * d.R))
        // Soft waves of light: out with its words, in with yours.
        for n in 0..<3 {
            let f = fract(t * 0.42 + Double(n) / 3)
            let out = s.speak * (0.12 + 0.55 * engine.history.value(secondsAgo: f * 1.2)) * sin(Double.pi * f)
            ink.halo(&gc, 0, 0, glass * (0.18 + 0.78 * f), width: 0.09 * z, warm, out)
            let into = s.listen * (0.1 + 0.6 * s.level) * sin(Double.pi * f)
            ink.halo(&gc, 0, 0, glass * (0.96 - 0.78 * f), width: 0.09 * z, warm, into)
        }
        // The iris: fine fibres of light round the core, turning very slowly.
        let fibres = 56
        for j in 0..<Int(640 * k) + 40 {
            let h1 = OrbPoints.hash(j, 41), h2 = OrbPoints.hash(j, 42), h3 = OrbPoints.hash(j, 43)
            let a = 2 * Double.pi * (Double(Int(h1 * Double(fibres))) + 0.35 * h3) / Double(fibres) + 0.03 * t
            let rr = 0.12 + 0.5 * h2.squareRoot()
            let r = rr * glass
            let b = (0.12 + 0.75 * pow(1 - rr, 1.6)) * core * (0.8 + 0.2 * sin(t * 0.7 + h3 * 6))
            var x = r * cos(a), y = r * sin(a)
            let light = workEffect(&x, &y, phase: a)
            d.dot(x, y, (b + 0.6 * light) * countdownDim(x / (glass * 1.05), y / (glass * 1.05)), OrbPoints.hash(j, 44), size: 0.8)
        }
        // The core: a soft hot centre.
        ink.glow(&gc, 0, 0, glass * (0.2 + 0.08 * s.voice), Color(hex: 0xfff4dc), 0.7 * core)
        // Thinking: a soft light sweeping round the glass.
        if s.th > 0.01 {
            let head = fract(t * 0.3)
            let stops: [Gradient.Stop] = [.init(color: .clear, location: 0), .init(color: .clear, location: max(0, head - 0.3)),
                                          .init(color: warm.opacity(0.55 * s.th), location: head), .init(color: .clear, location: min(1, head + 0.02))]
            let sweep = GraphicsContext.Shading.conicGradient(Gradient(stops: stops), center: ink.p(0, 0), angle: .zero)
            gc.stroke(ink.circle(0, 0, 0.7 * glass), with: sweep, lineWidth: 0.16 * z * d.R)
            gc.stroke(ink.circle(0, 0, 0.7 * glass), with: sweep, lineWidth: 0.03 * z * d.R)
        }
        // The reflection: a soft pale crescent on the glass, upper left, and a glint.
        let shine = Gradient(colors: [Color.white.opacity(0.2), Color.white.opacity(0.05), .clear])
        gc.fill(ink.oval(-0.36 * glass, -0.44 * glass, 0.32 * glass, 0.13 * glass, angle: -0.72),
                with: .linearGradient(shine, startPoint: ink.p(-0.5 * glass, -0.62 * glass), endPoint: ink.p(-0.2 * glass, -0.24 * glass)))
        ink.glow(&gc, -0.5 * glass, -0.22 * glass, 0.05 * glass, .white, 0.55)
        finish(&gc, d, palette: pal)
    }

    // MARK: Dome

    /// A small droid seen from a little above: a domed head of metal panels (a big warm round eye, a
    /// small lamp, panels of lights, a projector) on a barrel body with two side legs. At rest the
    /// dome looks around; listening, it turns to face you and its eye brightens with your voice;
    /// thinking, the dome spins and its lights run; working, its projector casts a small hologram;
    /// speaking, it chatters (quick little turns) and its lights blink with the voice's bands.
    func drawDome(_ gc: inout GraphicsContext, _ box: CGSize) {
        var d = robotCanvas(box, scale: 1.36, dy: -0.06)
        let s = RobotState(engine, work)
        let k = density(box)
        let tint = Color(hex: 0x5aa8ff)
        let ink = Ink(d, robotPalette(tint))
        let warm = look.color ?? Color(hex: 0xffd68a), deep = look.color ?? Color(hex: 0xff9a4a)
        let sway = (0.55 * sin(t * 0.31) + 0.2 * sin(t * 0.83)) * (1 - 0.6 * s.speak)
        let chatter = 0.2 * sin(t * 3.3) * s.voice
        // Thinking spins the dome: the engine's turn (accumulated, never a phase times the clock).
        let spin = remainder(engine.ringTurn * 2.2, 2 * Double.pi)
        let domeYaw = (sway + chatter) * (1 - s.listen) * (1 - s.th) + spin * s.th
        let bodyYaw = 0.1 * sin(t * 0.17)
        let pitch = -0.26
        let bodyTurn = Turn3(yaw: bodyYaw, pitch: pitch), domeTurn = Turn3(yaw: bodyYaw + domeYaw, pitch: pitch)
        let oy = -0.2
        let R = 0.86
        func screen(_ turn: Turn3, _ x: Double, _ y: Double, _ z: Double) -> (x: Double, y: Double, z: Double) {
            let p = turn.apply(x, y, z)
            return (p.x, p.y + oy, p.z)
        }
        /// A surface point and its normal, turned; drawn only on the side facing us, lit, nearer larger.
        func surf(_ turn: Turn3, _ x: Double, _ y: Double, _ z: Double, _ nx: Double, _ ny: Double, _ nz: Double,
                  _ tone: Double, _ dither: Double, shine: Double = 0.5) {
            let n = turn.apply(nx, ny, nz)
            guard n.z > -0.02 else { return }
            let p = turn.apply(x, y, z)
            place(&d, p.x, p.y + oy, tone * metal(n.x, n.y, n.z, shine: shine), dither, phase: x, lum: 0.6, size: 0.8 + 0.3 * smoothstep(-1, 1, p.z))
        }
        func onDome(_ el: Double, _ az: Double, _ out: Double = 1.012) -> (Double, Double, Double) {
            (R * out * cos(el) * sin(az), -R * out * sin(el), R * out * cos(el) * cos(az))
        }
        // The legs: boxes at the sides (front and outer faces), lit metal, a shoulder joint each.
        for side in [-1.0, 1.0] {
            // The leg's front: a strut with a rounded shoulder, fading into the dark below.
            var front: [(Double, Double)] = (0...10).map { j in
                let a = Double.pi + Double.pi * Double(j) / 10
                let p = screen(bodyTurn, side * (1.14 + 0.15 * cos(a)), 0.12 + 0.15 * sin(a), 0.16); return (p.x, p.y)
            }
            front += [(1.29, 1.9), (0.99, 1.9)].map { c -> (Double, Double) in
                let p = screen(bodyTurn, side * c.0, c.1, 0.16); return (p.x, p.y)
            }
            let leg = ink.poly(front)
            ink.metal(&gc, leg, hi: (side * 1.08 - 0.06, oy - 0.02), reach: 1.65, 1.05, floor: 0)
            ink.rim(&gc, ink.poly(Array(front.prefix(11)), closed: false), 0.45)
            let outer = [(-0.16, 0.12), (0.16, 0.12), (0.16, 1.9), (-0.16, 1.9)].map { c -> (Double, Double) in
                let p = screen(bodyTurn, side * 1.29, c.1, c.0); return (p.x, p.y)
            }
            ink.metal(&gc, ink.poly(outer), hi: (side * 1.27, oy + 0.05), reach: 1.5, 0.4, floor: 0)
            // The shoulder joint: a round lit bolt facing us.
            let j = screen(bodyTurn, side * 1.14, 0.14, 0.17)
            ink.metal(&gc, ink.circle(j.x, j.y, 0.1), hi: (j.x - 0.035, j.y - 0.04), reach: 0.14, 1.5)
            ink.rim(&gc, ink.circle(j.x, j.y, 0.1), 0.55)
            // A lit panel down the strut.
            let panel = [(1.06, 0.42), (1.22, 0.42), (1.22, 1.05), (1.06, 1.05)].map { c -> (Double, Double) in
                let p = screen(bodyTurn, side * c.0, c.1, 0.17); return (p.x, p.y)
            }
            ink.rim(&gc, ink.poly(panel), 0.35)
        }
        // The body: a barrel, lit from the upper left, fading into the dark below; a sheen down it.
        let bodyOutline = [(-R, oy - 0.05), (R, oy - 0.05), (R, oy + 1.95), (-R, oy + 1.95)]
        ink.metal(&gc, ink.poly(bodyOutline), hi: (-0.38, oy + 0.3), reach: 1.75, 1.3, floor: 0)
        gc.fill(ink.oval(-0.4, oy + 0.65, 0.09, 0.6), with: .linearGradient(Gradient(colors: [.clear, ink.pal[4].opacity(0.16), .clear]),
                                                                             startPoint: ink.p(-0.5, 0), endPoint: ink.p(-0.3, 0)))
        // Its front panels: two lit plates (blue), a vent of three slots between them.
        for (az0, az1, y0, y1) in [(-0.62, -0.08, 0.18, 0.5), (0.08, 0.62, 0.62, 0.95)] {
            let pts = (0...8).map { j -> (Double, Double) in
                let az = az0 + (az1 - az0) * Double(j) / 8
                let p = screen(bodyTurn, R * 1.01 * sin(az), y0, R * 1.01 * cos(az)); return (p.x, p.y)
            } + (0...8).map { j -> (Double, Double) in
                let az = az1 - (az1 - az0) * Double(j) / 8
                let p = screen(bodyTurn, R * 1.01 * sin(az), y1, R * 1.01 * cos(az)); return (p.x, p.y)
            }
            let plate = ink.poly(pts)
            ink.metal(&gc, plate, hi: (pts[0].0 + 0.05, pts[0].1), reach: 0.75, 1.3)
            ink.rim(&gc, plate, 0.55)
        }
        for n in 0..<3 {
            let y = 0.66 + 0.09 * Double(n)
            let a = screen(bodyTurn, R * 1.01 * sin(-0.5), y, R * 1.01 * cos(-0.5)), b = screen(bodyTurn, R * 1.01 * sin(-0.14), y, R * 1.01 * cos(-0.14))
            var slot = Path(); slot.move(to: ink.p(a.x, a.y)); slot.addLine(to: ink.p(b.x, b.y))
            gc.stroke(slot, with: .color(ink.pal[3].opacity(0.4)), style: StrokeStyle(lineWidth: d.px * 1.6, lineCap: .round))
        }
        // The collar: a bright band where the dome meets the body.
        let collar = (0...28).map { j -> (Double, Double) in
            let az = -Double.pi / 2 + Double.pi * Double(j) / 28
            let p = screen(bodyTurn, R * 1.01 * sin(az), 0.02, R * 1.01 * cos(az)); return (p.x, p.y)
        }
        let collarPath = ink.poly(collar, closed: false)
        gc.stroke(collarPath, with: .color(ink.pal[3].opacity(0.25)), lineWidth: d.px * 5)
        gc.stroke(collarPath, with: .color(ink.pal[4].opacity(0.75)), lineWidth: d.px * 1.4)
        // The dome: a lit half sphere (its outline: the top of a circle and the near half of its base).
        var outline: [(Double, Double)] = (0...24).map { j in
            let a = Double.pi + Double.pi * Double(j) / 24
            return (R * cos(a), oy + R * sin(a))
        }
        outline += (1..<24).map { j -> (Double, Double) in
            let az = Double.pi / 2 - Double.pi * Double(j) / 24
            let p = screen(bodyTurn, R * sin(az), 0, R * cos(az)); return (p.x, p.y)
        }
        let dome = ink.poly(outline)
        ink.metal(&gc, dome, hi: (-0.34, oy - 0.56), reach: 1.25, 1.25, floor: 0.6)
        ink.rim(&gc, dome, 0.35, width: 1.1)
        // The dome's panels in points (the seams between them left open).
        for j in 0..<Int(620 * k) + 40 {
            let el = asin(evenPoint(j).0), az = 2 * Double.pi * evenPoint(j).1
            let seamA = abs(el - 0.33) < 0.02 || abs(el - 0.9) < 0.02
            let inBand = el > 0.35 && el < 0.88
            let seamB = inBand && abs(sin(4 * az)) < 0.06
            if seamA || seamB { continue }
            let block = inBand && sin(4 * az + 0.6) > 0.2 && sin(2 * az) > -0.3
            let nx = cos(el) * sin(az), ny = -sin(el), nz = cos(el) * cos(az)
            // The eye, the lamp and the panels of lights are drawn clear of the texture.
            let toEye = nx * 0 + ny * -sin(0.62) + nz * cos(0.62)
            let wrapped = remainder(az, 2 * Double.pi)
            let onPanels = el > 0.1 && el < 0.34 && ((wrapped > -0.5 && wrapped < -0.1) || (wrapped > 0.24 && wrapped < 0.64))
            if toEye > 0.955 || onPanels { continue }
            surf(domeTurn, R * nx, R * ny, R * nz, nx, ny, nz, block ? 1.3 : 0.75, OrbPoints.hash(j, 14), shine: 0.9)
        }
        /// A light on the dome: its centre on the screen, how it faces us, its tilt.
        func spot(_ el: Double, _ az: Double) -> (x: Double, y: Double, face: Double, angle: Double) {
            let q = onDome(el, az)
            let p = screen(domeTurn, q.0, q.1, q.2)
            let n = domeTurn.apply(q.0 / R, q.1 / R, q.2 / R)
            return (p.x, p.y, n.z, atan2(n.y, n.x))
        }
        // The panels of lights under the eye: little round lights, blinking at rest, with the voice's
        // bands as it speaks, in a chase as it thinks.
        var lit = Path(), dim = Path(), glowPath = Path()
        let tickRest = Int(t * 1.6), chase = Int(t * 10) % 12
        for panel in 0..<2 {
            let az0 = panel == 0 ? -0.44 : 0.3
            for c in 0..<4 {
                for r in 0..<3 {
                    let cell = panel * 12 + c * 3 + r
                    let idle = OrbPoints.hash(cell * 101 + tickRest, 7) < 0.45 ? 1.0 : 0.2
                    let voiced = s.spectrum.band(at: Double(c) / 3) > 0.3 + 0.2 * Double(r) ? 1.0 : 0.2
                    let thought = chase == c * 3 + r ? 1.0 : 0.25
                    let on = idle * max(0, 1 - s.speak - s.th) + voiced * s.speak + thought * s.th
                    let q = spot(0.3 - 0.075 * Double(r), az0 + 0.1 * Double(c))
                    guard q.face > 0.15 else { continue }
                    let rr = 0.032 * q.face.squareRoot()
                    if on > 0.55 {
                        lit.addPath(ink.circle(q.x, q.y, rr)); glowPath.addPath(ink.circle(q.x, q.y, rr * 2.4))
                    } else { dim.addPath(ink.circle(q.x, q.y, rr)) }
                }
            }
        }
        gc.fill(glowPath, with: .color(ink.pal[3].opacity(0.2)))
        gc.fill(lit, with: .color(ink.pal[4].opacity(0.95)))
        gc.fill(dim, with: .color(ink.pal[2].opacity(0.45)))
        // The main eye: big, round and warm; it brightens with your voice and blinks now and then.
        let eye = spot(0.62, 0)
        let eyeB = (0.68 + 0.08 * sin(t * 1.3) + 0.45 * s.listen * s.level + 0.3 * s.voice - 0.1 * s.th) * smoothstep(0.02, 0.35, eye.face)
        ink.metal(&gc, ink.oval(eye.x, eye.y, 0.25 * max(0.05, eye.face), 0.25, angle: eye.angle), hi: (eye.x - 0.08, eye.y - 0.1), reach: 0.35, 1.2)
        ink.eye(&gc, eye.x, eye.y, 0.19, eyeB, warm: warm, deep: deep, squash: max(0.05, eye.face), angle: eye.angle, open: blink(t))
        // A small lamp above it, and the projector at its side (bright while it works).
        let lamp = spot(0.86, 0.6)
        ink.eye(&gc, lamp.x, lamp.y, 0.06, (0.7 + 0.3 * s.voice) * smoothstep(0.02, 0.3, lamp.face), warm: ink.pal[3], deep: ink.pal[2],
                squash: max(0.05, lamp.face), angle: lamp.angle, catchlight: 0)
        let proj = spot(0.45, -1.2)
        ink.eye(&gc, proj.x, proj.y, 0.07, (0.4 + 0.8 * s.busy) * smoothstep(0.02, 0.3, proj.face), warm: warm, deep: deep,
                squash: max(0.05, proj.face), angle: proj.angle, catchlight: 0)
        // Working: the projector casts a small hologram, a beam to a turning disc of light.
        if s.busy > 0.02 {
            let target = (x: -1.08, y: -0.82)
            var beam = Path()
            beam.move(to: ink.p(proj.x, proj.y))
            beam.addLine(to: ink.p(target.x + 0.2, target.y + 0.07)); beam.addLine(to: ink.p(target.x - 0.2, target.y + 0.07)); beam.closeSubpath()
            gc.fill(beam, with: .linearGradient(Gradient(colors: [warm.opacity(0.45 * s.busy), ink.pal[3].opacity(0.12 * s.busy)]),
                                                startPoint: ink.p(proj.x, proj.y), endPoint: ink.p(target.x, target.y)))
            ink.glow(&gc, target.x, target.y - 0.06, 0.2, ink.pal[3], 0.5 * s.busy)
            gc.stroke(ink.oval(target.x, target.y + 0.07, 0.2, 0.06), with: .color(ink.pal[4].opacity(0.6 * s.busy)), lineWidth: d.px)
            for j in 0..<36 {
                let ang = 2 * Double.pi * Double(j) / 36 + t * 1.2
                place(&d, target.x + 0.13 * cos(ang), target.y - 0.06 + 0.13 * sin(ang) * 0.45 - 0.03 * sin(t * 3), s.busy * 0.85,
                      OrbPoints.hash(j, 13), phase: ang, lum: 1, size: 1.2)
            }
        }
        // The body's surface in points: seams and grooves left open, two recessed panels in front.
        for j in 0..<Int(460 * k) + 30 {
            let az = 2 * Double.pi * evenPoint(j).0, y = 0.04 + 1.6 * evenPoint(j).1
            if abs(sin(6 * az)) < 0.05 { continue }
            if abs(y - 0.5) < 0.016 || abs(y - 0.98) < 0.016 { continue }
            let front = abs(sin(az)) < 0.24
            let recess = front && ((y > 0.14 && y < 0.44 && az > .pi) || (y > 0.6 && y < 0.9 && az < .pi))
            let nx = sin(az), nz = cos(az)
            let fade = 1 - smoothstep(1.0, 1.62, y)
            if recess { continue }                                              // the panels are fills
            surf(bodyTurn, R * nx, y, R * nz, nx, 0, nz, 0.75 * fade, OrbPoints.hash(j, 14))
        }
        finish(&gc, d, tint: tint)
    }

    // MARK: Valet

    /// A servo's motion (Valet, Retro, Rover): it holds a pose, then moves to the next in a short
    /// eased step (`move`: the share of each period spent moving). The poses (-1…1) are a fixed
    /// sequence and the pace is fixed, so the motion never jumps.
    private func servoStep(_ t: Double, period: Double, move: Double = 0.2, salt: Double) -> Double {
        let x = t / period, n = x.rounded(.down), f = x - n
        let k = Int(n.truncatingRemainder(dividingBy: 7919))
        let a = 2 * OrbPoints.hash(k, salt) - 1, b = 2 * OrbPoints.hash((k + 1) % 7919, salt) - 1
        let e = smoothstep(0, move, f)
        return a + (b - a) * e
    }

    /// A line of lit metal with round ends (an arm, a finger): a base stroke, a highlight along its
    /// lit side.
    private func litStroke(_ gc: inout GraphicsContext, _ ink: Ink, _ path: Path, width: Double, _ a: Double, hi: Double = 0.55) {
        let w = width * ink.R
        gc.stroke(path, with: .color(ink.pal[1].opacity(min(1, a))), style: StrokeStyle(lineWidth: w, lineCap: .round, lineJoin: .round))
        gc.stroke(path.offsetBy(dx: -0.12 * w, dy: -0.12 * w), with: .color(ink.pal[3].opacity(min(1, 0.6 * a))),
                  style: StrokeStyle(lineWidth: 0.55 * w, lineCap: .round, lineJoin: .round))
        gc.stroke(path.offsetBy(dx: -0.24 * w, dy: -0.24 * w), with: .color(ink.pal[4].opacity(min(1, 0.45 * hi * a))),
                  style: StrokeStyle(lineWidth: 0.16 * w, lineCap: .round, lineJoin: .round))
    }

    /// A gilded, well-mannered protocol robot (head, shoulders and hands), stiff and upright, moving
    /// in quick small servo steps (a pose held, then a short eased move). At rest it stands politely
    /// still, surveying the room in small turns of the head, now and then a little tilt; listening,
    /// it bows its head toward you and nods, its ear lamps glowing with your voice, its hands
    /// clasped; thinking, it frets: a little "no, no" of the head turned aside, its eyes dim and
    /// flickering, its hands wringing at its chest; working, a light ticks across its eyes as it
    /// calculates and its head snaps neatly from task to task; speaking, it talks with its whole body:
    /// its head bobs on the syllables, its mouth opens with the voice, its hands gesture, palms up.
    func drawValet(_ gc: inout GraphicsContext, _ box: CGSize) {
        var d = robotCanvas(box, scale: 1.2, dy: 0.04)
        let s = RobotState(engine, work)
        let k = density(box)
        let tint = Color(hex: 0xf0bd52)
        let ink = Ink(d, robotPalette(tint))
        let warm = look.color ?? Color(hex: 0xffe3a3), deep = look.color ?? Color(hex: 0xffa53a)
        let calm = max(0, 1 - s.listen - s.th - s.busy - s.speak)
        let h1 = engine.history.value(secondsAgo: 0.1), h2 = engine.history.value(secondsAgo: 0.35)
        let syllable = s.speak * min(1, 1.5 * h1)                          // its own voice a moment ago
        // Each state's own motion, all at fixed paces; the pose is their blend.
        let survey = servoStep(t, period: 2.9, move: 0.18, salt: 3.1)
        let ohMy = max(0, servoStep(t, period: 4.7, move: 0.22, salt: 7.7))
        let task = servoStep(t, period: 1.2, move: 0.12, salt: 5.3), taskTilt = servoStep(t, period: 1.2, move: 0.12, salt: 9.2)
        let fret = smoothstep(-0.2, 0.5, sin(t * 0.9))                        // the "no, no" comes in bursts
        let shake = fret * sin(t * 8.4)
        let yaw = calm * 0.2 * survey + s.th * (0.3 + 0.09 * shake) + s.busy * 0.26 * task
            + s.speak * (0.1 * sin(t * 1.3) + 0.05 * sin(t * 3.1))
        let bow = s.listen * (0.17 + 0.05 * sin(t * 2.4)) + s.th * 0.07 + s.busy * 0.05 * taskTilt + s.speak * (0.1 * syllable - 0.05)
        let roll = calm * (0.02 * sin(t * 0.3) + 0.11 * ohMy) + s.listen * 0.15 + s.th * (-0.08 + 0.025 * shake)
            + s.busy * 0.05 * taskTilt + s.speak * (0.06 * sin(t * 1.7) + 0.12 * (h1 - h2))
        let head = Turn3(yaw: yaw, pitch: -bow, roll: roll)
        let body = Turn3(yaw: 0.04 * calm * survey + 0.05 * s.th + s.speak * 0.07 * sin(t * 1.1), pitch: 0.12 + 0.05 * syllable,
                         roll: s.speak * 0.035 * sin(t * 0.9) + s.th * 0.02)
        let hy = -0.5, hw = 0.62, hh = 0.7, hd = 0.56
        func onScreen(_ p: (x: Double, y: Double, z: Double), _ cy: Double) -> (Double, Double) { (p.x, p.y + cy + 0.05) }
        func surf(_ turn: Turn3, _ cy: Double, _ x: Double, _ y: Double, _ z: Double, _ nx: Double, _ ny: Double, _ nz: Double,
                  _ tone: Double, _ dither: Double, shine: Double = 1.1) -> (Double, Double)? {
            let n = turn.apply(nx, ny, nz)
            guard n.z > -0.02 else { return nil }
            let q = onScreen(turn.apply(x, y - cy, z), cy)
            return (q.0, q.1)
        }
        /// A point of the face (head coordinates) on the screen.
        func face(_ x: Double, _ y: Double, _ z: Double) -> (Double, Double) { onScreen(head.apply(x, y - hy, z), hy) }
        func front(_ x: Double, _ y: Double) -> Double {
            let ny = (y - hy) / hh, w = hw * (ny > 0 ? 1 - 0.25 * ny : 1)
            return hd * max(0, 1 - pow(x / w, 2) - ny * ny).squareRoot() + 0.012
        }
        let facing = head.apply(0, 0, 1)                                   // the face's normal
        let squash = max(0.2, facing.z), faceAngle = atan2(facing.y, facing.x)
        // The hands' poses (screen units): out of sight at rest, clasped as it listens, wringing at
        // its chest as it frets, low and precise as it works, out and palms up as it speaks.
        struct Hand { let x: Double, y: Double, a: Double, spread: Double, shoulder: (Double, Double), elbow: (Double, Double) }
        let hands = [-1.0, 1.0].map { side -> Hand in
            let wring = sin(t * 3.3 + (side > 0 ? 1.7 : 0))
            let gesture = s.speak * min(1, 1.4 * engine.history.value(secondsAgo: side > 0 ? 0.08 : 0.3))
            let busyStep = servoStep(t, period: 0.9, move: 0.16, salt: side > 0 ? 2.2 : 4.4)
            let x = calm * side * 1.3 + s.listen * side * 0.17 + s.th * (side * 0.2 + 0.045 * wring)
                + s.busy * side * (0.46 + 0.05 * busyStep) + s.speak * side * (1.06 + 0.06 * sin(t * 1.9 + side))
            let y = calm * 2.3 + s.listen * 1.44 + s.th * (1.1 + 0.05 * side * wring) + s.busy * (1.5 - 0.06 * max(0, busyStep))
                + s.speak * (1.02 - 0.3 * gesture)
            let a = calm * side * 2.9 + s.listen * (-side * 1.2) + s.th * (-side * 0.5 + 0.3 * wring) + s.busy * (-side * 1.3 + 0.15 * busyStep)
                + s.speak * side * (0.55 + 0.3 * gesture)
            let ex = side * (1.36 * calm + 1.1 * s.listen + 1.06 * s.th + 1.2 * s.busy + 1.58 * s.speak)
            let ey = 1.64 * calm + 1.74 * s.listen + 1.62 * s.th + 1.74 * s.busy + 1.5 * s.speak
            let spread = 0.3 * s.listen + 0.5 * s.th + 0.2 * s.busy + 1.0 * s.speak
            return Hand(x: x, y: y, a: a, spread: spread, shoulder: (side * 1.24, 1.04), elbow: (ex, ey))
        }
        /// Is a shoulder point hidden behind a hand or a forearm?
        func behindHands(_ x: Double, _ y: Double) -> Bool {
            func near(_ p: (Double, Double), _ q: (Double, Double), _ r: Double) -> Bool {
                let ex = q.0 - p.0, ey = q.1 - p.1, l2 = max(1e-6, ex * ex + ey * ey)
                let f = max(0, min(1, ((x - p.0) * ex + (y - p.1) * ey) / l2))
                return pow(x - p.0 - f * ex, 2) + pow(y - p.1 - f * ey, 2) < r * r
            }
            for h in hands {
                if near(h.shoulder, h.elbow, 0.13) || near(h.elbow, (h.x, h.y), 0.11) { return true }
                if pow(x - h.x - 0.13 * sin(h.a), 2) + pow(y - h.y + 0.13 * cos(h.a), 2) < 0.05 { return true }
            }
            return false
        }
        // Shoulders and chest: the top of a broad plated shell, fading into the dark below.
        let shoulders = (0...30).map { j -> (Double, Double) in
            let a = Double.pi + Double.pi * Double(j) / 30
            return onScreen(body.apply(1.5 * cos(a), 1.0 * sin(a), 0), 1.5)
        } + [onScreen(body.apply(1.5, 0.6, 0), 1.5), onScreen(body.apply(-1.5, 0.6, 0), 1.5)]
        let shell = ink.poly(shoulders)
        ink.metal(&gc, shell, hi: (-0.55, 0.72), reach: 1.6, 1.15, floor: 0)
        ink.rim(&gc, ink.poly(Array(shoulders.prefix(31)), closed: false), 0.4, width: 1.2)
        // The collar plate: a gilded band under the neck.
        let collarL = onScreen(body.apply(-0.42, 0.56, 0.3), 0), collarR = onScreen(body.apply(0.42, 0.56, 0.3), 0)
        let collarM = onScreen(body.apply(0, 0.7, 0.45), 0)
        var collar = Path()
        collar.move(to: ink.p(collarL.0, collarL.1))
        collar.addQuadCurve(to: ink.p(collarR.0, collarR.1), control: ink.p(collarM.0, 2 * collarM.1 - (collarL.1 + collarR.1) / 2))
        gc.stroke(collar, with: .color(ink.pal[3].opacity(0.5)), lineWidth: d.px * 1.3)
        // The neck: a lit column of cables.
        let neckTop = onScreen(body.apply(0, 0.08, 0), 0), neckBottom = onScreen(body.apply(0, 0.56, 0), 0)
        let neck = ink.poly([(neckTop.0 - 0.17, neckTop.1), (neckTop.0 + 0.17, neckTop.1), (neckBottom.0 + 0.19, neckBottom.1), (neckBottom.0 - 0.19, neckBottom.1)])
        ink.metal(&gc, neck, hi: (neckTop.0 - 0.07, neckTop.1 + 0.1), reach: 0.55, 0.9)
        // The head: polished metal, lit from the upper left, its outline leaning with the head.
        let outline = (0..<40).map { j -> (Double, Double) in
            let a = 2 * Double.pi * Double(j) / 40
            let ny = sin(a), w = ny > 0 ? 1 - 0.25 * ny : 1
            let x = hw * w * cos(a), y = hh * ny
            let c = cos(roll), sn = sin(roll)
            return (x * c - y * sn + 0.5 * hd * sin(yaw) * 0.3, x * sn + y * c + hy + 0.05)
        }
        let headPath = ink.poly(outline)
        let hc = face(0, hy, 0)
        ink.metal(&gc, headPath, hi: (hc.0 - 0.24, hc.1 - 0.36), reach: 1.05, 1.25, floor: 0.6)
        ink.rim(&gc, headPath, 0.4, width: 1.1)
        // Ears: round discs at the sides, a lamp in each that glows as it listens.
        for side in [-1.0, 1.0] {
            let n = head.apply(side, 0, 0.2)
            let c = face(side * (hw + 0.015), -0.48, 0)
            let ear = ink.oval(c.0, c.1, 0.13 * max(0.15, abs(n.z) + 0.15), 0.13, angle: atan2(n.y, n.x))
            ink.metal(&gc, ear, hi: (c.0 - 0.04, c.1 - 0.05), reach: 0.2, 1.2)
            ink.rim(&gc, ear, 0.45)
            ink.glow(&gc, c.0, c.1, 0.11 + 0.05 * s.listen * s.level, warm, 0.22 + 0.75 * s.listen * (0.3 + s.level) + 0.1 * s.th * fret)
        }
        // The head's surface in points (its seams left open).
        for j in 0..<Int(600 * k) + 40 {
            let u = 1 - 2 * evenPoint(j).0, a = 2 * Double.pi * evenPoint(j).1
            let r = (1 - u * u).squareRoot()
            let nx = r * cos(a), ny = u, nz = r * sin(a)
            if abs(nx - 0.62) < 0.025 || abs(nx + 0.62) < 0.025 || abs(ny + 0.45) < 0.02 { continue }
            let w = ny > 0 ? 1 - 0.25 * ny : 1
            let n = head.apply(nx, ny, nz)
            guard n.z > -0.02 else { continue }
            let q = face(hw * nx * w, hy + hh * ny, hd * nz)
            place(&d, q.0, q.1, 0.75 * metal(n.x, n.y, n.z, shine: 1.1), OrbPoints.hash(j, 14), phase: nx, lum: 0.7, size: 0.85)
        }
        // The brow: a fine ridge over the eyes.
        let b0 = face(-0.44, -0.72, front(-0.44, -0.72)), b1 = face(0.44, -0.72, front(0.44, -0.72)), bm = face(0, -0.86, front(0, -0.8) + 0.02)
        var brow = Path()
        brow.move(to: ink.p(b0.0, b0.1)); brow.addQuadCurve(to: ink.p(b1.0, b1.1), control: ink.p(bm.0, bm.1))
        gc.stroke(brow, with: .color(ink.pal[3].opacity(0.42)), lineWidth: d.px * 1.2)
        // The eyes: big, round, warm; brighter as it speaks or listens, dim and flickering as it frets.
        let flicker = 0.5 + 0.5 * sin(t * 11.3) * sin(t * 4.1)
        let soft = 1 - s.th * (0.26 + 0.2 * flicker * fret)
        let eyeGlow = (0.7 + 0.38 * s.voice + 0.24 * s.listen + 0.12 * s.busy + 0.06 * sin(t * 1.1)) * soft
        let open = blink(t, 4.6) * (1 - 0.18 * s.th)
        // Working: a light ticking across both eyes, from position to position as it calculates.
        let tick = t * 3.4, tn = tick.rounded(.down)
        let station = tn.truncatingRemainder(dividingBy: 7) + smoothstep(0, 0.35, tick - tn)
        let stations = [-0.39, -0.31, -0.23, -0.15, 0.15, 0.23, 0.31, 0.39]   // it starts and ends its run off the eyes
        let si = min(6, Int(station)), sf = station - Double(si)
        let tickX = stations[si] + (stations[si + 1] - stations[si]) * sf
        for side in [-1.0, 1.0] {
            let ex = side * 0.23, ey = -0.55
            let c = face(ex, ey, front(ex, ey))
            ink.metal(&gc, ink.oval(c.0, c.1, 0.15 * squash, 0.15, angle: faceAngle), hi: (c.0 - 0.05, c.1 - 0.06), reach: 0.22, 0.9)
            ink.eye(&gc, c.0, c.1, 0.11, eyeGlow, warm: warm, deep: deep, squash: squash, angle: faceAngle, open: open)
            let near = max(0, 1 - abs(tickX - ex) / 0.11)
            if s.busy * near > 0.01 {
                let p = face(tickX, ey, front(tickX, ey))
                ink.glow(&gc, p.0, p.1, 0.055, .white, 0.95 * s.busy * near)
            }
        }
        // The mouth: a small slot that curves up a little, opening with the voice.
        let opening = 0.012 + 0.07 * s.voice * (0.5 + 0.5 * min(1, 1.6 * s.loud))
        let left = face(-0.13, -0.21, front(-0.13, -0.21)), right = face(0.13, -0.21, front(0.13, -0.21))
        let upperMid = face(0, -0.2 - 0.03 * s.th, front(0, -0.2)), lowerMid = face(0, -0.18 + opening, front(0, -0.18))
        var mouth = Path()
        mouth.move(to: ink.p(left.0, left.1))
        mouth.addQuadCurve(to: ink.p(right.0, right.1), control: ink.p(2 * upperMid.0 - (left.0 + right.0) / 2, 2 * upperMid.1 - (left.1 + right.1) / 2))
        mouth.addQuadCurve(to: ink.p(left.0, left.1), control: ink.p(2 * lowerMid.0 - (left.0 + right.0) / 2, 2 * lowerMid.1 - (left.1 + right.1) / 2))
        mouth.closeSubpath()
        let speech = 0.45 + 0.65 * s.voice
        gc.fill(mouth, with: .color(warm.opacity(min(1, 0.55 * speech))))
        gc.stroke(mouth, with: .color(warm.opacity(min(1, 0.7 * speech))), lineWidth: d.px * 1.1)
        ink.glow(&gc, (left.0 + right.0) / 2, upperMid.1 + 0.02, 0.2, warm, 0.16 * speech)
        // The neck's cables and the shoulders' surface in points (none behind the hands).
        for j in 0..<Int(150 * k) + 10 {
            let a = 2 * Double.pi * evenPoint(j).0, y = 0.15 + 0.38 * evenPoint(j).1
            if abs(sin(y * 80)) < 0.3 { continue }
            if let q = surf(body, 0, 0.18 * sin(a), y, 0.18 * cos(a), sin(a), 0, cos(a), 0, 0) {
                let n = body.apply(sin(a), 0, cos(a))
                place(&d, q.0, q.1, 0.9 * metal(n.x, n.y, n.z, shine: 1.1), OrbPoints.hash(j, 14), phase: a, lum: 0.7, size: 0.85)
            }
        }
        for j in 0..<Int(420 * k) + 30 {
            let u = evenPoint(j).0, a = 2 * Double.pi * evenPoint(j).1
            let el = 0.15 + 1.25 * u
            let nx = cos(el) * cos(a), ny = -sin(el), nz = cos(el) * sin(a)
            let x = 1.5 * nx, y = 1.5 + 1.0 * ny, z = 0.6 * nz
            guard y > 0.5, y < 1.7 else { continue }
            if abs(abs(x) - 0.64) < 0.02 { continue }                          // plate seams
            let n = body.apply(nx, ny * 1.4, nz)
            guard n.z > -0.02 else { continue }
            let q = onScreen(body.apply(x, y, z), 0)
            if behindHands(q.0, q.1) { continue }
            place(&d, q.0, q.1, 0.85 * (1 - smoothstep(1.1, 1.65, y)) * metal(n.x, n.y, n.z, shine: 1.1), OrbPoints.hash(j, 14), phase: x, lum: 0.7, size: 0.85)
        }
        // The chest lamp: round and warm, pulsing as it frets, ticking as it works.
        let lamp = onScreen(body.apply(0, 0.92, 0.62), 0)
        let tickPulse = 0.5 + 0.5 * cos(2 * Double.pi * (tick - tn))
        ink.eye(&gc, lamp.0, lamp.1, 0.085, 0.45 + 0.3 * s.th * (0.5 + 0.5 * sin(t * 3.3)) + 0.35 * s.busy * tickPulse + 0.3 * s.voice,
                warm: warm, deep: deep, catchlight: 0.6)
        // The arms: an upper arm from the shoulder, a forearm, a palm and four fingers (fanned as it
        // gestures); both arms' parts drawn together.
        var uppers = Path(), forearms = Path(), cuffs = Path(), palms = Path(), fingers = Path(), joints = Path()
        for (n, h) in hands.enumerated() {
            let side = n == 0 ? -1.0 : 1.0
            uppers.move(to: ink.p(h.shoulder.0, h.shoulder.1)); uppers.addLine(to: ink.p(h.elbow.0, h.elbow.1))
            ink.metal(&gc, ink.circle(h.shoulder.0, h.shoulder.1, 0.15), hi: (h.shoulder.0 - 0.05, h.shoulder.1 - 0.06), reach: 0.22, 1.3, floor: 0.8)
            joints.addPath(ink.circle(h.shoulder.0, h.shoulder.1, 0.15))
            guard h.y < 2.05 else { continue }
            let ux = sin(h.a), uy = -cos(h.a)                                // the fingers' way
            let vx = cos(h.a), vy = sin(h.a)                                 // across the palm
            forearms.move(to: ink.p(h.elbow.0, h.elbow.1)); forearms.addLine(to: ink.p(h.x - 0.02 * ux, h.y - 0.02 * uy))
            cuffs.addPath(ink.oval(h.x, h.y, 0.1, 0.04, angle: h.a))
            let pc = (h.x + 0.13 * ux, h.y + 0.13 * uy)
            palms.addPath(ink.oval(pc.0, pc.1, 0.135, 0.14, angle: h.a))
            for f in 0..<4 {
                let off = (Double(f) - 1.5) * 0.062 * (1 + 0.25 * h.spread)
                let fa = h.a + (Double(f) - 1.5) * 0.14 * h.spread, len = 0.155 - 0.018 * abs(Double(f) - 1.5)
                let bx = pc.0 + 0.105 * ux + off * vx, by = pc.1 + 0.105 * uy + off * vy
                fingers.move(to: ink.p(bx, by)); fingers.addLine(to: ink.p(bx + len * sin(fa), by - len * cos(fa)))
            }
            let ta = h.a - side * (1.0 + 0.3 * h.spread)                      // the thumb, on the inner side
            let tb = (pc.0 - side * 0.1 * vx, pc.1 - side * 0.1 * vy)
            fingers.move(to: ink.p(tb.0, tb.1)); fingers.addLine(to: ink.p(tb.0 + 0.12 * sin(ta), tb.1 - 0.12 * cos(ta)))
        }
        ink.rim(&gc, joints, 0.4)
        litStroke(&gc, ink, uppers, width: 0.21, 0.95)
        litStroke(&gc, ink, forearms, width: 0.18, 1)
        gc.stroke(cuffs, with: .color(ink.pal[3].opacity(0.55)), lineWidth: d.px * 1.3)
        gc.fill(palms, with: .linearGradient(Gradient(colors: [ink.pal[3].opacity(0.75), ink.pal[1].opacity(0.85)]),
                                             startPoint: ink.p(0, 0.85), endPoint: ink.p(0, 1.75)))
        ink.rim(&gc, palms, 0.5)
        litStroke(&gc, ink, fingers, width: 0.06, 1, hi: 0.8)
        finish(&gc, d, tint: tint)
    }
    // MARK: Retro

    /// A gentle giant of the fifties, heavy and slow (nothing jerks): a glass dome over whirring
    /// works, ear discs on rods, a face of dark grille with two small warm lamps and the neon tubes
    /// of its voice, a barrel chest with a panel of dials and lights, ribbed arms ending in claws.
    /// The works are its mind: at rest they tick slowly and its ear discs scan the room; listening,
    /// the discs turn to face you and glow with your voice while the works quieten; thinking, the
    /// works spin up, more of them turning at their own paces, its voice tubes dark; working, its
    /// claws tick and the chest's lights run; speaking, each neon tube flickers with its band of the
    /// voice and it gives a stately nod on the loud syllables.
    func drawRetro(_ gc: inout GraphicsContext, _ box: CGSize) {
        var d = robotCanvas(box, scale: 1.24, dy: -0.02)
        let s = RobotState(engine, work)
        let k = density(box)
        let tint = Color(hex: 0x9fb6d3)
        let ink = Ink(d, robotPalette(tint))
        let warm = look.color ?? Color(hex: 0xffd88a), deep = look.color ?? Color(hex: 0xff9f45)
        let neon = look.color ?? Color(hex: 0x9eeeff), neonCore = look.color.map { _ in Color.white } ?? Color(hex: 0xeefcff)
        // A heavy, slow sway; the head nods on the voice's emphasis (its loudness a moment ago).
        let emphasis = s.speak * min(1, 1.3 * engine.history.value(secondsAgo: 0.35))
        let sway = 0.09 * sin(t * 0.21) + 0.03 * sin(t * 0.13)
        let turn = Turn3(yaw: sway, pitch: 0.15)
        let head = Turn3(yaw: sway * 1.2 + 0.04 * s.th * sin(t * 0.4), pitch: 0.15 + 0.05 * s.listen - 0.03 * s.th + 0.1 * emphasis - 0.03 * s.speak)
        let oy = -0.08, pivot = -0.3
        func at(_ x: Double, _ y: Double, _ z: Double) -> (Double, Double) { let p = turn.apply(x, y, z); return (p.x, p.y + oy) }
        func atH(_ x: Double, _ y: Double, _ z: Double) -> (Double, Double) { let p = head.apply(x, y - pivot, z); return (p.x, p.y + pivot + oy) }
        // The chest: a barrel, lit metal fading into the dark below, three grooves round it.
        func chestWidth(_ y: Double) -> Double { 0.86 + 0.18 * sin(min(1, (y - 0.1) / 1.2) * .pi * 0.9) }
        let left = stride(from: 0.12, through: 1.9, by: 0.12).map { y in at(-chestWidth(y), y, 0) }
        let right = stride(from: 1.9, through: 0.12, by: -0.12).map { y in at(chestWidth(y), y, 0) }
        let w0 = chestWidth(0.12)
        let top = (1..<16).map { j -> (Double, Double) in
            let az = Double.pi / 2 - Double.pi * Double(j) / 16
            return at(w0 * sin(az), 0.12, 0.62 * w0 * cos(az))
        }
        ink.metal(&gc, ink.poly(left + right + top), hi: (-0.42, 0.42), reach: 1.75, 1.45, floor: 0)
        ink.rim(&gc, ink.poly([at(-w0, 0.12, 0)] + top + [at(w0, 0.12, 0)], closed: false), 0.4)
        var grooves = Path()
        for gy in [1.1, 1.32] {
            let w = chestWidth(gy)
            grooves.addLines((0...20).map { j -> CGPoint in
                let az = -Double.pi / 2 + Double.pi * Double(j) / 20
                let q = at(w * sin(az), gy, 0.62 * w * cos(az)); return ink.p(q.0, q.1)
            })
        }
        gc.stroke(grooves, with: .color(ink.pal[3].opacity(0.26)), lineWidth: d.px)
        // The chest in points, its grooves and its panel left open.
        for j in 0..<Int(260 * k) + 20 {
            let y = 0.16 + 1.4 * evenPoint(j).0, az = Double.pi * (evenPoint(j).1 - 0.5) * 0.92
            if abs(sin(y * 30)) < 0.16 { continue }
            if y > 0.3, y < 1.0, abs(az) < 0.5 { continue }
            let w = chestWidth(y)
            let nx = sin(az), nz = cos(az)
            let n = turn.apply(nx, 0, nz)
            guard n.z > -0.02 else { continue }
            let p = turn.apply(w * nx, y, 0.62 * w * nz)
            place(&d, p.x, p.y + oy, 0.45 * (1 - smoothstep(1.0, 1.55, y)) * metal(n.x, n.y, n.z, shine: 0.7), OrbPoints.hash(j, 14),
                  phase: nx, lum: 0.6, size: 0.8 + 0.3 * smoothstep(-1, 1, p.z))
        }
        // The chest panel: a dark plate, three dials (their needles swinging, briskly as it works)
        // and a row of six warm lights that run while it works.
        let panel = ink.poly([at(-0.46, 0.32, 0.66), at(0.46, 0.32, 0.66), at(0.46, 0.98, 0.64), at(-0.46, 0.98, 0.64)])
        gc.fill(panel, with: .color(Color.black.opacity(0.45)))
        ink.rim(&gc, panel, 0.35)
        var dials = Path(), needles = Path()
        for (n, dx) in [-0.27, 0.0, 0.27].enumerated() {
            let c = at(dx, 0.54, 0.68)
            dials.addPath(ink.circle(c.0, c.1, 0.1))
            let a = 0.7 * sin(t * (0.5 + 0.23 * Double(n)) + Double(n)) + s.busy * 0.9 * servoStep(t, period: 0.7, move: 0.3, salt: 1.3 + Double(n))
            needles.move(to: ink.p(c.0, c.1)); needles.addLine(to: ink.p(c.0 + 0.085 * sin(a), c.1 - 0.085 * cos(a)))
        }
        gc.fill(dials, with: .color(ink.pal[1].opacity(0.55)))
        gc.stroke(dials, with: .color(ink.pal[3].opacity(0.7)), lineWidth: d.px * 1.1)
        gc.stroke(needles, with: .color(warm.opacity(0.9)), style: StrokeStyle(lineWidth: d.px * 1.2, lineCap: .round))
        var litLamps = Path(), haloLamps = Path(), dimLamps = Path()
        let run = fract(t * 1.6) * 6
        for n in 0..<6 {
            let l = at(-0.3 + 0.12 * Double(n), 0.82, 0.66)
            let near = abs(Double(n) - run), on = 0.25 * (1 - s.busy) + s.busy * exp(-near * near / 0.5) + 0.25 * s.voice
            if on > 0.45 { litLamps.addPath(ink.circle(l.0, l.1, 0.032)); haloLamps.addPath(ink.circle(l.0, l.1, 0.07)) }
            else { dimLamps.addPath(ink.circle(l.0, l.1, 0.028)) }
        }
        gc.fill(haloLamps, with: .color(warm.opacity(0.25)))
        gc.fill(litLamps, with: .color(warm.opacity(0.95)))
        gc.fill(dimLamps, with: .color(deep.opacity(0.35)))
        // The arms: ribbed, hanging heavy at its sides, claws that tick open and shut as it works.
        let liftArms = s.speak * 0.12 * engine.history.value(secondsAgo: 0.5) + 0.03 * sin(t * 0.37)
        var arms = Path(), ribs = Path(), claws = Path()
        var wrists: [(Double, Double)] = []
        for side in [-1.0, 1.0] {
            let sh = at(side * 1.0, 0.3, 0.05)
            let swing = 0.04 * sin(t * 0.31 + side) + s.busy * 0.05 * servoStep(t, period: 1.1, move: 0.35, salt: side + 6)
            let wr = at(side * (1.2 + swing), 1.28 - liftArms, 0.3 + liftArms)
            arms.move(to: ink.p(sh.0, sh.1)); arms.addLine(to: ink.p(wr.0, wr.1))
            let ax = wr.0 - sh.0, ay = wr.1 - sh.1, len = (ax * ax + ay * ay).squareRoot()
            let ux = ax / len, uy = ay / len
            for r in 1..<8 {
                let f = Double(r) / 8, cx = sh.0 + ax * f, cy = sh.1 + ay * f
                ribs.move(to: ink.p(cx - 0.1 * uy, cy + 0.1 * ux))
                ribs.addQuadCurve(to: ink.p(cx + 0.1 * uy, cy - 0.1 * ux), control: ink.p(cx + 0.04 * ux, cy + 0.04 * uy))
            }
            // The claw: two curved fingers and a thumb.
            let open = 0.25 + 0.1 * sin(t * 0.5 + side) + s.busy * 0.3 * (0.5 + 0.5 * servoStep(t, period: 0.8, move: 0.3, salt: side + 2))
                + 0.15 * s.speak * engine.history.value(secondsAgo: 0.3)
            for f in [-1.0, 1.0] {
                let a = atan2(uy, ux) + f * open
                let mid = (wr.0 + 0.15 * cos(a), wr.1 + 0.15 * sin(a))
                let a2 = a - f * 0.7
                claws.move(to: ink.p(wr.0, wr.1))
                claws.addQuadCurve(to: ink.p(mid.0 + 0.1 * cos(a2), mid.1 + 0.1 * sin(a2)), control: ink.p(mid.0, mid.1))
            }
            wrists.append(wr)
        }
        litStroke(&gc, ink, arms, width: 0.2, 0.6, hi: 0.2)
        gc.stroke(ribs, with: .color(ink.pal[0].opacity(0.9)), lineWidth: d.px * 1.3)
        litStroke(&gc, ink, claws, width: 0.08, 0.75, hi: 0.3)
        for wr in wrists { ink.metal(&gc, ink.circle(wr.0, wr.1, 0.075), hi: (wr.0 - 0.02, wr.1 - 0.03), reach: 0.11, 1.3) }
        // The face: a dark grille, two small warm lamps, the neon tubes of its voice.
        let plate = atH(0, -0.15, 0.66)
        let plateShape = Path(roundedRect: CGRect(x: d.cx + (plate.0 - 0.52) * d.R, y: d.cy + (plate.1 - 0.22) * d.R, width: 1.04 * d.R, height: 0.44 * d.R),
                              cornerRadius: 0.14 * d.R)
        ink.metal(&gc, plateShape, hi: (plate.0 - 0.25, plate.1 - 0.15), reach: 0.7, 1.1, floor: 0.6)
        ink.rim(&gc, plateShape, 0.45)
        let grille = Path(roundedRect: CGRect(x: d.cx + (plate.0 - 0.33) * d.R, y: d.cy + (plate.1 - 0.15) * d.R, width: 0.66 * d.R, height: 0.3 * d.R),
                          cornerRadius: 0.05 * d.R)
        gc.fill(grille, with: .color(Color.black.opacity(0.6)))
        var mesh = Path()
        for r in 1..<6 {
            let y = plate.1 - 0.15 + 0.05 * Double(r)
            mesh.move(to: ink.p(plate.0 - 0.31, y)); mesh.addLine(to: ink.p(plate.0 + 0.31, y))
        }
        var tubes = Path(), lit = Path()
        let flickerTick = Int((t * 22).truncatingRemainder(dividingBy: 9973))
        for c in 0..<7 {
            let x = plate.0 - 0.27 + 0.09 * Double(c), y0 = plate.1 + 0.11, y1 = plate.1 - 0.11
            tubes.move(to: ink.p(x, y0)); tubes.addLine(to: ink.p(x, y1))
            let band = s.spectrum.band(at: Double(c) / 6)
            let flick = 0.7 + 0.3 * OrbPoints.hash(flickerTick + 37 * c, 5.1)
            let v = min(1, s.speak * (0.12 + 1.5 * band + 0.25 * s.loud) * flick)
            if v > 0.03 {
                let half = 0.11 * v
                lit.move(to: ink.p(x, plate.1 + half)); lit.addLine(to: ink.p(x, plate.1 - half))
            }
        }
        // The tubes glow behind the grille: a wash of their light, the lit lengths, the mesh over them.
        gc.stroke(tubes, with: .color(neon.opacity(0.12)), lineWidth: d.px * 2.2)
        let voiceGlow = min(1, 0.4 + 0.8 * s.voice)
        if s.speak > 0.02 {
            gc.fill(grille, with: .radialGradient(Gradient(colors: [neon.opacity(min(1, 0.4 * s.speak * (0.3 + s.loud))), .clear]),
                                                  center: ink.p(plate.0, plate.1), startRadius: 0, endRadius: 0.36 * d.R))
        }
        gc.stroke(lit, with: .color(neon.opacity(0.35 * voiceGlow)), lineWidth: d.px * 4.5)
        gc.stroke(lit, with: .color(neonCore.opacity(0.95 * voiceGlow)), lineWidth: d.px * 1.6)
        gc.stroke(mesh, with: .color(Color.black.opacity(0.55)), lineWidth: d.px * 1.2)
        gc.stroke(mesh, with: .color(ink.pal[2].opacity(0.18)), lineWidth: d.px * 0.6)
        let eyeB = (0.75 + 0.4 * s.listen * s.level + 0.2 * s.voice + 0.08 * sin(t * 1.2)) * (1 - 0.12 * s.th)
        for side in [-1.0, 1.0] {
            let e = atH(side * 0.42, -0.15, 0.7)
            ink.eye(&gc, e.0, e.1, 0.058, eyeB, warm: warm, deep: deep, open: blink(t, 6.1), halo: 0.8)
        }
        // The dome's collar: a metal band.
        let collar = ink.poly([atH(-0.7, -0.5, 0), atH(0.7, -0.5, 0), atH(0.7, -0.4, 0), atH(-0.7, -0.4, 0)])
        ink.metal(&gc, collar, hi: (-0.3, -0.56), reach: 0.9, 1.3)
        ink.rim(&gc, collar, 0.5)
        // The glass dome: clear in the middle, lit at its rim.
        let dc = atH(0, -0.48, 0), dr = 0.64
        let half = ink.poly((0...28).map { j -> (Double, Double) in
            let a = Double.pi + Double.pi * Double(j) / 28
            return (dc.0 + dr * cos(a), dc.1 + dr * sin(a))
        })
        let glassStops: [Gradient.Stop] = [.init(color: ink.pal[1].opacity(0.05), location: 0), .init(color: ink.pal[2].opacity(0.08), location: 0.6),
                                           .init(color: ink.pal[3].opacity(0.32), location: 0.94), .init(color: ink.pal[4].opacity(0.45), location: 1)]
        gc.fill(half, with: .radialGradient(Gradient(stops: glassStops), center: ink.p(dc.0, dc.1), startRadius: 0, endRadius: dr * d.R))
        // The works inside: a spindle on a base, a ticking cog, two gyro rings, a warm core; thinking,
        // two more discs and a scanner join in, each at its own pace.
        let spin = engine.ringTurn * 3 + t * 0.4 - engine.swirl * 0.3                 // the voice slows them: attention
        let quiet = 1 - 0.45 * s.listen                                         // listening, the works hush
        let coreB = (0.55 + 0.5 * s.th + 0.2 * s.voice + 0.15 * s.busy) * quiet
        let works = (x: dc.0, y: dc.1 - 0.3)
        var base = Path()
        base.addPath(ink.oval(dc.0, dc.1 - 0.06, 0.34, 0.05))
        base.move(to: ink.p(dc.0, dc.1 - 0.06)); base.addLine(to: ink.p(works.x, works.y - 0.2))
        gc.stroke(base, with: .color(ink.pal[3].opacity(0.45 * quiet)), lineWidth: d.px * 1.2)
        // The cog ticks: a step at a time, its pace the structure's turn (faster as it thinks).
        let ticks = engine.ringTurn * 7, tn = ticks.rounded(.down)
        let cogA = Double.pi / 9 * (tn.truncatingRemainder(dividingBy: 18) + smoothstep(0, 0.35, ticks - tn))   // a whole turn in 18 ticks
        var cog = Path()
        let cogC = (dc.0, dc.1 - 0.15)
        for n in 0..<9 {
            let a = cogA + 2 * Double.pi * Double(n) / 9
            let x0 = cogC.0 + 0.12 * cos(a), y0 = cogC.1 + 0.035 * sin(a), x1 = cogC.0 + 0.16 * cos(a), y1 = cogC.1 + 0.047 * sin(a)
            guard sin(a) > -0.3 else { continue }
            cog.move(to: ink.p(x0, y0)); cog.addLine(to: ink.p(x1, y1))
        }
        cog.addPath(ink.oval(cogC.0, cogC.1, 0.12, 0.035))
        gc.stroke(cog, with: .color(warm.opacity(0.75 * quiet)), lineWidth: d.px * 1.3)
        for (n, (r, tilt)) in [(0.22, 0.4), (0.16, -0.9)].enumerated() {
            let ring = ink.oval(works.x, works.y, r, r * abs(cos(tilt + Double(n) * spin * 0.3)) * 0.5 + 0.02, angle: 0.2 * sin(spin * 0.5 + Double(n)))
            gc.stroke(ring, with: .color(deep.opacity(0.25 * quiet)), lineWidth: d.px * 3.5)
            gc.stroke(ring, with: .color(warm.opacity(0.75 * quiet)), lineWidth: d.px * 0.9)
            let a = spin * (n == 0 ? 1 : -1.3)
            ink.glow(&gc, works.x + r * cos(a), works.y + r * sin(a) * abs(cos(tilt)) * 0.5, 0.05, warm, 0.8 * quiet)
        }
        let busyWorks = max(s.th, 0.6 * s.busy)
        if busyWorks > 0.02 {
            for (n, (r, pace)) in [(0.3, 2.3), (0.11, -3.7)].enumerated() {
                let y = works.y + (n == 0 ? 0.1 : -0.12)
                gc.stroke(ink.oval(works.x, y, r, 0.22 * r), with: .color(warm.opacity(0.55 * busyWorks)), lineWidth: d.px)
                let a = t * pace + Double(n)
                ink.glow(&gc, works.x + r * cos(a), y + 0.22 * r * sin(a), 0.04, .white, 0.9 * busyWorks)
            }
            let sx = works.x + 0.42 * sin(t * 1.9)
            var scanner = Path(); scanner.move(to: ink.p(sx, dc.1 - 0.1)); scanner.addLine(to: ink.p(sx, dc.1 - 0.85 * max(0, 0.36 - pow(sx - dc.0, 2)).squareRoot()))
            gc.stroke(scanner, with: .color(neon.opacity(0.6 * busyWorks)), style: StrokeStyle(lineWidth: d.px * 1.5, lineCap: .round))
        }
        ink.glow(&gc, works.x, works.y, 0.15, warm, 0.45 * coreB)
        ink.glow(&gc, works.x, works.y, 0.045, .white, 0.8 * coreB)
        let shine = Gradient(colors: [Color.white.opacity(0.24), .clear])
        gc.fill(ink.oval(dc.0 - 0.3, dc.1 - 0.4, 0.2, 0.08, angle: -0.75),
                with: .linearGradient(shine, startPoint: ink.p(dc.0 - 0.42, dc.1 - 0.52), endPoint: ink.p(dc.0 - 0.18, dc.1 - 0.28)))
        gc.fill(ink.oval(dc.0 + 0.4, dc.1 - 0.3, 0.035, 0.12, angle: 0.65), with: .color(.white.opacity(0.12)))
        for j in 0..<Int(220 * k) + 20 {                                       // sparkle on the glass's rim
            let a = Double.pi + Double.pi * evenPoint(j).0
            let r = dr * (0.97 + 0.03 * evenPoint(j).1)
            place(&d, dc.0 + r * cos(a), dc.1 + r * sin(a), 0.32 + 0.4 * pow(max(0, -cos(a - 0.6)), 2), OrbPoints.hash(j, 14), phase: a, lum: 0.9, size: 0.85)
        }
        // The ear discs on their rods: scanning the room slowly, turned to face you as it listens.
        for side in [-1.0, 1.0] {
            let base = atH(side * 0.6, -0.72, 0), tip = atH(side * 0.98, -1.0, 0)
            var rod = Path(); rod.move(to: ink.p(base.0, base.1)); rod.addLine(to: ink.p(tip.0, tip.1))
            gc.stroke(rod, with: .color(ink.pal[3].opacity(0.7)), lineWidth: d.px * 1.6)
            let scan = 1.25 * sin(t * 0.42 + side * 1.1) + 0.3 * s.th * sin(t * 0.9 + side)
            let w = abs(cos(scan * (1 - s.listen)))
            let disc = ink.oval(tip.0, tip.1, 0.17 * max(0.08, w), 0.17)
            ink.metal(&gc, disc, hi: (tip.0 - 0.06 * w, tip.1 - 0.07), reach: 0.24, 1.2)
            ink.rim(&gc, disc, 0.6)
            let hear = 0.35 + 0.9 * s.listen * (0.3 + s.level)
            ink.glow(&gc, tip.0, tip.1, 0.09 + 0.08 * s.listen * w, warm, hear * (0.4 + 0.6 * w))
        }
        finish(&gc, d, tint: tint)
    }
    // MARK: Deco

    /// The radius of a hoop of light round Deco at height `y` (her units): wide round the shoulders,
    /// close round the neck, the shape of her head above it.
    private func decoHoop(_ y: Double) -> Double {
        let head = 0.3 + 0.36 * max(0, 1 - pow((y + 0.6) / 0.8, 2)).squareRoot()
        let body = 0.36 + (1.32 - 0.36) * smoothstep(0.25, 0.7, y)
        return head + (body - head) * smoothstep(-0.2, 0.05, y)
    }

    /// An art-deco machine woman, poised and hieratic: a long serene metal face (almond eyes under
    /// heavy lids, a fine nose, closed lips), a crest over the head, a tall neck of rings, sculpted
    /// shoulders and a sunburst on the chest; rings of cool light pass round her, her signature.
    /// At rest a few rings drift slowly up round her; listening, she inclines her head toward you,
    /// her eyes soften and the rings draw in round her head, brighter with your voice; thinking,
    /// her eyes lower, her head bows a little and the rings gather close and slow; working, the rings
    /// multiply and rise fast up her body and her eyes light; speaking, her lips barely move but
    /// her eyes and crest glow with the voice, rings pulse outward on its syllables, her chin lifts.
    func drawDeco(_ gc: inout GraphicsContext, _ box: CGSize) {
        var d = robotCanvas(box, scale: 1.12, dy: 0.02)
        let s = RobotState(engine, work)
        let k = density(box)
        let tint = Color(hex: 0xdcb878)
        let ink = Ink(d, robotPalette(tint))
        let warm = look.color ?? Color(hex: 0xffe1a8), deep = look.color ?? Color(hex: 0xe8a050)
        let cool = look.color ?? Color(hex: 0x9ccaff), coolCore = look.color.map { _ in Color.white } ?? Color(hex: 0xeef6ff)
        let calm = max(0, 1 - s.listen - s.th - s.busy - s.speak)
        let emphasis = s.speak * min(1, 1.4 * engine.history.value(secondsAgo: 0.2))
        let bow = s.listen * 0.12 + s.th * 0.09 - s.speak * (0.05 + 0.05 * emphasis) - s.busy * 0.03
        let head = Turn3(yaw: 0.05 * sin(t * 0.21) * (1 - s.th), pitch: 0.025 * sin(t * 0.17) - bow,
                         roll: 0.02 * sin(t * 0.13) + 0.13 * s.listen)
        let hy = -0.6, hw = 0.45, hh = 0.64, hd = 0.46
        func sc(_ x: Double, _ y: Double) -> (Double, Double) { (x * 1.2, y * 1.2 + 0.1) }
        func onHead(_ x: Double, _ y: Double, _ z: Double) -> (x: Double, y: Double, z: Double) {
            let p = head.apply(x, y - hy, z)
            let q = sc(p.x, p.y + hy)
            return (q.0, q.1, p.z)
        }
        func putHead(_ x: Double, _ y: Double, _ z: Double, _ b: Double, _ dither: Double, _ phase: Double, lum: Double = 0.7) {
            let p = onHead(x, y, z)
            guard p.z > -0.1 else { return }
            place(&d, p.x, p.y, b * (0.35 + 0.65 * smoothstep(-0.1, 0.4, p.z)), dither, phase: phase, lum: lum, size: 0.8)
        }
        func front(_ x: Double, _ y: Double) -> Double {
            let ny = (y - hy) / hh, w = hw * (ny > 0 ? 1 - 0.3 * ny : 1)
            return hd * max(0, 1 - pow(x / w, 2) - ny * ny).squareRoot() + 0.01
        }
        let facing = head.apply(0, 0, 1)
        let squash = max(0.2, facing.z), faceAngle = atan2(facing.y, facing.x)
        // The rings of light round her, each state's own family at its own fixed pace (a change of
        // state fades one family out and the next in): behind her first (dim), in front last.
        var rings: [(y: Double, r: Double, b: Double)] = []
        for n in 0..<2 where calm > 0.02 {                                   // rest: two, drifting slowly up
            let f = fract(t * 0.055 + Double(n) / 2), y = 1.5 - 2.9 * f
            rings.append((y, 1.12 * decoHoop(y), calm * 0.55 * sin(Double.pi * f)))
        }
        for n in 0..<3 where s.listen > 0.02 {                                // listening: drawing in round her head
            let f = fract(t * 0.3 + Double(n) / 3), y = n == 2 ? 0.1 : -1.0 + 0.08 * f
            rings.append((y, (n == 2 ? 0.42 : 0.56) + 1.0 * pow(1 - f, 1.5), s.listen * (0.35 + 0.9 * s.level) * smoothstep(0, 0.3, f) * (1 - smoothstep(0.8, 1, f))))
        }
        for n in 0..<3 where s.th > 0.02 {                                    // thinking: close round her, slow
            let y = [-1.02, 0.1, 0.3][n] + 0.05 * sin(t * 0.33 + 2.1 * Double(n))
            rings.append((y, 1.04 * decoHoop(y) + 0.02 * sin(t * 0.5 + Double(n)), s.th * (0.5 + 0.15 * sin(t * 0.45 + Double(n)))))
        }
        for n in 0..<6 where s.busy > 0.02 {                                  // working: many, rising fast up her body
            let f = fract(t * 0.42 + Double(n) / 6), y = 1.6 - 3.0 * f
            rings.append((y, 1.1 * decoHoop(y), s.busy * 0.95 * pow(sin(Double.pi * f), 0.6)))
        }
        for n in 0..<3 where s.speak > 0.02 {                                 // speaking: pulsing outward on the syllables
            let f = fract(t * 0.55 + Double(n) / 3)
            rings.append((0.06 + 0.12 * f, 0.4 + 1.35 * f, s.speak * (0.15 + 1.1 * engine.history.value(secondsAgo: min(1.2, f / 0.55))) * (1 - f) * smoothstep(0, 0.12, f)))
        }
        func ring(_ r: (y: Double, r: Double, b: Double), frontHalf: Bool) {
            guard r.b > 0.02 else { return }
            let ry = 0.12 * r.r
            let arc = (0...20).map { j -> (Double, Double) in
                let a = (frontHalf ? 0 : Double.pi) + Double.pi * Double(j) / 20
                return sc(r.r * cos(a), r.y + ry * sin(a))
            }
            let path = ink.poly(arc, closed: false)
            let a = r.b * (frontHalf ? 1 : 0.35)
            if frontHalf { gc.stroke(path, with: .color(cool.opacity(min(1, 0.24 * a))), style: StrokeStyle(lineWidth: d.px * 4.2, lineCap: .round)) }
            gc.stroke(path, with: .color(coolCore.opacity(min(1, 0.95 * a))), style: StrokeStyle(lineWidth: d.px * 1.2, lineCap: .round))
        }
        for r in rings { ring(r, frontHalf: false) }
        // The shoulders: sculpted plates between three arcs each side; the sunburst on her chest.
        var arcs = [Path(), Path(), Path()]
        for side in [-1.0, 1.0] {
            let upper = (0...16).map { j -> (Double, Double) in let f = Double(j) / 16; return sc(side * (0.22 + 1.2 * f), 0.42 + 0.42 * f * f) }
            let lower = (0...16).reversed().map { j -> (Double, Double) in let f = Double(j) / 16; return sc(side * (0.22 + 1.2 * f), 0.6 + 0.42 * f * f) }
            ink.metal(&gc, ink.poly(upper + lower), hi: sc(side * 0.45, 0.42), reach: 1.4, 1.0, floor: 0)
            for arc in 0..<3 {
                let line = (0...16).map { j -> (Double, Double) in let f = Double(j) / 16; return sc(side * (0.22 + 1.2 * f), 0.42 + 0.09 * Double(arc) + 0.42 * f * f) }
                arcs[arc].addPath(ink.poly(line, closed: false))
            }
        }
        for (n, arc) in arcs.enumerated() { gc.stroke(arc, with: .color(ink.pal[3].opacity(0.55 - 0.15 * Double(n))), lineWidth: d.px * 1.1) }
        // The chest plate: a fan under the neck, carrying the sunburst.
        let fan = [sc(-0.24, 0.4), sc(0.24, 0.4), sc(0.8, 1.6), sc(-0.8, 1.6)]
        ink.metal(&gc, ink.poly(fan), hi: sc(-0.08, 0.5), reach: 1.3, 0.85, floor: 0)
        let rays = 11
        let lit = fract(t * 0.55) * Double(rays)
        for r in 0..<rays {
            let a = Double.pi / 2 + (Double(r) - Double(rays - 1) / 2) * 0.16
            let near = abs(Double(r) - lit)
            let glow = 0.4 + 0.9 * s.busy * exp(-near * near / 0.8)
            let from = sc(0.13 * cos(a), 0.6 + 0.13 * sin(a)), to = sc(0.9 * cos(a), 0.6 + 0.9 * sin(a))
            var ray = Path(); ray.move(to: ink.p(from.0, from.1)); ray.addLine(to: ink.p(to.0, to.1))
            let g = Gradient(colors: [ink.pal[4].opacity(min(1, 0.7 * glow)), ink.pal[3].opacity(min(1, 0.3 * glow)), .clear])
            gc.stroke(ray, with: .linearGradient(g, startPoint: ink.p(from.0, from.1), endPoint: ink.p(to.0, to.1)), lineWidth: d.px * 1.6)
        }
        ink.glow(&gc, sc(0, 0.6).0, sc(0, 0.6).1, 0.22, warm, 0.35 + 0.4 * s.busy + 0.3 * s.voice)
        // The collar where the shoulders meet.
        let collar = sc(0, 0.44)
        ink.metal(&gc, ink.oval(collar.0, collar.1, 0.34 * 1.2, 0.075 * 1.2), hi: (collar.0 - 0.12, collar.1 - 0.05), reach: 0.45, 1.2)
        ink.rim(&gc, ink.oval(collar.0, collar.1, 0.34 * 1.2, 0.075 * 1.2), 0.55)
        // The neck: rings, lit in front.
        var neckRings = Path()
        for n in 0..<6 {
            let y = -0.02 + 0.075 * Double(n), r = 0.15 + 0.012 * Double(n)
            let c = sc(0, y)
            neckRings.addPath(ink.oval(c.0, c.1, r * 1.2, 0.024 * 1.2))
        }
        gc.stroke(neckRings, with: .color(ink.pal[3].opacity(0.55)), lineWidth: d.px * 1.2)
        let neckTop = sc(0, -0.06), neckBottom = sc(0, 0.38)
        ink.metal(&gc, ink.poly([(neckTop.0 - 0.15, neckTop.1), (neckTop.0 + 0.15, neckTop.1), (neckBottom.0 + 0.18, neckBottom.1), (neckBottom.0 - 0.18, neckBottom.1)]),
                  hi: (neckTop.0 - 0.06, neckTop.1 + 0.1), reach: 0.5, 0.8)
        // The face: smooth champagne metal lit from the upper left, its outline leaning with the head.
        let outline = (0..<40).map { j -> (Double, Double) in
            let a = 2 * Double.pi * Double(j) / 40
            let ny = sin(a), w = ny > 0 ? 1 - 0.3 * ny : 1
            let p = onHead(hw * w * cos(a), hy + hh * ny, 0)
            return (p.x, p.y)
        }
        let facePath = ink.poly(outline)
        let fc = onHead(0, hy, 0)
        ink.metal(&gc, facePath, hi: (fc.x - 0.2, fc.y - 0.36), reach: 1.1, 1.3, floor: 0.6)
        ink.rim(&gc, facePath, 0.4, width: 1.1)
        for j in 0..<Int(520 * k) + 30 {
            let u = 1 - 2 * OrbPoints.hash(j, 1), a = 2 * Double.pi * OrbPoints.hash(j, 2)
            let r = (1 - u * u).squareRoot()
            let nx = r * cos(a), ny = u, nz = r * sin(a)
            guard nz > -0.1 else { continue }
            let w = ny > 0 ? 1 - 0.3 * ny : 1
            let light = max(0, -0.3 * nx - 0.4 * ny + 0.86 * nz)
            putHead(hw * nx * w, hy + hh * ny, hd * nz, 0.1 + 0.3 * light + 0.6 * pow(light, 12), OrbPoints.hash(j, 14), a)
        }
        // The crest over the head and the rivets at the temples.
        let crest = (0...14).map { j -> (Double, Double) in
            let a = -Double.pi / 2 - 0.1 + 0.95 * Double(j) / 14
            let p = onHead(0, hy + hh * 1.005 * sin(a), hd * 1.005 * cos(a)); return (p.x, p.y)
        }
        // The crest down her forehead, glowing with her voice.
        let crestGlow = 0.35 * s.voice + 0.12 * s.busy
        let ridge = Gradient(colors: [ink.pal[3].opacity(0.05), ink.pal[4].opacity(min(1, 0.5 + 0.5 * s.voice)), ink.pal[3].opacity(0.1)])
        if crestGlow > 0.02 {
            gc.stroke(ink.poly(crest, closed: false), with: .linearGradient(Gradient(colors: [.clear, warm.opacity(min(1, crestGlow)), .clear]),
                                                                          startPoint: ink.p(crest[0].0, crest[0].1), endPoint: ink.p(crest[14].0, crest[14].1)),
                      style: StrokeStyle(lineWidth: d.px * 4, lineCap: .round))
        }
        gc.stroke(ink.poly(crest, closed: false), with: .linearGradient(ridge, startPoint: ink.p(crest[0].0, crest[0].1), endPoint: ink.p(crest[14].0, crest[14].1)),
                  lineWidth: d.px * 1.1)
        for side in [-1.0, 1.0] {
            let p = onHead(side * hw * 0.97, -0.62, 0.05)
            ink.metal(&gc, ink.oval(p.x, p.y, 0.05 * 1.2 * 0.5, 0.06 * 1.2), hi: (p.x - 0.01, p.y - 0.03), reach: 0.08, 1.4)
            ink.rim(&gc, ink.oval(p.x, p.y, 0.05 * 1.2 * 0.5, 0.06 * 1.2), 0.6)
        }
        // Her eyes: warm almonds, open and calm (wider as she listens), a soft blink now and then.
        // Heavy lids: calm, softer as she listens, lowered as she thinks, open and lit as she works.
        let lid = (0.74 * calm + 0.66 * s.listen + 0.34 * s.th + 0.98 * s.busy + 0.86 * s.speak) * blink(t, 5.7)
        let eyeB = 0.8 + 0.5 * s.voice + 0.25 * s.listen * s.level + 0.4 * s.busy - 0.2 * s.th + 0.06 * sin(t * 1.3)
        for side in [-1.0, 1.0] {
            let ex = side * 0.16, ey = -0.62, ez = front(ex, ey)
            let inner = onHead(ex - side * 0.095, ey + 0.005, ez), outer = onHead(ex + side * 0.095, ey - 0.012, ez)
            let up = onHead(ex, ey - 0.075 * lid, ez + 0.01), down = onHead(ex, ey + 0.05 * max(0.3, lid), ez + 0.01)
            var almond = Path()
            almond.move(to: ink.p(inner.x, inner.y))
            almond.addQuadCurve(to: ink.p(outer.x, outer.y), control: ink.p(up.x, up.y))
            almond.addQuadCurve(to: ink.p(inner.x, inner.y), control: ink.p(down.x, down.y))
            almond.closeSubpath()
            let c = onHead(ex, ey - 0.008, ez + 0.01)
            ink.glow(&gc, c.x, c.y, 0.2, warm, 0.25 * eyeB)
            gc.fill(almond, with: .radialGradient(Gradient(colors: [warm.opacity(min(1, 0.9 * eyeB)), deep.opacity(min(1, 0.55 * eyeB))]),
                                                  center: ink.p(c.x, c.y), startRadius: 0, endRadius: 0.12 * 1.2 * d.R))
            gc.stroke(almond, with: .color(warm.opacity(min(1, 0.7 * eyeB))), lineWidth: d.px)
            if lid > 0.35 {
                ink.eye(&gc, c.x, c.y, 0.034 * 1.2, eyeB * min(1, 2 * (lid - 0.35)), warm: .white, deep: warm, squash: squash, angle: faceAngle, halo: 0.4)
            }
            // The brow: a fine arc over the eye.
            let b0 = onHead(ex - side * 0.1, ey - 0.1, ez), b1 = onHead(ex + side * 0.11, ey - 0.11, ez), bm = onHead(ex, ey - 0.14, ez + 0.01)
            var brow = Path(); brow.move(to: ink.p(b0.x, b0.y)); brow.addQuadCurve(to: ink.p(b1.x, b1.y), control: ink.p(bm.x, bm.y))
            gc.stroke(brow, with: .color(ink.pal[3].opacity(0.55)), lineWidth: d.px * 1.1)
        }
        // A fine nose, a small smile that opens with her voice.
        let n0 = onHead(0, -0.54, front(0, -0.54) + 0.01), n1 = onHead(0, -0.39, front(0, -0.39) + 0.03)
        var nose = Path(); nose.move(to: ink.p(n0.x, n0.y)); nose.addLine(to: ink.p(n1.x, n1.y))
        gc.stroke(nose, with: .color(ink.pal[3].opacity(0.45)), lineWidth: d.px)
        let open = 0.008 + 0.014 * s.voice
        let ml = onHead(-0.085, -0.3, front(-0.085, -0.3)), mr = onHead(0.085, -0.3, front(0.085, -0.3))
        let mu = onHead(0, -0.29, front(0, -0.29)), md = onHead(0, -0.27 + 2 * open, front(0, -0.27))
        var mouth = Path()
        mouth.move(to: ink.p(ml.x, ml.y))
        mouth.addQuadCurve(to: ink.p(mr.x, mr.y), control: ink.p(mu.x, mu.y))
        mouth.addQuadCurve(to: ink.p(ml.x, ml.y), control: ink.p(md.x, md.y))
        mouth.closeSubpath()
        gc.fill(mouth, with: .color(warm.opacity(0.4 + 0.3 * s.voice)))
        gc.stroke(mouth, with: .color(warm.opacity(0.6 + 0.2 * s.voice)), lineWidth: d.px)
        for r in rings { ring(r, frontHalf: true) }
        finish(&gc, d, tint: tint)
    }

    // MARK: Rover

    /// A shy, curious little rover, seen a little from the side: binocular eyes (lit boxes with big
    /// round warm lenses) on a neck that stretches and shrinks, a boxy body on tracks, two little
    /// arms with claws. Its eyes do the talking: each box tilts on its own like an eyebrow, the
    /// lenses zoom in and out. At rest it looks about, tilts its head, shifts a track and now and
    /// then zooms; listening, it stretches its neck and leans in, eyes wide and lifted, claws clasped
    /// shyly, very still (a little flinch on a sudden loud sound); thinking, its head tilts, one eye
    /// up and one down, its lenses zoom, a claw scratches its head; working, its tracks roll and
    /// bump, its head scans left and right, its lenses focus in quick steps and its meter runs;
    /// speaking, it bobs and wiggles happily, brows up, lenses pulsing with the voice.
    func drawRover(_ gc: inout GraphicsContext, _ box: CGSize) {
        var d = robotCanvas(box, scale: 1.2, dy: -0.18)
        let s = RobotState(engine, work)
        let k = density(box)
        let tint = Color(hex: 0xffb347)
        let ink = Ink(d, robotPalette(tint))
        let warm = look.color ?? Color(hex: 0xffe2a6), deep = look.color ?? Color(hex: 0xff9a3a)
        let calm = max(0, 1 - s.listen - s.th - s.busy - s.speak)
        let h1 = engine.history.value(secondsAgo: 0.08)
        let bounce = s.speak * min(1, 1.5 * h1)                                // its own voice, a moment ago
        // A sudden loud sound as it listens: now louder than a moment ago (smoothed, so never a jump).
        let flinch = s.listen * smoothstep(0.3, 0.7, s.loud - engine.history.value(secondsAgo: 1.0))
        // The tracks: two paces, blended; the body bumps as the treads pass under it.
        let paceSlow = 0.12, paceFast = 1.5
        let bump = 0.012 * (1 - s.busy) * abs(sin(Double.pi * 7 * t * paceSlow)) + 0.028 * s.busy * abs(sin(Double.pi * 7 * t * paceFast))
        let rock = 0.05 * s.busy * sin(t * 1.3) + 0.04 * s.speak * sin(t * 2.6)
        let view = Turn3(yaw: 0.32 + 0.06 * sin(t * 0.2) + 0.05 * s.speak * sin(t * 1.9), pitch: -0.2, roll: 0.035 * s.speak * sin(t * 4.1))
        let sc = 1.05, oy = 0.1
        func at(_ x: Double, _ y: Double, _ z: Double) -> (Double, Double) {
            let p = view.apply(x + rock, y - bump, z); return (p.x * sc, p.y * sc + oy)
        }
        func surf(_ x: Double, _ y: Double, _ z: Double, _ nx: Double, _ ny: Double, _ nz: Double, _ tone: Double, _ dither: Double) {
            let n = view.apply(nx, ny, nz)
            guard n.z > -0.02 else { return }
            let q = at(x, y, z)
            place(&d, q.0, q.1, tone * metal(n.x, n.y, n.z, shine: 0.5), dither, phase: x, lum: 0.6, size: 0.8)
        }
        /// A box: its three faces we see (front, top, a side) in lit metal, a texture of points.
        func block(_ cx: Double, _ cy: Double, _ cz: Double, _ w: Double, _ h: Double, _ dp: Double, tilt: Double = 0,
                   points: Int, seed: Int, tone: Double = 1) {
            let ct = cos(tilt), st = sin(tilt)
            func corner(_ x: Double, _ y: Double, _ z: Double) -> (Double, Double) {
                at(cx + x * ct - y * st, cy + x * st + y * ct, cz + z)
            }
            let faces: [([(Double, Double, Double)], (Double, Double, Double))] = [
                ([(-w / 2, -h / 2, dp / 2), (w / 2, -h / 2, dp / 2), (w / 2, h / 2, dp / 2), (-w / 2, h / 2, dp / 2)], (0, 0, 1)),
                ([(-w / 2, -h / 2, -dp / 2), (w / 2, -h / 2, -dp / 2), (w / 2, -h / 2, dp / 2), (-w / 2, -h / 2, dp / 2)], (st, -ct, 0)),
                ([(w / 2, -h / 2, dp / 2), (w / 2, -h / 2, -dp / 2), (w / 2, h / 2, -dp / 2), (w / 2, h / 2, dp / 2)], (ct, st, 0)),
                ([(-w / 2, -h / 2, -dp / 2), (-w / 2, -h / 2, dp / 2), (-w / 2, h / 2, dp / 2), (-w / 2, h / 2, -dp / 2)], (-ct, -st, 0)),
            ]
            for (corners, normal) in faces {
                let n = view.apply(normal.0, normal.1, normal.2)
                guard n.z > 0.02 else { continue }
                let pts = corners.map { corner($0.0, $0.1, $0.2) }
                let light = tone * (0.35 + 1.5 * metal(n.x, n.y, n.z, shine: 0.6))
                let path = ink.poly(pts)
                ink.face(&gc, path, top: pts[0], bottom: pts[3], light)
                ink.rim(&gc, path, 0.3 * tone, width: 0.9)
            }
            for j in 0..<points {
                let f = evenPoint(seed + j).0, g = evenPoint(seed + j).1, face = OrbPoints.hash(seed + j, 3)
                var x: Double, y: Double, z: Double, nx: Double, ny: Double, nz: Double
                if face < 0.6 { x = (f - 0.5) * w; y = (g - 0.5) * h; z = dp / 2; nx = 0; ny = 0; nz = 1 }
                else if face < 0.8 { x = (f - 0.5) * w; y = -h / 2; z = (g - 0.5) * dp; nx = 0; ny = -1; nz = 0 }
                else { x = -w / 2; y = (f - 0.5) * h; z = (g - 0.5) * dp; nx = -1; ny = 0; nz = 0 }
                let rx = x * ct - y * st, ry = x * st + y * ct
                surf(cx + rx, cy + ry, cz + z, nx * ct - ny * st, nx * st + ny * ct, nz, 0.6 * tone, OrbPoints.hash(seed + j, 14))
            }
        }
        // The tracks: rounded belts, their treads rolling down their faces (a track shifts now and then at rest).
        for side in [-1.0, 1.0] {
            let top = 1.02, bottom = 1.78
            func edge(_ y: Double, _ out: Double) -> (Double, Double) {
                let f = (y - top) / (bottom - top), half = 0.12 + 0.11 * f
                return at(side * (1.13 + out * half), y, 0.32)
            }
            let ys = stride(from: top, through: bottom, by: 0.076).map { $0 }
            let belt = ink.poly(ys.map { edge($0, -1) } + ys.reversed().map { edge($0, 1) })
            ink.metal(&gc, belt, hi: edge(top, -0.6), reach: 0.95, 1.0)
            gc.stroke(belt, with: .color(ink.pal[3].opacity(0.55)), style: StrokeStyle(lineWidth: d.px * 1.6, lineJoin: .round))
            let shift = 0.35 * calm * servoStep(t, period: 4.3, move: 0.3, salt: side + 11)
            for (pace, w) in [(paceSlow, 1 - s.busy), (paceFast, s.busy)] where w > 0.02 {
                var treads = Path()
                for n in 0..<7 {
                    let y = top + (bottom - top) * fract(t * pace + Double(n) / 7 + shift)
                    let a = edge(y, -0.8), b = edge(y, 0.8)
                    treads.move(to: ink.p(a.0, a.1)); treads.addLine(to: ink.p(b.0, b.1))
                }
                gc.stroke(treads, with: .color(ink.pal[3].opacity(0.5 * w)), style: StrokeStyle(lineWidth: d.px * 1.4, lineCap: .round))
            }
            let hub = edge(top + 0.1, 0)
            ink.metal(&gc, ink.circle(hub.0, hub.1, 0.07), hi: (hub.0 - 0.02, hub.1 - 0.03), reach: 0.1, 1.4)
        }
        // The body: a box with a hatch and a lamp.
        block(0, 1.05, 0, 1.9, 1.45, 1.1, points: Int(250 * k) + 30, seed: 6000)
        let hatch = [at(-0.55, 0.98, 0.56), at(0.6, 0.98, 0.56), at(0.6, 1.62, 0.56), at(-0.55, 1.62, 0.56)]
        gc.stroke(ink.poly(hatch), with: .color(ink.pal[3].opacity(0.4)), style: StrokeStyle(lineWidth: d.px * 1.1, lineJoin: .round))
        // Its meter: five lights that rise with your voice as it listens, with its own as it speaks,
        // and run as it works.
        let level = min(1, s.listen * (0.15 + 1.1 * s.level) + s.speak * (0.15 + 1.1 * s.loud) + 0.12 * calm + 0.12 * s.th)
        let runner = fract(t * 1.7) * 6 - 0.5
        var onBars = Path(), offBars = Path()
        for n in 0..<5 {
            let x0 = -0.42 + 0.2 * Double(n)
            let bar = ink.poly([at(x0, 0.62, 0.56), at(x0 + 0.15, 0.62, 0.56), at(x0 + 0.15, 0.8, 0.56), at(x0, 0.8, 0.56)])
            let lit = (1 - s.busy) * (level > Double(n) / 5 + 0.04 ? 1 : 0) + s.busy * (abs(Double(n) - runner) < 0.75 ? 1 : 0)
            if lit > 0.5 { onBars.addPath(bar) } else { offBars.addPath(bar) }
        }
        gc.fill(onBars, with: .color(warm.opacity(0.9)))
        gc.stroke(onBars, with: .color(warm.opacity(0.22)), style: StrokeStyle(lineWidth: d.px * 4, lineJoin: .round))
        gc.fill(offBars, with: .color(ink.pal[2].opacity(0.3)))
        let lampOn = 0.35 * (1 - s.busy) + s.busy * (0.55 + 0.45 * sin(t * 7)) + 0.1 * sin(t)
        let lampAt = at(-0.75, 0.5, 0.56)
        ink.eye(&gc, lampAt.0, lampAt.1, 0.05, lampOn, warm: warm, deep: deep, catchlight: 0)
        // The head's pose: each state's own motion at a fixed pace, blended.
        let peek = servoStep(t, period: 3.3, move: 0.3, salt: 2.7)             // rest: looking about
        let curious = servoStep(t, period: 5.1, move: 0.25, salt: 8.1)
        let scanX = sin(t * 1.5)                                               // working: scanning
        let stretch = 0.3 * s.listen * (1 - 0.5 * flinch) - 0.08 * flinch + 0.06 * s.th + 0.1 * s.busy + 0.12 * s.speak
            + 0.13 * bounce + 0.02 * sin(t * 0.9) + 0.04 * calm * max(0, curious)
        let neckBase = (x: 0.0, y: 0.33), neckLen = 0.88 + stretch
        let lean = 0.34 * s.listen * (1 - 0.5 * flinch) + 0.06 * s.speak                       // toward you
        let hx = calm * 0.1 * peek + s.busy * 0.2 * scanX + s.th * 0.05 + s.speak * 0.04 * sin(t * 2.1)
        let hy = neckBase.y - neckLen
        let roll = calm * (0.06 * curious + 0.02 * sin(t * 0.7)) + s.th * 0.2 + s.speak * 0.08 * sin(t * 2.3) + s.busy * 0.04 * scanX
        let grow = 1 + 0.1 * s.listen * (1 - 0.5 * flinch) + 0.03 * bounce
        let lookX = calm * 0.07 * peek + s.busy * 0.09 * scanX + s.th * 0.05 * sin(t * 0.6) + s.listen * 0.02
        // Its arms: hanging at rest, claws clasped shyly as it listens, one up scratching its head
        // as it thinks, both busy as it works, waving as it speaks.
        var arms = Path(), claws = Path()
        var shoulders: [(Double, Double)] = []
        for side in [-1.0, 1.0] {
            let sh = (side * 0.97, 0.95, 0.25)
            let scratch = 0.05 * sin(t * 9) * s.th
            let thinker = side > 0 ? 1.0 : 0.0
            let waver = side > 0 ? 1.0 : 0.0
            let busyA = sin(t * 3.4 + (side > 0 ? 0 : 2.2))
            var cx = calm * side * 1.04 + s.listen * side * 0.52 + s.busy * side * (1.02 + 0.06 * busyA) + s.speak * side * (1.12 + 0.05 * waver)
            var cy = calm * (1.4 + 0.03 * sin(t * 0.8 + side)) + s.listen * 0.98 + s.busy * (1.32 + 0.1 * busyA) + s.speak * (1.05 - 0.45 * waver - 0.1 * bounce)
            var cz = calm * 0.8 + s.listen * 1.0 + s.busy * (0.65 + 0.16 * busyA) + s.speak * 0.6
            cx += s.th * (thinker * (hx + 0.34 + 0.6 * scratch) + (1 - thinker) * side * 1.06)
            cy += s.th * (thinker * (hy + 0.42 + scratch) + (1 - thinker) * 1.48)
            cz += s.th * (thinker * (lean + 0.4) + (1 - thinker) * 0.6)
            cy -= s.speak * waver * 0.1 * sin(t * 4.6)
            let a = at(sh.0, sh.1, sh.2), c = at(cx, cy, cz)
            arms.move(to: ink.p(a.0, a.1)); arms.addLine(to: ink.p(c.0, c.1))
            shoulders.append(a)
            // The claw: two paddles, opening as it waves, shut as it clasps.
            let dir = atan2(c.1 - a.1, c.0 - a.0)
            let open = 0.35 + 0.25 * s.speak + 0.2 * s.busy * (0.5 + 0.5 * busyA) - 0.25 * s.listen
            for f in [-1.0, 1.0] {
                let fa = dir + f * open
                claws.move(to: ink.p(c.0, c.1)); claws.addLine(to: ink.p(c.0 + 0.14 * cos(fa), c.1 + 0.14 * sin(fa)))
            }
        }
        litStroke(&gc, ink, arms, width: 0.12, 0.6, hi: 0.2)
        for a in shoulders { ink.metal(&gc, ink.circle(a.0, a.1, 0.1), hi: (a.0 - 0.03, a.1 - 0.03), reach: 0.14, 1.3) }
        litStroke(&gc, ink, claws, width: 0.095, 0.75, hi: 0.3)
        // The neck: a column that stretches and shrinks, its joint at the base.
        let neckTop = at(hx, hy + 0.05, lean * 0.8), neckBottom = at(0, neckBase.y, 0)
        var neck = Path(); neck.move(to: ink.p(neckTop.0, neckTop.1)); neck.addLine(to: ink.p(neckBottom.0, neckBottom.1))
        gc.stroke(neck, with: .linearGradient(Gradient(colors: [ink.pal[3].opacity(0.75), ink.pal[2].opacity(0.4)]),
                                              startPoint: ink.p(neckTop.0 - 0.06, 0), endPoint: ink.p(neckTop.0 + 0.06, 0)), lineWidth: 0.11 * sc * d.R)
        var rungs = Path()
        for n in 1..<4 {
            let f = Double(n) / 4, x = neckTop.0 + (neckBottom.0 - neckTop.0) * f, y = neckTop.1 + (neckBottom.1 - neckTop.1) * f
            rungs.move(to: ink.p(x - 0.065, y)); rungs.addLine(to: ink.p(x + 0.065, y))
        }
        gc.stroke(rungs, with: .color(ink.pal[1].opacity(0.8)), lineWidth: d.px * 1.2)
        let joint = at(0, 0.33, 0.02)
        ink.metal(&gc, ink.circle(joint.0, joint.1, 0.09), hi: (joint.0 - 0.03, joint.1 - 0.04), reach: 0.13, 1.3)
        // The bracket that carries both eyes, on top of the neck.
        let b0 = at(hx - 0.15 * grow * cos(roll), hy - 0.15 * grow * sin(roll), lean), b1 = at(hx + 0.15 * grow * cos(roll), hy + 0.15 * grow * sin(roll), lean)
        var bracket = Path(); bracket.move(to: ink.p(b0.0, b0.1)); bracket.addLine(to: ink.p(b1.0, b1.1))
        gc.stroke(bracket, with: .color(ink.pal[3].opacity(0.7)), style: StrokeStyle(lineWidth: 0.1 * d.R, lineCap: .round))
        // The eyes: lit boxes that tilt like eyebrows, big round warm lenses that zoom.
        let zoomTurn = engine.ringTurn * 4
        for side in [-1.0, 1.0] {
            // Its brows: sweet (inner ends up) at rest, now and then one lifted in curiosity; lifted
            // as it listens; one up and one down, puzzled, as it thinks; up and happy as it speaks.
            let lift1 = calm * 0.06 * max(0, curious * side) + s.listen * 0.06 + s.th * 0.08 * side + s.speak * (0.05 + 0.05 * bounce)
            let outerUp = calm * (-0.13 + 0.12 * max(0, curious * side)) + s.listen * 0.1 + s.th * 0.22 * side + s.speak * 0.16 - s.busy * 0.02
            let tilt = roll - side * outerUp
            let cr = cos(roll), sr = sin(roll)
            let ox = side * 0.45 * grow, oyE = -lift1
            let ex = hx + ox * cr - oyE * sr, ey = hy + ox * sr + oyE * cr, ez = lean
            block(ex, ey, ez, 0.62 * grow, 0.5 * grow, 0.44 * grow, tilt: tilt, points: Int(100 * k) + 14, seed: side > 0 ? 1000 : 3000)
            let ct = cos(tilt), st = sin(tilt)
            let lx = lookX * grow
            let c = at(ex + lx * ct, ey + lx * st, ez + 0.225 * grow)
            let n = view.apply(0, 0, 1)
            let squash = n.z, angle = atan2(n.y, n.x)
            // The zoom: wide as it listens, in and out as it thinks, quick focusing steps as it works.
            let zoom = 1 + 0.08 * s.listen + 0.14 * s.th * sin(t * 1.25 + side * 0.9) + 0.09 * s.busy * servoStep(t, period: 0.55, move: 0.3, salt: side + 4)
                + 0.05 * calm * smoothstep(0.6, 1, sin(t * 0.37)) + 0.06 * bounce
            let rr = 0.215 * grow
            ink.metal(&gc, ink.oval(c.0, c.1, rr * squash, rr, angle: angle), hi: (c.0 - 0.07, c.1 - 0.08), reach: 0.3, 1.2)
            ink.rim(&gc, ink.oval(c.0, c.1, rr * squash, rr, angle: angle), 0.7, width: 1.2)
            let lensB = 0.62 + 0.45 * s.voice + 0.35 * s.listen * (0.4 + s.level) + 0.12 * s.busy + 0.05 * sin(t * 1.4 + side)
            ink.eye(&gc, c.0, c.1, 0.175 * grow * min(1.08, zoom), lensB, warm: warm, deep: deep, squash: squash, angle: angle, open: blink(t, 6.7))
            // The zoom ring (turning as it zooms) and the aperture.
            let ring = ink.oval(c.0, c.1, 0.155 * grow * squash, 0.155 * grow, angle: angle)
            gc.stroke(ring, with: .color(ink.pal[4].opacity(0.25 + 0.35 * s.th + 0.25 * s.busy)),
                      style: StrokeStyle(lineWidth: d.px * 1.4, dash: [CGFloat(0.05 * d.R), CGFloat(0.04 * d.R)],
                                         dashPhase: CGFloat((zoomTurn + 3 * (zoom - 1)) * side * 0.09 * d.R)))
            let aperture = (0.1 + 0.03 * s.listen - 0.02 * s.voice) * (2 - zoom) * grow
            gc.stroke(ink.oval(c.0, c.1, aperture * squash, aperture, angle: angle), with: .color(Color.white.opacity(0.35 + 0.3 * s.voice)), lineWidth: d.px)
        }
        finish(&gc, d, tint: tint)
    }

}
