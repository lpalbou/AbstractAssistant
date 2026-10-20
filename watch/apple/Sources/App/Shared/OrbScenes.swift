import SwiftUI

// The orb styles that are scenes of their own rather than a planet answering the voice: Rings (a
// geodesic structure of rigid rings), Face (a friendly portrait that talks and listens) and Ocean
// (a sea at night). The avatars made from the face are in OrbAvatars.swift. All use the planet's
// units (1 = the planet's radius, y down) unless said otherwise, its palette and five brightness
// levels, the light of its work and the listening countdown.

/// Points sorted into the five brightness levels, placed in units of `R` from the centre.
struct DotCanvas {
    var paths = [Path](repeating: Path(), count: 5)
    let cx: Double, cy: Double, R: Double, px: Double
    /// A larger square under each point (`softSize` × the point's unit size), painted blurred so a dense
    /// set of points reads as a smooth surface (`paintSoft`); 0: none (every style but the portraits).
    var softSize = 0.0
    var soft = [Path](repeating: Path(), count: 5)

    mutating func dot(_ x: Double, _ y: Double, _ bright: Double, _ dither: Double, size: Double = 1) {
        guard bright > 0.03 * dither else { return }
        let b = min(4, max(0, Int(bright * 5 + dither - 0.5)))
        let s = px * size
        paths[b].addRect(CGRect(x: cx + x * R - s / 2, y: cy + y * R - s / 2, width: s, height: s))
        if softSize > 0 {
            let q = px * softSize
            soft[b].addRect(CGRect(x: cx + x * R - q / 2, y: cy + y * R - q / 2, width: q, height: q))
        }
    }

    /// A point of the scene (its units) on the screen.
    func screen(_ x: Double, _ y: Double) -> CGPoint { CGPoint(x: cx + x * R, y: cy + y * R) }
}

/// The portraits' palette: cool shadows (indigo, violet) rising to a warm light (rose, peach, a
/// pale cream), so a face reads as lit skin rather than a cyan mask.
enum PortraitPalette {
    static let warm: [Color] = [Color(hex: 0x4f46e5).opacity(0.4), Color(hex: 0x8b6cf0).opacity(0.55), Color(hex: 0xe68fbd).opacity(0.7),
                                Color(hex: 0xffc4a3).opacity(0.86), Color(hex: 0xfff2e4).opacity(0.95)]
    /// The palette for a look: an entity's own colour wins.
    static func colors(_ tint: Color?) -> [Color] { tint == nil ? warm : OrbPalette.colors(for: tint) }
}

extension OrbCanvas {
    func dotCanvas(_ box: CGSize) -> DotCanvas {
        let half = Double(min(box.width, box.height)) / 2
        return DotCanvas(cx: Double(box.width) / 2, cy: Double(box.height) / 2, R: half * 0.46, px: max(0.55, half / 95))
    }

    func pointBudget(_ box: CGSize) -> Int {
        Int(Double(OrbPoints.count(half: Double(min(box.width, box.height)) / 2)) * pointScale)
    }

    /// The work's waves under the points, the points, the running tools' satellites over them.
    /// `tint`: the scene's own colour (an entity's colour wins).
    func finish(_ gc: inout GraphicsContext, _ d: DotCanvas, tint: Color? = nil, palette: [Color]? = nil) {
        let pal = look.color == nil ? (palette ?? OrbPalette.colors(for: tint)) : OrbPalette.colors(for: look.color)
        drawWaves(&gc, cx: d.cx, cy: d.cy, R: d.R, pal: pal)
        paintDots(&gc, d.paths, pal, px: d.px)
        drawSatellites(&gc, cx: d.cx, cy: d.cy, R: d.R, px: d.px, pal: pal)
    }

    /// A portrait's finish: the work's waves, then the points as a lit surface (`paintSoft`), the
    /// scene's own lines of light over them (`over`), the running tools' satellites on top.
    func finishSoft(_ gc: inout GraphicsContext, _ d: DotCanvas, _ pal: [Color], surface: Double = 0.55, crisp: Double = 0.75, blur: Double = 2.6,
                    under: (inout GraphicsContext) -> Void = { _ in }, over: (inout GraphicsContext) -> Void = { _ in }) {
        drawWaves(&gc, cx: d.cx, cy: d.cy, R: d.R, pal: pal)
        paintSoft(&gc, d, pal, surface: surface, crisp: crisp, blur: blur, under: under)
        over(&gc)
        drawSatellites(&gc, cx: d.cx, cy: d.cy, R: d.R, px: d.px, pal: pal)
    }

    /// Dense points as a surface of light: their soft squares blurred into one smooth skin (with
    /// `under`'s own soft shapes), a bloom on the brightest, then the points themselves, fainter.
    /// Two blurred layers in all.
    func paintSoft(_ gc: inout GraphicsContext, _ d: DotCanvas, _ pal: [Color], surface: Double, crisp: Double, blur: Double = 2.6,
                   under: (inout GraphicsContext) -> Void = { _ in }) {
        gc.drawLayer { layer in
            layer.addFilter(.blur(radius: d.px * blur))
            for b in 0..<5 { layer.fill(d.soft[b], with: .color(pal[b].opacity(surface))) }
            under(&layer)
        }
        gc.drawLayer { layer in
            layer.addFilter(.blur(radius: d.px * 5))
            layer.fill(d.soft[3], with: .color(pal[3].opacity(0.22)))
            layer.fill(d.soft[4], with: .color(pal[4].opacity(0.3)))
        }
        for b in 0..<5 { gc.fill(d.paths[b], with: .color(pal[b].opacity(crisp))) }
    }

    /// A portrait's point: the work's light without its push (a step's ring brightens the face as
    /// it passes but never parts it), and the countdown.
    func placeLit(_ d: inout DotCanvas, _ x: Double, _ y: Double, _ bright: Double, _ dither: Double, phase: Double,
                  lum: Double = 0.7, edge: Double = 1.6, size: Double = 1) {
        var sx = x, sy = y
        let light = workEffect(&sx, &sy, phase: phase)
        d.dot(x, y, (bright + 0.32 * light * (0.45 + 0.55 * lum)) * countdownDim(x / edge, y / edge), dither, size: size)
    }

    /// A point placed with the work's light and the countdown (`edge`: the scene's outer radius).
    func place(_ d: inout DotCanvas, _ x: Double, _ y: Double, _ bright: Double, _ dither: Double, phase: Double,
               lum: Double = 0.7, edge: Double = 1.6, size: Double = 1) {
        var sx = x, sy = y
        let light = workEffect(&sx, &sy, phase: phase)
        let b = (bright + 0.8 * light * (0.45 + 0.55 * lum)) * countdownDim(sx / edge, sy / edge)
        d.dot(sx, sy, b, dither, size: size)
    }

    // MARK: Rings

    /// A geodesic structure: six rigid rings on the great circles that cross at the corners of an
    /// icosidodecahedron, turning slowly as one body: fine lines of light, each running through the
    /// hues as it goes round (each ring from its own place on the colour wheel), brighter in front,
    /// with a soft glow and five soft beads of light running round it. A voice sets it in motion:
    /// each ring is driven by its own band (low pitches the first, high the last), swinging about
    /// its own diameter and spinning its beads, faster and wider as its band is louder; silence lets
    /// the structure settle back. Thinking spins it up like a gyroscope; working, a wave runs across
    /// the rings in turn and the beads race.
    func drawRings(_ gc: inout GraphicsContext, _ box: CGSize) {
        let half = Double(min(box.width, box.height)) / 2
        let cx = Double(box.width) / 2, cy = Double(box.height) / 2, R = half * 0.46
        let px = max(0.55, half / 95)
        let ph = OrbPhases(engine)
        let th = ph.think, busy = ph.work
        let yaw = engine.ringTurn, tilt = 0.42 + 0.1 * sin(t * 0.21)
        let cY = cos(yaw), sY = sin(yaw), cT = cos(tilt), sT = sin(tilt)
        let per = max(36, min(120, Int(R * 1.1)))
        let lw = max(0.6, R / 62)
        let n = OrbEngine.ringCount
        // Each ring's line in three levels of light (behind … in front), its beads in front and behind.
        var lines = [[Path]](repeating: [Path](repeating: Path(), count: 3), count: n)
        var beads = [[Path]](repeating: [Path](repeating: Path(), count: 2), count: n)
        for i in 0..<n {
            let ring = RingGeometry.rings[i]
            let swing = engine.ringSwing[i]
            // The swing about the ring's own diameter `u`: small at rest, wide with its band.
            // Working: a wave runs across the rings in turn (a machine running).
            let theta = (0.04 + 0.22 * swing) * sin(engine.ringPhase[i]) + 0.3 * th * sin(t * 1.4 + Double(i))
                + 0.45 * busy * sin(t * 3 - Double(i) * .pi / 3)
            let ct = cos(theta), st = sin(theta)
            let vx = ring.v.0 * ct + ring.n.0 * st, vy = ring.v.1 * ct + ring.n.1 * st, vz = ring.v.2 * ct + ring.n.2 * st
            // Its size is its harmonic: a quiet band draws its ring in, a loud one pushes it out.
            let radius = 0.97 + engine.engagement * (0.62 * swing - 0.22)
            let spin = engine.ringSpin[i]
            var prev = CGPoint.zero, prevB = 0.0
            for k in 0...per {
                let s = 2 * Double.pi * Double(k) / Double(per)
                let cs = cos(s), sn = sin(s)
                var x = radius * (cs * ring.u.0 + sn * vx)
                var y = radius * (cs * ring.u.1 + sn * vy)
                var z = radius * (cs * ring.u.2 + sn * vz)
                // The structure turns as one body (y axis), seen tilted (x axis).
                let bx = x * cY + z * sY, bz = -x * sY + z * cY
                x = bx; let y1 = y * cT - bz * sT; z = y * sT + bz * cT; y = y1
                let light = workEffect(&x, &y, phase: s)
                let depth = smoothstep(-1.1, 1.0, z)
                let b = ((0.2 + 0.8 * depth) * (0.75 + 0.55 * swing) + 0.12 * th + 0.6 * light) * countdownDim(x / 1.1, y / 1.1)
                let p = CGPoint(x: cx + x * R, y: cy + y * R)
                if k > 0 {
                    let m = (b + prevB) / 2
                    let lv = m > 0.72 ? 2 : (m > 0.42 ? 1 : 0)
                    lines[i][lv].move(to: prev); lines[i][lv].addLine(to: p)
                    // Five beads run round each ring at its own pace (racing while it works: the
                    // two blended, never a pace that changes with the phase).
                    let sm = s - Double.pi / Double(per)
                    let calm = pow(max(0, cos(5 * (sm - spin))), 12), race = pow(max(0, cos(5 * (sm - spin - 3 * t))), 12)
                    if calm * (1 - busy) + race * busy > 0.5 {
                        beads[i][depth > 0.45 ? 0 : 1].move(to: prev); beads[i][depth > 0.45 ? 0 : 1].addLine(to: p)
                    }
                }
                prev = p; prevB = b
            }
        }
        let pal = OrbPalette.colors(for: look.color)
        let hues: [Color] = look.color.map { c in [c.opacity(0.65), c, .white.opacity(0.85), c, c.opacity(0.65)] }
            ?? [Color(hex: 0x38bdf8), Color(hex: 0x6366f1), Color(hex: 0xa855f7), Color(hex: 0xf472b6), Color(hex: 0xfb923c),
                Color(hex: 0xf472b6), Color(hex: 0xa855f7), Color(hex: 0x6366f1), Color(hex: 0x38bdf8)]
        let centre = CGPoint(x: cx, y: cy)
        func shading(_ i: Int) -> GraphicsContext.Shading {
            .conicGradient(Gradient(colors: hues), center: centre, angle: .radians(Double(i) * 2 * .pi / Double(n) + 0.3 * t * 0.1))
        }
        let beadCore = Color.white.opacity(0.7)
        drawWaves(&gc, cx: cx, cy: cy, R: R, pal: pal)
        // A soft glow under the lines, brighter where they come forward, and the beads' halos.
        gc.drawLayer { layer in
            layer.addFilter(.blur(radius: lw * 2.6))
            for i in 0..<n {
                layer.opacity = 0.75
                layer.stroke(lines[i][2], with: shading(i), lineWidth: lw * 3.6)
                layer.opacity = 0.4
                layer.stroke(lines[i][1], with: shading(i), lineWidth: lw * 3)
                layer.opacity = 1
                layer.stroke(beads[i][0], with: shading(i), style: StrokeStyle(lineWidth: lw * 7, lineCap: .round))
                layer.opacity = 0.45
                layer.stroke(beads[i][1], with: shading(i), style: StrokeStyle(lineWidth: lw * 5, lineCap: .round))
            }
        }
        for i in 0..<n {
            for (lv, a) in [(0, 0.28), (1, 0.6), (2, 0.95)] {
                gc.opacity = a
                gc.stroke(lines[i][lv], with: shading(i), lineWidth: lw * (lv == 2 ? 1.2 : 1))
            }
            gc.opacity = 0.75
            gc.stroke(beads[i][0], with: .color(beadCore), style: StrokeStyle(lineWidth: lw * 1.7, lineCap: .round))
            gc.opacity = 0.35
            gc.stroke(beads[i][1], with: shading(i), style: StrokeStyle(lineWidth: lw * 1.8, lineCap: .round))
        }
        gc.opacity = 1
        drawSatellites(&gc, cx: cx, cy: cy, R: R, px: px, pal: pal)
    }
    // MARK: Face

    /// A portrait in light: a sculpted head and shoulders, the face's real relief (brows, nose, lips,
    /// chin, the eyes set in their sockets) as a smooth skin of warm light with cool shadows, lit from
    /// the upper left as it turns; open, friendly eyes (a soft white, an iris with a dark pupil and a
    /// catchlight, the lower lids lifted by its smile), soft brows, a gentle smile, a little colour in
    /// the cheeks, short hair. It blinks, breathes and moves its head a little. Listening, it turns to
    /// offer its ear and cups a hand behind it, your voice arriving as arcs toward the hand; thinking,
    /// it looks up and aside; working, it reads (quick glances down and aside) while a fine scan line
    /// passes down its face; speaking, its lips follow its voice like speech, the jaw following.
    func drawFace(_ gc: inout GraphicsContext, _ box: CGSize) {
        var d = dotCanvas(box)
        d.softSize = 2.7
        let ph = OrbPhases(engine)
        let th = ph.think, listen = ph.listen, busy = ph.work
        let pal = PortraitPalette.colors(look.color)
        let mouth = MouthShape(engine: engine, smileBase: 1.6 + 0.2 * listen - 0.1 * th - 0.1 * busy)
        let glance = busy * (0.5 + 0.5 * sin(t * 2.3)) * (Int(t * 1.6) % 2 == 0 ? 1 : -0.6)
        let scanY = -1.0 + 1.75 * (t * 0.55).truncatingRemainder(dividingBy: 1)
        let yaw = 0.1 * sin(t * 0.29) + 0.05 * sin(t * 0.71) + 0.14 * th - 0.42 * listen
        // Its own voice: a nod with its phrasing; yours: it nods along with you.
        let level = engine.history.value(secondsAgo: 0.05)
        let pitch = 0.035 * sin(t * 0.23) - 0.08 * th + 0.06 * busy + 0.05 * mouth.open * sin(t * 6.1)
            + 0.045 * listen * level * sin(t * 4.3) + 0.03 * ph.speak * (level - 0.35)
        let roll = 0.03 * sin(t * 0.19) + 0.06 * listen - 0.04 * th
        let blink = FaceGeometry.blink(t)
        let breathe = 0.012 * sin(t * 1.25)
        let pose = HeadPose(yaw: yaw, pitch: pitch, roll: roll, pivotY: FaceGeometry.neckY, lift: breathe * 0.5)
        let scale = 1.32, shift = -0.02
        let S = d.R * scale                                                  // screen points per face unit
        let lw = max(0.6, d.px * 0.75)
        let my = FaceGeometry.mouthY
        let gazeX = (0.015 * sin(t * 0.37) + 0.03 * th) * (1 - listen) - 0.03 * listen + 0.035 * glance
        let gazeY = -0.03 * th + 0.022 * busy
        // The eyes' opening (an almond, `u` from the inner corner 0 … outward ±1 at the outer corner):
        // open and kind, the lower lid lifted a little by the smile, the outer corners soft.
        let eyeW = 0.1, eyeX = FaceGeometry.eyeX, eyeY = FaceGeometry.eyeY
        let smiling = 0.45 + 0.35 * ph.speak + 0.25 * listen
        let opening = blink * (1 + 0.06 * listen - 0.1 * th)
        func lidUp(_ u: Double) -> Double { eyeY - 0.058 * opening * pow(max(0, 1 - u * u), 0.8) + 0.005 * u - 0.003 }
        func lidLow(_ u: Double) -> Double { eyeY + (0.035 - 0.011 * smiling) * opening * max(0, 1 - u * u) + 0.005 * u + 0.002 }
        func put(_ x: Double, _ y: Double, _ b: Double, _ dither: Double, _ phase: Double, size: Double = 1) {
            let sx = x * scale, sy = y * scale + shift
            let rr = (sx * sx + sy * sy).squareRoot()
            guard rr < 1.98 else { return }
            placeLit(&d, sx, sy, b * (1 - smoothstep(1.6, 1.98, rr)), dither, phase: phase, lum: 0.35, size: size)
        }
        for p in FaceSculpt.points(count: Int(Double(pointBudget(box)) * 0.95)) {
            var x = p.x, y = p.y, z = p.z
            // Less dither between the levels: the skin reads smooth.
            let dither = 0.5 + 0.35 * (p.dither - 0.5)
            if p.part == .face {
                // The eyes are drawn on their own (their white, iris and lids): the skin stops at the lids.
                let u = (abs(x) - eyeX) / eyeW
                if abs(u) < 1, y > lidUp(u), y < lidLow(u) { continue }
                // The mouth: the jaw drops below it, the opening between the lips goes dark.
                y += mouth.jaw(x, y)
                if mouth.open > 0.06 {
                    let gap = 0.09 * mouth.open
                    let inside = exp(-pow(x / (0.16 * mouth.width), 2) - pow((y - my - gap * 0.5 + 0.02 * pow(x / 0.17, 2)) / (gap + 0.004), 2))
                    if inside > 0.45 { continue }
                }
            }
            var bright: Double
            // The hair in finer, crisper points (its strands read), the shoulders a little softer.
            d.softSize = p.part == .hair ? 1.9 : (p.part == .body ? 2.0 : 2.7)
            if p.part == .body {
                y += breathe
                bright = p.tone * 0.7 * skin(p.nx, p.ny, p.nz)
                put(x, y, bright * (1 - smoothstep(1.05, 1.55, y)), dither, p.phase, size: 0.65)
                continue
            }
            let r = pose.apply(x, y, z)
            let n = pose.apply(p.nx, p.ny + FaceGeometry.neckY, p.nz)            // a direction: turn only
            let nn = (x: n.x, y: n.y - FaceGeometry.neckY - pose.lift, z: n.z)
            guard nn.z > -0.05 else { continue }
            // The hair: a soft light on the crown and a sheen across it, a rim at its edge.
            bright = p.part == .hair ? (0.26 + 0.3 * p.tone) * (0.5 + 0.5 * max(0, -0.3 * nn.x - 0.5 * nn.y + 0.8 * nn.z))
                + 0.22 * pow(1 - max(0, nn.z), 2) + 0.12 * exp(-pow((p.y + 0.72) / 0.12, 2)) : p.tone * skin(nn.x, nn.y, nn.z)
            if busy > 0.01 { bright += busy * 0.3 * exp(-pow((y - scanY) / 0.025, 2)) }
            bright += 0.06 * engine.signal
            x = r.x; y = r.y; z = r.z
            put(x, y, bright, dither, p.phase, size: 0.55 + 0.2 * smoothstep(-0.3, 0.6, z))
        }
        // The features in lines of light, on the relief as the head turns.
        func feature(_ x: Double, _ y: Double, _ lift: Double = 0.015) -> (p: CGPoint, z: Double) {
            let q = pose.apply(x, y, (ImprintGeometry.grid.at(x, y) ?? 0.45) + lift)
            return (CGPoint(x: d.cx + q.x * S, y: d.cy + (q.y * scale + shift) * d.R), q.z)
        }
        func curve(_ n: Int, _ f: (Double) -> (Double, Double), lift: Double = 0.015) -> Path {
            var path = Path(), open = false
            for j in 0...n {
                let (x, y) = f(-1 + 2 * Double(j) / Double(n))
                let q = feature(x, y, lift)
                guard q.z > 0.12 else { open = false; continue }
                if open { path.addLine(to: q.p) } else { path.move(to: q.p); open = true }
            }
            return path
        }
        let eyeLift = 0.03 * ph.speak * ph.loud + 0.015 * listen + 0.025 * listen * level
        let smile = 0.038 + 0.01 * listen - 0.008 * th - 0.01 * mouth.pout
        let squash = cos(yaw)
        let hand = listen > 0.02 ? listeningHand(d, pose: pose, listen: listen, level: level, scale: scale, shift: shift, pal: pal, lw: lw) : nil
        // Under the skin (blurred with it): a warm glow in the cheeks, the lids' and lips' soft light,
        // the hand's body.
        let under: (inout GraphicsContext) -> Void = { g in
            for side in [-1.0, 1.0] {
                let c = feature(side * 0.3, 0.1, 0)
                guard c.z > 0.1 else { continue }
                let rx = 0.12 * S * squash, ry = 0.075 * S
                g.fill(Path(ellipseIn: CGRect(x: c.p.x - rx, y: c.p.y - ry, width: 2 * rx, height: 2 * ry)),
                       with: .radialGradient(Gradient(colors: [pal[2].opacity(0.5 + 0.2 * ph.speak), .clear]), center: c.p, startRadius: 0, endRadius: rx))
                let lid = curve(12, { u in (side * (eyeX + eyeW * u), lidUp(u)) })
                g.stroke(lid, with: .color(pal[3].opacity(0.6)), style: StrokeStyle(lineWidth: lw * 3, lineCap: .round))
            }
            let lips = curve(20, { u in (0.17 * mouth.width * u, my - smile * u * u - (0.022 * mouth.open + 0.008 * mouth.pout) * (1 - u * u)) })
            g.stroke(lips, with: .color(pal[2].opacity(0.7)), style: StrokeStyle(lineWidth: lw * 3.2, lineCap: .round))
            // The shoulders' line, soft, fading out at the sides.
            var shoulders = Path()
            for j in 0...24 {
                let x = -1.5 + 3 * Double(j) / 24
                let y = 0.9 + 0.32 * pow(max(0, abs(x) - 0.22) / 1.33, 1.5) + breathe
                let q = d.screen(x * scale, y * scale + shift)
                j == 0 ? shoulders.move(to: q) : shoulders.addLine(to: q)
            }
            let ends = Gradient(stops: [.init(color: .clear, location: 0), .init(color: pal[3].opacity(0.55), location: 0.35),
                                        .init(color: pal[3].opacity(0.55), location: 0.65), .init(color: .clear, location: 1)])
            g.stroke(shoulders, with: .linearGradient(ends, startPoint: d.screen(-1.5 * scale, 0), endPoint: d.screen(1.5 * scale, 0)),
                     style: StrokeStyle(lineWidth: lw * 2.5, lineCap: .round))
            if let hand {
                for (path, shading, width) in hand.soft {
                    if width > 0 { g.stroke(path, with: shading, style: StrokeStyle(lineWidth: width, lineCap: .round)) } else { g.fill(path, with: shading) }
                }
            }
        }
        let over: (inout GraphicsContext) -> Void = { g in
            for side in [-1.0, 1.0] {
                // `u` runs from the nose outward on either side.
                func at(_ u: Double) -> Double { side * (eyeX + eyeW * u) }
                if blink > 0.3 {
                    var almond = Path(), seen = true
                    for j in 0...16 {
                        let u = -1 + 2 * Double(j) / 16, q = feature(at(u), lidUp(u))
                        seen = seen && q.z > 0.12
                        if j == 0 { almond.move(to: q.p) } else { almond.addLine(to: q.p) }
                    }
                    for j in (0...16).reversed() { almond.addLine(to: feature(at(-1 + 2 * Double(j) / 16), lidLow(-1 + 2 * Double(j) / 16)).p) }
                    almond.closeSubpath()
                    if seen {
                        var e = g
                        e.clip(to: almond)
                        let ri = 0.042, rp = 0.013 + 0.003 * listen - 0.002 * ph.speak * ph.loud
                        let ic = feature(side * eyeX + gazeX, eyeY + 0.004 + gazeY * blink, 0.02).p
                        let irisRect = CGRect(x: ic.x - ri * S * squash, y: ic.y - ri * S, width: 2 * ri * S * squash, height: 2 * ri * S)
                        let pupilRect = CGRect(x: ic.x - rp * S * squash, y: ic.y - rp * S, width: 2 * rp * S * squash, height: 2 * rp * S)
                        let mid = feature(at(0.05), eyeY, 0.02).p
                        var white = Path(almond.boundingRect.insetBy(dx: -2, dy: -2))
                        white.addEllipse(in: irisRect)
                        e.fill(white, with: .radialGradient(Gradient(colors: [pal[4].opacity(0.34), pal[3].opacity(0.1)]), center: mid,
                                                            startRadius: 0, endRadius: eyeW * S), style: FillStyle(eoFill: true))
                        var iris = Path(ellipseIn: irisRect)
                        iris.addEllipse(in: pupilRect)
                        let irisColors: [Color] = look.color.map { c in [Color.white.opacity(0.8), c.opacity(0.85), c] }
                            ?? [Color(hex: 0xffd59a).opacity(0.95), Color(hex: 0x9ad3ec).opacity(0.8), Color(hex: 0x6a72f0).opacity(0.95)]
                        e.fill(iris, with: .radialGradient(Gradient(colors: irisColors), center: ic, startRadius: rp * S, endRadius: ri * S),
                               style: FillStyle(eoFill: true))
                        let c1 = 0.011 * S, c2 = 0.0055 * S
                        e.fill(Path(ellipseIn: CGRect(x: ic.x - 0.013 * S - c1, y: ic.y - 0.013 * S - c1, width: 2 * c1, height: 2 * c1)), with: .color(.white.opacity(0.95)))
                        e.fill(Path(ellipseIn: CGRect(x: ic.x + 0.013 * S - c2, y: ic.y + 0.011 * S - c2, width: 2 * c2, height: 2 * c2)), with: .color(.white.opacity(0.55)))
                    }
                }
                // The lids: the upper one a clear soft line, the lower one faint.
                g.stroke(curve(16, { u in (at(u), lidUp(u)) }), with: .color(pal[3].opacity(0.75)),
                         style: StrokeStyle(lineWidth: lw * 1.15, lineCap: .round))
                if blink > 0.3 {
                    g.stroke(curve(12, { u in (at(u * 0.92), lidLow(u * 0.92)) }), with: .color(pal[3].opacity(0.4)),
                             style: StrokeStyle(lineWidth: lw * 0.8, lineCap: .round))
                }
                // The brow: a soft arch, its inner end a little higher (kind), lifted as it listens and
                // on a stressed syllable; one brow a little higher while it thinks.
                let browUp = 0.012 + eyeLift + 0.012 * th * (side > 0 ? 1 : 0)
                let brow = curve(12, { u in
                    let v = (u + 1) / 2                                     // 0 inner … 1 outer
                    return (side * (eyeX - 0.075 + 0.2 * v), eyeY - 0.1 - 0.026 * sin(.pi * min(1, v * 1.1)) - browUp + 0.014 * v)
                }, lift: 0.02)
                g.stroke(brow, with: .color(pal[3].opacity(0.32)), style: StrokeStyle(lineWidth: lw * 3, lineCap: .round))
                g.stroke(brow, with: .color(pal[4].opacity(0.42)), style: StrokeStyle(lineWidth: lw * 1.1, lineCap: .round))
            }
            // The lips: a gentle upturned line where they meet, small lifts at the corners; as it
            // talks they part (the lower lip following the jaw), rounder on dark vowels, wider on
            // bright ones, the upper teeth showing on open syllables.
            let w = 0.17 * mouth.width
            func upperLip(_ u: Double) -> (Double, Double) { (w * u, my - smile * u * u - (0.022 * mouth.open + 0.008 * mouth.pout) * (1 - u * u)) }
            func lowerLip(_ u: Double) -> (Double, Double) {
                (w * u * (1 - 0.06 * mouth.open), my - smile * u * u + (0.13 * mouth.open + 0.01 * mouth.pout) * pow(max(0, 1 - u * u), 0.8))
            }
            g.stroke(curve(24, upperLip), with: .color(pal[4].opacity(0.8)), style: StrokeStyle(lineWidth: lw * 1.3, lineCap: .round))
            for side in [-1.0, 1.0] {
                g.stroke(curve(4, { u in let v = (u + 1) / 2; return (side * (w + 0.016 * v), my - smile - 0.014 * v * v) }),
                         with: .color(pal[3].opacity(0.45)), style: StrokeStyle(lineWidth: lw * 0.9, lineCap: .round))
            }
            if mouth.open > 0.04 {
                let k = min(1, (mouth.open - 0.04) * 8)
                g.stroke(curve(24, lowerLip), with: .color(pal[3].opacity(0.7 * k)), style: StrokeStyle(lineWidth: lw * 1.2, lineCap: .round))
            }
            if mouth.open > 0.22 {
                var teeth = Path()
                for j in 0...12 { let (x, y) = upperLip(-0.6 + 1.2 * Double(j) / 12); let q = feature(x, y + 0.004).p; j == 0 ? teeth.move(to: q) : teeth.addLine(to: q) }
                for j in (0...12).reversed() { let (x, y) = upperLip(-0.6 + 1.2 * Double(j) / 12); teeth.addLine(to: feature(x * 0.95, y + 0.02).p) }
                teeth.closeSubpath()
                g.fill(teeth, with: .color(pal[4].opacity(0.32 * min(1, (mouth.open - 0.22) * 4))))
            }
            if let hand { for (path, shading, width) in hand.lines { g.stroke(path, with: shading, style: StrokeStyle(lineWidth: width, lineCap: .round, lineJoin: .round)) } }
        }
        finishSoft(&gc, d, pal, surface: 0.85, crisp: 0.4, under: under, over: over)
    }

    /// Skin lit from the upper left in front: soft, a gentle sheen.
    private func skin(_ nx: Double, _ ny: Double, _ nz: Double) -> Double {
        // Soft frontal light (a portrait's key light, a little from above and left): no hard
        // shadows under the brows.
        let l = (x: -0.3, y: -0.32, z: 0.9)
        let diffuse = max(0, nx * l.x + ny * l.y + nz * l.z)
        let rim = pow(1 - max(0, nz), 3) * 0.22
        return 0.1 + 0.74 * pow(diffuse, 1.4) + 0.14 * pow(diffuse, 8) + rim
    }

    /// The hand cupped behind the ear it offers, its forearm from below, and your voice arriving as
    /// arcs toward the hand (brighter as you speak louder). It rises and turns into place, sways a
    /// little, and its fingers cup a little more as your voice is louder. Soft shapes (blurred with
    /// the skin) and their lines of light, in screen points (a width of 0: a fill).
    private func listeningHand(_ d: DotCanvas, pose: HeadPose, listen: Double, level: Double, scale: Double, shift: Double,
                               pal: [Color], lw: Double) -> (soft: [(Path, GraphicsContext.Shading, Double)], lines: [(Path, GraphicsContext.Shading, Double)]) {
        let ear = pose.apply(FaceGeometry.halfWidth * 0.98, -0.1, 0)
        let ease = listen * listen * (3 - 2 * listen)
        // The wrist rises from below the frame to just under and behind the ear, turning into place.
        let wx = 1.25 + (ear.x + 0.2 - 1.25) * ease, wy = 2.1 + (ear.y + 0.27 - 2.1) * ease
        let size = 1.25, S = d.R * scale
        let tilt = 0.45 * (1 - ease) + 0.05 * sin(t * 1.1) + 0.06 * level, cT = cos(tilt), sT = sin(tilt)
        let curl = 0.4 + 0.6 * min(1, 1.4 * level)
        func at(_ x: Double, _ y: Double) -> CGPoint {
            let xr = x * cT - y * sT, yr = x * sT + y * cT
            return d.screen((wx + size * xr) * scale, (wy + size * yr) * scale + shift)
        }
        var soft: [(Path, GraphicsContext.Shading, Double)] = [], lines: [(Path, GraphicsContext.Shading, Double)] = []
        let body = GraphicsContext.Shading.color(pal[3].opacity(0.5 * ease)), edge = GraphicsContext.Shading.color(pal[4].opacity(0.7 * ease))
        /// A finger along a quadratic curve base → tip, `w` wide, cupping forward with `curl`: its body
        /// soft, its outline (both edges round the tip) a line of light.
        func finger(_ b: (Double, Double), _ c: (Double, Double), _ tip: (Double, Double), _ w: Double) {
            let tx = tip.0 - 0.03 * curl, ty = tip.1 + 0.012 * curl
            var mid: [(Double, Double)] = [], left: [CGPoint] = [], right: [CGPoint] = []
            let n = 10
            for i in 0...n {
                let s = Double(i) / Double(n), m = 1 - s
                let x = m * m * b.0 + 2 * m * s * c.0 + s * s * tx, y = m * m * b.1 + 2 * m * s * c.1 + s * s * ty
                let dx = 2 * m * (c.0 - b.0) + 2 * s * (tx - c.0), dy = 2 * m * (c.1 - b.1) + 2 * s * (ty - c.1)
                let l = max(1e-6, (dx * dx + dy * dy).squareRoot())
                let ww = w * (1 - 0.15 * s)
                mid.append((x, y)); left.append(at(x - dy / l * ww, y + dx / l * ww)); right.append(at(x + dy / l * ww, y - dx / l * ww))
            }
            var centre = Path()
            for (i, p) in mid.enumerated() { i == 0 ? centre.move(to: at(p.0, p.1)) : centre.addLine(to: at(p.0, p.1)) }
            soft.append((centre, body, 2 * w * size * S))
            var outline = Path()
            outline.move(to: left[0]); for p in left.dropFirst() { outline.addLine(to: p) }
            let tipP = at(mid[n].0, mid[n].1)
            outline.addQuadCurve(to: right[n], control: CGPoint(x: 2 * tipP.x - (left[n].x + right[n].x) / 2 + (tipP.x - at(mid[n - 1].0, mid[n - 1].1).x) * 0.6,
                                                                 y: 2 * tipP.y - (left[n].y + right[n].y) / 2 + (tipP.y - at(mid[n - 1].0, mid[n - 1].1).y) * 0.6))
            for p in right.reversed().dropFirst() { outline.addLine(to: p) }
            lines.append((outline, edge, lw * 0.85))
        }
        finger((-0.035, -0.19), (-0.04, -0.36), (-0.12, -0.42), 0.019)
        finger((-0.005, -0.2), (-0.005, -0.39), (-0.075, -0.47), 0.02)
        finger((0.025, -0.19), (0.03, -0.37), (-0.03, -0.45), 0.019)
        finger((0.052, -0.17), (0.062, -0.31), (0.012, -0.38), 0.017)
        finger((-0.045, -0.06), (-0.11, -0.075), (-0.14, -0.165), 0.02)          // the thumb
        // The palm and the forearm: one soft shape fading down the arm, its two edges in light.
        let fadeDown = Gradient(colors: [pal[3].opacity(0.45 * ease), pal[2].opacity(0.2 * ease), .clear])
        let top = at(0, -0.1), bottom = at(0.4, 1.0)
        var arm = Path()
        arm.move(to: at(-0.055, -0.2)); arm.addLine(to: at(0.068, -0.18))
        arm.addQuadCurve(to: at(0.5, 1.3), control: at(0.1, 0.4))
        arm.addLine(to: at(0.36, 1.32))
        arm.addQuadCurve(to: at(-0.055, -0.04), control: at(-0.02, 0.4))
        arm.closeSubpath()
        soft.append((arm, .linearGradient(fadeDown, startPoint: top, endPoint: bottom), 0))
        let edgeDown = Gradient(colors: [pal[4].opacity(0.6 * ease), pal[3].opacity(0.25 * ease), .clear])
        var edges = Path()
        edges.move(to: at(0.068, -0.18)); edges.addQuadCurve(to: at(0.5, 1.3), control: at(0.1, 0.4))
        edges.move(to: at(-0.05, -0.05)); edges.addQuadCurve(to: at(0.36, 1.32), control: at(-0.02, 0.4))
        lines.append((edges, .linearGradient(edgeDown, startPoint: top, endPoint: bottom), lw * 0.9))
        guard ease > 0.3 else { return (soft, lines) }
        // Your voice: arcs travelling in toward the cupped hand, brighter as you speak louder.
        let ec = d.screen((ear.x + 0.08) * scale, ear.y * scale + shift)
        let open = 0.6
        for j in 0..<4 {
            let age = (t * 0.8 + Double(j) / 4).truncatingRemainder(dividingBy: 1)   // 0 far … 1 at the ear
            let r = (0.3 + 0.8 * (1 - age)) * d.R
            let v = engine.history.value(secondsAgo: (1 - age) * 1.1)
            let bright = ease * (0.15 + 0.85 * v) * smoothstep(0, 0.2, age) * (1 - smoothstep(0.85, 1, age))
            var arc = Path()
            arc.addArc(center: ec, radius: r, startAngle: .radians(-open), endAngle: .radians(open), clockwise: false)
            soft.append((arc, .color(pal[3].opacity(0.6 * bright)), lw * 4))
            lines.append((arc, .color(pal[4].opacity(min(1, bright))), lw * 1.2))
        }
        return (soft, lines)
    }
    // MARK: Ocean

    /// A sea at night filling the frame, in lines of light (Wave's ribbons laid on the water): each
    /// line a row of the water at one distance, closing up toward the horizon, rising and falling
    /// with the waves, its crests glowing, the moon's path a band of warm light across them; a dusk
    /// glow on the horizon, the moon with its halo, a few stars. The waves are Gerstner waves (sharp
    /// crests, long waves faster than short ones); the light is the moon reflected off each wave's
    /// actual tilt, the sky's glow reflected more at grazing angles. At rest a low swell; a voice
    /// raises it and lights it, low pitches the long waves, high pitches the short ones, the last
    /// second of the voice travelling across the water: toward you while it speaks, away while you
    /// speak. While it thinks the sea calms and a gentle rain falls, each drop ringing the water;
    /// working, a lighthouse on the horizon sweeps its beam across the sea.
    func drawOcean(_ gc: inout GraphicsContext, _ box: CGSize) {
        let W = Double(box.width), H = Double(box.height)
        let cx = W / 2, cy = H / 2
        // The scene's units: the frame's half height (y) and half width (x).
        func screen(_ sx: Double, _ sy: Double) -> CGPoint { CGPoint(x: cx + sx * W / 2, y: cy + sy * H / 2) }
        let ax = W / H
        let ph = OrbPhases(engine)
        let e = engine.engagement, th = ph.think, talk = engine.talking, hist = engine.history, busy = ph.work
        // Working: a lighthouse on the horizon at the left, its beam sweeping the water (searching).
        let beamA = 0.45 + 0.25 * sin(t * 0.9), lightX = -0.82
        let hz = OceanGeometry.horizon, F = OceanGeometry.focal
        let toward = 2 * talk - 1                                       // +1: the waves come toward you
        let calm = 1 - 0.6 * th
        let lowB = (engine.bands[0] + engine.bands[1]) / 2, midB = engine.bands[3], highB = engine.bands[6]
        let moon = OceanGeometry.moon
        let moonDir = OceanGeometry.moonDirection
        let moonGlow = 0.9 + 0.08 * sin(t * 0.5) + 0.25 * engine.signal
        let waves = OceanGeometry.waves
        // The rain while it thinks: drops at their places on the water, in turn.
        var drops: [(x: Double, d: Double, age: Double, fade: Double)] = []
        if th > 0.01 {
            let period = 1.8
            for i in 0..<6 {
                let shifted = t + Double(i) * period / 6
                let n = Int(shifted / period), age = shifted - Double(n) * period
                let seed = n * 7 + i * 13
                drops.append((x: (OrbPoints.hash(seed, 31) - 0.5) * 3, d: 2.4 + 4 * OrbPoints.hash(seed, 37),
                              age: age, fade: th * pow(1 - age / period, 2)))
            }
        }
        let rows = max(8, min(34, Int(H / 9))), samples = max(20, min(64, Int(W / 6)))
        let lw = max(0.6, H / 300)
        // The water's lines: three groups by distance (finer far away), five levels of light each.
        var water = [[Path]](repeating: [Path](repeating: Path(), count: 5), count: 3)
        func rowY(_ f: Double) -> Double { hz + 0.012 + (1.04 - hz - 0.012) * pow(f, 1.7) }
        for j in 0..<rows {
            let f = Double(j) / Double(rows - 1)                         // 0 at the horizon … 1 near you
            let y0 = rowY(f), D = F / (y0 - hz)
            let group = f < 0.3 ? 0 : (f < 0.65 ? 1 : 2)
            // The far rows lie close together: each fainter, so they don't pile up into a band.
            let rowWeight = min(1, max(0.4, (y0 - rowY(max(0, f - 1 / Double(rows - 1)))) / 0.05))
            // Where the voice now is on this row (the last 1.2 s along the way).
            let ago = talk * min(1.2, max(0, (12 - D) / 9)) + (1 - talk) * min(1.2, max(0, (D - 1) / 9))
            let v = e * hist.value(secondsAgo: ago)
            var prev = CGPoint.zero, prevB = 0.0
            for i in 0...samples {
                let X = (-1.06 + 2.12 * Double(i) / Double(samples)) * D / F
                var dx = 0.0, dd = 0.0, h = 0.0, sxSlope = 0.0, sdSlope = 0.0, squeeze = 0.0, A = 0.0
                for w in waves {
                    let gain = w.low * (0.6 + 1.6 * lowB) + w.mid * (0.6 + 1.6 * midB) + w.high * (0.6 + 1.6 * highB)
                    let a = w.rest * calm * (1 + 5.5 * v * gain)
                    let px = w.dirX, pd = -w.dirD * toward
                    let phase = w.k * (px * X + pd * D) - w.omega * t + w.phase
                    let c = cos(phase), s = sin(phase)
                    let q = min(0.9, w.steep * 0.7)                      // the crests sharpen, never loop
                    dx -= q * a * px * s; dd -= q * a * pd * s
                    h += a * c; A += a
                    sxSlope -= a * w.k * px * s; sdSlope -= a * w.k * pd * s
                    squeeze += q * a * w.k * c
                }
                for drop in drops where drop.fade > 0.002 {
                    let ddx = X - drop.x, ddd = (D - drop.d) * 0.8
                    let dist = (ddx * ddx + ddd * ddd).squareRoot() - 0.6 * drop.age
                    let k = exp(-pow(dist / 0.16, 2)) * drop.fade
                    h += 0.04 * k * cos(dist * 22)
                    sdSlope += 0.5 * k * sin(dist * 22)
                }
                let Xw = X + dx, Dw = max(0.5, D + dd)
                let sx = Xw * F / Dw, sy = hz + F * (1 - h) / Dw
                // Light: the view ray reflected off the wave's normal (the moon's path, the sky's glow).
                let vl = (Xw * Xw + (h - 1) * (h - 1) + Dw * Dw).squareRoot()
                let vx = Xw / vl, vy = (h - 1) / vl, vz = Dw / vl
                let nl = (sxSlope * sxSlope + 1 + sdSlope * sdSlope).squareRoot()
                let nx = -sxSlope / nl, ny = 1 / nl, nz = -sdSlope / nl
                let vn = vx * nx + vy * ny + vz * nz
                let rx = vx - 2 * vn * nx, ry = vy - 2 * vn * ny, rz = vz - 2 * vn * nz
                let fresnel = 0.02 + 0.98 * pow(1 - min(1, max(0, -vn)), 5)
                let skyGlow = 0.12 + 0.55 * exp(-max(0, ry) * 7)
                let glitter = 0.55 + 0.45 * sin(37 * X + 11 * D - 2.3 * t)
                let spec = pow(max(0, rx * moonDir.x + ry * moonDir.y + rz * moonDir.z), 50) * 1.05 * moonGlow * glitter
                // The crests glow; the voice lights the water it raises.
                let crest = A > 1e-5 ? smoothstep(0.1, 0.95, h / A) : 0
                var b = 0.25 + 0.4 * fresnel * skyGlow + 0.28 * crest + spec + 0.45 * v * (0.4 + 0.6 * crest)
                if squeeze > 0.55 { b += 0.6 * (squeeze - 0.55) * (0.3 + v) }          // foam on steep crests
                // The moon's path: a column of glittering light under it, wider toward you.
                b += 0.42 * moonGlow * exp(-pow((sx - moon.x) / (0.04 + 0.1 * f), 2)) * (0.35 + 0.65 * glitter) * (0.6 + 0.4 * crest)
                for drop in drops where drop.age < 0.15 {
                    let ddx = X - drop.x, ddd = D - drop.d
                    b += 0.8 * exp(-(ddx * ddx + ddd * ddd) / 0.01) * drop.fade             // the splash
                }
                if busy > 0.01 {
                    let a = atan2(sy - hz, sx - lightX)
                    let inBeam = exp(-pow((a - beamA) / 0.12, 2)) * (1 - smoothstep(0.9, 3.0, hypot(sx - lightX, sy - hz)))
                    b += busy * 0.65 * inBeam
                }
                // The frame's edges dissolve into the night; the countdown dims the edge clockwise.
                let edge = (1 - smoothstep(0.9, 1.04, abs(sx))) * (1 - smoothstep(0.9, 1.02, sy))
                b *= rowWeight * edge * countdownDim(sx * ax / 0.75, sy / 0.75)
                let p = screen(sx, sy)
                if i > 0 {
                    let m = (b + prevB) / 2
                    if m > 0.04 {
                        let lv = min(4, max(0, Int(m * 5)))
                        water[group][lv].move(to: prev); water[group][lv].addLine(to: p)
                    }
                }
                prev = p; prevB = b
            }
        }
        let tint = look.color
        let hues: [Color] = tint.map { c in [c.opacity(0.7), c, c.opacity(0.85), c] }
            ?? [Color(hex: 0x38bdf8), Color(hex: 0x6366f1), Color(hex: 0xa855f7), Color(hex: 0xf472b6), Color(hex: 0xfb923c)]
        let hue = GraphicsContext.Shading.linearGradient(Gradient(colors: hues), startPoint: CGPoint(x: 0, y: cy), endPoint: CGPoint(x: W, y: cy))
        let moonLight = tint == nil ? Color(hex: 0xfff0d4) : Color(white: 0.95)
        let horizonY = screen(0, hz).y
        // The sky: dark above, a soft dusk glow down to the horizon.
        let dusk = tint ?? Color(hex: 0xa855f7)
        gc.fill(Path(CGRect(x: 0, y: 0, width: W, height: horizonY)),
                with: .linearGradient(Gradient(stops: [.init(color: .clear, location: 0), .init(color: dusk.opacity(0.06), location: 0.45),
                                                       .init(color: dusk.opacity(0.14), location: 0.8), .init(color: (tint ?? Color(hex: 0xf472b6)).opacity(0.2), location: 1)]),
                                      startPoint: CGPoint(x: 0, y: 0), endPoint: CGPoint(x: 0, y: horizonY)))
        // Stars, twinkling (three groups by their light now), fading while it rains.
        var stars = [Path](repeating: Path(), count: 3)
        let starCount = max(8, Int(W * H / 5000))
        for k in 0..<starCount {
            let sx = 2 * OrbPoints.hash(k, 51) - 1, sy = -1 + (hz + 1 - 0.08) * OrbPoints.hash(k, 52)
            if (sx * ax - moon.x * ax) * (sx * ax - moon.x * ax) + (sy - moon.y) * (sy - moon.y) < 0.06 { continue }
            let tw = 0.5 + 0.5 * sin(t * 1.3 + 6.3 * OrbPoints.hash(k, 53))
            let lv = min(2, Int(tw * 3)), r = lw * (0.7 + 0.8 * OrbPoints.hash(k, 54))
            let p = screen(sx, sy)
            stars[lv].addEllipse(in: CGRect(x: p.x - r, y: p.y - r, width: 2 * r, height: 2 * r))
        }
        for (lv, a) in [(0, 0.25), (1, 0.5), (2, 0.85)] { gc.fill(stars[lv], with: .color(moonLight.opacity(a * (1 - 0.6 * th)))) }
        // The moon: a soft disc in its halo, and its light on the water under it.
        let mc = screen(moon.x, moon.y), mr = moon.r * H / 2
        let halo = mr * 4.2
        gc.fill(Path(ellipseIn: CGRect(x: mc.x - halo, y: mc.y - halo, width: 2 * halo, height: 2 * halo)),
                with: .radialGradient(Gradient(colors: [moonLight.opacity(0.28 * moonGlow), dusk.opacity(0.08), .clear]), center: mc, startRadius: mr * 0.8, endRadius: halo))
        gc.fill(Path(ellipseIn: CGRect(x: mc.x - mr, y: mc.y - mr, width: 2 * mr, height: 2 * mr)),
                with: .radialGradient(Gradient(colors: [.white.opacity(0.95), moonLight.opacity(0.9), moonLight.opacity(0.75)]),
                                      center: CGPoint(x: mc.x - mr * 0.3, y: mc.y - mr * 0.3), startRadius: 0, endRadius: mr * 1.2))
        // Its path on the water: a soft column of light, a circle's gradient stretched down.
        var glade = gc
        let gr = mr * 2.4, stretch = (H - horizonY) / gr * 0.6
        glade.translateBy(x: mc.x, y: horizonY)
        glade.scaleBy(x: 1, y: stretch)
        glade.fill(Path(CGRect(x: -gr, y: 0, width: 2 * gr, height: 2 * gr)),
                   with: .radialGradient(Gradient(colors: [moonLight.opacity(0.12 * moonGlow), moonLight.opacity(0.04), .clear]),
                                         center: CGPoint(x: 0, y: gr * 0.5), startRadius: 0, endRadius: gr))
        // The horizon: a fine line of light.
        var horizon = Path(); horizon.move(to: CGPoint(x: 0, y: horizonY)); horizon.addLine(to: CGPoint(x: W, y: horizonY))
        gc.stroke(horizon, with: .linearGradient(Gradient(colors: [.clear, moonLight.opacity(0.3), moonLight.opacity(0.45), moonLight.opacity(0.3), .clear]),
                                                 startPoint: CGPoint(x: 0, y: horizonY), endPoint: CGPoint(x: W, y: horizonY)), lineWidth: lw * 0.8)
        // The water: a glow under its bright lines, the lines in the voice's hues, the brightest in
        // the moon's light.
        let widths = [0.55, 0.85, 1.2]
        gc.drawLayer { layer in
            layer.addFilter(.blur(radius: lw * 2.2))
            for g in 0..<3 {
                layer.stroke(water[g][3], with: .color(moonLight.opacity(0.35)), lineWidth: lw * widths[g] * 2.5)
                layer.stroke(water[g][4], with: .color(moonLight.opacity(0.55)), lineWidth: lw * widths[g] * 3)
            }
        }
        for g in 0..<3 {
            for (lv, a) in [(0, 0.3), (1, 0.5), (2, 0.75)] {
                gc.opacity = a
                gc.stroke(water[g][lv], with: hue, style: StrokeStyle(lineWidth: lw * widths[g], lineCap: .round))
            }
            gc.opacity = 1
            gc.stroke(water[g][3], with: .color(moonLight.opacity(0.8)), style: StrokeStyle(lineWidth: lw * widths[g], lineCap: .round))
            gc.stroke(water[g][4], with: .color(.white.opacity(0.95)), style: StrokeStyle(lineWidth: lw * widths[g] * 1.1, lineCap: .round))
        }
        // The rain while it thinks: fine slow streaks, and the rings each drop leaves.
        if th > 0.01 {
            var rain = Path()
            for k in 0..<max(10, Int(W / 14)) {
                let fall = (t * 0.9 + OrbPoints.hash(k, 55)).truncatingRemainder(dividingBy: 1)
                let sx = 2.1 * OrbPoints.hash(k, 56) - 1.05 + 0.05 * fall, sy = -1 + (hz + 1.25) * fall
                rain.move(to: screen(sx, sy)); rain.addLine(to: screen(sx - 0.006, sy - 0.07))
            }
            gc.stroke(rain, with: .color(moonLight.opacity(0.35 * th)), style: StrokeStyle(lineWidth: lw * 0.7, lineCap: .round))
            for drop in drops where drop.fade > 0.01 {
                let rho = 0.08 + 0.6 * drop.age
                let c = screen(drop.x * F / drop.d, hz + F / drop.d)
                let rx = rho * F / drop.d * W / 2, ry = rho * F / (drop.d * drop.d) * H / 2
                for (scale, a) in [(1.0, 0.32), (0.6, 0.18)] {
                    gc.stroke(Path(ellipseIn: CGRect(x: c.x - rx * scale, y: c.y - ry * scale, width: 2 * rx * scale, height: 2 * ry * scale)),
                              with: .color(moonLight.opacity(a * drop.fade)), lineWidth: lw * 0.6)
                }
            }
        }
        // The lighthouse while it works: its lamp on the horizon and its beam.
        if busy > 0.01 {
            let lamp = screen(lightX, hz - 0.02)
            var beam = Path()
            beam.move(to: lamp)
            for k in 0...8 {
                let a = beamA - 0.12 + 0.24 * Double(k) / 8
                beam.addLine(to: screen(lightX + 3 * cos(a), hz - 0.02 + 3 * sin(a)))
            }
            beam.closeSubpath()
            gc.fill(beam, with: .radialGradient(Gradient(colors: [moonLight.opacity(0.22 * busy), moonLight.opacity(0.05 * busy), .clear]),
                                                center: lamp, startRadius: 0, endRadius: W * 0.9))
            let lr = lw * 5
            gc.fill(Path(ellipseIn: CGRect(x: lamp.x - lr, y: lamp.y - lr, width: 2 * lr, height: 2 * lr)),
                    with: .radialGradient(Gradient(colors: [.white.opacity(busy), moonLight.opacity(0.5 * busy), .clear]), center: lamp, startRadius: 0, endRadius: lr))
        }
    }
}
// MARK: - Shared face pieces

/// How the head is turned: yaw (left/right), pitch (nod), roll (tilt), about the neck.
struct HeadPose {
    let pivotY: Double, lift: Double
    private let cY: Double, sY: Double, cP: Double, sP: Double, cR: Double, sR: Double
    init(yaw: Double, pitch: Double, roll: Double, pivotY: Double, lift: Double) {
        self.pivotY = pivotY; self.lift = lift
        cY = cos(yaw); sY = sin(yaw); cP = cos(pitch); sP = sin(pitch); cR = cos(roll); sR = sin(roll)
    }
    func apply(_ x: Double, _ y: Double, _ z: Double) -> (x: Double, y: Double, z: Double) {
        var ly = y - pivotY
        let lx0 = x * cY + z * sY
        var lz = -x * sY + z * cY
        let y2 = ly * cP - lz * sP; lz = ly * sP + lz * cP; ly = y2
        let rx = lx0 * cR - ly * sR, ry = lx0 * sR + ly * cR
        return (rx, ry + pivotY + lift, lz)
    }
}

/// The mouth's shape now, from the voice: how open (loud sounds, the jaw following), how round
/// (dark vowels: more low bands than high) or wide (bright vowels), the smile; and where each lip
/// and teeth point goes.
struct MouthShape {
    let open: Double, width: Double, pout: Double, smile: Double

    init(engine: OrbEngine, smileBase: Double) {
        let b = engine.bands
        let low = (b[0] + b[1] + b[2]) / 3, high = (b[5] + b[6] + b[7]) / 3
        let speaking = engine.engagement * engine.talking
        let o = min(1, speaking * (1.6 * engine.loud + 0.3 * low))
        let round = min(1, max(0, (low - high) * 1.6)) * min(1, o * 2)
        let spread = min(1, max(0, (high - low) * 1.6)) * min(1, o * 2)
        open = o
        width = 1 - 0.3 * round + 0.14 * spread
        pout = round
        smile = smileBase - 0.25 * round
    }

    /// The jaw's drop for a skin point below the mouth.
    func jaw(_ x: Double, _ y: Double) -> Double {
        let my = FaceGeometry.mouthY
        return y > my ? 0.17 * open * smoothstep(my, my + 0.2, y) * max(0, 1 - abs(x) / 0.62) : 0
    }

    func place(_ p: FaceGeometry.P) -> (x: Double, y: Double, lum: Double)? {
        let my = FaceGeometry.mouthY, u = p.u, v = p.v
        let along = max(0, 1 - u * u)
        let corner = -0.028 * smile * u * u
        let w = 0.19 * width
        let thick = 1 + 0.35 * pout
        let upperInner = my - 0.018 * open * along
        let lowerInner = my + 0.14 * open * pow(along, 0.8)
        switch p.kind {
        case .lipUpper:
            let outer = upperInner - (0.022 * along.squareRoot() - 0.007 * exp(-pow(u / 0.12, 2))) * thick - 0.003
            return (w * u, outer + (upperInner - outer) * v + corner, v < 0.2 || v > 0.85 ? 0.8 : 0.3)
        case .lipLower:
            let outer = lowerInner + (0.03 * along.squareRoot() + 0.003) * thick
            return (w * u * (1 - 0.05 * open), lowerInner + (outer - lowerInner) * v + corner, v < 0.15 || v > 0.8 ? 0.75 : 0.3)
        case .teeth:
            guard open > 0.12, abs(u) < 0.7 else { return nil }
            let y = upperInner + 0.006 + 0.022 * v
            return (w * 0.92 * u, y + corner * 0.8, 0.32 * min(1, (open - 0.12) * 5))
        default:
            return nil
        }
    }
}

// MARK: - The face's points

/// The portrait's fixed points (seeded: the same face every launch), in the planet's units, y down:
/// the head (skin, hair, ears), its features (lids, irises with a catchlight, brows, nose, lips,
/// teeth, cheeks), the neck and the shoulders; and the listening hand.
enum FaceGeometry {
    enum Kind {
        case skin, hair, ear, lidUpper, lidLower, iris, glint, brow, nose, lipUpper, lipLower, teeth, cheek, neck, body
        var isHead: Bool { self != .neck && self != .body }
        var isFeature: Bool { ![.skin, .hair, .ear, .neck, .body].contains(self) }
    }
    struct P {
        let kind: Kind; let x: Double; let y: Double; let z: Double
        /// Place along its curve (-1…1) and across it (0 outer edge … 1 inner edge), which side.
        let u: Double; let v: Double; let side: Double
        let lum: Double; let dither: Double; let phase: Double
    }
    struct HandPoint { let x: Double; let y: Double; let lum: Double; let dither: Double; let phase: Double }

    static let headY = -0.2, halfWidth = 0.6, halfHeight = 0.78, depth = 0.55
    static let eyeY = -0.2, eyeX = 0.24, mouthY = 0.33, neckY = 0.62

    /// How open the eyes are: a blink every 5.3 s, two in a row every third time.
    static func blink(_ t: Double) -> Double {
        let cyc = t.truncatingRemainder(dividingBy: 5.3)
        let closed = max(exp(-pow((cyc - 0.15) / 0.06, 2)), Int(t / 5.3) % 3 == 0 ? exp(-pow((cyc - 0.42) / 0.06, 2)) : 0)
        return 1 - 0.92 * closed
    }

    /// The head's surface at (x, y) on its front, or nil outside it (an egg: narrower at the chin).
    static func surfaceZ(_ x: Double, _ y: Double) -> Double? {
        let sy = (y - headY) / halfHeight
        let w = halfWidth * (sy > 0 ? 1 - 0.2 * sy : 1)
        let q = 1 - pow(x / w, 2) - sy * sy
        return q > 0 ? depth * q.squareRoot() : nil
    }

    @MainActor private static var cache: [Int: [P]] = [:]

    @MainActor static func points(count n: Int) -> [P] {
        if let c = cache[n] { return c }
        var out: [P] = []
        out.reserveCapacity(n)
        var k = 0
        func h(_ salt: Double) -> Double { OrbPoints.hash(k, salt) }
        func add(_ kind: Kind, _ x: Double, _ y: Double, u: Double = 0, v: Double = 0, side: Double = 0, lum: Double, z: Double? = nil) {
            let zz = z ?? (surfaceZ(x, y) ?? 0) + 0.01
            out.append(P(kind: kind, x: x, y: y, z: zz, u: u, v: v, side: side, lum: lum, dither: h(14), phase: 2 * .pi * h(12)))
        }
        func share(_ f: Double, min m: Int) -> Int { max(m, Int(Double(n) * f)) }

        for side in [-1.0, 1.0] {
            let ex = side * eyeX
            for _ in 0..<share(0.026, min: 10) {
                k += 1; let u = 2 * h(1) - 1
                add(.lidUpper, ex + 0.11 * u, eyeY - 0.058 * cos(.pi * u / 2) + 0.006 * (h(2) - 0.5), u: u, side: side, lum: 1)
            }
            for _ in 0..<share(0.016, min: 6) {
                k += 1; let u = 2 * h(1) - 1
                add(.lidLower, ex + 0.1 * u, eyeY + 0.03 * cos(.pi * u / 2) - 0.004, u: u, side: side, lum: 0.7)
            }
            for _ in 0..<share(0.022, min: 8) {
                k += 1; let a = 2 * Double.pi * h(1), r = 0.024 + 0.022 * h(2).squareRoot()
                add(.iris, ex + r * cos(a), eyeY - 0.004 + r * sin(a), side: side, lum: 0.85)
            }
            for _ in 0..<share(0.004, min: 2) {
                k += 1
                add(.glint, ex - 0.016 + 0.008 * (h(1) - 0.5), eyeY - 0.022 + 0.008 * (h(2) - 0.5), side: side, lum: 1.2)
            }
            for _ in 0..<share(0.018, min: 6) {
                k += 1; let u = 2 * h(1) - 1
                add(.brow, ex + 0.135 * u, eyeY - 0.17 - 0.035 * cos(.pi * u / 2) + 0.012 * u * side + 0.012 * (h(2) - 0.5),
                    u: u, side: side, lum: 0.8)
            }
            for _ in 0..<share(0.014, min: 5) {
                k += 1; let a = 2 * Double.pi * h(1), r = 0.1 * h(2)
                add(.cheek, side * 0.33 + r * cos(a), 0.12 + 0.7 * r * sin(a), side: side, lum: 0.2 - 0.6 * r)
            }
            for _ in 0..<share(0.016, min: 5) {
                k += 1; let v = h(1)
                add(.ear, side * (halfWidth * 0.97 + 0.06 * sin(.pi * v)), -0.24 + 0.32 * v, side: side, lum: 0.5, z: 0.05)
            }
        }
        for _ in 0..<share(0.018, min: 6) {
            k += 1
            if h(1) < 0.4 {
                let v = h(2); add(.nose, 0.012 + 0.02 * v, -0.1 + 0.2 * v, lum: 0.4)
            } else {
                let u = 2 * h(2) - 1; add(.nose, 0.065 * u, 0.115 + 0.028 * u * u, u: u, lum: 0.75)
            }
        }
        // The lips are shapes with thickness (placed each frame by `MouthShape`), and the teeth.
        for _ in 0..<share(0.04, min: 14) { k += 1; add(.lipUpper, 0, mouthY, u: 2 * h(1) - 1, v: h(2), lum: 1) }
        for _ in 0..<share(0.045, min: 14) { k += 1; add(.lipLower, 0, mouthY, u: 2 * h(1) - 1, v: h(2), lum: 1) }
        for _ in 0..<share(0.014, min: 6) { k += 1; add(.teeth, 0, mouthY, u: 2 * h(1) - 1, v: h(2), lum: 0.5) }
        for _ in 0..<share(0.04, min: 8) {
            k += 1; let v = h(1), u = 2 * h(2) - 1
            add(.neck, 0.2 * u, neckY - 0.08 + 0.32 * v, lum: abs(u) > 0.85 ? 0.45 : 0.25, z: 0.3 * (1 - u * u))
        }
        for _ in 0..<share(0.17, min: 20) {
            k += 1
            let x = (2 * h(1) - 1) * 1.55
            let top = 0.9 + 0.32 * pow(max(0, abs(x) - 0.22) / 1.33, 1.5) + (abs(x) > 1.3 ? 0.9 * pow((abs(x) - 1.3) / 0.25, 2) : 0)
            if h(3) < 0.35 {
                add(.body, x, top + 0.01 * (h(2) - 0.5), lum: 0.6, z: 0)
            } else if h(3) < 0.45 && abs(x) < 0.24 {
                add(.body, x, 0.9 + (0.24 - abs(x)) * 1.1, lum: 0.5, z: 0)
            } else {
                let dd = pow(h(2), 1.3) * 0.95
                add(.body, x, top + dd, lum: 0.32 * (1 - dd), z: 0)
            }
        }
        while out.count < n && k < n * 8 {
            k += 1
            let zz = 1 - 2 * h(1), rr = max(0, 1 - zz * zz).squareRoot(), a = 2 * Double.pi * h(2)
            let sxu = rr * cos(a), syu = zz, szu = rr * sin(a)
            if szu < -0.35 { continue }
            let x = halfWidth * sxu * (syu > 0 ? 1 - 0.2 * syu : 1)
            let y = headY + halfHeight * syu
            let hairline = -0.5 + 0.09 * sin(2.4 * x + 0.8) + 0.25 * pow(x / halfWidth, 2)
            let isHair = y < hairline || (abs(sxu) > 0.8 && y < -0.02) || szu < -0.05
            if isHair {
                let strand = 0.5 + 0.5 * sin(22 * x + 9 * y + 3 * sin(4 * x))
                let lift = 1.07 + 0.06 * max(0, -syu)
                out.append(P(kind: .hair, x: x * lift, y: headY + (y - headY) * lift, z: depth * szu * lift, u: 0, v: 0, side: 0,
                             lum: 0.28 + 0.38 * strand * strand, dither: h(14), phase: 2 * .pi * h(12)))
            } else {
                if szu < 0 { continue }
                let inEye = pow((abs(x) - eyeX) / 0.13, 2) + pow((y - eyeY) / 0.075, 2) < 1
                let inMouth = pow(x / 0.23, 2) + pow((y - mouthY - 0.03) / 0.09, 2) < 1
                if inEye || inMouth || h(4) < 0.35 { continue }
                out.append(P(kind: .skin, x: x, y: y, z: depth * szu, u: 0, v: 0, side: 0, lum: 0.2 + 0.1 * h(3),
                             dither: h(14), phase: 2 * .pi * h(12)))
            }
        }
        cache[n] = out
        return out
    }

    /// A hand cupped behind an ear, seen from the front, its wrist at (0, 0), y up negative: four
    /// fingers rising and curving forward over the ear (each drawn with both edges and a rounded
    /// tip), the thumb, the palm's edges, and the forearm down to the frame's edge.
    static let handPoints: [HandPoint] = {
        var out: [HandPoint] = []
        var k = 0
        func h(_ salt: Double) -> Double { OrbPoints.hash(90_000 + k, salt) }
        func add(_ x: Double, _ y: Double, _ lum: Double) {
            k += 1
            out.append(HandPoint(x: x, y: y, lum: lum, dither: h(14), phase: 2 * .pi * h(12)))
        }
        /// A finger along a quadratic curve base → tip (bent by `c`), `w` wide.
        func finger(_ b: (Double, Double), _ c: (Double, Double), _ tip: (Double, Double), _ w: Double, lum: Double) {
            let n = 34
            for i in 0...n {
                let s = Double(i) / Double(n), m = 1 - s
                let x = m * m * b.0 + 2 * m * s * c.0 + s * s * tip.0
                let y = m * m * b.1 + 2 * m * s * c.1 + s * s * tip.1
                let dx = 2 * m * (c.0 - b.0) + 2 * s * (tip.0 - c.0), dy = 2 * m * (c.1 - b.1) + 2 * s * (tip.1 - c.1)
                let l = max(1e-6, (dx * dx + dy * dy).squareRoot())
                let nx = -dy / l * w, ny = dx / l * w
                add(x + nx, y + ny, lum); add(x - nx, y - ny, lum * 0.8)
            }
            for i in 0..<10 {                                       // the rounded tip
                let a = Double.pi * Double(i) / 9
                let dx = 2 * (tip.0 - c.0), dy = 2 * (tip.1 - c.1)
                let l = max(1e-6, (dx * dx + dy * dy).squareRoot())
                let ux = dx / l, uy = dy / l
                add(tip.0 + w * (cos(a) * -uy + sin(a) * ux), tip.1 + w * (cos(a) * ux + sin(a) * uy), lum)
            }
        }
        // Index (front, curving most) to little finger (back).
        finger((-0.035, -0.2), (-0.04, -0.36), (-0.13, -0.42), 0.017, lum: 0.95)
        finger((-0.005, -0.21), (-0.005, -0.39), (-0.085, -0.47), 0.018, lum: 0.95)
        finger((0.025, -0.2), (0.03, -0.37), (-0.04, -0.45), 0.017, lum: 0.9)
        finger((0.05, -0.18), (0.06, -0.31), (0.0, -0.38), 0.015, lum: 0.85)
        finger((-0.05, -0.06), (-0.11, -0.08), (-0.14, -0.17), 0.018, lum: 0.85)        // the thumb
        for i in 0..<24 {                                           // the palm's edges
            let s = Double(i) / 23
            add(0.06 + 0.005 * sin(.pi * s), -0.18 * s, 0.7)        // its back edge
            add(-0.045 - 0.008 * sin(.pi * s), -0.06 - 0.14 * s, 0.6)
        }
        for i in 0..<60 {                                           // the forearm, two edges
            let s = Double(i) / 59
            add(-0.05 + 0.45 * s, 0.02 + 1.3 * s, 0.6 * (1 - 0.6 * s))
            add(0.065 + 0.45 * s, 0.0 + 1.3 * s, 0.6 * (1 - 0.6 * s))
        }
        return out
    }()
}

/// The sculpted head's points: the face's relief (`ImprintGeometry.relief`) sampled evenly over its
/// front, the sides and back of the head, short hair, the neck and the shoulders; each with its
/// surface normal (for the light) and its tone.
enum FaceSculpt {
    enum Part { case face, head, hair, body }
    struct P {
        let part: Part; let x: Double; let y: Double; let z: Double
        let nx: Double; let ny: Double; let nz: Double; let tone: Double; let dither: Double; let phase: Double
    }

    @MainActor private static var cache: [Int: [P]] = [:]

    @MainActor static func points(count n: Int) -> [P] {
        if let c = cache[n] { return c }
        var out: [P] = []
        out.reserveCapacity(n)
        let hy = FaceGeometry.headY, hh = FaceGeometry.halfHeight, hw = FaceGeometry.halfWidth, dp = FaceGeometry.depth
        func hairline(_ x: Double) -> Double { -0.52 + 0.08 * sin(2.4 * x + 0.8) + 0.24 * pow(x / hw, 2) }
        // The face: an even grid over the front, through the relief; normals by finite differences.
        var j = 0, made = 0
        let faceShare = Int(Double(n) * 0.52)
        while made < faceShare && j < faceShare * 3 {
            j += 1
            let (u, v) = evenPoint(j)
            let x = (u - 0.5) * 1.24, y = -0.98 + 1.6 * v
            guard y > hairline(x) - 0.02, let z = ImprintGeometry.relief(x, y) else { continue }
            let e = 0.01
            let zx = ((ImprintGeometry.relief(x + e, y) ?? z) - (ImprintGeometry.relief(x - e, y) ?? z)) / (2 * e)
            let zy = ((ImprintGeometry.relief(x, y + e) ?? z) - (ImprintGeometry.relief(x, y - e) ?? z)) / (2 * e)
            let l = (zx * zx + zy * zy + 1).squareRoot()
            out.append(P(part: .face, x: x, y: y, z: z, nx: -zx / l, ny: -zy / l, nz: 1 / l, tone: 0.78 * (0.55 + 0.45 * smoothstep(hairline(x) - 0.02, hairline(x) + 0.12, y)),
                         dither: OrbPoints.hash(j, 14), phase: OrbPoints.hash(j, 12) * 6.3))
            made += 1
        }
        // The sides and back of the head, and the hair over the top and back.
        let headShare = Int(Double(n) * 0.34)
        var placed = 0
        for k in 0..<(headShare * 4) where placed < headShare {
            let (u, v) = evenPoint(k + 50_000)
            let zz = 1 - 2 * u, r = max(0, 1 - zz * zz).squareRoot(), a = 2 * Double.pi * v
            let nx = r * cos(a), ny = zz, nz = r * sin(a)
            let w = ny > 0 ? 1 - 0.2 * ny : 1
            let x = hw * nx * w, y = hy + hh * ny, z = dp * nz
            let isHair = y < hairline(x) || nz < -0.1 || (abs(nx) > 0.82 && y < -0.05)
            if !isHair && nz > 0.35 { continue }                                 // the front is the relief's
            if nz < -0.3 { continue }                                            // never seen
            // Strands flowing from a side part, so it reads as hair (not a cap).
            let strand = pow(0.5 + 0.5 * sin(34 * (0.8 * (x + 0.12) + 0.6 * y) + 3 * sin(5 * y)), 3)
            let lift = isHair ? 1.045 : 1
            out.append(P(part: isHair ? .hair : .head, x: x * lift, y: hy + (y - hy) * lift, z: z * lift, nx: nx, ny: ny, nz: nz,
                         tone: isHair ? 0.22 + 0.55 * strand : 0.72, dither: OrbPoints.hash(k, 15), phase: OrbPoints.hash(k, 13) * 6.3))
            placed += 1
        }
        // The neck and the shoulders.
        for k in 0..<Int(Double(n) * 0.13) {
            let (u, v) = evenPoint(k + 90_000)
            if u < 0.25 {
                let a = Double.pi * (v - 0.5) * 1.6, y = FaceGeometry.neckY - 0.1 + 0.36 * (u / 0.25)
                out.append(P(part: .body, x: 0.2 * sin(a), y: y, z: 0.2 * cos(a), nx: sin(a), ny: 0, nz: cos(a), tone: 0.75,
                             dither: OrbPoints.hash(k, 16), phase: OrbPoints.hash(k, 17) * 6.3))
            } else {
                let x = (v - 0.5) * 3.1
                let top = 0.9 + 0.32 * pow(max(0, abs(x) - 0.22) / 1.33, 1.5)
                let dy = pow((u - 0.25) / 0.75, 1.4) * 0.9
                let slope = 0.32 * 1.5 * pow(max(0, abs(x) - 0.22) / 1.33, 0.5) / 1.33 * (x > 0 ? 1 : -1)
                let l = (slope * slope + 1 + 0.36).squareRoot()
                out.append(P(part: .body, x: x, y: top + dy, z: 0, nx: slope / l * (dy < 0.05 ? 1 : 0.4), ny: -1 / l * (dy < 0.05 ? 1 : 0.3), nz: 0.6 / l + (dy < 0.05 ? 0 : 0.6),
                             tone: 0.7 * (1 - 0.5 * dy), dither: OrbPoints.hash(k, 18), phase: OrbPoints.hash(k, 19) * 6.3))
            }
        }
        cache[n] = out
        return out
    }
}

/// The rings' fixed frames: the six great circles normal to an icosahedron's six axes through
/// opposite corners (together they cross at the 30 corners of an icosidodecahedron).
enum RingGeometry {
    typealias V = (Double, Double, Double)
    static let rings: [(n: V, u: V, v: V)] = {
        let phi = (1 + 5.0.squareRoot()) / 2
        let axes: [V] = [(0, 1, phi), (0, 1, -phi), (1, phi, 0), (-1, phi, 0), (phi, 0, 1), (phi, 0, -1)]
        func norm(_ a: V) -> V { let l = (a.0 * a.0 + a.1 * a.1 + a.2 * a.2).squareRoot(); return (a.0 / l, a.1 / l, a.2 / l) }
        func cross(_ a: V, _ b: V) -> V { (a.1 * b.2 - a.2 * b.1, a.2 * b.0 - a.0 * b.2, a.0 * b.1 - a.1 * b.0) }
        return axes.map { a in
            let n = norm(a)
            let helper: V = abs(n.1) < 0.9 ? (0, 1, 0) : (1, 0, 0)
            let u = norm(cross(n, helper)), v = cross(n, u)
            return (n, u, v)
        }
    }()
}

// MARK: - The ocean's geometry

/// The sea's fixed geometry, in the frame's half-side units: the horizon and the camera's focal
/// length (the camera one unit above the water), the moon, and the wave trains.
enum OceanGeometry {
    /// One wave train: its number, speed (deep water: long waves are faster), direction (toward the
    /// viewer at 0), its height at rest, steepness, and which part of the voice raises it.
    struct Wave {
        let k: Double, omega: Double, dirX: Double, dirD: Double, rest: Double, steep: Double, phase: Double
        let low: Double, mid: Double, high: Double
    }
    static let horizon = -0.36, focal = 1.36
    static let moon = (x: 0.38, y: -0.72, r: 0.085)
    /// From the water toward the moon.
    static let moonDirection: (x: Double, y: Double, z: Double) = {
        let x = moon.x / focal, y = (horizon - moon.y) / focal, z = 1.0
        let l = (x * x + y * y + z * z).squareRoot()
        return (x / l, y / l, z / l)
    }()
    static let waves: [Wave] = {
        let spec: [(lambda: Double, angle: Double, low: Double, mid: Double, high: Double)] = [
            (5.5, 0.0, 1, 0, 0), (3.4, 0.35, 1, 0.3, 0), (2.2, -0.42, 0.4, 1, 0),
            (1.4, 0.75, 0, 1, 0.3), (0.85, -0.9, 0, 0.3, 1), (0.5, 0.25, 0, 0, 1),
        ]
        return spec.enumerated().map { i, s in
            let k = 2 * Double.pi / s.lambda
            return Wave(k: k, omega: 0.42 * (9.8 * k).squareRoot(), dirX: sin(s.angle), dirD: cos(s.angle),
                        rest: 0.03 * s.lambda / (2 * .pi), steep: 0.03 * 6.5, phase: Double(i) * 1.7, low: s.low, mid: s.mid, high: s.high)
        }
    }()
}
