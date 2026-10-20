import SwiftUI

// Two portraits in lines of light, made from the Face's relief: Contour (after Wave: the face
// raised in ribbons of light across the screen, each line hiding those behind it) and Membrane
// (after Well: the fabric of the Well's grid with a face pressing through it from behind, lit by
// its own slopes). Both speak with their mouth (the jaw drops, the lips part, rounder or wider with
// the vowel), nod along with your voice as they listen, and keep Wave's and Well's answers to the
// voice around the face. Every motion runs at a fixed pace; the phases blend how much of each shows.

/// The face's relief with its mouth now: the jaw dropped below the mouth, the opening between the
/// lips sunk, narrower on a round vowel. Face units (as `FaceGeometry`), nil outside the head.
private func speakingRelief(_ x: Double, _ y: Double, _ mouth: MouthShape) -> Double? {
    let my = FaceGeometry.mouthY
    var sx = x, sy = y
    if abs(y - my) < 0.4 {
        let near = exp(-pow((y - my) / 0.12, 2)) * exp(-pow(x / 0.3, 2))
        sx = x / max(0.6, 1 - (1 - mouth.width) * near)
        sy = y - mouth.jaw(x, y)
    }
    guard var z = ImprintGeometry.grid.at(sx, sy) else { return nil }
    if mouth.open > 0.04 {
        let gap = 0.12 * mouth.open
        let inside = exp(-pow(x / (0.17 * mouth.width), 2) - pow((y - my - gap * 0.6) / (gap + 0.004), 2))
        z -= 0.2 * inside
    }
    z += 0.02 * mouth.pout * exp(-pow((y - my) / 0.08, 2) - pow(x / 0.16, 2))
    return z
}

/// The neck and shoulders under the head, a soft rise (face units).
private func bodyRelief(_ x: Double, _ y: Double) -> Double {
    var z = 0.0
    if y > 0.4 { z = max(z, 0.32 * max(0, 1 - pow(x / 0.21, 2)).squareRoot() * smoothstep(0.4, 0.62, y)) }
    if y > 0.82 {
        let sw = 0.32 + 0.9 * smoothstep(0.82, 1.2, y)
        z = max(z, 0.3 * max(0, 1 - pow(x / sw, 2)).squareRoot() * smoothstep(0.82, 1.05, y))
    }
    return z
}

extension OrbCanvas {

    /// How the head moves in either portrait: a breath, a nod along with your voice and with its
    /// own phrasing, a turn toward you as you speak, a look up as it thinks.
    private func portraitMotion(_ ph: OrbPhases, _ mouth: MouthShape) -> (dx: Double, dy: Double, turn: Double) {
        let level = engine.history.value(secondsAgo: 0.05)
        let dy = 0.01 * sin(t * 1.25) + 0.035 * ph.listen * level * sin(t * 4.3) + 0.03 * mouth.open * sin(t * 6.1) - 0.04 * ph.think
        let dx = 0.03 * sin(t * 0.29) + 0.05 * ph.think - 0.04 * ph.listen
        let turn = 0.08 * sin(t * 0.27) - 0.22 * ph.listen + 0.1 * ph.think
        return (dx, dy, turn)
    }

    // MARK: Contour

    /// A face raised in lines of light: ribbons across the screen, each lifted by the relief of
    /// the face behind it (as a line engraving shows depth), the nearer lines hiding those behind.
    /// At rest the lines breathe; listening, waves travel in along them from the edges carrying your
    /// voice while it nods along; thinking, the lines undulate slowly against each other as it
    /// looks up; working, a bright line scans down the face and the lines shimmer, a ring for each
    /// step; speaking, its mouth moves with its voice and the words leave its lips as waves along
    /// the lines.
    func drawContour(_ gc: inout GraphicsContext, _ box: CGSize) {
        let ph = OrbPhases(engine)
        let W = Double(box.width), H = Double(box.height)
        let cx = W / 2, cy = H / 2
        let mouth = MouthShape(engine: engine, smileBase: 1.3 + 0.2 * ph.listen - 0.2 * ph.think)
        let motion = portraitMotion(ph, mouth)
        let S = H * 0.5                                   // screen points per face unit
        let lift = 0.3 * S                                // how high a unit of depth raises a line
        let faceX = cx + motion.dx * S, faceY = cy + (0.12 + motion.dy) * S
        let hist = engine.history, spectrum = ph.spectrum
        let lines = 46, samples = 104
        let L = (x: -0.35, y: -0.45, z: 0.82)            // the light: upper left, in front
        let yTop = -1.25, yBot = 1.2
        let scanY = -1.1 + 1.9 * fract(t * 0.35)
        let colors: [Color] = look.color.map { c in [c.opacity(0.7), c, .white.opacity(0.9), c, c.opacity(0.7)] }
            ?? [Color(hex: 0x38bdf8), Color(hex: 0x6366f1), Color(hex: 0xa855f7), Color(hex: 0xf472b6), Color(hex: 0xfb923c)]
        let shading = GraphicsContext.Shading.linearGradient(Gradient(colors: colors), startPoint: CGPoint(x: 0, y: cy), endPoint: CGPoint(x: W, y: cy))
        let lw = max(0.6, min(W, H) / 210)
        var occluder = gc
        occluder.blendMode = .normal
        for k in 0..<lines {
            let fy = yTop + (yBot - yTop) * Double(k) / Double(lines - 1)
            let fk = Double(k)
            var pts: [CGPoint] = [], lit: [Double] = []
            pts.reserveCapacity(samples + 1); lit.reserveCapacity(samples + 1)
            for i in 0...samples {
                let X = W * Double(i) / Double(samples)
                let fx = (X - faceX) / S
                // The head turns: what stands out moves further.
                let z0 = speakingRelief(fx, fy, mouth) ?? bodyRelief(fx, fy)
                let fxTurned = fx - motion.turn * z0 * 0.5
                let z = speakingRelief(fxTurned, fy, mouth) ?? bodyRelief(fxTurned, fy)
                let far = smoothstep(0.35, 1.1, abs(fx) / 1.6 + max(0, fy - 0.9))
                let r = (fx * fx + fy * fy).squareRoot()
                var ripple = ph.rest * 0.014 * sin(2.2 * fx - 0.6 * t + fk * 0.7)
                if ph.listen > 0.002 {
                    let past = hist.value(secondsAgo: max(0, 1.6 - abs(fx)) * 0.35)
                    let a = 0.02 + 0.09 * past * (0.5 + spectrum.band(at: fk / Double(lines - 1)))
                    ripple += ph.listen * a * sin(7 * abs(fx) + 3.2 * t + fk * 0.4) * far
                }
                if ph.think > 0.002 {
                    ripple += ph.think * 0.03 * sin(1.6 * fx + (k % 2 == 0 ? 0.45 : -0.45) * t + fk)
                }
                if ph.work > 0.002 {
                    ripple += ph.work * 0.012 * sin(9 * fx - 5 * t + fk * 1.3)
                }
                if ph.speak > 0.002 {
                    let dm = ((fx * fx) + pow(fy - FaceGeometry.mouthY, 2)).squareRoot()
                    let past = hist.value(secondsAgo: dm * 0.3)
                    let a = 0.02 + 0.1 * past * (0.5 + spectrum.band(at: min(1, dm / 1.6)))
                    ripple += ph.speak * a * sin(9 * dm - 3.2 * t) * smoothstep(0.25, 0.55, dm)
                }
                for p in work.pulses where p.tone != .failure {
                    let fade = max(0, 1 - p.age / 1.6), ring = (r - p.age * 0.9) / 0.1
                    ripple += 0.035 * p.strength * fade * exp(-ring * ring)
                }
                pts.append(CGPoint(x: X, y: faceY + fy * S - z * lift - ripple * S))
                // Its light: the relief's slope there toward the light (the features read by it).
                let e = 0.012
                let zx = ((speakingRelief(fxTurned + e, fy, mouth) ?? bodyRelief(fxTurned + e, fy)) - (speakingRelief(fxTurned - e, fy, mouth) ?? bodyRelief(fxTurned - e, fy))) / (2 * e)
                let zy = ((speakingRelief(fxTurned, fy + e, mouth) ?? bodyRelief(fxTurned, fy + e)) - (speakingRelief(fxTurned, fy - e, mouth) ?? bodyRelief(fxTurned, fy - e))) / (2 * e)
                let nn = 1 / (zx * zx + zy * zy + 1).squareRoot()
                let l = max(0, (-zx * L.x - zy * L.y + L.z) * nn)
                lit.append(z > 0.02 ? 0.25 + 0.95 * pow(l, 2.2) : 0.75)
            }
            // Hide what lies behind this line, then draw it.
            var under = Path()
            under.move(to: CGPoint(x: 0, y: H)); for p in pts { under.addLine(to: p) }; under.addLine(to: CGPoint(x: W, y: H)); under.closeSubpath()
            occluder.fill(under, with: .color(.black))
            // The line in three levels of light, the brightest with a glow.
            var parts = [Path](repeating: Path(), count: 3)
            for i in 1..<pts.count {
                let b = (lit[i] + lit[i - 1]) / 2
                let lv = b > 0.85 ? 2 : b > 0.5 ? 1 : 0
                parts[lv].move(to: pts[i - 1]); parts[lv].addLine(to: pts[i])
            }
            let scan = ph.work * exp(-pow((fy - scanY) / 0.06, 2))
            let edge = 0.55 + 0.45 * (1 - smoothstep(0.9, 1.25, abs(fy + 0.05)))
            gc.drawLayer { layer in
                layer.addFilter(.blur(radius: lw * 2.5))
                layer.opacity = 0.45 * edge + 0.6 * scan
                layer.stroke(parts[2], with: shading, lineWidth: lw * 2.2)
            }
            for (lv, a) in [(0, 0.32), (1, 0.7), (2, 1.0)] {
                gc.opacity = min(1, a * edge + 0.5 * scan)
                gc.stroke(parts[lv], with: shading, lineWidth: lw * (lv == 2 ? 1.2 : 1))
            }
            gc.opacity = 1
        }
    }

    // MARK: Membrane

    /// A face pressing through the Well's fabric from behind: the grid of fine lines takes the shape
    /// of the face where it touches (the forehead, the brows, the nose, the cheeks, the lips, the
    /// chin), lit by its own slopes. At rest it presses lightly and breathes; listening, it presses
    /// closer with your voice and nods along while ripples run in from the edges; thinking, it
    /// draws back and the fabric swells slowly; working, the fabric carries a two-armed spiral of
    /// waves and a ring for each step; speaking, it presses forward with its voice, its mouth moves
    /// with the words and waves leave its lips across the fabric.
    func drawMembrane(_ gc: inout GraphicsContext, _ box: CGSize) {
        let ph = OrbPhases(engine)
        let W = Double(box.width), H = Double(box.height)
        let cx = W / 2, cy = H / 2
        let mouth = MouthShape(engine: engine, smileBase: 1.1 + 0.2 * ph.listen)
        let motion = portraitMotion(ph, mouth)
        let level = engine.history.value(secondsAgo: 0.05)
        let hist = engine.history, spectrum = ph.spectrum
        // How far the face pushes through: past the fabric's plane, only what stands out shows.
        let press = 0.62 + 0.1 * ph.speak * ph.loud + 0.08 * ph.listen * (0.5 + level) - 0.22 * ph.think + 0.015 * sin(t * 0.9)
        let plane = 0.2
        let S = min(W * 0.5, H * 0.52)
        let span = 1.6                                     // the fabric reaches ±span face units across
        func height(_ fx: Double, _ fy: Double) -> Double {
            let x = fx - motion.dx, y = fy - motion.dy - 0.18
            let z0 = speakingRelief(x, y, mouth) ?? 0
            let xt = x - motion.turn * z0 * 0.5
            let zf = speakingRelief(xt, y, mouth) ?? bodyRelief(xt, y) * 0.8
            // The fabric drapes over what pushes through it (a soft maximum with its plane).
            let k = 0.05, d = (zf * press - plane) / k
            var h = k * (d > 20 ? d : log(1 + exp(d)))
            let r = (fx * fx + fy * fy).squareRoot()
            let reach = smoothstep(0.75, 1.25, r) * (1 - smoothstep(1.5, 2.0, r))
            h += ph.rest * 0.01 * sin(5 * r - 1.2 * t) * reach
            if ph.listen > 0.002 {
                let past = hist.value(secondsAgo: max(0, 2 - r) * 0.35)
                h += ph.listen * (0.02 + 0.09 * past * (0.5 + spectrum.band(at: 1 - r / 2))) * sin(9 * r + 3.2 * t) * reach
            }
            if ph.think > 0.002 { h += ph.think * 0.04 * sin(2.4 * r - 0.8 * t) * smoothstep(0.6, 1.2, r) }
            if ph.work > 0.002 {
                let th = atan2(fy, fx)
                h += ph.work * 0.05 * cos(2 * (th - t * 2.6) + 7 * r) * reach
            }
            if ph.speak > 0.002 {
                let dm = (pow(fx - motion.dx, 2) + pow(fy - motion.dy - 0.18 - FaceGeometry.mouthY, 2)).squareRoot()
                let past = hist.value(secondsAgo: dm * 0.3)
                h += ph.speak * (0.02 + 0.1 * past * (0.5 + spectrum.band(at: min(1, dm / 1.8)))) * sin(9 * dm - 3.2 * t) * smoothstep(0.6, 0.95, dm)
            }
            for p in work.pulses where p.tone != .failure {
                let fade = max(0, 1 - p.age / 1.6), ring = (r - p.age * 1.1) / 0.1
                h += 0.04 * p.strength * fade * exp(-ring * ring)
            }
            return h
        }
        // The fabric seen a little from the side and below, so what stands out reads as depth.
        let yaw = 0.32 + 0.06 * sin(t * 0.07), cY = cos(yaw), sY = sin(yaw)
        func project(_ fx: Double, _ fy: Double, _ h: Double) -> CGPoint {
            let x = fx * cY + h * sY, z = -fx * sY + h * cY
            let f = 3.2 / (3.2 - z)
            return CGPoint(x: cx + x * f * S, y: cy + fy * f * S)
        }
        // The fabric once per frame on one grid (its lines are every third row and column), lit from
        // the upper left in front: each segment in one of five brightness levels.
        let n = 121, every = 2
        var hs = [Double](repeating: 0, count: n * n)
        for j in 0..<n {
            let fy = (-span + 2 * span * Double(j) / Double(n - 1)) * 0.95
            for i in 0..<n { hs[j * n + i] = height(-span + 2 * span * Double(i) / Double(n - 1), fy) }
        }
        let cell = 2 * span / Double(n - 1)
        let L = (x: -0.35, y: -0.45, z: 0.82)
        var levels = [Path](repeating: Path(), count: 5)
        var points = [CGPoint](repeating: .zero, count: n * n), bright = [Int](repeating: 0, count: n * n)
        for j in 0..<n {
            for i in 0..<n {
                let fx = -span + cell * Double(i), fy = (-span + cell * Double(j)) * 0.95
                let h = hs[j * n + i]
                let hx = (hs[j * n + min(n - 1, i + 1)] - hs[j * n + max(0, i - 1)]) / (2 * cell)
                let hy = (hs[min(n - 1, j + 1) * n + i] - hs[max(0, j - 1) * n + i]) / (2 * cell * 0.95)
                let nn = 1 / (hx * hx + hy * hy + 1).squareRoot()
                let lit = max(0, (-hx * L.x - hy * L.y + L.z) * nn)
                let r = (fx * fx + fy * fy).squareRoot()
                let fade = 1 - smoothstep(1.35, 1.75, r)
                let b = (0.08 + 1.05 * pow(lit, 2.4) * (0.3 + 0.7 * min(1, h / 0.1 + 0.2))) * fade
                points[j * n + i] = project(fx, fy, h)
                bright[j * n + i] = fade > 0.02 ? min(4, max(0, Int(b * 5))) : -1
            }
        }
        func segment(_ a: Int, _ b: Int) {
            guard bright[a] >= 0, bright[b] >= 0 else { return }
            let lv = (bright[a] + bright[b] + 1) / 2
            levels[lv].move(to: points[a]); levels[lv].addLine(to: points[b])
        }
        for j in stride(from: 0, to: n, by: every) { for i in 0..<(n - 1) { segment(j * n + i, j * n + i + 1) } }
        for i in stride(from: 0, to: n, by: every) { for j in 0..<(n - 1) { segment(j * n + i, (j + 1) * n + i) } }
        let tint = look.color
        let pal: [Color] = tint.map { c in [c.opacity(0.18), c.opacity(0.35), c.opacity(0.6), c.opacity(0.85), .white.opacity(0.95)] }
            ?? [Color(hex: 0x38bdf8).opacity(0.18), Color(hex: 0x818cf8).opacity(0.38), Color(hex: 0xa78bfa).opacity(0.62),
                Color(hex: 0xe9d5ff).opacity(0.85), Color(hex: 0xfdf4ff)]
        let lw = max(0.5, min(W, H) / 260)
        gc.drawLayer { layer in
            layer.addFilter(.blur(radius: lw * 3))
            layer.stroke(levels[3], with: .color(pal[3].opacity(0.5)), lineWidth: lw * 2)
            layer.stroke(levels[4], with: .color(pal[4].opacity(0.6)), lineWidth: lw * 2)
        }
        for b in 0..<5 { gc.stroke(levels[b], with: .color(pal[b]), lineWidth: lw) }
    }
}

@inline(__always) private func fract(_ x: Double) -> Double { x - x.rounded(.down) }
