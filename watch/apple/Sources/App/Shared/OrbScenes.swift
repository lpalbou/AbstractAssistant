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

    mutating func dot(_ x: Double, _ y: Double, _ bright: Double, _ dither: Double, size: Double = 1) {
        guard bright > 0.03 * dither else { return }
        let b = min(4, max(0, Int(bright * 5 + dither - 0.5)))
        let s = px * size
        paths[b].addRect(CGRect(x: cx + x * R - s / 2, y: cy + y * R - s / 2, width: s, height: s))
    }
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
    /// icosidodecahedron, turning slowly as one body. A voice sets it in motion: each ring is driven
    /// by its own band (low pitches the first, high the last), swinging about its own diameter and
    /// spinning its beads, faster and wider as its band is louder; silence lets the structure settle
    /// back. Thinking spins it up like a gyroscope.
    func drawRings(_ gc: inout GraphicsContext, _ box: CGSize) {
        var d = dotCanvas(box)
        let ph = OrbPhases(engine)
        let th = ph.think, busy = ph.work
        let yaw = engine.ringTurn, tilt = 0.42 + 0.1 * sin(t * 0.21)
        let cY = cos(yaw), sY = sin(yaw), cT = cos(tilt), sT = sin(tilt)
        let per = max(30, pointBudget(box) / OrbEngine.ringCount)
        for i in 0..<OrbEngine.ringCount {
            let ring = RingGeometry.rings[i]
            let swing = engine.ringSwing[i]
            // The swing about the ring's own diameter `u`: small at rest, wide with its band.
            // Working: a wave runs across the rings in turn (a machine running), the beads racing.
            let theta = (0.04 + 0.22 * swing) * sin(engine.ringPhase[i]) + 0.3 * th * sin(t * 1.4 + Double(i))
                + 0.45 * busy * sin(t * 3 - Double(i) * .pi / 3)
            let ct = cos(theta), st = sin(theta)
            let vx = ring.v.0 * ct + ring.n.0 * st, vy = ring.v.1 * ct + ring.n.1 * st, vz = ring.v.2 * ct + ring.n.2 * st
            // Its size is its harmonic: a quiet band draws its ring in, a loud one pushes it out.
            let radius = 0.97 + engine.engagement * (0.62 * swing - 0.22)
            let spin = engine.ringSpin[i]
            for k in 0..<per {
                let s = 2 * Double.pi * Double(k) / Double(per)
                let cs = cos(s), sn = sin(s)
                var x = radius * (cs * ring.u.0 + sn * vx)
                var y = radius * (cs * ring.u.1 + sn * vy)
                var z = radius * (cs * ring.u.2 + sn * vz)
                // The structure turns as one body (y axis), seen tilted (x axis).
                let bx = x * cY + z * sY, bz = -x * sY + z * cY
                x = bx; let y1 = y * cT - bz * sT; z = y * sT + bz * cT; y = y1
                // Five beads run around each ring at its own speed: its rotation reads.
                let bead = pow(max(0, cos(5 * (s - spin - 3 * busy * t))), 10)
                let depth = smoothstep(-1.1, 1.0, z)
                let lum = 0.4 + 0.6 * bead
                let bright = lum * (0.3 + 0.7 * depth) * (0.7 + 0.8 * swing) + 0.25 * th * bead + 0.45 * busy * bead
                place(&d, x, y, bright, OrbPoints.hash(i * 4096 + k, 14), phase: s, lum: lum, edge: 1.1)
            }
        }
        finish(&gc, d)
    }

    // MARK: Face

    /// A portrait in light: a sculpted head and shoulders, the face's real relief (brows, nose, lips,
    /// chin, the eyes set in their sockets) lit from the upper left as it turns, soft glowing eyes,
    /// short hair. It blinks, breathes and moves its head a little. Listening, it turns to offer its
    /// ear and cups a hand behind it, your voice arriving as arcs in the hand's cone; thinking, it looks
    /// up and aside; working, it reads (quick glances down and aside) while a fine scan line passes
    /// down its face; speaking, its lips follow its voice like speech, the jaw following.
    func drawFace(_ gc: inout GraphicsContext, _ box: CGSize) {
        var d = dotCanvas(box)
        let ph = OrbPhases(engine)
        let th = ph.think, listen = ph.listen, busy = ph.work
        let mouth = MouthShape(engine: engine, smileBase: 1.5 + 0.2 * listen - 0.2 * th - 0.1 * busy)
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
        let my = FaceGeometry.mouthY
        let faceGazeX = (0.015 * sin(t * 0.37) + 0.03 * th) * (1 - listen) - 0.03 * listen + 0.035 * glance
        let faceGazeY = -0.03 * th + 0.022 * busy
        func put(_ x: Double, _ y: Double, _ b: Double, _ dither: Double, _ phase: Double, size: Double = 1) {
            let sx = x * scale, sy = y * scale + shift
            let rr = (sx * sx + sy * sy).squareRoot()
            guard rr < 1.98 else { return }
            place(&d, sx, sy, b * (1 - smoothstep(1.6, 1.98, rr)), dither, phase: phase, lum: 0.7, size: size)
        }
        for p in FaceSculpt.points(count: Int(Double(pointBudget(box)) * 1.4)) {
            var x = p.x, y = p.y, z = p.z
            if p.part == .face {
                // The mouth: the jaw drops below it, the opening between the lips goes dark.
                y += mouth.jaw(x, y)
                if mouth.open > 0.06 {
                    // The mouth opens wider than tall, its inside soft dark (never a hole).
                    let gap = 0.09 * mouth.open
                    let inside = exp(-pow(x / (0.16 * mouth.width), 2) - pow((y - my - gap * 0.5 + 0.02 * pow(x / 0.17, 2)) / (gap + 0.004), 2))
                    if inside > 0.5 && OrbPoints.hash(Int(x * 1000 + y * 7000), 5) < 0.75 { continue }
                }
            }
            var bright: Double
            if p.part == .body {
                y += breathe
                bright = p.tone * skin(p.nx, p.ny, p.nz)
                put(x, y, bright * (1 - smoothstep(1.2, 1.6, y)), p.dither, p.phase, size: 0.9)
                continue
            }
            let r = pose.apply(x, y, z)
            let n = pose.apply(p.nx, p.ny + FaceGeometry.neckY, p.nz)            // a direction: turn only
            let nn = (x: n.x, y: n.y - FaceGeometry.neckY - pose.lift, z: n.z)
            guard nn.z > -0.05 else { continue }
            bright = p.tone * skin(nn.x, nn.y, nn.z)
            // The eyes' whites: soft, even, a little brighter than the skin; the pupil left dark.
            let ex = (abs(p.x) - FaceGeometry.eyeX) / 0.085, ey = (p.y - FaceGeometry.eyeY) / 0.04
            if ex * ex + ey * ey < 1 {
                let gx = p.x - (p.x > 0 ? 1 : -1) * FaceGeometry.eyeX - faceGazeX, gy = p.y - FaceGeometry.eyeY - faceGazeY
                let r = (gx * gx + gy * gy).squareRoot()
                if r < 0.014 && blink > 0.35 { continue }
                bright = r < 0.03 && blink > 0.35 ? 0.3 : 0.5
            }
            if busy > 0.01 { bright += busy * 0.5 * exp(-pow((y - scanY) / 0.022, 2)) }
            bright += 0.08 * engine.signal
            x = r.x; y = r.y; z = r.z
            put(x, y, bright, p.dither, p.phase, size: 0.8 + 0.4 * smoothstep(-0.3, 0.6, z))
        }
        // Friendly eyes: an almond outline (the upper lid stronger, the lower one lifted a little
        // by the smile), an iris with a dark pupil and a catchlight, a gently raised brow. The gaze
        // moves; the lids close in a blink.
        let gazeX = (0.015 * sin(t * 0.37) + 0.03 * th) * (1 - listen) - 0.03 * listen + 0.035 * glance
        let gazeY = -0.03 * th + 0.022 * busy
        let warm = 1 + 0.15 * ph.speak + 0.1 * listen                       // the eyes smile as it talks
        func eyePoint(_ x: Double, _ y: Double, _ b: Double, _ dither: Double, lift: Double = 0.02) {
            let q = pose.apply(x, y, (ImprintGeometry.relief(x, y) ?? 0.5) + lift)
            guard q.z > 0.15 else { return }
            put(q.x, q.y, b, dither, x * 9)
        }
        for side in [-1.0, 1.0] {
            let cx = side * FaceGeometry.eyeX, cy = FaceGeometry.eyeY
            for j in 0..<26 {                                                // the lids
                let u = 2 * Double(j) / 25 - 1
                let upper = cy - 0.042 * (1 - u * u) * blink - 0.004
                let lower = cy + (0.024 - 0.008 * (warm - 1) * 4) * (1 - u * u) * blink + 0.004
                eyePoint(cx + 0.085 * u, upper, 0.45 * (0.6 + 0.4 * (1 - u * u)), OrbPoints.hash(j, side))
                if j % 2 == 0 { eyePoint(cx + 0.075 * u, lower, 0.22, OrbPoints.hash(j, side + 2)) }
                // The brow: a soft arc, raised a little (more as it listens).
                // Lifted by a stressed syllable as it speaks, and by your voice as it listens.
                let lift = 0.015 * listen + 0.025 * listen * level + 0.03 * ph.speak * ph.loud
                let by = cy - 0.12 - 0.03 * (1 - u * u) - lift - 0.01 * th * (side > 0 ? 1 : 0)
                if j % 2 == 1 { eyePoint(cx + 0.1 * u + 0.012 * side, by, 0.4 * (1 - 0.6 * u * u), OrbPoints.hash(j, side + 4)) }
            }
            guard blink > 0.35 else { continue }
            let ix = cx + gazeX, iy = cy + gazeY * blink
            for j in 0..<24 {                                                // the iris ring
                let a = 2 * Double.pi * Double(j) / 24
                let ring = j % 2 == 0 ? 0.03 : 0.022
                let py = iy + ring * sin(a) * blink
                guard py > cy - 0.04 * blink else { continue }               // under the upper lid
                eyePoint(ix + ring * cos(a), py, ring > 0.025 ? 0.42 : 0.3, OrbPoints.hash(j, side + 6), lift: 0.03)
            }
            for j in 0..<2 {                                                 // the catchlight
                eyePoint(ix - 0.01 + 0.006 * Double(j), iy - 0.011, 0.95, 0.5, lift: 0.04)
            }
        }
        // The lips: a gentle upturned line where they meet; as it talks they part (the lower lip
        // following the jaw), rounder on dark vowels, wider on bright ones, the upper teeth showing
        // on open syllables.
        let smile = 0.032 + 0.01 * listen - 0.012 * th - 0.01 * mouth.pout
        for j in 0..<48 {
            let u = 2 * Double(j) / 47 - 1
            let xu = 0.17 * mouth.width * u
            let base = my - smile * u * u
            let along = 1 - u * u
            let upper = base - (0.022 * mouth.open + 0.008 * mouth.pout) * along
            let lower = base + (0.13 * mouth.open + 0.01 * mouth.pout) * pow(along, 0.8)
            let fade = 1 - 0.5 * u * u
            eyePoint(xu, upper, 0.6 * fade, OrbPoints.hash(j, 71))
            if mouth.open > 0.04 { eyePoint(xu * (1 - 0.06 * mouth.open), lower, 0.5 * fade, OrbPoints.hash(j, 72)) }
            if mouth.open > 0.25, abs(u) < 0.6, j % 2 == 0 {
                eyePoint(xu * 0.9, upper + 0.014, 0.28 * min(1, (mouth.open - 0.25) * 4), OrbPoints.hash(j, 73))
            }
        }
        if listen > 0.02 { drawListeningHand(&d, pose: pose, listen: listen, scale: scale, shift: shift) }
        finish(&gc, d)
    }

    /// Skin lit from the upper left in front: soft, a gentle sheen.
    private func skin(_ nx: Double, _ ny: Double, _ nz: Double) -> Double {
        // Soft frontal light (a portrait's key light, a little from above and left): no hard
        // shadows under the brows.
        let l = (x: -0.25, y: -0.3, z: 0.92)
        let diffuse = max(0, nx * l.x + ny * l.y + nz * l.z)
        let rim = pow(1 - max(0, nz), 3) * 0.3
        return 0.22 + 0.62 * diffuse + 0.12 * pow(diffuse, 8) + rim
    }

    /// The hand cupped behind the ear it offers, its forearm from below, and the voice it listens to
    /// as arcs flowing into the cone the hand makes (brighter as you speak louder).
    private func drawListeningHand(_ d: inout DotCanvas, pose: HeadPose, listen: Double, scale: Double, shift: Double) {
        let ear = pose.apply(FaceGeometry.halfWidth * 0.98, -0.1, 0)
        let ease = listen * listen * (3 - 2 * listen)
        // The wrist rises from below the frame to just under and behind the ear.
        let wx = 1.25 + (ear.x + 0.2 - 1.25) * ease, wy = 2.1 + (ear.y + 0.27 - 2.1) * ease
        let hand = 1.25
        for p in FaceGeometry.handPoints {
            let x = (wx + hand * p.x) * scale, y = (wy + hand * p.y) * scale + shift
            if (x * x + y * y).squareRoot() > 1.98 { continue }
            place(&d, x, y, p.lum * ease, p.dither, phase: p.phase, lum: p.lum)
        }
        guard ease > 0.3 else { return }
        // The cone: from the cupped hand out to the right, and arcs of your voice travelling in.
        let ex = (ear.x + 0.06) * scale, ey = ear.y * scale + shift
        let open = 0.62
        for side in [-1.0, 1.0] {
            for k in 0..<18 {
                let r = 0.2 + 0.05 * Double(k)
                place(&d, ex + r * cos(side * open), ey + r * sin(side * open), 0.22 * ease, OrbPoints.hash(k, side), phase: 0)
            }
        }
        for j in 0..<4 {
            let age = (t * 0.8 + Double(j) / 4).truncatingRemainder(dividingBy: 1)   // 0 far … 1 at the ear
            let r = 0.2 + 0.85 * (1 - age)
            let level = engine.history.value(secondsAgo: (1 - age) * 1.1)
            let bright = ease * (0.12 + 0.95 * level) * smoothstep(0, 0.2, age) * (1 - smoothstep(0.85, 1, age))
            let m = Int(14 + 26 * r)
            for k in 0..<m {
                let a = -open + 2 * open * Double(k) / Double(m - 1)
                place(&d, ex + r * cos(a), ey + r * sin(a), bright, OrbPoints.hash(j * 97 + k, 3), phase: a)
            }
        }
    }

    // MARK: Ocean

    /// A sea at night filling the frame: the water in rows that close up toward the horizon, a moon
    /// with its glade, a few stars. The waves are Gerstner waves (sharp crests, long waves faster
    /// than short ones); the light is the moon reflected off each wave's actual tilt, the sky's glow
    /// reflected more at grazing angles (brighter toward the horizon), foam on steep crests. At rest
    /// a low swell; a voice raises it, low pitches the long waves, high pitches the short ones, the
    /// last second of the voice travelling across the water: toward you while it speaks, away while
    /// you speak. While it thinks the sea calms and rain falls, each drop ringing the water.
    func drawOcean(_ gc: inout GraphicsContext, _ box: CGSize) {
        let half = Double(min(box.width, box.height)) / 2
        // The scene's own units: the frame's half height, its width stretched over the whole frame
        // (`ax`: the frame's width over its height; the sea can be wider than tall).
        var d = DotCanvas(cx: Double(box.width) / 2, cy: Double(box.height) / 2, R: Double(box.height) / 2, px: max(0.55, half / 105))
        let ax = Double(box.width) / Double(box.height)
        let ph = OrbPhases(engine)
        let e = engine.engagement, th = ph.think, talk = engine.talking, hist = engine.history, busy = ph.work
        // Working: a lighthouse on the horizon at the left, its beam sweeping the water (searching).
        let beamA = 0.45 + 0.25 * sin(t * 0.9), lightX = -0.82
        let hz = OceanGeometry.horizon, F = OceanGeometry.focal
        let toward = 2 * talk - 1                                       // +1: the waves come toward you
        let calm = 1 - 0.65 * th
        let lowB = (engine.bands[0] + engine.bands[1]) / 2, midB = engine.bands[3], highB = engine.bands[6]
        let moon = OceanGeometry.moon
        let moonDir = OceanGeometry.moonDirection
        let moonGlow = 0.85 + 0.1 * sin(t * 0.5) + 0.3 * engine.signal
        let waves = OceanGeometry.waves
        // The rain while it thinks: drops at their places on the water, in turn.
        var drops: [(x: Double, d: Double, age: Double, fade: Double)] = []
        if th > 0.01 {
            let period = 1.4
            for i in 0..<7 {
                let shifted = t + Double(i) * period / 7
                let n = Int(shifted / period), age = shifted - Double(n) * period
                let seed = n * 7 + i * 13
                drops.append((x: (OrbPoints.hash(seed, 31) - 0.5) * 3, d: 1.4 + 4.5 * OrbPoints.hash(seed, 37),
                              age: age, fade: th * pow(1 - age / period, 2)))
            }
        }
        for p in OceanGeometry.points(count: Int(Double(pointBudget(box)) * 1.25 * ax)) {
            var bright: Double
            var sx = p.sx, sy = p.sy
            switch p.kind {
            case .moon:
                bright = p.lum * moonGlow * (1 - 0.3 * busy)
            case .star:
                bright = p.lum * (0.6 + 0.4 * sin(t * 1.3 + p.phase)) * (1 - 0.5 * th)
            case .water:
                let X = p.wx, D = p.wd
                // Where the voice now is on the water (the last 1.2 s along the way).
                let ago = talk * min(1.2, max(0, (12 - D) / 9)) + (1 - talk) * min(1.2, max(0, (D - 1) / 9))
                let v = e * hist.value(secondsAgo: ago)
                var dx = 0.0, dd = 0.0, h = 0.0, sxSlope = 0.0, sdSlope = 0.0, squeeze = 0.0
                for w in waves {
                    let gain = w.low * (0.6 + 1.6 * lowB) + w.mid * (0.6 + 1.6 * midB) + w.high * (0.6 + 1.6 * highB)
                    let a = w.rest * calm * (1 + 5.5 * v * gain)
                    let px = w.dirX, pd = -w.dirD * toward
                    let ph = w.k * (px * X + pd * D) - w.omega * t + w.phase
                    let c = cos(ph), s = sin(ph)
                    let q = min(0.9, w.steep * 0.7)                      // the crests sharpen, never loop
                    dx -= q * a * px * s; dd -= q * a * pd * s
                    h += a * c
                    sxSlope -= a * w.k * px * s; sdSlope -= a * w.k * pd * s
                    squeeze += q * a * w.k * c
                }
                for drop in drops where drop.fade > 0.002 {
                    let ddx = X - drop.x, ddd = (D - drop.d) * 0.8
                    let dist = (ddx * ddx + ddd * ddd).squareRoot() - 0.85 * drop.age
                    let k = exp(-pow(dist / 0.16, 2)) * drop.fade
                    h += 0.06 * k * cos(dist * 22)
                    sdSlope += 0.8 * k * sin(dist * 22)
                }
                let Xw = X + dx, Dw = max(0.5, D + dd)
                sx = Xw * F / Dw; sy = hz + F * (1 - h) / Dw
                // Light: the view ray reflected off the wave's normal.
                let vl = (Xw * Xw + (h - 1) * (h - 1) + Dw * Dw).squareRoot()
                let vx = Xw / vl, vy = (h - 1) / vl, vz = Dw / vl
                let nl = (sxSlope * sxSlope + 1 + sdSlope * sdSlope).squareRoot()
                let nx = -sxSlope / nl, ny = 1 / nl, nz = -sdSlope / nl
                let vn = vx * nx + vy * ny + vz * nz
                let rx = vx - 2 * vn * nx, ry = vy - 2 * vn * ny, rz = vz - 2 * vn * nz
                let fresnel = 0.02 + 0.98 * pow(1 - min(1, max(0, -vn)), 5)
                let skyGlow = 0.12 + 0.55 * exp(-max(0, ry) * 7)
                let spec = pow(max(0, rx * moonDir.x + ry * moonDir.y + rz * moonDir.z), 60) * 2.2 * moonGlow
                // The water's own faint glow, a little stronger near the viewer, so the near waves read.
                bright = fresnel * skyGlow + 0.07 + 0.1 * smoothstep(0.1, 0.9, p.sy) + spec
                if squeeze > 0.55 { bright += 0.9 * (squeeze - 0.55) * (0.3 + v) }          // foam on steep crests
                for drop in drops where drop.age < 0.12 {
                    let ddx = X - drop.x, ddd = D - drop.d
                    bright += 2.5 * exp(-(ddx * ddx + ddd * ddd) / 0.006) * drop.fade             // the splash
                }
                if busy > 0.01 {
                    let a = atan2(p.sy - hz, p.sx - lightX)
                    let inBeam = exp(-pow((a - beamA) / 0.12, 2)) * (1 - smoothstep(0.9, 3.0, hypot(p.sx - lightX, p.sy - hz)))
                    bright += busy * 1.8 * inBeam * (0.5 + 0.5 * max(0, sin(13 * X + 7 * D - 3 * t)))
                }
                bright *= p.lum
            case .rain:
                guard th > 0.01 else { continue }
                let fall = (t * 1.7 + p.phase).truncatingRemainder(dividingBy: 1)
                sx = p.sx + 0.08 * fall; sy = -1 + 1.9 * fall + p.sy * 0.04
                if sy > hz + F / 6 { continue }
                bright = 0.35 * th * p.lum
            }
            // The frame's edges dissolve into the night.
            let edge = (1 - smoothstep(0.96, 1.02, abs(sx))) * (1 - smoothstep(0.92, 1.0, sy)) * (1 - smoothstep(0.88, 1.0, -sy))
            // The sea's work is its lighthouse: no ring pushes the water.
            let px0 = sx * ax, py0 = sy
            bright = bright * edge * countdownDim(px0 / 0.75, py0 / 0.75)
            d.dot(px0, py0, bright, p.dither)
        }
        // The lighthouse's lamp, on the horizon, while it works.
        if busy > 0.01 {
            for k in 0..<10 {
                let a = 2 * Double.pi * Double(k) / 10
                d.dot((lightX + 0.012 * cos(a)) * ax, hz - 0.02 + 0.012 * sin(a), 1.3 * busy, 0.5)
            }
        }
        let pal = OrbPalette.colors(for: look.color)
        // The moon's halo under it.
        let halo = d.R * 0.32, mx = d.cx + moon.x * ax * d.R, my = d.cy + moon.y * d.R
        gc.fill(Path(ellipseIn: CGRect(x: mx - halo, y: my - halo, width: 2 * halo, height: 2 * halo)),
                with: .radialGradient(Gradient(colors: [OrbPalette.glow(pal).opacity(0.22 * moonGlow), .clear]),
                                      center: CGPoint(x: mx, y: my), startRadius: 0, endRadius: halo))
        paintDots(&gc, d.paths, pal, px: d.px)
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
        let faceShare = Int(Double(n) * 0.55)
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
        let headShare = Int(Double(n) * 0.38)
        for k in 0..<headShare {
            let (u, v) = evenPoint(k + 50_000)
            let zz = 1 - 2 * u, r = max(0, 1 - zz * zz).squareRoot(), a = 2 * Double.pi * v
            let nx = r * cos(a), ny = zz, nz = r * sin(a)
            let w = ny > 0 ? 1 - 0.2 * ny : 1
            let x = hw * nx * w, y = hy + hh * ny, z = dp * nz
            let isHair = y < hairline(x) || nz < -0.1 || (abs(nx) > 0.82 && y < -0.05)
            if !isHair && nz > 0.35 { continue }                                 // the front is the relief's
            // Strands flowing from a side part, so it reads as hair (not a cap).
            let strand = pow(0.5 + 0.5 * sin(34 * (0.8 * (x + 0.12) + 0.6 * y) + 3 * sin(5 * y)), 3)
            let lift = isHair ? 1.045 : 1
            out.append(P(part: isHair ? .hair : .head, x: x * lift, y: hy + (y - hy) * lift, z: z * lift, nx: nx, ny: ny, nz: nz,
                         tone: isHair ? 0.2 + 0.45 * strand : 0.72, dither: OrbPoints.hash(k, 15), phase: OrbPoints.hash(k, 13) * 6.3))
        }
        // The neck and the shoulders.
        for k in 0..<Int(Double(n) * 0.2) {
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

// MARK: - The ocean's points

/// The sea's fixed points, in the frame's half-side units: the water in rows of equal distance
/// that close up toward the horizon (each point knowing where it lies on the water through a camera
/// one unit above it), the moon, a few stars, and the rain's streaks.
enum OceanGeometry {
    enum Kind { case water, moon, star, rain }
    struct P {
        let kind: Kind; let sx: Double; let sy: Double; let wx: Double; let wd: Double
        let lum: Double; let dither: Double; let phase: Double
    }
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

    @MainActor private static var cache: [Int: [P]] = [:]

    @MainActor static func points(count n: Int) -> [P] {
        if let c = cache[n] { return c }
        var out: [P] = []
        out.reserveCapacity(n)
        var k = 0
        func h(_ salt: Double) -> Double { OrbPoints.hash(k, salt) }
        for _ in 0..<max(14, n / 22) {                              // the moon
            k += 1
            let a = 2 * Double.pi * h(1), r = moon.r * pow(h(2), 0.55)
            out.append(P(kind: .moon, sx: moon.x + r * cos(a), sy: moon.y + r * sin(a), wx: 0, wd: 0,
                         lum: 1.05 - 0.4 * r / moon.r, dither: h(14), phase: 2 * .pi * h(12)))
        }
        for _ in 0..<max(8, n / 45) {                               // stars
            k += 1
            let sx = 2 * h(1) - 1, sy = -1 + (horizon + 1 - 0.06) * h(2)
            if (sx - moon.x) * (sx - moon.x) + (sy - moon.y) * (sy - moon.y) < 0.05 { continue }
            out.append(P(kind: .star, sx: sx, sy: sy, wx: 0, wd: 0, lum: 0.2 + 0.4 * h(3), dither: h(14), phase: 2 * .pi * h(12)))
        }
        for _ in 0..<max(10, n / 30) {                              // rain streaks (shown while thinking)
            k += 1
            out.append(P(kind: .rain, sx: 2 * h(1) - 1.05, sy: h(2), wx: 0, wd: 0, lum: 0.5 + 0.5 * h(3), dither: h(14), phase: h(5)))
        }
        // The water: rows of equal distance, geometric (perspective), evenly spaced along each row;
        // each point's light weighted by its row's share of the screen, so the far rows, packed
        // close together, do not pile up into a bright band.
        let left = n - out.count
        let rows = max(10, Int(Double(left).squareRoot() * 0.8))
        let perRow = max(8, left / rows)
        // Rows placed on screen from the horizon down, closer together near the horizon (still
        // enough of them near the viewer for the near waves to read).
        func rowY(_ f: Double) -> Double { horizon + 0.01 + (1.02 - horizon - 0.01) * pow(f, 1.8) }
        for j in 0..<rows {
            let f = Double(rows - 1 - j) / Double(rows - 1)
            let y = rowY(f)
            let d = focal / (y - horizon)
            let weight = min(1, max(0.3, (y - rowY(max(0, f - 1 / Double(rows - 1)))) / 0.05))
            for i in 0..<perRow {
                k += 1
                let sx = -1.02 + (Double(i) + 0.5 + 0.6 * (h(1) - 0.5)) * 2.04 / Double(perRow)
                out.append(P(kind: .water, sx: sx, sy: y, wx: sx * d / focal, wd: d, lum: weight * (0.85 + 0.3 * h(3)),
                             dither: h(14), phase: 2 * .pi * h(12)))
            }
        }
        cache[n] = out
        return out
    }
}
