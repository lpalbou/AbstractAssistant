import AbstractGatewayClient
import AssistantPush
import SwiftUI
import WatchKit

/// The watch's sign-in: the gateway, the account, and either its token or a 30-day session from an
/// emailed code. A Keychain item shared through the app group (`SharedSignInStore`) so the
/// notification service extension reads the same sign-in;
/// the address and the account name (no secret) also stay in UserDefaults for the sign-in page.
/// A save is a sign-in: it takes a new push registration handle (`reg`). It comes from the sign-in
/// page or the launch arguments: the watch signs in on its own, never through the iPhone.
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

    /// `at`: when it was signed in.
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
    /// False when a sign-in is still there afterwards (the Keychain refused to delete it).
    @discardableResult
    static func clear(_ d: UserDefaults = .standard) -> Bool {
        SharedSignInStore.clear()
        for k in legacyKeys { d.removeObject(forKey: k) }
        if SharedSignInStore.load() != nil { SharedSignInStore.clear() }   // once more before saying so
        return SharedSignInStore.load() == nil
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

/// An account kept at Sign out ("Keep my sign-in") for a one-tap return from the sign-in page: the
/// account and its credential (an account token, or a session id with its CSRF value). It belongs
/// to one gateway's entry in `GatewayBook`, never to a list shared by every gateway.
struct KeptSignIn: Codable, Equatable, Identifiable {
    var gateway: String
    var user: String
    var token: String?
    var session: String?
    var csrf: String?
    var keptAt: Date

    var id: String { user.lowercased() }

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

/// One gateway of the book: its address, when it was last signed into or out of (the chooser's
/// order), and the accounts kept on it, most recently kept first.
struct GatewayEntry: Codable, Equatable {
    var gateway: String
    var usedAt: Date
    var accounts: [KeptSignIn]

    var url: URL? { SavedSignIn.normalize(gateway) }
}

/// Every gateway this watch has signed into, each with the accounts kept on it: gateway → accounts,
/// so an account kept on one gateway is never offered on another. One Keychain item (`gateways`,
/// beside the sign-in in `SharedSignInStore`, never UserDefaults: a kept account holds its
/// credential). A gateway with accounts is never dropped; at most `gatewayLimit` without any are
/// remembered. Earlier builds kept the addresses in UserDefaults (`gateway.known`) and the
/// accounts in one flat Keychain list (`kept-signins`): the first read moves both in, then deletes them.
enum GatewayBook {
    static let itemName = "gateways"
    static let legacyKeptName = "kept-signins"
    static let legacyKnownKey = "gateway.known"
    /// Gateways without a kept account that are remembered.
    static let gatewayLimit = 8
    /// Accounts kept per gateway.
    static let accountLimit = 8
    /// Rows the sign-in page shows for the chosen gateway (it must fit one screen).
    static let shown = 3

    /// A gateway's identity: its normalized address, lowercased (scheme, host, port, path).
    static func key(_ url: URL) -> String {
        (SavedSignIn.normalize(url.absoluteString) ?? url).absoluteString.lowercased()
    }

    /// The book, most recently used gateway first.
    static func entries(_ store: SecretStore = SharedSignInStore.store, _ d: UserDefaults = .standard) -> [GatewayEntry] {
        if let data = try? SharedSignInStore.read(named: itemName, from: store),
           let book = try? JSONDecoder().decode([GatewayEntry].self, from: data) {
            return book.sorted { $0.usedAt > $1.usedAt }
        }
        return migrate(store, d)
    }

    /// The gateways, most recent first.
    static func gateways(_ store: SecretStore = SharedSignInStore.store) -> [URL] {
        entries(store).compactMap(\.url)
    }

    /// The accounts kept on this gateway, most recently kept first.
    static func accounts(on gateway: URL, _ store: SecretStore = SharedSignInStore.store) -> [KeptSignIn] {
        let k = key(gateway)
        return entries(store).first { $0.gateway.lowercased() == k }?.accounts ?? []
    }

    static func account(on gateway: URL, user: String, _ store: SecretStore = SharedSignInStore.store) -> KeptSignIn? {
        accounts(on: gateway, store).first { $0.id == user.lowercased() }
    }

    /// Signed into (or out of) this gateway: it moves to the top of the chooser.
    static func touch(_ gateway: URL, at date: Date = Date(), _ store: SecretStore = SharedSignInStore.store) {
        try? update(gateway, at: date, store) { _ in }
    }

    /// Keeps `s` as `user`'s account on its gateway, replacing the one kept before for that user.
    /// Throws when the Keychain refuses it, or when it does not read back: a sign-in the person
    /// asked to keep is never lost without a word.
    static func keep(_ s: SavedSignIn, user: String, _ store: SecretStore = SharedSignInStore.store) throws {
        let new = KeptSignIn(s, user: user)
        try update(s.gateway, at: new.keptAt, store) { accounts in
            accounts = Array(([new] + accounts.filter { $0.id != new.id }).prefix(accountLimit))
        }
        guard account(on: s.gateway, user: user, store)?.signIn?.credential == s.credential else { throw KeepError() }
    }

    struct KeepError: Error {}

    /// Forgets `user`'s account on this gateway (the gateway itself stays in the chooser).
    static func forget(gateway: URL, user: String, _ store: SecretStore = SharedSignInStore.store) {
        guard account(on: gateway, user: user, store) != nil else { return }
        let k = key(gateway)
        var book = entries(store)
        if let i = book.firstIndex(where: { $0.gateway.lowercased() == k }) {
            book[i].accounts.removeAll { $0.id == user.lowercased() }
        }
        try? write(book, store)
    }

    static func clear(_ store: SecretStore = SharedSignInStore.store, _ d: UserDefaults = .standard) {
        SharedSignInStore.remove(named: itemName, from: store)
        SharedSignInStore.remove(named: legacyKeptName, from: store)
        d.removeObject(forKey: legacyKnownKey)
    }

    private static func update(_ gateway: URL, at date: Date, _ store: SecretStore, _ change: (inout [KeptSignIn]) -> Void) throws {
        let k = key(gateway)
        var book = entries(store)
        var entry = book.first { $0.gateway.lowercased() == k }
            ?? GatewayEntry(gateway: (SavedSignIn.normalize(gateway.absoluteString) ?? gateway).absoluteString, usedAt: date, accounts: [])
        entry.usedAt = max(entry.usedAt, date)
        change(&entry.accounts)
        book.removeAll { $0.gateway.lowercased() == k }
        try write([entry] + book, store)
    }

    /// Writes the book, most recent first: every gateway with an account, and at most
    /// `gatewayLimit` of those without one.
    private static func write(_ book: [GatewayEntry], _ store: SecretStore) throws {
        var bare = 0
        let kept = book.sorted { $0.usedAt > $1.usedAt }.filter { e in
            if !e.accounts.isEmpty { return true }
            bare += 1
            return bare <= gatewayLimit
        }
        try SharedSignInStore.write(named: itemName, JSONEncoder().encode(kept), to: store)
    }

    /// The first read of a watch upgraded from an earlier build: the flat kept list and the known
    /// addresses become the book (the known order kept), then the old ones are deleted, only once
    /// the book is written.
    private static func migrate(_ store: SecretStore, _ d: UserDefaults) -> [GatewayEntry] {
        let known = (d.stringArray(forKey: legacyKnownKey) ?? []).compactMap(SavedSignIn.normalize)
        let kept = (try? SharedSignInStore.read(named: legacyKeptName, from: store))
            .flatMap { try? JSONDecoder().decode([KeptSignIn].self, from: $0) } ?? []
        guard !known.isEmpty || !kept.isEmpty else { return [] }
        var book: [GatewayEntry] = []
        let now = Date()
        for (i, url) in known.enumerated() {
            book.append(GatewayEntry(gateway: url.absoluteString, usedAt: now.addingTimeInterval(-Double(i)), accounts: []))
        }
        for account in kept.sorted(by: { $0.keptAt > $1.keptAt }) {
            guard let url = SavedSignIn.normalize(account.gateway) else { continue }
            let k = key(url)
            if let i = book.firstIndex(where: { $0.gateway.lowercased() == k }) {
                if !book[i].accounts.contains(where: { $0.id == account.id }) { book[i].accounts.append(account) }
            } else {
                book.append(GatewayEntry(gateway: url.absoluteString, usedAt: account.keptAt, accounts: [account]))
            }
        }
        do { try write(book, store) } catch { return book.sorted { $0.usedAt > $1.usedAt } }
        SharedSignInStore.remove(named: legacyKeptName, from: store)
        d.removeObject(forKey: legacyKnownKey)
        return book.sorted { $0.usedAt > $1.usedAt }
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

    /// The accounts kept on the chosen gateway (at most 3), and on no other.
    private var kept: [KeptSignIn] { Array(GatewayBook.accounts(on: gateway).prefix(GatewayBook.shown)) }

    /// What the field starts with: the user signed in last, on that gateway, unless a kept sign-in
    /// already offers that user as a row (two ways into one account would read as two accounts).
    static var initialIdentifier: String {
        guard let user = UserDefaults.standard.string(forKey: "gateway.user"), !user.isEmpty else { return "" }
        return GatewayBook.account(on: lastGateway, user: user) == nil ? user : ""
    }

    /// The gateway signed into last, else the most recent known one, else AbstractFramework's.
    static var lastGateway: URL {
        UserDefaults.standard.string(forKey: "gateway.url").flatMap(SavedSignIn.normalize)
            ?? GatewayBook.gateways().first
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
            if let url = SavedSignIn.normalize(kept.gateway) { GatewayBook.forget(gateway: url, user: kept.user) }
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

/// The gateway chooser (a tap on the sign-in page's gateway line): every gateway of the book
/// (`GatewayBook`: signed into, or with accounts kept on it), most recent first, the current one
/// marked, AbstractFramework's own always, each with how many accounts are kept on it; then
/// "Another gateway…", which takes a typed address ("gateway.example.org" is read as https).
struct GatewayChooser: View {
    let current: URL
    let choose: (URL) -> Void
    @State private var invalid = false

    /// The book's gateways (the current one on top when the book does not have it yet), then
    /// AbstractFramework's when it is not among them.
    private var options: [URL] {
        let book = GatewayBook.gateways()
        var list = book.contains { GatewayBook.key($0) == GatewayBook.key(current) } ? book : [current] + book
        if let home = SavedSignIn.normalize(SavedSignIn.defaultGateway), !list.contains(where: { GatewayBook.key($0) == GatewayBook.key(home) }) {
            list.append(home)
        }
        return list
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 6) {
                Text("Gateway").font(.rounded(.headline)).frame(maxWidth: .infinity)
                ForEach(options, id: \.absoluteString) { url in
                    let isCurrent = GatewayBook.key(url) == GatewayBook.key(current)
                    let accounts = GatewayBook.accounts(on: url).count
                    Button { choose(url) } label: {
                        CapsuleRow(symbol: "server.rack", text: SavedSignIn.label(url), color: isCurrent ? Theme.text : Theme.text2,
                                   trailingWidth: (accounts > 0 ? 26 : 0) + (isCurrent ? 16 : 0)) {
                            HStack(spacing: 3) {
                                // How many accounts are kept there (one tap each on the sign-in page).
                                if accounts > 0 {
                                    Label("\(accounts)", systemImage: "person.fill").labelStyle(CountLabel())
                                }
                                if isCurrent { Image(systemName: "checkmark").font(.system(size: 13, weight: .bold)).foregroundStyle(Theme.cyan) }
                            }
                        }
                    }
                    .buttonStyle(.tap)
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel(SavedSignIn.label(url) + (accounts > 0 ? ", \(accounts) kept \(accounts == 1 ? "account" : "accounts")" : "")
                                        + (isCurrent ? ", current" : ""))
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

/// "👤2": a glyph and a number, small and muted (the chooser's kept accounts).
private struct CountLabel: LabelStyle {
    func makeBody(configuration: Configuration) -> some View {
        HStack(spacing: 1) { configuration.icon.font(.system(size: 9)); configuration.title.font(.rounded(.caption2)) }
            .foregroundStyle(Theme.muted)
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
