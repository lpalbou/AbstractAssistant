import AbstractGatewayClient
import AssistantPush
import SwiftUI
import WatchKit

/// The watch's sign-in: the gateway, the account, and either its token or a 30-day session from an
/// emailed code. A Keychain item shared through the app group (`SharedSignInStore`) so the
/// notification service extension reads the same sign-in;
/// the address and the account name (no secret) also stay in UserDefaults for the sign-in page.
/// A save is a sign-in: it takes a new push registration handle (`reg`). It comes from the sign-in
/// page, the launch arguments, or the iPhone (`WatchPush` adopts the iPhone's sign-in).
struct SavedSignIn {
    var gateway: URL
    var user: String?
    var credential: GatewayCredential

    static let defaultGateway = "https://gateway.abstractframework.ai"
    private static let legacyKeys = ["gateway.token", "gateway.session", "gateway.csrf"]

    init(gateway: URL, user: String?, credential: GatewayCredential) {
        self.gateway = gateway; self.user = user; self.credential = credential
    }

    init?(_ s: SharedSignIn) {
        if let token = s.token, !token.isEmpty { credential = .token(token) }
        else if let sid = s.session, let csrf = s.csrf, !sid.isEmpty { credential = .session(id: sid, csrf: csrf) }
        else { return nil }
        gateway = s.gateway; user = s.user
    }

    /// The sealed record (its push handle and sign-in time).
    static func current() -> SharedSignIn? { SharedSignInStore.load() }

    static func load(_ d: UserDefaults = .standard) -> SavedSignIn? {
        if let sealed = SharedSignInStore.load(), let s = SavedSignIn(sealed) { return s }
        // A sign-in kept by an earlier version in UserDefaults: sealed once, then removed there.
        guard let url = d.string(forKey: "gateway.url").flatMap(URL.init(string:)) else { return nil }
        let legacy: SavedSignIn
        if let sid = d.string(forKey: "gateway.session"), let csrf = d.string(forKey: "gateway.csrf") {
            legacy = SavedSignIn(gateway: url, user: d.string(forKey: "gateway.user"), credential: .session(id: sid, csrf: csrf))
        } else if let token = d.string(forKey: "gateway.token") {
            legacy = SavedSignIn(gateway: url, user: d.string(forKey: "gateway.user"), credential: .token(token))
        } else { return nil }
        legacy.save(d)
        return legacy
    }

    /// `at`: when it was signed in (the iPhone's time for a sign-in it handed over).
    func save(_ d: UserDefaults = .standard, at date: Date = Date()) {
        d.set(gateway.absoluteString, forKey: "gateway.url")
        d.set(user, forKey: "gateway.user")
        try? SharedSignInStore.save(shared(at: date))
        for k in Self.legacyKeys { d.removeObject(forKey: k) }
    }

    func shared(at date: Date = Date()) -> SharedSignIn {
        switch credential {
        case .token(let t): SharedSignIn(gateway: gateway, user: user, token: t, signedInAt: date)
        case .session(let id, let csrf): SharedSignIn(gateway: gateway, user: user, session: id, csrf: csrf, signedInAt: date)
        }
    }

    /// Signing out forgets the credential; the gateway address stays as the next sign-in's default.
    static func clear(_ d: UserDefaults = .standard) {
        SharedSignInStore.clear()
        for k in legacyKeys { d.removeObject(forKey: k) }
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

    /// What the sign-in page shows of a gateway: its host (and port), the scheme only when it is
    /// plain http.
    static func label(_ url: URL) -> String {
        let host = (url.host() ?? url.absoluteString) + (url.port.map { ":\($0)" } ?? "")
        return url.scheme == "http" ? "http://" + host : host
    }
}

/// Every gateway this watch has signed into, most recent first: normalized addresses in
/// UserDefaults ("gateway.known"), at most 8. The sign-in page's gateway chooser lists them.
enum KnownGateways {
    static let storageKey = "gateway.known"
    static let limit = 8

    static func all(_ d: UserDefaults = .standard) -> [URL] {
        (d.stringArray(forKey: storageKey) ?? []).compactMap(SavedSignIn.normalize)
    }

    /// Signed in on `url`: it moves to the top of the list.
    static func add(_ url: URL, _ d: UserDefaults = .standard) {
        guard let u = SavedSignIn.normalize(url.absoluteString) else { return }
        var list = (d.stringArray(forKey: storageKey) ?? []).filter { $0.lowercased() != u.absoluteString.lowercased() }
        list.insert(u.absoluteString, at: 0)
        d.set(Array(list.prefix(limit)), forKey: storageKey)
    }

    static func clear(_ d: UserDefaults = .standard) { d.removeObject(forKey: storageKey) }
}

/// A sign-in kept at Sign out ("Keep my sign-in") for a one-tap return from the sign-in page: the
/// gateway, the account, and its credential (an account token, or a session id with its CSRF
/// value). A Keychain item beside the sign-in (`SharedSignInStore`, the same store as `SavedSignIn`:
/// never UserDefaults), keyed by the gateway's host and the user.
struct KeptSignIn: Codable, Equatable, Identifiable {
    var gateway: String
    var user: String
    var token: String?
    var session: String?
    var csrf: String?
    var keptAt: Date

    var id: String { KeptSignIns.key(host: URL(string: gateway).map(KeptSignIns.host) ?? gateway, user: user) }

    init(_ s: SavedSignIn, user: String, at date: Date = Date()) {
        gateway = s.gateway.absoluteString; self.user = user; keptAt = date
        switch s.credential {
        case .token(let t): token = t
        case .session(let sid, let c): session = sid; csrf = c
        }
    }

    /// The sign-in to connect with; nil when the stored entry is incomplete.
    var signIn: SavedSignIn? {
        guard let url = SavedSignIn.normalize(gateway) else { return nil }
        if let session, let csrf { return SavedSignIn(gateway: url, user: user, credential: .session(id: session, csrf: csrf)) }
        if let token { return SavedSignIn(gateway: url, user: user, credential: .token(token)) }
        return nil
    }
}

/// The kept sign-ins (the Keychain item `kept-signins` beside the sign-in), one per gateway host
/// and user, most recently kept first. The sign-in page shows at most 3 for the chosen gateway.
enum KeptSignIns {
    static let fileName = "kept-signins"
    static let shown = 3
    static let limit = 24

    static func host(_ url: URL) -> String {
        (url.host() ?? url.absoluteString).lowercased() + (url.port.map { ":\($0)" } ?? "")
    }

    static func key(host: String, user: String) -> String { host + "|" + user.lowercased() }

    static func all(_ store: SecretStore = SharedSignInStore.store) -> [KeptSignIn] {
        guard let data = try? SharedSignInStore.read(named: fileName, from: store),
              let list = try? JSONDecoder().decode([KeptSignIn].self, from: data) else { return [] }
        return list.sorted { $0.keptAt > $1.keptAt }
    }

    /// The kept sign-ins for this gateway, most recent first, at most `shown`.
    static func entries(for gateway: URL, _ store: SecretStore = SharedSignInStore.store) -> [KeptSignIn] {
        let h = host(gateway)
        return Array(all(store).filter { $0.signIn.map { host($0.gateway) } == h }.prefix(shown))
    }

    static func entry(gateway: URL, user: String, _ store: SecretStore = SharedSignInStore.store) -> KeptSignIn? {
        let k = key(host: host(gateway), user: user)
        return all(store).first { $0.id == k }
    }

    /// Keeps `s` as `user`'s sign-in on its gateway, replacing the one kept before.
    static func keep(_ s: SavedSignIn, user: String, _ store: SecretStore = SharedSignInStore.store) {
        let new = KeptSignIn(s, user: user)
        write([new] + all(store).filter { $0.id != new.id }, store)
    }

    static func forget(gateway: URL, user: String, _ store: SecretStore = SharedSignInStore.store) {
        let k = key(host: host(gateway), user: user)
        let list = all(store)
        if list.contains(where: { $0.id == k }) { write(list.filter { $0.id != k }, store) }
    }

    static func clear(_ store: SecretStore = SharedSignInStore.store) { SharedSignInStore.remove(named: fileName, from: store) }

    private static func write(_ list: [KeptSignIn], _ store: SecretStore) {
        if list.isEmpty { SharedSignInStore.remove(named: fileName, from: store); return }
        guard let data = try? JSONEncoder().encode(Array(list.prefix(limit))) else { return }
        try? SharedSignInStore.write(named: fileName, data, to: store)
    }
}

/// First launch, after Sign out, or when a session ends: the gateway (the last one used; a tap
/// chooses another), the sign-ins kept on it for a one-tap return, then who you are, then your
/// token or an emailed one-time code. A user name asks for its token; a registered email gets an
/// 8-digit code by email (the gateway sends it from the account's own mailbox and keeps it 10 minutes).
struct SignInView: View {
    enum Step: Equatable { case identify, token(user: String), code(email: String, sentTo: String) }

    @EnvironmentObject private var model: AppModel
    @State private var step: Step = .identify
    @State private var identifier = SignInView.initialIdentifier
    @State private var secret = ""
    @State private var gateway: URL = SignInView.lastGateway
    @State private var choosingGateway = false
    @State private var working = false
    @State private var error: String?

    var body: some View {
        FitScroll {
                VStack(spacing: 6) {
                    Spacer(minLength: 0)
                    // Smaller as kept sign-ins add their rows, so the page still fits one screen.
                    LogoMark(size: kept.isEmpty ? 44 : kept.count == 1 ? 38 : 28)
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
                .padding(.top, 4)
        }
        // The mark may rise into the time's band (it is centred, the time is at the right): the
        // band's height is what lets the gateway, a kept sign-in and the field fit one screen.
        .ignoresSafeArea(edges: .top)
        .background(
            RadialGradient(colors: [Theme.indigoButton.opacity(0.22), Theme.ground], center: .top, startRadius: 4, endRadius: 190)
                .ignoresSafeArea()
        )
        .sheet(isPresented: $choosingGateway) {
            GatewayChooser(current: gateway) { url in
                // Another gateway: its own kept rows, and an empty field (the user typed or signed
                // in last belongs to the gateway left).
                if url != gateway { gateway = url; identifier = ""; error = nil }
                choosingGateway = false
            }
        }
        .task { await runTestHooks() }
    }

    /// The sign-ins kept on the chosen gateway (at most 3).
    private var kept: [KeptSignIn] { KeptSignIns.entries(for: gateway) }

    /// What the field starts with: the user signed in last, on that gateway, unless a kept sign-in
    /// already offers that user as a row (two ways into one account would read as two accounts).
    static var initialIdentifier: String {
        guard let user = UserDefaults.standard.string(forKey: "gateway.user"), !user.isEmpty else { return "" }
        return KeptSignIns.entry(gateway: lastGateway, user: user) == nil ? user : ""
    }

    /// The gateway signed into last, else the most recent known one, else AbstractFramework's.
    static var lastGateway: URL {
        UserDefaults.standard.string(forKey: "gateway.url").flatMap(SavedSignIn.normalize)
            ?? KnownGateways.all().first
            ?? SavedSignIn.normalize(SavedSignIn.defaultGateway)!
    }

    // MARK: - Steps

    private var identify: some View {
        VStack(spacing: 5) {
            gatewayRow
            ForEach(kept) { kept in
                keptRow(kept)
            }
            InputRow(placeholder: "Sign in with user or email", text: $identifier, working: working,
                     ready: !identifier.trimmingCharacters(in: .whitespaces).isEmpty) {
                Task { await proceed() }
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("signin.identify")
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
        .buttonStyle(.tap)
    }

    /// The gateway, in the field's capsule: a tap opens the chooser.
    private var gatewayRow: some View {
        Button { choosingGateway = true } label: {
            CapsuleRow(symbol: "server.rack", text: SavedSignIn.label(gateway), color: Theme.text2) {
                Image(systemName: "chevron.up.chevron.down").font(.system(size: 13, weight: .semibold)).foregroundStyle(Theme.muted)
            }
        }
        .buttonStyle(.tap)
        .disabled(working)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Gateway \(SavedSignIn.label(gateway))")
        .accessibilityHint("Choose the gateway")
        .accessibilityAddTraits(.isButton)
        .accessibilityIdentifier("signin.gateway")
    }

    /// A sign-in kept at Sign out: one tap signs in again with its credential. A credential the
    /// gateway no longer accepts is forgotten on its first 401 (`AppModel.signOut`).
    private func keptRow(_ kept: KeptSignIn) -> some View {
        Button { quickSignIn(kept) } label: {
            CapsuleRow(symbol: "person.crop.circle.fill", text: "Sign in as \(kept.user)", color: Theme.text) {
                Image(systemName: "arrow.up.circle.fill").font(.system(size: 24)).foregroundStyle(Theme.cyan)
            }
        }
        .buttonStyle(.tap)
        .disabled(working)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Sign in as \(kept.user)")
        .accessibilityAddTraits(.isButton)
        .accessibilityIdentifier("signin.kept")
    }

    private var gatewayURL: URL? { gateway }

    private func quickSignIn(_ kept: KeptSignIn) {
        guard let s = kept.signIn else {
            if let url = SavedSignIn.normalize(kept.gateway) { KeptSignIns.forget(gateway: url, user: kept.user) }
            error = "That sign-in can't be used. Sign in again."
            return
        }
        identifier = kept.user
        finish(s)
    }

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

/// One line of the sign-in page in the field's capsule: a glyph, a text, and a trailing control in
/// the send arrow's place (a chevron, an arrow).
struct CapsuleRow<Trailing: View>: View {
    let symbol: String
    let text: String
    var color: Color = Theme.text
    /// The trailing control's width: the send arrow's 28, less for a checkmark.
    var trailingWidth: CGFloat = 28
    @ViewBuilder let trailing: () -> Trailing

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: symbol).font(.system(size: 13, weight: .semibold)).foregroundStyle(Theme.muted)
                .frame(width: 16)
            Text(text).font(.rounded(.footnote)).foregroundStyle(color).lineLimit(1).minimumScaleFactor(0.7)
                .frame(maxWidth: .infinity, minHeight: 28, alignment: .leading)
            trailing().frame(width: trailingWidth, height: 28)
        }
        .padding(.leading, 10).padding(.trailing, trailingWidth < 28 ? 10 : 4).padding(.vertical, 4)
        .background(Theme.card, in: Capsule())
        .contentShape(Capsule())
    }
}

/// The gateway chooser (a tap on the sign-in page's gateway line): every gateway signed into, most
/// recent first, the current one marked, then "Another gateway…", which takes a typed address
/// ("gateway.example.org" is read as https).
struct GatewayChooser: View {
    let current: URL
    let choose: (URL) -> Void
    @State private var invalid = false

    private var options: [URL] {
        let known = KnownGateways.all()
        let same: (URL) -> Bool = { $0.absoluteString.lowercased() == current.absoluteString.lowercased() }
        return known.contains(where: same) ? known : [current] + known
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 6) {
                Text("Gateway").font(.rounded(.headline)).frame(maxWidth: .infinity)
                ForEach(options, id: \.absoluteString) { url in
                    let isCurrent = url.absoluteString.lowercased() == current.absoluteString.lowercased()
                    Button { choose(url) } label: {
                        CapsuleRow(symbol: "server.rack", text: SavedSignIn.label(url), color: isCurrent ? Theme.text : Theme.text2,
                                   trailingWidth: isCurrent ? 16 : 0) {
                            if isCurrent { Image(systemName: "checkmark").font(.system(size: 13, weight: .bold)).foregroundStyle(Theme.cyan) }
                        }
                    }
                    .buttonStyle(.tap)
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel(SavedSignIn.label(url) + (isCurrent ? ", current" : ""))
                    .accessibilityAddTraits(isCurrent ? [.isButton, .isSelected] : .isButton)
                    .accessibilityIdentifier("gateway.option.\(SavedSignIn.label(url))")
                }
                // A text-field link, as the sign-in field: the system field would draw its own capsule.
                TextFieldLink(prompt: Text("gateway.example.org")) {
                    CapsuleRow(symbol: "plus", text: "Another gateway…", color: Theme.cyan, trailingWidth: 0) { EmptyView() }
                } onSubmit: { value in
                    if let url = SavedSignIn.normalize(value) { invalid = false; choose(url) }
                    else if !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { invalid = true }
                }
                .buttonStyle(.tap)
                .accessibilityIdentifier("gateway.another")
                if invalid {
                    Text("That is not a gateway address.").font(.rounded(.caption2)).foregroundStyle(Theme.red)
                        .multilineTextAlignment(.center)
                }
            }
            .padding(.horizontal, 4)
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
            .buttonStyle(.tap)
            Button(action: send) {
                Group {
                    if working { ProgressView() } else { Image(systemName: "arrow.up.circle.fill").font(.system(size: 24)) }
                }
                .frame(width: 28, height: 28)
                .foregroundStyle(ready ? Theme.cyan : Theme.muted.opacity(0.5))
            }
            .buttonStyle(.tap)
            .disabled(!ready || working)
            .accessibilityLabel("Continue")
        }
        .padding(.leading, 12).padding(.trailing, 4).padding(.vertical, 4)
        .background(Theme.card, in: Capsule())
    }
}
