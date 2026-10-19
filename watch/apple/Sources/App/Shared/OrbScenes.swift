import SwiftUI

// The two orb styles that are scenes of their own rather than a planet answering the voice:
// Face (a friendly portrait that talks) and Ocean (a sea at night whose waves rise with the
// voice). Both use the planet's units (1 = the planet's radius, y down), its palette, its five
// brightness levels, the light of its work and the listening countdown.

extension OrbCanvas {
    // MARK: Face

    /// A head-and-shoulders portrait in points, seen from the front: smiling eyes with a catchlight,
    /// a soft smile, rosy cheeks. It blinks, breathes and moves its head a little; its mouth opens
    /// with its own voice; it tilts its head and raises its brows to listen; thinking, it looks up
    /// and aside.
    func drawFace(_ gc: inout GraphicsContext, _ box: CGSize) {
        let half = Double(min(box.width, box.height)) / 2
        let cx = Double(box.width) / 2, cy = Double(box.height) / 2
        let R = half * 0.46
        let px = max(0.55, half / 95)
        let e = engine.engagement, th = engine.thinking, talk = engine.talking, loud = engine.loud
        let spectrum = VoiceFeatures(level: loud, bands: engine.bands)
        func band(_ x: Double) -> Double { spectrum.band(at: x) }
        let listen = e * (1 - talk)

        // The mouth: open with its own voice (vowels, low bands), wider on bright sounds.
        let open = min(1, e * talk * (1.5 * loud + 0.5 * band(0.15)))
        let wide = 1 + 0.14 * e * talk * (band(0.75) - band(0.2)) - 0.08 * open
        let smile = 1 + 0.35 * listen - 0.3 * th
        // The head: a slow drift, an attentive tilt while listening, looking up and aside to think,
        // a small nod with its speech.
        let yaw = 0.1 * sin(t * 0.29) + 0.05 * sin(t * 0.71) + 0.12 * th
        let pitch = 0.035 * sin(t * 0.23) - 0.07 * th + 0.04 * open * sin(t * 6.1)
        let roll = 0.035 * sin(t * 0.19) + 0.09 * listen - 0.05 * th
        // Eyes: a blink every few seconds (two in a row now and then), the gaze wandering a little.
        let cyc = t.truncatingRemainder(dividingBy: 5.3)
        let closed = max(exp(-pow((cyc - 0.15) / 0.06, 2)), Int(t / 5.3) % 3 == 0 ? exp(-pow((cyc - 0.42) / 0.06, 2)) : 0)
        let lid = 1 - 0.92 * closed
        let gazeX = (0.018 * sin(t * 0.37) + 0.03 * th) * (1 - listen)
        let gazeY = -0.03 * th
        let browUp = 0.03 * listen * (0.4 + 0.6 * min(1, engine.signal * 1.5)) + 0.012 * talk * loud
        let breathe = 0.012 * sin(t * 1.25)
        let cY = cos(yaw), sY = sin(yaw), cP = cos(pitch), sP = sin(pitch), cR = cos(roll), sR = sin(roll)
        let pivotY = FaceGeometry.neckY

        var paths = [Path](repeating: Path(), count: 5)
        for p in FaceGeometry.points(count: Int(Double(OrbPoints.count(half: half)) * pointScale)) {
            var x = p.x, y = p.y, z = p.z
            var lum = p.lum
            // 1. The expression, on the face's own coordinates.
            switch p.kind {
            case .lidUpper, .lidLower:
                let ey = FaceGeometry.eyeY
                y = ey + (y - ey) * lid
                if p.kind == .lidLower { y -= 0.012 * (smile - 1) }            // smiling eyes
            case .iris, .glint:
                x += gazeX; y = FaceGeometry.eyeY + (y - FaceGeometry.eyeY + gazeY) * lid
                if lid < 0.4 { continue }
            case .brow:
                y -= browUp + (p.side > 0 ? 0.02 * th : 0)
            case .lipUpper:
                x *= wide
                y -= 0.015 * open * (1 - p.u * p.u)
                y += (smile - 1) * 0.03 * (-p.u * p.u)
            case .lipLower:
                x *= wide
                y += 0.13 * open * (1 - p.u * p.u)
                y += (smile - 1) * 0.03 * (-p.u * p.u)
            case .skin:
                // The jaw follows the open mouth.
                let my = FaceGeometry.mouthY
                if y > my { y += 0.09 * open * smoothstep(my, my + 0.2, y) * max(0, 1 - abs(x) / 0.62) }
            case .cheek:
                lum *= 1 + 0.25 * (smile - 1)
            default: break
            }
            // 2. The head turns about the neck; the body only breathes.
            if p.kind.isHead {
                var ly = y - pivotY
                var lx = x * cY + z * sY
                var lz = -x * sY + z * cY
                let y2 = ly * cP - lz * sP; lz = ly * sP + lz * cP; ly = y2
                let rx = lx * cR - ly * sR, ry = lx * sR + ly * cR
                lx = rx; ly = ry
                x = lx; y = ly + pivotY + breathe * 0.5; z = lz
                // The far side of the head fades; a feature turned away is hidden.
                let facing = z / FaceGeometry.depth
                if p.kind.isFeature && facing < 0.15 { continue }
                lum *= 0.35 + 0.65 * smoothstep(-0.35, 0.85, facing)
            } else {
                y += breathe
            }
            // 3. Light: its own voice lights the mouth, any voice the face a little.
            if p.kind == .lipUpper || p.kind == .lipLower { lum += 0.5 * open }
            lum += 0.12 * engine.signal
            // Portrait framing: a little larger than the planet, the shoulders fading into the frame.
            var sx = x * 1.32, sy = y * 1.32 - 0.02
            let workLight = workEffect(&sx, &sy, phase: p.phase)
            var bright = lum + 1.4 * workLight * (0.45 + 0.55 * p.lum)
            bright *= countdownDim(sx / 1.6, sy / 1.6)
            let rr = (sx * sx + sy * sy).squareRoot()
            if rr > 1.98 { continue }
            bright *= 1 - smoothstep(1.6, 1.98, rr)
            guard bright > 0.03 * p.dither else { continue }
            let b = min(4, max(0, Int(bright * 5 + p.dither - 0.5)))
            paths[b].addRect(CGRect(x: cx + sx * R - px / 2, y: cy + sy * R - px / 2, width: px, height: px))
        }
        let pal = OrbPalette.colors(for: look.color)
        drawWaves(&gc, cx: cx, cy: cy, R: R, pal: pal)
        for b in 0..<5 { gc.fill(paths[b], with: .color(pal[b])) }
        drawSatellites(&gc, cx: cx, cy: cy, R: R, px: px, pal: pal)
    }

    // MARK: Ocean

    /// A round window onto a sea at night, a moon over the horizon and its glade on the water. At
    /// rest a slow swell; a voice raises the waves (low pitches the long swell, high pitches the
    /// chop), coming toward you while it speaks and going away while you do; thinking calms the sea
    /// and rain falls, each drop sending out rings.
    func drawOcean(_ gc: inout GraphicsContext, _ box: CGSize) {
        let half = Double(min(box.width, box.height)) / 2
        let cx = Double(box.width) / 2, cy = Double(box.height) / 2
        let R = half * 0.46
        let px = max(0.55, half / 95)
        let e = engine.engagement, th = engine.thinking, talk = engine.talking, hist = engine.history
        let spectrum = VoiceFeatures(level: engine.loud, bands: engine.bands)
        func band(_ x: Double) -> Double { spectrum.band(at: x) }
        let hz = OceanGeometry.horizon, F = OceanGeometry.focal
        let calm = 1 - 0.6 * th
        // The voice's bands now (the chop answers at once; the swell carries the last second).
        let low = 0.6 + 0.8 * band(0.15), mid = 0.6 + 0.8 * band(0.45)
        let chop = e * (0.5 * engine.loud + 0.8 * band(0.8))
        let moonGlow = 0.8 + 0.12 * sin(t * 0.5) + 0.35 * engine.signal + 0.2 * th * (0.5 + 0.5 * sin(t * 2))
        let moon = OceanGeometry.moon

        // Rain while it thinks: five drops in turn, each at its own place.
        struct Drop { let x: Double; let d: Double; let age: Double; let fade: Double }
        var drops: [Drop] = []
        if th > 0.01 {
            let period = 1.8
            for i in 0..<5 {
                let shifted = t + Double(i) * period / 5
                let n = Int(shifted / period)
                let age = shifted - Double(n) * period
                let seed = n * 7 + i * 13
                drops.append(Drop(x: (OrbPoints.hash(seed, 31) - 0.5) * 2.2, d: 1.3 + 3.2 * OrbPoints.hash(seed, 37),
                                  age: age, fade: th * pow(1 - age / period, 2)))
            }
        }

        var paths = [Path](repeating: Path(), count: 5)
        for p in OceanGeometry.points(count: Int(Double(OrbPoints.count(half: half)) * pointScale)) {
            var sx = p.sx, sy = p.sy
            var bright: Double
            if p.isMoon {
                bright = p.lum * moonGlow
            } else if p.isStar {
                bright = p.lum * (0.7 + 0.3 * sin(t * 1.3 + p.phase))
            } else {
                let X = p.wx, D = p.wd
                // Where the voice now is on the water: it enters far away and comes toward you while
                // it speaks, near you and goes away while you speak (the last 1.2 s along the way).
                let ago = talk * min(1.2, max(0, (8 - D) / 6)) + (1 - talk) * min(1.2, max(0, (D - 1) / 6))
                let v = e * hist.value(secondsAgo: ago)
                let a1 = (0.035 + 0.3 * v * low) * calm, a2 = (0.02 + 0.17 * v * mid) * calm, a3 = (0.008 + 0.07 * chop) * calm
                let dir = 2 * talk - 1                                          // +1: toward you
                var h = a1 * sin(2.0 * D * 1 + dir * 1.1 * t + p.phase * 0.2)
                h += a2 * sin(3.1 * (0.6 * X + 0.8 * D) + dir * 1.6 * t + 1.3)
                h += a3 * sin(5.3 * (-0.7 * X + 0.7 * D) + dir * 2.4 * t + p.phase)
                var ringLight = 0.0
                for drop in drops where drop.fade > 0.002 {
                    let dx = X - drop.x, dd = (D - drop.d) * 0.8
                    let dist = (dx * dx + dd * dd).squareRoot() - 0.75 * drop.age
                    let k = exp(-pow(dist / 0.2, 2)) * drop.fade
                    h += 0.2 * k * cos(dist * 14)
                    ringLight += k
                    if drop.age < 0.15 { ringLight += 3 * exp(-(dx * dx + dd * dd) / 0.004) * drop.fade }   // the splash
                }
                sy -= h * F / D
                // Light: fading into the haze at the horizon, crests brighter, foam on a loud one,
                // the moon's glade glittering under it.
                let haze = smoothstep(0.02, 0.5, p.sy - hz)
                let total = a1 + a2 + a3
                let crest = max(0, h / total)
                bright = p.lum * (0.22 + 0.55 * haze) + 0.35 * crest * haze
                if v > 0.35 && crest > 0.75 { bright += 0.5 * (crest - 0.75) * 4 * v }
                let gladeWidth = 0.1 + 0.32 * (p.sy - hz)
                let glade = exp(-pow((p.sx - moon.x) / gladeWidth, 2))
                let glint = max(0, sin(13 * X + 7 * D - 3 * t + p.phase))
                bright += 0.75 * glade * glint * glint * (0.6 + 0.4 * moonGlow)
                bright += 1.6 * ringLight
                // The round window's edge, soft.
                let r = (p.sx * p.sx + p.sy * p.sy).squareRoot()
                bright *= 1 - smoothstep(OceanGeometry.radius - 0.2, OceanGeometry.radius, r)
            }
            let workLight = workEffect(&sx, &sy, phase: p.phase)
            bright += 1.4 * workLight * (0.45 + 0.55 * p.lum)
            bright *= countdownDim(sx / 1.6, sy / 1.6)
            guard bright > 0.03 * p.dither else { continue }
            let b = min(4, max(0, Int(bright * 5 + p.dither - 0.5)))
            paths[b].addRect(CGRect(x: cx + sx * R - px / 2, y: cy + sy * R - px / 2, width: px, height: px))
        }
        let pal = OrbPalette.colors(for: look.color)
        drawWaves(&gc, cx: cx, cy: cy, R: R, pal: pal)
        for b in 0..<5 { gc.fill(paths[b], with: .color(pal[b])) }
        drawSatellites(&gc, cx: cx, cy: cy, R: R, px: px, pal: pal)
    }
}

// MARK: - The face's points

/// The portrait's fixed points (seeded: the same face every launch), in the planet's units, y down:
/// the head (skin, hair, ears), its features (lids, irises with a catchlight, brows, nose, lips,
/// cheeks), the neck and the shoulders.
enum FaceGeometry {
    enum Kind {
        case skin, hair, ear, lidUpper, lidLower, iris, glint, brow, nose, lipUpper, lipLower, cheek, neck, body
        var isHead: Bool { self != .neck && self != .body }
        var isFeature: Bool { ![.skin, .hair, .ear, .neck, .body].contains(self) }
    }
    struct P {
        let kind: Kind; let x: Double; let y: Double; let z: Double
        /// Place along its curve (-1…1, lips and lids), and which side (-1 left, +1 right).
        let u: Double; let side: Double
        let lum: Double; let dither: Double; let phase: Double
    }

    static let headY = -0.2, halfWidth = 0.6, halfHeight = 0.78, depth = 0.55
    static let eyeY = -0.2, eyeX = 0.24, mouthY = 0.33, neckY = 0.62

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
        func add(_ kind: Kind, _ x: Double, _ y: Double, u: Double = 0, side: Double = 0, lum: Double, z: Double? = nil) {
            let zz = z ?? (surfaceZ(x, y) ?? 0) + 0.01
            out.append(P(kind: kind, x: x, y: y, z: zz, u: u, side: side, lum: lum, dither: h(14), phase: 2 * .pi * h(12)))
        }
        // How many points each part gets (at least a few, so a small orb still reads as a face).
        func share(_ f: Double, min m: Int) -> Int { max(m, Int(Double(n) * f)) }

        // Features first: they must read even on a small orb.
        for side in [-1.0, 1.0] {
            let ex = side * eyeX
            for _ in 0..<share(0.026, min: 10) {                         // upper lid: a full arc
                k += 1; let u = 2 * h(1) - 1
                add(.lidUpper, ex + 0.11 * u, eyeY - 0.058 * cos(.pi * u / 2) + 0.006 * (h(2) - 0.5), u: u, side: side, lum: 1)
            }
            for _ in 0..<share(0.016, min: 6) {                          // lower lid: flatter
                k += 1; let u = 2 * h(1) - 1
                add(.lidLower, ex + 0.1 * u, eyeY + 0.03 * cos(.pi * u / 2) - 0.004, u: u, side: side, lum: 0.7)
            }
            for _ in 0..<share(0.022, min: 8) {                          // iris: a ring around the pupil
                k += 1; let a = 2 * Double.pi * h(1), r = 0.024 + 0.022 * h(2).squareRoot()
                add(.iris, ex + r * cos(a), eyeY - 0.004 + r * sin(a), side: side, lum: 0.85)
            }
            for _ in 0..<share(0.004, min: 2) {                          // the catchlight
                k += 1
                add(.glint, ex - 0.016 + 0.008 * (h(1) - 0.5), eyeY - 0.022 + 0.008 * (h(2) - 0.5), side: side, lum: 1.2)
            }
            for _ in 0..<share(0.018, min: 6) {                          // brow: a gentle raised arc
                k += 1; let u = 2 * h(1) - 1
                add(.brow, ex + 0.135 * u, eyeY - 0.17 - 0.035 * cos(.pi * u / 2) + 0.012 * u * side + 0.012 * (h(2) - 0.5),
                    u: u, side: side, lum: 0.8)
            }
            for _ in 0..<share(0.014, min: 5) {                          // a rosy cheek
                k += 1; let a = 2 * Double.pi * h(1), r = 0.1 * h(2)
                add(.cheek, side * 0.33 + r * cos(a), 0.12 + 0.7 * r * sin(a), side: side, lum: 0.55 - 1.5 * r)
            }
            for _ in 0..<share(0.012, min: 4) {                          // ear
                k += 1; let v = h(1)
                add(.ear, side * (halfWidth * 0.97 + 0.055 * sin(.pi * v)), -0.24 + 0.32 * v, side: side, lum: 0.5, z: 0.05)
            }
        }
        for _ in 0..<share(0.018, min: 6) {                              // nose: a light bridge and its tip
            k += 1
            if h(1) < 0.4 {
                let v = h(2); add(.nose, 0.012 + 0.02 * v, -0.1 + 0.2 * v, lum: 0.4)
            } else {
                let u = 2 * h(2) - 1; add(.nose, 0.065 * u, 0.115 + 0.028 * u * u, u: u, lum: 0.75)
            }
        }
        for _ in 0..<share(0.028, min: 10) {                             // upper lip: a smile
            k += 1; let u = 2 * h(1) - 1
            add(.lipUpper, 0.19 * u, mouthY - 0.045 * u * u + 0.004 * (h(2) - 0.5), u: u, lum: 1)
        }
        for _ in 0..<share(0.024, min: 8) {                              // lower lip
            k += 1; let u = 2 * h(1) - 1
            add(.lipLower, 0.17 * u, mouthY - 0.045 * u * u + 0.03 * (1 - u * u) + 0.004 * (h(2) - 0.5), u: u, lum: 0.85)
        }
        // The neck and the shoulders (a gentle slope, a collar), fading downward.
        for _ in 0..<share(0.04, min: 8) {
            k += 1; let v = h(1), u = 2 * h(2) - 1
            let edge = abs(u) > 0.85
            add(.neck, 0.2 * u, neckY - 0.08 + 0.32 * v, lum: edge ? 0.45 : 0.25, z: 0.3 * (1 - u * u))
        }
        let bodyCount = share(0.18, min: 20)
        for _ in 0..<bodyCount {
            k += 1
            let x = (2 * h(1) - 1) * 1.55
            let top = 0.9 + 0.32 * pow(max(0, abs(x) - 0.22) / 1.33, 1.5) + (abs(x) > 1.3 ? 0.9 * pow((abs(x) - 1.3) / 0.25, 2) : 0)
            if h(3) < 0.35 {
                add(.body, x, top + 0.01 * (h(2) - 0.5), lum: 0.6, z: 0)        // the shoulders' line
            } else if h(3) < 0.45 && abs(x) < 0.24 {
                add(.body, x, 0.9 + (0.24 - abs(x)) * 1.1, lum: 0.5, z: 0)       // a V collar
            } else {
                let d = pow(h(2), 1.3) * 0.95
                add(.body, x, top + d, lum: 0.32 * (1 - d), z: 0)
            }
        }
        // Hair and skin share what is left: hair above a side-swept hairline and down the sides.
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
                // Volume on top, strands sweeping to one side.
                let strand = 0.5 + 0.5 * sin(22 * x + 9 * y + 3 * sin(4 * x))
                let lift = 1.07 + 0.06 * max(0, -syu)
                out.append(P(kind: .hair, x: x * lift, y: headY + (y - headY) * lift, z: depth * szu * lift, u: 0, side: 0,
                             lum: 0.38 + 0.5 * strand * strand, dither: h(14), phase: 2 * .pi * h(12)))
            } else {
                if szu < 0 { continue }
                // Keep the eyes and the mouth clear, so they read.
                let inEye = pow((abs(x) - eyeX) / 0.13, 2) + pow((y - eyeY) / 0.075, 2) < 1
                let inMouth = pow(x / 0.21, 2) + pow((y - mouthY - 0.01) / 0.06, 2) < 1
                if inEye || inMouth { continue }
                if h(4) < 0.25 { continue }                               // skin a little sparser than hair
                out.append(P(kind: .skin, x: x, y: y, z: depth * szu, u: 0, side: 0, lum: 0.26 + 0.12 * h(3),
                             dither: h(14), phase: 2 * .pi * h(12)))
            }
        }
        cache[n] = out
        return out
    }
}

// MARK: - The ocean's points

/// The sea's fixed points: spread evenly on screen below the horizon inside a round window, each
/// knowing where it lies on the water (across `wx`, distance `wd`, through a camera one unit above
/// the sea); and the moon's.
enum OceanGeometry {
    struct P {
        let sx: Double; let sy: Double; let wx: Double; let wd: Double
        let lum: Double; let dither: Double; let phase: Double; let isMoon: Bool
        var isStar = false
    }
    static let radius = 1.6, horizon = -0.42, focal = 2.0
    static let moon = (x: 0.42, y: -0.92, r: 0.15)

    @MainActor private static var cache: [Int: [P]] = [:]

    @MainActor static func points(count n: Int) -> [P] {
        if let c = cache[n] { return c }
        var out: [P] = []
        out.reserveCapacity(n)
        let moonCount = max(12, n / 14)
        var k = 0
        func h(_ salt: Double) -> Double { OrbPoints.hash(k, salt) }
        while out.count < moonCount {                                   // the moon: a soft round disc
            k += 1
            let a = 2 * Double.pi * h(1), r = moon.r * pow(h(2), 0.6)
            out.append(P(sx: moon.x + r * cos(a), sy: moon.y + r * sin(a), wx: 0, wd: 0,
                         lum: 1.0 - 0.35 * r / moon.r, dither: h(14), phase: 2 * .pi * h(12), isMoon: true))
        }
        let starCount = max(6, n / 40)
        while out.count < moonCount + starCount {                      // a few faint stars in the sky
            k += 1
            let a = 2 * Double.pi * h(1), r = radius * h(2).squareRoot()
            let sx = r * cos(a), sy = r * sin(a)
            guard sy < horizon - 0.08, (sx - moon.x) * (sx - moon.x) + (sy - moon.y) * (sy - moon.y) > 0.09 else { continue }
            out.append(P(sx: sx, sy: sy, wx: 0, wd: 0, lum: 0.25 + 0.35 * h(3), dither: h(14), phase: 2 * .pi * h(12),
                         isMoon: false, isStar: true))
        }
        // The water in rows of equal distance, closer together toward the horizon (perspective), so
        // the waves read as rows rising and falling; points evenly spaced along each row.
        let rows = max(8, Int((Double(n - out.count)).squareRoot() * 0.75))
        let near = focal / (radius - horizon), far = 28.0
        var chords: [(d: Double, y: Double, w: Double)] = []
        for j in 0..<rows {
            let d = near * pow(far / near, Double(j) / Double(rows - 1))
            let y = horizon + focal / d
            chords.append((d, y, 2 * max(0, radius * radius - y * y).squareRoot()))
        }
        let total = chords.reduce(0) { $0 + $1.w }
        let spacing = total / Double(max(1, n - out.count))
        for (j, c) in chords.enumerated() {
            let m = Int(c.w / spacing)
            guard m > 0 else { continue }
            for i in 0..<m {
                k += 1
                let sx = -c.w / 2 + (Double(i) + 0.5 + 0.35 * (h(1) - 0.5)) * c.w / Double(m)
                out.append(P(sx: sx, sy: c.y, wx: sx * c.d / focal, wd: c.d, lum: 0.75 + 0.25 * h(3),
                             dither: h(14), phase: 2 * .pi * h(12) + Double(j), isMoon: false))
            }
        }
        cache[n] = out
        return out
    }
}
