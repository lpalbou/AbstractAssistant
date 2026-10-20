import SwiftUI

// Three scenes of the universe, one shape per state of the assistant, morphing from one to the
// next as the state changes: Well (the fabric of space bending round a mass, after Wave's lines),
// Black hole (the ring of light round a shadow, as the Event Horizon Telescope photographed it) and
// Accretion (a solar system forming: a young star in a disk of dust whose rings gather into
// planets). Every shape is a blend of the five phases' shapes weighted by `OrbPhases`, and every
// motion runs at a fixed pace (a phase changes how much of a motion shows, never its speed), so a
// change of state is always a smooth morph. Units as the planet (1 = its radius, y down).

/// A point and its light, summed over the phases' shapes.
private struct Mix {
    var x = 0.0, y = 0.0, b = 0.0, size = 0.0
    mutating func add(_ w: Double, _ x: Double, _ y: Double, _ b: Double, size: Double = 1) {
        guard w > 0.002 else { return }
        self.x += w * x; self.y += w * y; self.b += w * b; self.size += w * size
    }
}

@inline(__always) private func fract(_ x: Double) -> Double { x - x.rounded(.down) }
/// A rough normal deviate from three uniform ones (mean 0, deviation about 0.5).
@inline(__always) private func spread(_ a: Double, _ b: Double, _ c: Double) -> Double { a + b + c - 1.5 }

extension OrbCanvas {

    // MARK: Well

    /// The fabric of space: a grid of fine lines in perspective, curving down into a well round a
    /// glowing mass. At rest the well is shallow and breathes. Listening, ripples run in from the
    /// edges carrying your voice (each radius the voice of a moment ago). Thinking, the well deepens
    /// and a second mass circles inside it. Working, the two masses orbit close and fast and the
    /// fabric carries their gravitational waves out in a two-armed spiral, a ring for each step;
    /// each tool running is a small body circling in the well. Speaking, waves leave the centre
    /// with the voice, its low pitches near the mass and its high ones at the rim.
    func drawWell(_ gc: inout GraphicsContext, _ box: CGSize) {
        let ph = OrbPhases(engine)
        let W = Double(box.width), H = Double(box.height)
        let cx = W / 2, cy = H / 2
        let S = min(W * 0.54, H * 0.74)
        let pitch = 0.64, cP = cos(pitch), sP = sin(pitch)
        let yaw = 0.35 + 0.22 * sin(t * 0.07), cY = cos(yaw), sY = sin(yaw)
        let spectrum = ph.spectrum
        let hist = engine.history
        // The masses: one at rest; two circling each other while it thinks (slow) and works (close, fast).
        let a1 = t * 1.1, a2 = t * 2.6
        let ox = 0.19 * ph.think * cos(a1) + 0.12 * ph.work * cos(a2)
        let oy = 0.19 * ph.think * sin(a1) + 0.12 * ph.work * sin(a2)
        let depth = 0.36 * ph.rest + 0.4 * ph.listen + 0.62 * ph.think + 0.7 * ph.work + (0.46 + 0.16 * ph.loud) * ph.speak
        let tools = work.satellites
        let busy = ph.work + 0.5 * ph.think

        /// The fabric's height at (u, v): the well, its ripples, the bodies in it.
        func height(_ u: Double, _ v: Double) -> Double {
            let r = (u * u + v * v).squareRoot()
            let d1 = (u - ox) * (u - ox) + (v - oy) * (v - oy), d2 = (u + ox) * (u + ox) + (v + oy) * (v + oy)
            // Each mass's well: deep and narrow at the mass, its pull reaching far (a softened 1/r).
            let soft = 0.1, rim = soft / (1.7 * 1.7 + soft * soft).squareRoot()
            var h = -depth * 0.5 * (soft / (d1 + soft * soft).squareRoot() + soft / (d2 + soft * soft).squareRoot() - 2 * rim)
            let reach = smoothstep(0.08, 0.3, r) * (1 - smoothstep(0.9, 1.45, r))
            // At rest: a slow breath of the whole fabric.
            h += ph.rest * 0.014 * sin(6 * r - t * 1.2) * reach
            // Listening: in from the edges, the voice of a moment ago at each radius.
            if ph.listen > 0.002 {
                let past = hist.value(secondsAgo: max(0, 1.4 - r) * 0.35)
                let amp = 0.025 + 0.12 * past * (0.5 + spectrum.band(at: 1 - r / 1.4))
                h += ph.listen * amp * sin(10 * r + t * 3.2) * reach
            }
            // Thinking: a slow two-armed swell following the orbit.
            if ph.think > 0.002 {
                let th = atan2(v, u)
                h += ph.think * 0.03 * cos(2 * (th - a1) - 5 * r) * reach
            }
            // Working: the binary's gravitational waves, a spiral of two arms leaving it.
            if ph.work > 0.002 {
                let th = atan2(v, u)
                h += ph.work * 0.065 * cos(2 * (th - a2) + 8 * r) * reach / (1 + 1.5 * r)
            }
            // Speaking: out from the centre with the voice, low pitches near the mass.
            if ph.speak > 0.002 {
                let past = hist.value(secondsAgo: r * 0.35)
                let amp = 0.03 + 0.14 * past * (0.5 + spectrum.band(at: r / 1.4)) + 0.04 * ph.loud
                h += ph.speak * amp * sin(10 * r - t * 3.2) * reach
            }
            // Each step: a ring travelling out across the fabric.
            for p in work.pulses where p.tone != .failure {
                let fade = max(0, 1 - p.age / 1.6)
                let ring = (r - p.age * 0.9) / 0.09
                h += 0.06 * p.strength * fade * exp(-ring * ring)
            }
            // Each tool running: a small body circling in the well.
            if tools > 0, busy > 0.002 {
                for k in 0..<tools {
                    let a = t * 0.9 + 2 * Double.pi * Double(k) / Double(tools)
                    let bx = 0.55 * cos(a), by = 0.55 * sin(a)
                    let dd = (u - bx) * (u - bx) + (v - by) * (v - by)
                    h -= busy * 0.07 / (1 + dd / 0.006)
                }
            }
            return h
        }
        /// A point of the fabric on the screen, and how near it is (0 far … 1 near).
        func project(_ u: Double, _ v: Double, _ h: Double) -> (p: CGPoint, near: Double) {
            let x = u * cY - v * sY, z = u * sY + v * cY
            let up = h * cP + z * sP, deep = z * cP - h * sP
            let f = 2.8 / (2.8 + deep)
            return (CGPoint(x: cx + x * f * S, y: cy - 0.02 * H - up * f * S * 0.92), (1 - deep) / 2)
        }
        let lines = 13, samples = 56
        var paths: [(Path, Double)] = []
        for dir in 0..<2 {
            for k in 0..<lines {
                let c = -1.2 + 2.4 * Double(k) / Double(lines - 1)
                var path = Path(), near = 0.0
                for i in 0...samples {
                    let s = -1.2 + 2.4 * Double(i) / Double(samples)
                    let (u, v) = dir == 0 ? (s, c) : (c, s)
                    let pr = project(u, v, height(u, v))
                    if i == 0 { path.move(to: pr.p) } else { path.addLine(to: pr.p) }
                    near += pr.near
                }
                paths.append((path, near / Double(samples + 1)))
            }
        }
        // Light gathers at the bottom of the well and fades toward the grid's edges.
        let bottom = project(0, 0, height(0, 0)).p
        let colors: [Color] = look.color.map { c in [.white.opacity(0.95), c, c.opacity(0.8), c.opacity(0.45), c.opacity(0)] }
            ?? [Color(hex: 0xfdf4ff), Color(hex: 0xc084fc), Color(hex: 0x818cf8), Color(hex: 0x38bdf8).opacity(0.7), Color(hex: 0x38bdf8).opacity(0)]
        let shading = GraphicsContext.Shading.radialGradient(Gradient(colors: colors), center: bottom, startRadius: 0, endRadius: S * 1.25)
        let lw = max(0.6, min(W, H) / 230)
        gc.drawLayer { layer in
            layer.addFilter(.blur(radius: lw * 4))
            for (p, near) in paths { layer.opacity = 0.25 + 0.5 * near; layer.stroke(p, with: shading, lineWidth: lw * 2) }
        }
        for (p, near) in paths {
            gc.opacity = 0.35 + 0.6 * near
            gc.stroke(p, with: shading, lineWidth: lw)
        }
        gc.opacity = 1
        // The masses, glowing at the bottom of the well (brighter as it speaks).
        let glow = 1 + 0.8 * ph.speak * ph.loud + 0.3 * ph.work
        func body(_ u: Double, _ v: Double, _ size: Double, _ bright: Double) {
            let p = project(u, v, height(u, v)).p
            let g = S * size
            let halo = Gradient(colors: [Color.white.opacity(min(1, 0.9 * bright)), (look.color ?? Color(hex: 0xc084fc)).opacity(0.5 * bright), .clear])
            gc.fill(Path(ellipseIn: CGRect(x: p.x - g, y: p.y - g, width: 2 * g, height: 2 * g)),
                    with: .radialGradient(halo, center: p, startRadius: 0, endRadius: g))
        }
        let split = min(1, (ox * ox + oy * oy).squareRoot() / 0.08)
        body(ox, oy, 0.09 * glow, 1)
        body(-ox, -oy, 0.09 * glow * (0.55 + 0.45 * split), split)
        if tools > 0, busy > 0.002 {
            for k in 0..<tools {
                let a = t * 0.9 + 2 * Double.pi * Double(k) / Double(tools)
                body(0.55 * cos(a), 0.55 * sin(a), 0.045, busy)
            }
        }
    }

    // MARK: Black hole

    /// A black hole as the Event Horizon Telescope photographed it: a soft ring of orange light
    /// round a dark shadow, brightest where the gas comes toward us. Listening, gas spirals in from
    /// far out as you speak and the ring brightens. Thinking, the gas settles into a thin disk seen
    /// almost edge on, its far side bent by gravity into arcs over and under the shadow, the ring
    /// sharpening. Working, twin jets leave the poles, a bright knot along them for each step.
    /// Speaking, the ring follows the voice round its circumference and a hot spot circles it,
    /// flaring on loud syllables. A few stars behind it are pushed aside by its lensing.
    func drawBlackHole(_ gc: inout GraphicsContext, _ box: CGSize) {
        var d = dotCanvas(box)
        let ph = OrbPhases(engine)
        let n = pointBudget(box)
        let level = ph.level, loud = ph.loud, spectrum = ph.spectrum
        let ringR = 0.66, shadow = 0.44
        let blur = 0.13 * (ph.rest + ph.listen) + 0.05 * (ph.think + ph.work) + 0.09 * ph.speak
        let brightA = Double.pi / 2 + 0.35 * sin(t * 0.21)                 // where the gas comes toward us
        let spot = t * 1.3
        for i in 0..<n {
            let h1 = OrbPoints.hash(i, 21), h2 = OrbPoints.hash(i, 22), h3 = OrbPoints.hash(i, 23)
            let h4 = OrbPoints.hash(i, 24), h5 = OrbPoints.hash(i, 25)
            let role = i % 20
            var mx = Mix()
            // The thin disk's orbit (thinking, working): Keplerian. Each point keeps its angle in the
            // ring, so the ring flattens into the disk and rounds back out of it.
            let rd = 0.8 + 0.8 * pow(h2, 0.8)
            let th = 2 * Double.pi * h5 + t * 0.9 * pow(rd, -1.5)
            // The ring (rest, listening, speaking): a blurred band, Doppler-bright on one side.
            let a = th
            let g = spread(h2, h3, h4)
            let rim = abs(atan2(cos(a), -sin(a))) / .pi                     // 0 at the top … 1 at the bottom
            let swell = 1 + 0.14 * ph.speak * spectrum.band(at: rim) + 0.05 * ph.listen * level
            let rr = ringR * swell + blur * g
            let doppler = pow((1 + cos(a - brightA)) / 2, 1.6)
            let flare = ph.speak * loud * 1.3 * exp(-pow(remainder(a - spot, 2 * .pi) / 0.28, 2))
            let ringB = (0.22 + 0.9 * doppler) * exp(-g * g * 1.6) * (1 + 0.6 * ph.listen * level + 0.6 * ph.speak * loud) + flare
            let ring = (x: rr * cos(a), y: rr * sin(a))
            // The disk, its far side hidden by the shadow.
            let dx = rd * cos(th), dy = rd * sin(th) * 0.15
            let tilt = -0.14
            let disk = (x: dx * cos(tilt) - dy * sin(tilt), y: dx * sin(tilt) + dy * cos(tilt))
            let hidden = sin(th) < 0 && abs(dx) < shadow ? 0.0 : 1.0
            let diskB = (0.25 + 0.85 * pow((1 + cos(th)) / 2, 2)) * (1.1 - 0.4 * (rd - 0.8)) * hidden
            // Its far side's image, bent over the top of the shadow (and, fainter, under it).
            let over = h3 > 0.28
            let la = over ? Double.pi + Double.pi * h1 : Double.pi * h1
            let lr = over ? 0.5 + 0.16 * h4 * h4 : 0.47 + 0.05 * h4
            let lens = (x: lr * cos(la), y: lr * sin(la))
            let lensB = (over ? 0.75 : 0.35) * (0.6 + 0.4 * pow((1 + cos(la - Double.pi * 1.5)) / 2, 2))
            switch role {
            case 0..<14:
                mx.add(ph.rest + ph.listen + ph.speak, ring.x, ring.y, ringB)
                if role < 9 { mx.add(ph.think + ph.work, disk.x, disk.y, diskB) }
                else { mx.add(ph.think + ph.work, lens.x, lens.y, lensB) }
            case 14..<18:
                // Rest: a faint halo; listening: gas spiralling in along three streams.
                let ha = a * 0.9 + 0.3, hr = 0.85 + 0.6 * h4
                mx.add(ph.rest, hr * cos(ha), hr * sin(ha), 0.08 + 0.12 * h5)
                let s = fract(h4 + t * 0.28)
                let fr = 1.6 - 0.9 * s
                let fa = 2 * Double.pi * (Double(Int(h5 * 3)) / 3) + 2.4 / fr + 0.12 * (h3 - 0.5)
                let fall = (0.15 + 0.8 * s) * (0.35 + 0.9 * level) * pow(sin(Double.pi * s), 0.5)
                mx.add(ph.listen, fr * cos(fa), fr * sin(fa), fall)
                mx.add(ph.think + ph.work, disk.x, disk.y, diskB)
                mx.add(ph.speak, ring.x, ring.y, ringB)
            default:
                // Stars behind it, pushed aside by its lensing; working: the jets.
                let sx = 3.2 * h1 - 1.6, sy = 3.2 * h4 - 1.6
                let sr = max(0.05, (sx * sx + sy * sy).squareRoot())
                let pushed = sr + 0.09 / sr
                let starB = pushed < shadow + 0.08 ? 0 : 0.1 + 0.22 * h5 * (0.7 + 0.3 * sin(t * 1.7 + h3 * 40))
                mx.add(1 - ph.work, sx / sr * pushed, sy / sr * pushed, starB)
                let side: Double = h3 < 0.5 ? -1 : 1
                let s = fract(h2 + t * 0.55)
                let jy = side * (0.42 + 1.2 * s)
                let jx = (h5 - 0.5) * 0.05 * (1 + 3 * s) + 0.08 * s * sin(t * 0.8 + side)
                let jetB = (0.45 + 0.75 * (1 - s)) * pow(sin(Double.pi * s), 0.4)
                mx.add(ph.work, jx, jy, jetB)
            }
            // Whatever is behind the hole is hidden by its shadow, in every phase and between them.
            if sin(th) < 0, role < 18 {
                let r = (mx.x * mx.x + mx.y * mx.y).squareRoot()
                mx.b *= smoothstep(shadow * 0.85, shadow * 1.02, r)
            }
            place(&d, mx.x * 1.2, mx.y * 1.2, mx.b, OrbPoints.hash(i, 26), phase: a, lum: min(1, mx.b))
        }
        // Under the points: the soft glow of the photographs, brightest where the gas comes toward
        // us; with the disk, a thin sharp photon ring round the shadow.
        let soft = 0.75 * (ph.rest + ph.listen + ph.speak) + 0.3 * (ph.think + ph.work)
        let stops = (0...24).map { k -> Gradient.Stop in
            let a = 2 * Double.pi * Double(k) / 24
            let dop = pow((1 + cos(a - brightA)) / 2, 1.6)
            let flareGlow = ph.speak * loud * exp(-pow(remainder(a - spot, 2 * .pi) / 0.4, 2))
            let alpha = soft * (0.14 + 0.62 * dop + 0.5 * flareGlow) * (1 + 0.4 * ph.listen * level)
            return .init(color: Color(hex: 0xf08a2c).opacity(min(1, alpha)), location: Double(k) / 24)
        }
        let center = CGPoint(x: d.cx, y: d.cy), glowR = ringR * 1.2 * d.R
        gc.drawLayer { layer in
            layer.addFilter(.blur(radius: d.R * 0.11))
            layer.stroke(Path(ellipseIn: CGRect(x: center.x - glowR, y: center.y - glowR, width: 2 * glowR, height: 2 * glowR)),
                         with: .conicGradient(Gradient(stops: stops), center: center, angle: .zero), lineWidth: d.R * 0.24)
        }
        let photon = 0.47 * 1.2 * d.R, crisp = 0.55 * (ph.think + ph.work)
        if crisp > 0.01 {
            gc.stroke(Path(ellipseIn: CGRect(x: center.x - photon, y: center.y - photon, width: 2 * photon, height: 2 * photon)),
                      with: .color(Color(hex: 0xffd59a).opacity(crisp)), lineWidth: max(0.6, d.px * 0.9))
        }
        // The photographed palette: dark red in the dim levels to a yellow-white peak.
        finish(&gc, d, palette: [Color(hex: 0x5c1106).opacity(0.55), Color(hex: 0xa2310c).opacity(0.7), Color(hex: 0xe0661a).opacity(0.8),
                                 Color(hex: 0xf8ac3c).opacity(0.92), Color(hex: 0xfff2cc)])
    }

    // MARK: Accretion

    /// A solar system forming: a young star in a disk of dust turning at Kepler's pace, dark lanes
    /// between its rings (as the disk round HL Tauri was photographed). Listening, streams of dust
    /// fall onto the disk with your voice. Thinking, the dust gathers into seven clumps along its
    /// orbits. Working, the clumps merge two by two into planets that clear their lanes, a flash
    /// for each step. Speaking, each ring of the disk glows with one band of the voice (the inner
    /// rings its low pitches), a spiral wave runs through it and the star flares.
    func drawAccretion(_ gc: inout GraphicsContext, _ box: CGSize) {
        var d = dotCanvas(box)
        let ph = OrbPhases(engine)
        let n = pointBudget(box)
        let level = ph.level, loud = ph.loud, spectrum = ph.spectrum
        let pitch = 0.46, cP = cos(pitch), sP = sin(pitch)
        let roll = -0.16, cR = cos(roll), sR = sin(roll)
        let rings = [0.3, 0.64, 0.97, 1.3]
        let lane = 0.35 * ph.rest + 0.45 * ph.listen + 0.6 * ph.think + 1.0 * ph.work + 0.6 * ph.speak
        // The clumps (thinking), on both sides of each lane, and the planets they merge into
        // (working), each in the lane it clears.
        let clumpR = [0.36, 0.58, 0.7, 0.9, 1.03, 1.22, 1.36]
        let planetR = [0.47, 0.8, 1.13, 1.42]
        /// A place on an orbit: its angle turns at the pace of the orbit `kepler` (never of a radius
        /// that changes with the phase: the pace multiplies the clock, so it would jump).
        func orbit(_ r: Double, _ a0: Double, kepler: Double? = nil) -> (x: Double, z: Double) {
            let a = a0 + t * 0.55 * pow(kepler ?? r, -1.5)
            return (r * cos(a), r * sin(a))
        }
        func screen(_ x: Double, _ y: Double, _ z: Double) -> (x: Double, y: Double, z: Double) {
            let sy = y * cP - z * sP, sz = y * sP + z * cP
            return (x * cR - sy * sR, x * sR + sy * cR, sz)
        }
        let clumps = clumpR.enumerated().map { k, r in orbit(r, Double(k) * 2.4) }
        let planets = planetR.enumerated().map { k, r -> (x: Double, z: Double) in
            // Each planet sits where its two clumps meet (the last one alone).
            let a = clumps[min(2 * k, clumps.count - 1)], b = clumps[min(2 * k + 1, clumps.count - 1)]
            let mx = (a.x + b.x) / 2, mz = (a.z + b.z) / 2, m = max(1e-3, (mx * mx + mz * mz).squareRoot())
            return (mx / m * r, mz / m * r)
        }
        for i in 0..<n {
            let h1 = OrbPoints.hash(i, 31), h2 = OrbPoints.hash(i, 32), h3 = OrbPoints.hash(i, 33)
            let h4 = OrbPoints.hash(i, 34), h5 = OrbPoints.hash(i, 35)
            var mx = Mix()
            if i % 45 == 0 {
                // The young star: a dense bright core that flares as it speaks.
                let r = 0.07 * h2, a = 2 * Double.pi * h1
                let p = screen(r * cos(a), 0.6 * r * sin(a), 0)
                let b = 1.1 + 0.6 * ph.speak * loud + 0.3 * ph.listen * level
                place(&d, p.x * 1.15, p.y * 1.15, b, h3, phase: a, lum: 1, size: 1.6)
                continue
            }
            // The disk: bright rings with dark lanes between them, sharper as planets clear the
            // lanes; a fifth of the dust lies between the rings.
            let ringK = min(rings.count - 1, Int(h2 * Double(rings.count)))
            let diffuse = OrbPoints.hash(i, 37) < 0.22
            let width = 0.06 * (1 + 0.25 * Double(ringK)) * (1.9 - 0.95 * lane)
            let g = spread(h4, OrbPoints.hash(i, 39), h5)
            let base = diffuse ? 0.2 + 1.3 * OrbPoints.hash(i, 38) : rings[ringK] + width * g
            let rr = max(0.12, base)
            let kepler = max(0.12, diffuse ? base : rings[ringK] + 0.06 * (1 + 0.25 * Double(ringK)) * 1.4 * g)
            let ringBand = spectrum.band(at: Double(ringK) / Double(rings.count - 1))
            let wob = 1 + 0.03 * ph.speak * ringBand * sin(t * 2.5 + h3 * 6)
            let o = orbit(rr * wob, 2 * Double.pi * h1, kepler: kepler)
            let thick = (h3 - 0.5) * 0.05 * rr
            let disk = screen(o.x, thick, o.z)
            let theta = atan2(o.z, o.x)
            let spiral = 1 + 0.6 * ph.speak * loud * max(0, cos(2 * theta - 4 * log(rr) - t * 1.8))
            let near = 0.6 + 0.4 * smoothstep(-1.2, 1.2, -o.z)
            let diskB = (diffuse ? 0.16 : 0.3 + 0.45 * pow(1 - min(1, rr / 1.6), 0.6)) * near
            mx.add(ph.rest, disk.x, disk.y, diskB)
            mx.add(ph.speak, disk.x, disk.y, diskB * (0.55 + 1.3 * ringBand) * spiral)
            let role = i % 10
            // Listening: three tenths of the dust falls in from the envelope along two streamers.
            if role < 3 {
                let s = fract(h4 + t * 0.22)
                let fr = 1.75 - 1.0 * s
                let fa = Double(Int(h5 * 2)) * .pi + 1.9 / fr + 0.15 * (h3 - 0.5) + t * 0.05
                let fall = screen(fr * cos(fa), -0.32 * (1 - s) * (h3 < 0.5 ? 1 : -1), fr * sin(fa))
                let fallB = (0.18 + 0.7 * s) * (0.35 + 0.9 * level) * pow(sin(Double.pi * s), 0.5)
                mx.add(ph.listen, fall.x, fall.y, fallB)
            } else {
                mx.add(ph.listen, disk.x, disk.y, diskB * (1 + 0.5 * level))
            }
            // Thinking: four tenths gather into the clump on their orbit; working, into its planet.
            if (3..<7).contains(role) {
                let k = clumpR.enumerated().min { abs($0.element - kepler) < abs($1.element - kepler) }!.offset   // fixed: never changes clump
                let c = clumps[k], p = planets[min(k / 2, planets.count - 1)]
                let g1 = spread(OrbPoints.hash(i, 40), OrbPoints.hash(i, 41), OrbPoints.hash(i, 42))
                let g2 = spread(OrbPoints.hash(i, 43), OrbPoints.hash(i, 44), OrbPoints.hash(i, 45))
                let g3 = spread(OrbPoints.hash(i, 46), OrbPoints.hash(i, 47), OrbPoints.hash(i, 48))
                // Thinking, a round cloud of dust on the orbit; working, the clouds merged into a small
                // round planet. The dust gets there along its orbit, the nearer way round (a drift
                // round its ring, not a straight line across the disk).
                let cw = ph.think + ph.work
                if cw > 0.002 {
                    let pw = ph.work / cw
                    let ca = atan2(c.z, c.x), pa = atan2(p.z, p.x)
                    let ta = ca + pw * remainder(pa - ca, 2 * .pi)
                    let tr = clumpR[k] + pw * (planetR[min(k / 2, planetR.count - 1)] - clumpR[k])
                    let r0 = rr * wob
                    let a = theta + cw * remainder(ta - theta, 2 * .pi)
                    let r = r0 + cw * (tr - r0)
                    let blob = cw * (0.1 * (1 - pw) + 0.03 * pw)
                    let pos = screen(r * cos(a) + blob * g1, thick * (1 - cw) + blob * g3, r * sin(a) + blob * g2)
                    let nearC = 0.7 + 0.3 * smoothstep(-1.2, 1.2, -r * sin(a))
                    let b = (1 - pw) * (0.55 + 0.35 * (1 - abs(g1))) * nearC + pw * (1.0 + 0.2 * h2)
                    mx.x = pos.x; mx.y = pos.y                     // the other phases' place is this at cw = 0
                    mx.b += cw * b; mx.size += cw * (1 + 0.5 * pw)
                }
            } else {
                mx.add(ph.think, disk.x, disk.y, diskB * 0.75)
                mx.add(ph.work, disk.x, disk.y, diskB * 0.6)
            }
            let size = mx.size > 0 ? mx.size / max(0.001, ph.rest + ph.listen + ph.think + ph.work + ph.speak) : 1
            place(&d, mx.x * 1.15, mx.y * 1.15, mx.b, OrbPoints.hash(i, 36), phase: theta, lum: min(1, mx.b), size: max(1, size))
        }
        // Dust lit by a young star, as the disk round HL Tauri was photographed: rose-brown in the
        // dim levels, orange rings, a white-gold peak.
        finish(&gc, d, palette: [Color(hex: 0x4a1c2e).opacity(0.55), Color(hex: 0x9a3a1c).opacity(0.72), Color(hex: 0xe0782e).opacity(0.84),
                                 Color(hex: 0xf8c070).opacity(0.94), Color(hex: 0xfff6e0)])
    }
}
