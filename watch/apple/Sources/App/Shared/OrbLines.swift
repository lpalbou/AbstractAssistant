import SwiftUI

// Two portraits in lines of light: Contour (after Wave, from the Face's relief: the face raised in
// ribbons of light across the screen, each line hiding those behind it) and Membrane (a soft,
// smiling face of its own pressing into a curtain of silk threads from behind, lit where the silk
// stretches). Both speak with their mouth (the jaw drops, the lips part, rounder or wider with the
// vowel), nod along with your voice as they listen, and answer the voice around the face. Every motion runs at a fixed pace; the phases blend how much of each shows.

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

    /// A face pressing softly into a curtain of silk from behind: fine threads of light hanging
    /// side by side that the face lifts and bends as it pushes through (they spread where the
    /// fabric turns to the light and crowd where it turns away, so the face is drawn by the threads
    /// themselves), lit where the silk stretches over the face (the brow, the nose, the cheeks, the
    /// lips, the chin), a warm light behind it. A soft, smiling face, its eyes closed. At rest it
    /// barely touches the silk and breathes; listening, it presses closer with your voice and the
    /// threads bend in toward it while ripples run in; thinking, it draws back, faint, and the silk
    /// sways in slow waves; working, the threads tighten and ripples run out from the face, one
    /// for each step; speaking, its mouth pushes with its voice, its lips' press lit, and ribbons
    /// of light leave its lips along the threads.
    func drawMembrane(_ gc: inout GraphicsContext, _ box: CGSize) {
        let ph = OrbPhases(engine)
        let W = Double(box.width), H = Double(box.height)
        let cx = W / 2, cy = H / 2
        let mouth = MouthShape(engine: engine, smileBase: 1.2 + 0.2 * ph.listen)
        let motion = portraitMotion(ph, mouth)
        let hist = engine.history, level = ph.level
        let S = min(W * 0.5, H * 0.52)                     // screen points per face unit
        let faceX = motion.dx, faceY = motion.dy + 0.08    // the face's centre (it sits a little low)
        let my = FaceGeometry.mouthY
        // How far the face presses into the silk, how soft the silk is (tighter at work), how
        // much of the face shows (thinking, it draws back).
        let press = 0.86 + 0.03 * sin(t * 0.9) + ph.listen * (0.1 + 0.25 * level) - 0.04 * ph.think
            + ph.speak * (0.06 + 0.1 * ph.loud) + 0.05 * ph.work
        let plane = 0.13, soft = 0.05 - 0.02 * ph.work
        let faceAmp = 1 - 0.45 * ph.think
        let mouthPush = ph.speak * (0.01 + 0.05 * ph.loud)
        // The silk on one grid: each column a thread, sampled down its length.
        let nx = max(21, min(105, Int(W * 0.24) | 1)), ny = max(25, min(101, Int(H * 0.25)))
        let halfX = W / 2 / S + 0.12, halfY = H / 2 / S + 0.06
        let dx = 2 * halfX / Double(nx - 1), dy = 2 * halfY / Double(ny - 1)
        var face = [Double](repeating: 0, count: nx * ny), waves = face, extra = face
        for j in 0..<ny {
            let fy = -halfY + dy * Double(j)
            for i in 0..<nx {
                let fx = -halfX + dx * Double(i)
                let c = j * nx + i
                let x = fx - faceX, y = fy - faceY
                // The face, turned a little (what stands out moves further), its mouth now.
                let z0 = MembraneFace.z(x, y, mouth)
                var z = abs(motion.turn) < 0.002 ? z0 : MembraneFace.z(x - motion.turn * z0 * 0.6, y, mouth)
                if mouthPush > 0.001 {
                    let lips = exp(-pow(x / 0.19, 2) - pow((y - my) / 0.08, 2))
                    z += mouthPush * lips
                    extra[c] += ph.speak * (0.06 + 0.3 * ph.loud) * lips       // the lips' press, lit
                }
                // The silk drapes over what pushes into it (a soft maximum with its plane).
                let e = (press * z - plane) / soft
                face[c] = faceAmp * soft * (e > 20 ? e : log(1 + exp(e)))
                var h = 0.0, light = 0.0
                let r = (x * x + 0.75 * pow(y + 0.12, 2)).squareRoot()     // from the face's centre
                let off = smoothstep(0.5, 0.85, r)                           // off the face
                // Its breath: a gentle sway down the silk (less of it while the threads are tight).
                h += 0.008 * (1 - 0.7 * ph.work) * sin(2.1 * fx + 1.3 * fy - 0.9 * t)
                if ph.think > 0.002 {
                    h += ph.think * (0.06 * sin(1.7 * fx + 0.6 * fy - 0.55 * t) + 0.035 * sin(2.6 * fy - 1.1 * fx + 0.4 * t))
                }
                if ph.listen > 0.002 {
                    // Your voice: ripples running in toward the face.
                    let past = hist.value(secondsAgo: max(0, 1.8 - r) * 0.4)
                    let w = sin(10 * r + 4.5 * t)
                    h += ph.listen * (0.005 + 0.035 * past) * w * off
                    light += ph.listen * (0.08 + 0.4 * past) * pow(max(0, w), 4) * off
                }
                if ph.work > 0.002 { h += ph.work * 0.006 * sin(11 * r - 5 * t) * off }
                for p in work.pulses where p.tone != .failure {
                    // Each step: a ripple running out from the face.
                    let fade = max(0, 1 - p.age / 1.6), ring = (r - 0.45 - p.age * 1.0) / 0.06
                    let k = p.strength * fade * exp(-ring * ring) * off
                    h += 0.035 * k; light += 0.4 * k
                }
                if ph.speak > 0.002 {
                    // Its voice: ribbons of light leaving its lips along the threads.
                    let dm = (x * x + pow(y - my, 2)).squareRoot()
                    let past = hist.value(secondsAgo: dm * 0.35)
                    let w = sin(8 * dm - 4.5 * t)
                    let reach = smoothstep(0.2, 0.5, dm) * (1 - smoothstep(1.0, 1.6, dm)) * off
                    h += ph.speak * (0.003 + 0.012 * past) * w * reach
                    light += ph.speak * (0.15 + 0.6 * past) * pow(max(0, w), 8) * reach
                }
                // A slow sheen across the silk.
                light += 0.05 * sin(2.6 * fx + 1.2 * fy - 0.3 * t) * off
                waves[c] = h; extra[c] += light
            }
        }
        // The silk bridges the face's hollows and falls softly from its outline: the face's push,
        // blurred wide, under it.
        var wide = face, tmp = face
        for _ in 0..<3 {
            for j in 0..<ny {
                let row = j * nx
                for i in 0..<nx {
                    tmp[row + i] = (wide[row + max(0, i - 2)] + 4 * wide[row + max(0, i - 1)] + 6 * wide[row + i]
                        + 4 * wide[row + min(nx - 1, i + 1)] + wide[row + min(nx - 1, i + 2)]) / 16
                }
            }
            for j in 0..<ny {
                for i in 0..<nx {
                    wide[j * nx + i] = (tmp[max(0, j - 2) * nx + i] + 4 * tmp[max(0, j - 1) * nx + i] + 6 * tmp[j * nx + i]
                        + 4 * tmp[min(ny - 1, j + 1) * nx + i] + tmp[min(ny - 1, j + 2) * nx + i]) / 16
                }
            }
        }
        // The threads lie on the silk's broad shape (they bend round the head and the nose, never
        // squiggle over the lips); its finer forms show in its light.
        var hs = face, lay = face
        for c in 0..<(nx * ny) {
            face[c] = max(face[c], 0.8 * wide[c])
            hs[c] = face[c] + waves[c]
            lay[c] = 0.35 * face[c] + 0.65 * wide[c] + waves[c]
        }
        // Each point of each thread on the screen and how bright: a soft light from in front and a
        // little above, brighter where the silk is lifted and where it stretches over a rise.
        let L = (x: -0.25, y: -0.4, z: 0.88)
        let levels = 10
        var pts = [CGPoint](repeating: .zero, count: nx * ny), bright = [Double](repeating: 0, count: nx * ny)
        let pull = ph.listen * (0.03 + 0.09 * level)
        let side = -0.45 - 0.05 * sin(t * 0.11)
        for j in 0..<ny {
            let fy = -halfY + dy * Double(j)
            for i in 0..<nx {
                let fx = -halfX + dx * Double(i)
                let c = j * nx + i, h = hs[c]
                let l = hs[j * nx + max(0, i - 1)], rr = hs[j * nx + min(nx - 1, i + 1)]
                let u = hs[max(0, j - 1) * nx + i], dn = hs[min(ny - 1, j + 1) * nx + i]
                let hx = (rr - l) / (2 * dx), hy = (dn - u) / (2 * dy)
                let nn = 1 / (hx * hx + hy * hy + 1).squareRoot()
                let lit = max(0, (-hx * L.x - hy * L.y + L.z) * nn)
                let curve = (rr + l - 2 * h) / (dx * dx) + (dn + u - 2 * h) / (dy * dy)
                let convex = max(0, -curve), hollow = max(0, curve)
                let lifted = smoothstep(0.004, 0.07 * faceAmp, face[c])
                let wrap = 0.35 + 0.65 * lit                                 // a soft light: no deep shadows
                let b = 0.1 + 0.4 * max(0, lit - L.z) + lifted * (0.35 + 0.65 * faceAmp) * (0.22 + 0.45 * wrap * wrap + 0.3 * min(1, convex / 50) - 0.4 * min(1, hollow / 50)) + extra[c]
                // The threads bend in toward the face as it listens.
                var px = fx, py = fy
                let ox = fx - faceX, oy = fy - faceY, orr = (ox * ox + oy * oy).squareRoot()
                if pull > 0.001 && orr > 0.01 {
                    let k = pull * exp(-pow((orr - 0.95) / 0.45, 2))
                    px -= ox / orr * k; py -= oy / orr * k
                }
                // Thinking, the silk sways slowly from side to side.
                if ph.think > 0.002 { px += ph.think * 0.035 * sin(1.4 * fy + 0.6 * fx - 0.5 * t) }
                // Seen a little from the side: what is lifted shifts and spreads.
                let hl = lay[c], f = 3.0 / (3.0 - hl)
                pts[c] = CGPoint(x: cx + (px + side * hl) * f * S, y: cy + (py - 0.12 * hl) * f * S)
                bright[c] = b
            }
        }
        // Where the threads crowd together each carries less light, where they spread more (the
        // silk's light is the same, shared by more or fewer threads).
        var lv = [Int](repeating: 0, count: nx * ny)
        for j in 0..<ny {
            for i in 0..<nx {
                let c = j * nx + i
                let a = pts[j * nx + max(0, i - 1)].x, b = pts[j * nx + min(nx - 1, i + 1)].x
                let spread = Double(b - a) / (Double(min(nx - 1, i + 1) - max(0, i - 1)) * dx * S)
                lv[c] = min(levels - 1, max(0, Int(bright[c] * min(1.15, max(0.35, spread)) * Double(levels))))
            }
        }
        // Each thread in runs of one level of light (a run is one continuous line: no seams).
        var threads = [Path](repeating: Path(), count: levels)
        for i in 0..<nx {
            var run = -1
            for j in 0..<(ny - 1) {
                let a = j * nx + i, b = a + nx, k = (lv[a] + lv[b] + 1) / 2
                if k != run { threads[k].move(to: pts[a]); run = k }
                threads[k].addLine(to: pts[b])
            }
        }
        let pal: [Color] = look.color.map { c in [c.opacity(0.22), c.opacity(0.4), c.opacity(0.62), c.opacity(0.85), .white.opacity(0.95)] }
            ?? [Color(hex: 0x5b5bd6).opacity(0.4), Color(hex: 0x8b7cf6).opacity(0.6), Color(hex: 0xd99ad8).opacity(0.8),
                Color(hex: 0xffcdb5).opacity(0.92), Color(hex: 0xfff6ec)]
        let ramp: [Color] = (0..<levels).map { k in
            let u = Double(k) / Double(levels - 1) * 4, lo = min(3, Int(u))
            return pal[lo].mix(with: pal[lo + 1], by: u - Double(lo))
        }
        let lw = max(0.45, min(W, H) / 400)
        // The warm light of the face behind the silk.
        let fc = CGPoint(x: cx + faceX * S, y: cy + (faceY - 0.12) * S), gr = 0.9 * S
        let warmth = max(0, min(1, faceAmp * (press - 0.3) / 0.6))
        gc.fill(Path(ellipseIn: CGRect(x: fc.x - gr, y: fc.y - gr * 1.1, width: 2 * gr, height: 2.2 * gr)),
                with: .radialGradient(Gradient(colors: [pal[3].opacity(0.12 * warmth), pal[2].opacity(0.04 * warmth), .clear]),
                                      center: fc, startRadius: 0, endRadius: gr * 1.1))
        // The silk with its glow, fading out softly toward the screen's round edge.
        gc.drawLayer { silk in
            silk.drawLayer { layer in
                layer.addFilter(.blur(radius: lw * 3))
                for k in 6..<levels { layer.stroke(threads[k], with: .color(ramp[k].opacity(0.45)), lineWidth: lw * 2.6) }
            }
            for k in 0..<levels { silk.stroke(threads[k], with: .color(ramp[k]), lineWidth: lw) }
            silk.blendMode = .destinationIn
            silk.fill(Path(CGRect(x: 0, y: 0, width: W, height: H)),
                      with: .radialGradient(Gradient(stops: [.init(color: .white, location: 0), .init(color: .white, location: 0.6),
                                                             .init(color: .clear, location: 1)]),
                                            center: CGPoint(x: cx, y: cy), startRadius: 0, endRadius: 0.58 * max(W, H)))
        }
    }
}

/// Membrane's face: a soft, smiling face (round cheeks lifted by the smile, the eyes closed and
/// content under round lids, a gentle brow, a short soft nose, full lips curving up), computed
/// once on a fine grid and read back by interpolation; 0 outside the head. Face units, y down.
private enum MembraneFace {
    static func relief(_ x: Double, _ y: Double) -> Double {
        let sy = (y + 0.15) / 0.8
        let w = 0.56 * (sy > 0 ? 1 - 0.3 * pow(sy, 1.3) : 1 - 0.05 * sy * sy)
        let q = pow(x / w, 2) + sy * sy
        guard q < 1 else { return 0 }
        func g(_ dx: Double, _ sx: Double, _ dy: Double, _ syy: Double) -> Double { exp(-pow(dx / sx, 2) - pow(dy / syy, 2)) }
        let ax = abs(x), my = FaceGeometry.mouthY, ex = FaceGeometry.eyeX, ey = FaceGeometry.eyeY
        // The head, its crown falling away behind the forehead.
        let z = 0.3 * pow(1 - q, 0.5) * (1 - 0.2 * smoothstep(-0.45, -0.95, y))
        var f = 0.0
        f += 0.02 * g(x, 0.3, y + 0.62, 0.22)                                   // the forehead
        f += 0.014 * g(ax - 0.2, 0.18, y + 0.37, 0.07)                          // a gentle brow
        // The closed eyes: round lids in soft hollows.
        f -= 0.026 * g(ax - ex, 0.14, y - ey + 0.01, 0.1)
        f += 0.03 * g(ax - ex, 0.085, y - ey - 0.01, 0.05)
        // The line of the closed lids, curving gently down, content.
        let lid = ey + 0.012 + 0.02 * max(0, 1 - pow((ax - ex) / 0.1, 2))
        f -= 0.02 * exp(-pow((ax - ex) / 0.105, 4)) * exp(-pow((y - lid) / 0.018, 2))
        // The nose: a soft bridge to a round tip and its wings.
        let bridgeW = 0.045 + 0.03 * smoothstep(-0.2, 0.08, y)
        f += 0.07 * smoothstep(-0.24, 0.05, y) * (1 - smoothstep(0.08, 0.14, y)) * exp(-pow(x / bridgeW, 2))
        f += 0.04 * g(x, 0.06, y - 0.07, 0.045)
        f += 0.025 * g(ax - 0.065, 0.04, y - 0.1, 0.035)
        // The smile: round cheeks lifted toward the eyes, lips curving up at the corners.
        f += 0.07 * g(ax - 0.27, 0.13, y - 0.06, 0.11)
        let smileY = my - 0.06 * pow(x / 0.18, 2)
        f += 0.032 * g(x, 0.15, y - (smileY - 0.034), 0.034)
        f += 0.04 * g(x, 0.13, y - (smileY + 0.04), 0.038)
        f -= 0.022 * g(x, 0.19, y - smileY, 0.016)
        f += 0.045 * g(x, 0.13, y - 0.5, 0.07)                                  // the chin
        return z + f * smoothstep(1, 0.75, q)
    }

    static let grid: ImprintGeometry.Grid = {
        typealias G = ImprintGeometry.Grid
        var z = [Double](repeating: 0, count: G.nx * G.ny)
        for j in 0..<G.ny { for i in 0..<G.nx { z[j * G.nx + i] = max(0, relief(G.x0 + Double(i) * G.step, G.y0 + Double(j) * G.step)) } }
        return G(z: z)
    }()

    /// The face with its mouth now: the jaw dropped below the mouth, the lips parted, narrower on a
    /// round vowel, a little forward on a pout.
    static func z(_ x: Double, _ y: Double, _ mouth: MouthShape) -> Double {
        let my = FaceGeometry.mouthY
        var sx = x, sy = y
        if abs(y - my) < 0.4 {
            let near = exp(-pow((y - my) / 0.12, 2)) * exp(-pow(x / 0.3, 2))
            sx = x / max(0.6, 1 - (1 - mouth.width) * near)
            sy = y - 0.6 * mouth.jaw(x, y)
        }
        var z = grid.at(sx, sy) ?? 0
        if mouth.open > 0.04 {
            let gap = 0.07 * mouth.open
            z -= 0.045 * exp(-pow(x / (0.16 * mouth.width), 2) - pow((y - my - gap * 0.6) / (gap + 0.01), 2))
        }
        if mouth.pout > 0.001 { z += 0.02 * mouth.pout * exp(-pow((y - my) / 0.08, 2) - pow(x / 0.16, 2)) }
        return max(0, z)
    }
}

@inline(__always) private func fract(_ x: Double) -> Double { x - x.rounded(.down) }
