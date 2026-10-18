import AbstractGatewayClient
import SwiftUI

/// Settings → Connection: the gateway this watch talks to and the account it is signed in as. Email
/// and tools belong to the account: another device signed in as someone else can show different ones.
struct ConnectionView: View {
    @EnvironmentObject private var model: AppModel
    @State private var email: EmailStatus?
    @State private var emailFailed = false

    private var saved: SavedSignIn? { SavedSignIn.load() }

    var body: some View {
        FitScroll {
            VStack(alignment: .leading, spacing: 6) {
                section("Gateway") {
                    line(model.gatewayHost, strong: true)
                    line(status, color: model.unreachable ? Theme.red : model.connecting ? Theme.amber : Theme.green)
                }
                section("Account") {
                    line(model.principal?.userId ?? (model.connecting ? "Checking…" : "Unknown"), strong: true)
                        .accessibilityIdentifier("connection.user")
                    if model.isAdmin { line("Administrator") }
                    if let how = signInMethod { line(how) }
                }
                section("Email") {
                    if let email {
                        if email.configured {
                            line(email.address ?? "Mailbox connected", strong: true)
                            line(email.agentToolsOn ? "Email tools on" : "Email tools off for this account")
                        } else {
                            line("No mailbox connected", strong: true)
                            line("Connect one for this account in the gateway's Settings → Email.")
                        }
                    } else if emailFailed {
                        line("Couldn't read it")
                    } else {
                        ProgressView().frame(maxWidth: .infinity)
                    }
                }
                .accessibilityIdentifier("connection.email")
                section("Tools") {
                    if model.tools.isEmpty { line("Reading…") }
                    else {
                        line("\(model.tools.values.filter(\.offered).count) of \(model.tools.count) set up for this account", strong: true)
                    }
                }
                Text("Email and tools belong to the account: a device signed in as another account can show different ones.")
                    .font(.rounded(.caption2)).foregroundStyle(Theme.muted)
                if !model.client.isMock {
                    Button("Sign in as someone else") { model.signOut() }
                        .buttonStyle(FilledButtonStyle(fill: Theme.neutralButton))
                }
            }
            .padding(.horizontal, 4)
        }
        .screen("Connection")
        .task {
            await model.ensureTools(maxAge: 0)
            do { email = try await model.client.emailStatus() } catch { emailFailed = true }
        }
    }

    private var status: String {
        if model.unreachable { return "Not connected" }
        if model.connecting { return "Connecting…" }
        return model.freshness.map { "Connected · \($0)" } ?? "Connected"
    }

    private var signInMethod: String? {
        switch saved?.credential {
        case .token?: "Signed in with an access token"
        case .session?: "Signed in with an emailed code"
        case nil: nil
        }
    }

    private func section<Content: View>(_ title: String, @ViewBuilder _ content: () -> Content) -> some View {
        Card {
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.rounded(.caption2, weight: .semibold)).foregroundStyle(Theme.muted)
                content()
            }
        }
    }

    private func line(_ text: String, strong: Bool = false, color: Color? = nil) -> some View {
        Text(text).font(.rounded(strong ? .footnote : .caption2, weight: strong ? .semibold : .regular))
            .foregroundStyle(color ?? (strong ? Theme.text : Theme.text2)).fixedSize(horizontal: false, vertical: true)
    }
}
