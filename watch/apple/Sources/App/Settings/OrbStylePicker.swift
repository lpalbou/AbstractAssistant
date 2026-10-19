import SwiftUI
import WatchKit

/// Choose the orb's style: the styles by family (Orbs, Forms, Faces, Machines), each row a live
/// small orb, its name and what it does; a row opens its preview. In Settings → Orb style, and once
/// at first launch (`onboarding`), after sign-in.
struct OrbStylePicker: View {
    var onboarding = false
    @AppStorage(OrbDesign.storageKey) private var stored = OrbDesign.a.rawValue
    @AppStorage(OrbDesign.chosenKey) private var chosen = false
    @State private var voice = SyntheticVoice()

    var body: some View {
        List {
            ForEach(OrbFamily.allCases) { family in
                Section {
                    ForEach(family.designs) { d in
                        NavigationLink(value: Route.orbStylePreview(d.rawValue)) { row(d) }
                            .accessibilityIdentifier("orb.\(d.name)")
                    }
                } header: {
                    Text(family.title).font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.text2).textCase(nil)
                        .accessibilityHint(family.note)
                        .accessibilityIdentifier("family.\(family.title)")
                }
            }
        }
        .navigationTitle(onboarding ? "Choose your orb" : "Orb style")
        .navigationBarTitleDisplayMode(.inline)
        .containerBackground(Theme.ground, for: .navigation)
    }

    private func row(_ d: OrbDesign) -> some View {
        HStack(spacing: 8) {
            // Speaking to a sample voice (at rest the planets all look alike), drawn larger than its
            // frame so the shape fills it.
            let v = voice
            Orb(mode: .speaking, size: 72, fps: 12, voice: { @MainActor _ in v.features() }, design: d)
                .frame(width: 44, height: 44)
                .clipShape(Circle())
                .allowsHitTesting(false)
            VStack(alignment: .leading, spacing: 0) {
                Text(d.name).font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.text)
                Text(d.tagline).font(.rounded(.caption2)).foregroundStyle(Theme.muted).lineLimit(1).minimumScaleFactor(0.8)
            }
            Spacer(minLength: 2)
            if stored == d.rawValue && chosen {
                Image(systemName: "checkmark").font(.caption2.weight(.semibold)).foregroundStyle(Theme.cyan).accessibilityLabel("In use")
            }
        }
        .padding(.vertical, 2)
    }
}

/// One style, live: it goes through the assistant's phases in turn (listening, thinking, working,
/// speaking), the phase named under it (tap a phase to hold it), and "Use this" at the bottom.
struct OrbStylePreview: View {
    let design: OrbDesign
    var onboarding = false
    @EnvironmentObject private var model: AppModel
    @AppStorage(OrbDesign.storageKey) private var stored = OrbDesign.a.rawValue
    @AppStorage(OrbDesign.chosenKey) private var chosen = false
    @State private var voice = SyntheticVoice()
    @State private var phase = 0
    @State private var held = false

    private static let phases: [(name: String, symbol: String)] = [
        ("Listening", "ear"), ("Thinking", "ellipsis"), ("Working", "gearshape.2"), ("Speaking", "waveform"),
    ]

    var body: some View {
        let v = voice
        let level: (@MainActor (Double) -> VoiceFeatures)? = { @MainActor _ in v.features() }
        let mode: Orb.Mode = phase == 0 ? .listening : (phase == 3 ? .speaking : .thinking)
        let work: (@MainActor (Double) -> OrbWork)? = phase == 2
            ? { @MainActor t in OrbWork(pulses: [.init(age: t.truncatingRemainder(dividingBy: 1.1), strength: 1, tone: .tool)], satellites: 2) }
            : nil
        GeometryReader { geo in
            VStack(spacing: 4) {
                Orb(mode: mode, size: max(80, min(geo.size.width, geo.size.height - 92)), voice: level, design: design, work: work)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .accessibilityIdentifier("orb.preview")
                HStack(spacing: 6) {
                    ForEach(Self.phases.indices, id: \.self) { i in
                        Button { phase = i; held = true } label: {
                            Image(systemName: Self.phases[i].symbol)
                                .font(.system(size: 11, weight: .semibold))
                                .frame(width: 28, height: 22)
                                .foregroundStyle(i == phase ? Theme.text : Theme.muted)
                                .background(i == phase ? Theme.neutralButton : .clear, in: Capsule())
                        }
                        .buttonStyle(.tap)
                        .accessibilityLabel(Self.phases[i].name)
                    }
                }
                Text(Self.phases[phase].name).font(.rounded(.caption2)).foregroundStyle(Theme.text2)
                    .accessibilityIdentifier("orb.phase")
                Button(stored == design.rawValue && chosen ? "In use" : "Use this") { choose() }
                    .buttonStyle(FilledButtonStyle(fill: stored == design.rawValue && chosen ? Theme.neutralButton : Theme.indigoButton))
                    .disabled(stored == design.rawValue && chosen)
                    .padding(.horizontal, 6)
            }
            .frame(width: geo.size.width, height: geo.size.height)
        }
        .ignoresSafeArea(edges: .bottom)
        .navigationTitle(design.name)
        .navigationBarTitleDisplayMode(.inline)
        .containerBackground(Theme.ground, for: .navigation)
        .task {
            // The phases in turn, 3.5 s each, until one is held.
            while !Task.isCancelled && !held {
                try? await Task.sleep(for: .seconds(3.5))
                if !held { phase = (phase + 1) % Self.phases.count }
            }
        }
    }

    private func choose() {
        stored = design.rawValue
        chosen = true
        WKInterfaceDevice.current().play(.success)
        // From Settings: back to Settings (past the list).
        if !onboarding, model.path.count >= 2, case .orbStylePreview = model.path.last { model.path.removeLast(2) }
    }
}

/// A speech-like loudness for previews: syllables at ~4.5 Hz inside phrases of 2–3 s, with pauses.
final class SyntheticVoice: @unchecked Sendable {
    private let start = Date()
    func level() -> Double {
        let t = Date().timeIntervalSince(start)
        let phrase = t.truncatingRemainder(dividingBy: 3.6)
        guard phrase < 2.6 else { return 0 }
        let envelope = min(1, phrase / 0.25) * min(1, (2.6 - phrase) / 0.35)
        let syllable = pow(max(0, sin(t * 2 * .pi * 4.4)), 0.7)
        let accent = 0.55 + 0.45 * sin(t * 1.7) * sin(t * 0.9 + 1)
        return max(0, min(1, envelope * syllable * accent))
    }

    /// The same speech with a spectrum: vowels move two formant peaks across the bands.
    func features() -> VoiceFeatures {
        let l = level()
        let t = Date().timeIntervalSince(start)
        let f1 = 1.5 + 1.2 * sin(t * 2.3), f2 = 4.5 + 1.5 * sin(t * 1.7 + 1)
        let bands = (0..<VoiceFeatures.bandCount).map { i -> Double in
            let x = Double(i)
            return l * min(1, exp(-pow(x - f1, 2) / 1.2) + 0.7 * exp(-pow(x - f2, 2) / 1.5))
        }
        return VoiceFeatures(level: l, bands: bands)
    }
}
