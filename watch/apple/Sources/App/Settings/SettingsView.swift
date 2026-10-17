import SwiftUI

/// The orb's style, whether answers are spoken, About (this version), and Sign out: who is signed
/// in, and where, is one small line above Sign out at the bottom.
struct SettingsView: View {
    @EnvironmentObject private var model: AppModel
    @AppStorage("ask.speak") private var speakAnswers = true
    @AppStorage(OrbDesign.storageKey) private var orbDesign = OrbDesign.a.rawValue

    var body: some View {
        FitScroll {
            VStack(spacing: 6) {
                NavigationLink(value: Route.orbStyle) {
                    Card {
                        HStack {
                            Text("Orb style").font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.text)
                            Spacer(minLength: 4)
                            Text((OrbDesign(rawValue: orbDesign) ?? .a).name).font(.rounded(.footnote)).foregroundStyle(Theme.muted)
                            Image(systemName: "chevron.right").font(.caption2).foregroundStyle(Theme.muted)
                        }
                    }
                }
                .buttonStyle(.plain)
                Card {
                    Toggle("Speak answers", isOn: $speakAnswers)
                        .font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.text).tint(Theme.indigoButton)
                }
                NavigationLink(value: Route.about) {
                    Card {
                        HStack {
                            Text("About").font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.text)
                            Spacer(minLength: 4)
                            Text(AppIdentity.version).font(.rounded(.footnote)).foregroundStyle(Theme.muted)
                            Image(systemName: "chevron.right").font(.caption2).foregroundStyle(Theme.muted)
                        }
                    }
                }
                .buttonStyle(.plain)
                Spacer(minLength: 10)
                if !model.client.isMock {
                    Text([model.principal?.userId, model.gatewayHost].compactMap { $0 }.joined(separator: " · "))
                        .font(.rounded(.caption2)).foregroundStyle(Theme.muted).lineLimit(1).minimumScaleFactor(0.7)
                    Button("Sign out", role: .destructive) { model.signOut() }
                        .buttonStyle(FilledButtonStyle(fill: Theme.neutralButton, foreground: Theme.red))
                }
            }
        }
        .screen("Settings")
    }
}
