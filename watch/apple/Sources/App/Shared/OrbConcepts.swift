import SwiftUI

// Five orbs with one shape per state of the assistant (listening, thinking, working with its
// tools, speaking; at rest a calm listening shape), the points morphing from one to the next as the
// state changes: Lotus (a bud that blooms), Crystal (a crystal that grows wings), Eclipse (a golden
// eclipse), Synapse (a network of nodes) and Drop (a drop of light). Units as the planet (1 = its
// radius, y down).

/// How much of each state is happening now (they sum to 1): the weights each point's place in each
/// state's shape is blended with.
private struct StateMix {
    let rest: Double, listen: Double, think: Double, work: Double, speak: Double
    init(_ e: OrbEngine) {
        var speak = e.engagement * e.talking
        var listen = e.engagement * (1 - e.talking)
        let busy = (1 - e.engagement) * e.thinking
        var work = busy * e.working
        var think = busy * (1 - e.working)
        let sum = speak + listen + work + think
        if sum > 1 { speak /= sum; listen /= sum; work /= sum; think /= sum }
        self.speak = speak; self.listen = listen; self.work = work; self.think = think
        rest = max(0, 1 - speak - listen - work - think)
    }
}

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

    // MARK: Lotus

    /// Listening, a closed bud breathing with your voice over rings of light; thinking, its petals
    /// open and twist; working, it becomes a branching network, a glowing node at each tip; speaking,
    /// a full bloom, its petals opening wider and its stamens reaching up with the voice. A thread of
    /// light falls from its base.
    func drawLotus(_ gc: inout GraphicsContext, _ box: CGSize) {
        var d = dotCanvas(box)
        let m = StateMix(engine)
        let n = pointBudget(box)
        let level = engine.history.value(secondsAgo: 0.05), loud = engine.loud
        let spectrum = VoiceFeatures(level: loud, bands: engine.bands)
        let view = View3(yaw: t * 0.12 + 0.3 * m.think * sin(t * 0.4), pitch: 0.38)
        let base = (x: 0.0, y: 0.38, z: 0.0)
        let petals = Int(Double(n) * 0.7), stamens = Int(Double(n) * 0.13)
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
            if i < petals {
                let layer = i % 2, p = (i / 2) % 8, u = h1
                // Most points on the petal's outline (it reads as a petal), a few inside.
                let onEdge = OrbPoints.hash(i, 5) < 0.6
                let v = onEdge ? (h2 < 0.5 ? -1.0 : 1.0) * (0.94 + 0.06 * OrbPoints.hash(i, 6)) : 2 * h2 - 1
                let edge = onEdge ? 0.8 : 0.22
                let tip = 0.5 * smoothstep(0.85, 1, u)
                let outer = layer == 0
                let bud = petal(layer, p, u, v, phi: (outer ? 0.36 : 0.2) + 0.14 * level * m.listen, twist: 0.25, len: outer ? 0.78 : 0.7, spread: 0.85)
                bl.add(m.rest + m.listen, bud.0, bud.1, bud.2, edge + tip * (0.5 + m.listen * level))
                let turning = petal(layer, p, u, v, phi: outer ? 0.75 : 0.42, twist: 0.9 + 0.5 * sin(t * 0.6), len: 0.85, spread: 0.8)
                bl.add(m.think, turning.0, turning.1, turning.2, edge + tip)
                let open = petal(layer, p, u, v, phi: (outer ? 1.28 : 0.74) + 0.2 * loud, twist: 0.05, len: outer ? 0.98 : 0.82, spread: 1)
                bl.add(m.speak, open.0, open.1, open.2, edge + tip + 0.5 * loud)
                if m.work > 0.003 {
                    // A branch per petal, rising and leaning out; a node (a small square) at its tip.
                    let br = layer * 8 + p
                    let ab = 2 * Double.pi * Double(br) / 16 + 0.2 * sin(Double(br))
                    let reach = 0.55 + 0.45 * OrbPoints.hash(br, 7)
                    let tipX = reach * 1.05 * cos(ab), tipZ = reach * 1.05 * sin(ab), tipY = base.y - 1.15 * reach
                    if abs(v) > 0.78 {
                        let q = (abs(v) - 0.78) / 0.22 * 4
                        let side = 0.06
                        let sx = q < 1 ? -side + 2 * side * q : (q < 2 ? side : (q < 3 ? side - 2 * side * (q - 2) : -side))
                        let sy = q < 1 ? -side : (q < 2 ? -side + 2 * side * (q - 1) : (q < 3 ? side : side - 2 * side * (q - 3)))
                        bl.add(m.work, tipX + sx, tipY + sy, tipZ, 0.95)
                    } else {
                        let f = u
                        let x = tipX * f * f, z = tipZ * f * f, y = base.y + (tipY - base.y) * f
                        let pulse = 0.35 + 0.6 * pow(max(0, sin((f - t * 0.9) * 2 * .pi)), 8)
                        bl.add(m.work, x, y, z, pulse)
                    }
                }
            } else if i < petals + stamens {
                // Stamens: hidden in the bud; reaching up with the voice in the bloom.
                let f = (i - petals) % 24, u = h1
                let af = 2 * Double.pi * Double(f) / 24, tilt = 0.15 + 0.5 * OrbPoints.hash(f, 3)
                let bandLen = 0.35 + 0.7 * spectrum.band(at: Double(f % 8) / 7) * m.speak
                let tipB = u > 0.92 ? 1.0 : 0.4
                let len = 0.25 + 0.35 * OrbPoints.hash(f, 4)
                bl.add(m.rest + m.listen, 0.05 * cos(af) * u, base.y - 0.3 * u, 0.05 * sin(af) * u, 0.2)
                bl.add(m.think, 0.3 * sin(tilt) * cos(af) * u, base.y - 0.45 * u, 0.3 * sin(tilt) * sin(af) * u, 0.35 * tipB)
                bl.add(m.speak, (len + bandLen) * sin(tilt) * cos(af) * u, base.y - (len + bandLen) * cos(tilt) * u, (len + bandLen) * sin(tilt) * sin(af) * u, tipB)
                // Working: rings of light at the base.
                let ra = 2 * Double.pi * h1, rr = 0.45 + 0.3 * Double(f % 2)
                bl.add(m.work, rr * cos(ra), base.y + 0.05, rr * sin(ra), 0.35)
            } else {
                // The thread of light below and the rings around the base (rippling as you speak).
                if i % 3 == 0 {
                    let ring = Double(i % 2)
                    let r = 0.45 + 0.35 * ring + 0.35 * m.listen * frac(t * 0.6 + ring * 0.5)
                    let a = 2 * Double.pi * h1
                    bl.add(1, r * cos(a), base.y + 0.06, r * sin(a), 0.25 + 0.6 * m.listen * level)
                } else {
                    let f = frac(h1 + t * 0.35)
                    bl.add(1, 0.04 * (h2 - 0.5) * (1 + f), base.y + 0.1 + 1.5 * f, 0.03 * (h2 - 0.5), 0.55 * (1 - f))
                }
            }
            let p = view.apply(bl.x, bl.y, bl.z)
            place(&d, p.x * 1.2, p.y * 1.2 - 0.05, bl.b * depthLight(p.z), OrbPoints.hash(i, 14), phase: h1 * 6.3, lum: min(1, bl.b))
        }
        finish(&gc, d)
    }

    // MARK: Crystal

    /// Listening, a small faceted crystal turning slowly in a haze of sparkles that draw in with your
    /// voice; thinking, it grows into a larger compound of two crystals, the sparkles circling; working,
    /// orbits ring it with small crystals travelling on them and a beam runs through it; speaking,
    /// ribbons of light spread from it like wings, carrying the last second of the voice outward.
    func drawCrystal(_ gc: inout GraphicsContext, _ box: CGSize) {
        var d = dotCanvas(box)
        let m = StateMix(engine)
        let n = pointBudget(box)
        let level = engine.history.value(secondsAgo: 0.05), loud = engine.loud
        let spin = engine.ringTurn * 1.5 + t * 0.12
        let vtx = ConceptGeometry.icosahedron, edges = ConceptGeometry.icosaEdges
        let view = View3(yaw: spin, pitch: 0.35 + 0.1 * sin(t * 0.3))
        let still = View3(yaw: 0, pitch: 0.25)
        let edgePoints = Int(Double(n) * 0.42)
        for i in 0..<n {
            let h1 = OrbPoints.hash(i, 1), h2 = OrbPoints.hash(i, 2), h3 = OrbPoints.hash(i, 3)
            var bl = Blend()
            var turned = true
            if i < edgePoints {
                let e = edges[i % edges.count], u = h1
                let a = vtx[e.0], b = vtx[e.1]
                let ex = a.0 + (b.0 - a.0) * u, ey = a.1 + (b.1 - a.1) * u, ez = a.2 + (b.2 - a.2) * u
                let corner = (u < 0.06 || u > 0.94) ? 0.4 : 0
                let restS = 0.5 * (1 + 0.15 * level * m.listen)
                bl.add(m.rest + m.listen, ex * restS, ey * restS, ez * restS, 0.45 + corner + 0.5 * m.listen * level)
                // Thinking: half the edges form a second crystal turned a quarter turn (a compound).
                if i % 2 == 1 {
                    bl.add(m.think, ez * 0.88, ey * 0.88, -ex * 0.88, 0.5 + corner)
                } else {
                    bl.add(m.think, ex * 0.88, ey * 0.88, ez * 0.88, 0.55 + corner)
                }
                bl.add(m.work, ex * 0.58, ey * 0.58, ez * 0.58, 0.55 + corner)
                let sp = 0.6 * (1 + 0.12 * loud)
                bl.add(m.speak, ex * sp, ey * sp, ez * sp, 0.55 + corner + 0.4 * loud)
            } else {
                // Sparkles at rest and thinking; orbits, travellers and a beam working; wings speaking.
                let dir = ConceptGeometry.direction(i)
                let r0 = 0.65 + 0.45 * h1
                let inward = 1 - 0.3 * m.listen * level
                let tw = 0.15 + 0.25 * max(0, sin(t * 2 + h2 * 20))
                bl.add(m.rest + m.listen, dir.0 * r0 * inward, dir.1 * r0 * inward, dir.2 * r0 * inward, tw)
                let ra = atan2(dir.2, dir.0) + t * 0.6, rr = 0.95 + 0.4 * h1
                bl.add(m.think, rr * cos(ra), dir.1 * 0.7, rr * sin(ra), tw + 0.1)
                if m.work > 0.003 {
                    let kind = i % 9
                    if kind == 0 {                                            // the beam
                        bl.add(m.work, 0, -1.7 + 3.4 * h1, 0, 0.5 * (1 - abs(2 * h1 - 1)) + 0.2)
                    } else if kind < 3 {                                      // a traveller (a small diamond)
                        let k = i % 3, ta = t * 0.9 + 2 * Double.pi * Double(k) / 3
                        let cxr = 1.1 * cos(ta), czr = 1.1 * sin(ta)
                        let q = 2 * Double.pi * h1, s = 0.07
                        bl.add(m.work, cxr + s * cos(q), 0.1 * sin(ta) + s * 1.4 * sin(q) * (h2 < 0.5 ? 1 : -1), czr, 0.9)
                    } else {                                                  // two tilted orbits
                        let tilt = kind % 2 == 0 ? 0.35 : -0.5, rad = kind % 2 == 0 ? 1.1 : 0.85
                        let a = 2 * Double.pi * h1
                        bl.add(m.work, rad * cos(a), rad * sin(a) * sin(tilt), rad * sin(a) * cos(tilt), 0.4)
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
                    bl.add(m.speak, x, y, z, (0.3 + 0.8 * past) * (1 - 0.5 * s) + 0.1 * h3)
                }
            }
            let p = turned ? view.apply(bl.x, bl.y, bl.z) : still.apply(bl.x, bl.y, bl.z)
            place(&d, p.x * 1.15, p.y * 1.15, bl.b * depthLight(p.z), OrbPoints.hash(i, 14), phase: h1 * 6.3, lum: min(1, bl.b))
        }
        finish(&gc, d)
    }

    // MARK: Eclipse

    /// A golden eclipse. Listening, a dark disc in a corona of sparks with a bright point at its
    /// heart, the corona swelling with your voice; thinking, the sphere's lit crescent turns inside
    /// tilted orbits; working, a shutter opens on one half and rays fan out from it; speaking,
    /// crescents of light on the sphere and the voice drawn as bars on both sides.
    func drawEclipse(_ gc: inout GraphicsContext, _ box: CGSize) {
        var d = dotCanvas(box)
        let m = StateMix(engine)
        let n = pointBudget(box)
        let level = engine.history.value(secondsAgo: 0.05), loud = engine.loud
        let spectrum = VoiceFeatures(level: loud, bands: engine.bands)
        let R = 0.62
        let lightA = t * 0.5
        for i in 0..<n {
            let h1 = OrbPoints.hash(i, 1), h2 = OrbPoints.hash(i, 2), h3 = OrbPoints.hash(i, 3)
            var bl = Blend()
            let a = 2 * Double.pi * h1
            let role = i % 10
            // The corona, the place every point has at rest (dense at the rim, thinning outward).
            let rho = pow(h2, 2.2)
            let swell = 1 + 0.18 * m.listen * level * h3
            let cr = (R + 0.04 + 0.55 * rho) * swell
            let coronaB = (0.75 - 0.6 * rho) * (0.6 + 0.4 * sin(t * 1.3 + h3 * 30))
            if role == 0 && i % 30 == 0 {                                      // the bright point at the heart
                let r = 0.035 * h2
                bl.add(m.rest + m.listen, r * cos(a), r * sin(a), 0, 1.2)
                bl.add(m.think + m.work + m.speak, cr * cos(a), cr * sin(a), 0, coronaB * 0.6)
            } else {
                bl.add(m.rest + m.listen, cr * cos(a), cr * sin(a), 0, coronaB * (1 + 0.6 * m.listen * level))
            }
            // Thinking: the lit crescent turning, and three tilted orbits.
            if m.think > 0.003 {
                if role < 4 {
                    let lit = max(0, cos(a - lightA))
                    bl.add(m.think, R * cos(a), R * sin(a), 0, 0.15 + 0.95 * pow(lit, 2))
                } else if role < 8 {
                    let o = role % 3, tilt = [0.35, -0.6, 1.1][o], rr = 0.85 + 0.12 * Double(o)
                    let oa = a + t * (0.4 + 0.15 * Double(o))
                    let x = rr * cos(oa), y = rr * sin(oa) * 0.32
                    bl.add(m.think, x * cos(tilt) - y * sin(tilt), x * sin(tilt) + y * cos(tilt), 0, 0.45)
                } else {
                    bl.add(m.think, cr * 1.15 * cos(a), cr * 1.15 * sin(a), 0, coronaB * 0.5)
                }
            }
            // Working: a shutter on the left half (six blades), rays fanning to the right, a vertical line.
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
                    bl.add(m.work, x < 0.02 ? x : -x, y, 0, 0.5)
                } else if role < 8 {
                    let ray = Int(h2 * 9), ra = -0.55 + 1.1 * Double(ray) / 8, len = 1.0 + 0.6 * OrbPoints.hash(ray, 5)
                    let f = h1
                    let pulse = pow(max(0, sin((f - t * 1.2) * 2 * .pi)), 6)
                    bl.add(m.work, f * len * cos(ra), f * len * sin(ra), 0, (f > 0.96 ? 1.0 : 0.35) + 0.6 * pulse)
                } else {
                    bl.add(m.work, 0, -1.7 + 3.4 * h1, 0, 0.35)
                }
            }
            // Speaking: crescents on the sphere, and the voice as bars on both sides.
            if m.speak > 0.003 {
                if role < 4 {
                    let shift = role < 2 ? 0.0 : 0.12
                    let lit = max(0, cos(a))
                    let crA = R * (1 - shift) + shift * 0.1
                    bl.add(m.speak, crA * cos(a) + shift * R * 0.5, crA * sin(a), 0, 0.2 + 1.0 * pow(lit, 3) * (0.6 + 0.6 * loud))
                } else if role < 8 {
                    let side: Double = h3 < 0.5 ? -1 : 1
                    let bar = Int(h1 * 18), s = (Double(bar) + 0.5) / 18
                    let past = engine.history.value(secondsAgo: s * 0.9)
                    let hgt = (0.06 + 0.55 * past * (0.6 + 0.6 * spectrum.band(at: s))) * (1 - 0.4 * s)
                    bl.add(m.speak, side * (R + 0.15 + 1.15 * s), (2 * h2 - 1) * hgt, 0, 0.45 + 0.7 * past)
                } else {
                    bl.add(m.speak, cr * cos(a), cr * sin(a), 0, coronaB * (0.8 + 0.6 * loud))
                }
            }
            place(&d, bl.x * 1.15, bl.y * 1.15, bl.b, OrbPoints.hash(i, 14), phase: a, lum: min(1, bl.b))
        }
        // A golden eclipse: deep violet in the dim levels, gold in the bright ones.
        finish(&gc, d, palette: [Color(hex: 0x4c2a85).opacity(0.5), Color(hex: 0x7b4fd0).opacity(0.65), Color(hex: 0xd9954a).opacity(0.75),
                                 Color(hex: 0xf2c46b).opacity(0.9), Color(hex: 0xfff1cf).opacity(0.95)])
    }

    // MARK: Synapse

    /// A network of nodes and their links. Listening, a compact cluster that pulses with your voice;
    /// thinking, it spreads into a large tangled network with signals running along its links;
    /// working, hubs at its centre and nodes travelling on orbits around them; speaking, a starburst
    /// from a central node, the links lighting outward with the voice.
    func drawSynapse(_ gc: inout GraphicsContext, _ box: CGSize) {
        var d = dotCanvas(box)
        let m = StateMix(engine)
        let level = engine.history.value(secondsAgo: 0.05), loud = engine.loud
        let nodes = ConceptGeometry.nodes, links = ConceptGeometry.links
        let view = View3(yaw: t * 0.15 + engine.ringTurn * 0.6, pitch: 0.3)
        var pos: [(x: Double, y: Double, z: Double, b: Double)] = []
        pos.reserveCapacity(nodes.count)
        for (i, u) in nodes.enumerated() {
            let h = OrbPoints.hash(i, 7)
            var bl = Blend()
            let r0 = 0.42 * (1 + 0.25 * m.listen * level * h) + 0.02 * sin(t * 1.3 + Double(i))
            bl.add(m.rest + m.listen, u.0 * r0, u.1 * r0, u.2 * r0, 0.7 + 0.6 * m.listen * level)
            let wob = 0.08 * sin(t * 0.7 + Double(i) * 1.7)
            let r1 = 0.6 + 0.55 * h + wob
            bl.add(m.think, u.0 * r1, u.1 * r1 * 0.85, u.2 * r1, 0.75)
            if i < 3 {
                bl.add(m.work, 0.18 * cos(Double(i) * 2.1), 0.18 * sin(Double(i) * 2.1), 0, 1.2)
            } else {
                let ring = i % 3, tilt = [0.3, -0.45, 1.2][ring]
                let a = 2 * Double.pi * Double(i / 3) / Double(nodes.count / 3) + t * (0.35 + 0.15 * Double(ring)) * (ring == 1 ? -1 : 1)
                let rr = 0.75 + 0.18 * Double(ring)
                let x = rr * cos(a), y = rr * sin(a) * 0.35
                bl.add(m.work, x * cos(tilt) - y * sin(tilt), x * sin(tilt) + y * cos(tilt), rr * sin(a) * 0.3, 0.7)
            }
            if i == 0 {
                bl.add(m.speak, 0, 0, 0, 1.3 + loud)
            } else {
                let past = engine.history.value(secondsAgo: h * 0.8)
                let r2 = (0.55 + 0.65 * h) * (1 + 0.35 * past)
                bl.add(m.speak, u.0 * r2, u.1 * r2, u.2 * r2, 0.6 + 0.7 * past)
            }
            let p = view.apply(bl.x, bl.y, bl.z)
            pos.append((p.x * 1.2, p.y * 1.2, p.z, bl.b * depthLight(p.z)))
        }
        let pal = OrbPalette.colors(for: look.color)
        // The links: the network's own (faint as it speaks), and the starburst's spokes.
        var lines = [Path](repeating: Path(), count: 4)
        func link(_ a: Int, _ b: Int, _ bright: Double) {
            guard bright > 0.04 else { return }
            let level = min(3, max(0, Int(bright * 4)))
            lines[level].move(to: CGPoint(x: d.cx + pos[a].x * d.R, y: d.cy + pos[a].y * d.R))
            lines[level].addLine(to: CGPoint(x: d.cx + pos[b].x * d.R, y: d.cy + pos[b].y * d.R))
        }
        for (k, l) in links.enumerated() {
            let base = (0.3 + 0.2 * m.think + 0.3 * m.listen * level) * (1 - m.speak)
            link(l.0, l.1, base + 0.15 * sin(t + Double(k)))
        }
        for i in 1..<nodes.count {
            let past = engine.history.value(secondsAgo: OrbPoints.hash(i, 7) * 0.8)
            link(0, i, m.speak * (0.25 + 0.75 * past))
        }
        for level in 0..<4 {
            gc.stroke(lines[level], with: .color(pal[3].opacity(0.15 + 0.22 * Double(level))), lineWidth: max(0.5, d.px * 0.7))
        }
        // Thinking: signals running along the links.
        if m.think > 0.02 {
            for (k, l) in links.enumerated() where k % 2 == 0 {
                let f = frac(t * 0.7 + OrbPoints.hash(k, 9))
                let a = pos[l.0], b = pos[l.1]
                d.dot(a.x + (b.x - a.x) * f, a.y + (b.y - a.y) * f, 1.1 * m.think, 0.5, size: 1.8)
            }
        }
        // Dust around it.
        for k in 0..<Int(Double(pointBudget(box)) * 0.15) {
            let u = ConceptGeometry.direction((k * 389) % 997), r = 0.5 + 1.1 * OrbPoints.hash(k, 3)
            let p = view.apply(u.0 * r, u.1 * r, u.2 * r)
            d.dot(p.x * 1.2, p.y * 1.2, (0.08 + 0.12 * sin(t + Double(k))) * depthLight(p.z), OrbPoints.hash(k, 14))
        }
        // The nodes: a glow and a round core, the hubs larger.
        var cores = [Path](repeating: Path(), count: 5)
        for (i, p) in pos.enumerated() {
            var x = p.x, y = p.y
            let b = p.b + workEffect(&x, &y, phase: Double(i))
            let g = d.px * (3 + 3 * min(1.3, b))
            let cxp = d.cx + x * d.R, cyp = d.cy + y * d.R
            gc.fill(Path(ellipseIn: CGRect(x: cxp - g, y: cyp - g, width: 2 * g, height: 2 * g)),
                    with: .radialGradient(Gradient(colors: [OrbPalette.glow(pal).opacity(min(0.7, 0.3 * b)), .clear]),
                                          center: CGPoint(x: cxp, y: cyp), startRadius: 0, endRadius: g))
            let core = d.px * (1.4 + 0.9 * min(1.2, b) + (i < 3 ? 0.8 * m.work : 0) + (i == 0 ? 1.2 * m.speak : 0))
            cores[min(4, max(0, Int(b * 4)))].addEllipse(in: CGRect(x: cxp - core, y: cyp - core, width: 2 * core, height: 2 * core))
        }
        drawWaves(&gc, cx: d.cx, cy: d.cy, R: d.R, pal: pal)
        for b in 0..<5 { gc.fill(d.paths[b], with: .color(pal[b])) }
        for b in 0..<5 { gc.fill(cores[b], with: .color(pal[min(4, b + 1)])) }
        drawSatellites(&gc, cx: d.cx, cy: d.cy, R: d.R, px: d.px, pal: pal)
    }

    // MARK: Drop

    /// A drop of light. Listening, a drop wobbling with your voice over rings that ripple out;
    /// thinking, it whirls into a spiral vortex; working, it unravels into fibres fanning out to
    /// nodes; speaking, a horn of particles pours out of it, opening wider with the voice.
    func drawDrop(_ gc: inout GraphicsContext, _ box: CGSize) {
        var d = dotCanvas(box)
        let m = StateMix(engine)
        let n = pointBudget(box)
        let level = engine.history.value(secondsAgo: 0.05)
        let view = View3(yaw: t * 0.1, pitch: 0.42)
        let flat = View3(yaw: 0, pitch: 0.2)
        let surface = Int(Double(n) * 0.6)
        for i in 0..<n {
            let h1 = OrbPoints.hash(i, 1), h2 = OrbPoints.hash(i, 2), h3 = OrbPoints.hash(i, 3)
            var bl = Blend()
            let th = 2 * Double.pi * h1
            if i < surface {
                // The drop: pointed at the top, round below; wobbling with your voice.
                let tt = Double.pi * pow(h2, 0.8)
                let wob = 1 + 0.08 * m.listen * level * sin(3 * th + t * 5) + 0.015 * sin(t * 1.4)
                let r = 0.62 * sin(tt) * pow(sin(tt / 2), 1.3) * wob
                let y = 0.25 - 1.0 * (1 + cos(tt)) / 2
                let rim = 0.35 + 0.5 * pow(abs(cos(th)), 6) + 0.3 * smoothstep(0.85, 1, h2)
                bl.add(m.rest + m.listen, r * cos(th), y, r * sin(th), rim)
            } else {
                // The rings under it, rippling out as you speak.
                let ring = Double(i % 3)
                let rr = 0.68 + 0.22 * ring + 0.4 * m.listen * frac(t * 0.5 + ring / 3)
                let past = engine.history.value(secondsAgo: (rr - 0.68) * 1.2)
                bl.add(m.rest + m.listen, rr * cos(th), 0.28, rr * sin(th), 0.3 + 0.7 * m.listen * past)
            }
            // Thinking: a vortex of three arms.
            if m.think > 0.003 {
                let r = 0.05 + 1.15 * pow(h2, 0.7)
                let arm = Double(i % 3)
                let a = arm * 2 * .pi / 3 + 2.4 * log(r + 0.06) - t * 1.3 + 0.35 * (h3 - 0.5)
                bl.add(m.think, r * cos(a), 0.05 * (h3 - 0.5), r * sin(a), 0.35 + 0.6 * (1 - r / 1.2))
            }
            // Working: fibres from a bundle on the left fanning out to nodes on the right.
            if m.work > 0.003 {
                let fibre = i % 16, u = h2
                let endY = (Double(fibre) - 7.5) * 0.12, endZ = 0.25 * sin(Double(fibre) * 1.3)
                let x = -1.3 + 2.5 * u
                let y = 0.1 + endY * pow(u, 1.6) + 0.04 * sin(u * 9 + t * 3 + Double(fibre))
                if fibre % 4 == 0 && u > 0.93 {
                    let q = 2 * Double.pi * h3
                    bl.add(m.work, 1.2 + 0.08 * cos(q), 0.1 + endY + 0.08 * sin(q), endZ, 0.9)
                } else {
                    let pulse = pow(max(0, sin((u - t * 0.8) * 2 * .pi)), 8)
                    bl.add(m.work, x, y, endZ * u, 0.3 + 0.7 * pulse)
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
                bl.add(m.speak, x + 0.15 * rad * cos(ang), y + rad * cos(ang) * 0.95, rad * sin(ang), (0.3 + 0.7 * past) * (0.9 - 0.4 * s) + rimLight)
            }
            let flatShare = m.work + m.speak
            let p1 = view.apply(bl.x, bl.y, bl.z), p2 = flat.apply(bl.x, bl.y, bl.z)
            let x = p1.x + (p2.x - p1.x) * flatShare, y = p1.y + (p2.y - p1.y) * flatShare, z = p1.z + (p2.z - p1.z) * flatShare
            place(&d, x * 1.2, y * 1.2, bl.b * depthLight(z), OrbPoints.hash(i, 14), phase: th, lum: min(1, bl.b))
        }
        finish(&gc, d)
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
