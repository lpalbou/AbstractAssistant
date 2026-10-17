import AbstractGatewayClient
import SwiftUI
import WatchKit

/// The watch's sign-in, kept in UserDefaults (scaffold storage; a sealed store is a known gap):
/// the gateway, the account, and either its token or a 30-day session from an emailed code.
struct SavedSignIn {
    var gateway: URL
    var user: String?
    var credential: GatewayCredential

    static let defaultGateway = "https://gateway.abstractframework.ai"

    static func load(_ d: UserDefaults = .standard) -> SavedSignIn? {
        guard let url = d.string(forKey: "gateway.url").flatMap(URL.init(string:)) else { return nil }
        if let sid = d.string(forKey: "gateway.session"), let csrf = d.string(forKey: "gateway.csrf") {
            return SavedSignIn(gateway: url, user: d.string(forKey: "gateway.user"), credential: .session(id: sid, csrf: csrf))
        }
        if let token = d.string(forKey: "gateway.token") {
            return SavedSignIn(gateway: url, user: d.string(forKey: "gateway.user"), credential: .token(token))
        }
        return nil
    }

    func save(_ d: UserDefaults = .standard) {
        d.set(gateway.absoluteString, forKey: "gateway.url")
        d.set(user, forKey: "gateway.user")
        switch credential {
        case .token(let t):
            d.set(t, forKey: "gateway.token"); d.removeObject(forKey: "gateway.session"); d.removeObject(forKey: "gateway.csrf")
        case .session(let id, let csrf):
            d.set(id, forKey: "gateway.session"); d.set(csrf, forKey: "gateway.csrf"); d.removeObject(forKey: "gateway.token")
        }
    }

    /// Signing out forgets the credential; the gateway address stays as the next sign-in's default.
    static func clear(_ d: UserDefaults = .standard) {
        for k in ["gateway.token", "gateway.session", "gateway.csrf"] { d.removeObject(forKey: k) }
    }

    /// "gateway.example.org" → "https://gateway.example.org"; plain http only when typed.
    static func normalize(_ text: String) -> URL? {
        var s = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if s.isEmpty { return nil }
        if !s.contains("://") { s = "https://" + s }
        while s.hasSuffix("/") { s.removeLast() }
        guard let u = URL(string: s), u.host() != nil else { return nil }
        return u
    }
}

/// First launch, after Sign out, or when a session ends: who you are, then your token or an
/// emailed one-time code. A user name asks for its token; a registered email gets an 8-digit
/// code by email (the gateway sends it from the account's own mailbox and keeps it 10 minutes).
struct SignInView: View {
    enum Step: Equatable { case identify, token(user: String), code(email: String, sentTo: String) }

    @EnvironmentObject private var model: AppModel
    @State private var step: Step = .identify
    @State private var identifier = UserDefaults.standard.string(forKey: "gateway.user") ?? ""
    @State private var secret = ""
    @State private var gatewayText = UserDefaults.standard.string(forKey: "gateway.url") ?? SavedSignIn.defaultGateway
    @State private var editingGateway = false
    @State private var working = false
    @State private var error: String?

    var body: some View {
        FitScroll {
                VStack(spacing: 6) {
                    Spacer(minLength: 0)
                    LogoMark(size: 44)
                    Text("AbstractFramework")
                        .font(.rounded(.headline, weight: .bold))
                        .foregroundStyle(LinearGradient(colors: [Theme.cyan, Theme.indigo, Theme.green], startPoint: .leading, endPoint: .trailing))
                    if let notice = model.signInNotice, step == .identify {
                        Text(notice).font(.rounded(.caption2)).foregroundStyle(Theme.amber).multilineTextAlignment(.center)
                    }
                    Spacer(minLength: 4)
                    switch step {
                    case .identify: identify
                    case .token(let user): tokenStep(user)
                    case .code(_, let to): codeStep(to)
                    }
                    if let error { Text(error).font(.rounded(.caption2)).foregroundStyle(Theme.red).multilineTextAlignment(.center) }
                }
                // Fits one screen: the field sits at the bottom; longer (an error) scrolls.
                .padding(.horizontal, 2)
        }
        .background(
            RadialGradient(colors: [Theme.indigoButton.opacity(0.22), Theme.ground], center: .top, startRadius: 4, endRadius: 190)
                .ignoresSafeArea()
        )
        .task { await runTestHooks() }
    }

    // MARK: - Steps

    private var identify: some View {
        VStack(spacing: 5) {
            InputRow(placeholder: "Sign in with user or email", text: $identifier, working: working,
                     ready: !identifier.trimmingCharacters(in: .whitespaces).isEmpty && gatewayURL != nil) {
                Task { await proceed() }
            }
            gatewayRow
        }
    }

    private func tokenStep(_ user: String) -> some View {
        VStack(spacing: 5) {
            contextLine("Token for \(user)")
            InputRow(placeholder: "Token", text: $secret, secure: true, working: working,
                     ready: !secret.trimmingCharacters(in: .whitespaces).isEmpty) {
                Task { await signInWithToken(user) }
            }
        }
    }

    private func codeStep(_ sentTo: String) -> some View {
        VStack(spacing: 5) {
            contextLine("Code sent to \(sentTo)", extra: ("Resend", { Task { await proceed() } }))
            InputRow(placeholder: "8-digit code", text: $secret, working: working, ready: secret.filter(\.isNumber).count == 8) {
                Task { await signInWithCode() }
            }
        }
    }

    /// One small line of context above the field, with "change" (back to the first step) and an
    /// optional second link.
    private func contextLine(_ text: String, extra: (String, () -> Void)? = nil) -> some View {
        VStack(spacing: 2) {
            Text(text).foregroundStyle(Theme.text2).lineLimit(1).minimumScaleFactor(0.6)
            HStack(spacing: 14) {
                Button("Change") { step = .identify; secret = ""; error = nil }
                if let (label, action) = extra { Button(label, action: action).disabled(working) }
            }
            .foregroundStyle(Theme.cyan)
        }
        .font(.rounded(.caption2))
        .buttonStyle(.plain)
    }

    private var gatewayRow: some View {
        Group {
            if editingGateway {
                TextField("Server", text: $gatewayText)
                    .textFieldStyle(.plain).multilineTextAlignment(.center)
                    .textContentType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
                    .font(.rounded(.caption2)).foregroundStyle(Theme.muted)
                    .onSubmit { editingGateway = false }
            } else {
                Button { editingGateway = true } label: {
                    Text(gatewayURL?.host() ?? gatewayText).lineLimit(1).minimumScaleFactor(0.7)
                        .font(.rounded(.caption2)).foregroundStyle(Theme.muted.opacity(0.8))
                }
                .buttonStyle(.plain)
                .accessibilityHint("Change the server")
            }
        }
        .padding(.horizontal, 18)
    }

    private var gatewayURL: URL? { SavedSignIn.normalize(gatewayText) }

    // MARK: - Actions

    private func proceed() async {
        let id = identifier.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let gw = gatewayURL, !id.isEmpty else { return }
        error = nil; secret = ""
        guard GatewaySignIn.isEmail(id) else { step = .token(user: id); return }
        working = true
        defer { working = false }
        do {
            let answer = try await GatewaySignIn.requestCode(gateway: gw, identifier: id)
            if answer.sent {
                step = .code(email: id, sentTo: answer.to ?? "your email")
                WKInterfaceDevice.current().play(.success)
            } else {
                step = .identify
                error = "No code could be sent. Use your user name."
            }
        } catch {
            self.error = AppModel.say(error)
        }
    }

    private func signInWithToken(_ user: String) async {
        guard let gw = gatewayURL else { return }
        let token = secret.trimmingCharacters(in: .whitespacesAndNewlines)
        working = true; error = nil
        defer { working = false }
        do {
            let me = try await GatewaySignIn.verify(gateway: gw, user: user, token: token)
            finish(SavedSignIn(gateway: gw, user: me.userId ?? user, credential: .token(token)))
        } catch {
            self.error = AppModel.say(error)
            WKInterfaceDevice.current().play(.failure)
        }
    }

    private func signInWithCode() async {
        guard let gw = gatewayURL, case .code(let email, _) = step else { return }
        working = true; error = nil
        defer { working = false }
        do {
            let (cred, me) = try await GatewaySignIn.redeem(gateway: gw, identifier: email, code: secret.filter(\.isNumber))
            finish(SavedSignIn(gateway: gw, user: me.userId ?? email, credential: cred))
        } catch {
            self.error = AppModel.say(error)
            WKInterfaceDevice.current().play(.failure)
        }
    }

    private func finish(_ s: SavedSignIn) {
        WKInterfaceDevice.current().play(.success)
        model.connect(s)
    }

    /// Simulator/device checks without typing: `--test-identify <user or email>` then `--test-secret <token or code>`.
    private func runTestHooks() async {
        guard let id = model.testIdentify else { return }
        model.testIdentify = nil
        identifier = id
        await proceed()
        if let s = model.testSecret {
            model.testSecret = nil
            secret = s
            switch step {
            case .token(let user): await signInWithToken(user)
            case .code: await signInWithCode()
            case .identify: break
            }
        }
    }
}

/// The AbstractFramework mark: the six cubes, breathing slowly in their own glow.
struct LogoMark: View {
    var size: CGFloat = 70
    var body: some View {
        TimelineView(.animation(minimumInterval: 1 / 20)) { ctx in
            let t = ctx.date.timeIntervalSinceReferenceDate
            let pulse = 0.5 * (1 + sin(t * 1.1))
            ZStack {
                Circle()
                    .fill(RadialGradient(colors: [Theme.cyan.opacity(0.18 + 0.12 * pulse), .clear], center: .center, startRadius: 4, endRadius: size * 0.75))
                    .frame(width: size * 1.5, height: size * 1.5)
                Image("Logo").resizable().scaledToFill()
                    .frame(width: size, height: size)
                    .clipShape(Circle())
                    .scaleEffect(1 + 0.025 * pulse)
                    .shadow(color: Theme.indigo.opacity(0.45), radius: 6)
            }
            .frame(height: size * 1.25)
        }
        .accessibilityLabel("AbstractFramework")
    }
}


/// A field with its send arrow inside, on the right: the label is the placeholder, the arrow is the
/// only button (enabled when the field is ready; a spinner while working).
struct InputRow: View {
    let placeholder: String
    @Binding var text: String
    var secure = false
    var working = false
    var ready = true
    let send: () -> Void

    var body: some View {
        HStack(spacing: 4) {
            // A text-field link, not a TextField: the system field draws its own grey capsule inside
            // ours. The link opens the same input (dictation, Scribble, keyboard); what was typed
            // is shown in our capsule, and submitting it continues at once.
            TextFieldLink(prompt: Text(placeholder)) {
                Group {
                    if text.isEmpty { Text(placeholder).foregroundStyle(Theme.muted) }
                    else { Text(secure ? String(repeating: "•", count: min(text.count, 12)) : text).foregroundStyle(Theme.text) }
                }
                .font(.rounded(.footnote)).lineLimit(1).minimumScaleFactor(0.7)
                .frame(maxWidth: .infinity, minHeight: 28, alignment: .leading)
                .contentShape(Rectangle())
            } onSubmit: { value in
                text = value.trimmingCharacters(in: .whitespacesAndNewlines)
                if !text.isEmpty && !working { DispatchQueue.main.async { send() } }   // the parent re-checks the value
            }
            .buttonStyle(.plain)
            Button(action: send) {
                Group {
                    if working { ProgressView() } else { Image(systemName: "arrow.up.circle.fill").font(.system(size: 24)) }
                }
                .frame(width: 28, height: 28)
                .foregroundStyle(ready ? Theme.cyan : Theme.muted.opacity(0.5))
            }
            .buttonStyle(.plain)
            .disabled(!ready || working)
            .accessibilityLabel("Continue")
        }
        .padding(.leading, 12).padding(.trailing, 4).padding(.vertical, 4)
        .background(Theme.card, in: Capsule())
    }
}
