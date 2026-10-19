import SwiftUI

// Three avatars made from the Face, each another way of showing what is happening:
// Imprint (a face seen only where it touches a pane of glass), Hologram (the head as scan lines of
// light) and Eye (one large, friendly eye).

extension OrbCanvas {
    // MARK: Imprint

    /// A face, zoomed in, pressed against a pane of glass: only what touches the pane is drawn,
    /// flattened against it with a bright rim (the brows, the nose, the lips, the chin; the eyes are
    /// hollows). Its voice presses it in, so more of it shows as it speaks (the cheeks, the forehead)
    /// and the lips part with the words; while you speak it turns to lay its cheek against the pane;
    /// thinking, it draws back until only the tip of its nose touches, the pane drifting through
    /// its depth.
    func drawImprint(_ gc: inout GraphicsContext, _ box: CGSize) {
        var d = dotCanvas(box)
        let ph = OrbPhases(engine)
        let th = ph.think, talk = engine.talking, e = engine.engagement, listen = ph.listen
        let mouth = MouthShape(engine: engine, smileBase: 1 + 0.2 * listen)
        let yaw = 0.12 * sin(t * 0.27) - 0.62 * listen + 0.1 * th
        let pitch = 0.04 * sin(t * 0.19) - 0.05 * th
        let roll = 0.03 * sin(t * 0.23) + 0.05 * listen
        let pose = HeadPose(yaw: yaw, pitch: pitch, roll: roll, pivotY: 0, lift: 0)
        let press = 0.03 * talk * e * min(1, 1.6 * engine.loud) + 0.012 * listen + 0.005 * sin(t * 0.9) - 0.05 * th
        // Thinking: the pane drifts slowly through its depth; working: it flickers through it quickly.
        let plane = ImprintGeometry.plane + 0.05 * th * sin(t * 1.3) + ph.work * (0.035 * sin(t * 5.3) - 0.02)
        let band = ImprintGeometry.band
        let my = FaceGeometry.mouthY
        let scale = 1.78, shift = 0.08
        for p in ImprintGeometry.points(count: min(6000, pointBudget(box) * 4)) {
            var x = p.x, y = p.y, z = p.z
            // The mouth: the jaw drops below it, the opening recedes, rounder or wider with the vowel.
            if abs(y - my) < 0.3 {
                let near = exp(-pow((y - my) / 0.12, 2)) * exp(-pow(x / 0.3, 2))
                x *= 1 - (1 - mouth.width) * near
                y += mouth.jaw(x, y) * 1.2
                if mouth.open > 0.05 {
                    let gap = 0.07 * mouth.open
                    let inside = exp(-pow(x / (0.17 * mouth.width), 2) - pow((y - my - gap * 0.6) / (gap + 0.004), 2))
                    z -= 0.12 * inside
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
            guard dz > -band else { continue }
            // Pressed flat: brighter the harder it presses, a bright rim where it meets the pane.
            // Lit by its own surface (soft frontal light), so the features read; pressed harder, a
            // little brighter; a bright rim where it meets the pane.
            let n = pose.apply(p.nx, p.ny, p.nz)
            let light = max(0, -0.25 * n.x - 0.32 * n.y + 0.91 * n.z)
            let flat = (0.1 + 0.55 * pow(light, 1.6)) * (0.8 + 0.3 * smoothstep(0, 0.08, dz)) + 0.35 * exp(-pow(dz / band, 2))
            let sx = r.x * scale, sy = (r.y + shift) * scale
            place(&d, sx, sy, flat * (0.8 + 0.3 * p.lum) + 0.12 * engine.signal, p.dither, phase: p.phase, lum: p.lum)
        }
        // The pane: a faint sheen sweeping across it.
        for k in 0..<60 {
            let x = 2 * OrbPoints.hash(k, 41) - 1, y = 2 * OrbPoints.hash(k, 43) - 1
            let sweep = exp(-pow((x + y) * 0.7 - (t * 0.25).truncatingRemainder(dividingBy: 3) + 1.5, 2) * 6)
            d.dot(x * 1.9, y * 1.9, 0.06 + 0.25 * sweep, OrbPoints.hash(k, 14))
        }
        finish(&gc, d)
    }

    // MARK: Hologram

    /// A hologram of the head: the face's head (its relief: brows, nose, lips, chin) drawn as glowing
    /// horizontal scan lines that wrap around it, the far side faint, turning slowly so its depth
    /// reads, with its eyes and lips drawn over the lines. As it speaks, light pulses along the lines
    /// out from its mouth and its lips move with the words; while you speak it turns toward you and
    /// the lines ripple with your voice; thinking, a bright scan band sweeps down the head.
    func drawHologram(_ gc: inout GraphicsContext, _ box: CGSize) {
        var d = dotCanvas(box)
        let ph = OrbPhases(engine)
        let th = ph.think, talk = engine.talking, e = engine.engagement, hist = engine.history, listen = ph.listen
        let busy = ph.work
        let mouth = MouthShape(engine: engine, smileBase: 1 + 0.3 * listen - 0.2 * th)
        let yaw = 0.38 * sin(t * 0.2) * (1 - 0.7 * listen) + 0.15 * th * sin(t * 0.9)
        let pitch = 0.04 * sin(t * 0.27) - 0.05 * th + 0.03 * mouth.open * sin(t * 6.1)
        let pose = HeadPose(yaw: yaw, pitch: pitch, roll: 0.03 * sin(t * 0.17), pivotY: FaceGeometry.neckY, lift: 0.01 * sin(t * 1.25))
        let scanY = -1.1 + 2.0 * (t * 0.45).truncatingRemainder(dividingBy: 1)
        let my = FaceGeometry.mouthY
        let scale = 1.3, shift = -0.02
        let level = hist.value(secondsAgo: 0.05)
        for p in HologramGeometry.points(count: min(4200, pointBudget(box) * 2)) {
            var x = p.x, y = p.y, z = p.z
            if p.front && abs(y - my) < 0.3 {
                y += mouth.jaw(x, y) * 1.1
                if mouth.open > 0.05 {
                    let gap = 0.07 * mouth.open
                    z -= 0.25 * exp(-pow(x / (0.17 * mouth.width), 2) - pow((y - my - gap * 0.6) / (gap + 0.004), 2))
                }
            }
            if listen > 0.01 { x += listen * (0.006 + 0.03 * level) * sin(16 * p.y - 7 * t) }
            let r: (x: Double, y: Double, z: Double) = p.head ? pose.apply(x, y, z) : (x: x, y: y + 0.01 * sin(t * 1.25), z: z)
            let facing: Double = r.z > 0 ? 0.42 + 0.5 * smoothstep(0, FaceGeometry.depth, r.z) : 0.12
            var bright: Double = p.lum * facing
            let words: Double = hist.value(secondsAgo: abs(p.y - my) * 0.55)
            bright += talk * e * 0.85 * words * (r.z > 0 ? 1 : 0.3)
            let scan: Double = exp(-pow((p.y - scanY) / 0.05, 2))
            bright += th * 1.1 * scan
            if busy > 0.01 {
                // Working: three fast bands and a flicker along each line, as data runs through it.
                var bands = 0.0
                for k in 0..<3 {
                    let by = -1.0 + 1.9 * ((t * 1.3 + Double(k) / 3).truncatingRemainder(dividingBy: 1))
                    bands += exp(-pow((p.y - by) / 0.035, 2))
                }
                let flicker = OrbPoints.hash(Int(p.y * 200) * 31 + Int(t * 12), 3) < 0.25 ? 0.35 : 0
                bright += busy * (0.7 * bands + flicker)
            }
            bright += 0.1 * engine.signal
            let sx = r.x * scale, sy = r.y * scale + shift
            let rr = (sx * sx + sy * sy).squareRoot()
            if rr > 1.98 { continue }
            place(&d, sx, sy, bright * (1 - smoothstep(1.6, 1.98, rr)), p.dither, phase: p.phase, lum: p.lum)
        }
        // The eyes and the lips over the lines (they make it a face, and a friendly one).
        let blink = FaceGeometry.blink(t)
        for p in FaceGeometry.points(count: pointBudget(box)) where p.kind.isFeature && p.kind != .cheek && p.kind != .nose {
            var x = p.x, y = p.y, z = p.z, lum = p.lum
            switch p.kind {
            case .lidUpper, .lidLower: y = FaceGeometry.eyeY + (y - FaceGeometry.eyeY) * blink
            case .iris, .glint:
                if blink < 0.4 { continue }
                x += 0.03 * th; y = FaceGeometry.eyeY + (y - FaceGeometry.eyeY - 0.025 * th) * blink
            case .brow: y -= 0.03 * listen + 0.02 * th
            case .lipUpper, .lipLower, .teeth:
                guard let m = mouth.place(p) else { continue }
                x = m.x; y = m.y; lum = m.lum
                z = (ImprintGeometry.relief(x, y) ?? 0.5) + 0.02
            default:
                z = (ImprintGeometry.relief(x, y) ?? p.z) + 0.02
            }
            let r = pose.apply(x, y, z)
            guard r.z > 0.15 else { continue }
            place(&d, r.x * scale, r.y * scale + shift, lum * 0.95, p.dither, phase: p.phase, lum: lum)
        }
        finish(&gc, d)
    }

    // MARK: Eye

    /// One large, friendly eye: soft lids with lashes, a catchlight, an iris of fine fibers around
    /// the pupil. As it speaks its eye smiles, the fibers glow with its voice (its spectrum around
    /// the iris) and the pupil narrows on loud sounds; while you speak it opens wide, its brow lifts,
    /// its pupil widens and rings of your voice ripple in toward it; thinking, it looks up and aside,
    /// its lids lower a little and its iris turns slowly. It blinks every few seconds.
    func drawEye(_ gc: inout GraphicsContext, _ box: CGSize) {
        var d = dotCanvas(box)
        let ph = OrbPhases(engine)
        let th = ph.think, hist = engine.history, loud = engine.loud
        let listen = ph.listen, speak = ph.speak, busy = ph.work
        let spectrum = VoiceFeatures(level: loud, bands: engine.bands)
        let blink = FaceGeometry.blink(t)
        let open = (0.82 + 0.18 * listen - 0.22 * th) * blink
        let smile = 0.14 * speak + 0.06 * listen
        let W = EyeGeometry.halfWidth
        let hu = 0.62 * open, hl = max(0.02, (0.44 - smile) * open)
        func upper(_ x: Double) -> Double { -hu * pow(max(0, 1 - pow(x / W, 2)), 0.75) }
        func lower(_ x: Double) -> Double { hl * pow(max(0, 1 - pow(x / W, 2)), 0.9) - 0.5 * smile * max(0, 1 - pow(x / W, 2)) * 0.2 }
        func inside(_ x: Double, _ y: Double) -> Bool { abs(x) < W && y > upper(x) && y < lower(x) }
        // Working: the gaze jumps from point to point (reading), each fixation a moment long.
        let fix = Int(t * 2.2)
        let jumpX = (OrbPoints.hash(fix, 81) - 0.5) * 0.5, jumpY = (OrbPoints.hash(fix, 82) - 0.5) * 0.18
        let gx = (0.1 * sin(t * 0.4) + 0.05 * sin(t * 0.13)) * (1 - listen) * (1 - th) * (1 - busy) + th * (-0.26 + 0.07 * sin(t * 0.7)) + busy * jumpX
        let gy = 0.03 * sin(t * 0.33) * (1 - th) * (1 - busy) - 0.17 * th + busy * jumpY
        let iris = EyeGeometry.irisRadius
        let pupil = 0.16 + 0.07 * listen - 0.05 * speak * min(1, 1.5 * loud) - 0.02 * th - 0.04 * busy
        let turn = 0.12 * engine.ringTurn                                // the iris turns while it thinks
        let scale = 1.42, shift = 0.08
        func put(_ x: Double, _ y: Double, _ b: Double, _ dither: Double, _ phase: Double, lum: Double = 0.7) {
            place(&d, x * scale, (y + shift) * scale, b, dither, phase: phase, lum: lum)
        }
        for p in EyeGeometry.points(count: pointBudget(box)) {
            switch p.kind {
            case .fiber:
                // A point on its fiber, from the pupil's edge out to the iris's rim.
                let r = pupil + (iris - pupil) * p.u
                let a = p.a + turn + 0.22 * sin(3 * p.u + p.a * 2) * (1 - p.u)
                let x = gx + r * cos(a), y = gy + r * sin(a)
                guard inside(x, y) else { continue }
                var b = p.lum * (0.32 + 0.3 * exp(-pow((p.u - 0.32) / 0.08, 2)) + 0.45 * smoothstep(0.88, 1, p.u))
                let pos = (a.truncatingRemainder(dividingBy: 2 * .pi) + 2 * .pi).truncatingRemainder(dividingBy: 2 * .pi) / (2 * .pi)
                b += speak * 0.9 * spectrum.band(at: abs(pos * 2 - 1)) * (0.4 + 0.6 * p.u)
                if listen > 0.01 { b += listen * 0.8 * hist.value(secondsAgo: (1 - p.u) * 0.9) * exp(-pow(sin((p.u - t * 1.2) * .pi * 2), 2) * 2) }
                b += 0.08 * engine.signal
                put(x, y, b, p.dither, p.phase, lum: p.lum)
            case .pupilEdge:
                let x = gx + pupil * cos(p.a), y = gy + pupil * sin(p.a)
                guard inside(x, y) else { continue }
                put(x, y, 0.75, p.dither, p.phase)
            case .sclera:
                let x = p.x * W, y = p.y < 0 ? -p.y * upper(p.x * W) : p.y * lower(p.x * W)
                let dx = x - gx, dy = y - gy
                guard dx * dx + dy * dy > iris * iris * 1.08, inside(x, y) else { continue }
                put(x, y, 0.13 * p.lum, p.dither, p.phase)
            case .upperLid, .lowerLid, .crease, .lash:
                let x = p.x * W
                var y: Double
                switch p.kind {
                case .upperLid: y = upper(x) - 0.012 * p.v
                case .lowerLid: y = lower(x) + 0.01 * p.v
                case .crease: y = upper(x) * 1.0 - 0.13 - 0.05 * open - 0.03 * listen
                default:
                    // A lash: from the upper lid, outward and up, curling.
                    let base = upper(x), out = p.v
                    let dir = (x / W) * 0.6
                    put(x + dir * 0.14 * out, base - 0.11 * out * (0.6 + 0.4 * open) + 0.03 * out * out, p.lum * (0.85 - 0.3 * out), p.dither, p.phase)
                    continue
                }
                put(x, y, p.lum, p.dither, p.phase, lum: p.lum)
            case .brow:
                let x = p.x * 1.15
                let y = -0.95 - 0.1 * listen - 0.06 * th * (x > 0 ? 1 : 0.3) + 0.14 * pow(x / 1.15, 2) + 0.02 * p.v
                put(x, y + 0.04 * (1 - open), p.lum, p.dither, p.phase)
            case .glint:
                // The catchlight stays put as the eye looks around (the light does not move).
                let x = gx * 0.5 - 0.14 + p.x, y = gy * 0.5 - 0.17 + p.y
                guard inside(x, y) else { continue }
                put(x, y, 1.25, p.dither, p.phase, lum: 1)
            }
        }
        finish(&gc, d)
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
        let w = FaceGeometry.halfWidth * (sy > 0 ? 1 - 0.2 * sy : 1)
        guard 1 - pow(x / w, 2) - sy * sy > 0 else { return nil }
        // A face is nearly flat from forehead to chin and curves back at the sides.
        let ax = abs(x)
        var z = FaceGeometry.depth * pow(max(0, 1 - pow(x / w, 2)), 0.3) * (1 - 0.25 * pow((y + 0.1) / FaceGeometry.halfHeight, 2))
        z += 0.15 * exp(-pow(x / 0.075, 2)) * smoothstep(-0.26, 0.08, y) * (1 - smoothstep(0.08, 0.15, y))   // nose
        z += 0.06 * exp(-pow((ax - 0.065) / 0.04, 2) - pow((y - 0.12) / 0.04, 2))                           // nostrils
        z += 0.04 * exp(-pow((y + 0.37) / 0.06, 2)) * exp(-pow((ax - 0.22) / 0.2, 2))                        // brow ridge
        z -= 0.07 * exp(-pow((ax - FaceGeometry.eyeX) / 0.11, 2) - pow((y - FaceGeometry.eyeY) / 0.07, 2))  // soft sockets
        z += 0.05 * exp(-pow((ax - FaceGeometry.eyeX) / 0.055, 2) - pow((y - FaceGeometry.eyeY) / 0.035, 2)) // eyes
        let smileY = FaceGeometry.mouthY - 0.035 * pow(x / 0.17, 2)                                    // the mouth line smiles
        z -= 0.05 * exp(-pow(x / 0.19, 2) - pow((y - smileY) / 0.016, 2))                              // between the lips
        z -= 0.08 * exp(-pow((ax - 0.05) / 0.02, 2) - pow((y - 0.135) / 0.015, 2))                          // nostrils
        z += 0.08 * exp(-pow((ax - 0.3) / 0.13, 2) - pow((y - 0.12) / 0.11, 2))                              // full cheeks (a smile lifts them)
        z += 0.07 * exp(-pow(x / 0.17, 2) - pow((y - 0.29) / 0.03, 2))                                     // upper lip
        z += 0.075 * exp(-pow(x / 0.15, 2) - pow((y - 0.37) / 0.035, 2))                                   // lower lip
        z += 0.08 * exp(-pow(x / 0.15, 2) - pow((y - 0.56) / 0.08, 2))                                     // chin
        return z
    }

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

// MARK: - Hologram's points

/// The head as horizontal scan lines: each line wraps around the head at its height, its front
/// following the face's relief (`ImprintGeometry.relief`), its back the egg of the head; then the
/// neck and the shoulders' lines. Points evenly spaced along each line.
enum HologramGeometry {
    struct P { let x: Double; let y: Double; let z: Double; let front: Bool; let head: Bool; let lum: Double; let dither: Double; let phase: Double }

    @MainActor private static var cache: [Int: [P]] = [:]

    @MainActor static func points(count n: Int) -> [P] {
        if let c = cache[n] { return c }
        var lines: [[(Double, Double, Double, Bool, Bool)]] = []
        let headLines = 30
        for j in 0..<headLines {
            let y = -0.97 + 1.58 * Double(j) / Double(headLines - 1)
            let sy = (y - FaceGeometry.headY) / FaceGeometry.halfHeight
            let w = FaceGeometry.halfWidth * (sy > 0 ? 1 - 0.2 * sy : 1) * max(0, 1 - sy * sy).squareRoot()
            guard w > 0.03 else { continue }
            var line: [(Double, Double, Double, Bool, Bool)] = []
            for i in 0...80 {                                       // the front, through the relief
                let x = -w + 2 * w * Double(i) / 80
                line.append((x, y, ImprintGeometry.relief(x, y) ?? 0, true, true))
            }
            for i in 1..<60 {                                       // the back: half an ellipse
                let a = Double.pi * Double(i) / 60
                line.append((w * cos(a), y, -FaceGeometry.depth * 0.95 * sin(a) * max(0, 1 - sy * sy).squareRoot(), false, true))
            }
            lines.append(line)
        }
        for j in 0..<5 {                                            // the neck
            let y = 0.66 + 0.06 * Double(j)
            lines.append((0..<60).map { i in
                let a = 2 * Double.pi * Double(i) / 60
                return (0.2 * cos(a), y, 0.18 * sin(a), sin(a) > 0, false)
            })
        }
        for j in 0..<4 {                                            // the shoulders
            let y0 = 0.95 + 0.14 * Double(j)
            lines.append((0...90).map { i in
                let x = -1.5 + 3 * Double(i) / 90
                let top = 0.32 * pow(max(0, abs(x) - 0.22) / 1.33, 1.5)
                return (x, y0 + top, 0.25 * max(0, 1 - pow(x / 1.5, 2)), true, false)
            })
        }
        // Evenly spaced points along each line, as many as the budget allows.
        var length = 0.0
        for line in lines { for i in 1..<line.count { length += hypot(line[i].0 - line[i - 1].0, line[i].2 - line[i - 1].2) } }
        let step = length / Double(n)
        var out: [P] = []
        out.reserveCapacity(n)
        var k = 0
        for line in lines {
            var carry = 0.0
            for i in 1..<line.count {
                let a = line[i - 1], b = line[i]
                let seg = hypot(b.0 - a.0, b.2 - a.2)
                var s = carry
                while s < seg {
                    let f = s / seg
                    k += 1
                    out.append(P(x: a.0 + (b.0 - a.0) * f, y: a.1, z: a.2 + (b.2 - a.2) * f, front: a.3, head: a.4,
                                 lum: (a.4 ? 0.9 : 0.6) + 0.2 * OrbPoints.hash(k, 3), dither: OrbPoints.hash(k, 14),
                                 phase: 2 * .pi * OrbPoints.hash(k, 12)))
                    s += step
                }
                carry = s - seg
            }
        }
        cache[n] = out
        return out
    }
}

// MARK: - The eye's points

/// The eye's fixed points, placed each frame from their parameters: the iris's fibers (each point
/// at its angle and its place along the fiber), the pupil's edge, the white of the eye, the lids,
/// the crease, the lashes, the brow and the catchlight.
enum EyeGeometry {
    enum Kind { case fiber, pupilEdge, sclera, upperLid, lowerLid, crease, lash, brow, glint }
    struct P {
        let kind: Kind
        /// Fibers: angle `a`, place `u` (0 the pupil … 1 the rim). Lids, brow: `x` −1…1 across, `v`
        /// a little thickness. Sclera: `x` −1…1, `y` −1…1 (up to the upper lid … down to the lower).
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
        let fiberPoints = Int(Double(n) * 0.52)
        let fibers = max(36, fiberPoints / 14)
        for f in 0..<fibers {
            let a = 2 * Double.pi * (Double(f) + 0.4 * OrbPoints.hash(f, 21)) / Double(fibers)
            let lum = 0.65 + 0.35 * OrbPoints.hash(f, 22)
            for _ in 0..<(fiberPoints / fibers) { k += 1; add(.fiber, a: a, u: h(1), lum: lum) }
        }
        for i in 0..<max(24, n / 40) { k += 1; add(.pupilEdge, a: 2 * Double.pi * Double(i) / Double(max(24, n / 40)), lum: 0.8) }
        for _ in 0..<Int(Double(n) * 0.1) { k += 1; add(.sclera, x: 2 * h(1) - 1, y: 2 * h(2) - 1, lum: 0.6 + 0.4 * h(3)) }
        for _ in 0..<Int(Double(n) * 0.1) { k += 1; add(.upperLid, x: 2 * h(1) - 1, v: h(2), lum: 1) }
        for _ in 0..<Int(Double(n) * 0.06) { k += 1; add(.lowerLid, x: 2 * h(1) - 1, v: h(2), lum: 0.7) }
        for _ in 0..<Int(Double(n) * 0.04) { k += 1; let x = 1.7 * h(1) - 0.85; add(.crease, x: x, lum: 0.35 * (1 - abs(x))) }
        for l in 0..<9 {                                            // the lashes, along the outer half
            let x = 0.1 + 0.85 * Double(l) / 8
            for i in 0..<9 { k += 1; add(.lash, x: x, v: Double(i) / 8, lum: 0.75) }
        }
        for _ in 0..<Int(Double(n) * 0.05) { k += 1; add(.brow, x: 2 * h(1) - 1, v: h(2), lum: 0.65) }
        for _ in 0..<max(12, n / 60) {                              // the catchlight
            k += 1; let a = 2 * Double.pi * h(1), r = 0.06 * h(2).squareRoot()
            add(.glint, x: r * cos(a), y: r * sin(a), lum: 1)
        }
        cache[n] = out
        return out
    }
}
