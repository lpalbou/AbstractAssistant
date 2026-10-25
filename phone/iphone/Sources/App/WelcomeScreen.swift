import SwiftUI
import AssistantKit
import AbstractGatewayClient

struct WelcomeScreen: View {
    var onConnect: (SavedConnection) -> Void
    var onDemo: () -> Void
    var notice: String?
    @State private var gateway = ""
    @State private var identifier = ""
    @State private var secret = ""
    @State private var codeSent = false
    @State private var busy = false
    @State private var message: String?
    @State private var error: String?
    @State private var attempt = 0
    @FocusState private var focused: Bool
    private var email: Bool { GatewaySignIn.isEmail(identifier) }
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 28) {
                    HStack { Image(systemName: "sparkle"); QuietLabel(text: "AbstractAssistant") }.foregroundStyle(PhoneTheme.lavender)
                    AssistantOrb(size: 132).frame(maxWidth: .infinity).padding(.top, 10)
                    VStack(alignment: .leading, spacing: 12) {
                        Text("A little space.\nFor big ideas.").font(.system(.largeTitle, design: .rounded, weight: .semibold)).tracking(-1)
                        Text("Your assistant, your conversations, your gateway. Pick up wherever you left off.").foregroundStyle(PhoneTheme.secondary).lineSpacing(4)
                    }
                    PhoneCard {
                        VStack(alignment: .leading, spacing: 18) {
                            QuietLabel(text: "Connect your gateway")
                            field("Gateway", text: $gateway, type: .URL).disabled(busy || codeSent)
                            field("User name or email", text: $identifier, type: .emailAddress).disabled(busy || codeSent)
                            if !email || codeSent {
                                VStack(alignment: .leading, spacing: 8) {
                                    Text(email ? "Email sign-in code" : "Account token").font(.footnote).foregroundStyle(PhoneTheme.secondary)
                                    SecureField(email ? "8-digit code" : "Paste your gateway token", text: $secret)
                                        .textContentType(email ? .oneTimeCode : .password)
                                        .keyboardType(email ? .numberPad : .default).textInputAutocapitalization(.never).autocorrectionDisabled()
                                        .padding(13).background(.black.opacity(0.18), in: RoundedRectangle(cornerRadius: 12))
                                }
                            }
                            if let message { Text(message).font(.footnote).foregroundStyle(PhoneTheme.mint) }
                            if let error = error ?? notice { ErrorBanner(message: error) }
                            Button(action: submit) {
                                HStack { Spacer(); if busy { ProgressView().tint(.white) }; Text(email && !codeSent ? "Email me a sign-in code" : "Connect").fontWeight(.semibold); Spacer(); Image(systemName: "arrow.right") }.padding(.vertical, 7)
                            }
                            .buttonStyle(.borderedProminent).controlSize(.large)
                            .disabled(busy || identifier.trimmingCharacters(in: .whitespaces).isEmpty || ((!email || codeSent) && secret.isEmpty))
                            if codeSent { Button("Use another account") { attempt += 1; codeSent = false; secret = ""; message = nil; error = nil }.font(.footnote).disabled(busy) }
                        }
                    }
                    VStack(spacing: 14) {
                        Label("Your sign-in stays sealed on this iPhone and your Apple Watch.", systemImage: "lock.shield").font(.footnote).foregroundStyle(PhoneTheme.secondary)
                        Button("Take a look around", action: onDemo).font(.subheadline.weight(.medium)).disabled(busy)
                    }.frame(maxWidth: .infinity)
                }.padding(24)
            }.background(PhoneTheme.ground).scrollDismissesKeyboard(.interactively)
        }
    }
    private func field(_ title: String, text: Binding<String>, type: UIKeyboardType) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title).font(.footnote).foregroundStyle(PhoneTheme.secondary)
            TextField(type == .URL ? "https://your-gateway.example" : title, text: text).keyboardType(type).textInputAutocapitalization(.never).autocorrectionDisabled()
                .padding(13).background(.black.opacity(0.18), in: RoundedRectangle(cornerRadius: 12))
        }
    }
    private func submit() {
        guard !busy else { return }
        let current = attempt
        busy = true; error = nil
        Task {
            defer { busy = false }
            do {
                let url = try SavedConnection.parseURL(gateway)
                let id = identifier.trimmingCharacters(in: .whitespacesAndNewlines)
                let transport = PhoneTransport.makeSession()
                if email && !codeSent {
                    let result = try await GatewaySignIn.requestCode(gateway: url, identifier: id, session: transport)
                    guard current == attempt else { return }
                    guard result.sent else { error = result.message ?? "A code couldn’t be sent. Try your user name and token."; return }
                    codeSent = true; message = result.message ?? "Check your email for the sign-in code."
                } else {
                    let credential: GatewayCredential, principal: Principal
                    if email {
                        let result = try await GatewaySignIn.redeem(gateway: url, identifier: id, code: secret.filter(\.isNumber), session: transport)
                        credential = result.0; principal = result.1
                    } else {
                        let token = secret.trimmingCharacters(in: .whitespacesAndNewlines)
                        principal = try await GatewaySignIn.verify(gateway: url, user: id, token: token, session: transport)
                        credential = .token(token)
                    }
                    guard current == attempt else { return }
                    secret = ""
                    onConnect(SavedConnection(gateway: url, user: principal.userId ?? id, tenant: principal.tenantId ?? "default", credential: credential))
                }
            } catch { self.error = error.localizedDescription }
        }
    }
}
