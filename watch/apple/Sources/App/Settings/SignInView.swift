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
    @State private var info: String?

    var body: some View {
        ScrollView {
            VStack(spacing: 7) {
                LogoMark(size: 44)
                Text("AbstractFramework")
                    .font(.rounded(.headline, weight: .bold))
                    .foregroundStyle(LinearGradient(colors: [Theme.cyan, Theme.indigo, Theme.green], startPoint: .leading, endPoint: .trailing))
                Text(subtitle).font(.rounded(.caption2)).foregroundStyle(Theme.muted).multilineTextAlignment(.center)
                if let notice = model.signInNotice, step == .identify {
                    Text(notice).font(.rounded(.caption2)).foregroundStyle(Theme.amber).multilineTextAlignment(.center)
                }
                switch step {
                case .identify: identify
                case .token(let user): tokenStep(user)
                case .code(_, let to): codeStep(to)
                }
                if let info { Text(info).font(.rounded(.caption2)).foregroundStyle(Theme.cyan).multilineTextAlignment(.center) }
                if let error { Text(error).font(.rounded(.caption2)).foregroundStyle(Theme.red).multilineTextAlignment(.center) }
                Text("Your token or code goes only to your gateway.").font(.rounded(.caption2)).foregroundStyle(Theme.muted.opacity(0.8))
                    .multilineTextAlignment(.center).padding(.top, 2)
            }
            .padding(.horizontal, 2)
        }
        .background(
            RadialGradient(colors: [Theme.indigoButton.opacity(0.22), Theme.ground], center: .top, startRadius: 4, endRadius: 190)
                .ignoresSafeArea()
        )
        .task { await runTestHooks() }
    }

    private var subtitle: String {
        switch step {
        case .identify: "Sign in to your assistant"
        case .token(let user): "Token for \(user)"
        case .code: "Enter the code from your email"
        }
    }

    // MARK: - Steps

    private var identify: some View {
        VStack(spacing: 6) {
            TextField("User or email", text: $identifier)
                .textContentType(.username)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .font(.rounded(.footnote))
            Button(working ? "…" : "Continue") { Task { await proceed() } }
                .buttonStyle(FilledButtonStyle(fill: Theme.indigoButton))
                .disabled(working || identifier.trimmingCharacters(in: .whitespaces).isEmpty || gatewayURL == nil)
            gatewayRow
        }
    }

    private func tokenStep(_ user: String) -> some View {
        VStack(spacing: 6) {
            SecureField("Token", text: $secret).font(.mono(.caption2)).textContentType(.password)
            Button(working ? "Signing in…" : "Sign in") { Task { await signInWithToken(user) } }
                .buttonStyle(FilledButtonStyle(fill: Theme.indigoButton))
                .disabled(working || secret.trimmingCharacters(in: .whitespaces).isEmpty)
            backButton
        }
    }

    private func codeStep(_ sentTo: String) -> some View {
        VStack(spacing: 6) {
            Text("Sent to \(sentTo) · valid 10 min").font(.rounded(.caption2)).foregroundStyle(Theme.text2)
            TextField("8-digit code", text: $secret)
                .textContentType(.oneTimeCode)
                .font(.mono(.footnote, weight: .semibold))
            Button(working ? "Signing in…" : "Sign in") { Task { await signInWithCode() } }
                .buttonStyle(FilledButtonStyle(fill: Theme.indigoButton))
                .disabled(working || secret.filter(\.isNumber).count != 8)
            Button("Send a new code") { Task { await proceed() } }
                .buttonStyle(FilledButtonStyle(fill: Theme.neutralButton, foreground: Theme.text2))
                .disabled(working)
            backButton
        }
    }

    private var backButton: some View {
        Button { step = .identify; secret = ""; error = nil; info = nil } label: {
            Label("Back", systemImage: "chevron.left").font(.rounded(.caption2)).foregroundStyle(Theme.muted)
        }
        .buttonStyle(.plain)
    }

    private var gatewayRow: some View {
        Group {
            if editingGateway {
                TextField("Gateway address", text: $gatewayText)
                    .textContentType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
                    .font(.mono(.caption2))
            } else {
                Button { editingGateway = true } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "server.rack").font(.system(size: 10))
                        Text(gatewayURL?.host() ?? gatewayText).lineLimit(1).minimumScaleFactor(0.7)
                        Text("· change").foregroundStyle(Theme.muted.opacity(0.7))
                    }
                    .font(.rounded(.caption2)).foregroundStyle(Theme.muted)
                }
                .buttonStyle(.plain)
            }
        }
    }

    private var gatewayURL: URL? { SavedSignIn.normalize(gatewayText) }

    // MARK: - Actions

    private func proceed() async {
        let id = identifier.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let gw = gatewayURL, !id.isEmpty else { return }
        error = nil; info = nil; secret = ""
        guard GatewaySignIn.isEmail(id) else { step = .token(user: id); return }
        working = true
        defer { working = false }
        do {
            let answer = try await GatewaySignIn.requestCode(gateway: gw, identifier: id)
            if answer.sent {
                step = .code(email: id, sentTo: answer.to ?? "your email")
                info = nil
                WKInterfaceDevice.current().play(.success)
            } else {
                step = .identify
                error = answer.message ?? "No code could be sent. Use your user name and token."
            }
        } catch {
            self.error = error.localizedDescription
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
            self.error = error.localizedDescription
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
            self.error = error.localizedDescription
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
