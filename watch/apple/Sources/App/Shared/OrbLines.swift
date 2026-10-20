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
    if mouth.pout > 0.001 { z += 0.02 * mouth.pout * exp(-pow((y - my) / 0.08, 2) - pow(x / 0.16, 2)) }
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
    /// the face behind it (as a line engraving shows depth, its sides rounded off), the nearer lines
    /// hiding those behind; the face in a warm light (cream where it is lit, rose and violet in its
    /// shadows), the lines around it in Wave's hues. At rest the lines breathe; listening, ribbons
    /// travel in along the lines toward the face, each line its own pitch of your voice, while it
    /// nods along; thinking, the lines undulate slowly against each other as it looks up; working,
    /// a bright line scans down the face and the lines shimmer, a ring for each step; speaking, its
    /// mouth moves with its voice and its voice flows out from either side of the face as Wave's
    /// ribbons, each line its own pitch.
    func drawContour(_ gc: inout GraphicsContext, _ box: CGSize) {
        let ph = OrbPhases(engine)
        let W = Double(box.width), H = Double(box.height)
        let cx = W / 2, cy = H / 2
        let mouth = MouthShape(engine: engine, smileBase: 1.4 + 0.2 * ph.listen - 0.15 * ph.think)
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
        // The face's own light, three levels: its shadows cool, its light warm.
        let skin: [Color] = look.color.map { c in [c.opacity(0.8), c, .white.opacity(0.95)] }
            ?? [Color(hex: 0xa78bfa), Color(hex: 0xf4a6c8), Color(hex: 0xffd6b8)]
        let lw = max(0.6, min(W, H) / 210)
        let round = StrokeStyle(lineWidth: lw, lineCap: .round, lineJoin: .round)
        var occluder = gc
        occluder.blendMode = .normal
        let dxFace = W / Double(samples) / S, dyFace = (yBot - yTop) / Double(lines - 1)
        var above = [Double](repeating: 0, count: samples + 1)
        var raw = [Double](repeating: 0, count: samples + 1), z = raw
        var glow = Path()
        for k in 0..<lines {
            let fy = yTop + (yBot - yTop) * Double(k) / Double(lines - 1)
            let fk = Double(k)
            // The relief along this line (the head turning: what stands out moves further), its
            // sides rounded off (two passes of a small smoothing), so the head reads round, not stepped.
            var before = 0.0
            for i in 0...samples {
                let fx = (W * Double(i) / Double(samples) - faceX) / S
                let fxTurned = fx - motion.turn * before * 0.5
                raw[i] = speakingRelief(fxTurned, fy, mouth) ?? bodyRelief(fxTurned, fy)
                before = raw[i]
            }
            for _ in 0..<2 {
                for i in 0...samples {
                    let a = raw[max(0, i - 2)], b = raw[max(0, i - 1)], c = raw[i], d = raw[min(samples, i + 1)], e = raw[min(samples, i + 2)]
                    z[i] = (a + 2 * b + 3 * c + 2 * d + e) / 9
                }
                swap(&raw, &z)
            }
            // Each line its own pitch of the voice and its own frequency and pace, as Wave's ribbons.
            let band = spectrum.band(at: fk / Double(lines - 1))
            let freq = 1.3 + 0.55 * Double(k % 5), pace = 0.6 + 0.25 * Double(k % 5), offset = fk * 1.3
            var pts: [CGPoint] = [], lit: [Double] = [], onFace: [Bool] = []
            pts.reserveCapacity(samples + 1); lit.reserveCapacity(samples + 1); onFace.reserveCapacity(samples + 1)
            var prevZ = 0.0
            for i in 0...samples {
                let X = W * Double(i) / Double(samples)
                let fx = (X - faceX) / S, xr = (X - faceX) / (W / 2)
                let zz = raw[i]
                let far = smoothstep(0.35, 1.1, abs(fx) / 1.6 + max(0, fy - 0.9))
                let r = (fx * fx + fy * fy).squareRoot()
                // The ribbons' shape: zero on the face, rising at its sides, fading to the screen's edges.
                let env = pow(max(0, 1 - xr * xr), 2) * smoothstep(0.16, 0.5, abs(xr))
                var ripple = ph.rest * 0.014 * sin(2.2 * fx - 0.6 * t + fk * 0.7)
                if ph.listen > 0.002 {
                    let past = hist.value(secondsAgo: max(0, 1.6 - abs(fx)) * 0.35)
                    let a = 0.02 + 0.1 * past * (0.4 + band)
                    ripple += ph.listen * a * sin(-freq * .pi * abs(xr) - 3.2 * pace * t + offset) * max(far, env)
                }
                if ph.think > 0.002 {
                    ripple += ph.think * 0.03 * sin(1.6 * fx + (k % 2 == 0 ? 0.45 : -0.45) * t + fk)
                }
                if ph.work > 0.002 {
                    ripple += ph.work * 0.012 * sin(9 * fx - 5 * t + fk * 1.3)
                }
                if ph.speak > 0.002 {
                    let past = hist.value(secondsAgo: abs(xr) * 0.5)
                    let a = 0.025 + 0.14 * (0.35 + 0.65 * past) * (0.3 + band)
                    ripple += ph.speak * a * env * sin(freq * .pi * abs(xr) - 3.2 * pace * t + offset)
                }
                for p in work.pulses where p.tone != .failure {
                    let fade = max(0, 1 - p.age / 1.6), ring = (r - p.age * 0.9) / 0.1
                    ripple += 0.035 * p.strength * fade * exp(-ring * ring)
                }
                pts.append(CGPoint(x: X, y: faceY + fy * S - zz * lift - ripple * S))
                // Its light: the relief's slope there toward the light (the features read by it), soft.
                let zx = i == 0 ? 0 : (zz - prevZ) / dxFace
                let zy = k == 0 ? 0 : (zz - above[i]) / dyFace
                prevZ = zz; above[i] = zz
                let nn = 1 / (zx * zx + zy * zy + 1).squareRoot()
                let l = max(0, (-zx * L.x - zy * L.y + L.z) * nn)
                let face = zz > 0.03
                lit.append(face ? 0.45 + 0.65 * pow(l, 1.4) : 0.75)
                onFace.append(face)
            }
            // Hide what lies behind this line, then draw it.
            var under = Path()
            under.move(to: CGPoint(x: 0, y: H)); for p in pts { under.addLine(to: p) }; under.addLine(to: CGPoint(x: W, y: H)); under.closeSubpath()
            occluder.fill(under, with: .color(.black))
            // The line: around the face in the hues, on the face in its warm light (three levels).
            var back = Path(), faceParts = [Path](repeating: Path(), count: 3)
            for i in 1..<pts.count {
                if onFace[i] && onFace[i - 1] {
                    let b = (lit[i] + lit[i - 1]) / 2
                    let lv = b > 0.82 ? 2 : b > 0.5 ? 1 : 0
                    faceParts[lv].move(to: pts[i - 1]); faceParts[lv].addLine(to: pts[i])
                    if lv == 2 { glow.move(to: pts[i - 1]); glow.addLine(to: pts[i]) }
                } else {
                    back.move(to: pts[i - 1]); back.addLine(to: pts[i])
                }
            }
            let scan = ph.work * exp(-pow((fy - scanY) / 0.06, 2))
            let edge = 0.55 + 0.45 * (1 - smoothstep(0.9, 1.25, abs(fy + 0.05)))
            gc.opacity = min(1, 0.7 * edge + 0.5 * scan)
            gc.stroke(back, with: shading, style: round)
            for (lv, a) in [(0, 0.45), (1, 0.75), (2, 1.0)] where !faceParts[lv].isEmpty {
                gc.opacity = min(1, a * edge + 0.5 * scan)
                gc.stroke(faceParts[lv], with: .color(skin[lv]), style: round)
            }
            gc.opacity = 1
        }
        // A soft warm glow over the face's lit lines (one blurred layer for all of them).
        gc.drawLayer { layer in
            layer.addFilter(.blur(radius: lw * 2))
            layer.stroke(glow, with: .color(skin[2].opacity(0.3)), lineWidth: lw * 2.2)
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
        let press = 0.62 + 0.1 * ph.speak * ph.loud + 0.08 * ph.listen * (0.5 + level) - 0.06 * ph.think + 0.015 * sin(t * 0.9)
        let plane = 0.2
        let S = min(W * 0.5, H * 0.52)
        let span = 1.6                                     // the fabric reaches ±span face units across
        // The voice's three ribbons: low, middle and high pitches, each its own frequency and pace.
        let bands = [spectrum.band(at: 0.1), spectrum.band(at: 0.5), spectrum.band(at: 0.9)]
        let harmonic = [6.5, 9.5, 13.0], paces = [0.8, 1.0, 1.25]
        func height(_ fx: Double, _ fy: Double) -> Double {
            let x = fx - motion.dx, y = fy - motion.dy - 0.18
            let z0 = speakingRelief(x, y, mouth) ?? 0
            let shiftX = motion.turn * z0 * 0.5
            let zf = abs(shiftX) < 0.002 ? (z0 > 0 ? z0 : bodyRelief(x, y) * 0.8)
                : (speakingRelief(x - shiftX, y, mouth) ?? bodyRelief(x - shiftX, y) * 0.8)
            // The fabric drapes over what pushes through it (a soft maximum with its plane).
            let k = 0.05, d = (zf * press - plane) / k
            var h = k * (d > 20 ? d : log(1 + exp(d)))
            let r = (fx * fx + fy * fy).squareRoot()
            let reach = smoothstep(0.75, 1.25, r) * (1 - smoothstep(1.5, 2.0, r))
            h += ph.rest * 0.01 * sin(5 * r - 1.2 * t) * reach
            if ph.listen > 0.002 && reach > 0 {
                // Your voice: ribbons of three pitches running in toward the face, as Wave's.
                let past = hist.value(secondsAgo: max(0, 2 - r) * 0.35)
                var v = 0.0
                for m in 0..<3 { v += (0.006 + 0.05 * past * (0.3 + bands[m])) * sin(harmonic[m] * r + 3.2 * paces[m] * t + Double(m) * 1.3) }
                h += ph.listen * v * reach
            }
            if ph.think > 0.002 { h += ph.think * 0.04 * sin(2.4 * r - 0.8 * t) * smoothstep(0.6, 1.2, r) }
            if ph.work > 0.002 {
                let th = atan2(fy, fx)
                h += ph.work * 0.05 * cos(2 * (th - t * 2.6) + 7 * r) * reach
            }
            let dm = ph.speak > 0.002 ? (pow(fx - motion.dx, 2) + pow(fy - motion.dy - 0.18 - FaceGeometry.mouthY, 2)).squareRoot() : 0
            if dm > 0.95 && dm < 2.3 {
                // Its voice: ribbons of three pitches leaving its lips across the fabric, as Wave's.
                let past = hist.value(secondsAgo: dm * 0.3)
                var v = 0.0
                for m in 0..<3 { v += (0.008 + 0.06 * past * (0.3 + bands[m])) * sin(harmonic[m] * dm - 3.2 * paces[m] * t + Double(m) * 1.3) }
                h += ph.speak * v * smoothstep(0.95, 1.3, dm) * (1 - smoothstep(1.8, 2.3, dm))
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
        // The fabric once per frame on one grid (its lines are every other row and column), lit from
        // the upper left in front: each segment in one of five brightness levels.
        // As fine as the size drawn needs (a thumbnail: a coarse grid).
        let n = max(41, min(121, Int(min(W, H) * 0.5) | 1)), every = 2
        var hs = [Double](repeating: 0, count: n * n)
        for j in 0..<n {
            let fy = (-span + 2 * span * Double(j) / Double(n - 1)) * 0.95
            for i in 0..<n { hs[j * n + i] = height(-span + 2 * span * Double(i) / Double(n - 1), fy) }
        }
        // One soft pass over the fabric (across, then down): the face's outline drapes round, never
        // stepped from one cell to the next.
        var tmp = hs
        for j in 0..<n { for i in 1..<(n - 1) { tmp[j * n + i] = 0.25 * hs[j * n + i - 1] + 0.5 * hs[j * n + i] + 0.25 * hs[j * n + i + 1] } }
        for j in 1..<(n - 1) { for i in 0..<n { hs[j * n + i] = 0.25 * tmp[(j - 1) * n + i] + 0.5 * tmp[j * n + i] + 0.25 * tmp[(j + 1) * n + i] } }
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
            ?? [Color(hex: 0x6366f1).opacity(0.2), Color(hex: 0x8b7cf6).opacity(0.4), Color(hex: 0xd99ad8).opacity(0.62),
                Color(hex: 0xffcdb5).opacity(0.86), Color(hex: 0xfff4e8)]
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
