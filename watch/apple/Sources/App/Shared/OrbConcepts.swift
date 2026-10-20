import SwiftUI

// Five orbs with one shape per state of the assistant (listening, thinking, working with its
// tools, speaking; at rest a calm listening shape), the points morphing from one to the next as the
// state changes: Lotus (a bud that blooms), Crystal (a crystal that grows wings), Eclipse (a golden
// eclipse), Synapse (a network of nodes) and Drop (a drop of light). Units as the planet (1 = its
// radius, y down).

/// Each point's place in each phase's shape is blended with the phases' weights.
private typealias StateMix = OrbPhases

/// A point in space and its light, summed over the states' shapes.
private struct Blend {
    var x = 0.0, y = 0.0, z = 0.0, b = 0.0
    mutating func add(_ w: Double, _ x: Double, _ y: Double, _ z: Double, _ b: Double) {
        guard w > 0.003 else { return }
        self.x += w * x; self.y += w * y; self.z += w * z; self.b += w * b
    }
}

/// The view: a turn about the vertical axis, then a tilt toward the viewer.
private struct View3 {
    let cY: Double, sY: Double, cP: Double, sP: Double
    init(yaw: Double, pitch: Double) { cY = cos(yaw); sY = sin(yaw); cP = cos(pitch); sP = sin(pitch) }
    func apply(_ x: Double, _ y: Double, _ z: Double) -> (x: Double, y: Double, z: Double) {
        let x1 = x * cY + z * sY, z1 = -x * sY + z * cY
        return (x1, y * cP - z1 * sP, y * sP + z1 * cP)
    }
}

@inline(__always) private func frac(_ x: Double) -> Double { x - x.rounded(.down) }

extension OrbCanvas {
    private func depthLight(_ z: Double) -> Double { 0.45 + 0.55 * smoothstep(-0.9, 0.7, z) }

    /// A point of a form with the work's light and the countdown, in its hue (`edge`: the form's
    /// outer radius for the countdown).
    private func put(_ d: inout HueDots, _ x: Double, _ y: Double, _ bright: Double, _ hue: Double, _ i: Int,
                     phase: Double, lum: Double = 0.7, edge: Double = 1.6, size: Double = 1) {
        var sx = x, sy = y
        let light = workEffect(&sx, &sy, phase: phase)
        let b = (bright + 0.8 * light * (0.45 + 0.55 * lum)) * countdownDim(sx / edge, sy / edge)
        d.dot(sx, sy, b, hue, OrbPoints.hash(i, 14), OrbPoints.hash(i, 15), size: size)
    }

    /// A soft disc of light (a radial gradient) at a point of the form, `r` in units.
    private func glow(_ c: inout GraphicsContext, _ d: HueDots, _ x: Double, _ y: Double, _ r: Double, _ colors: [Color]) {
        let p = CGPoint(x: d.cx + x * d.R, y: d.cy + y * d.R), rr = r * d.R
        c.fill(Path(ellipseIn: CGRect(x: p.x - rr, y: p.y - rr, width: 2 * rr, height: 2 * rr)),
               with: .radialGradient(Gradient(colors: colors), center: p, startRadius: 0, endRadius: rr))
    }

    // MARK: Lotus

    /// Listening, a closed bud breathing with your voice over rings of light; thinking, its petals
    /// open and twist; working, it becomes a branching network, a glowing node at each tip; speaking,
    /// a full bloom, its petals opening wider and its stamens reaching up with the voice. A thread of
    /// light falls from its base. Petals cyan at the heart to rose at their tips.
    func drawLotus(_ gc: inout GraphicsContext, _ box: CGSize) {
        var d = hueDots(box)
        let m = StateMix(engine)
        let n = pointBudget(box)
        let level = engine.history.value(secondsAgo: 0.05), loud = engine.loud
        let spectrum = VoiceFeatures(level: loud, bands: engine.bands)
        let view = View3(yaw: t * 0.12 + 0.3 * m.think * sin(t * 0.4), pitch: 0.38)
        let base = (x: 0.0, y: 0.38, z: 0.0)
        let petals = Int(Double(n) * 0.74), stamens = Int(Double(n) * 0.12)
        let k = 1.65, lift = -0.24
        /// A petal point: its petal's tilt from upright `phi`, twist, length, how wide it spreads.
        func petal(_ layer: Int, _ p: Int, _ u: Double, _ v: Double, phi: Double, twist: Double, len: Double, spread: Double) -> (Double, Double, Double) {
            let a = 2 * Double.pi * Double(p) / 8 + Double(layer) * .pi / 8 + twist * u
            let sp = sin(phi), cp = cos(phi), ca = cos(a), sa = sin(a)
            let width = 0.36 * pow(sin(Double.pi * min(u, 0.999)), 0.85) * len * spread
            let along = u * len, across = v * width, cup = 0.14 * v * v * width
            return (base.x + along * sp * ca - across * sa - cup * cp * ca,
                    base.y - along * cp + cup * sp,
                    base.z + along * sp * sa + across * ca - cup * cp * sa)
        }
        for i in 0..<n {
            let h1 = OrbPoints.hash(i, 1), h2 = OrbPoints.hash(i, 2)
            var bl = Blend()
            var hue = 0.3
            if i < petals {
                let layer = i % 2, p = (i / 2) % 8, u = h1
                // Most points on the petal's outline (it reads as a petal), a few inside.
                let onEdge = OrbPoints.hash(i, 5) < 0.62
                let v = onEdge ? (h2 < 0.5 ? -1.0 : 1.0) * (0.94 + 0.06 * OrbPoints.hash(i, 6)) : 2 * h2 - 1
                let edge = onEdge ? 0.95 : 0.34
                let tip = 0.5 * smoothstep(0.85, 1, u)
                let outer = layer == 0
                hue = 0.1 + 0.72 * u + (outer ? 0.12 : 0)
                let bud = petal(layer, p, u, v, phi: (outer ? 0.36 : 0.2) + 0.14 * level * m.listen, twist: 0.25, len: outer ? 0.78 : 0.7, spread: 0.85)
                bl.add(m.rest + m.listen, bud.0, bud.1, bud.2, edge + tip * (0.5 + m.listen * level))
                let turning = petal(layer, p, u, v, phi: outer ? 0.75 : 0.42, twist: 0.9 + 0.5 * sin(t * 0.6), len: 0.85, spread: 0.8)
                bl.add(m.think, turning.0, turning.1, turning.2, edge + tip)
                let open = petal(layer, p, u, v, phi: (outer ? 1.28 : 0.74) + 0.2 * loud, twist: 0.05, len: outer ? 0.98 : 0.82, spread: 1)
                bl.add(m.speak, open.0, open.1, open.2, edge + tip + 0.5 * loud)
                if m.work > 0.003 {
                    // A branch per petal, rising and leaning out; a node (a small disc) at its tip.
                    let br = layer * 8 + p
                    let ab = 2 * Double.pi * Double(br) / 16 + 0.2 * sin(Double(br))
                    let reach = 0.55 + 0.45 * OrbPoints.hash(br, 7)
                    let tipX = reach * 1.05 * cos(ab), tipZ = reach * 1.05 * sin(ab), tipY = base.y - 1.15 * reach
                    if abs(v) > 0.78 {
                        let q = 2 * Double.pi * (abs(v) - 0.78) / 0.22, r = 0.05 * (0.4 + 0.6 * OrbPoints.hash(i, 8))
                        let arrive = pow(max(0, sin((1 - t * 0.9) * 2 * .pi)), 4)
                        bl.add(m.work, tipX + r * cos(q), tipY + r * sin(q), tipZ, 0.8 + 0.5 * arrive)
                    } else {
                        let f = u
                        let x = tipX * f * f, z = tipZ * f * f, y = base.y + (tipY - base.y) * f
                        let pulse = 0.4 + 0.6 * pow(max(0, sin((f - t * 0.9) * 2 * .pi)), 8)
                        bl.add(m.work, x, y, z, pulse)
                    }
                }
            } else if i < petals + stamens {
                // Stamens: hidden in the bud; reaching up with the voice in the bloom.
                let f = (i - petals) % 24, u = h1
                let af = 2 * Double.pi * Double(f) / 24, tilt = 0.15 + 0.5 * OrbPoints.hash(f, 3)
                let bandLen = 0.35 + 0.7 * spectrum.band(at: Double(f % 8) / 7) * m.speak
                let tipB = u > 0.92 ? 1.1 : 0.45
                let len = 0.25 + 0.35 * OrbPoints.hash(f, 4)
                hue = 0.55 + 0.45 * u
                bl.add(m.rest + m.listen, 0.05 * cos(af) * u, base.y - 0.3 * u, 0.05 * sin(af) * u, 0.25)
                bl.add(m.think, 0.3 * sin(tilt) * cos(af) * u, base.y - 0.45 * u, 0.3 * sin(tilt) * sin(af) * u, 0.4 * tipB)
                bl.add(m.speak, (len + bandLen) * sin(tilt) * cos(af) * u, base.y - (len + bandLen) * cos(tilt) * u, (len + bandLen) * sin(tilt) * sin(af) * u, tipB)
                // Working: rings of light at the base.
                let ra = 2 * Double.pi * h1, rr = 0.45 + 0.3 * Double(f % 2)
                bl.add(m.work, rr * cos(ra), base.y + 0.05, rr * sin(ra), 0.4)
            } else {
                // The thread of light below and the rings around the base (rippling as you speak).
                if i % 3 == 0 {
                    let ring = Double(i % 2)
                    let r = 0.45 + 0.35 * ring + 0.35 * m.listen * frac(t * 0.6 + ring * 0.5)
                    let a = 2 * Double.pi * h1
                    hue = 0.35 + 0.3 * ring
                    bl.add(1, r * cos(a), base.y + 0.06, r * sin(a), 0.32 + 0.6 * m.listen * level)
                } else {
                    let f = frac(h1 + t * 0.35)
                    hue = 0.1 + 0.4 * f
                    bl.add(1, 0.04 * (h2 - 0.5) * (1 + f), base.y + 0.1 + 1.5 * f, 0.03 * (h2 - 0.5), 0.6 * (1 - f))
                }
            }
            let p = view.apply(bl.x, bl.y, bl.z)
            put(&d, p.x * k, p.y * k + lift, bl.b * depthLight(p.z), hue, i, phase: h1 * 6.3, lum: min(1, bl.b))
        }
        // A soft light at the flower's heart, brighter as it blooms and speaks.
        let heart = view.apply(0, base.y - 0.28 - 0.1 * m.speak, 0)
        let hs = OrbPalette.hues(for: look.color)
        let warm = 0.32 + 0.18 * m.speak * (1 + loud) + 0.12 * m.listen * level
        finishHue(&gc, d) { c in
            glow(&c, d, heart.x * k, heart.y * k + lift, 0.95 + 0.25 * m.speak,
                 [hs[0][3].opacity(warm), hs[1][2].opacity(0.5 * warm), hs[2][2].opacity(0.2 * warm), .clear])
        }
    }

    // MARK: Crystal

    /// Listening, a faceted crystal turning slowly in a haze of sparkles that draw in with your
    /// voice; thinking, it grows into a larger compound of two crystals, the sparkles circling; working,
    /// orbits ring it with small crystals travelling on them and a beam runs through it; speaking,
    /// ribbons of light spread from it like wings, carrying the last second of the voice outward.
    /// Its edges glow, its faces are glass, cyan at the top to violet below.
    func drawCrystal(_ gc: inout GraphicsContext, _ box: CGSize) {
        var d = hueDots(box)
        let m = StateMix(engine)
        let n = pointBudget(box)
        let level = engine.history.value(secondsAgo: 0.05), loud = engine.loud
        let spin = engine.ringTurn * 1.5 + t * 0.12
        let vtx = ConceptGeometry.icosahedron, edges = ConceptGeometry.icosaEdges, faces = ConceptGeometry.icosaFaces
        let view = View3(yaw: spin, pitch: 0.35 + 0.1 * sin(t * 0.3))
        let still = View3(yaw: 0, pitch: 0.25)
        let edgePoints = Int(Double(n) * 0.4), facePoints = Int(Double(n) * 0.2)
        // Larger while it is compact; the wings need the room.
        let k = 1.5 - 0.32 * m.speak
        let restS = 0.5 * (1 + 0.15 * level * m.listen), sp = 0.6 * (1 + 0.12 * loud)
        for i in 0..<n {
            let h1 = OrbPoints.hash(i, 1), h2 = OrbPoints.hash(i, 2), h3 = OrbPoints.hash(i, 3)
            var bl = Blend()
            var turned = true
            var hue = 0.3
            if i < edgePoints {
                let e = edges[i % edges.count], u = h1
                let a = vtx[e.0], b = vtx[e.1]
                let ex = a.0 + (b.0 - a.0) * u, ey = a.1 + (b.1 - a.1) * u, ez = a.2 + (b.2 - a.2) * u
                let corner = (u < 0.06 || u > 0.94) ? 0.45 : 0
                hue = 0.12 + 0.5 * (ey + 0.95) / 1.9
                bl.add(m.rest + m.listen, ex * restS, ey * restS, ez * restS, 0.68 + corner + 0.5 * m.listen * level)
                // Thinking: the crystal grows and a second one turns inside it, the other way.
                if (i / edges.count) % 3 == 0 {                                  // every edge has points in both
                    let a = -2.4 * t, c = cos(a), s = sin(a)
                    bl.add(m.think, (ex * c + ez * s) * 0.36, ey * 0.36, (-ex * s + ez * c) * 0.36, 0.85 + corner)
                } else {
                    bl.add(m.think, ex * 0.85, ey * 0.85, ez * 0.85, 0.65 + corner)
                }
                bl.add(m.work, ex * 0.58, ey * 0.58, ez * 0.58, 0.7 + corner)
                bl.add(m.speak, ex * sp, ey * sp, ez * sp, 0.7 + corner + 0.4 * loud)
            } else if i < edgePoints + facePoints {
                // Its faces: glass, a faint sheen where a face turns toward the light.
                let f = faces[i % faces.count]
                let a = vtx[f.0], b = vtx[f.1], c = vtx[f.2]
                let r1 = h1.squareRoot(), w1 = 1 - r1, w2 = r1 * (1 - h2), w3 = r1 * h2
                let fx = w1 * a.0 + w2 * b.0 + w3 * c.0, fy = w1 * a.1 + w2 * b.1 + w3 * c.1, fz = w1 * a.2 + w2 * b.2 + w3 * c.2
                let nrm = view.apply(a.0 + b.0 + c.0, a.1 + b.1 + c.1, a.2 + b.2 + c.2)
                let sheen = max(0, (-0.45 * nrm.x - 0.6 * nrm.y + 0.65 * nrm.z) / 2.6)
                let b0 = 0.16 + 0.55 * sheen * sheen
                hue = 0.4 + 0.3 * (fy + 0.95) / 1.9
                bl.add(m.rest + m.listen, fx * restS, fy * restS, fz * restS, b0)
                bl.add(m.think, fx * 0.85, fy * 0.85, fz * 0.85, b0 * 0.8)
                bl.add(m.work, fx * 0.58, fy * 0.58, fz * 0.58, b0)
                bl.add(m.speak, fx * sp, fy * sp, fz * sp, b0)
            } else {
                // Sparkles at rest and thinking; orbits, travellers and a beam working; wings speaking.
                let dir = ConceptGeometry.direction(i)
                let r0 = 0.65 + 0.45 * h1
                let inward = 1 - 0.3 * m.listen * level
                let tw = 0.18 + 0.32 * max(0, sin(t * 2 + h2 * 20))
                hue = 0.55 + 0.4 * h1
                bl.add(m.rest + m.listen, dir.0 * r0 * inward, dir.1 * r0 * inward, dir.2 * r0 * inward, tw)
                let ra = atan2(dir.2, dir.0) + t * 0.6, rr = 0.95 + 0.4 * h1
                bl.add(m.think, rr * cos(ra), dir.1 * 0.7, rr * sin(ra), tw + 0.12)
                if m.work > 0.003 {
                    let kind = i % 9
                    if kind == 0 {                                            // the beam
                        bl.add(m.work, 0, -1.25 + 2.5 * h1, 0, 0.5 * pow(1 - abs(2 * h1 - 1), 2) + 0.04)
                    } else if kind < 3 {                                      // a traveller (a small diamond)
                        let k = i % 3, ta = t * 0.9 + 2 * Double.pi * Double(k) / 3
                        let cxr = 1.1 * cos(ta), czr = 1.1 * sin(ta)
                        let q = 2 * Double.pi * h1, s = 0.07
                        bl.add(m.work, cxr + s * cos(q), 0.1 * sin(ta) + s * 1.4 * sin(q) * (h2 < 0.5 ? 1 : -1), czr, 0.95)
                    } else {                                                  // two tilted orbits
                        let tilt = kind % 2 == 0 ? 0.35 : -0.5, rad = kind % 2 == 0 ? 1.1 : 0.85
                        let a = 2 * Double.pi * h1
                        bl.add(m.work, rad * cos(a), rad * sin(a) * sin(tilt), rad * sin(a) * cos(tilt), 0.45)
                    }
                }
                if m.speak > 0.003 {
                    turned = m.speak < 0.5
                    let line = i % 10, s = h1, side: Double = h2 < 0.5 ? -1 : 1
                    let past = engine.history.value(secondsAgo: s * 1.1)
                    let amp = (0.06 + 0.5 * s) * (0.3 + 1.3 * past)
                    let ph = 6 * s - 5 * t + Double(line) * 0.55
                    let x = side * (0.55 + 1.4 * s)
                    let y = amp * sin(ph) * (0.45 + 0.55 * cos(Double(line) * 0.35)) + (Double(line) - 4.5) * 0.018 * s
                    let z = amp * cos(ph) * 0.4
                    hue += (0.15 + 0.8 * s - hue) * m.speak
                    bl.add(m.speak, x, y, z, (0.35 + 0.8 * past) * (1 - 0.5 * s) + 0.1 * h3)
                }
            }
            let p = turned ? view.apply(bl.x, bl.y, bl.z) : still.apply(bl.x, bl.y, bl.z)
            put(&d, p.x * k, p.y * k, bl.b * depthLight(p.z), hue, i, phase: h1 * 6.3, lum: min(1, bl.b))
        }
        // The light inside it.
        let hs = OrbPalette.hues(for: look.color)
        let size = (m.rest + m.listen) * restS + m.think * 0.85 + m.work * 0.58 + m.speak * sp
        let inner = 0.3 + 0.15 * m.listen * level + 0.2 * m.speak * loud
        finishHue(&gc, d) { c in
            glow(&c, d, 0, 0, size * k * 1.15, [hs[0][3].opacity(inner), hs[1][2].opacity(0.55 * inner), hs[2][1].opacity(0.25 * inner), .clear])
        }
    }

    // MARK: Eclipse

    /// A golden eclipse, soft as a photograph of the solar corona. Listening, a dark disc in a
    /// corona of streamers, its rim glowing, a bright point at its heart; the corona swells with your
    /// voice and its light flows in; thinking, the sphere's lit crescent turns inside tilted orbits;
    /// working, a shutter opens on one half and rays fan out from it; speaking, the streamers reach
    /// out with its voice, a crescent travels round the rim and flares on loud syllables.
    func drawEclipse(_ gc: inout GraphicsContext, _ box: CGSize) {
        var d = hueDots(box)
        let m = StateMix(engine)
        let n = pointBudget(box)
        let level = engine.history.value(secondsAgo: 0.05), loud = engine.loud
        let spectrum = VoiceFeatures(level: loud, bands: engine.bands)
        let R = 0.66, k = 1.18
        let lightA = t * 0.5
        // The streamers: their angles, and their lengths in each phase (at rest, swelling with your
        // voice, reaching with its own: the spectrum round the circle, low pitches at the top).
        let streamers = 8
        let corona = m.rest + m.listen + m.speak
        var sAngle = [Double](repeating: 0, count: streamers), sLen = sAngle, sWidth = sAngle
        for j in 0..<streamers {
            let a = 2 * Double.pi * (Double(j) + 0.6 * OrbPoints.hash(j, 41)) / Double(streamers) + 0.02 * t
            sAngle[j] = a
            sWidth[j] = 0.38 + 0.3 * OrbPoints.hash(j, 43)
            let pos = abs(atan2(cos(a), -sin(a))) / .pi
            let restL = (0.28 + 0.55 * OrbPoints.hash(j, 42)) * (1 + 0.5 * m.listen * level)
            let past = engine.history.value(secondsAgo: pos * 0.7)
            let speakL = 0.25 + 0.85 * min(1, 0.4 * past + 0.8 * spectrum.band(at: pos))
            sLen[j] = corona > 0.003 ? ((m.rest + m.listen) * restL + m.speak * speakL) / corona : restL
        }
        for i in 0..<n {
            let h1 = OrbPoints.hash(i, 1), h2 = OrbPoints.hash(i, 2), h3 = OrbPoints.hash(i, 3)
            var bl = Blend()
            let a = 2 * Double.pi * h1
            let role = i % 10
            var hue = 0.0
            // The corona, the place every point has at rest and while it listens or speaks: the
            // rim's glow, streamers (their light flowing in as you speak, out as it speaks), a haze.
            var cx = 0.0, cy = 0.0, cb = 0.0
            if role < 3 {
                let rr = R * (1 + 0.035 * h2 * h2)
                let lit = m.speak > 0.003 ? max(0, cos(a - t * 1.1)) : 0
                let flare = loud > 0.45 ? exp(-pow(remainder(a - t * 1.1, 2 * .pi) / 0.12, 2)) * (loud - 0.45) * 3 : 0
                let pos = abs(atan2(cos(a), -sin(a))) / .pi
                let swell = 1 + m.speak * (0.06 * spectrum.band(at: pos) + 0.03 * loud * sin(6 * a - t * 4))
                cx = rr * swell * cos(a); cy = rr * swell * sin(a)
                cb = (0.62 + 0.25 * sin(t * 1.3 + h3 * 30)) * (1 + 0.4 * m.listen * level) * (1 - 0.45 * m.speak)
                    + m.speak * (0.9 * pow(lit, 3) * (0.5 + 0.7 * loud) + flare)
                hue = 0.05 * h2
            } else if role < 9 {
                let j = Int(h3 * Double(streamers)) % streamers
                let fIn = frac(h2 - 0.3 * t), fOut = frac(h2 + 0.35 * t)
                let f = corona > 0.003 ? (m.rest * h2 + m.listen * fIn + m.speak * fOut) / corona : h2
                let rr = R + sLen[j] * pow(f, 1.5)
                // Fine striations inside a broad streamer, as in a photograph of the corona.
                var off = (h1 - 0.5) * sWidth[j]
                if i % 2 == 0 { off = (off / 0.045).rounded() * 0.045 }
                let sa = sAngle[j] + off * (1 - 0.6 * f)
                cx = rr * cos(sa); cy = rr * sin(sa)
                cb = 0.6 * pow(1 - f, 1.4) * (1 - 1.2 * abs(off) / sWidth[j]) * (1 + 0.5 * m.listen * level + 0.4 * m.speak * loud)
                hue = min(1, 0.1 + 0.95 * f)
            } else if i % 30 == 9 {                                            // the bright point at the heart
                let r = 0.03 * h2
                cx = r * cos(a); cy = r * sin(a)
                cb = (m.rest + m.listen) / max(0.003, corona) * 0.9
                hue = 0
            } else {
                let rr = R + 0.7 * h2 * h2
                cx = rr * cos(a); cy = rr * sin(a)
                cb = 0.24 * (1 - h2)
                hue = 0.3 + 0.6 * h2
            }
            bl.add(corona, cx, cy, 0, cb)
            // Thinking: the lit crescent turning, and three tilted orbits.
            if m.think > 0.003 {
                if role < 4 {
                    let lit = max(0, cos(a - lightA))
                    bl.add(m.think, R * cos(a), R * sin(a), 0, 0.15 + 0.95 * pow(lit, 2))
                } else if role < 7 {
                    let o = role % 3, tilt = [0.35, -0.6, 1.1][o], rr = 0.9 + 0.12 * Double(o)
                    let oa = a + t * (0.4 + 0.15 * Double(o))
                    let x = rr * cos(oa), y = rr * sin(oa) * 0.32
                    bl.add(m.think, x * cos(tilt) - y * sin(tilt), x * sin(tilt) + y * cos(tilt), 0, 0.32)
                } else {
                    bl.add(m.think, cx, cy, 0, cb * 0.5)
                }
            }
            // Working: a shutter on the left half (six blades) and rays fanning to the right.
            if m.work > 0.003 {
                if role < 3 {
                    let la = Double.pi / 2 + Double.pi * h1                      // the left half's rim
                    bl.add(m.work, R * cos(la), R * sin(la), 0, 0.6)
                } else if role < 5 {
                    let blade = Int(h1 * 6), f = frac(h1 * 6)
                    let rot = t * 0.8
                    let a0 = Double(blade) * .pi / 3 + rot, a1 = a0 + .pi / 3
                    let inner = 0.18
                    let x0 = inner * cos(a0), y0 = inner * sin(a0), x1 = R * cos(a1 - 0.5), y1 = R * sin(a1 - 0.5)
                    let x = x0 + (x1 - x0) * f, y = y0 + (y1 - y0) * f
                    bl.add(m.work, x < 0.02 ? x : -x, y, 0, 0.16)
                } else if role < 8 {
                    let ray = Int(h2 * 9), ra = -0.55 + 1.1 * Double(ray) / 8, len = 1.0 + 0.5 * OrbPoints.hash(ray, 5)
                    let f = h1
                    let pulse = pow(max(0, sin((f - t * 1.2) * 2 * .pi)), 6)
                    let rr = R + f * (len - R)
                    bl.add(m.work, rr * cos(ra), rr * sin(ra), 0, (0.25 + 0.6 * pulse) * (1 - 0.5 * f) + (f > 0.96 ? 0.6 : 0))
                } else {
                    bl.add(m.work, cx, cy, 0, cb * 0.6)
                }
            }
            put(&d, bl.x * k, bl.y * k, bl.b, hue, i, phase: a, lum: min(1, bl.b))
        }
        // The corona's light: a soft glow hugging the rim, fading out through amber to violet, and a
        // soft wedge of light under each streamer; thinking, the orbits as faint rings.
        let hs = look.color == nil ? Self.eclipseHues : OrbPalette.hues(for: look.color)
        let rimLight = 0.5 + 0.2 * m.listen * level + 0.3 * m.speak * loud + 0.2 * m.think
        finishHue(&gc, d, hues: Self.eclipseHues) { c in
            let center = CGPoint(x: d.cx, y: d.cy), Rp = R * k * d.R, outer = Rp * 2.6
            c.fill(Path(ellipseIn: CGRect(x: d.cx - outer, y: d.cy - outer, width: 2 * outer, height: 2 * outer)),
                   with: .radialGradient(Gradient(stops: [.init(color: .clear, location: 0.35),
                                                          .init(color: hs[0][4].opacity(0.7 * rimLight), location: 1 / 2.6),
                                                          .init(color: hs[0][3].opacity(0.32 * rimLight), location: 1.12 / 2.6),
                                                          .init(color: hs[1][2].opacity(0.14 * rimLight), location: 1.4 / 2.6),
                                                          .init(color: hs[3][2].opacity(0.06 * rimLight), location: 1.9 / 2.6),
                                                          .init(color: .clear, location: 1)]),
                                         center: center, startRadius: 0, endRadius: outer))
            if corona > 0.01 {
                var wedges = Path()
                for j in 0..<streamers {
                    let a = sAngle[j], w = sWidth[j] * 0.55, tip = R + sLen[j] * 1.1
                    func pt(_ r: Double, _ a: Double) -> CGPoint { CGPoint(x: d.cx + r * k * d.R * cos(a), y: d.cy + r * k * d.R * sin(a)) }
                    wedges.move(to: pt(R * 0.98, a - w))
                    wedges.addQuadCurve(to: pt(tip, a), control: pt(R + 0.45 * sLen[j], a - 0.45 * w))
                    wedges.addQuadCurve(to: pt(R * 0.98, a + w), control: pt(R + 0.45 * sLen[j], a + 0.45 * w))
                    wedges.closeSubpath()
                }
                var cc = c
                cc.opacity = corona
                cc.fill(wedges, with: .radialGradient(Gradient(stops: [.init(color: hs[0][3].opacity(0.55), location: 0),
                                                                       .init(color: hs[1][2].opacity(0.3), location: 0.35),
                                                                       .init(color: hs[3][2].opacity(0.1), location: 0.75),
                                                                       .init(color: .clear, location: 1)]),
                                                      center: center, startRadius: Rp, endRadius: Rp * 2.7))
            }
            if m.work > 0.01 {
                // Working: the fan of rays as soft light.
                var fan = Path()
                for ray in 0..<9 {
                    let ra = -0.55 + 1.1 * Double(ray) / 8, len = (1.0 + 0.5 * OrbPoints.hash(ray, 5)) * k * d.R
                    func pt(_ r: Double, _ a: Double) -> CGPoint { CGPoint(x: d.cx + r * cos(a), y: d.cy + r * sin(a)) }
                    fan.move(to: pt(Rp, ra - 0.05)); fan.addLine(to: pt(len, ra)); fan.addLine(to: pt(Rp, ra + 0.05)); fan.closeSubpath()
                }
                var cc = c
                cc.opacity = m.work
                cc.fill(fan, with: .radialGradient(Gradient(colors: [hs[0][3].opacity(0.6), hs[1][2].opacity(0.3), hs[3][2].opacity(0.1), .clear]),
                                                   center: center, startRadius: Rp, endRadius: Rp * 2.5))
            }
            if m.think > 0.01 {
                var orbits = Path()
                for o in 0..<3 {
                    let tilt = [0.35, -0.6, 1.1][o], rr = (0.9 + 0.12 * Double(o)) * k * d.R
                    orbits.addPath(Path(ellipseIn: CGRect(x: -rr, y: -rr * 0.32, width: 2 * rr, height: 2 * rr * 0.32)),
                                   transform: CGAffineTransform(rotationAngle: tilt).concatenating(CGAffineTransform(translationX: d.cx, y: d.cy)))
                }
                c.stroke(orbits, with: .color(hs[2][2].opacity(0.4 * m.think)), lineWidth: d.px * 1.6)
            }
        }
    }

    /// Eclipse's hues: gold at the rim, amber, rose-violet, violet at the corona's edge.
    static let eclipseHues: [[Color]] = [
        OrbPalette.levels(0x8a5a1c, 0xb7791f, 0xe0a54a, 0xf6c96f, 0xfff3d6),
        OrbPalette.levels(0x8c3f1f, 0xc2622f, 0xf0965a, 0xfbbf8a, 0xffe9d6),
        OrbPalette.levels(0x6d2a7a, 0x9b3fa8, 0xc67ad6, 0xe0aef0, 0xf8e8ff),
        OrbPalette.levels(0x3b2470, 0x5b3aa6, 0x7b5fd6, 0xa58cf0, 0xe8e0ff),
    ]

    // MARK: Synapse

    /// A network of nodes and their links. Listening, a compact cluster that pulses with your voice;
    /// thinking, it spreads into a large tangled network with signals running along its links;
    /// working, hubs at its centre and nodes travelling on orbits around them; speaking, a starburst
    /// from a central node, the links lighting outward with the voice. Soft light runs along the
    /// links; the nodes glow, cyan at the top to violet and rose below.
    func drawSynapse(_ gc: inout GraphicsContext, _ box: CGSize) {
        var d = hueDots(box)
        let m = StateMix(engine)
        let level = engine.history.value(secondsAgo: 0.05), loud = engine.loud
        let nodes = ConceptGeometry.nodes, links = ConceptGeometry.links
        let view = View3(yaw: t * 0.15 + engine.ringTurn * 0.6, pitch: 0.3)
        let k = 1.38
        var pos: [(x: Double, y: Double, z: Double, b: Double)] = []
        pos.reserveCapacity(nodes.count)
        for (i, u) in nodes.enumerated() {
            let h = OrbPoints.hash(i, 7)
            var bl = Blend()
            let r0 = 0.52 * (1 + 0.25 * m.listen * level * h) + 0.02 * sin(t * 1.3 + Double(i))
            bl.add(m.rest + m.listen, u.0 * r0, u.1 * r0, u.2 * r0, 0.75 + 0.6 * m.listen * level)
            let wob = 0.08 * sin(t * 0.7 + Double(i) * 1.7)
            let r1 = 0.6 + 0.55 * h + wob
            bl.add(m.think, u.0 * r1, u.1 * r1 * 0.85, u.2 * r1, 0.8)
            if i < 3 {
                bl.add(m.work, 0.18 * cos(Double(i) * 2.1), 0.18 * sin(Double(i) * 2.1), 0, 1.2)
            } else {
                let ring = i % 3, tilt = [0.3, -0.45, 1.2][ring]
                let a = 2 * Double.pi * Double(i / 3) / Double(nodes.count / 3) + t * (0.35 + 0.15 * Double(ring)) * (ring == 1 ? -1 : 1)
                let rr = 0.75 + 0.18 * Double(ring)
                let x = rr * cos(a), y = rr * sin(a) * 0.35
                bl.add(m.work, x * cos(tilt) - y * sin(tilt), x * sin(tilt) + y * cos(tilt), rr * sin(a) * 0.3, 0.75)
            }
            if i == 0 {
                bl.add(m.speak, 0, 0, 0, 1.3 + loud)
            } else {
                let past = engine.history.value(secondsAgo: h * 0.8)
                let r2 = (0.55 + 0.6 * h) * (1 + 0.32 * past)
                bl.add(m.speak, u.0 * r2, u.1 * r2, u.2 * r2, 0.65 + 0.7 * past)
            }
            let p = view.apply(bl.x, bl.y, bl.z)
            var x = p.x * k, y = p.y * k
            let b = bl.b * depthLight(p.z) + workEffect(&x, &y, phase: Double(i))
            pos.append((x, y, p.z, b))
        }
        let hs = OrbPalette.hues(for: look.color)
        /// The form's gradient, top to bottom (cyan, indigo, violet, rose), for the links and the nodes.
        func shading(_ level: Int, _ alpha: Double) -> GraphicsContext.Shading {
            .linearGradient(Gradient(colors: hs.map { $0[level].opacity(alpha) }),
                            startPoint: CGPoint(x: d.cx, y: d.cy - 1.05 * d.R), endPoint: CGPoint(x: d.cx, y: d.cy + 1.15 * d.R))
        }
        // The links: the network's own (faint as it speaks), and the starburst's spokes.
        var lines = [Path](repeating: Path(), count: 4)
        func link(_ a: Int, _ b: Int, _ bright: Double) {
            guard bright > 0.04 else { return }
            let level = min(3, max(0, Int(bright * 4)))
            lines[level].move(to: CGPoint(x: d.cx + pos[a].x * d.R, y: d.cy + pos[a].y * d.R))
            lines[level].addLine(to: CGPoint(x: d.cx + pos[b].x * d.R, y: d.cy + pos[b].y * d.R))
        }
        for (k, l) in links.enumerated() {
            let base = (0.4 + 0.2 * m.think + 0.3 * m.listen * level) * (1 - m.speak)
            link(l.0, l.1, base + 0.15 * sin(t + Double(k)))
        }
        for i in 1..<nodes.count {
            let past = engine.history.value(secondsAgo: OrbPoints.hash(i, 7) * 0.8)
            link(0, i, m.speak * (0.3 + 0.7 * past))
        }
        // Thinking: signals running along the links.
        if m.think > 0.02 {
            for (k, l) in links.enumerated() where k % 2 == 0 {
                let f = frac(t * 0.7 + OrbPoints.hash(k, 9))
                let a = pos[l.0], b = pos[l.1]
                d.dot(a.x + (b.x - a.x) * f, a.y + (b.y - a.y) * f, 1.1 * m.think, 0.1 + 0.8 * frac(a.y + 1.5), 0.5, 0.5, size: 2.2)
            }
        }
        // Dust around it.
        for j in 0..<Int(Double(pointBudget(box)) * 0.15) {
            let u = ConceptGeometry.direction((j * 389) % 997), r = 0.5 + 1.1 * OrbPoints.hash(j, 3)
            let p = view.apply(u.0 * r, u.1 * r, u.2 * r)
            d.dot(p.x * k, p.y * k, (0.1 + 0.12 * sin(t + Double(j))) * depthLight(p.z), OrbPoints.hash(j, 4), OrbPoints.hash(j, 14), OrbPoints.hash(j, 15))
        }
        // The nodes: a round core (the hubs larger), and its glow in the bloom.
        var cores = [Path](repeating: Path(), count: 5), halos = [Path](repeating: Path(), count: 3)
        for (i, p) in pos.enumerated() {
            let cxp = d.cx + p.x * d.R, cyp = d.cy + p.y * d.R
            let core = d.px * (1.5 + 1.0 * min(1.2, p.b) + (i < 3 ? 0.8 * m.work : 0) + (i == 0 ? 1.4 * m.speak : 0))
            cores[min(4, max(0, Int(p.b * 4)))].addEllipse(in: CGRect(x: cxp - core, y: cyp - core, width: 2 * core, height: 2 * core))
            let g = core * 2.6
            halos[min(2, max(0, Int(p.b * 2.2)))].addEllipse(in: CGRect(x: cxp - g, y: cyp - g, width: 2 * g, height: 2 * g))
        }
        let lw = max(0.5, d.px * 0.75)
        finishHue(&gc, d) { c in
            for level in 0..<4 where !lines[level].isEmpty {
                c.stroke(lines[level], with: shading(2, 0.2 + 0.2 * Double(level)), lineWidth: lw * 4)
            }
            for level in 0..<3 where !halos[level].isEmpty { c.fill(halos[level], with: shading(3, 0.3 + 0.22 * Double(level))) }
        }
        for level in 0..<4 where !lines[level].isEmpty {
            gc.stroke(lines[level], with: shading(3, 0.25 + 0.2 * Double(level)), lineWidth: lw)
        }
        for b in 0..<5 where !cores[b].isEmpty { gc.fill(cores[b], with: shading(min(4, b + 1), 0.75 + 0.06 * Double(b))) }
    }

    // MARK: Drop

    /// A drop of light. Listening, a drop wobbling with your voice over rings that ripple out;
    /// thinking, it whirls into a spiral vortex; working, it unravels into fibres fanning out to
    /// nodes; speaking, a horn of particles pours out of it, opening wider with the voice. Cyan at
    /// its tip, violet and rose where it is full.
    func drawDrop(_ gc: inout GraphicsContext, _ box: CGSize) {
        var d = hueDots(box)
        let m = StateMix(engine)
        let n = pointBudget(box)
        let level = engine.history.value(secondsAgo: 0.05)
        let view = View3(yaw: t * 0.1, pitch: 0.42)
        let flat = View3(yaw: 0, pitch: 0.2)
        let surface = Int(Double(n) * 0.66)
        let k = 1.5 - 0.22 * (m.work + m.speak), lift = 0.12 * (m.rest + m.listen)
        for i in 0..<n {
            let h1 = OrbPoints.hash(i, 1), h2 = OrbPoints.hash(i, 2), h3 = OrbPoints.hash(i, 3)
            var bl = Blend()
            let th = 2 * Double.pi * h1
            var hue = 0.3
            if i < surface {
                // The drop: pointed at the top, round below; wobbling with your voice.
                let tt = Double.pi * pow(h2, 0.8)
                let wob = 1 + 0.08 * m.listen * level * sin(3 * th + t * 5) + 0.015 * sin(t * 1.4)
                let r = 0.62 * sin(tt) * pow(sin(tt / 2), 1.3) * wob
                let y = 0.25 - 1.0 * (1 + cos(tt)) / 2
                let rim = 0.45 + 0.55 * pow(abs(cos(th)), 6) + 0.35 * smoothstep(0.85, 1, h2)
                hue = 0.05 + 0.7 * pow(h2, 1.2) + 0.15 * pow(abs(sin(th)), 4)
                bl.add(m.rest + m.listen, r * cos(th), y, r * sin(th), rim)
            } else {
                // The rings under it, rippling out as you speak.
                let ring = Double(i % 3)
                let rr = 0.68 + 0.22 * ring + 0.4 * m.listen * frac(t * 0.5 + ring / 3)
                let past = engine.history.value(secondsAgo: (rr - 0.68) * 1.2)
                hue = 0.35 + 0.25 * ring
                bl.add(m.rest + m.listen, rr * cos(th), 0.28, rr * sin(th), 0.36 + 0.7 * m.listen * past)
            }
            // Thinking: a vortex of three arms.
            if m.think > 0.003 {
                let r = 0.05 + 1.15 * pow(h2, 0.7)
                let arm = Double(i % 3)
                let a = arm * 2 * .pi / 3 + 2.4 * log(r + 0.06) - t * 1.3 + 0.35 * (h3 - 0.5)
                hue += (0.08 + 0.8 * r / 1.2 - hue) * m.think
                bl.add(m.think, r * cos(a), 0.05 * (h3 - 0.5), r * sin(a), 0.4 + 0.6 * (1 - r / 1.2))
            }
            // Working: fibres from a bundle on the left fanning out to nodes on the right.
            if m.work > 0.003 {
                let fibre = i % 16, u = h2
                let endY = (Double(fibre) - 7.5) * 0.12, endZ = 0.25 * sin(Double(fibre) * 1.3)
                let x = -1.3 + 2.5 * u
                let y = 0.1 + endY * pow(u, 1.6) + 0.04 * sin(u * 9 + t * 3 + Double(fibre))
                hue += (0.1 + 0.8 * u - hue) * m.work
                if fibre % 4 == 0 && u > 0.93 {
                    let q = 2 * Double.pi * h3
                    bl.add(m.work, 1.2 + 0.08 * cos(q), 0.1 + endY + 0.08 * sin(q), endZ, 0.95)
                } else {
                    let pulse = pow(max(0, sin((u - t * 0.8) * 2 * .pi)), 8)
                    bl.add(m.work, x, y, endZ * u, 0.35 + 0.7 * pulse)
                }
            }
            // Speaking: a horn of particles pouring out to the right, wider with the voice.
            if m.speak > 0.003 {
                // Streamlines: sixteen lines along a horn that bends up and opens like a bell.
                let s = frac(h2 + t * 0.45)
                let past = engine.history.value(secondsAgo: s * 1.1)
                let line = Double(i % 16), ang = 2 * Double.pi * line / 16 + 0.6 * s * s + 0.04 * (h3 - 0.5)
                let rad = (0.04 + 0.85 * pow(s, 2.1)) * (0.75 + 0.6 * past)
                let x = -1.0 + 1.9 * s - 0.25 * pow(s, 3), y = 0.2 - 0.35 * s * s
                let rimLight = smoothstep(0.75, 1, s) * 0.6
                hue += (0.05 + 0.9 * s - hue) * m.speak
                bl.add(m.speak, x + 0.15 * rad * cos(ang), y + rad * cos(ang) * 0.95, rad * sin(ang), (0.35 + 0.7 * past) * (0.9 - 0.4 * s) + rimLight)
            }
            let flatShare = m.work + m.speak
            let p1 = view.apply(bl.x, bl.y, bl.z), p2 = flat.apply(bl.x, bl.y, bl.z)
            let x = p1.x + (p2.x - p1.x) * flatShare, y = p1.y + (p2.y - p1.y) * flatShare, z = p1.z + (p2.z - p1.z) * flatShare
            put(&d, x * k, y * k + lift, bl.b * depthLight(z), hue, i, phase: th, lum: min(1, bl.b))
        }
        // The drop's body of light: its outline filled with a soft gradient while it is a drop.
        let hs = OrbPalette.hues(for: look.color)
        let held = m.rest + m.listen
        finishHue(&gc, d) { c in
            guard held > 0.01 else { return }
            var drop = Path()
            let cP = cos(0.42)
            for j in 0...40 {
                let tt = Double.pi * Double(j) / 40
                let wob = 1 + 0.015 * sin(t * 1.4)
                let r = 0.62 * sin(tt) * pow(sin(tt / 2), 1.3) * wob
                let y = (0.25 - 1.0 * (1 + cos(tt)) / 2) * cP
                let pt = CGPoint(x: d.cx + r * k * d.R, y: d.cy + (y * k + lift) * d.R)
                if j == 0 { drop.move(to: pt) } else { drop.addLine(to: pt) }
            }
            for j in stride(from: 39, through: 1, by: -1) {
                let tt = Double.pi * Double(j) / 40
                let r = 0.62 * sin(tt) * pow(sin(tt / 2), 1.3) * (1 + 0.015 * sin(t * 1.4))
                let y = (0.25 - 1.0 * (1 + cos(tt)) / 2) * cP
                drop.addLine(to: CGPoint(x: d.cx - r * k * d.R, y: d.cy + (y * k + lift) * d.R))
            }
            drop.closeSubpath()
            var cc = c
            cc.opacity = held * (0.85 + 0.3 * m.listen * level)
            let focus = CGPoint(x: d.cx - 0.15 * k * d.R, y: d.cy + (-0.05 * k + lift) * d.R)
            cc.fill(drop, with: .radialGradient(Gradient(stops: [.init(color: hs[0][3].opacity(0.4), location: 0),
                                                                 .init(color: hs[1][2].opacity(0.3), location: 0.45),
                                                                 .init(color: hs[2][2].opacity(0.3), location: 0.8),
                                                                 .init(color: hs[3][2].opacity(0.25), location: 1)]),
                                                center: focus, startRadius: 0, endRadius: 0.75 * k * d.R))
        }
    }
}

/// Fixed shapes the orbs share: an icosahedron and its edges, even directions on a sphere, the
/// network's nodes and links.
enum ConceptGeometry {
    typealias V = (Double, Double, Double)
    static let icosahedron: [V] = {
        let p = (1 + 5.0.squareRoot()) / 2, s = 1 / (1 + p * p).squareRoot()
        return [(-1, p, 0), (1, p, 0), (-1, -p, 0), (1, -p, 0), (0, -1, p), (0, 1, p),
                (0, -1, -p), (0, 1, -p), (p, 0, -1), (p, 0, 1), (-p, 0, -1), (-p, 0, 1)].map { ($0.0 * s, $0.1 * s, $0.2 * s) }
    }()
    static let icosaEdges: [(Int, Int)] = {
        var out: [(Int, Int)] = []
        for a in 0..<12 {
            for b in (a + 1)..<12 {
                let p = icosahedron[a], q = icosahedron[b]
                let d = (p.0 - q.0) * (p.0 - q.0) + (p.1 - q.1) * (p.1 - q.1) + (p.2 - q.2) * (p.2 - q.2)
                if d < 1.2 { out.append((a, b)) }                      // the 30 shortest: the edges
            }
        }
        return out
    }()
    /// Its 20 faces: the triples of vertices joined to each other.
    static let icosaFaces: [(Int, Int, Int)] = {
        var out: [(Int, Int, Int)] = []
        func joined(_ a: Int, _ b: Int) -> Bool { icosaEdges.contains { ($0.0 == a && $0.1 == b) || ($0.0 == b && $0.1 == a) } }
        for a in 0..<12 { for b in (a + 1)..<12 where joined(a, b) { for c in (b + 1)..<12 where joined(a, c) && joined(b, c) { out.append((a, b, c)) } } }
        return out
    }()
    /// An even direction on the sphere (a Fibonacci spiral), by index.
    static func direction(_ i: Int) -> V {
        let k = Double(i % 997) + 0.5
        let z = 1 - 2 * k / 997, r = max(0, 1 - z * z).squareRoot(), a = k * 2.39996
        return (r * cos(a), z, r * sin(a))
    }
    static let nodes: [V] = (0..<30).map { i in
        let k = Double(i) + 0.5, z = 1 - 2 * k / 30, r = max(0, 1 - z * z).squareRoot(), a = k * 2.39996
        return (r * cos(a), z, r * sin(a))
    }
    /// Each node joined to its three nearest.
    static let links: [(Int, Int)] = {
        var out: [(Int, Int)] = []
        for a in 0..<nodes.count {
            let near = (0..<nodes.count).filter { $0 != a }.sorted { b, c in
                dist(nodes[a], nodes[b]) < dist(nodes[a], nodes[c])
            }.prefix(3)
            for b in near where !out.contains(where: { ($0.0 == a && $0.1 == b) || ($0.0 == b && $0.1 == a) }) { out.append((a, b)) }
        }
        return out
    }()
    private static func dist(_ p: V, _ q: V) -> Double { (p.0 - q.0) * (p.0 - q.0) + (p.1 - q.1) * (p.1 - q.1) + (p.2 - q.2) * (p.2 - q.2) }
}

// MARK: - Wave

extension OrbCanvas {
    /// Ribbons of light across the screen, each a band of the voice (its own harmonic), coloured
    /// from blue through violet and rose to amber and green, overlapping in light. At rest a gentle
    /// swell; listening, the waves come in from the edges with your voice; thinking, slow crossing
    /// undulations; working, the ribbons wind into a turning swirl; speaking, the waves travel out
    /// from the centre, rising with its voice.
    func drawWave(_ gc: inout GraphicsContext, _ box: CGSize) {
        let ph = OrbPhases(engine)
        let W = Double(box.width), H = Double(box.height)
        let cx = W / 2, cy = H / 2
        let span = W * 0.47, amp = min(W, H) * 0.3
        let swirlR = min(W, H) * 0.4
        let ribbons = 5, samples = 72
        let w = ph.work * ph.work * (3 - 2 * ph.work)
        let voiced = ph.listen + ph.speak
        let colors: [Color] = look.color.map { c in [c.opacity(0.7), c, c.opacity(0.85), .white.opacity(0.8), c.opacity(0.7)] }
            ?? [Color(hex: 0x38bdf8), Color(hex: 0x6366f1), Color(hex: 0xa855f7), Color(hex: 0xf472b6), Color(hex: 0xfb923c), Color(hex: 0x4ade80)]
        let shading = GraphicsContext.Shading.linearGradient(Gradient(colors: colors), startPoint: CGPoint(x: cx - span, y: cy),
                                                              endPoint: CGPoint(x: cx + span, y: cy))
        var fills: [Path] = [], lines: [Path] = []
        for k in 0..<ribbons {
            let fk = Double(k)
            // Each ribbon its own band (low pitches the first), its own frequency and pace.
            let band = ph.spectrum.band(at: fk / Double(ribbons - 1))
            let rest = 0.1 * (1 - 0.12 * fk) * (0.8 + 0.2 * sin(t * 0.7 + fk))
            let voice = voiced * (0.12 + 1.1 * band + 0.25 * ph.loud)
            let thinking = ph.think * (0.32 + 0.08 * sin(t * 0.5 + fk * 1.7))
            let a = rest * (1 - voiced - ph.think) + voice + thinking
            let freq = 1.3 + 0.55 * fk
            // Each motion at a fixed pace, the phases blending how much of each shows (a pace
            // that changed with the phase would jump: it multiplies the clock): calm, thinking
            // (slower, the ribbons turning against each other), and the voice travelling out from
            // the centre as it speaks, in toward it as you speak.
            let pace = 0.6 + 0.25 * fk, offset = fk * 1.3
            let counter = 0.4 * t * (k % 2 == 0 ? 1 : -1)
            let calmW = max(0, 1 - voiced - ph.think)
            var outer: [CGPoint] = [], inner: [CGPoint] = []
            for i in 0...samples {
                let u = Double(i) / Double(samples), x = 2 * u - 1
                // A shape that peaks in the middle and fades at the ends.
                let env = pow(1 - x * x, 2) * (0.35 + 0.65 * exp(-x * x / 0.22))
                let calm = sin(freq * .pi * x - pace * t + offset)
                let thought = sin(freq * .pi * x - 0.5 * pace * t + offset + counter)
                let out = sin(freq * .pi * abs(x) - 3.2 * pace * t + offset)
                let into = sin(-freq * .pi * abs(x) - 3.2 * pace * t + offset)
                let y = a * env * (calmW * calm + ph.think * thought + ph.speak * out + ph.listen * into)
                // The wave, and its swirl (each ribbon an arm of a turning spiral).
                let wx = cx + x * span, wy = cy - y * amp, wyIn = cy - y * amp * 0.12
                let sa = 2 * .pi * (1.5 * u) + t * 1.6 + fk * 2 * .pi / Double(ribbons)
                let sr = swirlR * (0.12 + 0.88 * u) * (1 + 0.06 * sin(u * 12 - t * 4))
                let sx = cx + sr * cos(sa), sy = cy + sr * sin(sa) * 0.92
                let sri = sr * 0.8, sai = sa - 0.12
                let ix = cx + sri * cos(sai), iy = cy + sri * sin(sai) * 0.92
                outer.append(CGPoint(x: wx + (sx - wx) * w, y: wy + (sy - wy) * w))
                inner.append(CGPoint(x: wx + (ix - wx) * w, y: wyIn + (iy - wyIn) * w))
            }
            var fill = Path(), line = Path()
            fill.move(to: outer[0]); line.move(to: outer[0])
            for p in outer.dropFirst() { fill.addLine(to: p); line.addLine(to: p) }
            for p in inner.reversed() { fill.addLine(to: p) }
            fill.closeSubpath()
            fills.append(fill); lines.append(line)
        }
        let lw = max(0.7, min(W, H) / 180)
        // A glow under it, then the translucent bodies adding up in light, then the bright edges.
        gc.drawLayer { layer in
            layer.addFilter(.blur(radius: lw * 5))
            layer.opacity = 1 - 0.5 * w
            for f in fills { layer.fill(f, with: shading) }
        }
        gc.opacity = 0.32 * (1 - 0.45 * w)
        for f in fills { gc.fill(f, with: shading) }
        gc.opacity = 0.9
        for l in lines { gc.stroke(l, with: shading, lineWidth: lw) }
        gc.opacity = 1
        // The centre line, faint.
        var base = Path()
        base.move(to: CGPoint(x: cx - span, y: cy)); base.addLine(to: CGPoint(x: cx + span, y: cy))
        gc.opacity = 0.35 * (1 - w)
        gc.stroke(base, with: shading, lineWidth: lw * 0.6)
        gc.opacity = 1
    }
}
