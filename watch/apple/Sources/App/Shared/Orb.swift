import SwiftUI
import WatchKit

/// The orb's style: how its points answer a voice (Settings → Orb style, and asked once at first
/// launch). Stored by letter so a choice survives renames.
enum OrbDesign: String, CaseIterable, Identifiable {
    // The picker's order: the planets, the state shapes, the universe's, the avatars, the robots,
    // then the sea (letters stay stable).
    case a = "A", b = "B", c = "C", d = "D", e = "E", f = "F"
    case r = "R", s = "S", u = "U", v = "V", w = "W", x = "X"
    case t = "T", y = "Y", z = "Z"
    case g = "G", i = "I", contour = "CT", membrane = "MB", k = "K"
    case aurora = "AU", murmuration = "MU"
    case l = "L", m = "M", n = "N", o = "O", p = "P", q = "Q", h = "H"
    var id: String { rawValue }
    var name: String {
        switch self {
        case .a: "Halo"
        case .b: "Vortex"
        case .c: "Nebula"
        case .d: "Rings"
        case .e: "Liquid"
        case .f: "Galaxy"
        case .r: "Lotus"
        case .s: "Crystal"
        case .u: "Eclipse"
        case .v: "Synapse"
        case .w: "Drop"
        case .x: "Wave"
        case .t: "Well"
        case .y: "Black hole"
        case .z: "Accretion"
        case .g: "Face"
        case .i: "Imprint"
        case .contour: "Contour"
        case .membrane: "Membrane"
        case .aurora: "Aurora"
        case .murmuration: "Murmuration"
        case .k: "Eye"
        case .l: "Lens"
        case .m: "Dome"
        case .n: "Valet"
        case .o: "Retro"
        case .p: "Deco"
        case .q: "Rover"
        case .h: "Ocean"
        }
    }
    var summary: String {
        switch self {
        case .a: "rays of light around it, as long as your voice is loud"
        case .b: "the points swirl out into arms that reach with the voice"
        case .c: "a cloud that breathes outward with the voice"
        case .d: "a geodesic structure of rigid rings, each turning with its own part of the voice"
        case .e: "its surface ripples in waves with the voice"
        case .f: "a spiral galaxy that turns and spreads its arms with the voice"
        case .r: "a bud that listens, opens to think, branches out to work, blooms to speak"
        case .s: "a crystal that grows to think, gathers orbits to work, spreads wings to speak"
        case .u: "a golden eclipse: a corona to listen, orbits to think, a shutter to work, bars to speak"
        case .v: "a network of nodes: tangled to think, orbiting to work, a starburst to speak"
        case .w: "a drop of light: a vortex to think, fibres to work, a horn of particles to speak"
        case .x: "ribbons of light, each a harmonic of the voice; they wind into a swirl to work"
        case .t: "space bending into a well: ripples carry the voice, two masses circle it as it works"
        case .y: "a ring of light round a shadow: gas falls in to listen, a disk to think, jets to work"
        case .z: "a young star's disk of dust: it gathers into clumps to think and merges into planets to work"
        case .g: "a friendly face whose lips follow its voice; it cups its ear to listen"
        case .i: "a face seen only where it touches a pane of glass; it presses in as it speaks"
        case .contour: "a face raised in lines of light: its lips speak, the words leave them as waves along the lines"
        case .membrane: "a face pressing through a fabric of light: it presses closer with the voice and speaks through it"
        case .aurora: "the northern lights over a lake: they rise with the voice and gather into a corona to think"
        case .murmuration: "a flock of starlings at dusk: it swells to listen, spins to think, streams to work, draws the voice"
        case .k: "one friendly eye: its iris glows with its voice, it opens wide to listen"
        case .l: "a glowing red camera eye; its core flares as it speaks"
        case .m: "a dome-headed droid: it turns to face you, chatters with its lights, spins to think"
        case .n: "a gilded robot head: glowing eyes, it talks with its whole head"
        case .o: "a glass-domed robot of the fifties: its grille of lights follows its voice"
        case .p: "an art-deco machine woman with rings of light passing around her"
        case .q: "a little rover with binocular eyes that lean in to listen"
        case .h: "a sea at night whose waves rise with the voice; rain falls while it thinks"
        }
    }
    /// The family it belongs to (the picker's sections).
    var family: OrbFamily {
        switch self {
        case .a, .b, .c, .d, .e, .f: .orbs
        case .r, .s, .u, .v, .w, .x: .forms
        case .t, .y, .z: .cosmos
        case .h, .aurora, .murmuration: .nature
        case .g, .i, .contour, .membrane, .k: .faces
        case .l, .m, .n, .o, .p, .q: .machines
        }
    }
    /// What it is, in a few words (the picker's rows).
    var tagline: String {
        switch self {
        case .a: "Rays of voice"
        case .b: "Swirling arms"
        case .c: "A breathing cloud"
        case .d: "Geodesic rings"
        case .e: "A rippling surface"
        case .f: "A spiral galaxy"
        case .r: "A bud that blooms"
        case .s: "A crystal that spreads wings"
        case .u: "A golden eclipse"
        case .v: "A network of nodes"
        case .w: "A drop of light"
        case .x: "Ribbons of voice"
        case .t: "Space bending round a mass"
        case .y: "A ring round a shadow"
        case .z: "A solar system forming"
        case .h: "A sea at night"
        case .g: "A sculpted face"
        case .i: "A face pressed on glass"
        case .contour: "A face in lines of light"
        case .membrane: "A face through a fabric"
        case .aurora: "The northern lights"
        case .murmuration: "A flock of starlings"
        case .k: "One watchful eye"
        case .l: "A red camera eye"
        case .m: "A dome-headed droid"
        case .n: "A gilded humanoid"
        case .o: "A fifties robot"
        case .p: "An art-deco machine"
        case .q: "Binocular eyes on tracks"
        }
    }
    static let storageKey = "orb.design"
    /// Set once the person has chosen (the first-launch question is asked only once).
    static let chosenKey = "orb.chosen"
    static var current: OrbDesign { OrbDesign(rawValue: UserDefaults.standard.string(forKey: storageKey) ?? "") ?? .a }
}

/// The picker's sections: the styles grouped by what they are.
enum OrbFamily: String, CaseIterable, Identifiable {
    case orbs, forms, cosmos, nature, faces, machines
    var id: String { rawValue }
    var title: String {
        switch self {
        case .orbs: "Orbs"
        case .forms: "Forms"
        case .cosmos: "Cosmos"
        case .nature: "Nature"
        case .faces: "Faces"
        case .machines: "Machines"
        }
    }
    /// One line under the section's title.
    var note: String {
        switch self {
        case .orbs: "A sphere of light that answers the voice"
        case .forms: "A shape for each phase, morphing from one to the next"
        case .cosmos: "Gravity, a black hole, a solar system forming"
        case .nature: "The sea at night, the northern lights, a flock at dusk"
        case .faces: "A face that listens, thinks and talks"
        case .machines: "Classic talking machines"
        }
    }
    var designs: [OrbDesign] { OrbDesign.allCases.filter { $0.family == self } }
}

/// The silhouette the points draw (an entity's choice, `appearance.shape` on the gateway).
enum OrbShape: String, CaseIterable, Identifiable {
    case planet, kitty, face, wave
    var id: String { rawValue }
}

/// An orb's look: its colour (nil = the app's cyan and indigo) and shape.
struct OrbLook: Equatable {
    var color: Color? = nil
    var shape: OrbShape = .planet
    static let assistant = OrbLook()
}

/// The assistant's presence: a planet of pixel-size points turning slowly, like the Earth seen from
/// space (a tilted axis, about one turn every fifty seconds, a lit side and a night side, uneven
/// "continents" so the turn reads). When it hears you or speaks, about 85% of the points leave the
/// planet and answer the voice in real time (the design decides how); the other 15% keep turning in
/// place, so it stays the same orb. Thinking turns it faster and draws it in. Positions are functions
/// of time, so every motion is continuous; a missing loudness is silence, never a fake one.
struct Orb: View {
    enum Mode: Hashable { case idle, listening, thinking, speaking }

    var mode: Mode
    var size: CGFloat = 84
    var fps: Double = 30
    /// Listening and speaking: the voice now (loudness in its own range, and its spectrum), at time t.
    var voice: (@MainActor (Double) -> VoiceFeatures)? = nil
    /// Listening: 0…1 progress of the silence that sends.
    var countdown: (@MainActor () -> Double)? = nil
    var since: Date? = nil
    var look: OrbLook = .assistant
    /// nil = the chosen design (Settings → Orb design).
    var design: OrbDesign? = nil
    /// While it works: the pulses of its steps and the tools running now, at time t.
    var work: (@MainActor (Double) -> OrbWork)? = nil

    @State private var engine = OrbEngine()
    @AppStorage(OrbDesign.storageKey) private var storedDesign = OrbDesign.a.rawValue
    @Environment(\.isLuminanceReduced) private var dimmed
    @Environment(\.scenePhase) private var scenePhase
    @State private var onScreen = false

    var body: some View {
        // At rest it moves slowly (a turn in fifty seconds): a few frames a second are enough.
        let rate = mode == .idle ? max(10, fps * 0.4) : fps
        let chosen = design ?? OrbDesign(rawValue: storedDesign) ?? .a
        // Nobody looks: the screen dimmed (wrist down, always on), the app not active, or the orb
        // covered by another page. It holds its last frame and costs nothing.
        let still = dimmed || scenePhase != .active || !onScreen
        TimelineView(.animation(minimumInterval: 1 / rate, paused: still)) { ctx in
            let t = ctx.date.timeIntervalSinceReferenceDate
            let voiced = mode == .listening || mode == .speaking
            let doing = work?(t)
            let _ = engine.step(t: t, voice: voiced ? (voice?(t) ?? .silent) : .silent, engaged: voiced, thinking: mode == .thinking,
                                speaking: mode == .speaking, working: (doing?.satellites ?? 0) > 0)
            OrbCanvas(t: t, engine: engine, design: chosen, look: look, countdown: countdown?() ?? 0, work: work?(t) ?? .none)
                .frame(width: fillsWidth(chosen) ? WKInterfaceDevice.current().screenBounds.width : size, height: size)
        }
        .onAppear { onScreen = true }
        .onDisappear { onScreen = false }
        .accessibilityLabel(label)
    }

    /// The sea takes the screen's whole width where the orb is the page (the talk and Read pages),
    /// not on Home or in a small tile.
    private func fillsWidth(_ d: OrbDesign) -> Bool {
        [.h, .x, .t, .contour, .membrane, .aurora, .murmuration].contains(d) && look.shape == .planet && size > 0.6 * WKInterfaceDevice.current().screenBounds.width
    }

    private var label: String {
        switch mode {
        case .idle: "Ready"
        case .listening: "Listening"
        case .thinking: "Thinking"
        case .speaking: "Speaking"
        }
    }
}

/// The assistant's phase now, the one interface every orb style draws from: how much of each phase
/// is happening (they sum to 1) and the voice now. At rest; listening (you speak); thinking; working
/// (tools running, while it thinks); speaking.
struct OrbPhases {
    let rest: Double, listen: Double, think: Double, work: Double, speak: Double
    /// The voice: smoothed loudness, its value a moment ago, the pull it has on the shape, its bands.
    let loud: Double, level: Double, signal: Double, spectrum: VoiceFeatures
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
        loud = e.loud; level = e.history.value(secondsAgo: 0.05); signal = e.signal
        spectrum = VoiceFeatures(level: e.loud, bands: e.bands)
    }
}

/// Frame-to-frame state, all frame-rate independent: a smoothed loudness (rises in ~45 ms, falls
/// in ~200 ms) and its 1.2 s history, how engaged the cloud is (a smoothstep over 0.6 s in, 1 s
/// out), how much it is thinking, and an accumulated swirl phase (never `engagement × time`).
final class OrbEngine {
    let history = LoudnessHistory()
    private(set) var engagement: Double = 0
    private(set) var thinking: Double = 0
    private(set) var swirl: Double = 0
    private(set) var loud: Double = 0
    /// How strongly the voice pulls the cloud, 0…1: the engagement times a loudness that rises in
    /// ~60 ms and falls over ~250 ms (it follows syllables without flickering within one).
    private(set) var signal: Double = 0
    /// The voice's spectrum now (8 bands, 100 Hz–6 kHz), each smoothed over a syllable's attack.
    private(set) var bands = [Double](repeating: 0, count: VoiceFeatures.bandCount)
    /// 0 while it listens, 1 while it speaks (eased over 0.4 s): the face talks only with its own
    /// voice, the ocean's waves come toward you when it speaks and go away when you do.
    private(set) var talking: Double = 0
    private var kLin: Double = 0
    /// Rings: each ring's swing (its band's energy, rising in ~0.15 s, settling in ~0.8 s), the
    /// phase of that swing and its spin, advanced by its band (one ring per band, low to high).
    static let ringCount = 6
    private(set) var ringSwing = [Double](repeating: 0, count: OrbEngine.ringCount)
    private(set) var ringPhase = [Double](repeating: 0, count: OrbEngine.ringCount)
    private(set) var ringSpin = [Double](repeating: 0, count: OrbEngine.ringCount)
    /// The structure's turn: slow at rest, faster while it thinks (a gyroscope spinning up).
    private(set) var ringTurn: Double = 0
    /// 0…1: tools are running (eased over 0.5 s; a tool call between two thoughts does not flicker).
    private(set) var working: Double = 0
    private var wLin: Double = 0
    private var slow: Double = 0
    private var eLin: Double = 0
    private var tLin: Double = 0
    private var lastT: Double = 0

    @discardableResult
    func step(t: Double, voice: VoiceFeatures, engaged: Bool, thinking isThinking: Bool, speaking: Bool = false, working isWorking: Bool = false) -> Bool {
        let dt = lastT == 0 ? 0 : min(0.2, max(0, t - lastT))
        lastT = t
        let level = voice.level
        let tau = level > loud ? 0.025 : 0.09
        if dt > 0 { loud += (level - loud) * (1 - exp(-dt / tau)) } else { loud = level }
        for i in bands.indices {
            let v = i < voice.bands.count ? voice.bands[i] : 0
            bands[i] += (v - bands[i]) * (dt > 0 ? 1 - exp(-dt / (v > bands[i] ? 0.03 : 0.12)) : 1)
        }
        history.push(loud, at: t)
        eLin = min(1, max(0, eLin + (engaged ? dt / 0.6 : -dt / 1.0)))
        engagement = eLin * eLin * (3 - 2 * eLin)
        tLin = min(1, max(0, tLin + (isThinking ? dt / 0.5 : -dt / 0.8)))
        thinking = tLin * tLin * (3 - 2 * tLin)
        kLin = min(1, max(0, kLin + (speaking ? dt / 0.4 : -dt / 0.4)))
        talking = kLin * kLin * (3 - 2 * kLin)
        wLin = min(1, max(0, wLin + (isWorking ? dt / 0.5 : -dt / 0.9)))
        working = wLin * wLin * (3 - 2 * wLin)
        for i in 0..<Self.ringCount {
            // Each ring follows its own band (its harmonic), not the overall loudness.
            let b = engagement * min(1, 1.6 * bands[min(bands.count - 1, i + 1)] + 0.08 * loud)
            ringSwing[i] += (b - ringSwing[i]) * (dt > 0 ? 1 - exp(-dt / (b > ringSwing[i] ? 0.08 : 0.35)) : 1)
            ringPhase[i] += dt * (0.4 + 0.15 * Double(i) + 3.5 * ringSwing[i])
            ringSpin[i] += dt * (0.1 + 0.05 * Double(i) + 2.8 * ringSwing[i] + 1.5 * thinking) * (i % 2 == 0 ? 1 : -1)
        }
        ringTurn += dt * (0.12 + 1.1 * thinking)
        if dt > 0 { slow += (loud - slow) * (1 - exp(-dt / (loud > slow ? 0.06 : 0.25))) } else { slow = loud }
        signal = engagement * (0.12 + 0.88 * min(1, slow))
        swirl += dt * engagement * (0.2 + 1.4 * loud)
        return true
    }
}

/// The j-th point of an even two-dimensional sequence (Roberts' R2): spread without clumps or gaps,
/// so a sampled surface reads clean instead of grainy.
@inline(__always) func evenPoint(_ j: Int) -> (Double, Double) {
    let a = Double(j)
    let u = 0.5 + a * 0.7548776662466927, v = 0.5 + a * 0.5698402909980532
    return (u - u.rounded(.down), v - v.rounded(.down))
}

@inline(__always) func smoothstep(_ a: Double, _ b: Double, _ x: Double) -> Double {
    let u = min(1, max(0, (x - a) / (b - a)))
    return u * u * (3 - 2 * u)
}

/// One frame of the orb (also used to render the app icon).
struct OrbCanvas: View {
    let t: Double
    let engine: OrbEngine
    let design: OrbDesign
    let look: OrbLook
    var countdown: Double = 0
    /// Its work: each step sends a wave of light across it; each running tool circles it.
    var work: OrbWork = .none
    /// More points than the screen needs (the 1024 px icon).
    var pointScale: Double = 1

    private static let ringTilt: [Double] = [0.35, -0.55, 1.15]

    var body: some View {
        Canvas { gc, box in draw(&gc, box) }
            .drawingGroup()
    }

    private func draw(_ gc: inout GraphicsContext, _ box: CGSize) {
        gc.blendMode = .plusLighter
        // The Assistant's own scenes (an entity keeps its shape, with Nebula's answer to the voice).
        if look.shape == .planet {
            switch design {
            case .d: drawRings(&gc, box); return
            case .g: drawFace(&gc, box); return
            case .h: drawOcean(&gc, box); return
            case .i: drawImprint(&gc, box); return
            case .contour: drawContour(&gc, box); return
            case .membrane: drawMembrane(&gc, box); return
            case .aurora: drawAurora(&gc, box); return
            case .murmuration: drawMurmuration(&gc, box); return
            case .k: drawEye(&gc, box); return
            case .l: drawLens(&gc, box); return
            case .m: drawDome(&gc, box); return
            case .n: drawValet(&gc, box); return
            case .o: drawRetro(&gc, box); return
            case .p: drawDeco(&gc, box); return
            case .q: drawRover(&gc, box); return
            case .r: drawLotus(&gc, box); return
            case .s: drawCrystal(&gc, box); return
            case .u: drawEclipse(&gc, box); return
            case .v: drawSynapse(&gc, box); return
            case .w: drawDrop(&gc, box); return
            case .x: drawWave(&gc, box); return
            case .t: drawWell(&gc, box); return
            case .y: drawBlackHole(&gc, box); return
            case .z: drawAccretion(&gc, box); return
            default: break
            }
        }
        let design = [.a, .b, .c, .d, .e, .f].contains(design) ? design : OrbDesign.c
        let half = Double(min(box.width, box.height)) / 2
        let cx = Double(box.width) / 2, cy = Double(box.height) / 2
        let R = half * 0.46                    // the planet; at full voice the outer points reach the frame
        let e = engine.engagement, th = engine.thinking, hist = engine.history, now = engine.loud
        let spectrum = VoiceFeatures(level: now, bands: engine.bands)
        /// The voice's spectrum at 0…1 across its bands (low → high pitch).
        func band(_ x: Double) -> Double { spectrum.band(at: x) }
        func wrap(_ v: Double) -> Double { v - v.rounded(.down) }
        let tau = 2 * Double.pi
        // The turn: the planet spins on a 23° tilted axis (one turn ≈ 50 s, ~4× while thinking: an
        // accumulated phase, so the faster turn never jumps); a kitty or a face turns its head gently
        // instead; the wave is seen from a fixed pitch.
        let spinning = look.shape == .planet
        let yaw: Double = spinning ? 0.08 * t + 0.36 * engine.ringTurn : (look.shape == .wave ? 0.2 * sin(t * 0.08) : 0.45 * sin(t * 0.25))
        let tilt: Double = look.shape == .planet ? 0.41 : (look.shape == .wave ? 0.6 : 0.12)
        let cY = cos(yaw), sY = sin(yaw), cT = cos(tilt), sT = sin(tilt)
        let sun = (x: -0.55, y: -0.35, z: 0.76)
        let contract = 1 - 0.08 * th
        let phases = OrbPhases(engine)
        let swirlBase = engine.swirl
        let voiced = phases.listen + phases.speak
        /// How much of the voice shape is the listening one (light drawn in) vs. the speaking one (sent out).
        let inward = voiced > 1e-3 ? phases.listen / voiced : 0.5
        var d = hueDots(box)
        let n = Int(Double(min(2000, OrbPoints.count(half: half) * 11 / 10)) * pointScale)
        // Once a frame: Halo's corona, sampled round the rim. Seven broad streamers whose lengths
        // vary smoothly round it: with the voice (its spectrum, low pitches at the top, mirrored, and
        // its last second), turning slowly as a crown while it thinks, steady while it works. Each
        // phase has its own shape; the light blends them by the phases' weights.
        let coronaN = 72
        // Per phase: the corona's reach at each angle, and where its streamers are (0…1). A streamer
        // is broad at its foot and narrows outward (its profile sharpens with the distance out).
        var coronaV = [Double](repeating: 0, count: coronaN + 1), coronaVS = coronaV, coronaVB = coronaV
        var coronaT = coronaV, coronaTS = coronaV, coronaTB = coronaV, coronaW = coronaV, coronaWS = coronaV
        /// Where the streamers are round the rim at angle a (0…1): five broad ones and three finer,
        /// so they are uneven, as in a photograph, never a comb.
        func streamersAt(_ a: Double) -> Double {
            0.5 + 0.5 * (0.62 * cos(5 * a) + 0.38 * cos(8 * a + 1.7))
        }
        if design == .a {
            for j in 0...coronaN {
                let a = tau * Double(j) / Double(coronaN)
                let shapeVar = 1 + 0.3 * sin(3 * a + 1.3) + 0.15 * sin(5 * a - 0.4)
                if e > 0.001 {
                    let sv = streamersAt(a - 0.03 * t)
                    let pos = abs(atan2(cos(a), -sin(a))) / .pi
                    let v = min(1.2, 0.35 * hist.value(secondsAgo: pos * 0.8) + 0.85 * band(pos))
                    coronaV[j] = (0.35 + 1.1 * v) * shapeVar; coronaVS[j] = sv
                    coronaVB[j] = (0.35 + 0.55 * v) * (0.5 + 0.5 * sv)
                }
                if phases.think > 0.003 {
                    let st = streamersAt(a - 0.25 * t)
                    let lit = pow(0.5 + 0.5 * cos(a - 1.57 * t), 3)
                    coronaT[j] = 0.72 * shapeVar * (0.75 + 0.25 * lit); coronaTS[j] = st
                    coronaTB[j] = (0.25 + 0.8 * lit) * (0.5 + 0.5 * st)
                }
                if phases.work > 0.003 {
                    coronaW[j] = 0.85 * shapeVar; coronaWS[j] = streamersAt(a)
                }
            }
        }
        /// The corona's reach at a streamer's place `sv` and distance out `g` (0 its foot, 1 its tip).
        func reach(_ base: Double, _ sv: Double, _ g: Double) -> Double { base * (0.2 + 0.8 * pow(sv, 0.6 + 2.2 * g)) }
        /// A corona sample at angle a (linear between the samples).
        func corona(_ arr: [Double], _ a: Double) -> Double {
            var u = a / tau; u -= u.rounded(.down)
            let f = u * Double(coronaN), i = min(coronaN - 1, Int(f))
            return arr[i] + (arr[i + 1] - arr[i]) * (f - Double(i))
        }
        /// Halo thinking and working: the points in the crown's streamers (static, the crown turning
        /// through them) or flowing out along the steady ones.
        func haloMotif(_ p: OrbPoints.P, _ x: Double, _ y: Double, _ working: Bool) -> (x: Double, y: Double, b: Double, h: Double) {
            let a = atan2(y, x)
            if !working {
                let g = p.dither, r = 0.97 + reach(corona(coronaT, a), corona(coronaTS, a), g) * pow(g, 1.4)
                return (r * cos(a), r * sin(a), corona(coronaTB, a) * pow(1 - g, 2) + 0.25 * pow(1 - g, 6), 0.12 + 0.8 * g)
            }
            let g = wrap(p.dither + t * (0.55 + 0.3 * p.reach)), lw = reach(corona(coronaW, a), corona(coronaWS, a), g)
            let r = 0.97 + lw * pow(g, 1.3)
            return (r * cos(a), r * sin(a), (0.2 + 0.8 * lw) * pow(1 - g, 2) + 0.25 * pow(1 - g, 6), 0.12 + 0.8 * g)
        }
        let liquidAmp = (0..<Self.liquidWaves.count).map { k in
            0.12 * hist.value(secondsAgo: Double(k) * 0.12) + 0.2 * band(Double(k) / 2)
        }
        /// Liquid's surface lift at a point of the sphere (screen axes): smooth travelling waves.
        func liquidLift(_ x: Double, _ y: Double, _ z: Double) -> Double {
            var f = 0.0
            for (k, wv) in Self.liquidWaves.enumerated() {
                f += liquidAmp[k] * sin(wv.f * (wv.x * x + wv.y * y + wv.z * z) - wv.pace * t + wv.o)
            }
            return f
        }
        /// Vortex's arm at s (0 at the core, 1 at its tip): radius and angle.
        func vortexArm(_ s: Double, _ arm: Double) -> (r: Double, a: Double, lh: Double) {
            let lh = min(1.2, 0.5 * hist.value(secondsAgo: s * 0.8) + 0.6 * band(s))
            // Listening draws them in, wound tighter; speaking lets them out.
            let rr = 0.55 + (0.75 + 0.5 * lh) * s * (1 - 0.18 * inward)
            let wind = 3.0 - 1.4 * min(1, lh) + 0.9 * inward
            return (rr, arm * .pi + wind * log(rr / 0.55) + swirlBase * 0.6 + t * 0.12, lh)
        }
        /// Nebula's cloud, as in a photograph: a bright soft core, three lobes (indigo, violet, rose)
        /// breathing outward each with its own part of the voice, two wisps of filament, and a dark
        /// lane crossing it. Its parts, once a frame.
        let nebulaLh = min(1.2, 0.5 * hist.value(secondsAgo: 0.25) + 0.6 * band(0.5))
        let nebulaCore = 0.24 * (1 + 0.3 * nebulaLh)
        let lobes: [(x: Double, y: Double, a: Double, size: Double)] = (0..<3).map { j in
            let lh = min(1.2, 0.5 * hist.value(secondsAgo: 0.15 + 0.2 * Double(j)) + 0.6 * band(Double(j) / 2))
            let a = tau * Double(j) / 3 + 0.5 + 0.03 * t + 0.08 * sin(0.4 * t + Double(j))
            let c = 0.42 * (1 + 0.55 * lh)
            return (c * cos(a), c * sin(a), a, 0.3 * (1 + 0.4 * lh))
        }
        func filament(_ k: Int, _ u: Double) -> (x: Double, y: Double) {
            let r = 0.3 + 0.95 * u * (1 + 0.25 * nebulaLh), a = 2.3 + 3.1 * Double(k) + 0.03 * t + 1.9 * u
            return (r * cos(a), r * sin(a))
        }
        let lane = (x: 1.05 * cos(2.6 + 0.03 * t), y: 1.05 * sin(2.6 + 0.03 * t), r: 0.95)
        /// How much of a point's light the dark lane leaves (it crosses the cloud near its core).
        func laneLight(_ x: Double, _ y: Double) -> Double {
            let dl = abs(((x - lane.x) * (x - lane.x) + (y - lane.y) * (y - lane.y)).squareRoot() - lane.r)
            return 0.25 + 0.75 * smoothstep(0.03, 0.13, dl)
        }

        for p in OrbPoints.points(for: look.shape, count: n) {
            var px0 = p.x, py0 = p.y, pz0 = p.z
            if look.shape == .wave && !p.feature {
                // Rolling ocean: the surface height is computed now, so the waves travel.
                py0 = 0.18 * sin(4 * p.rad + 2 * p.ang - 1.3 * t) + 0.04 * sin(9 * p.rad - 2.1 * t + p.phase)
            }
            // 1. Turn (y axis), then tilt (x axis); y points down on screen.
            let bx = px0 * cY + pz0 * sY, bz = -px0 * sY + pz0 * cY
            px0 = bx; let y1 = py0 * cT - bz * sT; pz0 = py0 * sT + bz * cT; py0 = y1
            var x = px0 * contract, y = py0 * contract
            let z = pz0
            // 2b. Work: each step sends a ring of light out from the centre (a tool call a quick
            //     bright one, thinking a soft one, media a slow wide wave); a failed tool shivers.
            let workLight = workEffect(&x, &y, phase: p.phase)
            // 2. Light: the sun, the night side, depth (the far side fades), a rim.
            let lit = max(0.0, x * sun.x + y * sun.y + z * sun.z)
            var bright = (0.22 + 0.68 * lit) * p.lum
            bright *= 0.22 + 0.78 * smoothstep(-0.25, 0.15, z)
            if p.surface { bright += 0.3 * pow(1 - min(1, abs(z)), 3) * p.lum }
            bright += 1.6 * workLight * (0.45 + 0.55 * p.lum) * smoothstep(-0.4, 0.2, z)
            // Its hue: the lit side cyan, the terminator indigo, the night side violet, a touch of
            // rose low on the far limb.
            var hue = min(1, 0.08 + 0.5 * (1 - lit) + 0.28 * smoothstep(0.1, 1.1, 0.5 * x + 0.85 * y) + 0.12 * smoothstep(0, -0.8, z))
            // The anchored sixth stays home in every phase and glows a little brighter while the rest
            // are away, so the sphere always reads.
            if p.anchored { bright *= 1 + 0.4 * (1 - phases.rest) }
            // 3. The voice. Each style defines where a point goes at full strength (its target);
            //    how far it goes is its participation w, a smoothstep of its mobility m (its
            //    distance from the centre on screen, plus a little chance) against a threshold that
            //    moves inward as the signal s grows: a weak voice moves only the outer band (the
            //    buffer zone), a stronger one draws in more and more points. The anchored sixth
            //    follows at most 15%, so the shape breathes with the voice yet stays. Every target
            //    keeps the point's own direction where the style allows (rays, a cloud, a surface),
            //    so a point on its way is still on the shape's line, never in a fog.
            if e > 0.001 {
                let r0 = max(1e-3, (x * x + y * y).squareRoot())
                let a0 = atan2(y, x)
                let m = min(1, 0.72 * r0 + 0.28 * p.dither)
                let theta = 1 - 1.05 * engine.signal
                var w = e * smoothstep(theta - 0.16, theta + 0.16, m)
                if p.anchored { w *= 0.15 }
                if w > 0.002 {
                    var tx = x, ty = y, glow = 0.0, th2 = hue
                    let s = (p.reach - 0.45) / 0.55                        // 0…1, the point's own place along its line
                    switch design {
                    case .a:   // Halo: a soft corona round the planet, its streamers as long as the
                               // voice at their angle; light flows in along them as you speak, out
                               // as it speaks (two fixed paces, blended), densest at their feet.
                        let fIn = wrap(s - t * 0.4), fOut = wrap(s + t * 0.4)
                        let g = inward * fIn + (1 - inward) * fOut
                        let rr = 0.97 + reach(corona(coronaV, a0), corona(coronaVS, a0), g) * pow(g, 1.5)
                        tx = rr * cos(a0); ty = rr * sin(a0)
                        glow = corona(coronaVB, a0) * pow(1 - g, 2) + 0.25 * pow(1 - g, 6)
                        th2 = 0.12 + 0.8 * g
                    case .b:   // Vortex: two clean arms out of the planet's heart, winding up when the
                               // voice is quiet and unwinding, reaching out, as it grows louder.
                        let arm = vortexArm(s, Double(p.band % 2))
                        let width = (p.dither - 0.5) * 0.24 * (1 - 0.5 * s)
                        let na = arm.a + 0.5 * width / arm.r, r2 = arm.r + 0.5 * width
                        tx = cos(na) * r2; ty = sin(na) * r2
                        glow = (0.25 + 0.45 * arm.lh) * (1 - 0.5 * s) * (1 - 2.5 * abs(width))
                        th2 = 0.08 + 0.87 * s
                    case .c:   // Nebula: the points gather into the cloud's core, its lobes and wisps
                               // (gaussian about each), a few soft stars round it.
                        let g = (-2 * log(1 - 0.84 * p.dither)).squareRoot()   // a gaussian radius (its tail cut)
                        let gx = g * cos(p.phase), gy = g * sin(p.phase)
                        if p.band <= 1 || (p.band == 8 && p.reach < 0.7) {
                            tx = nebulaCore * gx; ty = nebulaCore * gy
                            glow = 0.15 + 0.7 * exp(-g * g / 2)
                            th2 = 0.03 + 0.12 * g
                        } else if p.band <= 6 {
                            let j = p.band % 3, lb = lobes[j]
                            let ca = cos(lb.a), sa = sin(lb.a)
                            let rad = gy * lb.size, tan = gx * lb.size * 1.5
                            tx = lb.x + rad * ca - tan * sa; ty = lb.y + rad * sa + tan * ca
                            glow = 0.04 + 0.48 * exp(-g * g / 2)
                            th2 = [0.36, 0.62, 0.86][j] + 0.1 * min(1, g / 2)
                        } else if p.band == 7 {
                            let fl = filament(p.phase > .pi ? 1 : 0, s)
                            tx = fl.x + 0.04 * gx; ty = fl.y + 0.04 * gy
                            glow = 0.32 * (1 - 0.6 * s)
                            th2 = 0.5 + 0.35 * s
                        } else {
                            // The stars: few, soft, twinkling.
                            let rr = 1.05 + 0.6 * p.dither
                            tx = rr * cos(a0); ty = rr * sin(a0)
                            glow = 0.12 + 0.2 * pow(max(0, sin(t * 1.7 + p.phase * 9)), 4)
                            th2 = p.dither
                        }
                        if p.band != 8 { glow *= laneLight(tx, ty) }
                    case .d:   // Rings: three tilted orbits that pulse
                        let ring = p.band % 3
                        let lh = 0.5 * hist.value(secondsAgo: Double(ring) * 0.3) + 0.6 * band(Double(ring) / 2)
                        let rr = 1.15 + 0.15 * Double(ring) + 0.4 * lh + 0.05 * (p.dither - 0.5)
                        let a = p.phase + swirlBase * (0.8 + 0.3 * Double(ring)) * (ring == 1 ? -1 : 1) + t * 0.15
                        tx = cos(a) * rr; ty = sin(a) * rr * cos(Self.ringTilt[ring]) * 0.35 + 0.02 * (p.reach - 0.5)
                        glow = 0.7 * lh
                    case .e:   // Liquid: the sphere's surface rolls in smooth waves (travelling waves
                               // of low order across the sphere, so its outline is always round), each
                               // one a band of the voice, rising with it.
                        let f = liquidLift(x, y, z)
                        let scale = 1.12 + 0.22 * now + f
                        tx = x * scale; ty = y * scale
                        glow = 0.3 + 2.0 * max(0, f) + 0.2 * now
                        th2 = min(1, max(0, hue + 2.2 * f))
                    case .g, .h, .i, .k, .l, .m, .n, .o, .p, .q, .r, .s, .u, .v, .w, .x, .t, .y, .z, .contour, .membrane, .aurora, .murmuration:   // scenes of their own
                        break
                    case .f:   // Galaxy: a continuous disc of stars, densest at the core, crowded along two arms
                        let lh = 0.5 * hist.value(secondsAgo: 0.1 + 0.4 * p.reach) + 0.6 * band(0.15)
                        var gr: Double, ga: Double
                        if p.band == 0 {
                            // The bulge: a dense, bright, slightly round core.
                            gr = 0.3 * pow(p.dither, 0.6); ga = p.phase
                            glow = 0.9
                        } else {
                            // The disc: exponential density (scale 0.55), out to ~1.7.
                            gr = min(1.7, -0.55 * log(1 - 0.96 * p.dither)) + 0.08
                            if p.band <= 2 {
                                ga = p.phase                                     // between the arms
                                glow = 0.15
                            } else {
                                // Around one of two log-spiral arms: densest at the arm, thinning
                                // away from it (a soft, wide spread, not a line).
                                let off = (s - 0.5) * (0.35 + 4.4 * (s - 0.5) * (s - 0.5))
                                ga = Double(p.band % 2) * .pi + 2.3 * log(gr + 0.08) + off
                                glow = 0.35 + 0.45 * lh * (1 - abs(off))
                            }
                            gr *= 1 + 0.3 * lh                                    // the arms reach with the voice
                        }
                        // The centre turns faster than the edge.
                        ga -= swirlBase * (0.8 / (0.3 + gr)) + t * 0.04
                        tx = cos(ga) * gr
                        ty = sin(ga) * gr * 0.6 + 0.03 * (p.dither - 0.5)      // seen at a slant, a thin disc
                        th2 = p.band == 0 ? 0 : 0.1 + 0.8 * smoothstep(0.15, 1.6, gr) + (p.band <= 2 ? 0.1 : 0)
                    }
                    if design == .b || design == .f || design == .d || design == .c {
                        // The structured shapes: a point is home or on its arm, briefly on its way.
                        w = w * w * (3 - 2 * w)
                    }
                    x += (tx - x) * w; y += (ty - y) * w
                    hue += (th2 - hue) * w
                    // A moving point lights up as it travels (wherever it came from, even the night
                    // side), so the shape the voice draws is clearly lit.
                    let voiceLight = ((design == .c || design == .a ? 0.12 : 0.3) + 0.75 * glow) * (0.75 + 0.25 * p.lum)
                    bright += (voiceLight - bright) * w
                }
            }
            // The countdown: the outer edge dims clockwise from the top, softly.
            if countdown > 0 {
                let r = (x * x + y * y).squareRoot()
                let a = (atan2(x, -y) + .pi) / (2 * .pi)
                bright *= 1 - 0.8 * (1 - smoothstep(countdown - 0.03, countdown + 0.03, a)) * smoothstep(0.8, 1.0, r)
            }
            // Thinking and working: each style's own motif (a crown of rays, a whirlpool, a forming
            // cloud, a lava lamp, a galaxy; and its work), the points blending into it.
            if (phases.think > 0.01 || phases.work > 0.01) && !p.anchored {
                for (weight, working) in [(phases.think, false), (phases.work, true)] where weight > 0.01 {
                    let m = design == .a ? haloMotif(p, x, y, working) : planetMotif(design, p, x, y, working: working)
                    let w = weight * weight * (3 - 2 * weight)
                    x += (m.x - x) * w; y += (m.y - y) * w
                    bright += (m.b - bright) * w
                    hue += (m.h - hue) * w
                }
            }
            // Never off screen: the voice's reach stays inside the orb's circle (beyond 70% of the
            // frame's half a point slows smoothly toward 84%; the resting planet is unchanged).
            let lim = half * 0.84 / R, knee = half * 0.7 / R
            let rr = (x * x + y * y).squareRoot()
            if rr > knee {
                let soft = knee + (lim - knee) * (1 - exp(-(rr - knee) / (lim - knee)))
                x *= soft / rr; y *= soft / rr
            }
            d.dot(x, y, bright, hue, p.dither, p.phase / tau)
        }
        // Light under the points, blurred with their bloom: the planet's body (a shaded disc of
        // light, its limb soft), and each style's own shapes of light. Their outlines are blends of
        // the phases' shapes, so they morph with the points.
        let hues = OrbPalette.hues(for: look.color)
        let away = 1 - phases.rest
        let busy = phases.think + phases.work
        func bodyRadius(_ a: Double) -> Double {
            switch design {
            case .e:
                let c = (cos(a), sin(a))
                return phases.rest * contract + voiced * (1.12 + 0.22 * now + liquidLift(c.0, c.1, 0))
                    + phases.think * (1 + 0.2 * sin(3 * a + t * 0.8) + 0.1 * sin(5 * a - t * 1.3)) * contract + phases.work * contract
            case .c:
                return phases.rest * contract + voiced * 0.75 * (1 + 0.3 * nebulaLh) + phases.think * 0.62 + phases.work * 0.42
            case .f: return phases.rest * contract + away * 0.42
            case .b: return phases.rest * contract + away * 0.7
            default: return contract
            }
        }
        let bodyLight: Double = {
            switch design {
            case .e: return 1 - 0.4 * phases.work
            case .c: return phases.rest + 0.3 * voiced + 0.95 * phases.think + 0.45 * phases.work
            case .f: return phases.rest + 0.75 * away
            case .a: return phases.rest + 0.7 * away
            default: return phases.rest + 0.45 * away
            }
        }()
        var body = Path()
        if design == .e || design == .c {
            for j in 0..<48 {
                let a = tau * Double(j) / 48, r = bodyRadius(a) * R
                let pt = CGPoint(x: cx + r * cos(a), y: cy + r * sin(a))
                if j == 0 { body.move(to: pt) } else { body.addLine(to: pt) }
            }
            body.closeSubpath()
        } else {
            let rb = bodyRadius(0) * R, flat = design == .f ? 1 - 0.4 * away : 1
            body.addEllipse(in: CGRect(x: cx - rb, y: cy - rb * flat, width: 2 * rb, height: 2 * rb * flat))
        }
        let bodyR = max(0.3, design == .c || design == .e ? bodyRadius(0.7) : bodyRadius(0)) * R
        let bodyShade = GraphicsContext.Shading.radialGradient(
            Gradient(stops: [.init(color: hues[0][4].opacity(0.36 * bodyLight), location: 0),
                             .init(color: hues[0][3].opacity(0.36 * bodyLight), location: 0.2),
                             .init(color: hues[1][2].opacity(0.3 * bodyLight), location: 0.5),
                             .init(color: hues[2][2].opacity(0.26 * bodyLight), location: 0.8),
                             .init(color: hues[3][1].opacity(0.22 * bodyLight), location: 1)]),
            center: CGPoint(x: cx - 0.3 * bodyR, y: cy - 0.25 * bodyR), startRadius: 0, endRadius: bodyR * 1.45)
        let outward = GraphicsContext.Shading.radialGradient(
            Gradient(stops: [.init(color: hues[0][3].opacity(0.85), location: 0), .init(color: hues[1][2].opacity(0.65), location: 0.3),
                             .init(color: hues[2][2].opacity(0.42), location: 0.6), .init(color: hues[3][2].opacity(0.16), location: 0.85),
                             .init(color: .clear, location: 1)]),
            center: CGPoint(x: cx, y: cy), startRadius: 0.8 * R, endRadius: 1.85 * R)
        /// A point of a light shape, kept inside the frame as the points are.
        func spot(_ r: Double, _ a: Double) -> CGPoint {
            let lim = half * 0.84 / R, knee = half * 0.7 / R
            let rr = r > knee ? knee + (lim - knee) * (1 - exp(-(r - knee) / (lim - knee))) : r
            return CGPoint(x: cx + rr * cos(a) * R, y: cy + rr * sin(a) * R)
        }
        // An entity seen as a wave (a surface, not a body) has no body of light or atmosphere.
        let solid = look.shape != .wave
        let light: (inout GraphicsContext) -> Void = { layer in
            if solid { layer.fill(body, with: bodyShade) }
            switch design {
            case .a where voiced + busy > 0.01:
                // The corona: three nested soft shells following the streamers' outline (a glow at
                // their feet, fading out along them), the phases' shapes blended.
                for (out, alpha) in [(0.25, 0.85), (0.55, 0.55), (1.0, 0.3)] {
                    var shell = Path()
                    for j in 0..<coronaN {
                        let a = tau * Double(j) / Double(coronaN)
                        let l = voiced * reach(coronaV[j], coronaVS[j], out) + phases.think * reach(coronaT[j], coronaTS[j], out)
                            + phases.work * reach(coronaW[j], coronaWS[j], out)
                        let pt = spot(0.95 + l * pow(out, 1.2), a)
                        if j == 0 { shell.move(to: pt) } else { shell.addLine(to: pt) }
                    }
                    shell.closeSubpath()
                    // A ring (the planet's disc left to its body's own light).
                    let inner = 0.92 * R
                    shell.addEllipse(in: CGRect(x: cx - inner, y: cy - inner, width: 2 * inner, height: 2 * inner))
                    var c = layer
                    c.opacity = alpha * min(1, voiced + busy)
                    c.fill(shell, with: outward, style: FillStyle(eoFill: true))
                }
            case .b where voiced + busy > 0.01:
                // The arms, drawn as soft strokes of light along their curves: the voice's two,
                // thinking's whirlpool of three, working's four.
                var c = layer
                for (weight, count) in [(voiced, 2), (phases.think, 3), (phases.work, 4)] where weight > 0.01 {
                    var arms = Path()
                    for arm in 0..<count {
                        for j in 2...28 {
                            let u = Double(j) / 28
                            let pt: CGPoint
                            switch count {
                            case 2:
                                let a = vortexArm(u, Double(arm)); pt = spot(a.r, a.a)
                            case 3:
                                let r = 1.45 * pow(u, 1.25) + 0.04
                                pt = spot(r, Double(arm) * tau / 3 + 2.8 * log(r + 0.1) + t * 0.9)
                            default:
                                let r = 0.08 + 1.42 * u
                                pt = spot(r, Double(arm) * tau / 4 - 2.1 * log(r + 0.1) - t * 2.2)
                            }
                            if j == 2 { arms.move(to: pt) } else { arms.addLine(to: pt) }
                        }
                    }
                    c.opacity = weight * (count == 2 ? 1 : 0.6)
                    c.stroke(arms, with: outward, style: StrokeStyle(lineWidth: 0.2 * R, lineCap: .round, lineJoin: .round))
                    c.stroke(arms, with: outward, style: StrokeStyle(lineWidth: 0.07 * R, lineCap: .round, lineJoin: .round))
                }
            case .c where voiced + phases.work > 0.01:
                // The cloud's light: the lobes as soft elongated glows, the wisps, the bright core,
                // and the dark lane carved out of their light. Working, its four clumps.
                if voiced > 0.01 {
                    for (j, lb) in lobes.enumerated() {
                        var c = layer
                        let c0 = spot((lb.x * lb.x + lb.y * lb.y).squareRoot(), atan2(lb.y, lb.x))
                        c.translateBy(x: c0.x, y: c0.y); c.rotate(by: .radians(lb.a)); c.scaleBy(x: 1, y: 1.5)
                        let rb = lb.size * 2.6 * R
                        c.fill(Path(ellipseIn: CGRect(x: -rb, y: -rb, width: 2 * rb, height: 2 * rb)),
                               with: .radialGradient(Gradient(stops: [.init(color: hues[j + 1][3].opacity(0.75 * voiced), location: 0),
                                                                      .init(color: hues[j + 1][2].opacity(0.36 * voiced), location: 0.4),
                                                                      .init(color: hues[j + 1][1].opacity(0.08 * voiced), location: 0.75),
                                                                      .init(color: .clear, location: 1)]),
                                                     center: .zero, startRadius: 0, endRadius: rb))
                    }
                    var wisps = Path()
                    for k in 0..<2 {
                        for j in 0...20 {
                            let fl = filament(k, Double(j) / 20), pt = spot((fl.x * fl.x + fl.y * fl.y).squareRoot(), atan2(fl.y, fl.x))
                            if j == 0 { wisps.move(to: pt) } else { wisps.addLine(to: pt) }
                        }
                    }
                    var c = layer
                    c.opacity = 0.3 * voiced
                    c.stroke(wisps, with: .color(hues[2][3]), style: StrokeStyle(lineWidth: 0.1 * R, lineCap: .round))
                    let rc = nebulaCore * 4 * R
                    layer.fill(Path(ellipseIn: CGRect(x: cx - rc, y: cy - rc, width: 2 * rc, height: 2 * rc)),
                               with: .radialGradient(Gradient(stops: [.init(color: hues[0][4].opacity(0.85 * voiced), location: 0),
                                                                      .init(color: hues[0][3].opacity(0.45 * voiced), location: 0.25),
                                                                      .init(color: hues[1][2].opacity(0.14 * voiced), location: 0.6),
                                                                      .init(color: .clear, location: 1)]),
                                                     center: CGPoint(x: cx, y: cy), startRadius: 0, endRadius: rc))
                    var carve = layer
                    carve.blendMode = .destinationOut
                    let lr = lane.r * R, lc = CGPoint(x: cx + lane.x * R, y: cy + lane.y * R)
                    carve.stroke(Path(ellipseIn: CGRect(x: lc.x - lr, y: lc.y - lr, width: 2 * lr, height: 2 * lr)),
                                 with: .color(.black.opacity(0.75 * voiced)), lineWidth: 0.2 * R)
                }
                for c in 0..<4 where phases.work > 0.01 {
                    let c0 = spot(0.78, Double(c) * tau / 4 + t * 0.75), rb = 0.3 * R
                    layer.fill(Path(ellipseIn: CGRect(x: c0.x - rb, y: c0.y - rb, width: 2 * rb, height: 2 * rb)),
                               with: .radialGradient(Gradient(colors: [hues[0][3].opacity(0.45 * phases.work), .clear]),
                                                     center: c0, startRadius: 0, endRadius: rb))
                }
            case .f where away > 0.01:
                // The disc's own faint glow, seen at a slant.
                var c = layer
                c.translateBy(x: cx, y: cy); c.scaleBy(x: 1, y: 0.6)
                let rd = 1.6 * R
                c.fill(Path(ellipseIn: CGRect(x: -rd, y: -rd, width: 2 * rd, height: 2 * rd)),
                       with: .radialGradient(Gradient(stops: [.init(color: hues[0][3].opacity(0.3 * away), location: 0),
                                                              .init(color: hues[1][2].opacity(0.14 * away), location: 0.3),
                                                              .init(color: hues[2][1].opacity(0.08 * away), location: 0.65),
                                                              .init(color: .clear, location: 1)]),
                                             center: .zero, startRadius: 0, endRadius: rd))
            default: break
            }
        }
        // A soft atmosphere round the limb (outside the bloom: it is soft already).
        let air = 0.5 + 0.5 * phases.rest, sky = R * 1.4
        if solid {
            gc.fill(Path(ellipseIn: CGRect(x: cx - sky, y: cy - sky, width: 2 * sky, height: 2 * sky)),
                    with: .radialGradient(Gradient(stops: [.init(color: .clear, location: 0.62),
                                                            .init(color: hues[2][2].opacity(0.14 * air), location: 0.72),
                                                            .init(color: hues[1][1].opacity(0.05 * air), location: 0.83),
                                                            .init(color: .clear, location: 1)]),
                                          center: CGPoint(x: cx, y: cy), startRadius: 0, endRadius: sky))
        }
        finishHue(&gc, d, hues: hues, light: light)
    }

    /// Liquid's travelling waves over the sphere: a direction, a frequency, a pace, an offset.
    private static let liquidWaves: [(x: Double, y: Double, z: Double, f: Double, pace: Double, o: Double)] = [
        (0.8, -0.6, 0.0, 2.4, 1.1, 0.0), (-0.3, -0.7, 0.65, 3.0, 1.4, 1.7), (0.45, 0.55, -0.7, 3.6, 1.8, 3.1),
    ]

    /// Where a planet's point goes while it thinks or works, and its light: each style's own motif.
    /// Units of the planet's radius, on screen.
    private func planetMotif(_ design: OrbDesign, _ p: OrbPoints.P, _ x: Double, _ y: Double, working: Bool) -> (x: Double, y: Double, b: Double, h: Double) {
        let m = motifPlace(design, p, x, y, working: working)
        // Its hue by how far out it is: cyan at the heart, indigo, violet, rose at the edge.
        let r = (m.x * m.x + m.y * m.y).squareRoot()
        return (m.x, m.y, m.b, 0.08 + 0.87 * smoothstep(0.35, 1.65, r))
    }

    private func motifPlace(_ design: OrbDesign, _ p: OrbPoints.P, _ x: Double, _ y: Double, working: Bool) -> (x: Double, y: Double, b: Double) {
        let f = p.dither, tau = 2 * Double.pi
        func wrap(_ v: Double, _ n: Double) -> Double { let m = v.truncatingRemainder(dividingBy: n); return m < 0 ? m + n : m }
        switch design {
        case .a:   // Halo
            let rays = 36.0, k = (p.phase / tau * rays).rounded(.down)
            if !working {
                // A crown of rays turning slowly, lit one after another round the circle.
                let a = tau * k / rays + 0.25 * t + (p.reach - 0.72) * 0.12 * (1.1 - f)
                let r = 1.02 + 0.42 * f
                let d = wrap(k - t * 9, rays)
                let lit = exp(-d / 5)
                return (r * cos(a), r * sin(a), 0.2 + 0.85 * lit * (1 - 0.6 * f))
            }
            // Light flowing outward along every ray, each ray at its own pace.
            let s = wrap(f + t * (0.9 + 0.8 * OrbPoints.hash(Int(k), 41)), 1)
            let a = tau * k / rays + (p.reach - 0.72) * 0.12 * (1.1 - s)
            let r = 0.98 + 0.62 * s
            return (r * cos(a), r * sin(a), 0.2 + 0.95 * (1 - s) * (1 - s))
        case .b:   // Vortex
            if !working {
                // A whirlpool: three arms winding inward, the points drawn down its throat.
                let s = wrap(f + t * 0.18, 1), r = 1.45 * pow(1 - s, 1.25) + 0.04
                let arm = Double(p.band % 3)
                let a = arm * tau / 3 + 2.8 * log(r + 0.1) + t * 0.9 + 0.3 * (p.reach - 0.72)
                return (r * cos(a), r * sin(a) * 0.92, 0.22 + 0.85 * (1 - r / 1.5))
            }
            // Four arms flinging light outward, fast.
            let s = wrap(f + t * 0.6, 1), r = 0.08 + 1.42 * s
            let arm = Double(p.band % 4)
            let a = arm * tau / 4 - 2.1 * log(r + 0.1) - t * 2.2 + 0.2 * (p.reach - 0.72)
            return (r * cos(a), r * sin(a), 0.25 + 0.9 * (1 - s))
        case .c:   // Nebula
            if !working {
                // The cloud condenses into a soft core, stars igniting in it here and there.
                let r0 = max(1e-3, (x * x + y * y).squareRoot())
                let rad = 0.62 * pow(f, 0.6) * (1 + 0.08 * sin(t * 0.9 + p.phase))
                let drift = 0.06 * sin(t * 0.7 + p.phase * 3)
                let star = p.band == 0 ? pow(max(0, sin(t * 2.6 + p.phase * 7)), 10) : 0
                return (x / r0 * rad + drift, y / r0 * rad - drift, 0.22 + 0.5 * (1 - f) + 1.1 * star)
            }
            // Four clumps (stars forming) orbiting the core, each trailing a tail.
            let c = Double(p.band % 4)
            let ca = c * tau / 4 + t * 0.75, cr = 0.78
            let tail = p.reach * 0.55
            let a = ca - tail, r = cr + 0.12 * cos(p.phase) * f
            let spread = 0.14 * pow(f, 0.7) * (1 - 0.5 * tail)
            return (r * cos(a) + spread * cos(p.phase), r * sin(a) + spread * sin(p.phase), 0.3 + 0.8 * (1 - tail) * (1 - f))
        case .e:   // Liquid
            let r0 = max(1e-3, (x * x + y * y).squareRoot()), a0 = atan2(y, x)
            if !working {
                // A slow lava lamp: three lobes rolling round the blob.
                let k = 1 + 0.2 * sin(3 * a0 + t * 0.8) + 0.1 * sin(5 * a0 - t * 1.3)
                return (x * k, y * k, 0.2 + 0.7 * smoothstep(0.6, 1.1, r0 * k))
            }
            // Droplets thrown off the surface, arcing and falling back; the rest rippling.
            if p.band < 1 {
                let s = wrap(f + t * 0.7, 1)
                let da = p.phase
                let lx = cos(da) * (1 + 0.5 * s), ly = sin(da) * (1 + 0.5 * s) + 0.7 * s * s - 0.35 * s
                return (lx, ly, 0.9 * (1 - s) + 0.15)
            }
            let ripple = 1 + 0.06 * sin(9 * r0 - t * 6)
            return (x * ripple, y * ripple, 0.25 + 0.5 * max(0, sin(9 * r0 - t * 6)))
        default:   // Galaxy
            let gr = min(1.55, -0.5 * log(1 - 0.96 * f)) + 0.06
            let arm = Double(p.band % 2)
            let off = (p.reach - 0.72) * 0.5
            if !working {
                // The disc forms, its arms tightening as it turns, the core pulsing.
                let ga = arm * .pi + 2.6 * log(gr + 0.08) + off - t * (0.7 / (0.3 + gr))
                let core = 0.6 + 0.4 * sin(t * 2.2)
                return (gr * cos(ga), gr * sin(ga) * 0.6, gr < 0.25 ? 0.6 + 0.6 * core : 0.25 + 0.5 * (1 - gr / 1.6))
            }
            // Light flowing out along the arms in pulses.
            let ga = arm * .pi + 2.3 * log(gr + 0.08) + off - t * 0.35
            let pulse = pow(max(0, sin((gr - t * 0.9) * 7)), 6)
            return (gr * cos(ga), gr * sin(ga) * 0.6, 0.22 + 0.4 * (1 - gr / 1.6) + 0.9 * pulse)
        }
    }

    /// Its work on one point: each step's ring of light pushes it out a little as it passes, a    /// Its work on one point: each step's ring of light pushes it out a little as it passes, a
    /// failed tool shivers it. Returns the light it gains.
    func workEffect(_ x: inout Double, _ y: inout Double, phase: Double) -> Double {
        guard !work.pulses.isEmpty else { return 0 }
        var light = 0.0
        let r0 = (x * x + y * y).squareRoot()
        var push = 0.0
        for pulse in work.pulses {
            let fade = max(0, 1 - pulse.age / 1.6)
            switch pulse.tone {
            case .failure:
                let k = pulse.strength * fade * fade
                x += 0.025 * k * sin(t * 55 + phase); y += 0.025 * k * cos(t * 47 + phase * 1.3)
                light += 0.2 * k
            default:
                let speed = pulse.tone == .media ? 0.85 : (pulse.tone == .thinking ? 1.0 : 1.5)
                let width = pulse.tone == .media ? 0.24 : (pulse.tone == .thinking ? 0.2 : 0.13)
                let ring = (r0 - pulse.age * speed) / width
                let k = exp(-ring * ring) * pulse.strength * fade
                push += k; light += 0.45 * k
            }
        }
        if r0 > 1e-3 { x += x / r0 * 0.05 * push; y += y / r0 * 0.05 * push }
        return light
    }

    /// The listening countdown on one point: the outer edge dims clockwise from the top.
    func countdownDim(_ x: Double, _ y: Double) -> Double {
        guard countdown > 0 else { return 1 }
        let r = (x * x + y * y).squareRoot()
        let a = (atan2(x, -y) + .pi) / (2 * .pi)
        return 1 - 0.8 * (1 - smoothstep(countdown - 0.03, countdown + 0.03, a)) * smoothstep(0.8, 1.0, r)
    }

    /// Under the points: each step's ring of light travelling out and fading: a fine line with a
    /// faint halo (a fog over the shape would blur it).
    func drawWaves(_ gc: inout GraphicsContext, cx: Double, cy: Double, R: Double, pal: [Color]) {
        let waves = work.pulses.filter { $0.tone != .failure }
        guard !waves.isEmpty else { return }
        let glow = OrbPalette.glow(pal)
        let line = max(0.6, R / 70)
        for w in waves {
            let speed = w.tone == .media ? 0.85 : (w.tone == .thinking ? 1.0 : 1.5)
            let r = w.age * speed * 0.92 * R
            guard r > 2 else { continue }
            let fade = max(0, 1 - w.age / 1.6)
            let alpha = min(0.7, 0.6 * w.strength * fade * (w.tone == .thinking ? 0.5 : 1))
            let ring = Path(ellipseIn: CGRect(x: cx - r, y: cy - r, width: 2 * r, height: 2 * r))
            gc.stroke(ring, with: .color(glow.opacity(alpha * 0.25)), lineWidth: line * 5)
            gc.stroke(ring, with: .color(glow.opacity(alpha)), lineWidth: line)
        }
    }

    /// The points, level by level, with a soft bloom under the brightest two levels (light that
    /// glows, not pixels that sit on the ground).
    func paintDots(_ gc: inout GraphicsContext, _ paths: [Path], _ pal: [Color], px: Double) {
        gc.drawLayer { layer in
            layer.addFilter(.blur(radius: px * 2.4))
            layer.fill(paths[3], with: .color(pal[3].opacity(0.55)))
            layer.fill(paths[4], with: .color(pal[4].opacity(0.75)))
        }
        for b in 0..<5 { gc.fill(paths[b], with: .color(pal[b])) }
    }

    /// The planets' and forms' canvas: points sorted by hue and brightness (`HueDots`).
    func hueDots(_ box: CGSize) -> HueDots {
        let half = Double(min(box.width, box.height)) / 2
        return HueDots(cx: Double(box.width) / 2, cy: Double(box.height) / 2, R: half * 0.46, px: max(0.55, half / 95))
    }

    /// The work's waves under the points, the points in their hues with their bloom, the running
    /// tools' satellites over them (an entity's colour wins over the hues).
    func finishHue(_ gc: inout GraphicsContext, _ d: HueDots, hues: [[Color]]? = nil, bloom: Double = 1,
                   light: ((inout GraphicsContext) -> Void)? = nil) {
        let hs = look.color == nil ? (hues ?? OrbPalette.hues(for: nil)) : OrbPalette.hues(for: look.color)
        let pal = OrbPalette.colors(for: look.color)
        drawWaves(&gc, cx: d.cx, cy: d.cy, R: d.R, pal: look.color == nil ? hs[0] : pal)
        paintHueDots(&gc, d.paths, hs, px: d.px, bloom: bloom, light: light)
        drawSatellites(&gc, cx: d.cx, cy: d.cy, R: d.R, px: d.px, pal: look.color == nil ? hs[0] : pal)
    }

    /// Points in four hues × five levels: one bloom under all of them (they fuse into a body of
    /// light), then the fine points themselves.
    /// `light`: soft shapes of light drawn in the same blurred layer, under the points.
    func paintHueDots(_ gc: inout GraphicsContext, _ paths: [Path], _ hues: [[Color]], px: Double, bloom: Double = 1,
                      light: ((inout GraphicsContext) -> Void)? = nil) {
        let glow = [0, 0.3, 0.45, 0.6, 0.8]
        gc.drawLayer { layer in
            layer.addFilter(.blur(radius: px * 2.6))
            light?(&layer)
            for i in 0..<20 where i % 5 > 0 && !paths[i].isEmpty {
                layer.fill(paths[i], with: .color(hues[i / 5][i % 5].opacity(min(1, glow[i % 5] * bloom))))
            }
        }
        for i in 0..<20 where !paths[i].isEmpty { gc.fill(paths[i], with: .color(hues[i / 5][i % 5])) }
    }

    /// Each tool running now circles the planet on a tilted orbit, a bright point with a fading
    /// trail, dimmed while it passes behind.
    func drawSatellites(_ gc: inout GraphicsContext, cx: Double, cy: Double, R: Double, px: Double, pal: [Color]) {
        let n = work.satellites
        guard n > 0 else { return }
        let tilt = -0.32, ca = cos(tilt), sa = sin(tilt)
        func spot(_ i: Int, _ k: Int) -> (x: Double, y: Double, behind: Bool) {
            let a = t * 1.7 + 2 * .pi * Double(i) / Double(n) - Double(k) * 0.06
            let ox = cos(a) * 1.3, oy = sin(a) * 1.3 * 0.34
            return (cx + (ox * ca - oy * sa) * R, cy + (ox * sa + oy * ca) * R, sin(a) < -0.15)
        }
        // A glow under each head (a radial gradient), then the trail and the head.
        let glow = OrbPalette.glow(pal)
        for i in 0..<n {
            let s = spot(i, 0), g = px * 6
            let fill = Gradient(colors: [glow.opacity(s.behind ? 0.25 : 0.75), .clear])
            gc.fill(Path(ellipseIn: CGRect(x: s.x - g, y: s.y - g, width: 2 * g, height: 2 * g)),
                    with: .radialGradient(fill, center: CGPoint(x: s.x, y: s.y), startRadius: 0, endRadius: g))
        }
        // The trails in five levels of light and the heads in two (one fill each, not one per bead).
        var trail = [Path](repeating: Path(), count: 5), heads = [Path](repeating: Path(), count: 2)
        for i in 0..<n {
            for k in stride(from: 16, through: 0, by: -1) {
                let s = spot(i, k)
                let size = px * (k == 0 ? 4.2 : 2.4 - 0.1 * Double(k))
                let bead = CGRect(x: s.x - size / 2, y: s.y - size / 2, width: size, height: size)
                if k == 0 {
                    heads[s.behind ? 1 : 0].addEllipse(in: bead)
                } else {
                    let alpha = 0.7 * (1 - Double(k) / 17) * (s.behind ? 0.3 : 1)
                    trail[min(4, Int(alpha / 0.7 * 5))].addEllipse(in: bead)
                }
            }
        }
        for b in 0..<5 where !trail[b].isEmpty { gc.fill(trail[b], with: .color(pal[3].opacity(0.7 * (Double(b) + 0.5) / 5))) }
        gc.fill(heads[0], with: .color(pal[4]))
        if !heads[1].isEmpty { gc.fill(heads[1], with: .color(pal[4].opacity(0.3))) }
    }
}

enum OrbPalette {
    /// The light of its work: the palette's bright colour at full strength (a dark entity colour
    /// would make a faded one vanish on the ground).
    static func glow(_ pal: [Color]) -> Color { pal[3].opacity(1 / 0.85) }
    /// Five brightness levels: deep, mid, the colour, light, near-white (default: indigo → cyan).
    static func colors(for tint: Color?) -> [Color] {
        guard let tint else {
            return [Color(hex: 0x4338ca).opacity(0.4), Color(hex: 0x6366f1).opacity(0.55), Color(hex: 0x38bdf8).opacity(0.7),
                    Color(hex: 0x22d3ee).opacity(0.85), Color(hex: 0xcffafe).opacity(0.95)]
        }
        return [tint.opacity(0.28), tint.opacity(0.45), tint.opacity(0.65), tint.opacity(0.85), Color.white.opacity(0.85)]
    }

    /// Four hues of five levels each, the gradient the planets and forms are painted with: cyan,
    /// indigo, violet, rose (Wave's ribbons). An entity's colour is its one hue.
    static func hues(for tint: Color?) -> [[Color]] {
        guard let tint else { return defaultHues }
        let c = colors(for: tint)
        return [c, c, c, c]
    }

    static func levels(_ a: UInt32, _ b: UInt32, _ c: UInt32, _ d: UInt32, _ e: UInt32) -> [Color] {
        [Color(hex: a).opacity(0.4), Color(hex: b).opacity(0.55), Color(hex: c).opacity(0.7), Color(hex: d).opacity(0.85), Color(hex: e).opacity(0.95)]
    }

    static let defaultHues: [[Color]] = [
        levels(0x0369a1, 0x0284c7, 0x38bdf8, 0x7dd3fc, 0xe0f2fe),     // cyan
        levels(0x3730a3, 0x4f46e5, 0x6366f1, 0x8b9cf8, 0xdbe1ff),     // indigo
        levels(0x6b21a8, 0x9333ea, 0xa855f7, 0xc084fc, 0xeedcff),     // violet
        levels(0x9d174d, 0xdb2777, 0xf472b6, 0xf9a8d4, 0xffdcea),     // rose
    ]
}

/// Points sorted by hue (four: `OrbPalette.hues`) and brightness (five levels), placed in units of
/// `R` from the centre; the hue and the level are dithered, so a gradient reads smooth.
struct HueDots {
    var paths = [Path](repeating: Path(), count: 20)
    let cx: Double, cy: Double, R: Double, px: Double
    /// The points' size against the canvas's pixel unit (finer than `DotCanvas`'s, the bloom fills between).
    var fine = 0.85

    mutating func dot(_ x: Double, _ y: Double, _ bright: Double, _ hue: Double, _ dither: Double, _ dither2: Double, size: Double = 1) {
        guard bright > 0.03 * dither else { return }
        let b = min(4, max(0, Int(bright * 5 + dither - 0.5)))
        let h = min(3, max(0, Int(hue * 3 + dither2)))
        let s = px * fine * size
        paths[h * 5 + b].addRect(CGRect(x: cx + x * R - s / 2, y: cy + y * R - s / 2, width: s, height: s))
    }
}

/// The fixed point sets, one per shape (seeded: the same orb every launch), in unit coordinates
/// (y down). Each point: position, brightness, whether it is part of the anchored 1/6 (or a feature
/// of the shape: ears, eyes, mouth, which are always anchored), and the per-point parameters.
enum OrbPoints {
    struct P {
        let x: Double; let y: Double; let z: Double; let lum: Double
        let anchored: Bool; let feature: Bool; let surface: Bool
        let reach: Double; let phase: Double; let band: Int; let dither: Double
        let rad: Double; let ang: Double
    }

    /// About one point per 5 pt² of the orb's square: ≈ 2,600 full screen, ≈ 300 on a 40 pt tile.
    /// 30% fewer than the first design (it lagged at times on a Series 11; older watches are slower).
    static func count(half: Double) -> Int { max(154, min(1820, Int(0.7 * 4 * half * half / 5))) }

    @MainActor private static var cache: [Int: [P]] = [:]

    @MainActor static func points(for shape: OrbShape, count n: Int) -> [P] {
        let key = (OrbShape.allCases.firstIndex(of: shape) ?? 0) * 1_000_000 + n
        if let c = cache[key] { return c }
        var out: [P] = []
        out.reserveCapacity(n)
        var k = 0
        while out.count < n && k < n * 4 {
            defer { k += 1 }
            // The planet's points spread evenly (no clumps or holes: a body, not grain).
            var (u, v) = shape == .planet ? evenPoint(k) : (hash(k, 1), hash(k, 2))
            if shape == .planet {
                // A little jitter, under a point's spacing, so no rows show.
                let j = 0.7 / Double(max(1, n)).squareRoot()
                u = min(1, max(0, u + (hash(k, 15) - 0.5) * j)); v += (hash(k, 16) - 0.5) * j
            }
            let w = hash(k, 3)
            var (x, y, z) = spherePoint(u, v)
            var r = hash(k, 4) < 0.88 ? 1.0 : 0.55 + 0.4 * w        // mostly surface, some depth
            if hash(k, 5) < 0.04 { r = 1.05 + 0.1 * w }               // a thin atmosphere
            // Two or three continents: low-frequency land, thresholded, so the turn reads.
            let land = 0.5 + 0.5 * sin(1.9 * x + 1.0 * sin(1.4 * z)) * cos(1.6 * y + 0.8 * x)
            var lum = smoothstep(0.45, 0.6, land) * 0.6 + 0.4
            var feature = false
            var rad = 0.0, ang = 0.0
            switch shape {
            case .planet: break
            case .kitty:
                if hash(k, 6) < 0.16 {   // two ears above the head
                    let side: Double = hash(k, 7) < 0.5 ? -1 : 1
                    let h = hash(k, 8), spread = (hash(k, 9) - 0.5) * (1 - h)
                    x = side * (0.5 + 0.35 * spread + 0.08 * h); y = -0.78 - 0.55 * h; z = 0.1 * (hash(k, 10) - 0.5)
                    r = 1; lum = 0.95; feature = true
                }
            case .face:
                if z < -0.2 { continue }                                   // the face is its front
                lum = 0.45
                let ex = abs(x) - 0.36, ey = y + 0.22
                if z > 0.35 && ex * ex + ey * ey < 0.022 { continue }      // the eyes stay empty
                if z > 0.35 && abs(ex * ex + ey * ey - 0.03) < 0.012 { lum = 1; feature = true }
                if abs(y - (0.32 - 0.5 * x * x)) < 0.045 && abs(x) < 0.45 && z > 0.4 { lum = 1; feature = true }
            case .wave:
                ang = 2 * Double.pi * u; rad = 0.25 + 0.95 * v.squareRoot()
                x = cos(ang) * rad; z = sin(ang) * rad; y = 0
                r = 1; lum = 0.55 + 0.45 * w
            }
            x *= r; y *= r; z *= r
            out.append(P(x: x, y: y, z: z, lum: lum, anchored: k % 6 == 0, feature: feature,
                         surface: abs(r - 1) < 0.01 && shape != .wave,
                         reach: 0.45 + 0.55 * hash(k, 11), phase: 2 * .pi * hash(k, 12), band: Int(hash(k, 13) * 9),
                         dither: hash(k, 14), rad: rad, ang: ang))
        }
        cache[key] = out
        return out
    }

    private static func spherePoint(_ u: Double, _ v: Double) -> (Double, Double, Double) {
        let zz = 1 - 2 * u, rr = (max(0, 1 - zz * zz)).squareRoot(), a = 2 * Double.pi * v
        return (rr * cos(a), zz, rr * sin(a))
    }

    static func hash(_ k: Int, _ salt: Double) -> Double {
        let v = sin(Double(k) * 12.9898 + salt * 78.233) * 43758.5453
        return v - v.rounded(.down)
    }
}

/// The last 1.2 s of the smoothed loudness at 30 samples a second, read with linear interpolation
/// (no steps), the newest sample being the current value.
final class LoudnessHistory {
    private var samples = [Double](repeating: 0, count: 40)
    private var head = 0
    private var lastT: Double = 0

    func push(_ v: Double, at t: Double) {
        if lastT == 0 { lastT = t }
        let steps = min(40, Int((t - lastT) * 30))
        if steps > 0 {
            for _ in 0..<steps { head = (head + 1) % samples.count; samples[head] = v }
            lastT += Double(steps) / 30
        } else {
            samples[head] = v
        }
    }

    func value(secondsAgo s: Double) -> Double {
        let f = max(0, min(Double(samples.count - 2), s * 30))
        let i = Int(f), frac = f - Double(i)
        let a = samples[(head - i + samples.count) % samples.count]
        let b = samples[(head - i - 1 + samples.count) % samples.count]
        return a + (b - a) * frac
    }
}

#if DEBUG
/// The app icon is the orb itself: `--render-icon` (simulator) renders the resting planet at
/// 1024 × 1024 on the app's ground into Documents/orb-icon.png.
enum OrbIcon {
    @MainActor static func render() {
        let engine = OrbEngine()
        let art = ZStack {
            Color(hex: 0x05060c)
            // Drawn larger than the icon so the planet fills ~3/4 of the watch's round mask.
            OrbCanvas(t: 812_345_678.0, engine: engine, design: .a, look: .assistant, pointScale: 3.2)
                .frame(width: 1400, height: 1400)
        }
        .frame(width: 1024, height: 1024)
        .clipped()
        let renderer = ImageRenderer(content: art)
        renderer.scale = 1
        guard let image = renderer.uiImage, let data = image.pngData(),
              let dir = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first else { return }
        try? data.write(to: dir.appending(path: "orb-icon.png"))
        print("icon rendered: \(dir.appending(path: "orb-icon.png").path)")
    }

    /// `--render-orb-work` (simulator): the orb at work, frame by frame, into Documents/orb-work-*.png:
    /// a tool pulse travelling out, a media wave, a failure, and three tools running (satellites).
    @MainActor static func renderWork() {
        guard let dir = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first else { return }
        let frames: [(String, OrbWork)] = [
            ("tool-0.15", OrbWork(pulses: [.init(age: 0.15, strength: 1, tone: .tool)], satellites: 1)),
            ("tool-0.45", OrbWork(pulses: [.init(age: 0.45, strength: 1, tone: .tool)], satellites: 1)),
            ("tool-0.8", OrbWork(pulses: [.init(age: 0.8, strength: 1, tone: .tool)], satellites: 1)),
            ("three", OrbWork(pulses: [.init(age: 0.55, strength: 1, tone: .tool), .init(age: 0.37, strength: 1, tone: .tool),
                                       .init(age: 0.19, strength: 1, tone: .tool)], satellites: 3)),
            ("media-0.7", OrbWork(pulses: [.init(age: 0.7, strength: 1.3, tone: .media)])),
            ("failure", OrbWork(pulses: [.init(age: 0.1, strength: 0.9, tone: .failure)])),
            ("rest", .none),
        ]
        for (name, work) in frames {
            let engine = OrbEngine()
            for k in 0..<30 { engine.step(t: 1000 + Double(k) / 30, voice: .silent, engaged: false, thinking: true) }
            let art = ZStack {
                Color(hex: 0x0a0a12)
                OrbCanvas(t: 1001, engine: engine, design: .a, look: .assistant, work: work).frame(width: 396, height: 396)
            }
            .frame(width: 396, height: 396)
            let renderer = ImageRenderer(content: art)
            renderer.scale = 2
            if let data = renderer.uiImage?.pngData() { try? data.write(to: dir.appending(path: "orb-work-\(name).png")) }
        }
        print("orb work rendered: \(dir.path)")
    }

    /// `--render-icons` (simulator): each round icon alone, 8× its size, into Documents/icon-<symbol>.png
    /// (to measure how far each glyph sits from the circle's centre).
    @MainActor static func renderIcons() {
        guard let dir = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first else { return }
        for symbol in GlassIcon.symbols {
            let art = Image(systemName: symbol).font(.system(size: 35 * 0.45, weight: .semibold)).foregroundStyle(.white)
                .frame(width: 35, height: 35).background(Color.black)
            let r = ImageRenderer(content: art); r.scale = 8
            if let data = r.uiImage?.pngData() { try? data.write(to: dir.appending(path: "icon-\(symbol).png")) }
        }
        print("icons rendered: \(dir.path)")
    }

    /// `--render-orb-scenes` (simulator): every style in each phase (rest, listening, thinking,
    /// working, speaking) into Documents/orb-<style>-<phase>.png; `--render-only Lotus,Face` renders
    /// those styles only.
    @MainActor static func renderScenes() {
        guard let dir = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first else { return }
        func voice(_ level: Double, _ low: Double, _ high: Double) -> VoiceFeatures {
            VoiceFeatures(level: level, bands: (0..<VoiceFeatures.bandCount).map { i in
                level * (low * exp(-pow(Double(i) - 1.5, 2) / 1.5) + high * exp(-pow(Double(i) - 5.5, 2) / 1.5)) })
        }
        let args = ProcessInfo.processInfo.arguments
        let only = args.firstIndex(of: "--render-only").flatMap { i in i + 1 < args.count ? Set(args[i + 1].split(separator: ",").map(String.init)) : nil }
        // (phase, voice, engaged, speaking, thinking, working, time)
        let phases: [(String, VoiceFeatures, Bool, Bool, Bool, Bool, Double)] = [
            ("rest", .silent, false, false, false, false, 1000.3),
            ("listen", voice(0.7, 0.8, 0.6), true, false, false, false, 1001.2),
            ("think", .silent, false, false, true, false, 1003.0),
            ("work", .silent, false, false, true, true, 1004.2),
            ("speak", voice(0.8, 1, 0.5), true, true, false, false, 1000.3),
        ]
        for design in OrbDesign.allCases where only?.contains(design.name) ?? true {
            for (name, v, engaged, speaking, thinking, working, t) in phases {
                let engine = OrbEngine()
                for k in 0..<45 {
                    engine.step(t: t - 1.5 + Double(k) / 30, voice: v, engaged: engaged, thinking: thinking, speaking: speaking, working: working)
                }
                // The sea as on the talk page: the screen's width over 90% of it (208 × 187 pt).
                let w: CGFloat = [.h, .x, .t, .contour, .membrane, .aurora, .murmuration].contains(design) ? 440 : 396
                let art = ZStack {
                    Color(hex: 0x000000)
                    OrbCanvas(t: t, engine: engine, design: design, look: .assistant,
                              work: working ? OrbWork(pulses: [.init(age: 0.4, strength: 1, tone: .tool)], satellites: 2) : .none)
                        .frame(width: w, height: 396)
                }
                .frame(width: w, height: 396)
                let renderer = ImageRenderer(content: art)
                renderer.scale = 2
                if let data = renderer.uiImage?.pngData() { try? data.write(to: dir.appending(path: "orb-\(design.name)-\(name).png")) }
            }
        }
        print("orb scenes rendered: \(dir.path)")
        if args.contains("--render-morph") { renderMorph(dir: dir, only: only, voice: voice) }
    }

    /// The transitions: rest → listen → think → work → speak → rest, two seconds each, the engine
    /// stepped at 30 fps throughout; frames 0.2, 0.5, 0.8 and 1.6 s after each change
    /// (orb-<name>-m<step>.png, 24 frames).
    @MainActor static func renderMorph(dir: URL, only: Set<String>?, voice: (Double, Double, Double) -> VoiceFeatures) {
        // (voice, engaged, speaking, thinking, working)
        let states: [(VoiceFeatures, Bool, Bool, Bool, Bool)] = [
            (.silent, false, false, false, false), (voice(0.7, 0.8, 0.6), true, false, false, false),
            (.silent, false, false, true, false), (.silent, false, false, true, true),
            (voice(0.8, 1, 0.5), true, true, false, false), (.silent, false, false, false, false),
        ]
        let marks = [0.2, 0.5, 0.8, 1.6]
        for design in OrbDesign.allCases where only?.contains(design.name) ?? true {
            let engine = OrbEngine()
            var frame = 0
            let t0 = 2000.0
            for (k, st) in states.enumerated() {
                for f in 0..<60 {
                    let t = t0 + Double(k) * 2 + Double(f) / 30
                    // A voice that moves, so the frames show it answering.
                    let v = st.1 ? VoiceFeatures(level: st.0.level * (0.6 + 0.4 * sin(t * 9)), bands: st.0.bands) : st.0
                    engine.step(t: t, voice: v, engaged: st.1, thinking: st.3, speaking: st.2, working: st.4)
                    let since = Double(f) / 30
                    guard k > 0, marks.contains(where: { abs($0 - since) < 0.017 }) else { continue }
                    let w: CGFloat = [.h, .x, .t, .contour, .membrane, .aurora, .murmuration].contains(design) ? 440 : 396
                    let art = ZStack {
                        Color(hex: 0x000000)
                        OrbCanvas(t: t, engine: engine, design: design, look: .assistant,
                                  work: st.4 ? OrbWork(pulses: [.init(age: since.truncatingRemainder(dividingBy: 1.4), strength: 1, tone: .tool)], satellites: 2) : .none)
                            .frame(width: w, height: 396)
                    }
                    .frame(width: w, height: 396)
                    let renderer = ImageRenderer(content: art)
                    renderer.scale = 1
                    if let data = renderer.uiImage?.pngData() { try? data.write(to: dir.appending(path: "orb-\(design.name)-m\(frame).png")) }
                    frame += 1
                }
            }
        }
        print("orb morphs rendered: \(dir.path)")
    }
}
#endif
