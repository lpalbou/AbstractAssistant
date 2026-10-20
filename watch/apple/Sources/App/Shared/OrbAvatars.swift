import SwiftUI

// Two avatars made from the Face, each another way of showing what is happening: Imprint (a face
// seen only where it touches a pane of glass) and Eye (one large, friendly eye). Contour and
// Membrane, the face in lines of light, are in OrbLines.swift.

extension OrbCanvas {
    // MARK: Imprint

    /// A face, zoomed in, resting against a pane of glass: what touches the pane is drawn as warm,
    /// smooth light with a bright rim where it meets the glass (the brows, the nose, the lips, the
    /// chin; the eyes closed and serene), the rest of the face a faint glow behind it. Its voice
    /// presses it in, so more of it shows as it speaks (the cheeks, the forehead) and the lips part
    /// with the words; while you speak it turns to lay its cheek against the pane; thinking, it draws
    /// back softly from the glass, dimmer but whole, the pane drifting through its depth.
    func drawImprint(_ gc: inout GraphicsContext, _ box: CGSize) {
        var d = dotCanvas(box)
        d.softSize = 2.5
        let ph = OrbPhases(engine)
        let th = ph.think, talk = engine.talking, e = engine.engagement, listen = ph.listen
        let pal = PortraitPalette.colors(look.color)
        let mouth = MouthShape(engine: engine, smileBase: 1.3 + 0.2 * listen)
        let yaw = 0.12 * sin(t * 0.27) - 0.5 * listen + 0.08 * th
        // Its own voice: a nod with its phrasing; yours: it nods along with you.
        let level = engine.history.value(secondsAgo: 0.05)
        let pitch = 0.04 * sin(t * 0.19) - 0.05 * th + 0.05 * listen * level * sin(t * 4.3) + 0.04 * mouth.open * sin(t * 6.1)
        let roll = 0.03 * sin(t * 0.23) + 0.05 * listen
        let pose = HeadPose(yaw: yaw, pitch: pitch, roll: roll, pivotY: 0, lift: 0)
        let press = 0.03 * talk * e * min(1, 1.6 * engine.loud) + (0.006 + 0.015 * level) * listen + 0.005 * sin(t * 0.9) - 0.035 * th
        // Thinking: the pane drifts slowly through its depth; working: it flickers through it quickly.
        let plane = ImprintGeometry.plane + 0.03 * th * sin(t * 1.3) + ph.work * (0.035 * sin(t * 5.3) - 0.02)
        let band = ImprintGeometry.band
        // How much of the face behind the pane still glows: a little at rest, more as it draws back.
        let behind = 0.16 + 0.34 * th
        let reach = 0.16 + 0.3 * th
        let my = FaceGeometry.mouthY
        // Drawing back: a little smaller and dimmer.
        let scale = 1.78 * (1 - 0.07 * th), shift = 0.08
        let dim = 1 - 0.3 * th
        for p in ImprintGeometry.points(count: min(2000, Int(Double(pointBudget(box)) * 1.1))) {
            var x = p.x, y = p.y, z = p.z
            // The mouth: the jaw drops below it, the opening recedes, rounder or wider with the vowel.
            if abs(y - my) < 0.3 {
                let near = exp(-pow((y - my) / 0.12, 2)) * exp(-pow(x / 0.3, 2))
                x *= 1 - (1 - mouth.width) * near
                y += mouth.jaw(x, y) * 0.9
                if mouth.open > 0.05 {
                    let gap = 0.1 * mouth.open
                    let inside = exp(-pow(x / (0.17 * mouth.width), 2) - pow((y - my - gap * 0.6) / (gap + 0.004), 2))
                    z -= 0.13 * inside
                }
                z += 0.02 * mouth.pout * near
            }
            // Closed, serene eyes: a lid crease curving gently down (no hollow).
            let ex = (abs(x) - FaceGeometry.eyeX) / 0.1
            if abs(ex) < 1 {
                let lid = FaceGeometry.eyeY + 0.02 * (1 - ex * ex)
                z -= 0.035 * exp(-pow((y - lid) / 0.008, 2))
            }
            let r = pose.apply(x, y, z)
            let dz = r.z + press - plane
            guard dz > -reach else { continue }
            // Lit by its own surface (soft frontal light), so the features read; what touches the
            // pane bright, with a rim where it meets it; what lies behind, a faint glow fading with depth.
            let n = pose.apply(p.nx, p.ny, p.nz)
            let light = max(0, -0.25 * n.x - 0.32 * n.y + 0.91 * n.z)
            let lit = 0.12 + 0.6 * pow(light, 1.5)
            let touch = smoothstep(-band, 0.01, dz)
            let flat = touch * min(0.8, lit * (0.85 + 0.2 * smoothstep(0, 0.08, dz)) + 0.3 * exp(-pow(dz / band, 2)))
                + (1 - touch) * behind * lit * (1 - smoothstep(0, reach, -dz)) * 1.6
            let sx = r.x * scale, sy = (r.y + shift) * scale
            placeLit(&d, sx, sy, (flat * (0.8 + 0.3 * p.lum) + 0.1 * engine.signal) * dim, 0.5 + 0.3 * (p.dither - 0.5), phase: p.phase,
                  lum: p.lum, size: 0.8)
        }
        // The pane: a faint sheen sweeping across it.
        for k in 0..<40 {
            let x = 2 * OrbPoints.hash(k, 41) - 1, y = 2 * OrbPoints.hash(k, 43) - 1
            let sweep = exp(-pow((x + y) * 0.7 - (t * 0.25).truncatingRemainder(dividingBy: 3) + 1.5, 2) * 6)
            d.dot(x * 1.9, y * 1.9, 0.05 + 0.2 * sweep, OrbPoints.hash(k, 14))
        }
        // The closed eyes' lashes (a content, upturned curve) and the smile, in soft lines of light
        // on the face, brighter where it touches the pane.
        let lw = max(0.6, d.px * 0.8)
        func on(_ x: Double, _ y: Double) -> (p: CGPoint, a: Double) {
            let r = pose.apply(x, y, (ImprintGeometry.grid.at(x, y) ?? 0.4) + 0.01)
            let dz = r.z + press - plane
            return (d.screen(r.x * scale, (r.y + shift) * scale), dim * (0.45 + 0.55 * smoothstep(-reach, 0, dz)) * (r.z > 0.1 ? 1 : 0))
        }
        var lashes = Path(), smileLine = Path(), seen = 0.0
        for side in [-1.0, 1.0] {
            for j in 0...10 {
                let u = -1 + 2 * Double(j) / 10
                let q = on(side * (FaceGeometry.eyeX + 0.085 * u), FaceGeometry.eyeY + 0.022 * (1 - u * u) - 0.004)
                seen += q.a / 22
                j == 0 ? lashes.move(to: q.p) : lashes.addLine(to: q.p)
            }
        }
        let rest = max(0, 1 - 4 * mouth.open)
        for j in 0...14 {
            let u = -1 + 2 * Double(j) / 14
            let q = on(0.16 * mouth.width * u, my - 0.046 * u * u + 0.004)
            j == 0 ? smileLine.move(to: q.p) : smileLine.addLine(to: q.p)
        }
        let under: (inout GraphicsContext) -> Void = { g in
            g.stroke(lashes, with: .color(pal[3].opacity(0.6 * seen)), style: StrokeStyle(lineWidth: lw * 3.5, lineCap: .round))
            g.stroke(smileLine, with: .color(pal[2].opacity(0.5 * rest * dim)), style: StrokeStyle(lineWidth: lw * 3.5, lineCap: .round))
        }
        let over: (inout GraphicsContext) -> Void = { g in
            g.stroke(lashes, with: .color(pal[4].opacity(0.7 * seen)), style: StrokeStyle(lineWidth: lw * 1.2, lineCap: .round))
            g.stroke(smileLine, with: .color(pal[4].opacity(0.55 * rest * dim)), style: StrokeStyle(lineWidth: lw * 1.1, lineCap: .round))
        }
        finishSoft(&gc, d, pal, surface: 0.45, crisp: 0.6, blur: 1.8, under: under, over: over)
    }
    // MARK: Eye

    /// One large, friendly eye: soft lids drawn in light with curling lashes, a soft white, an iris
    /// of fine fibers glowing warm near the pupil and cool at its rim, a catchlight. As it speaks its
    /// eye smiles, the fibers glow with its voice (its spectrum around the iris) and the pupil narrows
    /// on loud sounds; while you speak it opens wide, its brow lifts, its pupil widens and rings of
    /// your voice ripple in toward it; thinking, it looks up and aside, its lids lower a little and
    /// its iris turns slowly. It blinks every few seconds.
    func drawEye(_ gc: inout GraphicsContext, _ box: CGSize) {
        var d = dotCanvas(box)
        d.softSize = 2.2
        let ph = OrbPhases(engine)
        let th = ph.think, hist = engine.history, loud = engine.loud
        let listen = ph.listen, speak = ph.speak, busy = ph.work
        let pal = PortraitPalette.colors(look.color)
        let spectrum = VoiceFeatures(level: loud, bands: engine.bands)
        let blink = FaceGeometry.blink(t)
        let open = (0.8 + 0.18 * listen - 0.2 * th) * blink
        let smile = 0.06 + 0.12 * speak + 0.06 * listen
        let W = EyeGeometry.halfWidth
        let hu = 0.62 * open, hl = max(0.02, (0.42 - smile) * open)
        func upper(_ x: Double) -> Double { -hu * pow(max(0, 1 - pow(x / W, 2)), 0.75) + 0.04 * (x / W) }
        func lower(_ x: Double) -> Double { hl * pow(max(0, 1 - pow(x / W, 2)), 0.9) - 0.1 * smile * max(0, 1 - pow(x / W, 2)) + 0.04 * (x / W) }
        func inside(_ x: Double, _ y: Double) -> Bool { abs(x) < W && y > upper(x) && y < lower(x) }
        // Working: the gaze jumps from point to point (reading), each fixation a moment long.
        let fix = Int(t * 2.2)
        let jumpX = (OrbPoints.hash(fix, 81) - 0.5) * 0.5, jumpY = (OrbPoints.hash(fix, 82) - 0.5) * 0.18
        let gx = (0.1 * sin(t * 0.4) + 0.05 * sin(t * 0.13)) * (1 - listen) * (1 - th) * (1 - busy) + th * (-0.26 + 0.07 * sin(t * 0.7)) + busy * jumpX
        let gy = 0.03 * sin(t * 0.33) * (1 - th) * (1 - busy) - 0.17 * th + busy * jumpY + 0.03
        let iris = EyeGeometry.irisRadius
        let pupil = 0.16 + 0.07 * listen - 0.05 * speak * min(1, 1.5 * loud) - 0.02 * th - 0.04 * busy
        let turn = 0.12 * engine.ringTurn                                // the iris turns while it thinks
        let scale = 1.42, shift = 0.08
        let S = d.R * scale
        let lw = max(0.6, d.px * 0.8)
        func scr(_ x: Double, _ y: Double) -> CGPoint { d.screen(x * scale, (y + shift) * scale) }
        func put(_ x: Double, _ y: Double, _ b: Double, _ dither: Double, _ phase: Double, lum: Double = 0.7) {
            place(&d, x * scale, (y + shift) * scale, b, 0.5 + 0.4 * (dither - 0.5), phase: phase, lum: lum, size: 0.8)
        }
        for p in EyeGeometry.points(count: pointBudget(box)) {
            switch p.kind {
            case .fiber:
                // A point on its fiber, from the pupil's edge out to the iris's rim.
                let r = pupil + (iris - pupil) * p.u
                let a = p.a + turn + 0.22 * sin(3 * p.u + p.a * 2) * (1 - p.u)
                let x = gx + r * cos(a), y = gy + r * sin(a)
                guard inside(x, y) else { continue }
                var b = p.lum * (0.3 + 0.3 * exp(-pow((p.u - 0.3) / 0.1, 2)) + 0.35 * smoothstep(0.85, 1, p.u))
                let pos = (a.truncatingRemainder(dividingBy: 2 * .pi) + 2 * .pi).truncatingRemainder(dividingBy: 2 * .pi) / (2 * .pi)
                b += speak * 0.8 * spectrum.band(at: abs(pos * 2 - 1)) * (0.4 + 0.6 * p.u)
                if listen > 0.01 { b += listen * 0.8 * hist.value(secondsAgo: (1 - p.u) * 0.9) * exp(-pow(sin((p.u - t * 1.2) * .pi * 2), 2) * 2) }
                b += 0.08 * engine.signal
                put(x, y, b, p.dither, p.phase, lum: p.lum)
            case .pupilEdge:
                let x = gx + pupil * cos(p.a), y = gy + pupil * sin(p.a)
                guard inside(x, y) else { continue }
                put(x, y, 0.6, p.dither, p.phase)
            }
        }
        // The eye's opening, and the lines of its lids, crease, lashes and brow.
        func line(_ n: Int, from x0: Double, to x1: Double, _ f: (Double) -> Double) -> Path {
            var path = Path()
            for j in 0...n {
                let x = x0 + (x1 - x0) * Double(j) / Double(n)
                j == 0 ? path.move(to: scr(x, f(x))) : path.addLine(to: scr(x, f(x)))
            }
            return path
        }
        var almond = line(28, from: -W, to: W, upper)
        for j in (0...28).reversed() { let x = -W + 2 * W * Double(j) / 28; almond.addLine(to: scr(x, lower(x))) }
        almond.closeSubpath()
        let upperLid = line(28, from: -W * 1.02, to: W * 1.02, upper)
        let lowerLid = line(24, from: -W * 0.94, to: W * 0.94, lower)
        let crease = line(20, from: -W * 0.8, to: W * 0.85) { x in upper(x) * 1.05 - 0.13 - 0.05 * open - 0.03 * listen }
        let browY = -0.98 - 0.1 * listen - 0.04 * th
        let brow = line(20, from: -1.1, to: 1.15) { x in browY - 0.04 * th * (0.65 + 0.35 * x / 1.15) + 0.2 * pow(x / 1.15, 2) + 0.04 * (1 - open) + 0.03 * (x / 1.15) }
        // Lashes along the upper lid, longer toward the outer corner, curling up and out.
        var lashes = Path()
        for l in 0..<10 {
            let f = Double(l) / 9, x = W * (-0.4 + 1.32 * f + 0.03 * (OrbPoints.hash(l, 61) - 0.5))
            guard abs(x) < W * 0.97 else { continue }
            let base = upper(x), len = (0.07 + 0.1 * f * f) * (0.9 + 0.2 * OrbPoints.hash(l, 62)) * (0.55 + 0.45 * open)
            let dir = 0.2 + 0.8 * f
            lashes.move(to: scr(x, base))
            lashes.addQuadCurve(to: scr(x + dir * len * 0.7, base - len * 1.05), control: scr(x + dir * len * 0.6, base - len * 0.4))
        }
        let ic = scr(gx, gy), ri = iris * S, rp = pupil * S
        let glint = scr(gx * 0.5 - 0.14, gy * 0.5 - 0.17), g1 = 0.075 * S, g2 = 0.035 * S
        let irisColors: [Color] = look.color.map { c in [Color.white.opacity(0.55), c.opacity(0.5), c.opacity(0.85)] }
            ?? [Color(hex: 0xffd08a).opacity(0.85), Color(hex: 0xffb38a).opacity(0.6), Color(hex: 0xf09ac6).opacity(0.5), Color(hex: 0x8b7cf6).opacity(0.6),
                Color(hex: 0x6366f1).opacity(0.85)]
        let under: (inout GraphicsContext) -> Void = { g in
            g.stroke(upperLid, with: .color(pal[3].opacity(0.55)), style: StrokeStyle(lineWidth: lw * 5, lineCap: .round))
            g.stroke(brow, with: .color(pal[2].opacity(0.4)), style: StrokeStyle(lineWidth: lw * 6, lineCap: .round))
        }
        let over: (inout GraphicsContext) -> Void = { g in
            if blink > 0.25 {
                var e = g
                e.clip(to: almond)
                // The white: soft and warm, dimmer toward the corners; the iris's own light under its fibers.
                var white = Path(almond.boundingRect.insetBy(dx: -2, dy: -2))
                white.addEllipse(in: CGRect(x: ic.x - ri, y: ic.y - ri, width: 2 * ri, height: 2 * ri))
                e.fill(white, with: .radialGradient(Gradient(colors: [pal[4].opacity(0.18), pal[1].opacity(0.07)]), center: scr(0, 0.05),
                                                    startRadius: 0, endRadius: W * S), style: FillStyle(eoFill: true))
                var disc = Path(ellipseIn: CGRect(x: ic.x - ri, y: ic.y - ri, width: 2 * ri, height: 2 * ri))
                disc.addEllipse(in: CGRect(x: ic.x - rp, y: ic.y - rp, width: 2 * rp, height: 2 * rp))
                e.fill(disc, with: .radialGradient(Gradient(colors: irisColors), center: ic, startRadius: rp, endRadius: ri), style: FillStyle(eoFill: true))
                e.fill(Path(ellipseIn: CGRect(x: glint.x - g1, y: glint.y - g1, width: 2 * g1, height: 2 * g1)),
                       with: .radialGradient(Gradient(colors: [.white.opacity(0.95), .white.opacity(0.7), .clear]), center: glint, startRadius: 0, endRadius: g1))
                let gl2 = CGPoint(x: glint.x + 0.24 * S, y: glint.y + 0.22 * S)
                e.fill(Path(ellipseIn: CGRect(x: gl2.x - g2, y: gl2.y - g2, width: 2 * g2, height: 2 * g2)), with: .color(.white.opacity(0.45)))
            }
            g.stroke(crease, with: .color(pal[2].opacity(0.35)), style: StrokeStyle(lineWidth: lw, lineCap: .round))
            g.stroke(lashes, with: .color(pal[4].opacity(0.65)), style: StrokeStyle(lineWidth: lw * 1.0, lineCap: .round))
            g.stroke(upperLid, with: .color(pal[4].opacity(0.9)), style: StrokeStyle(lineWidth: lw * 2, lineCap: .round))
            if blink > 0.25 { g.stroke(lowerLid, with: .color(pal[3].opacity(0.5)), style: StrokeStyle(lineWidth: lw * 1.1, lineCap: .round)) }
            g.stroke(brow, with: .color(pal[2].opacity(0.4)), style: StrokeStyle(lineWidth: lw * 3, lineCap: .round))
            g.stroke(brow, with: .color(pal[4].opacity(0.55)), style: StrokeStyle(lineWidth: lw * 1.1, lineCap: .round))
        }
        finishSoft(&gc, d, pal, surface: 0.35, crisp: 0.8, blur: 1.6, under: under, over: over)
    }
}
// MARK: - Imprint's points

/// The face as a relief: a dense even grid over the head's front, each point at the depth of the
/// face there (the egg of the head, the nose, the brow ridge, the eye sockets and eyes, the
/// cheekbones, the lips, the chin).
enum ImprintGeometry {
    struct P {
        let x: Double; let y: Double; let z: Double; let lum: Double; let dither: Double; let phase: Double
        /// The surface's normal there (its light shows the features).
        var nx = 0.0, ny = 0.0, nz = 1.0
    }
    /// The pane: at rest most of the face touches it (the forehead, brows, nose, cheeks, lips and
    /// chin; the eyes, the nostrils and the line between the lips stay open); how wide the rim of a
    /// touch is.
    static let plane = 0.47, band = 0.016

    static func relief(_ x: Double, _ y: Double) -> Double? {
        let sy = (y - FaceGeometry.headY) / FaceGeometry.halfHeight
        // The outline: the cranium round, the jaw tapering to the chin.
        let w = FaceGeometry.halfWidth * (sy > 0 ? 1 - 0.3 * pow(sy, 1.25) : 1 - 0.04 * sy * sy)
        guard 1 - pow(x / w, 2) - sy * sy > 0 else { return nil }
        let ax = abs(x), my = FaceGeometry.mouthY, ex = FaceGeometry.eyeX, ey = FaceGeometry.eyeY
        func g(_ dx: Double, _ sx: Double, _ dy: Double, _ syy: Double) -> Double { exp(-pow(dx / sx, 2) - pow(dy / syy, 2)) }
        // A face is nearly flat from forehead to chin and curves back at the sides.
        var z = FaceGeometry.depth * pow(max(0, 1 - pow(x / w, 2)), 0.32) * (1 - 0.22 * pow((y + 0.1) / FaceGeometry.halfHeight, 2))
        // The forehead's dome, the temples' hollows, the brow ridge and the soft rise between the brows.
        z += 0.02 * g(x, 0.35, y + 0.62, 0.2)
        z -= 0.03 * g(ax - 0.47, 0.08, y + 0.36, 0.15)
        z += 0.026 * g(ax - 0.2, 0.17, y + 0.335, 0.05)
        z += 0.016 * g(x, 0.06, y + 0.3, 0.05)
        // The eyes: sockets deepest at the inner corners, the eyeball under its lids, the lid's crease.
        z -= 0.065 * g(ax - ex, 0.12, y - ey, 0.075)
        z -= 0.03 * g(ax - 0.13, 0.04, y - ey - 0.01, 0.04)
        z += 0.06 * g(ax - ex, 0.07, y - ey, 0.042)
        let crease = ey - 0.048 - 0.012 * max(0, 1 - pow((ax - ex) / 0.09, 2))
        z -= 0.012 * exp(-pow((y - crease) / 0.008, 2)) * max(0, 1 - pow((ax - ex) / 0.1, 2))
        // The nose: a narrow bridge widening to a rounded tip, its wings, the nostrils under it.
        let bridgeW = 0.032 + 0.034 * smoothstep(-0.2, 0.08, y)
        z += 0.13 * smoothstep(-0.27, 0.05, y) * (1 - smoothstep(0.07, 0.13, y)) * exp(-pow(x / bridgeW, 2))
        z += 0.045 * g(x, 0.05, y - 0.07, 0.04)
        z += 0.05 * g(ax - 0.07, 0.034, y - 0.1, 0.034)
        z -= 0.055 * g(ax - 0.04, 0.018, y - 0.135, 0.012)
        // The philtrum: a groove between two soft ridges down to the upper lip.
        z -= 0.012 * g(x, 0.015, y - 0.22, 0.05)
        z += 0.008 * g(ax - 0.024, 0.01, y - 0.22, 0.05)
        // The lips: the mouth's line smiling a little, a cupid's bow on the upper lip, a fuller
        // lower lip, the corners tucked in, the groove under the lower lip.
        let smileY = my - 0.048 * pow(x / 0.17, 2)
        let bow = exp(-pow((ax - 0.032) / 0.02, 2))
        z += 0.055 * g(x, 0.16, y - (my - 0.034 - 0.008 * bow), 0.024)
        z += 0.072 * g(x, 0.14, y - (my + 0.042), 0.03)
        z -= 0.048 * g(x, 0.18, y - smileY, 0.012)
        z -= 0.014 * g(ax - 0.18, 0.025, y - my + 0.045, 0.03)
        z -= 0.025 * g(x, 0.12, y - (my + 0.105), 0.025)
        // The chin, the cheekbones high at the sides, full cheeks under them, a hollow toward the jaw.
        z += 0.07 * g(x, 0.13, y - 0.5, 0.07)
        z += 0.06 * g(ax - 0.36, 0.1, y + 0.04, 0.07)
        z += 0.06 * g(ax - 0.27, 0.12, y - 0.1, 0.1)
        z -= 0.025 * g(ax - 0.41, 0.07, y - 0.21, 0.1)
        // The folds from the nose's wings to the mouth's corners.
        let fx = 0.09 + (0.2 - 0.09) * min(1, max(0, (y - 0.12) / 0.21)), fy = min(max(y, 0.12), 0.33)
        if y > 0.08 && y < 0.37 { z -= 0.008 * exp(-pow((ax - fx) / 0.012, 2)) * exp(-pow((y - fy) / 0.2, 2)) }
        return z
    }

    /// The relief, computed once on a fine grid over the head and read back by interpolation (the
    /// line styles read it thousands of times a frame); nil outside the head.
    struct Grid: Sendable {
        static let x0 = -0.72, y0 = -1.0, step = 0.01, nx = 145, ny = 165
        let z: [Double]                                      // -1: outside the head
        func at(_ x: Double, _ y: Double) -> Double? {
            let fx = (x - Grid.x0) / Grid.step, fy = (y - Grid.y0) / Grid.step
            guard fx >= 0, fy >= 0, fx < Double(Grid.nx - 1), fy < Double(Grid.ny - 1) else { return nil }
            let i = Int(fx), j = Int(fy), u = fx - Double(i), v = fy - Double(j)
            let a = z[j * Grid.nx + i], b = z[j * Grid.nx + i + 1], c = z[(j + 1) * Grid.nx + i], d = z[(j + 1) * Grid.nx + i + 1]
            guard a >= 0, b >= 0, c >= 0, d >= 0 else { return nil }
            return (a * (1 - u) + b * u) * (1 - v) + (c * (1 - u) + d * u) * v
        }
    }
    static let grid: Grid = {
        var z = [Double](repeating: -1, count: Grid.nx * Grid.ny)
        for j in 0..<Grid.ny {
            for i in 0..<Grid.nx {
                if let v = relief(Grid.x0 + Double(i) * Grid.step, Grid.y0 + Double(j) * Grid.step) { z[j * Grid.nx + i] = v }
            }
        }
        return Grid(z: z)
    }()

    @MainActor private static var cache: [Int: [P]] = [:]

    @MainActor static func points(count n: Int) -> [P] {
        if let c = cache[n] { return c }
        var out: [P] = []
        out.reserveCapacity(n)
        // An even (hexagonal) grid over the face's box, as dense as the budget allows.
        let area = 1.25 * 1.5
        let step = (area / Double(n) * 2 / 3.0.squareRoot()).squareRoot()
        var row = 0, k = 0
        var y = -0.95
        while y < 0.62 {
            var x = -0.64 + (row % 2 == 0 ? 0 : step / 2)
            while x < 0.64 {
                k += 1
                if let z = relief(x, y) {
                    let e = 0.008
                    let zx = ((relief(x + e, y) ?? z) - (relief(x - e, y) ?? z)) / (2 * e)
                    let zy = ((relief(x, y + e) ?? z) - (relief(x, y - e) ?? z)) / (2 * e)
                    let l = (zx * zx + zy * zy + 1).squareRoot()
                    out.append(P(x: x, y: y, z: z, lum: 0.75 + 0.25 * OrbPoints.hash(k, 3), dither: OrbPoints.hash(k, 14),
                                 phase: 2 * .pi * OrbPoints.hash(k, 12), nx: -zx / l, ny: -zy / l, nz: 1 / l))
                }
                x += step
            }
            y += step * 3.0.squareRoot() / 2; row += 1
        }
        cache[n] = out
        return out
    }
}

// MARK: - The eye's points

/// The eye's fixed points, placed each frame from their parameters: the iris's fibers (each point
/// at its angle and its place along the fiber) and the pupil's edge. The white, the lids, the
/// crease, the lashes, the brow and the catchlight are drawn as lines and fills.
enum EyeGeometry {
    enum Kind { case fiber, pupilEdge }
    struct P {
        let kind: Kind
        /// Fibers: angle `a`, place `u` (0 the pupil … 1 the rim); the pupil's edge: angle `a`.
        let a: Double; let u: Double; let x: Double; let y: Double; let v: Double
        let lum: Double; let dither: Double; let phase: Double
    }
    static let halfWidth = 1.25, irisRadius = 0.46

    @MainActor private static var cache: [Int: [P]] = [:]

    @MainActor static func points(count n: Int) -> [P] {
        if let c = cache[n] { return c }
        var out: [P] = []
        out.reserveCapacity(n)
        var k = 0
        func h(_ salt: Double) -> Double { OrbPoints.hash(k, salt) }
        func add(_ kind: Kind, a: Double = 0, u: Double = 0, x: Double = 0, y: Double = 0, v: Double = 0, lum: Double) {
            out.append(P(kind: kind, a: a, u: u, x: x, y: y, v: v, lum: lum, dither: h(14), phase: 2 * .pi * h(12)))
        }
        // The fibers and the pupil's edge (the lids, the lashes, the brow and the catchlight are lines).
        let fiberPoints = Int(Double(n) * 0.8)
        let fibers = max(36, fiberPoints / 14)
        for f in 0..<fibers {
            let a = 2 * Double.pi * (Double(f) + 0.4 * OrbPoints.hash(f, 21)) / Double(fibers)
            let lum = 0.65 + 0.35 * OrbPoints.hash(f, 22)
            for _ in 0..<(fiberPoints / fibers) { k += 1; add(.fiber, a: a, u: h(1), lum: lum) }
        }
        for i in 0..<max(24, n / 40) { k += 1; add(.pupilEdge, a: 2 * Double.pi * Double(i) / Double(max(24, n / 40)), lum: 0.8) }
        cache[n] = out
        return out
    }
}
