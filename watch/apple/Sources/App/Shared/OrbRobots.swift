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

/// What the robot is doing now, from the engine and the work.
private struct RobotState {
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
private struct Ink {
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
    private func density(_ box: CGSize) -> Double { Double(pointBudget(box)) / 1820 }

    /// The robot's canvas: the planet's units scaled by `scale` (a robot fills more of the frame than
    /// the planet), its centre moved down by `dy` (in halves of the frame).
    private func robotCanvas(_ box: CGSize, scale: Double, dy: Double = 0) -> DotCanvas {
        let half = Double(min(box.width, box.height)) / 2
        return DotCanvas(cx: Double(box.width) / 2, cy: Double(box.height) / 2 + dy * half, R: half * 0.46 * scale, px: max(0.55, half / 95))
    }

    /// The robot's palette (an entity's colour wins).
    private func robotPalette(_ tint: Color) -> [Color] { OrbPalette.colors(for: look.color ?? tint) }

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

    /// A gilded humanoid robot, head and shoulders, polished metal: big round warm eyes that blink
    /// now and then, a gentle smile, ear lamps, a ribbed neck, plated shoulders. Listening, it cocks
    /// its head and its ear lamps glow with your voice; thinking, it turns aside and looks up, its
    /// eyes dimming softly; working, a light scans across its eyes; speaking, its smile opens with
    /// the voice and it talks with its whole head.
    func drawValet(_ gc: inout GraphicsContext, _ box: CGSize) {
        var d = robotCanvas(box, scale: 1.2, dy: 0.04)
        let s = RobotState(engine, work)
        let k = density(box)
        let tint = Color(hex: 0xf0bd52)
        let ink = Ink(d, robotPalette(tint))
        let warm = look.color ?? Color(hex: 0xffe3a3), deep = look.color ?? Color(hex: 0xffa53a)
        let yaw = 0.12 * sin(t * 0.27) + 0.32 * s.th + 0.1 * s.speak * sin(t * 1.3)
        let pitch = 0.04 * sin(t * 0.21) - 0.12 * s.th + 0.05 * s.voice * sin(t * 5.2)
        let roll = 0.04 * sin(t * 0.19) + 0.18 * s.listen + 0.08 * s.speak * sin(t * 1.7)
        let head = Turn3(yaw: yaw, pitch: pitch, roll: roll), body = Turn3(yaw: 0.05 * sin(t * 0.2), pitch: 0.12)
        let hy = -0.5, hw = 0.62, hh = 0.7, hd = 0.56
        let scale = 1.0
        func onScreen(_ p: (x: Double, y: Double, z: Double), _ cy: Double) -> (Double, Double) { (p.x * scale, (p.y + cy) * scale + 0.05) }
        func surf(_ turn: Turn3, _ cy: Double, _ x: Double, _ y: Double, _ z: Double, _ nx: Double, _ ny: Double, _ nz: Double,
                  _ tone: Double, _ dither: Double, shine: Double = 1.1) {
            let n = turn.apply(nx, ny, nz)
            guard n.z > -0.02 else { return }
            let q = onScreen(turn.apply(x, y - cy, z), cy)
            place(&d, q.0, q.1, tone * metal(n.x, n.y, n.z, shine: shine), dither, phase: x, lum: 0.7, size: 0.85)
        }
        /// A point of the face (head coordinates) on the screen.
        func face(_ x: Double, _ y: Double, _ z: Double) -> (Double, Double) { onScreen(head.apply(x, y - hy, z), hy) }
        func front(_ x: Double, _ y: Double) -> Double {
            let ny = (y - hy) / hh, w = hw * (ny > 0 ? 1 - 0.25 * ny : 1)
            return hd * max(0, 1 - pow(x / w, 2) - ny * ny).squareRoot() + 0.012
        }
        let facing = head.apply(0, 0, 1)                                   // the face's normal
        let squash = max(0.2, facing.z), faceAngle = atan2(facing.y, facing.x)
        // Shoulders and chest: the top of a broad plated shell, fading into the dark below.
        let shoulders = (0...30).map { j -> (Double, Double) in
            let a = Double.pi + Double.pi * Double(j) / 30
            return onScreen(body.apply(1.5 * cos(a), 1.0 * sin(a), 0), 1.5)
        } + [onScreen(body.apply(1.5, 0.6, 0), 1.5), onScreen(body.apply(-1.5, 0.6, 0), 1.5)]
        let shell = ink.poly(shoulders)
        ink.metal(&gc, shell, hi: (-0.55, 0.72), reach: 1.6, 1.15, floor: 0)
        ink.rim(&gc, ink.poly(Array(shoulders.prefix(31)), closed: false), 0.4, width: 1.2)
        // The neck: a lit column.
        let neckTop = onScreen(body.apply(0, 0.08, 0), 0), neckBottom = onScreen(body.apply(0, 0.56, 0), 0)
        let neck = ink.poly([(neckTop.0 - 0.17, neckTop.1), (neckTop.0 + 0.17, neckTop.1), (neckBottom.0 + 0.19, neckBottom.1), (neckBottom.0 - 0.19, neckBottom.1)])
        ink.metal(&gc, neck, hi: (neckTop.0 - 0.07, neckTop.1 + 0.1), reach: 0.55, 0.9)
        // The head: polished metal, lit from the upper left, its outline leaning with the head.
        let outline = (0..<40).map { j -> (Double, Double) in
            let a = 2 * Double.pi * Double(j) / 40
            let ny = sin(a), w = ny > 0 ? 1 - 0.25 * ny : 1
            let x = hw * w * cos(a), y = hh * ny
            let c = cos(roll), sn = sin(roll)
            return ((x * c - y * sn) * scale + 0.5 * hd * sin(yaw) * 0.3, (x * sn + y * c + hy) * scale + 0.05)
        }
        let headPath = ink.poly(outline)
        let hc = face(0, hy, 0)
        ink.metal(&gc, headPath, hi: (hc.0 - 0.24, hc.1 - 0.36), reach: 1.05, 1.25, floor: 0.6)
        ink.rim(&gc, headPath, 0.4, width: 1.1)
        // Ears: discs at the sides, a lamp in each that glows as it listens.
        for side in [-1.0, 1.0] {
            let n = head.apply(side, 0, 0.2)
            let c = face(side * (hw + 0.015), -0.48, 0)
            let ear = ink.oval(c.0, c.1, 0.13 * max(0.15, abs(n.z) + 0.15), 0.13, angle: atan2(n.y, n.x))
            ink.metal(&gc, ear, hi: (c.0 - 0.04, c.1 - 0.05), reach: 0.2, 1.2)
            ink.rim(&gc, ear, 0.45)
            ink.glow(&gc, c.0, c.1, 0.11, warm, 0.25 + 0.6 * s.listen * (0.3 + s.level))
        }
        // The head's surface in points (its seams left open).
        for j in 0..<Int(760 * k) + 40 {
            let u = 1 - 2 * evenPoint(j).0, a = 2 * Double.pi * evenPoint(j).1
            let r = (1 - u * u).squareRoot()
            let nx = r * cos(a), ny = u, nz = r * sin(a)
            if abs(nx - 0.62) < 0.025 || abs(nx + 0.62) < 0.025 || abs(ny + 0.45) < 0.02 { continue }
            let w = ny > 0 ? 1 - 0.25 * ny : 1
            surf(head, hy, hw * nx * w, hy + hh * ny, hd * nz, nx, ny, nz, 0.75, OrbPoints.hash(j, 14))
        }
        // The eyes: big, round, warm (brighter as it speaks, dimming softly as it thinks, scanned as it works).
        let soft = 1 - 0.15 * s.th * (0.5 + 0.5 * sin(t * 2.2))
        let eyeGlow = (0.7 + 0.36 * s.voice + 0.18 * s.listen + 0.06 * sin(t * 1.1)) * soft
        let scan = sin(t * 3)
        let open = blink(t, 4.6)
        for side in [-1.0, 1.0] {
            let ex = side * 0.23, ey = -0.55
            let c = face(ex, ey, front(ex, ey))
            ink.metal(&gc, ink.oval(c.0, c.1, 0.15 * squash, 0.15, angle: faceAngle), hi: (c.0 - 0.05, c.1 - 0.06), reach: 0.22, 0.9)
            ink.eye(&gc, c.0, c.1, 0.11, eyeGlow, warm: warm, deep: deep, squash: squash, angle: faceAngle, open: open)
            if s.busy > 0.01 { ink.glow(&gc, c.0 + 0.07 * scan * squash, c.1, 0.06, .white, 0.7 * s.busy) }
        }
        // The smile: gentle at rest, opening with the voice.
        let opening = 0.015 + 0.075 * s.voice
        let left = face(-0.17, -0.2, front(-0.17, -0.2)), right = face(0.17, -0.2, front(0.17, -0.2))
        let upperMid = face(0, -0.175, front(0, -0.18)), lowerMid = face(0, -0.15 + opening, front(0, -0.15))
        var mouth = Path()
        mouth.move(to: ink.p(left.0, left.1))
        mouth.addQuadCurve(to: ink.p(right.0, right.1), control: ink.p(2 * upperMid.0 - (left.0 + right.0) / 2, 2 * upperMid.1 - (left.1 + right.1) / 2))
        mouth.addQuadCurve(to: ink.p(left.0, left.1), control: ink.p(2 * lowerMid.0 - (left.0 + right.0) / 2, 2 * lowerMid.1 - (left.1 + right.1) / 2))
        mouth.closeSubpath()
        let smile = 0.45 + 0.6 * s.voice
        gc.fill(mouth, with: .color(warm.opacity(min(1, 0.55 * smile))))
        gc.stroke(mouth, with: .color(warm.opacity(min(1, 0.7 * smile))), lineWidth: d.px * 1.1)
        ink.glow(&gc, (left.0 + right.0) / 2, upperMid.1 + 0.02, 0.22, warm, 0.18 * smile)
        // The neck's ribs and the shoulders' surface in points.
        for j in 0..<Int(150 * k) + 10 {
            let a = 2 * Double.pi * evenPoint(j).0, y = 0.15 + 0.38 * evenPoint(j).1
            if abs(sin(y * 80)) < 0.3 { continue }
            surf(body, 0, 0.18 * sin(a), y, 0.18 * cos(a), sin(a), 0, cos(a), 0.9, OrbPoints.hash(j, 14))
        }
        for j in 0..<Int(560 * k) + 30 {
            let u = evenPoint(j).0, a = 2 * Double.pi * evenPoint(j).1
            let el = 0.15 + 1.25 * u
            let nx = cos(el) * cos(a), ny = -sin(el), nz = cos(el) * sin(a)
            let x = 1.5 * nx, y = 1.5 + 1.0 * ny, z = 0.6 * nz
            guard y > 0.5, y < 1.7 else { continue }
            if abs(abs(x) - 0.64) < 0.02 { continue }                          // plate seams
            surf(body, 0, x, y, z, nx, ny * 1.4, nz, 0.85 * (1 - smoothstep(1.1, 1.65, y)), OrbPoints.hash(j, 14))
        }
        // The chest lamp: round and warm, pulsing while it works.
        let lamp = onScreen(body.apply(0, 0.92, 0.62), 0)
        ink.eye(&gc, lamp.0, lamp.1, 0.085, 0.45 + 0.4 * s.busy * (0.5 + 0.5 * sin(t * 7)) + 0.3 * s.voice, warm: warm, deep: deep, catchlight: 0.6)
        finish(&gc, d, tint: tint)
    }

    // MARK: Retro

    /// A robot of the fifties: a glass dome with its works glowing inside, antennae with spinning
    /// discs, a face plate with two round warm eyes over a grille of lights, a barrel chest with
    /// dials. Listening, the discs spin and the works glow with your voice; thinking, the works spin
    /// and the grille runs a chase; working, the chest's dials swing and its lamps pulse; speaking,
    /// the grille's columns light with the voice's bands.
    func drawRetro(_ gc: inout GraphicsContext, _ box: CGSize) {
        var d = robotCanvas(box, scale: 1.26, dy: -0.04)
        let s = RobotState(engine, work)
        let k = density(box)
        let tint = Color(hex: 0x5be3b4)
        let ink = Ink(d, robotPalette(tint))
        let warm = look.color ?? Color(hex: 0xffdc8f), deep = look.color ?? Color(hex: 0xff9f45)
        let turn = Turn3(yaw: 0.1 * sin(t * 0.23), pitch: 0.15)
        let oy = -0.08
        func at(_ x: Double, _ y: Double, _ z: Double) -> (Double, Double) { let p = turn.apply(x, y, z); return (p.x, p.y + oy) }
        func surf(_ x: Double, _ y: Double, _ z: Double, _ nx: Double, _ ny: Double, _ nz: Double, _ tone: Double, _ dither: Double, shine: Double = 0.7) {
            let n = turn.apply(nx, ny, nz)
            guard n.z > -0.02 else { return }
            let p = turn.apply(x, y, z)
            place(&d, p.x, p.y + oy, tone * metal(n.x, n.y, n.z, shine: shine), dither, phase: x, lum: 0.6, size: 0.8 + 0.3 * smoothstep(-1, 1, p.z))
        }
        // The chest: a barrel, lit metal fading into the dark below, three grooves round it.
        func chestWidth(_ y: Double) -> Double { 0.86 + 0.18 * sin(min(1, (y - 0.1) / 1.2) * .pi * 0.9) }
        let left = stride(from: 0.12, through: 1.9, by: 0.12).map { y in at(-chestWidth(y), y, 0) }
        let right = stride(from: 1.9, through: 0.12, by: -0.12).map { y in at(chestWidth(y), y, 0) }
        let w0 = chestWidth(0.12)
        let top = (1..<16).map { j -> (Double, Double) in
            let az = Double.pi / 2 - Double.pi * Double(j) / 16
            return at(w0 * sin(az), 0.12, 0.62 * w0 * cos(az))
        }
        ink.metal(&gc, ink.poly(left + right + top), hi: (-0.42, 0.42), reach: 1.75, 1.2, floor: 0)
        ink.rim(&gc, ink.poly([at(-w0, 0.12, 0)] + top + [at(w0, 0.12, 0)], closed: false), 0.4)
        for (n, gy) in [0.3, 1.05, 1.3].enumerated() {
            let w = chestWidth(gy)
            let groove = (0...20).map { j -> (Double, Double) in
                let az = -Double.pi / 2 + Double.pi * Double(j) / 20
                return at(w * sin(az), gy, 0.62 * w * cos(az))
            }
            gc.stroke(ink.poly(groove, closed: false), with: .color(ink.pal[3].opacity(0.32 - 0.08 * Double(n))), lineWidth: d.px)
        }
        // The chest in points, its grooves left open.
        for j in 0..<Int(320 * k) + 24 {
            let y = 0.16 + 1.4 * evenPoint(j).0, az = Double.pi * (evenPoint(j).1 - 0.5) * 0.92
            if abs(sin(y * 30)) < 0.16 { continue }
            let w = chestWidth(y)
            let nx = sin(az), nz = cos(az)
            surf(w * nx, y, 0.62 * w * nz, nx, 0, nz, 0.45 * (1 - smoothstep(1.0, 1.55, y)), OrbPoints.hash(j, 14))
        }
        // The dials: rims, swinging needles, and a warm lamp under each (pulsing as it works).
        for (n, dx) in [-0.32, 0.0, 0.32].enumerated() {
            let c = at(dx, 0.58, 0.68)
            ink.metal(&gc, ink.circle(c.0, c.1, 0.1), hi: (c.0 - 0.03, c.1 - 0.04), reach: 0.14, 1.1)
            ink.rim(&gc, ink.circle(c.0, c.1, 0.1), 0.7, width: 1.1)
            let needle = 0.8 * sin(t * (0.7 + 0.4 * Double(n)) + Double(n)) + 1.3 * s.busy * sin(t * 6 + Double(n))
            var line = Path()
            line.move(to: ink.p(c.0, c.1)); line.addLine(to: ink.p(c.0 + 0.08 * sin(needle), c.1 - 0.08 * cos(needle)))
            gc.stroke(line, with: .color(ink.pal[4].opacity(0.85)), lineWidth: d.px * 1.1)
            let pulse = 0.35 * (1 - s.busy) + s.busy * (0.55 + 0.45 * sin(t * 6 + 2 * Double(n)))
            let l = at(dx, 0.84, 0.66)
            ink.eye(&gc, l.0, l.1, 0.035, pulse, warm: warm, deep: deep, catchlight: 0)
        }
        // The face plate: a broad lit plate, two round warm eyes, the grille of lights.
        let plate = at(0, -0.14, 0.66)
        ink.metal(&gc, ink.oval(plate.0, plate.1, 0.54, 0.25), hi: (plate.0 - 0.2, plate.1 - 0.12), reach: 0.6, 1.2, floor: 0.6)
        ink.rim(&gc, ink.oval(plate.0, plate.1, 0.54, 0.25), 0.45)
        let eyeB = 0.85 + 0.4 * s.listen * s.level + 0.3 * s.voice + 0.1 * sin(t * 1.2)
        for side in [-1.0, 1.0] {
            let e = at(side * 0.2, -0.22, 0.72)
            ink.eye(&gc, e.0, e.1, 0.075, eyeB, warm: warm, deep: deep, open: blink(t, 6.1))
        }
        var lit = Path(), dim = Path(), glowPath = Path()
        let columns = 7, chase = Int(t * 8) % columns
        for c in 0..<columns {
            let cx = -0.27 + 0.09 * Double(c)
            let voice = s.speak * min(1, 1.6 * s.spectrum.band(at: Double(c) / Double(columns - 1)) + 0.3 * s.loud)
            for r in 0..<3 {
                let shown = voice > (2 - Double(r)) / 2 * 0.8 ? voice : 0
                let on = 0.12 + 0.9 * shown + s.th * (chase == c ? 0.9 : 0) + 0.08 * sin(t * 0.8 + Double(c))
                let g = at(cx, -0.06 + 0.06 * Double(r), 0.72)
                if on > 0.5 { lit.addPath(ink.circle(g.0, g.1, 0.026)); glowPath.addPath(ink.circle(g.0, g.1, 0.06)) }
                else { dim.addPath(ink.circle(g.0, g.1, 0.022)) }
            }
        }
        gc.fill(glowPath, with: .color(warm.opacity(0.22)))
        gc.fill(lit, with: .color(warm.opacity(0.95)))
        gc.fill(dim, with: .color(ink.pal[2].opacity(0.4)))
        // The dome's collar: a metal band.
        let collar = ink.poly([at(-0.7, -0.5, 0.0), at(0.7, -0.5, 0.0), at(0.7, -0.41, 0.0), at(-0.7, -0.41, 0.0)])
        ink.metal(&gc, collar, hi: (-0.3, -0.56), reach: 0.9, 1.3)
        ink.rim(&gc, collar, 0.5)
        // The glass dome: clear in the middle, lit at its rim, two soft reflections.
        let dc = at(0, -0.48, 0), dr = 0.64
        let half = ink.poly((0...28).map { j -> (Double, Double) in
            let a = Double.pi + Double.pi * Double(j) / 28
            return (dc.0 + dr * cos(a), dc.1 + dr * sin(a))
        })
        let glassStops: [Gradient.Stop] = [.init(color: ink.pal[1].opacity(0.05), location: 0), .init(color: ink.pal[2].opacity(0.08), location: 0.6),
                                           .init(color: ink.pal[3].opacity(0.32), location: 0.94), .init(color: ink.pal[4].opacity(0.45), location: 1)]
        gc.fill(half, with: .radialGradient(Gradient(stops: glassStops), center: ink.p(dc.0, dc.1), startRadius: 0, endRadius: dr * d.R))
        // The works inside: a warm core, two gyro rings turning round it.
        let spin = engine.ringTurn * 3 + t * 0.6 + engine.swirl * 2.5
        let coreB = 0.6 + 0.6 * s.listen * s.level + 0.4 * s.th + 0.2 * s.voice
        let works = (x: dc.0, y: dc.1 - 0.32)
        for (n, (r, tilt)) in [(0.22, 0.4), (0.16, -0.9)].enumerated() {
            let ring = ink.oval(works.x, works.y, r, r * abs(cos(tilt + Double(n) * spin * 0.3)) * 0.5 + 0.02, angle: 0.2 * sin(spin * 0.5 + Double(n)))
            gc.stroke(ring, with: .color(ink.pal[3].opacity(0.25)), lineWidth: d.px * 3.5)
            gc.stroke(ring, with: .color(ink.pal[4].opacity(0.7)), lineWidth: d.px * 0.9)
            let a = spin * (n == 0 ? 1 : -1.3)
            ink.glow(&gc, works.x + r * cos(a), works.y + r * sin(a) * abs(cos(tilt)) * 0.5, 0.05, ink.pal[4], 0.8)
        }
        ink.glow(&gc, works.x, works.y, 0.14, warm, 0.45 * coreB)
        ink.glow(&gc, works.x, works.y, 0.045, .white, 0.8 * coreB)
        let shine = Gradient(colors: [Color.white.opacity(0.24), .clear])
        gc.fill(ink.oval(dc.0 - 0.3, dc.1 - 0.4, 0.2, 0.08, angle: -0.75),
                with: .linearGradient(shine, startPoint: ink.p(dc.0 - 0.42, dc.1 - 0.52), endPoint: ink.p(dc.0 - 0.18, dc.1 - 0.28)))
        gc.fill(ink.oval(dc.0 + 0.4, dc.1 - 0.3, 0.035, 0.12, angle: 0.65), with: .color(.white.opacity(0.12)))
        for j in 0..<Int(260 * k) + 20 {                                       // sparkle on the glass's rim
            let a = Double.pi + Double.pi * evenPoint(j).0
            let r = dr * (0.97 + 0.03 * evenPoint(j).1)
            place(&d, dc.0 + r * cos(a), dc.1 + r * sin(a), 0.32 + 0.4 * pow(max(0, -cos(a - 0.6)), 2), OrbPoints.hash(j, 14), phase: a, lum: 0.9, size: 0.85)
        }
        // The antennae: rods, discs spinning (faster with your voice and as it thinks), warm tips.
        let discSpin = t * 1.4 + engine.swirl * 7 + engine.ringTurn * 3
        for side in [-1.0, 1.0] {
            let base = at(side * 0.6, -0.72, 0), tip = at(side * 0.98, -1.02, 0)
            var rod = Path(); rod.move(to: ink.p(base.0, base.1)); rod.addLine(to: ink.p(tip.0, tip.1))
            gc.stroke(rod, with: .color(ink.pal[3].opacity(0.7)), lineWidth: d.px * 1.4)
            let w = abs(cos(discSpin * side))
            let disc = ink.oval(tip.0, tip.1, 0.17 * max(0.08, w), 0.17)
            ink.metal(&gc, disc, hi: (tip.0 - 0.06 * w, tip.1 - 0.07), reach: 0.24, 1.2)
            ink.rim(&gc, disc, 0.6)
            ink.eye(&gc, tip.0, tip.1, 0.04, 0.6 + 0.6 * s.listen * s.level + 0.3 * s.th, warm: warm, deep: deep, catchlight: 0)
        }
        finish(&gc, d, tint: tint)
    }

    // MARK: Deco

    /// An art-deco machine woman: a long serene metal face (warm almond eyes, a fine nose, a small
    /// smile), a crest over the head and rivets at the temples, a tall neck of rings, sculpted
    /// shoulders and a sunburst on the chest. Rings of light pass around her: rising from her chest
    /// as she speaks (brighter with the voice), coming down onto her head as she listens (her eyes
    /// open wide), sweeping slowly up and down as she thinks; working, the sunburst glows in turn.
    func drawDeco(_ gc: inout GraphicsContext, _ box: CGSize) {
        var d = robotCanvas(box, scale: 1.12, dy: 0.02)
        let s = RobotState(engine, work)
        let k = density(box)
        let tint = Color(hex: 0xe8d6a8)
        let ink = Ink(d, robotPalette(tint))
        let warm = look.color ?? Color(hex: 0xffe1a8), deep = look.color ?? Color(hex: 0xf3a55a)
        let head = Turn3(yaw: 0.1 * sin(t * 0.21) + 0.06 * s.th, pitch: 0.03 * sin(t * 0.17) - 0.06 * s.th, roll: 0.03 * sin(t * 0.13))
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
        // The rings of light around her: behind her first (dim), in front of her last.
        var rings: [(y: Double, b: Double)] = []
        let rest = fract(t * 0.15)
        rings.append((1.5 - 3.0 * rest, 0.3 * max(0, 1 - s.speak - s.listen - s.th) * sin(Double.pi * rest)))
        for n in 0..<3 {
            let f = fract(t * 0.45 + Double(n) / 3)
            rings.append((1.4 - 2.6 * f, s.speak * (0.2 + 0.9 * engine.history.value(secondsAgo: f * 1.0)) * sin(Double.pi * f)))
            rings.append((-1.2 + 1.0 * f, s.listen * (0.25 + 0.8 * s.level) * (1 - f * 0.6) * min(1, 6 * f)))
            rings.append((0.2 + 1.1 * sin(t * 0.6 + Double(n) * 2.1), s.th * 0.7))
        }
        func ring(_ r: (y: Double, b: Double), frontHalf: Bool) {
            guard r.b > 0.02 else { return }
            let rx = r.y > 0.2 ? 1.25 : 0.66, ry = 0.12 * rx
            let arc = (0...24).map { j -> (Double, Double) in
                let a = (frontHalf ? 0 : Double.pi) + Double.pi * Double(j) / 24
                return sc(rx * cos(a), r.y + ry * sin(a))
            }
            let path = ink.poly(arc, closed: false)
            let a = r.b * (frontHalf ? 1 : 0.35)
            gc.stroke(path, with: .color(warm.opacity(min(1, 0.3 * a))), lineWidth: d.px * 5)
            gc.stroke(path, with: .color(ink.pal[4].opacity(min(1, 0.9 * a))), lineWidth: d.px * 1.1)
        }
        for r in rings { ring(r, frontHalf: false) }
        // The shoulders: sculpted plates between three arcs each side; the sunburst on her chest.
        for side in [-1.0, 1.0] {
            let upper = (0...16).map { j -> (Double, Double) in let f = Double(j) / 16; return sc(side * (0.22 + 1.2 * f), 0.42 + 0.42 * f * f) }
            let lower = (0...16).reversed().map { j -> (Double, Double) in let f = Double(j) / 16; return sc(side * (0.22 + 1.2 * f), 0.6 + 0.42 * f * f) }
            ink.metal(&gc, ink.poly(upper + lower), hi: sc(side * 0.45, 0.42), reach: 1.4, 1.0, floor: 0)
            for arc in 0..<3 {
                let line = (0...16).map { j -> (Double, Double) in let f = Double(j) / 16; return sc(side * (0.22 + 1.2 * f), 0.42 + 0.09 * Double(arc) + 0.42 * f * f) }
                gc.stroke(ink.poly(line, closed: false), with: .color(ink.pal[3].opacity(0.55 - 0.15 * Double(arc))), lineWidth: d.px * 1.1)
            }
        }
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
        for n in 0..<6 {
            let y = -0.02 + 0.075 * Double(n), r = 0.15 + 0.012 * Double(n)
            let c = sc(0, y)
            let o = ink.oval(c.0, c.1, r * 1.2, 0.024 * 1.2)
            gc.stroke(o, with: .color(ink.pal[3].opacity(0.55)), lineWidth: d.px * 1.2)
        }
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
        let crest = (0...20).map { j -> (Double, Double) in
            let a = -Double.pi / 2 + (Double(j) / 20 - 0.5) * 1.6
            let p = onHead(0, hy + hh * 1.005 * sin(a), hd * 1.005 * cos(a)); return (p.x, p.y)
        }
        gc.stroke(ink.poly(crest, closed: false), with: .linearGradient(Gradient(colors: [ink.pal[4].opacity(0.55), ink.pal[3].opacity(0.05)]),
                                                                      startPoint: ink.p(crest[10].0, crest[10].1), endPoint: ink.p(crest[20].0, crest[20].1)),
                  lineWidth: d.px * 1.1)
        for side in [-1.0, 1.0] {
            let p = onHead(side * hw * 0.97, -0.62, 0.05)
            ink.metal(&gc, ink.oval(p.x, p.y, 0.05 * 1.2 * 0.5, 0.06 * 1.2), hi: (p.x - 0.01, p.y - 0.03), reach: 0.08, 1.4)
            ink.rim(&gc, ink.oval(p.x, p.y, 0.05 * 1.2 * 0.5, 0.06 * 1.2), 0.6)
        }
        // Her eyes: warm almonds, open and calm (wider as she listens), a soft blink now and then.
        let lid = (0.72 + 0.28 * s.listen + 0.12 * s.speak) * blink(t, 5.7)
        let eyeB = 0.8 + 0.35 * s.voice + 0.3 * s.listen * s.level + 0.06 * sin(t * 1.3)
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
        let open = 0.01 + 0.035 * s.voice
        let ml = onHead(-0.085, -0.3, front(-0.085, -0.3)), mr = onHead(0.085, -0.3, front(0.085, -0.3))
        let mu = onHead(0, -0.29, front(0, -0.29)), md = onHead(0, -0.27 + 2 * open, front(0, -0.27))
        var mouth = Path()
        mouth.move(to: ink.p(ml.x, ml.y))
        mouth.addQuadCurve(to: ink.p(mr.x, mr.y), control: ink.p(mu.x, mu.y))
        mouth.addQuadCurve(to: ink.p(ml.x, ml.y), control: ink.p(md.x, md.y))
        mouth.closeSubpath()
        gc.fill(mouth, with: .color(warm.opacity(0.4 + 0.5 * s.voice)))
        gc.stroke(mouth, with: .color(warm.opacity(0.6 + 0.3 * s.voice)), lineWidth: d.px)
        for r in rings { ring(r, frontHalf: true) }
        finish(&gc, d, tint: tint)
    }

    // MARK: Rover

    /// A little rover, seen a little from the side: two binocular eyes (lit boxes with big round warm
    /// lenses) on a neck over a boxy body on tracks. Its eyes do the talking: listening, they lift,
    /// lean in and tilt toward each other, lenses wide; thinking, they look one way then the other,
    /// zoom rings turning; working, a light scans across the lenses and its tracks roll; speaking,
    /// its lenses pulse with the voice and its eyes bob.
    func drawRover(_ gc: inout GraphicsContext, _ box: CGSize) {
        var d = robotCanvas(box, scale: 1.2, dy: -0.18)
        let s = RobotState(engine, work)
        let k = density(box)
        let tint = Color(hex: 0xffb347)
        let ink = Ink(d, robotPalette(tint))
        let warm = look.color ?? Color(hex: 0xffe2a6), deep = look.color ?? Color(hex: 0xff9a3a)
        let view = Turn3(yaw: 0.32 + 0.06 * sin(t * 0.2), pitch: -0.2)
        let lift = -0.12 * s.listen + 0.04 * s.voice * sin(t * 6) + 0.015 * sin(t * 0.9)
        // Thinking: a look one way, then the other (a smooth swing, never a jump).
        let look = 0.06 * sin(t * 0.35) * (1 - s.th) + s.th * 0.1 * max(-1, min(1, 3 * sin(t * 0.9)))
        let aperture = 0.1 + 0.035 * s.listen - 0.025 * s.voice + 0.01 * sin(t * 0.7)
        let zoom = engine.ringTurn * 4
        let scan = sin(t * 2.6)
        let sc = 1.05, oy = 0.1
        func at(_ x: Double, _ y: Double, _ z: Double) -> (Double, Double) { let p = view.apply(x, y, z); return (p.x * sc, p.y * sc + oy) }
        func surf(_ x: Double, _ y: Double, _ z: Double, _ nx: Double, _ ny: Double, _ nz: Double, _ tone: Double, _ dither: Double) {
            let n = view.apply(nx, ny, nz)
            guard n.z > -0.02 else { return }
            let q = at(x, y, z)
            place(&d, q.0, q.1, tone * metal(n.x, n.y, n.z, shine: 0.5), dither, phase: x, lum: 0.6, size: 0.8)
        }
        /// A box: its three faces we see (front, top, the right side) in lit metal, a texture of points.
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
        // The tracks: lit plates, their treads rolling (faster while it works: two paces, blended).
        for side in [-1.0, 1.0] {
            // A track: a rounded belt (wider at its foot), its treads rolling down its face.
            let top = 1.02, bottom = 1.78
            func edge(_ y: Double, _ out: Double) -> (Double, Double) {
                let f = (y - top) / (bottom - top), half = 0.12 + 0.11 * f
                return at(side * (1.13 + out * half), y, 0.32)
            }
            let ys = stride(from: top, through: bottom, by: 0.076).map { $0 }
            let belt = ink.poly(ys.map { edge($0, -1) } + ys.reversed().map { edge($0, 1) })
            ink.metal(&gc, belt, hi: edge(top, -0.6), reach: 0.95, 1.0)
            gc.stroke(belt, with: .color(ink.pal[3].opacity(0.55)), style: StrokeStyle(lineWidth: d.px * 1.6, lineJoin: .round))
            for (pace, w) in [(0.35, 1 - s.busy), (1.6, s.busy)] where w > 0.02 {
                var treads = Path()
                for n in 0..<7 {
                    let y = top + (bottom - top) * fract(t * pace + Double(n) / 7)
                    let a = edge(y, -0.8), b = edge(y, 0.8)
                    treads.move(to: ink.p(a.0, a.1)); treads.addLine(to: ink.p(b.0, b.1))
                }
                gc.stroke(treads, with: .color(ink.pal[3].opacity(0.5 * w)), style: StrokeStyle(lineWidth: d.px * 1.4, lineCap: .round))
            }
            let hub = edge(top + 0.1, 0)
            ink.metal(&gc, ink.circle(hub.0, hub.1, 0.07), hi: (hub.0 - 0.02, hub.1 - 0.03), reach: 0.1, 1.4)
        }
        // The body: a box with a lamp; the neck, its joint.
        block(0, 1.05, 0, 1.9, 1.45, 1.1, points: Int(300 * k) + 30, seed: 6000)
        let hatch = [at(-0.55, 0.98, 0.56), at(0.6, 0.98, 0.56), at(0.6, 1.62, 0.56), at(-0.55, 1.62, 0.56)]
        gc.stroke(ink.poly(hatch), with: .color(ink.pal[3].opacity(0.4)), style: StrokeStyle(lineWidth: d.px * 1.1, lineJoin: .round))
        // Its meter: five lights that rise with your voice as it listens and with its own as it speaks.
        let meter = min(1, s.listen * (0.15 + 1.1 * s.level) + s.speak * (0.15 + 1.1 * s.loud) + 0.12 * (1 - s.listen - s.speak))
        var onBars = Path(), offBars = Path()
        for n in 0..<5 {
            let x0 = -0.42 + 0.2 * Double(n)
            let bar = ink.poly([at(x0, 0.62, 0.56), at(x0 + 0.15, 0.62, 0.56), at(x0 + 0.15, 0.8, 0.56), at(x0, 0.8, 0.56)])
            if meter > Double(n) / 5 + 0.04 { onBars.addPath(bar) } else { offBars.addPath(bar) }
        }
        gc.fill(onBars, with: .color(warm.opacity(0.9)))
        gc.stroke(onBars, with: .color(warm.opacity(0.22)), style: StrokeStyle(lineWidth: d.px * 4, lineJoin: .round))
        gc.fill(offBars, with: .color(ink.pal[2].opacity(0.3)))
        let lampOn = 0.35 * (1 - s.busy) + s.busy * (0.55 + 0.45 * sin(t * 7)) + 0.1 * sin(t)
        let lampAt = at(-0.75, 0.5, 0.56)
        ink.eye(&gc, lampAt.0, lampAt.1, 0.05, lampOn, warm: warm, deep: deep, catchlight: 0)
        let neckTop = at(0, -0.55 + lift, 0), neckBottom = at(0, 0.33, 0)
        var neck = Path(); neck.move(to: ink.p(neckTop.0, neckTop.1)); neck.addLine(to: ink.p(neckBottom.0, neckBottom.1))
        gc.stroke(neck, with: .linearGradient(Gradient(colors: [ink.pal[3].opacity(0.75), ink.pal[2].opacity(0.4)]),
                                              startPoint: ink.p(neckTop.0 - 0.06, 0), endPoint: ink.p(neckTop.0 + 0.06, 0)), lineWidth: 0.11 * sc * d.R)
        let joint = at(0, 0.33, 0.02)
        ink.metal(&gc, ink.circle(joint.0, joint.1, 0.09), hi: (joint.0 - 0.03, joint.1 - 0.04), reach: 0.13, 1.3)
        // The eyes: lit boxes, big round warm lenses (a zoom ring, the aperture, a glint).
        for side in [-1.0, 1.0] {
            let tilt = side * (-0.08 * (1 - s.listen) * (1 - s.th) + 0.22 * s.listen) + s.th * 0.18 * sin(t * 0.9 + side)
            let ex = side * 0.45, ey = -0.62 + lift, ez = 0.0
            block(ex, ey, ez, 0.62, 0.5, 0.44, tilt: tilt, points: Int(110 * k) + 16, seed: side > 0 ? 1000 : 3000)
            let ct = cos(tilt), st = sin(tilt)
            let lx = look * 0.6
            let c = at(ex + lx * ct, ey + lx * st, ez + 0.225)
            let n = view.apply(0, 0, 1)
            let squash = n.z, angle = atan2(n.y, n.x)
            ink.metal(&gc, ink.oval(c.0, c.1, 0.215 * squash, 0.215, angle: angle), hi: (c.0 - 0.07, c.1 - 0.08), reach: 0.3, 1.2)
            ink.rim(&gc, ink.oval(c.0, c.1, 0.215 * squash, 0.215, angle: angle), 0.7, width: 1.2)
            let lensB = 0.62 + 0.4 * s.voice + 0.35 * s.listen * s.level + 0.05 * sin(t * 1.4 + side)
            ink.eye(&gc, c.0, c.1, 0.175, lensB, warm: warm, deep: deep, squash: squash, angle: angle, open: blink(t, 6.7))
            // The zoom ring (turning as it thinks) and the aperture (wider as it listens).
            let ring = ink.oval(c.0, c.1, 0.155 * squash, 0.155, angle: angle)
            gc.stroke(ring, with: .color(ink.pal[4].opacity(0.25 + 0.4 * s.th)),
                      style: StrokeStyle(lineWidth: d.px * 1.4, dash: [CGFloat(0.05 * d.R), CGFloat(0.04 * d.R)], dashPhase: CGFloat(zoom * side * 0.09 * d.R)))
            gc.stroke(ink.oval(c.0, c.1, aperture * squash, aperture, angle: angle), with: .color(Color.white.opacity(0.35 + 0.3 * s.voice)), lineWidth: d.px)
            if s.busy > 0.01 { ink.glow(&gc, c.0 + 0.12 * scan * squash, c.1, 0.07, .white, 0.7 * s.busy) }
        }
        finish(&gc, d, tint: tint)
    }

}
