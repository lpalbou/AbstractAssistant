import SwiftUI

/// The orb's style, whether answers are spoken, About (this version), and Sign out: who is signed
/// in, and where, is one small line above Sign out at the bottom.
struct SettingsView: View {
    @EnvironmentObject private var model: AppModel
    @AppStorage("ask.speak") private var speakAnswers = true
    @AppStorage(AutomationNotices.key) private var automationNotices = true
    @AppStorage(OrbDesign.storageKey) private var orbDesign = OrbDesign.a.rawValue

    var body: some View {
        FitScroll {
            VStack(spacing: 6) {
                Button { model.push(.connection) } label: {
                    Card {
                        HStack {
                            Text("Connection").font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.text)
                            Spacer(minLength: 4)
                            Text(model.principal?.userId ?? model.gatewayHost).font(.rounded(.footnote)).foregroundStyle(Theme.muted)
                                .lineLimit(1).minimumScaleFactor(0.8)
                            Image(systemName: "chevron.right").font(.caption2).foregroundStyle(Theme.muted)
                        }
                    }
                }
                .buttonStyle(.tap)
                .accessibilityIdentifier("settings.connection")
                Button { model.push(.orbStyle) } label: {
                    Card {
                        HStack {
                            Text("Orb style").font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.text)
                            Spacer(minLength: 4)
                            Text((OrbDesign(rawValue: orbDesign) ?? .a).name).font(.rounded(.footnote)).foregroundStyle(Theme.muted)
                            Image(systemName: "chevron.right").font(.caption2).foregroundStyle(Theme.muted)
                        }
                    }
                }
                .buttonStyle(.tap)
                Card {
                    Toggle("Read aloud", isOn: $speakAnswers)
                        .font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.text).tint(Theme.indigoButton)
                }
                // A nudge when an automation finishes a run (a notification when the app is closed).
                Card {
                    Toggle("Automation results", isOn: $automationNotices)
                        .font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.text).tint(Theme.indigoButton)
                        .accessibilityIdentifier("settings.automationNotices")
                }
                Button { model.push(.voiceSettings) } label: {
                    Card {
                        HStack {
                            Text("Voice").font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.text)
                            Spacer(minLength: 4)
                            Text(VoicePrefs.voice?.voice ?? "Default").font(.rounded(.footnote)).foregroundStyle(Theme.muted).lineLimit(1)
                            Image(systemName: "chevron.right").font(.caption2).foregroundStyle(Theme.muted)
                        }
                    }
                }
                .buttonStyle(.tap)
                Button { model.push(.tools(.defaults)) } label: {
                    Card {
                        HStack {
                            Text("Tools").font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.text)
                            Spacer(minLength: 4)
                            Text("Defaults").font(.rounded(.footnote)).foregroundStyle(Theme.muted).lineLimit(1)
                            Image(systemName: "chevron.right").font(.caption2).foregroundStyle(Theme.muted)
                        }
                    }
                }
                .buttonStyle(.tap)
                .accessibilityIdentifier("settings.tools")
                Button { model.push(.about) } label: {
                    Card {
                        HStack {
                            Text("About").font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.text)
                            Spacer(minLength: 4)
                            Text(AppIdentity.version).font(.rounded(.footnote)).foregroundStyle(Theme.muted)
                            Image(systemName: "chevron.right").font(.caption2).foregroundStyle(Theme.muted)
                        }
                    }
                }
                .buttonStyle(.tap)
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
