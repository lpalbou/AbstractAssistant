import SwiftUI

// Two scenes of nature: Aurora (the northern lights over a dark ridge and their reflection in a
// lake) and Murmuration (a flock of starlings at dusk). One shape per state of the assistant, a
// blend of the five phases' shapes; every motion at a fixed pace (a phase changes how much of a
// motion shows, never its speed), so a change of state is always a smooth morph.

@inline(__always) private func fract(_ x: Double) -> Double { x - x.rounded(.down) }

extension OrbCanvas {

    // MARK: Aurora

    /// The northern lights: curtains of light rays, green at their foot and violet at their top,
    /// folding slowly over a dark ridge, mirrored in a still lake under a sky of stars. Listening,
    /// waves run along the curtains toward the middle carrying your voice and they brighten.
    /// Thinking, the rays gather into a corona overhead, turning. Working, the curtains pulse in
    /// patches and their rays dance, brightening with each step. Speaking, the rays rise with the
    /// voice's spectrum across the sky (low pitches in the middle) and their foot flares pink on
    /// loud syllables.
    func drawAurora(_ gc: inout GraphicsContext, _ box: CGSize) {
        let ph = OrbPhases(engine)
        let W = Double(box.width), H = Double(box.height)
        let cx = W / 2
        let horizon = H * 0.68
        let hist = engine.history, spectrum = ph.spectrum, loud = ph.loud
        let level = engine.history.value(secondsAgo: 0.05)
        let flash = work.pulses.reduce(0.0) { $0 + max(0, 1 - $1.age / 1.2) * $1.strength }
        var normal = gc
        normal.blendMode = .normal
        // The night: a deep sky, a few stars.
        normal.fill(Path(CGRect(x: 0, y: 0, width: W, height: H)),
                    with: .linearGradient(Gradient(colors: [Color(hex: 0x020617), Color(hex: 0x071a2b), Color(hex: 0x0b2a3a)]),
                                          startPoint: CGPoint(x: cx, y: 0), endPoint: CGPoint(x: cx, y: horizon)))
        var stars = Path()
        for k in 0..<70 {
            let x = W * OrbPoints.hash(k, 61), y = horizon * 0.95 * OrbPoints.hash(k, 62)
            let tw = 0.5 + 0.5 * sin(t * (1 + 2 * OrbPoints.hash(k, 63)) + Double(k))
            let s = 0.6 + 1.1 * OrbPoints.hash(k, 64) * tw
            stars.addEllipse(in: CGRect(x: x - s / 2, y: y - s / 2, width: s, height: s))
        }
        gc.fill(stars, with: .color(.white.opacity(0.55)))
        // The curtains: three, each a soft ribbon of light from its foot to its top, with rays of
        // light running up it. Their shapes are computed once and painted twice (the sky, the lake).
        let raysPer = 48
        let zenith = CGPoint(x: cx, y: H * 0.28)
        let w = ph.think
        struct Curtain { var ribbon = Path(), rays = Path(), bright = Path(), hem = Path(), footY = 0.0, topY = 0.0, inner = 0.0, outer = 0.0 }
        var curtains: [Curtain] = []
        for c in 0..<3 {
            let fc = Double(c)
            var cur = Curtain()
            var feet: [CGPoint] = [], tops: [CGPoint] = []
            for i in 0..<raysPer {
                let u = Double(i) / Double(raysPer - 1), x0 = (u - 0.5) * 1.15 * W + cx
                let fu = 2 * u - 1
                // The curtain's foot folds slowly; its rays sway.
                let fold = 0.07 * H * sin(2.4 * fu + 0.25 * t + fc * 1.9) + 0.03 * H * sin(5.3 * fu - 0.4 * t + fc)
                let baseY = horizon - H * (0.1 + 0.07 * fc) + fold
                var height = H * (0.2 + 0.08 * fc) * (0.65 + 0.35 * sin(3.1 * fu + 0.5 * t + fc * 2.2))
                var bright = 0.45 + 0.25 * sin(6.7 * fu - 0.9 * t + fc * 3)
                // Listening: waves run in toward the middle along the curtain, your voice in them.
                let past = hist.value(secondsAgo: abs(fu) * 0.6)
                height *= 1 + ph.listen * (0.25 * past + 0.12 * sin(8 * abs(fu) + 3 * t))
                bright += ph.listen * 0.5 * past
                // Working: patches pulse along it, the rays dance.
                let patch = pow(max(0, sin(4 * fu - 1.7 * t + fc * 2)), 6)
                height *= 1 + ph.work * (0.2 * sin(13 * fu + 6 * t + fc) + 0.3 * patch)
                bright += ph.work * (0.6 * patch + 0.4 * flash)
                // Speaking: the rays rise with the voice's spectrum, low pitches in the middle.
                let band = spectrum.band(at: abs(fu))
                height *= 1 + ph.speak * (0.15 + 1.1 * band * (0.4 + 0.6 * past))
                bright += ph.speak * (0.3 + 0.6 * band)
                let lean = 0.03 * W * sin(1.3 * fu + 0.3 * t + fc)
                let foot = CGPoint(x: x0, y: baseY), top = CGPoint(x: x0 + lean, y: baseY - height)
                // Thinking: the rays gather into a round corona overhead, turning slowly.
                let a = 2 * Double.pi * (u + fc / 3) + 0.25 * t
                // (Its rim's waves are periodic round the circle: the curtain's two ends meet without a seam.)
                let r1 = H * (0.025 + 0.012 * fc), r2 = H * (0.2 + 0.04 * fc) * (0.93 + 0.07 * sin(2 * Double.pi * 3 * u + t + fc))
                let cFoot = CGPoint(x: zenith.x + r1 * cos(a) * 1.12, y: zenith.y + r1 * sin(a))
                let cTop = CGPoint(x: zenith.x + r2 * cos(a) * 1.12, y: zenith.y + r2 * sin(a))
                func mix(_ p: CGPoint, _ q: CGPoint) -> CGPoint { CGPoint(x: p.x + (q.x - p.x) * w, y: p.y + (q.y - p.y) * w) }
                let f = mix(foot, cFoot), tp = mix(top, cTop)
                feet.append(f); tops.append(tp)
                var ray = Path(); ray.move(to: f); ray.addLine(to: CGPoint(x: f.x + (tp.x - f.x) * 0.92, y: f.y + (tp.y - f.y) * 0.92))
                if bright > 0.62 { cur.bright.addPath(ray) } else { cur.rays.addPath(ray) }
            }
            cur.ribbon.addLines(feet + tops.reversed()); cur.ribbon.closeSubpath()
            cur.inner = H * (0.025 + 0.012 * fc); cur.outer = H * (0.2 + 0.04 * fc) * 1.12
            cur.footY = feet.reduce(0) { $0 + Double($1.y) } / Double(feet.count)
            cur.topY = tops.reduce(0) { $0 + Double($1.y) } / Double(tops.count)
            cur.hem.addLines(feet)
            curtains.append(cur)
        }
        // A gentle gradient: mint at the foot, through teal, to a soft violet fading out at the top
        // (the rays' light over the whole sky; each veil fades out over its own height).
        let topY = horizon - H * 0.75, footY = horizon - H * 0.05
        let veil = Gradient(stops: [.init(color: Color(hex: 0x8b5cf6).opacity(0), location: 0),
                                    .init(color: Color(hex: 0xa78bfa).opacity(0.32), location: 0.28),
                                    .init(color: Color(hex: 0x5eead4).opacity(0.55), location: 0.55),
                                    .init(color: Color(hex: 0x34d399).opacity(0.85), location: 0.82),
                                    .init(color: Color(hex: 0x86efac), location: 1)])
        let shading = GraphicsContext.Shading.linearGradient(veil, startPoint: CGPoint(x: cx, y: topY), endPoint: CGPoint(x: cx, y: footY))
        let fade = Gradient(stops: [.init(color: Color(hex: 0x8b5cf6).opacity(0), location: 0),
                                    .init(color: Color(hex: 0xa78bfa).opacity(0.22), location: 0.3),
                                    .init(color: Color(hex: 0x5eead4).opacity(0.5), location: 0.62),
                                    .init(color: Color(hex: 0x34d399).opacity(0.85), location: 0.88),
                                    .init(color: Color(hex: 0x86efac), location: 1)])
        // The corona's light: soft at its heart, green, then teal, a violet rim fading out.
        let coronaR = H * 0.32
        func coronaLight(_ inner: Double, _ outer: Double) -> GraphicsContext.Shading {
            let a = inner / outer
            return .radialGradient(
                Gradient(stops: [.init(color: Color(hex: 0x86efac).opacity(0), location: a), .init(color: Color(hex: 0x86efac).opacity(0.9), location: min(0.4, 2.6 * a)),
                                 .init(color: Color(hex: 0x34d399).opacity(0.7), location: 0.45), .init(color: Color(hex: 0x5eead4).opacity(0.4), location: 0.68),
                                 .init(color: Color(hex: 0xa78bfa).opacity(0.22), location: 0.86), .init(color: Color(hex: 0x8b5cf6).opacity(0), location: 1)]),
                center: zenith, startRadius: 0, endRadius: outer)
        }
        let corona = coronaLight(0, coronaR)
        let lw = max(1.2, W / 95)
        let pink = ph.speak * max(0, loud - 0.3) * 1.2 + 0.25 * ph.work * min(1, flash)
        /// The curtains' veils (soft fills); `glow`: their rays and bright hems, blurred (one layer).
        func paint(_ g: inout GraphicsContext, _ alpha: Double, glow: Bool) {
            for (c, cur) in curtains.enumerated() {
                let fc = Double(c)
                // Each veil fades out toward its own top (no hard upper edge).
                let top = cur.topY - 0.25 * (cur.footY - cur.topY)
                let own = GraphicsContext.Shading.linearGradient(fade, startPoint: CGPoint(x: cx, y: top), endPoint: CGPoint(x: cx, y: cur.footY))
                // Between the two shapes the veil would fold over itself: only the rays show there.
                let veilShare = 1 - smoothstep(0, 0.42, w), coronaShare = smoothstep(0.72, 1, w)
                g.opacity = alpha * (0.34 - 0.06 * fc) * veilShare
                if veilShare > 0.01 { g.fill(cur.ribbon, with: own) }
                g.opacity = alpha * (0.3 - 0.05 * fc) * coronaShare
                if coronaShare > 0.01 { g.fill(cur.ribbon, with: coronaLight(cur.inner, cur.outer)) }
            }
            g.opacity = 1
            guard glow else { return }
            g.drawLayer { layer in
                layer.addFilter(.blur(radius: lw * 1.5))
                for (c, cur) in curtains.enumerated() {
                    let fc = Double(c)
                    // The rays in the curtains' light, blended into the corona's as it thinks.
                    for (ink, share) in [(shading, 1 - w), (corona, 0.45 * w)] where share > 0.01 {
                        layer.opacity = alpha * (0.55 - 0.1 * fc) * share
                        layer.stroke(cur.rays, with: ink, lineWidth: lw * 1.5)
                        layer.opacity = alpha * (0.9 - 0.1 * fc) * share
                        layer.stroke(cur.bright, with: ink, lineWidth: lw * 1.8)
                    }
                    // The bright hem at the curtain's foot (pink on loud syllables and as it works).
                    layer.opacity = alpha * (0.55 - 0.12 * fc) * (1 - 0.6 * w)
                    layer.stroke(cur.hem, with: .color(Color(hex: 0xa7f3d0)), style: StrokeStyle(lineWidth: lw * 1.4, lineCap: .round, lineJoin: .round))
                    if pink > 0.02 {
                        layer.opacity = alpha * min(0.8, pink)
                        layer.stroke(cur.hem, with: .color(Color(hex: 0xf472b6)), style: StrokeStyle(lineWidth: lw * 1.8, lineCap: .round, lineJoin: .round))
                    }
                }
            }
        }
        paint(&gc, 1, glow: true)
        // The lake: dark water, the lights mirrored in it, dimmer and softened.
        normal.fill(Path(CGRect(x: 0, y: horizon, width: W, height: H - horizon)),
                    with: .linearGradient(Gradient(colors: [Color(hex: 0x04121a), Color(hex: 0x01060a)]),
                                          startPoint: CGPoint(x: cx, y: horizon), endPoint: CGPoint(x: cx, y: H)))
        gc.drawLayer { layer in
            layer.clip(to: Path(CGRect(x: 0, y: horizon, width: W, height: H - horizon)))
            layer.addFilter(.blur(radius: 3))
            layer.translateBy(x: 0, y: 2 * horizon)
            layer.scaleBy(x: 1, y: -1)
            paint(&layer, 0.5, glow: false)
        }
        // The ridge: a dark silhouette on the horizon, and the lake's line.
        var ridge = Path()
        ridge.move(to: CGPoint(x: 0, y: horizon))
        for i in 0...40 {
            let u = Double(i) / 40
            let y = horizon - H * (0.03 + 0.05 * pow(max(0, sin(u * 5.1 + 0.6)), 2) + 0.025 * sin(u * 17 + 1.3))
            ridge.addLine(to: CGPoint(x: W * u, y: y))
        }
        ridge.addLine(to: CGPoint(x: W, y: horizon)); ridge.closeSubpath()
        normal.fill(ridge, with: .color(Color(hex: 0x02040a)))
        var shore = Path(); shore.move(to: CGPoint(x: 0, y: horizon)); shore.addLine(to: CGPoint(x: W, y: horizon))
        gc.stroke(shore, with: .color(Color(hex: 0x6ee7b7).opacity(0.12 + 0.2 * level * (ph.listen + ph.speak))), lineWidth: 0.6)
    }

    // MARK: Murmuration

    /// A murmuration: a flock of starlings at dusk, black against a sky turning from indigo to
    /// amber. At rest a long cloud drifting and folding on itself. Listening, it swells toward you
    /// with your voice and dark waves of birds sweep through it. Thinking, it turns into a slow
    /// spinning ring. Working, it streams along a figure of eight, a dense knot passing each step.
    /// Speaking, it stretches into a ribbon across the sky whose thickness follows the voice, as
    /// if drawing it.
    func drawMurmuration(_ gc: inout GraphicsContext, _ box: CGSize) {
        let ph = OrbPhases(engine)
        let W = Double(box.width), H = Double(box.height)
        let cx = W / 2, cy = H * 0.44
        let S = min(W, H) * 0.42
        let hist = engine.history, spectrum = ph.spectrum
        let level = hist.value(secondsAgo: 0.05)
        var normal = gc
        normal.blendMode = .normal
        // Dusk: indigo overhead to amber at the horizon, a low line of land.
        normal.fill(Path(CGRect(x: 0, y: 0, width: W, height: H)),
                    with: .linearGradient(Gradient(stops: [.init(color: Color(hex: 0x1e1b4b), location: 0),
                                                           .init(color: Color(hex: 0x6d2862), location: 0.45),
                                                           .init(color: Color(hex: 0xe0703c), location: 0.8),
                                                           .init(color: Color(hex: 0xf8c77a), location: 0.93)]),
                                          startPoint: CGPoint(x: cx, y: 0), endPoint: CGPoint(x: cx, y: H)))
        var land = Path()
        land.move(to: CGPoint(x: 0, y: H))
        for i in 0...30 {
            let u = Double(i) / 30
            land.addLine(to: CGPoint(x: W * u, y: H * (0.9 - 0.025 * sin(u * 9 + 0.5) - 0.015 * sin(u * 23))))
        }
        land.addLine(to: CGPoint(x: W, y: H)); land.closeSubpath()
        normal.fill(land, with: .color(Color(hex: 0x120a12)))
        let n = Int(Double(pointBudget(box)) * 1.05)
        var near = Path(), far = Path()
        for i in 0..<n {
            let u = OrbPoints.hash(i, 81), v = OrbPoints.hash(i, 82), w = OrbPoints.hash(i, 83)
            var x = 0.0, y = 0.0, z = 0.0
            func add(_ wt: Double, _ px: Double, _ py: Double, _ pz: Double) {
                guard wt > 0.002 else { return }
                x += wt * px; y += wt * py; z += wt * pz
            }
            // A volume of birds (a point inside a ball, from three numbers).
            let th = 2 * Double.pi * u, ph1 = acos(2 * v - 1), rr = pow(w, 0.45)
            let bx = rr * sin(ph1) * cos(th), by = rr * sin(ph1) * sin(th), bz = rr * cos(ph1)
            // Rest: a long cloud, drifting and folding.
            let fold = 0.35 * sin(2.1 * bx + 0.31 * t) + 0.18 * sin(3.7 * bx - 0.23 * t + 1)
            let restP = (bx * 1.25 + 0.12 * sin(0.17 * t), by * 0.42 + fold * (0.6 + 0.4 * bx * bx), bz * 0.5)
            add(ph.rest, restP.0, restP.1, restP.2)
            // Listening: it swells with your voice; dark waves sweep through it.
            if ph.listen > 0.002 {
                let swell = 1 + 0.35 * level
                let wave = 0.12 * sin(5 * bx - 3.2 * t) * (0.3 + level)
                add(ph.listen, restP.0 * swell, restP.1 * swell + wave, restP.2 * swell)
            }
            // (Each shape is computed only while its phase shows.)
            // Thinking: a slow spinning ring.
            if ph.think > 0.002 {
                let ra = 2 * Double.pi * u + 0.6 * t, rad = 0.75 + 0.18 * (v - 0.5) + 0.06 * sin(3 * ra + t)
                add(ph.think, rad * cos(ra), 0.32 * rad * sin(ra) + 0.12 * (w - 0.5), rad * sin(ra) * 0.6)
            }
            // Working: a stream along a figure of eight.
            if ph.work > 0.002 {
                let s = 2 * Double.pi * fract(u + 0.12 * t)
                let lx = 1.15 * sin(s), ly = 0.45 * sin(s) * cos(s)
                add(ph.work, lx + 0.07 * (v - 0.5), ly + 0.07 * (w - 0.5) * 1.4, 0.3 * cos(s))
            }
            // Speaking: one flowing ribbon across the sky, as thick as the voice (its middle the
            // voice now, its ends a moment ago), densest along its spine, twisting as it flows.
            if ph.speak > 0.002 {
                let rx = 2 * u - 1
                let env = pow(max(0, 1 - rx * rx), 0.7)
                let voice = hist.value(secondsAgo: abs(rx) * 0.45) * (0.6 + 0.6 * spectrum.band(at: abs(rx)))
                let thick = (0.08 + 0.48 * voice) * env
                let spine = 0.13 * sin(2.2 * rx - 1.3 * t) + 0.04 * sin(5.1 * rx + 0.9 * t)
                let across = v + w - 1                                       // −1…1, densest at 0
                let twist = 2.6 * rx - 1.1 * t
                add(ph.speak, rx * 1.35, spine + across * thick * cos(twist), across * thick * sin(twist) * 0.8)
            }
            // Each bird jitters a little on its own.
            x += 0.012 * sin(t * 7 + Double(i)); y += 0.012 * cos(t * 6 + Double(i) * 1.3)
            let f = 2.6 / (2.6 - z)
            let px = cx + x * f * S, py = cy + y * f * S
            let size = (1.0 + 1.0 * (f - 0.8)) * max(0.9, S / 70) * 1.3
            let rect = CGRect(x: px - size / 2, y: py - size * 0.33, width: size, height: size * 0.66)
            if z > 0 { near.addEllipse(in: rect) } else { far.addEllipse(in: rect) }
        }
        let tone = look.color ?? Color(hex: 0x0b0710)
        // Soft birds: a little translucent, so the flock is darker where it is denser.
        normal.fill(far, with: .color(tone.opacity(0.5)))
        normal.fill(near, with: .color(tone.opacity(0.8)))
    }
}
