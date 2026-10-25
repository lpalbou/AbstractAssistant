import AbstractGatewayClient
import SwiftUI

/// Settings → Connection: the gateway this watch talks to and the account it is signed in as. Email
/// and tools belong to the account: another device signed in as someone else can show different ones.
struct ConnectionView: View {
    @EnvironmentObject private var model: AppModel
    @State private var email: EmailStatus?
    @State private var emailFailed = false
    @State private var confirmingSignOut = false

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
                // Shown with sample data too (screenshots, tests); it asks first.
                Button("Sign out") { confirmingSignOut = true }
                    .buttonStyle(FilledButtonStyle(fill: Theme.redButton))
                    .accessibilityIdentifier("connection.signout")
            }
            .padding(.horizontal, 4)
        }
        .screen("Connection")
        .signOutConfirmation(isPresented: $confirmingSignOut)
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

/// Sign out asks first, in the confirmation style of Archive: keep this sign-in on the watch for a
/// one-tap return from the sign-in page, or sign out and forget it.
struct SignOutConfirm: View {
    enum Choice { case keep, forget, cancel }
    let user: String?
    let gateway: String
    let done: (Choice) -> Void
    var body: some View {
        ScrollView {
            VStack(spacing: 8) {
                Image(systemName: "rectangle.portrait.and.arrow.right").font(.system(size: 22, weight: .semibold)).foregroundStyle(Theme.amber)
                Text("Sign out?").font(.rounded(.headline)).multilineTextAlignment(.center)
                Text([user, gateway].compactMap { $0 }.joined(separator: " · "))
                    .font(.rounded(.footnote)).foregroundStyle(Theme.text2).lineLimit(2).multilineTextAlignment(.center)
                if user != nil {
                    Text("Keep your sign-in to come back with one tap from the sign-in page.")
                        .font(.rounded(.caption2)).foregroundStyle(Theme.muted).multilineTextAlignment(.center)
                    Button("Keep my sign-in") { done(.keep) }
                        .buttonStyle(FilledButtonStyle(fill: Theme.indigoButton))
                        .accessibilityIdentifier("signout.keep")
                }
                Button("Sign out and forget") { done(.forget) }
                    .buttonStyle(FilledButtonStyle(fill: Theme.redButton))
                    .accessibilityIdentifier("signout.forget")
                Button("Cancel") { done(.cancel) }
                    .buttonStyle(FilledButtonStyle(fill: Theme.neutralButton))
            }
            .padding(.horizontal, 4)
        }
    }
}

extension View {
    /// The Sign out question (`SignOutConfirm`) as a sheet, answered through `AppModel.signOut(keep:)`.
    func signOutConfirmation(isPresented: Binding<Bool>) -> some View {
        modifier(SignOutConfirmation(isPresented: isPresented))
    }
}

private struct SignOutConfirmation: ViewModifier {
    @EnvironmentObject private var model: AppModel
    @Binding var isPresented: Bool
    func body(content: Content) -> some View {
        content.sheet(isPresented: $isPresented) {
            SignOutConfirm(user: SavedSignIn.load()?.user ?? model.principal?.userId, gateway: model.gatewayHost) { choice in
                isPresented = false
                switch choice {
                case .keep: model.signOut(keep: true)
                case .forget: model.signOut()
                case .cancel: break
                }
            }
        }
    }
}
