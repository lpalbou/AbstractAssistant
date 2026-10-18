import SwiftUI

/// Choose the orb's style: one page per style (Digital Crown to scroll), each a live orb answering a
/// speech rhythm, its name, one line and "Use this". In Settings → Orb style, and once at first
/// launch (`onboarding`), after sign-in.
struct OrbStylePicker: View {
    var onboarding = false
    @AppStorage(OrbDesign.storageKey) private var stored = OrbDesign.a.rawValue
    @AppStorage(OrbDesign.chosenKey) private var chosen = false
    @State private var page = OrbDesign.current
    @State private var voice = SyntheticVoice()
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        let v = voice
        let level: (@MainActor (Double) -> VoiceFeatures)? = { @MainActor _ in v.features() }
        TabView(selection: $page) {
            ForEach(OrbDesign.allCases) { d in
                GeometryReader { geo in
                    // The orb takes the free space, its name under it; the choice is at the bottom.
                    VStack(spacing: 2) {
                        Orb(mode: .listening, size: max(80, min(geo.size.width, geo.size.height - 66)), voice: level, design: d)
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                        Text(d.name).font(.rounded(.headline, weight: .bold)).foregroundStyle(Theme.text)
                            .accessibilityHint(d.summary)
                        Button(stored == d.rawValue && chosen ? "In use" : "Use this") { choose(d) }
                            .buttonStyle(FilledButtonStyle(fill: stored == d.rawValue && chosen ? Theme.neutralButton : Theme.indigoButton))
                            .disabled(stored == d.rawValue && chosen)
                            .padding(.horizontal, 6)
                    }
                    .frame(width: geo.size.width, height: geo.size.height)
                }
                // The button sits at the screen's bottom edge, as on the system's own pages.
                .ignoresSafeArea(edges: .bottom)
                .tag(d)
            }
        }
        .tabViewStyle(.verticalPage)
        .navigationTitle(onboarding ? "Choose your orb" : "Orb style")
        .navigationBarTitleDisplayMode(.inline)
        .containerBackground(Theme.ground, for: .navigation)
    }

    private func choose(_ d: OrbDesign) {
        stored = d.rawValue
        let first = !chosen
        chosen = true
        WKInterfaceDeviceHaptic.success()
        if !onboarding && !first { dismiss() }
    }
}

import WatchKit
private enum WKInterfaceDeviceHaptic { @MainActor static func success() { WKInterfaceDevice.current().play(.success) } }

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
