import SwiftUI

// Four more machines, each a classic way of picturing a machine with a character: Hover (a round
// floating robot, polite and brave), Spark (a curious robot on tracks with shutter eyes), Cruiser
// (a sleek black car with a scanning light) and Android (a pale gold android with amber eyes).
// They share the robots' kit (OrbRobots.swift: `RobotState`, `Turn3`, `Ink`, `robotCanvas`,
// `robotPalette`, `density`) and the same rules: smooth lit metal under a fine texture of points,
// warm glowing eyes and lamps, five states that read at a glance, every motion at a fixed pace so
// a change of state is a smooth morph (a phase changes how much of a motion shows, never its speed).

@inline(__always) private func mFract(_ x: Double) -> Double { x - x.rounded(.down) }

/// Metal lit from the upper left in front: a matte part and a highlight (`shine`: its strength).
@inline(__always) private func mMetal(_ nx: Double, _ ny: Double, _ nz: Double, shine: Double = 0.6) -> Double {
    let lx = -0.48, ly = -0.55, lz = 0.68
    let diffuse = max(0, nx * lx + ny * ly + nz * lz)
    let hx = lx, hy = ly, hz = lz + 1, hl = (hx * hx + hy * hy + hz * hz).squareRoot()
    let spec = pow(max(0, (nx * hx + ny * hy + nz * hz) / hl), 22)
    return 0.1 + 0.55 * diffuse + shine * spec
}

/// A soft blink every `period` seconds (1 open … 0.1 shut), at a fixed pace.
@inline(__always) private func mBlink(_ t: Double, _ period: Double, width: Double = 0.012) -> Double {
    let f = mFract(t / period)
    return 1 - 0.9 * exp(-pow((f - 0.5) / width, 2))
}

/// A sequence of glances at a fixed pace: every `period` seconds a new target (−1…1 on both axes),
/// reached in the first `move` of the period and held. A phase only scales how much of it shows.
private func mGlance(_ t: Double, period: Double, salt: Double, move: Double = 0.2) -> (x: Double, y: Double) {
    let u = t / period
    let step = Int(u.rounded(.down)), f = u - u.rounded(.down)
    func target(_ n: Int) -> (Double, Double) { (2 * OrbPoints.hash(n, salt) - 1, 2 * OrbPoints.hash(n, salt + 0.37) - 1) }
    let a = target(step - 1), b = target(step)
    let w = smoothstep(0, move, f)
    return (a.0 + (b.0 - a.0) * w, a.1 + (b.1 - a.1) * w)
}

/// A smooth closed (or open) curve through screen points (Catmull-Rom as cubic Béziers).
private func mSmooth(_ pts: [CGPoint], closed: Bool = true) -> Path {
    var path = Path()
    let n = pts.count
    guard n > 2 else { path.addLines(pts); if closed { path.closeSubpath() }; return path }
    path.move(to: pts[0])
    for i in 0..<(closed ? n : n - 1) {
        let p1 = pts[i], p2 = pts[(i + 1) % n]
        let p0 = closed || i > 0 ? pts[(i - 1 + n) % n] : p1
        let p3 = closed || i + 2 < n ? pts[(i + 2) % n] : p2
        path.addCurve(to: p2, control1: CGPoint(x: p1.x + (p2.x - p0.x) / 6, y: p1.y + (p2.y - p0.y) / 6),
                      control2: CGPoint(x: p2.x - (p3.x - p1.x) / 6, y: p2.y - (p3.y - p1.y) / 6))
    }
    if closed { path.closeSubpath() }
    return path
}

/// A soft oval of light (or shade) fading from its centre to its rim on every side (a radial
/// gradient on a stretched circle, so the oval never shows a hard edge on its short axis).
private func mSoftOval(_ gc: inout GraphicsContext, _ c: CGPoint, _ rx: Double, _ ry: Double, angle: Double = 0, _ stops: [Gradient.Stop]) {
    guard rx > 0.01, ry > 0.01 else { return }
    var g = gc
    g.translateBy(x: c.x, y: c.y)
    g.rotate(by: .radians(angle))
    g.scaleBy(x: rx, y: ry)
    g.fill(Path(ellipseIn: CGRect(x: -1, y: -1, width: 2, height: 2)),
           with: .radialGradient(Gradient(stops: stops), center: .zero, startRadius: 0, endRadius: 1))
}

/// A soft oval in one colour: `a` at its centre, gone at its rim.
private func mSoftOval(_ gc: inout GraphicsContext, _ c: CGPoint, _ rx: Double, _ ry: Double, angle: Double = 0, _ color: Color, _ a: Double) {
    guard a > 0.005 else { return }
    mSoftOval(&gc, c, rx, ry, angle: angle, [.init(color: color.opacity(min(1, a)), location: 0),
                                             .init(color: color.opacity(min(1, a) * 0.35), location: 0.5), .init(color: color.opacity(0), location: 1)])
}

/// A polygon with rounded corners (each corner cut by `r` along both edges, a curve between).
private func mRounded(_ pts: [CGPoint], _ r: Double) -> Path {
    var path = Path()
    let n = pts.count
    for i in 0..<n {
        let prev = pts[(i - 1 + n) % n], cur = pts[i], next = pts[(i + 1) % n]
        func toward(_ q: CGPoint) -> CGPoint {
            let dx = Double(q.x - cur.x), dy = Double(q.y - cur.y), l = max(1e-6, (dx * dx + dy * dy).squareRoot())
            let f = min(0.45, r / l)
            return CGPoint(x: Double(cur.x) + dx * f, y: Double(cur.y) + dy * f)
        }
        let a = toward(prev), b = toward(next)
        if i == 0 { path.move(to: a) } else { path.addLine(to: a) }
        path.addQuadCurve(to: b, control: cur)
    }
    path.closeSubpath()
    return path
}

extension OrbCanvas {
    // MARK: Hover

    /// A small round robot that floats: a squat barrel of pale warm metal under a domed top, a dark
    /// visor band round it carrying two round red-amber eyes, stubby arms at its sides, three small
    /// thrusters glowing under it. It never touches the ground: a slow bob, a light pool far below.
    /// At rest it hovers and surveys (a slow yaw); listening, it drifts closer and lower, tilts its
    /// head and its eyes brighten with your voice; thinking, it rises, turns a little aside, narrows
    /// its eyes while a light circles its visor; working, its arms unfold, a bit whirs and a light
    /// scans, its thrusters flare; speaking, its eyes and visor pulse with its voice and it dips on
    /// each emphasis.
    func drawHover(_ gc: inout GraphicsContext, _ box: CGSize) {
        let s = RobotState(engine, work)
        let k = density(box)
        let rest = max(0, 1 - s.listen - s.th - s.busy - s.speak)
        let near = 1 + 0.12 * s.listen - 0.05 * s.th
        var d = robotCanvas(box, scale: 1.3 * near, dy: -0.08)
        let custom = look.color
        let pal: [Color] = custom.map { OrbPalette.colors(for: $0) } ?? [
            Color(hex: 0x6b5232).opacity(0.45), Color(hex: 0xa88a5c).opacity(0.6), Color(hex: 0xdcc296).opacity(0.75),
            Color(hex: 0xf5e6c8).opacity(0.88), Color(hex: 0xfffaf0).opacity(0.95)]
        let ink = Ink(d, pal)
        let cream = custom ?? Color(hex: 0xf2dfbc), brass = custom ?? Color(hex: 0xc9a46a)
        let warm = custom ?? Color(hex: 0xffa463), deep = custom ?? Color(hex: 0xe0402a)
        let flame = custom ?? Color(hex: 0xffcf96)
        // Floating: a slow bob that never stops; it comes down to listen, rises to think, dips on emphasis.
        let bob = 0.05 * sin(t * 1.05) + 0.015 * sin(t * 2.3 + 1)
        let emphasis = 0.09 * s.speak * engine.history.value(secondsAgo: 0.12)
        let oy = -0.1 + bob + 0.16 * s.listen - 0.16 * s.th + emphasis - 0.04 * s.busy
        let survey = 0.28 * sin(t * 0.29) + 0.06 * sin(t * 0.71)
        let yaw = survey * (rest + 0.5 * s.speak + 0.4 * s.busy) + s.th * (0.5 + 0.05 * sin(t * 0.4))
        let pitch = -0.3 - 0.1 * s.listen + 0.04 * s.th
        let roll = 0.025 * sin(t * 0.6) + 0.13 * s.listen - 0.04 * s.th
        let view = Turn3(yaw: 0, pitch: pitch, roll: roll), body = Turn3(yaw: yaw, pitch: pitch, roll: roll)
        let Rb = 0.78, top = -0.3, bottom = 0.58, domeH = 0.52, baseH = 0.26
        let cr = cos(roll), sr = sin(roll)
        func at(_ p: (x: Double, y: Double, z: Double)) -> (Double, Double) { (p.x, p.y + oy) }
        /// A horizontal circle of the barrel (radius r at height y), from azimuth a0 to a1 (0 faces us).
        func ring(_ y: Double, _ r: Double, _ a0: Double, _ a1: Double, n: Int = 20) -> [(Double, Double)] {
            (0...n).map { j in let az = a0 + (a1 - a0) * Double(j) / Double(n); return at(view.apply(r * sin(az), y, r * cos(az))) }
        }
        /// Part of the outline of an ellipsoid's silhouette (an ellipse leaning with the roll).
        func arc(_ c: (Double, Double), _ ax: Double, _ ay: Double, _ a0: Double, _ a1: Double, n: Int = 20) -> [(Double, Double)] {
            (0...n).map { j in
                let a = a0 + (a1 - a0) * Double(j) / Double(n), x = ax * cos(a), y = ay * sin(a)
                return (c.0 + x * cr - y * sr, c.1 + x * sr + y * cr)
            }
        }
        // Far below: a soft pool of its thrusters' light on the floor (smaller as it rises).
        let pool = 1.0 - 0.6 * (oy + 0.1)
        mSoftOval(&gc, ink.p(0, 1.55), 0.95 * pool * d.R, 0.16 * pool * d.R, flame, (0.16 + 0.14 * s.busy) * pool)
        mSoftOval(&gc, ink.p(0, 1.55), 0.4 * pool * d.R, 0.06 * pool * d.R, Color.white, (0.08 + 0.1 * s.busy) * pool)
        // The thrusters: three nozzles under it, each a soft flame (flaring while it works).
        for i in 0..<3 {
            let az = 2 * Double.pi * Double(i) / 3 + 0.4
            let n = at(body.apply(0.42 * sin(az), bottom + 0.2, 0.42 * cos(az)))
            let z = body.apply(sin(az), 0, cos(az)).z
            let lit = (0.55 + 0.45 * smoothstep(-0.6, 0.4, z)) * (0.75 + 0.1 * sin(t * 17 + Double(i) * 2.1) + 0.6 * s.busy + 0.1 * s.voice)
            let len = 0.3 + 0.04 * sin(t * 13 + Double(i)) + 0.28 * s.busy - 0.04 * s.listen
            // A plume of light: bright at the nozzle, fading downward (never a solid leg).
            let plume: [Gradient.Stop] = [.init(color: Color.white.opacity(min(1, 0.85 * lit)), location: 0),
                                          .init(color: flame.opacity(min(1, 0.65 * lit)), location: 0.22),
                                          .init(color: deep.opacity(min(1, 0.22 * lit)), location: 0.6), .init(color: .clear, location: 1)]
            mSoftOval(&gc, ink.p(n.0, n.1 + 0.02), 0.085 * d.R, len * d.R, plume)
            ink.glow(&gc, n.0, n.1, 0.13, flame, 0.4 * lit)
            mSoftOval(&gc, ink.p(n.0, n.1), 0.065 * d.R, 0.022 * d.R, Color.white, 0.8 * lit)
        }
        // The arms: a shoulder at each side, folded down along the body, unfolding forward and out to work.
        let unfold = smoothstep(0, 1, s.busy)
        struct Arm { let s: (Double, Double), e: (Double, Double), z: Double, side: Double, dir: (Double, Double) }
        let arms: [Arm] = [-1.0, 1.0].map { side in
            let az = side * Double.pi / 2
            let sh = (Rb * 1.02 * sin(az), 0.2, Rb * 1.02 * cos(az))
            var dx = side * (0.12 + 0.75 * unfold), dy = 1 - 0.55 * unfold, dz = 0.18 + 0.5 * unfold
            let l = (dx * dx + dy * dy + dz * dz).squareRoot(); dx /= l; dy /= l; dz /= l
            let L = 0.36
            let a = body.apply(sh.0, sh.1, sh.2), b = body.apply(sh.0 + L * dx, sh.1 + L * dy, sh.2 + L * dz)
            let sa = at(a), eb = at(b)
            let len = max(1e-6, ((eb.0 - sa.0) * (eb.0 - sa.0) + (eb.1 - sa.1) * (eb.1 - sa.1)).squareRoot())
            return Arm(s: sa, e: eb, z: a.z, side: side, dir: ((eb.0 - sa.0) / len, (eb.1 - sa.1) / len))
        }
        func drawArm(_ a: Arm) {
            let dim = a.z < 0 ? 0.55 : 1.0
            var line = Path(); line.move(to: ink.p(a.s.0, a.s.1)); line.addLine(to: ink.p(a.e.0, a.e.1))
            gc.stroke(line, with: .color(Color(hex: 0x0b0806)), style: StrokeStyle(lineWidth: 0.22 * d.R, lineCap: .round))
            gc.stroke(line, with: .linearGradient(Gradient(colors: [cream.opacity(0.5 * dim), brass.opacity(0.22 * dim)]),
                                                   startPoint: ink.p(a.s.0 - 0.08, a.s.1), endPoint: ink.p(a.s.0 + 0.1, a.s.1 + 0.1)),
                      style: StrokeStyle(lineWidth: 0.2 * d.R, lineCap: .round))
            gc.stroke(line, with: .color(Color.white.opacity(0.25 * dim)), style: StrokeStyle(lineWidth: d.px * 1.1, lineCap: .round))
            ink.metal(&gc, ink.circle(a.e.0, a.e.1, 0.1), hi: (a.e.0 - 0.035, a.e.1 - 0.035), reach: 0.15, 1.8 * dim)
            ink.rim(&gc, ink.circle(a.e.0, a.e.1, 0.1), 0.35 * dim)
            ink.rim(&gc, ink.circle(a.s.0, a.s.1, 0.08), 0.4 * dim)
        }
        var occluder = gc
        occluder.blendMode = .normal
        for a in arms where a.z < 0 { drawArm(a) }
        // The base: a shallow rounded cap under the barrel.
        let hb = (baseH * baseH * cos(pitch) * cos(pitch) + Rb * Rb * sin(pitch) * sin(pitch)).squareRoot()
        let baseC = at(view.apply(0, bottom, 0))
        let baseOutline = ring(bottom, Rb, -Double.pi / 2, Double.pi / 2) + arc(baseC, Rb * 0.97, hb, 0, Double.pi).reversed()
        // The barrel and the dome as solid bodies (whatever is behind them hidden), then their light.
        let hd = (domeH * domeH * cos(pitch) * cos(pitch) + Rb * Rb * sin(pitch) * sin(pitch)).squareRoot()
        let domeC = at(view.apply(0, top, 0))
        let domeOutline = arc(domeC, Rb, hd, Double.pi, 2 * Double.pi, n: 24) + ring(top, Rb, Double.pi / 2, -Double.pi / 2)
        let barrelOutline = ring(bottom, Rb, -Double.pi / 2, Double.pi / 2) + ring(top, Rb, Double.pi / 2, 3 * Double.pi / 2)
        let barrel = ink.poly(barrelOutline), dome = ink.poly(domeOutline), base = ink.poly(baseOutline)
        let solid = Color(hex: 0x0a0807)
        occluder.fill(base, with: .color(solid)); occluder.fill(barrel, with: .color(solid)); occluder.fill(dome, with: .color(solid))
        /// A barrel's light across its width: lit from the upper left, a highlight stripe near the left.
        func across(_ y: Double, _ s0: Double, spec: Bool) -> GraphicsContext.Shading {
            let stops = (0...14).map { j -> Gradient.Stop in
                let az = -Double.pi / 2 + Double.pi * Double(j) / 14
                let n = view.apply(sin(az), 0, cos(az))
                let lit = spec ? pow(max(0, mMetal(n.x, n.y, n.z, shine: 1) - 0.62), 1.2) * 1.6 : max(0, n.x * -0.48 + n.z * 0.68)
                return .init(color: (spec ? Color.white : cream).opacity(min(1, s0 * (spec ? lit : 0.06 + 0.62 * lit))), location: (sin(az) + 1) / 2)
            }
            let l = at(view.apply(-Rb, y, 0)), r = at(view.apply(Rb, y, 0))
            return .linearGradient(Gradient(stops: stops), startPoint: ink.p(l.0, l.1), endPoint: ink.p(r.0, r.1))
        }
        gc.fill(base, with: across(bottom + 0.1, 0.62, spec: false))
        gc.fill(barrel, with: across(0.1, 1.2, spec: false))
        gc.fill(barrel, with: across(0.1, 0.55, spec: true))
        // The barrel's warm underside: the thrusters' light on it.
        gc.fill(base, with: .linearGradient(Gradient(colors: [.clear, flame.opacity(0.18 + 0.2 * s.busy)]),
                                            startPoint: ink.p(0, baseC.1 - 0.05), endPoint: ink.p(0, baseC.1 + hb)))
        // Seams: the base's rim, a band low on the barrel, the dome's rim.
        for (y, a) in [(bottom, 0.5), (0.38, 0.28)] {
            gc.stroke(ink.poly(ring(y, Rb * 1.003, -Double.pi / 2, Double.pi / 2), closed: false), with: .color(pal[3].opacity(a)), lineWidth: d.px)
        }
        // The dome: lit from the upper left, a soft highlight, a small cap on top.
        ink.metal(&gc, dome, hi: (domeC.0 - 0.32, domeC.1 - 0.55 * hd), reach: 1.3, 2.2, floor: 0.8)
        gc.fill(dome, with: across(top - 0.2, 0.5, spec: false))
        ink.glow(&gc, domeC.0 - 0.3, domeC.1 - 0.6 * hd, 0.2, .white, 0.28)
        ink.rim(&gc, ink.poly(arc(domeC, Rb, hd, Double.pi, 2 * Double.pi, n: 24), closed: false), 0.5, width: 1.1)
        let capC = at(view.apply(0, top - domeH * 0.97, 0))
        ink.metal(&gc, ink.oval(capC.0, capC.1, 0.18, 0.05, angle: roll), hi: (capC.0 - 0.06, capC.1 - 0.02), reach: 0.2, 1.6)
        ink.rim(&gc, ink.oval(capC.0, capC.1, 0.18, 0.05, angle: roll), 0.45)
        // The visor: a dark glass band round the barrel, glowing softly (with its voice as it speaks).
        let vTop = -0.2, vBottom = 0.13
        let band = ink.poly(ring(vTop, Rb * 1.006, -Double.pi / 2, Double.pi / 2) + ring(vBottom, Rb * 1.006, Double.pi / 2, -Double.pi / 2))
        occluder.fill(band, with: .color(Color(hex: 0x0c0505)))
        let vMid = at(view.apply(0, (vTop + vBottom) / 2, Rb))
        let visorGlow = 0.12 + 0.06 * sin(t * 1.3) + 0.4 * s.voice + 0.12 * s.listen * s.level
        gc.fill(band, with: .radialGradient(Gradient(colors: [deep.opacity(min(1, visorGlow)), deep.opacity(0.4 * visorGlow), .clear]),
                                            center: ink.p(vMid.0, vMid.1), startRadius: 0, endRadius: 1.0 * d.R))
        gc.fill(band, with: across(vTop, 0.35, spec: true))
        gc.stroke(ink.poly(ring(vTop, Rb * 1.006, -Double.pi / 2, Double.pi / 2), closed: false), with: .color(pal[4].opacity(0.55)), lineWidth: d.px * 1.1)
        gc.stroke(ink.poly(ring(vBottom, Rb * 1.006, -Double.pi / 2, Double.pi / 2), closed: false), with: .color(pal[3].opacity(0.4)), lineWidth: d.px)
        // Thinking: a slow light circling the visor (the engine's accumulated turn).
        if s.th > 0.01 {
            let az = remainder(engine.ringTurn * 1.5, 2 * Double.pi)
            let q = at(body.apply(Rb * 1.01 * sin(az), (vTop + vBottom) / 2, Rb * 1.01 * cos(az)))
            let face = body.apply(sin(az), 0, cos(az)).z
            if face > 0 {
                gc.fill(ink.oval(q.0, q.1, 0.2 * face, 0.1, angle: roll),
                        with: .radialGradient(Gradient(colors: [warm.opacity(0.7 * s.th * face), .clear]), center: ink.p(q.0, q.1), startRadius: 0, endRadius: 0.2 * d.R))
            }
        }
        // The eyes: round, red-amber and warm (a halo and a catchlight); narrowed as it thinks.
        let eyeB = 0.8 + 0.06 * sin(t * 1.3) + 0.5 * s.listen * s.level + 0.55 * s.voice - 0.14 * s.th + 0.1 * s.busy
        let open = mBlink(t + 1.9, 5.7) * (1 - 0.48 * s.th)
        for side in [-1.0, 1.0] {
            let az = side * 0.36
            let q = at(body.apply(Rb * 1.01 * sin(az), -0.035, Rb * 1.01 * cos(az)))
            let n = body.apply(sin(az), 0, cos(az))
            guard n.z > 0.05 else { continue }
            let ang = roll
            ink.metal(&gc, ink.oval(q.0, q.1, 0.17 * n.z, 0.17, angle: ang), hi: (q.0 - 0.04, q.1 - 0.05), reach: 0.22, 1.1)
            ink.eye(&gc, q.0, q.1, 0.135, eyeB, warm: warm, deep: deep, squash: n.z, angle: ang, open: open, halo: 1.3)
            // Its lids: a soft line across the narrowed eye.
            if s.th > 0.02 {
                let lidY = q.1 - 0.135 * open
                var lid = Path()
                lid.move(to: ink.p(q.0 - 0.16 * n.z, lidY + 0.01)); lid.addQuadCurve(to: ink.p(q.0 + 0.16 * n.z, lidY + 0.01), control: ink.p(q.0, lidY - 0.025))
                gc.stroke(lid, with: .color(cream.opacity(0.6 * s.th)), style: StrokeStyle(lineWidth: d.px * 1.5, lineCap: .round))
            }
        }
        // A fine texture of points on the dome and the barrel (panel seams turning with it).
        for j in 0..<Int(300 * k) + 20 {
            let u = evenPoint(j).0, v = evenPoint(j).1
            let el = asin(u) , az = Double.pi * (v - 0.5)
            let nx = cos(el) * sin(az), ny = -sin(el) * 0.9, nz = cos(el) * cos(az)
            if abs(sin(3 * (az - yaw))) < 0.05 && el < 0.9 { continue }
            let p = view.apply(Rb * cos(el) * sin(az), top - domeH * sin(el), Rb * cos(el) * cos(az))
            let n = view.apply(nx, ny, nz)
            guard n.z > 0 else { continue }
            place(&d, p.x, p.y + oy, 0.6 * mMetal(n.x, n.y, n.z, shine: 0.9), OrbPoints.hash(j, 14), phase: az, lum: 0.6, size: 0.7)
        }
        for j in 0..<Int(320 * k) + 20 {
            let y = top + (bottom - top) * evenPoint(j + 5000).0, az = Double.pi * (evenPoint(j + 5000).1 - 0.5)
            if y > vTop - 0.02 && y < vBottom + 0.02 { continue }
            if abs(sin(3 * (az - yaw))) < 0.05 || abs(y - 0.38) < 0.015 { continue }
            let p = view.apply(Rb * sin(az), y, Rb * cos(az)), n = view.apply(sin(az), 0, cos(az))
            place(&d, p.x, p.y + oy, 0.55 * mMetal(n.x, n.y, n.z, shine: 0.8), OrbPoints.hash(j, 15), phase: az, lum: 0.6, size: 0.7)
        }
        for a in arms where a.z >= 0 { drawArm(a) }
        // Working: a tiny bit whirring at one hand, a scanning light from the other.
        if s.busy > 0.02 {
            for a in arms {
                let tip = (a.e.0 + 0.1 * a.dir.0, a.e.1 + 0.1 * a.dir.1)
                if a.side > 0 {
                    var spokes = Path()
                    for n in 0..<3 {
                        let ang = t * 11 + 2 * Double.pi * Double(n) / 3
                        spokes.move(to: ink.p(tip.0, tip.1)); spokes.addLine(to: ink.p(tip.0 + 0.07 * cos(ang), tip.1 + 0.035 * sin(ang)))
                    }
                    gc.stroke(spokes, with: .color(Color.white.opacity(0.8 * s.busy)), style: StrokeStyle(lineWidth: d.px * 1.3, lineCap: .round))
                    gc.stroke(ink.oval(tip.0, tip.1, 0.075, 0.038), with: .color(warm.opacity(0.5 * s.busy)), lineWidth: d.px)
                    ink.glow(&gc, tip.0, tip.1, 0.16, warm, 0.45 * s.busy * (0.8 + 0.2 * sin(t * 23)))
                } else {
                    let sweep = 0.45 * sin(t * 2.4)
                    let base = atan2(a.dir.1, a.dir.0) + sweep
                    var fan = Path()
                    fan.move(to: ink.p(tip.0, tip.1))
                    fan.addLine(to: ink.p(tip.0 + 0.6 * cos(base - 0.16), tip.1 + 0.6 * sin(base - 0.16)))
                    fan.addLine(to: ink.p(tip.0 + 0.6 * cos(base + 0.16), tip.1 + 0.6 * sin(base + 0.16)))
                    fan.closeSubpath()
                    gc.fill(fan, with: .radialGradient(Gradient(colors: [warm.opacity(0.5 * s.busy), deep.opacity(0.12 * s.busy), .clear]),
                                                       center: ink.p(tip.0, tip.1), startRadius: 0, endRadius: 0.6 * d.R))
                    ink.glow(&gc, tip.0, tip.1, 0.08, warm, 0.8 * s.busy)
                }
            }
        }
        finish(&gc, d, palette: pal)
    }

    // MARK: Spark

    /// A curious robot on tracks, seen a little from the side: two camera eyes with shutter lids that
    /// work as eyebrows, on a tall head at the top of a long neck; a boxy shoulder frame with a little
    /// antenna; triangular tracks below. Eager and quick: at rest it looks around in small darts and
    /// its shutters blink; listening, it leans right in, shutters wide, still ("input!"), its eyes
    /// brightening with your voice; thinking, shutters half closed, head tilted, its eyes flick from
    /// spot to spot and a spark runs up the antenna; working, its tracks roll, its head scans left and
    /// right and a light bar counts; speaking, its eyes flutter with the voice, its head bobs, its
    /// shutters flap on the loud syllables and a little flash of lightning greets the first one.
    func drawSpark(_ gc: inout GraphicsContext, _ box: CGSize) {
        let s = RobotState(engine, work)
        let k = density(box)
        let rest = max(0, 1 - s.listen - s.th - s.busy - s.speak)
        var d = robotCanvas(box, scale: 1.36, dy: -0.2)
        let custom = look.color
        let pal: [Color] = custom.map { OrbPalette.colors(for: $0) } ?? [
            Color(hex: 0x2c3a52).opacity(0.45), Color(hex: 0x52698f).opacity(0.6), Color(hex: 0x8ea8cc).opacity(0.75),
            Color(hex: 0xcfdff4).opacity(0.88), Color(hex: 0xf4f9ff).opacity(0.95)]
        let ink = Ink(d, pal)
        let blue = custom ?? Color(hex: 0x5cb8ff)
        let warm = custom ?? Color(hex: 0xffd69a), deep = custom ?? Color(hex: 0xff8f3c)
        let viewYaw = -0.62 + 0.04 * sin(t * 0.21)
        let view = Turn3(yaw: viewYaw, pitch: -0.16)
        func at(_ x: Double, _ y: Double, _ z: Double) -> (Double, Double) { let p = view.apply(x, y, z); return (p.x, p.y) }
        var occluder = gc
        occluder.blendMode = .normal
        let solid = Color(hex: 0x05070b)
        /// A box (centre, half sizes): its faces turned to us in lit steel, a rim, an occluder behind.
        func block(_ c: (Double, Double, Double), _ h: (Double, Double, Double), tone: Double = 1) {
            let faces: [([(Double, Double, Double)], (Double, Double, Double))] = [
                ([(-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)], (0, 0, 1)),
                ([(-1, -1, -1), (1, -1, -1), (1, -1, 1), (-1, -1, 1)], (0, -1, 0)),
                ([(1, -1, 1), (1, -1, -1), (1, 1, -1), (1, 1, 1)], (1, 0, 0)),
                ([(-1, -1, -1), (-1, -1, 1), (-1, 1, 1), (-1, 1, -1)], (-1, 0, 0)),
            ]
            var all = Path()
            var lit: [(Path, (Double, Double), (Double, Double), Double)] = []
            for (corners, normal) in faces {
                let n = view.apply(normal.0, normal.1, normal.2)
                guard n.z > 0.02 else { continue }
                let pts = corners.map { at(c.0 + $0.0 * h.0, c.1 + $0.1 * h.1, c.2 + $0.2 * h.2) }
                let path = ink.poly(pts)
                all.addPath(path)
                lit.append((path, pts[0], pts[3], tone * (0.45 + 1.6 * mMetal(n.x, n.y, n.z, shine: 0.7))))
            }
            // One occluder and one rim for the box, a lit fill per face.
            occluder.fill(all, with: .color(solid))
            for f in lit { ink.face(&gc, f.0, top: f.1, bottom: f.2, f.3) }
            ink.rim(&gc, all, 0.4 * tone, width: 0.9)
        }
        // The tracks: triangular belts (a near one, a far one): their sides, the sloping belt in
        // front, the treads rolling round them (two paces, blended).
        let tri: [(Double, Double)] = [(0.04, 0.74), (0.8, 1.62), (-0.72, 1.62)]       // (z, y)
        func track(_ side: Double) {
            let xIn = side * 0.4, xOut = side * 0.76
            let outerN = view.apply(side, 0, 0)
            let inner = tri.map { at(xIn, $0.1, $0.0) }, outer = tri.map { at(xOut, $0.1, $0.0) }
            // The belt's front slope (apex to front foot), facing us.
            let slope = ink.poly([outer[0], outer[1], inner[1], inner[0]])
            occluder.fill(slope, with: .color(solid))
            let sn = view.apply(0, -0.72, 0.69)
            ink.face(&gc, slope, top: outer[0], bottom: outer[1], 0.45 + 1.3 * mMetal(sn.x, sn.y, sn.z, shine: 0.5))
            for (pace, w) in [(0.4, 1 - s.busy), (1.9, s.busy)] where w > 0.02 {
                var treads = Path()
                for n in 0..<6 {
                    let f = mFract(t * pace + Double(n) / 6)
                    let a = (outer[0].0 + (outer[1].0 - outer[0].0) * f, outer[0].1 + (outer[1].1 - outer[0].1) * f)
                    let b = (inner[0].0 + (inner[1].0 - inner[0].0) * f, inner[0].1 + (inner[1].1 - inner[0].1) * f)
                    treads.move(to: ink.p(a.0, a.1)); treads.addLine(to: ink.p(b.0, b.1))
                }
                gc.stroke(treads, with: .color(pal[4].opacity(0.4 * w)), style: StrokeStyle(lineWidth: d.px * 1.6, lineCap: .round))
            }
            // The side we see (the outer one on the near track, the inner on the far).
            let showOuter = outerN.z > 0
            let face = showOuter ? outer : inner
            let path = mRounded(face.map { ink.p($0.0, $0.1) }, 0.16 * d.R)
            occluder.fill(path, with: .color(solid))
            let fn = showOuter ? outerN : view.apply(-side, 0, 0)
            ink.face(&gc, path, top: face[0], bottom: face[1], (0.4 + 1.4 * mMetal(fn.x, fn.y, fn.z, shine: 0.5)) * (showOuter ? 1 : 0.7))
            gc.stroke(path, with: .color(pal[3].opacity(0.55)), style: StrokeStyle(lineWidth: d.px * 3, lineJoin: .round))
            for (pace, w) in [(0.4, 1 - s.busy), (1.9, s.busy)] where w > 0.02 {
                let period = 0.1 * d.R
                gc.stroke(path, with: .color(pal[4].opacity(0.6 * w)),
                          style: StrokeStyle(lineWidth: d.px * 2.4, dash: [CGFloat(0.04 * d.R), CGFloat(0.06 * d.R)],
                                             dashPhase: CGFloat(-mFract(t * pace) * period)))
            }
            // Its wheels: lit hubs in the corners (a big drive wheel at the front).
            let x = showOuter ? xOut + side * 0.01 : xIn - side * 0.01
            var hubs = Path()
            for (z, y, r) in [(0.04, 0.92, 0.07), (0.56, 1.48, 0.12), (-0.5, 1.48, 0.1)] {
                let h = at(x, y, z)
                let o = ink.oval(h.0, h.1, r * max(0.25, abs(fn.z)), r)
                ink.metal(&gc, o, hi: (h.0 - 0.02, h.1 - 0.03), reach: r * 1.4, 1.7)
                hubs.addPath(o)
                hubs.addPath(ink.circle(h.0, h.1, 0.02))
            }
            ink.rim(&gc, hubs, 0.6)
        }
        // Which track is nearer: the one on the side turned toward us.
        let nearSide: Double = view.apply(1, 0, 0).z > 0 ? 1 : -1
        track(-nearSide)
        // The hips and the torso: a box between the tracks, a light bar on its front.
        block((0, 1.18, 0.02), (0.5, 0.1, 0.24), tone: 0.8)
        block((0, 0.8, 0.04), (0.36, 0.3, 0.27))
        let count = Int(mFract(t * 0.75) * 7)
        var on = Path(), off = Path()
        for n in 0..<6 {
            let x = -0.25 + 0.1 * Double(n)
            let bar = ink.poly([at(x, 0.96, 0.315), at(x + 0.07, 0.96, 0.315), at(x + 0.07, 1.02, 0.315), at(x, 1.02, 0.315)])
            let counted = n < count ? 1.0 : 0.0
            let voiced = s.spectrum.band(at: Double(n) / 5) > 0.25 ? 1.0 : 0.0
            let lit = 0.2 * (1 - s.busy - s.speak) + s.busy * counted + s.speak * voiced
            if lit > 0.5 { on.addPath(bar) } else { off.addPath(bar) }
        }
        gc.fill(on, with: .color(blue.opacity(0.95)))
        gc.stroke(on, with: .color(blue.opacity(0.3)), style: StrokeStyle(lineWidth: d.px * 4, lineJoin: .round))
        gc.fill(off, with: .color(blue.opacity(0.22)))
        let core = at(0, 0.7, 0.315)
        ink.eye(&gc, core.0, core.1, 0.06, 0.55 + 0.3 * s.busy * (0.5 + 0.5 * sin(t * 6)) + 0.3 * s.voice, warm: blue, deep: Color(hex: 0x2a6fd8), catchlight: 0)
        track(nearSide)
        // The shoulder frame: a wide bar with round joints; the arms hanging from it, a gripper each.
        block((0, 0.44, 0.02), (0.8, 0.06, 0.1))
        for side in [-1.0, 1.0] {
            let j = at(side * 0.82, 0.44, 0.12)
            ink.metal(&gc, ink.circle(j.0, j.1, 0.09), hi: (j.0 - 0.03, j.1 - 0.03), reach: 0.13, 1.5)
            ink.rim(&gc, ink.circle(j.0, j.1, 0.09), 0.6)
            let swing = 0.06 * sin(t * 0.8 + side) * rest + s.busy * 0.12 * sin(t * 3.1 + side)
            let elbow = at(side * 0.86, 0.82, 0.2 + swing), hand = at(side * 0.82, 0.92, 0.55 + swing)
            var arm = Path(); arm.move(to: ink.p(j.0, j.1)); arm.addLine(to: ink.p(elbow.0, elbow.1)); arm.addLine(to: ink.p(hand.0, hand.1))
            gc.stroke(arm, with: .color(solid), style: StrokeStyle(lineWidth: 0.09 * d.R, lineCap: .round, lineJoin: .round))
            gc.stroke(arm, with: .color(pal[3].opacity(0.55)), style: StrokeStyle(lineWidth: 0.07 * d.R, lineCap: .round, lineJoin: .round))
            gc.stroke(arm, with: .color(Color.white.opacity(0.35)), style: StrokeStyle(lineWidth: d.px, lineCap: .round, lineJoin: .round))
            for f in [-1.0, 1.0] {
                var grip = Path(); grip.move(to: ink.p(hand.0, hand.1)); grip.addLine(to: ink.p(hand.0 + 0.05 * f, hand.1 + 0.08))
                gc.stroke(grip, with: .color(pal[3].opacity(0.6)), style: StrokeStyle(lineWidth: d.px * 2, lineCap: .round))
            }
        }
        // The antenna: a thin rod from the shoulder, a blue tip; a spark runs up it as it thinks.
        let aBase = at(0.56, 0.38, -0.02), aTip = at(0.62, -0.18, -0.02)
        var rod = Path(); rod.move(to: ink.p(aBase.0, aBase.1)); rod.addLine(to: ink.p(aTip.0, aTip.1))
        gc.stroke(rod, with: .color(pal[3].opacity(0.6)), style: StrokeStyle(lineWidth: d.px * 1.4, lineCap: .round))
        ink.eye(&gc, aTip.0, aTip.1, 0.035, 0.6 + 0.4 * s.th + 0.2 * sin(t * 2.1), warm: blue, deep: Color(hex: 0x2a6fd8), catchlight: 0)
        if s.th > 0.01 {
            let f = mFract(t * 1.3)
            let q = (aBase.0 + (aTip.0 - aBase.0) * f, aBase.1 + (aTip.1 - aBase.1) * f)
            ink.glow(&gc, q.0, q.1, 0.09, blue, 0.9 * s.th * sin(Double.pi * f))
            gc.fill(ink.circle(q.0, q.1, 0.018), with: .color(Color.white.opacity(0.9 * s.th * sin(Double.pi * f))))
        }
        // The head's pose: darting at rest, leaning right in to listen, tilted while it thinks,
        // scanning while it works, bobbing with its voice.
        let dart = mGlance(t, period: 1.25, salt: 11, move: 0.14)
        let headYaw = 0.44 + 0.4 * dart.x * (rest + 0.4 * s.speak) + 0.18 * s.listen - 0.12 * s.th + 0.5 * s.busy * sin(t * 2.3)
            + 0.08 * s.speak * sin(t * 0.9)
        let headPitch = 0.14 * dart.y * rest + 0.08 * s.listen - 0.06 * s.th + 0.08 * s.busy
        let headRoll = 0.05 * dart.x * rest + 0.24 * s.th - 0.04 * s.listen + 0.05 * s.speak * sin(t * 1.7)
        let headScale = 1.22 + 0.32 * s.listen
        let bobV = 0.07 * s.speak * engine.history.value(secondsAgo: 0.1)
        let hc = (0.04 * dart.x * rest, -0.74 + 0.3 * s.listen + bobV + 0.02 * s.th, 0.08 + 0.45 * s.listen)
        let head = Turn3(yaw: viewYaw + headYaw, pitch: -0.16 + headPitch, roll: headRoll)
        func onHead(_ x: Double, _ y: Double, _ z: Double) -> (Double, Double) {
            let c = view.apply(hc.0, hc.1, hc.2)
            let p = head.apply(x * headScale, y * headScale, z * headScale)
            return (c.x + p.x, c.y + p.y)
        }
        // The neck: a long post from the shoulders to the head, ribbed.
        let neckBottom = at(0, 0.4, 0.02), neckTop = onHead(0, 0.2, -0.05)
        var neck = Path(); neck.move(to: ink.p(neckBottom.0, neckBottom.1)); neck.addLine(to: ink.p(neckTop.0, neckTop.1))
        gc.stroke(neck, with: .color(solid), style: StrokeStyle(lineWidth: 0.12 * d.R, lineCap: .round))
        gc.stroke(neck, with: .linearGradient(Gradient(colors: [pal[4].opacity(0.7), pal[2].opacity(0.35)]),
                                              startPoint: ink.p(neckTop.0 - 0.05, 0), endPoint: ink.p(neckTop.0 + 0.05, 0)), lineWidth: 0.09 * d.R)
        var ribs = Path()
        for n in 1..<6 {
            let f = Double(n) / 6
            let c = (neckBottom.0 + (neckTop.0 - neckBottom.0) * f, neckBottom.1 + (neckTop.1 - neckBottom.1) * f)
            ribs.move(to: ink.p(c.0 - 0.055, c.1)); ribs.addLine(to: ink.p(c.0 + 0.055, c.1))
        }
        gc.stroke(ribs, with: .color(pal[4].opacity(0.4)), lineWidth: d.px)
        // The head: a bridge between the eyes, a small chin plate under them.
        let headFaces: [([(Double, Double, Double)])] = [
            [(-0.12, -0.08, 0.14), (0.12, -0.08, 0.14), (0.1, 0.16, 0.14), (-0.1, 0.16, 0.14)],
            [(-0.3, 0.14, 0.08), (0.3, 0.14, 0.08), (0.22, 0.24, 0.02), (-0.22, 0.24, 0.02)],
        ]
        for f in headFaces {
            let pts = f.map { onHead($0.0, $0.1, $0.2) }
            let path = ink.poly(pts)
            occluder.fill(path, with: .color(solid))
            ink.face(&gc, path, top: pts[0], bottom: pts[3], 1.3)
            ink.rim(&gc, path, 0.5)
        }
        // The eyes: lens barrels (a back ring, a front ring), dark glass, a warm core; the shutters.
        let facing = head.apply(0, 0, 1)
        let squash = max(0.08, facing.z), angle = atan2(facing.y, facing.x)
        let flick = mGlance(t, period: 0.3, salt: 23, move: 0.3)
        let blinkLid = 1 - mBlink(t, 3.3, width: 0.02)
        let lidBase = max(blinkLid, 0.46 * s.th + 0.1 * s.busy) * (1 - s.listen)
        let er = 0.19
        for side in [-1.0, 1.0] {
            let ex = side * 0.25
            let back = onHead(ex, 0, -0.08), front = onHead(ex, 0, 0.16)
            let rx = er * headScale
            for (c, r, a) in [(back, rx * 0.96, 0.6), (front, rx, 1.4)] {
                let o = ink.oval(c.0, c.1, r * squash, r, angle: angle)
                occluder.fill(o, with: .color(solid))
                ink.metal(&gc, o, hi: (c.0 - 0.06, c.1 - 0.07), reach: r * 1.5, a)
                ink.rim(&gc, o, 0.55 * a, width: 1.1)
            }
            let glass = ink.oval(front.0, front.1, 0.8 * rx * squash, 0.8 * rx, angle: angle)
            gc.fill(glass, with: .radialGradient(Gradient(colors: [blue.opacity(0.35), Color(hex: 0x10233f).opacity(0.5), .clear]),
                                                 center: ink.p(front.0, front.1), startRadius: 0, endRadius: 0.8 * rx * d.R))
            // The core: flicking from spot to spot while it thinks; fluttering with the voice.
            let fx = 0.06 * flick.x * s.th + 0.03 * dart.x * rest, fy = 0.04 * flick.y * s.th
            let flutter = s.speak * s.spectrum.band(at: side < 0 ? 0.25 : 0.7)
            let coreB = 0.75 + 0.45 * s.listen * (0.4 + s.level) + 0.6 * flutter + 0.08 * sin(t * 1.7 + side)
            let cc = onHead(ex + fx, fy, 0.17)
            ink.eye(&gc, cc.0, cc.1, 0.085 * headScale * (1 + 0.15 * s.listen), coreB, warm: warm, deep: deep, squash: squash, angle: angle)
            // The shutter: a plate hinged above the lens, its lower edge the brow; it slides down to
            // close, tilts and flaps with feeling.
            let flap = side * (0.1 * (0.6 + 0.4 * dart.y) * rest + (0.1 + 0.5 * s.loud) * s.speak + 0.16 * s.listen + 0.06 * s.busy)
                + s.th * (side > 0 ? 0.3 : -0.04)
            let raise = 0.06 * s.listen + 0.07 * s.speak * s.loud + (side > 0 ? 0.05 : 0) * s.th
            let lidY = -er * 1.12 - raise + 2.05 * er * lidBase
            func lid(_ x: Double, _ y: Double) -> CGPoint {
                let c = cos(flap), sn = sin(flap)
                let q = onHead(ex + x * c - (y - lidY) * sn, lidY + x * sn + (y - lidY) * c, 0.19)
                return ink.p(q.0, q.1)
            }
            var cover = Path()
            cover.addLines([lid(-er * 1.3, lidY), lid(er * 1.3, lidY), lid(er * 1.3, lidY - 2.4 * er), lid(-er * 1.3, lidY - 2.4 * er)])
            cover.closeSubpath()
            var clipped = occluder
            clipped.clip(to: ink.oval(front.0, front.1, rx * squash, rx, angle: angle))
            clipped.fill(cover, with: .color(Color(hex: 0x1a2232)))
            var shine = gc
            shine.clip(to: ink.oval(front.0, front.1, rx * squash, rx, angle: angle))
            shine.fill(cover, with: .linearGradient(Gradient(colors: [pal[3].opacity(0.05), pal[3].opacity(0.4)]),
                                                     startPoint: lid(0, lidY - 1.5 * er), endPoint: lid(0, lidY)))
            var plate = Path()
            plate.addLines([lid(-er * 1.18, lidY), lid(er * 1.18, lidY), lid(er * 1.05, lidY - 0.08), lid(-er * 1.05, lidY - 0.08)])
            plate.closeSubpath()
            occluder.fill(plate, with: .color(solid))
            gc.fill(plate, with: .linearGradient(Gradient(colors: [pal[4].opacity(0.85), pal[2].opacity(0.5)]),
                                                 startPoint: lid(0, lidY - 0.08), endPoint: lid(0, lidY)))
            var edge = Path(); edge.move(to: lid(-er * 1.18, lidY)); edge.addLine(to: lid(er * 1.18, lidY))
            gc.stroke(edge, with: .color(Color.white.opacity(0.7)), style: StrokeStyle(lineWidth: d.px * 1.3, lineCap: .round))
        }
        // Speaking: a little flash of lightning at the first loud syllable after a pause.
        let hush = 1 - smoothstep(0.04, 0.12, engine.history.value(secondsAgo: 0.45))       // a pause just before
        let onset = s.speak * smoothstep(0.2, 0.45, s.loud) * hush
        let flash = min(1, onset + 3.5 * s.speak * (1 - s.speak) * min(1, 2 * s.loud))
        if flash > 0.02 {
            let o = (aTip.0 + 0.1, aTip.1 - 0.06)
            let bolt = ink.poly([(o.0, o.1 - 0.16), (o.0 - 0.05, o.1 - 0.01), (o.0 + 0.02, o.1 - 0.02), (o.0 - 0.03, o.1 + 0.15),
                                 (o.0 + 0.07, o.1 - 0.05), (o.0, o.1 - 0.04)])
            ink.glow(&gc, o.0, o.1, 0.32, blue, 0.6 * flash)
            gc.fill(bolt, with: .color(Color.white.opacity(0.95 * flash)))
            gc.stroke(bolt, with: .color(blue.opacity(0.8 * flash)), lineWidth: d.px)
        }
        // A brushed texture of points on the torso's front (fine horizontal grain).
        for j in 0..<Int(200 * k) + 20 {
            let u = evenPoint(j).0, v = evenPoint(j).1
            let x = -0.34 + 0.68 * u, y = 0.52 + 0.36 * v
            if abs(sin(y * 90)) < 0.5 { continue }
            let p = view.apply(x, y, 0.315), n = view.apply(0, 0, 1)
            place(&d, p.x, p.y, 0.45 * mMetal(n.x, n.y, n.z, shine: 0.6) + 0.08 * u, OrbPoints.hash(j, 14), phase: x, lum: 0.6, size: 0.65)
        }
        finish(&gc, d, palette: pal)
    }

    // MARK: Cruiser

    /// A sleek black car seen from the front and a little above: a low nose with a red light sweeping
    /// in a slot, headlights, a glossy dark body read by the light along its edges and on its glass, a
    /// soft glow of road under it. Calm and suave: at rest the scanner sweeps slowly and the body
    /// gleams; listening, the scanner comes to the centre, narrows and pulses with your voice, the
    /// headlights dim; thinking, it sweeps faster and wider and the dash glows; working, the
    /// headlights come on, the body lights up and streaks of light rush past (a boost) while the
    /// scanner races; speaking, three bars of light on the dash rise and fall with its voice.
    func drawCruiser(_ gc: inout GraphicsContext, _ box: CGSize) {
        let s = RobotState(engine, work)
        let rest = max(0, 1 - s.listen - s.th - s.busy - s.speak)
        // Square (a tile, the thumbnail): the whole car. Wide (the talk page): a little closer, the
        // fenders reaching the screen's edges, stretched only half the extra width (no distortion).
        let aspect = Double(box.width / max(1, box.height))
        let wide = smoothstep(1.02, 1.1, aspect)
        let d = robotCanvas(box, scale: 1.12 + 0.12 * wide, dy: 0)
        let wx = min(1.15, 1 + 0.5 * max(0, aspect - 1))
        let custom = look.color
        let pal: [Color] = custom.map { OrbPalette.colors(for: $0) } ?? [
            Color(hex: 0x1c2433).opacity(0.45), Color(hex: 0x354258).opacity(0.6), Color(hex: 0x5d6f8c).opacity(0.75),
            Color(hex: 0xa9bbd6).opacity(0.88), Color(hex: 0xeaf1fc).opacity(0.95)]
        let ink = Ink(d, pal)
        let red = custom ?? Color(hex: 0xff2d1e), redCore = custom ?? Color(hex: 0xff9078)
        let lamp = Color(hex: 0xfff1da), lampGlow = custom ?? Color(hex: 0xffe2b0)
        let edge = Color(hex: 0xdbe6f6)
        let oy = 0.12 - 0.02 * s.busy + 0.004 * sin(t * 41) * s.busy
        func P(_ x: Double, _ y: Double) -> CGPoint { ink.p(x * wx, y + oy) }
        func smooth(_ pts: [(Double, Double)], closed: Bool = true) -> Path { mSmooth(pts.map { P($0.0, $0.1) }, closed: closed) }
        func line(_ pts: [(Double, Double)]) -> Path { var p = Path(); p.addLines(pts.map { P($0.0, $0.1) }); return p }
        var occluder = gc
        occluder.blendMode = .normal
        // The road: a faint horizon behind it and a soft glow of road under it.
        gc.fill(Path(CGRect(x: 0, y: P(0, -0.53).y - 0.8 * d.px, width: box.width, height: 1.6 * d.px)),
                with: .linearGradient(Gradient(colors: [.clear, edge.opacity(0.22), edge.opacity(0.3), edge.opacity(0.22), .clear]),
                                      startPoint: CGPoint(x: 0, y: 0), endPoint: CGPoint(x: box.width, y: 0)))
        mSoftOval(&gc, P(0, -0.53), 2.6 * wx * d.R, 0.12 * d.R, Color(hex: 0x6f86ad), 0.2)
        mSoftOval(&gc, P(0, -0.53), 2.8 * wx * d.R, 0.9 * d.R, Color(hex: 0x2a3550), 0.22)
        mSoftOval(&gc, P(0, 0.66), 2.3 * wx * d.R, 0.3 * d.R, Color(hex: 0x5a6c8e), 0.3 + 0.15 * s.busy)
        // Working: streaks of light rushing past from the horizon (a boost), behind the car.
        if s.busy > 0.02 {
            var streaks = Path(), warmStreaks = Path()
            for i in 0..<22 {
                let h = OrbPoints.hash(i, 61), h2 = OrbPoints.hash(i, 62)
                let side: Double = i % 2 == 0 ? 1 : -1
                let ang = side > 0 ? -0.45 + 0.85 * h2 : Double.pi + 0.45 - 0.85 * h2
                let f = mFract(t * 0.85 + h)
                let r0 = 1.0 + 3.4 * f * f, r1 = r0 + 0.15 + 1.0 * f * f
                let a = (r0 * cos(ang), -0.53 + 0.55 * r0 * sin(ang)), b = (r1 * cos(ang), -0.53 + 0.55 * r1 * sin(ang))
                var p = Path(); p.move(to: P(a.0, a.1)); p.addLine(to: P(b.0, b.1))
                if i % 5 == 0 { warmStreaks.addPath(p) } else { streaks.addPath(p) }
            }
            gc.stroke(streaks, with: .color(edge.opacity(0.4 * s.busy)), style: StrokeStyle(lineWidth: d.px * 1.3, lineCap: .round))
            gc.stroke(warmStreaks, with: .color(red.opacity(0.5 * s.busy)), style: StrokeStyle(lineWidth: d.px * 1.4, lineCap: .round))
            // The road's markings rushing past under it, toward us.
            var dashes = Path()
            for side in [-1.0, 1.0] {
                for n in 0..<3 {
                    let f = mFract(t * 1.1 + Double(n) / 3), g = min(1, f + 0.12)
                    let a = (side * (0.9 + 1.6 * f * f), 0.62 + 1.0 * f * f), b = (side * (0.9 + 1.6 * g * g), 0.62 + 1.0 * g * g)
                    dashes.move(to: P(a.0, a.1)); dashes.addLine(to: P(b.0, b.1))
                }
            }
            gc.stroke(dashes, with: .color(edge.opacity(0.45 * s.busy)), style: StrokeStyle(lineWidth: d.px * 2, lineCap: .round))
        }
        // The tyres under the body's sides.
        for side in [-1.0, 1.0] {
            let tyre = Path(roundedRect: CGRect(x: min(P(side * 1.4, 0).x, P(side * 1.72, 0).x), y: P(0, 0.4).y,
                                                width: abs(P(1.72, 0).x - P(1.4, 0).x), height: 0.26 * d.R), cornerRadius: 0.07 * d.R)
            occluder.fill(tyre, with: .color(Color(hex: 0x040506)))
            gc.stroke(tyre, with: .linearGradient(Gradient(colors: [.clear, edge.opacity(0.14)]),
                                                  startPoint: P(side * 1.4, 0), endPoint: P(side * 1.72, 0)), lineWidth: d.px)
        }
        // The body: solid black, then its light.
        let outline: [(Double, Double)] = [
            (-1.68, 0.56), (-1.8, 0.36), (-1.81, 0.12), (-1.75, -0.06), (-1.58, -0.2), (-1.3, -0.31), (-1.04, -0.43),
            (-0.86, -0.8), (-0.6, -0.93), (0.6, -0.93), (0.86, -0.8), (1.04, -0.43), (1.3, -0.31), (1.58, -0.2),
            (1.75, -0.06), (1.81, 0.12), (1.8, 0.36), (1.68, 0.56), (0, 0.6)]
        let bodyPath = smooth(outline)
        occluder.fill(bodyPath, with: .color(Color(hex: 0x06080c)))
        let gleam = 1 + 0.7 * s.busy + 0.05 * sin(t * 0.9)
        gc.fill(bodyPath, with: .linearGradient(Gradient(colors: [Color(hex: 0x30394a).opacity(0.3), Color(hex: 0x141a24).opacity(0.2), Color(hex: 0x252d3c).opacity(0.3)]),
                                                startPoint: P(0, -0.9), endPoint: P(0, 0.6)))
        // The glass: deep blue-black, a diagonal reflection, the dash behind it.
        let glass = smooth([(-0.98, -0.45), (-0.8, -0.82), (-0.58, -0.88), (0.58, -0.88), (0.8, -0.82), (0.98, -0.45), (0, -0.42)])
        occluder.fill(glass, with: .color(Color(hex: 0x03050a)))
        gc.fill(glass, with: .linearGradient(Gradient(colors: [Color(hex: 0x4a5c7c).opacity(0.42), Color(hex: 0x1a2232).opacity(0.18), Color(hex: 0x0c1018).opacity(0.1)]),
                                             startPoint: P(0, -0.9), endPoint: P(0, -0.44)))
        var reflect = gc
        reflect.clip(to: glass)
        reflect.fill(line([(-0.7, -0.9), (-0.42, -0.9), (0.05, -0.4), (-0.25, -0.4)]), with: .color(Color.white.opacity(0.07)))
        reflect.fill(line([(-0.3, -0.9), (-0.22, -0.9), (0.26, -0.4), (0.18, -0.4)]), with: .color(Color.white.opacity(0.05)))
        // Thinking: the dash glows softly through the glass, little lights twinkling along it.
        if s.th > 0.01 {
            reflect.fill(glass, with: .radialGradient(Gradient(colors: [red.opacity(0.32 * s.th), red.opacity(0.08 * s.th), .clear]),
                                                      center: P(0, -0.47), startRadius: 0, endRadius: 0.9 * wx * d.R))
            var dots = Path()
            let tick = Int((t * 5).rounded(.down))
            for i in 0..<10 where OrbPoints.hash(tick &+ i * 7, 9) < 0.5 {
                let x = -0.68 + 0.15 * Double(i)
                dots.addEllipse(in: CGRect(x: P(x, 0).x - 1.3 * d.px, y: P(0, -0.5).y - 1.3 * d.px, width: 2.6 * d.px, height: 2.6 * d.px))
            }
            gc.fill(dots, with: .color(redCore.opacity(0.85 * s.th)))
        }
        // Speaking: three bars of light on the dash, rising and falling with its voice (mirrored
        // about their middle, the centre one the tallest).
        if s.speak > 0.01 {
            let levels = [0.15 + 0.95 * s.spectrum.band(at: 0.2), 0.25 + 1.1 * s.loud, 0.15 + 0.95 * s.spectrum.band(at: 0.75)]
            var lit = Path(), dim = Path()
            for (n, lv) in levels.enumerated() {
                let x = -0.2 + 0.2 * Double(n)
                let segs = n == 1 ? 5 : 4
                for j in -segs..<segs {
                    let y0 = -0.655 + 0.038 * Double(j)
                    let r = CGRect(x: P(x - 0.06, 0).x, y: P(0, y0 + 0.006).y, width: P(0.12, 0).x - P(0, 0).x, height: 0.026 * d.R)
                    let reach = abs(Double(j) + 0.5) / Double(segs)
                    if reach < min(1, lv) { lit.addRect(r) } else { dim.addRect(r) }
                }
            }
            reflect.fill(glass, with: .radialGradient(Gradient(colors: [red.opacity(0.22 * s.speak * (0.5 + s.loud)), .clear]),
                                                      center: P(0, -0.66), startRadius: 0, endRadius: 0.6 * wx * d.R))
            gc.fill(dim, with: .color(red.opacity(0.16 * s.speak)))
            gc.fill(lit, with: .color(redCore.opacity(0.95 * s.speak)))
            gc.stroke(lit, with: .color(red.opacity(0.5 * s.speak)), lineWidth: d.px * 2)
        }
        // The hood: lit by the sky, brighter toward the glass, a crease down its middle; a slow
        // shimmer crossing it.
        let hood = smooth([(-1.02, -0.43), (0, -0.41), (1.02, -0.43), (1.5, -0.03), (0.8, 0.03), (0, 0.05), (-0.8, 0.03), (-1.5, -0.03)])
        gc.fill(hood, with: .linearGradient(Gradient(colors: [Color(hex: 0x5a6a86).opacity(0.38), Color(hex: 0x262e3e).opacity(0.14), Color(hex: 0x3c4860).opacity(0.3)]),
                                            startPoint: P(0, -0.42), endPoint: P(0, 0.04)))
        var onHood = gc
        onHood.clip(to: hood)
        let sweep = mFract(t * 0.055) * 5 - 2.5
        onHood.fill(hood, with: .linearGradient(Gradient(stops: [.init(color: .clear, location: 0), .init(color: Color.white.opacity(0.1 * gleam), location: 0.5),
                                                                  .init(color: .clear, location: 1)]),
                                                startPoint: P(sweep - 0.5, -0.5), endPoint: P(sweep + 0.3, 0.1)))
        gc.stroke(line([(0, -0.41), (0, 0.05)]), with: .linearGradient(Gradient(colors: [edge.opacity(0.35), edge.opacity(0.05)]),
                                                                    startPoint: P(0, -0.41), endPoint: P(0, 0.05)), lineWidth: d.px)
        for side in [-1.0, 1.0] {
            gc.stroke(smooth([(side * 0.56, -0.42), (side * 0.7, -0.2), (side * 0.86, 0.03)], closed: false),
                      with: .color(edge.opacity(0.12 * gleam)), lineWidth: d.px)
        }
        // Its edges of light: the roof, the pillars, the fenders' crests, the nose, the lip.
        let crest = 0.5 * gleam
        gc.stroke(smooth([(-0.6, -0.93), (0, -0.95), (0.6, -0.93)], closed: false), with: .color(edge.opacity(0.6 * gleam)), lineWidth: d.px * 1.2)
        for side in [-1.0, 1.0] {
            gc.stroke(line([(side * 0.6, -0.92), (side * 0.85, -0.8), (side * 1.03, -0.44)]), with: .color(edge.opacity(0.32 * gleam)), lineWidth: d.px)
            let fender = smooth([(side * 1.04, -0.43), (side * 1.3, -0.31), (side * 1.58, -0.2), (side * 1.75, -0.06), (side * 1.81, 0.12)], closed: false)
            gc.stroke(fender, with: .color(edge.opacity(0.14 * gleam)), lineWidth: d.px * 4)
            gc.stroke(fender, with: .linearGradient(Gradient(colors: [edge.opacity(0.75 * crest), edge.opacity(0.2 * crest)]),
                                                    startPoint: P(side * 1.0, -0.45), endPoint: P(side * 1.8, 0.1)), lineWidth: d.px * 1.2)
            gc.stroke(smooth([(side * 1.81, 0.14), (side * 1.8, 0.36), (side * 1.68, 0.56)], closed: false), with: .color(edge.opacity(0.15 * gleam)), lineWidth: d.px)
        }
        let nose = smooth([(-1.5, -0.03), (-0.8, 0.03), (0, 0.05), (0.8, 0.03), (1.5, -0.03)], closed: false)
        gc.stroke(nose, with: .color(edge.opacity(0.18 * gleam)), lineWidth: d.px * 3.5)
        gc.stroke(nose, with: .color(edge.opacity(0.7 * gleam)), lineWidth: d.px * 1.1)
        let lip = smooth([(-1.62, 0.47), (0, 0.52), (1.62, 0.47)], closed: false)
        gc.stroke(lip, with: .linearGradient(Gradient(colors: [.clear, edge.opacity(0.45 * gleam), edge.opacity(0.45 * gleam), .clear]),
                                             startPoint: P(-1.62, 0), endPoint: P(1.62, 0)), lineWidth: d.px * 1.1)
        // The intake low on the nose.
        let intake = smooth([(-0.82, 0.34), (0.82, 0.34), (0.86, 0.4), (-0.86, 0.4)])
        occluder.fill(intake, with: .color(Color(hex: 0x020305)))
        gc.stroke(intake, with: .color(edge.opacity(0.16)), lineWidth: d.px)
        // Working: a glint running along the lip (the body lit up).
        if s.busy > 0.02 {
            let f = mFract(t * 0.9)
            let gx = -1.6 + 3.2 * f
            gc.fill(Path(ellipseIn: CGRect(x: P(gx, 0).x - 0.25 * d.R, y: P(0, 0.495).y - 0.03 * d.R, width: 0.5 * d.R, height: 0.06 * d.R)),
                    with: .radialGradient(Gradient(colors: [Color.white.opacity(0.7 * s.busy * sin(Double.pi * f)), .clear]),
                                          center: P(gx, 0.495), startRadius: 0, endRadius: 0.25 * d.R))
        }
        // The headlights: slim and slanted, warm white; dim as it listens, full on as it works.
        let hl = 0.42 * rest + 0.14 * s.listen + 0.36 * s.th + 1.0 * s.busy + 0.46 * s.speak
        for side in [-1.0, 1.0] {
            let quad = smooth([(side * 1.1, 0.09), (side * 1.58, 0.04), (side * 1.62, 0.16), (side * 1.12, 0.2)])
            occluder.fill(quad, with: .color(Color(hex: 0x05070a)))
            let c = P(side * 1.36, 0.12)
            gc.fill(quad, with: .radialGradient(Gradient(colors: [lamp.opacity(min(1, 0.95 * hl + 0.08)), lampGlow.opacity(min(1, 0.5 * hl + 0.05)), lampGlow.opacity(0.1)]),
                                                center: c, startRadius: 0, endRadius: 0.3 * wx * d.R))
            gc.stroke(quad, with: .color(edge.opacity(0.35)), lineWidth: d.px)
            ink.glow(&gc, side * 1.36 * wx, 0.12 + oy, 0.42 + 0.4 * s.busy, lampGlow, 0.32 * hl)
            if s.busy > 0.02 { ink.glow(&gc, side * 1.36 * wx, 0.14 + oy, 1.1, lampGlow, 0.22 * s.busy) }
            // On the road: the headlight's reflection.
            mSoftOval(&gc, P(side * 1.36, 0.86), 0.09 * d.R, 0.28 * d.R, lampGlow, 0.16 * hl)
        }
        // The scanner: a slot across the nose, a red light sweeping in it with a fading trail.
        let slot = smooth([(-0.94, 0.13), (0.94, 0.13), (0.97, 0.19), (0.94, 0.25), (-0.94, 0.25), (-0.97, 0.19)])
        occluder.fill(slot, with: .color(Color(hex: 0x030203)))
        gc.fill(slot, with: .linearGradient(Gradient(colors: [red.opacity(0.03), red.opacity(0.12), red.opacity(0.03)]), startPoint: P(-0.95, 0), endPoint: P(0.95, 0)))
        gc.stroke(slot, with: .color(edge.opacity(0.3)), lineWidth: d.px)
        func sweepAt(_ tt: Double) -> Double {
            rest * 0.8 * sin(tt * 2.3) + s.th * 0.92 * sin(tt * 4.2) + s.busy * 0.94 * sin(tt * 7.4) + s.speak * 0.2 * sin(tt * 1.4)
        }
        let lampW = 0.13 - 0.06 * s.listen + 0.04 * s.busy
        let scanB = 0.8 + s.listen * (1.0 * s.level - 0.15) + 0.25 * s.busy + 0.35 * s.voice + 0.08 * rest * sin(t * 1.1)
        let x0 = 0.8 * sweepAt(t)
        for n in stride(from: 10, through: 1, by: -1) {
            let xn = 0.8 * sweepAt(t - 0.03 * Double(n))
            let a = scanB * 0.55 * pow(1 - Double(n) / 11, 1.5) * (1 - 0.8 * s.listen)
            gc.fill(Path(ellipseIn: CGRect(x: P(xn, 0).x - lampW * d.R, y: P(0, 0.19).y - 0.045 * d.R, width: 2 * lampW * d.R, height: 0.09 * d.R)),
                    with: .radialGradient(Gradient(colors: [red.opacity(min(1, a)), .clear]), center: P(xn, 0.19), startRadius: 0, endRadius: lampW * d.R))
        }
        ink.glow(&gc, x0 * wx, 0.19 + oy, 0.5, red, 0.4 * scanB)
        gc.fill(Path(ellipseIn: CGRect(x: P(x0, 0).x - lampW * d.R, y: P(0, 0.19).y - 0.04 * d.R, width: 2 * lampW * d.R, height: 0.08 * d.R)),
                with: .radialGradient(Gradient(colors: [Color.white.opacity(min(1, 0.9 * scanB)), redCore.opacity(min(1, scanB)), red.opacity(min(1, 0.7 * scanB))]),
                                      center: P(x0, 0.19), startRadius: 0, endRadius: lampW * d.R))
        // Its light on the nose's edge and on the road.
        ink.glow(&gc, x0 * wx, 0.05 + oy, 0.22, red, 0.22 * scanB)
        mSoftOval(&gc, P(x0, 0.88), 0.1 * d.R, 0.3 * d.R, red, 0.2 * scanB)
        finish(&gc, d, palette: pal)
    }

    // MARK: Android

    /// A calm android face, a quiet tribute: pale gold skin, amber-yellow eyes, dark hair combed
    /// straight back from a high forehead, a composed, curious expression. Its tells are in how it
    /// behaves: a precise, slightly too regular blink; listening, it turns to you with a small polite
    /// nod, its eyes bright with your voice; thinking, a tilt of the head, one brow raised, its eyes
    /// to the side and a soft glow within; working, its eyes dart in a quick fixed pattern (as if
    /// reaching into memory) and a faint shimmer crosses its face; speaking, precise movements of
    /// the mouth with the voice, small turns of the head, a hint of a smile. Painted like a lit
    /// portrait: the skin, hair, neck and collar as soft gradients in one softly blurred layer (no
    /// cut-out edges), the features over it drawn gently, a key light from the upper left and a cool
    /// rim light on the far side.
    func drawAndroid(_ gc: inout GraphicsContext, _ box: CGSize) {
        let s = RobotState(engine, work)
        let rest = max(0, 1 - s.listen - s.th - s.busy - s.speak)
        let d = robotCanvas(box, scale: 1.4 * (1 + 0.045 * s.listen), dy: 0.06)
        let custom = look.color
        let pal: [Color] = custom.map { OrbPalette.colors(for: $0) } ?? [
            Color(hex: 0x6a5a3e).opacity(0.45), Color(hex: 0xa4926c).opacity(0.6), Color(hex: 0xd8c8a2).opacity(0.75),
            Color(hex: 0xf1e7cf).opacity(0.88), Color(hex: 0xfffaee).opacity(0.95)]
        let ink = Ink(d, pal)
        let amber = custom ?? Color(hex: 0xffc845), amberDeep = custom ?? Color(hex: 0xd09020)
        let rimLight = custom ?? Color(hex: 0xb4cfff)
        // The pose: composed, a little turned at rest; facing you to listen, a polite nod; a tilt
        // and a look aside to think; small turns as it speaks.
        let nod = pow(max(0, sin(2 * Double.pi * t / 2.8)), 4)
        let yaw = rest * (0.15 + 0.05 * sin(t * 0.17)) - 0.13 * s.th + s.speak * (0.05 + 0.07 * sin(t * 0.55)) + s.busy * (0.07 + 0.02 * sin(t * 0.9))
        let pitch = 0.025 * sin(t * 0.13) + s.listen * 0.1 * nod - 0.07 * s.th + 0.05 * s.speak * engine.history.value(secondsAgo: 0.15)
        let roll = 0.018 * sin(t * 0.11) + 0.15 * s.th - 0.02 * s.listen
        let head = Turn3(yaw: yaw, pitch: pitch, roll: roll)
        let hy = -0.14, hw = 0.64, hh = 0.9, hd = 0.66
        func widthAt(_ y: Double) -> Double {
            let ny = min(1, max(-1, y / hh))
            return hw * (ny > 0 ? 1 - 0.24 * pow(ny, 2.2) : 1 - 0.07 * ny * ny)
        }
        func front(_ x: Double, _ y: Double) -> Double {
            hd * max(0, 1 - pow(x / widthAt(y), 2) - pow(y / hh, 2)).squareRoot() + 0.01
        }
        /// A point of the face (head coordinates, its centre the origin) on the screen.
        func F(_ x: Double, _ y: Double, lift: Double = 0) -> (Double, Double) {
            let p = head.apply(x, y, front(x, y) + lift)
            return (p.x, p.y + hy)
        }
        func FP(_ x: Double, _ y: Double, lift: Double = 0) -> CGPoint { let q = F(x, y, lift: lift); return ink.p(q.0, q.1) }
        let cr = cos(roll), sr = sin(roll), shift = 0.18 * hd * sin(yaw)
        /// The head's outline at angle `a` (a squarer jaw below, a rounded crown above), leaning with it.
        func outlinePoint(_ a: Double, _ sx: Double = 1, _ sy: Double = 1) -> (Double, Double) {
            let c = cos(a), sn = sin(a)
            var x: Double, y: Double
            if sn > 0 {
                x = hw * (c < 0 ? -1 : 1) * pow(abs(c), 0.6) * (1 - 0.3 * pow(sn, 2.4))
                y = hh * pow(sn, 0.95)
            } else {
                x = hw * c * (1 - 0.06 * sn * sn); y = hh * sn
            }
            x *= sx; y *= sy
            return (x * cr - y * sr + shift, x * sr + y * cr + hy)
        }
        func hex(_ v: UInt32, _ a: Double = 1) -> Color { Color(hex: v).opacity(a) }
        let headPath = ink.poly((0..<48).map { outlinePoint(2 * Double.pi * Double($0) / 48) })
        let centre = F(0, 0)
        let hairline: [(Double, Double)] = [(-0.62, 0.02), (-0.6, -0.2), (-0.57, -0.36), (-0.5, -0.5), (-0.36, -0.6), (-0.16, -0.625),
                                            (0, -0.585), (0.16, -0.625), (0.36, -0.6), (0.5, -0.5), (0.57, -0.36), (0.6, -0.2), (0.62, 0.02)]
        func hairlineY(_ x: Double) -> Double {
            for i in 1..<hairline.count where x <= hairline[i].0 {
                let a = hairline[i - 1], b = hairline[i], f = (x - a.0) / max(1e-6, b.0 - a.0)
                return a.1 + (b.1 - a.1) * f
            }
            return hairline.last!.1
        }
        // The hair's mass: fuller over the crown, close at the sides.
        var hairPts = hairline.map { F($0.0, $0.1) }
        hairPts += stride(from: 0.04, through: -Double.pi - 0.04, by: -Double.pi / 20).map { a -> (Double, Double) in
            let up = abs(sin(a))
            return outlinePoint(a, 1.035 + 0.04 * up, 1.0 + 0.1 * up)
        }
        let hair = mSmooth(hairPts.map { ink.p($0.0, $0.1) })
        let crown = outlinePoint(-Double.pi / 2 - 0.12, 1.06, 1.08)
        let neckTop = 0.5 + hy
        let collarTop = 1.0
        // The soft base: collar and shoulders, neck, ears, skin and hair, painted in one layer blurred a
        // little, so every silhouette and every shade melts into the next.
        gc.drawLayer { layer in
            layer.addFilter(.blur(radius: d.px * 0.75))
            layer.blendMode = .normal
            // Shoulders in a plain dark collarless top, lit from the left, fading into the dark.
            let shoulders = mSmooth([ink.p(-1.9, 2.1), ink.p(-1.6, 1.45), ink.p(-0.9, 1.16), ink.p(-0.36, collarTop + 0.02),
                                     ink.p(0.36, collarTop + 0.02), ink.p(0.9, 1.16), ink.p(1.6, 1.45), ink.p(1.9, 2.1)])
            layer.fill(shoulders, with: .linearGradient(Gradient(stops: [.init(color: hex(0x2a2d34), location: 0), .init(color: hex(0x16181d), location: 0.45),
                                                                         .init(color: hex(0x0c0d10, 0), location: 1)]),
                                                        startPoint: ink.p(-0.8, 1.05), endPoint: ink.p(0.3, 1.9)))
            mSoftOval(&layer, ink.p(0, collarTop + 0.12), 0.75 * d.R, 0.22 * d.R, Color.black, 0.55)          // the neck's shadow on the collar
            // The neck: a lit column, darker at its sides, deep in shadow under the jaw.
            let neck = ink.poly([(-0.34 + shift, neckTop), (0.34 + shift, neckTop), (0.37, collarTop + 0.08), (-0.37, collarTop + 0.08)])
            layer.fill(neck, with: .linearGradient(Gradient(stops: [.init(color: hex(0x6c5f48), location: 0), .init(color: hex(0xb9a982), location: 0.32),
                                                                    .init(color: hex(0xa49470), location: 0.55), .init(color: hex(0x4e4434), location: 1)]),
                                                   startPoint: ink.p(-0.36, 0), endPoint: ink.p(0.36, 0)))
            mSoftOval(&layer, ink.p(shift, neckTop + 0.12), 0.48 * d.R, 0.24 * d.R, hex(0x231c12), 0.75)
            // The collar: a plain dark band round the neck's base, its top edge catching the light.
            let collar = mSmooth([ink.p(-0.46, collarTop + 0.14), ink.p(-0.4, collarTop - 0.04), ink.p(0, collarTop + 0.03),
                                  ink.p(0.4, collarTop - 0.04), ink.p(0.46, collarTop + 0.14), ink.p(0, collarTop + 0.2)])
            layer.fill(collar, with: .linearGradient(Gradient(colors: [hex(0x3a3e46), hex(0x1a1c21), hex(0x111216)]),
                                                     startPoint: ink.p(-0.45, collarTop), endPoint: ink.p(0.45, collarTop + 0.15)))
            // The ears.
            for side in [-1.0, 1.0] {
                let c = outlinePoint(side > 0 ? 0.1 : Double.pi - 0.1)
                let ear = ink.oval(c.0 + side * 0.03, c.1, 0.08, 0.16, angle: roll)
                layer.fill(ear, with: .radialGradient(Gradient(colors: [hex(side < 0 ? 0xcdbd98 : 0xa8987a), hex(0x6a5c44)]), center: ink.p(c.0, c.1 - 0.04),
                                                      startRadius: 0, endRadius: 0.17 * d.R))
                mSoftOval(&layer, ink.p(c.0 + side * 0.03, c.1 + 0.03), 0.03 * d.R, 0.08 * d.R, angle: roll, hex(0x3e3424), 0.55)
            }
            // The skin: pale gold, a key light from the upper left falling off round the face.
            let key = F(-0.26, -0.32)
            layer.fill(headPath, with: .radialGradient(Gradient(stops: [
                .init(color: hex(0xf9f1dc), location: 0), .init(color: hex(0xeedab0), location: 0.28),
                .init(color: hex(0xcfb787), location: 0.6), .init(color: hex(0x8c7650), location: 0.86), .init(color: hex(0x564630), location: 1)]),
                center: ink.p(key.0, key.1), startRadius: 0, endRadius: 1.42 * d.R))
            var face = layer
            face.clip(to: headPath)
            // The face turning away from the light at its edges (a soft darkening all round it).
            mSoftOval(&face, ink.p(centre.0, centre.1 + 0.02), (hw + 0.06) * d.R, (hh + 0.04) * d.R, angle: roll,
                      [.init(color: .clear, location: 0), .init(color: .clear, location: 0.62), .init(color: hex(0x2e2618, 0.55), location: 1)])
            func shade(_ x: Double, _ y: Double, _ rx: Double, _ ry: Double, _ a: Double, _ color: UInt32 = 0x4a3a24) {
                mSoftOval(&face, FP(x, y), rx * d.R, ry * d.R, angle: roll, hex(color), a)
            }
            func light(_ x: Double, _ y: Double, _ rx: Double, _ ry: Double, _ a: Double, lift: Double = 0) {
                mSoftOval(&face, FP(x, y, lift: lift), rx * d.R, ry * d.R, angle: roll, hex(0xfffaee), a)
            }
            // Modelling: the brow ridge's light, the sockets, the temples, the cheekbones and the hollow
            // under them, the nose (lit ridge, shaded far side, wings), under the nose, the lips' shadow,
            // the chin, the jaw.
            light(-0.08, -0.36, 0.3, 0.14, 0.4)
            for side in [-1.0, 1.0] {
                shade(side * 0.22, -0.07, 0.2, 0.12, side < 0 ? 0.45 : 0.55)
                shade(side * 0.56, -0.2, 0.15, 0.3, side < 0 ? 0.2 : 0.34)
                light(side * 0.3, 0.13, 0.16, 0.08, side < 0 ? 0.45 : 0.1)
                shade(side * 0.4, 0.38, 0.22, 0.24, side < 0 ? 0.08 : 0.2)
                shade(side * 0.075, 0.27, 0.045, 0.04, 0.5)
            }
            light(-0.012, 0.06, 0.03, 0.16, 0.5, lift: 0.05)
            shade(0.065, 0.07, 0.045, 0.18, 0.5)
            light(-0.01, 0.23, 0.045, 0.035, 0.45, lift: 0.08)
            shade(0.02, 0.33, 0.1, 0.042, 0.55)
            shade(0.0, 0.4, 0.025, 0.04, 0.15)
            shade(0, 0.585, 0.13, 0.05, 0.42)
            light(-0.03, 0.7, 0.12, 0.06, 0.25)
            shade(0.1, 0.92, 0.6, 0.18, 0.4)
            // A soft shade along the hairline.
            shade(0, -0.56, 0.62, 0.07, 0.3)
            // The hair: near black, combed straight back, the crown's volume catching a soft light.
            layer.fill(hair, with: .radialGradient(Gradient(stops: [.init(color: hex(0x4a4038), location: 0), .init(color: hex(0x2a221c), location: 0.35),
                                                                    .init(color: hex(0x16110e), location: 0.75), .init(color: hex(0x0c0907), location: 1)]),
                                                   center: ink.p(crown.0 - 0.22, crown.1 + 0.18), startRadius: 0, endRadius: 1.0 * d.R))
        }
        // The light over the base: a sheen across the hair's volume, fine combed strands, the cool rim.
        var onHair = gc
        onHair.clip(to: hair)
        mSoftOval(&onHair, ink.p(crown.0 - 0.1, crown.1 + 0.2), 0.5 * d.R, 0.13 * d.R, angle: roll - 0.14, hex(0xa9b4c8), 0.34)
        var strands = Path()
        for i in 0..<9 {
            let x = -0.5 + 0.125 * Double(i)
            let a = F(x, hairlineY(x) - 0.02)
            let b = outlinePoint(-Double.pi / 2 + 0.62 * x, 1.06, 1.08)
            let c = F(x * 1.02, hairlineY(x) - 0.27)
            strands.move(to: ink.p(a.0, a.1)); strands.addQuadCurve(to: ink.p(b.0, b.1), control: ink.p(c.0, c.1))
        }
        onHair.stroke(strands, with: .color(hex(0x9aa6ba, 0.035)), lineWidth: d.px * 0.8)
        let rimShade = GraphicsContext.Shading.linearGradient(Gradient(stops: [.init(color: .clear, location: 0), .init(color: .clear, location: 0.6),
                                                                              .init(color: rimLight.opacity(0.1), location: 1)]),
                                                               startPoint: ink.p(-0.65 + shift, 0), endPoint: ink.p(0.7 + shift, 0))
        gc.stroke(headPath, with: rimShade, lineWidth: d.px * 4)
        var rimFace = gc
        rimFace.clip(to: headPath)
        rimFace.fill(headPath, with: .linearGradient(Gradient(stops: [.init(color: .clear, location: 0), .init(color: .clear, location: 0.78),
                                                                       .init(color: rimLight.opacity(0.12), location: 1)]),
                                                      startPoint: ink.p(-0.65 + shift, 0), endPoint: ink.p(0.66 + shift, 0)))
        var paint = gc
        paint.blendMode = .normal
        // Thinking: a soft glow within, behind the brow.
        if s.th > 0.01 {
            let g = F(-0.05, -0.28)
            ink.glow(&gc, g.0, g.1, 0.6, amber, 0.22 * s.th * (0.85 + 0.15 * sin(t * 1.4)))
        }
        // The brows: soft and dark, level and composed; one lifts as it thinks (curiosity).
        for side in [-1.0, 1.0] {
            let lift = side > 0 ? 0.06 * s.th + 0.012 * s.listen : 0.012 * s.listen - 0.008 * s.th
            let arch = side > 0 ? 0.02 + 0.035 * s.th : 0.02
            var brow = Path()
            brow.move(to: FP(side * 0.1, -0.18 - 0.6 * lift))
            brow.addQuadCurve(to: FP(side * 0.37, -0.165 - 0.7 * lift), control: FP(side * 0.25, -0.23 - arch - lift))
            paint.stroke(brow, with: .color(hex(0x3a2e20, 0.25)), style: StrokeStyle(lineWidth: 0.042 * d.R, lineCap: .round))
            paint.stroke(brow, with: .color(hex(0x241a12, 0.8)), style: StrokeStyle(lineWidth: 0.022 * d.R, lineCap: .round))
        }
        // The eyes: a soft white shaded under the lid, an amber iris with depth, a catchlight; the lids
        // and lashes drawn softly; a precise blink.
        let fb = mFract(t / 4.2)
        let shut = smoothstep(0, 0.012, fb) * (1 - smoothstep(0.03, 0.045, fb))
        let open = 1 - 0.94 * shut
        let dartTo = mGlance(t, period: 0.19, salt: 5, move: 0.35)
        let drift = mGlance(t, period: 3.4, salt: 8, move: 0.3)
        let gazeX = 0.25 * drift.x * rest - 0.75 * s.th + 0.8 * dartTo.x * s.busy + 0.1 * s.speak * sin(t * 0.7)
        let gazeY = 0.12 * drift.y * rest - 0.35 * s.th + 0.45 * dartTo.y * s.busy
        let irisB = 0.75 + 0.5 * s.listen * (0.3 + s.level) + 0.2 * s.th + 0.15 * s.busy + 0.15 * s.voice
        let facing = head.apply(0, 0, 1)
        let squash = max(0.3, facing.z), fAngle = atan2(facing.y, facing.x)
        for side in [-1.0, 1.0] {
            let ex = side * 0.225, ey = -0.045
            let inner = FP(side * 0.105, ey + 0.006), outer = FP(side * 0.35, ey - 0.008)
            let up = FP(ex - side * 0.012, ey - 0.1 * open), down = FP(ex, ey + 0.068 * max(0.12, open))
            var almond = Path()
            almond.move(to: inner)
            almond.addQuadCurve(to: outer, control: up)
            almond.addQuadCurve(to: inner, control: down)
            almond.closeSubpath()
            paint.fill(almond, with: .linearGradient(Gradient(stops: [.init(color: hex(0x9c917e), location: 0), .init(color: hex(0xd9d0bd), location: 0.45),
                                                                      .init(color: hex(0xe6ddca), location: 0.7), .init(color: hex(0xc4b9a4), location: 1)]),
                                                     startPoint: FP(ex, ey - 0.05), endPoint: FP(ex, ey + 0.04)))
            var inEye = paint
            inEye.clip(to: almond)
            for c in [inner, outer] {
                mSoftOval(&inEye, c, 0.05 * d.R, 0.04 * d.R, hex(0x6a5a44), 0.5)                    // the corners in shade
            }
            let ic = F(ex + 0.05 * gazeX, ey - 0.004 + 0.022 * gazeY)
            let ir = 0.066
            let iris = ink.oval(ic.0, ic.1, ir * squash, ir, angle: fAngle)
            inEye.fill(iris, with: .radialGradient(Gradient(stops: [
                .init(color: hex(0x120a03), location: 0), .init(color: hex(0x120a03), location: 0.27), .init(color: hex(0x7a5212), location: 0.33),
                .init(color: amber, location: 0.47), .init(color: amberDeep, location: 0.78), .init(color: hex(0x8a5c14), location: 0.92),
                .init(color: hex(0x3e2a0a), location: 1)]),
                center: ink.p(ic.0, ic.1), startRadius: 0, endRadius: ir * d.R))
            mSoftOval(&inEye, ink.p(ic.0, ic.1 - 0.5 * ir), ir * 1.6 * d.R, 0.55 * ir * d.R, hex(0x3a2a16), 0.45)   // the lid's shadow
            var glowEye = gc
            glowEye.clip(to: almond)
            glowEye.fill(iris, with: .radialGradient(Gradient(colors: [.clear, amber.opacity(0.36 * irisB), .clear]),
                                                     center: ink.p(ic.0, ic.1), startRadius: 0, endRadius: ir * d.R))
            if open > 0.5 {
                glowEye.fill(ink.circle(ic.0 - 0.022, ic.1 - 0.024, 0.013), with: .color(Color.white.opacity(0.85)))
                glowEye.fill(ink.circle(ic.0 + 0.024, ic.1 + 0.022, 0.006), with: .color(Color.white.opacity(0.3)))
            }
            ink.glow(&gc, ic.0, ic.1, 0.14, amber, (0.08 + 0.12 * s.listen * s.level) * irisB * open)
            // The lids: the upper lid's lashes a soft dark line, heavier toward the outer corner, a
            // faint crease above; the lower lid a light rim with a soft shade under it.
            var upper = Path(); upper.move(to: inner); upper.addQuadCurve(to: outer, control: up)
            paint.stroke(upper, with: .color(hex(0x2a1c10, 0.16)), style: StrokeStyle(lineWidth: d.px * 2.6, lineCap: .round))
            paint.stroke(upper, with: .color(hex(0x22160c, 0.75)), style: StrokeStyle(lineWidth: d.px * 1.3, lineCap: .round))
            var lash = Path()
            lash.move(to: FP(ex + side * 0.03, ey - 0.072 * open)); lash.addQuadCurve(to: FP(side * 0.362, ey - 0.02), control: FP(ex + side * 0.1, ey - 0.07 * open))
            paint.stroke(lash, with: .color(hex(0x1c1208, 0.6)), style: StrokeStyle(lineWidth: d.px * 1.9, lineCap: .round))
            var crease = Path(); crease.move(to: FP(side * 0.12, ey - 0.04)); crease.addQuadCurve(to: FP(side * 0.33, ey - 0.05), control: FP(ex, ey - 0.135))
            paint.stroke(crease, with: .color(hex(0x6a5a40, 0.22)), style: StrokeStyle(lineWidth: d.px * 1.2, lineCap: .round))
            var lower = Path(); lower.move(to: inner); lower.addQuadCurve(to: outer, control: down)
            paint.stroke(lower, with: .color(hex(0x6a5a40, 0.35)), style: StrokeStyle(lineWidth: d.px * 1.6, lineCap: .round))
            gc.stroke(lower, with: .color(hex(0xfff6e4, 0.12)), lineWidth: d.px * 0.8)
        }
        // The mouth: lips with volume (a darker upper lip, a fuller lit lower one), precise openings
        // with its voice, a hint of a smile.
        let my = 0.48
        let smile = 0.006 + 0.014 * s.speak + 0.004 * s.listen
        let openM = s.speak * min(1, 0.15 + 1.1 * s.loud) * 0.065
        let halfW = 0.14 + 0.025 * s.speak * s.spectrum.band(at: 0.8) - 0.015 * s.speak * s.spectrum.band(at: 0.15)
        let lc = FP(-halfW, my - smile), rc = FP(halfW, my - smile)
        let lowerBottom = FP(0, my + 0.07 + openM)
        if openM > 0.002 {
            var inside = Path()
            inside.move(to: lc)
            inside.addQuadCurve(to: rc, control: FP(0, my - 0.005))
            inside.addQuadCurve(to: lc, control: FP(0, my + 0.008 + 1.6 * openM))
            inside.closeSubpath()
            paint.fill(inside, with: .linearGradient(Gradient(colors: [hex(0x1a0e08), hex(0x3a2216)]), startPoint: FP(0, my), endPoint: FP(0, my + openM)))
        }
        var lowerLip = Path()
        lowerLip.move(to: lc)
        lowerLip.addQuadCurve(to: rc, control: FP(0, my + 0.012 + 1.6 * openM))
        lowerLip.addQuadCurve(to: lc, control: lowerBottom)
        lowerLip.closeSubpath()
        paint.fill(lowerLip, with: .linearGradient(Gradient(stops: [.init(color: hex(0x8c6a50), location: 0), .init(color: hex(0xbc9c7e), location: 0.5),
                                                                    .init(color: hex(0xa88a6c), location: 1)]),
                                                   startPoint: FP(0, my), endPoint: lowerBottom))
        let lit = F(-0.03, my + 0.035 + openM)
        mSoftOval(&gc, ink.p(lit.0, lit.1), 0.06 * d.R, 0.016 * d.R, angle: roll, hex(0xfff4e2), 0.22)
        var upperLip = Path()
        upperLip.move(to: lc)
        upperLip.addQuadCurve(to: FP(-0.022, my - 0.033), control: FP(-0.08, my - 0.036))
        upperLip.addQuadCurve(to: FP(0.022, my - 0.033), control: FP(0, my - 0.022))
        upperLip.addQuadCurve(to: rc, control: FP(0.08, my - 0.036))
        upperLip.addQuadCurve(to: lc, control: FP(0, my + 0.012))
        upperLip.closeSubpath()
        paint.fill(upperLip, with: .linearGradient(Gradient(colors: [hex(0xa48468), hex(0x80604a)]), startPoint: FP(0, my - 0.035), endPoint: FP(0, my + 0.01)))
        var lipSeam = Path(); lipSeam.move(to: lc); lipSeam.addQuadCurve(to: rc, control: FP(0, my + 0.012 + 0.8 * openM))
        paint.stroke(lipSeam, with: .color(hex(0x3e2618, 0.25)), style: StrokeStyle(lineWidth: d.px * 2.6, lineCap: .round))
        paint.stroke(lipSeam, with: .color(hex(0x3e2618, 0.7)), style: StrokeStyle(lineWidth: d.px * 1, lineCap: .round))
        for c in [lc, rc] { mSoftOval(&paint, c, 0.02 * d.R, 0.014 * d.R, hex(0x4a3020), 0.45) }
        // Working: a faint shimmer crossing the face, as if it were processing.
        if s.busy > 0.01 {
            var shimmer = gc
            shimmer.clip(to: headPath)
            for n in 0..<2 {
                let f = mFract(t * 0.6 + 0.5 * Double(n))
                let y = -1.1 + 2.2 * f + hy
                shimmer.fill(headPath, with: .linearGradient(Gradient(stops: [.init(color: .clear, location: 0), .init(color: amber.opacity(0.08 * s.busy), location: 0.5),
                                                                              .init(color: .clear, location: 1)]),
                                                         startPoint: ink.p(-0.2, y - 0.1), endPoint: ink.p(0.2, y + 0.1)))
            }
        }
        finish(&gc, d, palette: pal)
    }
}
