import SwiftUI

struct SettingsView: View {
    @EnvironmentObject private var model: AppModel
    @AppStorage("ask.speak") private var speakAnswers = true

    var body: some View {
        ScrollView {
            VStack(spacing: 6) {
                NavigationLink(value: Route.pairing) {
                    row("Gateway", "\(model.gatewayHost) · \(model.principal.map { "signed in as \($0.userId ?? "?")" } ?? (model.connecting ? "connecting…" : "not signed in"))")
                }
                .buttonStyle(.plain)
                row("Mode", model.client.isMock ? "mock data · pair a gateway to go live" : "live gateway")
                if let p = model.principal, !model.client.isMock {
                    row("Account", "\(p.userId ?? "?")" + (model.isAdmin ? " · admin token: prefer a dedicated user" : " · \((p.roles ?? []).joined(separator: ", "))"))
                }
                Button { Task { await model.refresh() } } label: {
                    Card { Text(model.freshness ?? "Refresh now").font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.cyan) }
                }
                .buttonStyle(.plain)
                Card {
                    Toggle(isOn: $speakAnswers) {
                        VStack(alignment: .leading, spacing: 1) {
                            Text("Speak answers").font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.text)
                            Text("the orb reads each answer aloud").font(.rounded(.caption2)).foregroundStyle(Theme.muted)
                        }
                    }
                    .tint(Theme.indigoButton)
                }
                row("Voice", "you speak to the orb · the gateway transcribes and speaks")
                row("Haptics", "new waits · allow · failures")
                row("Double Tap", "Allow once (non-destructive only)")
                Button {
                    model.signOut()
                } label: {
                    Card {
                        Text(model.client.isMock ? "Mock data (no gateway paired)" : "Sign out")
                            .font(.rounded(.footnote, weight: .semibold)).foregroundStyle(model.client.isMock ? Theme.muted : Theme.red)
                    }
                }
                .buttonStyle(.plain)
                .disabled(model.client.isMock)
                Footnote(text: "AbstractAssistant for Apple Watch · 0.1.0")
            }
        }
        .screen("Settings")
    }

    private func row(_ title: String, _ detail: String) -> some View {
        Card {
            HStack {
                VStack(alignment: .leading, spacing: 1) {
                    Text(title).font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.text)
                    Text(detail).font(.rounded(.caption2)).foregroundStyle(Theme.muted).lineLimit(2)
                }
                Spacer(minLength: 2)
                Image(systemName: "chevron.right").font(.caption2).foregroundStyle(Theme.muted)
            }
        }
    }
}
