import AbstractGatewayClient
import SwiftUI
import WatchKit

enum Route: Hashable {
    case approval(Wait), askUser(Wait), draft(Wait), waits
    case ask(AskView.Phase), picker, sessions, session(SessionSummary), automations, automation(AutomationSummary), automationEdit(AutomationSummary), newAutomation, message(title: String, Exchange), voiceSettings, settings
    case occurrence(title: String, LastOccurrence)
    case read(ReadItem), link(URL), answer(AnswerRef), orbStyle, about
    case tools(AppModel.ToolScope), toolGroup(AppModel.ToolScope, String)
}

/// App state: one GatewayClient, foreground polling every 15 s for waits and runs.
/// One exchange of a conversation: the question, the answer, and whose voice reads it (the run that
/// answered, or the entity).
struct Exchange: Identifiable, Hashable {
    let id: String
    var prompt: String
    var answer: String
    var scope: SpeechScope?
}

@MainActor
final class AppModel: ObservableObject {
    @Published var waits: [Wait] = []
    @Published var runs: [RunSummary] = []
    /// Conversations (turns grouped by session), newest activity first.
    var sessions: [SessionSummary] { SessionSummary.group(runs) }
    /// Each session's latest question, by its newest run id (the row's title).
    @Published private(set) var latestPrompts: [String: String] = [:]
    /// Latest runs whose question the gateway could not give (the row says so; nothing is made up).
    @Published private(set) var unreadablePrompts: Set<String> = []
    /// How many turns the session list reads (Show older adds 100).
    private(set) var runsLimit = 80
    func showOlder() async { runsLimit += 100; await refresh() }
    /// Set by "Continue" on a session: Ask opens on its last exchange, in that session.
    struct Resuming { let sessionId, title, prompt, answer, runId, status: String }
    var resuming: Resuming?
    @Published var automations: [AutomationSummary] = []
    @Published var principal: Principal?
    @Published var lastError: String?
    /// No usable sign-in: the sign-in page replaces everything (first launch, Sign out, a session that ended).
    @Published var needsSignIn = false
    /// Why the sign-in page is back, when it is not the first launch.
    @Published var signInNotice: String?
    /// The automations call failed while waits and runs were fine (shown on the Automations screen only).
    @Published var automationsError: String?
    @Published var path: [Route] = []
    @Published var entities: [EntitySummary] = []
    /// The gateway's tools by name, with their risk tier (observe · act · outreach · destroy).
    @Published var tools: [String: ToolInfo] = [:]
    /// Tool choices (ToolPrefs): defaults for new conversations, and this conversation's changes.
    @Published private(set) var toolDefaults: [String: ToolMode] = ToolPrefs.defaults
    @Published private(set) var sessionTools: [String: ToolMode] = [:]
    /// Waits answered from an approval or question screen (Back without deciding is not an answer).
    private(set) var decidedWaits: Set<String> = []
    /// When the last successful refresh happened; nil until the first one.
    @Published var lastRefresh: Date?
    /// The Ask conversation: one gateway session per watch, kept until "New".
    @Published var askSessionId: String = UserDefaults.standard.string(forKey: "ask.session") ?? AppModel.newSessionId() {
        didSet { sessionTools = ToolPrefs.session(askSessionId); ToolPrefs.touch(askSessionId) }
    }
    /// Who answers an Ask; kept per watch in UserDefaults.
    @Published private(set) var responder = Responder(storageKey: UserDefaults.standard.string(forKey: "ask.responder"))
    /// Open entity conversations, one per home (`chat/open` is "one live session per home").
    private var entityChats: [String: String] = [:]

    @Published private(set) var client: any GatewayClient
    @Published private(set) var gatewayHost: String
    private var seenWaitIDs: Set<String> = []
    private var pollTask: Task<Void, Never>?
    /// Live mode only: `--screen approval|askuser` opens the first real wait after the first poll.
    var pendingScreen: String?
    /// Simulator test hook (`--test-action allow-first|deny-first`): answers the first wait once.
    var testAction: String?
    /// Device test hook (`--test-ask "<prompt>"`): the Ask screen sends this prompt once on appear.
    var testAsk: String?
    /// Device test hooks: `--test-read "<markdown>"` opens the Read screen on that text (spoken through
    /// the newest run's session); `--test-open <url>` opens a URL as a tapped link would.
    var testRead: String?
    var testOpen: URL?
    /// `--test-listen`: Ask opens and starts listening at once (simulator/device check of the microphone).
    var testListen = false
    /// `--test-identify <user or email>` / `--test-secret <token or code>`: the sign-in page fills and submits them.
    var testIdentify: String?
    var testSecret: String?
    /// `--test-pause`: the Read screen pauses 2 s into the speech and resumes 3 s later (logged).
    var testPause = false
    /// `--test-approve once|all`: the next approval screen answers itself after 2 s (Allow once / Allow all in this session).
    var testApprove: String?
    /// `--open-automation N`: opens the Nth live automation after the first refresh (screenshots of real data).
    var testOpenAutomation: Int?
    static let pollInterval: Duration = .seconds(15)

    init(client: any GatewayClient, gatewayHost: String) {
        self.client = client; self.gatewayHost = gatewayHost
        if UserDefaults.standard.string(forKey: "ask.session") == nil { UserDefaults.standard.set(askSessionId, forKey: "ask.session") }
        sessionTools = ToolPrefs.session(askSessionId)
        UserDefaults.standard.removeObject(forKey: "ask.trusted")   // "Accept all" is now tool choices
    }

    var connected: Bool { principal != nil }
    /// First poll still in flight: no answer yet, but no failure either.
    var connecting: Bool { principal == nil && lastError == nil && !client.isMock }

    func startPolling() {
        guard pollTask == nil, !needsSignIn else { return }
        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                guard let self else { return }
                let keepGoing = await self.refresh()
                if !keepGoing { break }
                try? await Task.sleep(for: Self.pollInterval)
            }
        }
    }

    func stopPolling() { pollTask?.cancel(); pollTask = nil }

    /// Signed in (the sign-in page): saves it, replaces the client, clears the cached state, polls.
    func connect(_ signIn: SavedSignIn) {
        signIn.save()
        stopPolling()
        client = LiveGatewayClient(baseURL: signIn.gateway, credential: signIn.credential)
        gatewayHost = signIn.gateway.host() ?? signIn.gateway.absoluteString
        waits = []; runs = []; automations = []; principal = nil; lastError = nil; seenWaitIDs = []; entities = []
        needsSignIn = false; signInNotice = nil; path = []
        startPolling()
    }

    /// Forgets the credential (the gateway address stays as the next default) and shows the sign-in page.
    func signOut(notice: String? = nil) {
        SavedSignIn.clear()
        stopPolling()
        client = MockGatewayClient(); gatewayHost = "—"
        waits = []; runs = []; automations = []; principal = nil; lastError = nil; seenWaitIDs = []; entities = []
        path = []; signInNotice = notice; needsSignIn = true
    }

    /// A fresher row for one automation (its page knows first that it runs or has finished).
    func replaceAutomation(_ a: AutomationSummary) {
        if let i = automations.firstIndex(where: { $0.id == a.id }) { automations[i] = a }
    }

    /// Returns false when polling must stop (401: the gateway locks out by address).
    @discardableResult
    func refresh() async -> Bool {
        do {
            // The three first-poll calls go out together: on the watch's radio each round trip
            // costs seconds, and nothing on Home can be drawn before all three are back.
            async let waitsCall = client.waits()
            async let runsCall = client.recentRuns(limit: runsLimit)
            if principal == nil { principal = try await client.me() }
            let newWaits = try await waitsCall
            if newWaits.contains(where: { !seenWaitIDs.contains($0.id) }) {
                WKInterfaceDevice.current().play(.notification)
            }
            seenWaitIDs.formUnion(newWaits.map(\.id))
            waits = newWaits
            runs = try await runsCall
            // The fast part is on screen now. Automations is the slow call on a public gateway
            // (~7 s measured) and its own failure never marks the gateway offline.
            lastError = nil
            lastRefresh = Date()
            if let text = testRead, let run = runs.first {
                testRead = nil
                path = [.read(ReadItem(title: "Read", text: text, scope: .run(run.runId)))]
            }
            do { automations = try await client.automations() } catch { automationsError = Self.say(error) }
            #if DEBUG
            if let i = testOpenAutomation, i < automations.count {
                testOpenAutomation = nil
                path = [.automations, .automation(automations[i])]
            }
            #endif
            await loadTitles()
            await ensureTools(maxAge: 600)
            if entities.isEmpty, case .entity = responder { await loadEntities() }
            if let screen = pendingScreen, let first = waits.first {
                pendingScreen = nil
                path = [first.kind == .askUser || screen == "askuser" ? .askUser(first) : .approval(first)]
            }
            if let action = testAction, let first = waits.first {
                testAction = nil
                let ok = await answer(first, with: action == "deny-first" ? .deny : .approve)
                #if DEBUG
                print("test-action \(action): \(ok ? "sent" : "failed") for \(first.id)")
                #endif
                if ok { path = [] }
            }
            return true
        } catch GatewayError.unauthorized {
            // A revoked token or an ended session: back to the sign-in page, saying why.
            signOut(notice: "You were signed out. Please sign in again.")
            return false
        } catch {
            lastError = Self.say(error)
            return true
        }
    }

    func answer(_ wait: Wait, with answer: WaitAnswer) async -> Bool {
        do {
            try await client.answer(wait, with: answer)
            if answer == .approve { WKInterfaceDevice.current().play(.success) }
            waits.removeAll { $0.id == wait.id }
            return true
        } catch GatewayError.alreadyHandled {
            WKInterfaceDevice.current().play(.failure)
            waits.removeAll { $0.id == wait.id }
            lastError = Self.say(GatewayError.alreadyHandled)
            return false
        } catch GatewayError.unauthorized {
            signOut(notice: "You were signed out. Please sign in again.")
            return false
        } catch {
            WKInterfaceDevice.current().play(.failure)
            lastError = Self.say(error)
            return false
        }
    }

    var activeRunCount: Int { runs.filter { $0.status == "running" || $0.status == "waiting" }.count }
    var isAdmin: Bool { principal?.admin == true || (principal?.roles ?? []).contains("admin") }
    static func newSessionId() -> String { "watch-" + UUID().uuidString.lowercased() }
    /// An approval's "Accept all": in this conversation, the tools now on Ask stop asking, up to the
    /// risk of the call just approved (at least "makes changes"). Tools that are Off stay off; sends
    /// to someone else and tools whose destination the assistant picks keep asking. It is this
    /// conversation's tool choices, so the tools page shows it and can change it.
    func trustSession(approving wait: Wait) {
        let approved = (wait.details ?? []).map { tools[$0.name]?.riskRank ?? 4 }.max() ?? 4
        let ceiling = max(ToolChoices.allAutoMaxRank, approved)
        let rise = tools.values.filter { t in
            toolMode(t, scope: .session) == .ask && t.riskTier != "outreach" && t.modelControlledDestination != true
                && (t.riskRank ?? 4) <= ceiling
        }
        setTools(rise.map(\.name), .auto, scope: .session)
    }

    func markDecided(_ wait: Wait) { decidedWaits.insert(wait.id) }

    /// The watch approves a call itself only when the tool is known and this conversation runs it
    /// without asking (a run started before the choice still waits for it).
    func autoApprovable(_ wait: Wait) -> Bool {
        guard wait.kind == .toolApproval, let calls = wait.details, !calls.isEmpty else { return false }
        // The runtime asks for a batch as a whole: every call in it must be on Auto.
        return calls.allSatisfy { c in tools[c.name].map { toolMode($0, scope: .session) == .auto } ?? false }
    }

    // MARK: Tools

    /// Where a tool choice applies: the defaults for new conversations, or this conversation.
    enum ToolScope: Hashable { case defaults, session }

    func toolMode(_ tool: ToolInfo, scope: ToolScope) -> ToolMode {
        ToolChoices.mode(of: tool, defaults: toolDefaults, session: scope == .session ? sessionTools : [:])
    }

    /// Sets tools' modes in a scope, keeping only what differs from the level below (the gateway
    /// for defaults; the defaults for a conversation), so a later default still reaches them.
    func setTools(_ names: [String], _ mode: ToolMode, scope: ToolScope) {
        switch scope {
        case .defaults:
            var d = toolDefaults
            for n in names { guard let t = tools[n] else { continue }; d[n] = mode == ToolChoices.gatewayDefault(t) ? nil : mode }
            toolDefaults = d
            ToolPrefs.defaults = d
        case .session:
            var m = sessionTools
            for n in names {
                guard let t = tools[n] else { continue }
                m[n] = mode == ToolChoices.mode(of: t, defaults: toolDefaults, session: [:]) ? nil : mode
            }
            setSessionTools(m)
        }
    }

    private func setSessionTools(_ modes: [String: ToolMode]) {
        sessionTools = modes
        ToolPrefs.setSession(askSessionId, modes)
    }

    /// This conversation uses the defaults again.
    func resetSessionTools() { setSessionTools([:]) }

    /// The defaults follow the gateway again.
    func resetToolDefaults() { toolDefaults = [:]; ToolPrefs.defaults = [:] }

    #if DEBUG
    func reloadToolPrefs() { toolDefaults = ToolPrefs.defaults; sessionTools = ToolPrefs.session(askSessionId) }
    #endif

    /// What this conversation's next run receives (nil until the catalog is read).
    var toolPlan: ToolChoices.Plan? {
        guard !tools.isEmpty else { return nil }
        return ToolChoices.plan(Array(tools.values), defaults: toolDefaults, session: sessionTools)
    }


    /// The tool's risk tier from the gateway's inventory (the wait payload carries none).
    func tier(of wait: Wait) -> String? { tools[wait.toolName]?.riskTier ?? wait.riskTier }
    func isOutreach(_ wait: Wait) -> Bool { tier(of: wait) == "outreach" || wait.isOutreach }
    func isDestructive(_ wait: Wait) -> Bool { tier(of: wait) == "destroy" || wait.isDestructive }

    /// Opened from Ask (the orb is underneath): answering returns to it.
    var approvalFromAsk: Bool {
        guard path.count >= 2 else { return false }
        switch path[path.count - 2] { case .ask, .answer: return true; default: return false }
    }

    /// The orb's look for a responder: the Assistant's own, or the entity's colour and shape. Until
    /// the entities are loaded (launch) an entity shows the Assistant's look; a changed look shows
    /// on the next entities load (the picker reloads them).
    func look(for r: Responder) -> OrbLook {
        guard case .entity(let name) = r, let e = entities.first(where: { $0.name == name }) else { return .assistant }
        return OrbLook(color: e.appearanceColor.flatMap(Color.init(hexString:)),
                       shape: e.appearanceShape.flatMap(OrbShape.init(rawValue:)) ?? .planet)
    }
    var responderLook: OrbLook { look(for: responder) }

    /// Any error as one short sentence a person can act on (never a code or a server's text).
    nonisolated static func say(_ error: Error) -> String {
        switch error {
        case GatewayError.unauthorized: "You were signed out. Please sign in again."
        case GatewayError.alreadyHandled: "Already answered on another device."
        case let e as URLError where [.notConnectedToInternet, .networkConnectionLost, .dataNotAllowed].contains(e.code): "No connection."
        case is URLError: "Can't reach your assistant."
        case let e as GatewaySignIn.Failure: e.errorDescription ?? "Sign-in failed. Try again."
        case let e as GatewayError: e.errorDescription ?? "Something went wrong. Try again."
        default: "Something went wrong. Try again."
        }
    }

    /// Reads the gateway's tool catalog when it is not known yet (an Ask right after launch must not
    /// fall back to the workflow's 9 default tools).
    func ensureTools(maxAge: TimeInterval = .infinity) async {
        if !tools.isEmpty, let read = toolsReadAt, Date().timeIntervalSince(read) < maxAge { return }
        guard let list = try? await client.tools() else { return }
        tools = Dictionary(list.map { ($0.name, $0) }, uniquingKeysWith: { a, _ in a })
        toolsReadAt = Date()
    }

    /// When the tool catalog was read (a toolset the gateway's admin turns on or off shows up).
    private var toolsReadAt: Date?


    /// A conversation's label: its latest question, as the gateway has it (a watch conversation runs
    /// for days; its first question says little about it). Nil until read: never a made-up title.
    func title(of s: SessionSummary) -> String? { latestPrompts[s.latest.runId] }

    /// Reads each listed conversation's latest question (a new turn has a new run id: read again).
    func loadTitles() async {
        let missing = sessions.filter { latestPrompts[$0.latest.runId] == nil }.prefix(40)
        guard !missing.isEmpty else { return }
        let found: [(String, String?)] = await withTaskGroup(of: (String, String?).self) { group in
            for s in missing {
                group.addTask { [client] in
                    guard let p = try? await client.prompt(ofRun: s.latest.runId), !p.isEmpty else { return (s.latest.runId, nil) }
                    return (s.latest.runId, SessionSummary.title(fromPrompt: p))
                }
            }
            var out: [(String, String?)] = []
            for await x in group { out.append(x) }
            return out
        }
        for (k, v) in found {
            if let v { latestPrompts[k] = v; unreadablePrompts.remove(k) } else { unreadablePrompts.insert(k) }
        }
    }

    #if DEBUG
    /// Device probe (`--test-history <session id>`): the orb page's history read, timed (watch console).
    func probeHistory(_ id: String) async {
        for attempt in 1...3 {
            let t0 = Date()
            guard let rows = try? await client.turns(ofSession: id, limit: 1), let latest = rows.first else { print("history: listing failed"); return }
            do {
                let turns = try await client.sessionHistory(latestRun: latest.runId, limit: 1000)
                print("history \(attempt): \(turns.count) turns in \(String(format: "%.1f", Date().timeIntervalSince(t0))) s, oldest «\(turns.first?.prompt?.prefix(50) ?? "")»")
            } catch {
                print("history \(attempt): failed after \(String(format: "%.1f", Date().timeIntervalSince(t0))) s: \(error)")
            }
        }
        print("history probe done")
    }

    /// Test hooks that send questions use a conversation of their own, never kept: a test must not
    /// write into the person's conversation (it did once, 2026-10-17, and became its "title").
    func useTestSession() { askSessionId = "watch-test-" + UUID().uuidString.lowercased() }
    #endif

    /// A session's last exchange: its newest turn's question, answer and state (two requests together).
    func lastExchange(of s: SessionSummary) async -> (prompt: String, answer: String, runId: String, status: String) {
        async let runCall = try? client.run(id: s.latest.runId)
        async let promptCall = try? client.prompt(ofRun: s.latest.runId)
        let (run, prompt) = await (runCall, promptCall)
        return ((prompt ?? nil) ?? "", run?.outputText ?? "", s.latest.runId, run?.status ?? s.latest.status)
    }

    /// Tap on a session: read its last exchange, then open the orb in it.
    func continueSession(_ s: SessionSummary) async {
        let last = await lastExchange(of: s)
        resume(s, lastPrompt: last.prompt, lastAnswer: last.answer, runId: last.runId, status: last.status)
    }

    /// "Continue": Ask talks in this session from now on, opening on its last exchange (`runId`:
    /// the exchange shown, when the caller read a fresher one than the listing's).
    func resume(_ s: SessionSummary, lastPrompt: String, lastAnswer: String, runId: String? = nil, status: String? = nil) {
        resuming = Resuming(sessionId: s.id, title: title(of: s) ?? "", prompt: lastPrompt, answer: lastAnswer,
                            runId: runId ?? s.latest.runId, status: status ?? s.latest.status)
        askSessionId = s.id
        UserDefaults.standard.set(askSessionId, forKey: "ask.session")
        setResponder(.assistant)
        path = [.ask(.idle)]
    }

    func newAskSession() {
        resuming = nil                                   // a pending Continue never lands in a new conversation
        askSessionId = Self.newSessionId()
        UserDefaults.standard.set(askSessionId, forKey: "ask.session")
    }
    /// "updated 12 s ago" / "offline for 3 min".
    var freshness: String? {
        guard let t = lastRefresh else { return nil }
        let s = Int(Date().timeIntervalSince(t))
        let age = s < 60 ? "\(s) s" : s < 3600 ? "\(s / 60) min" : "\(s / 3600) h"
        return lastError == nil ? "updated \(age) ago" : "offline for \(age)"
    }
    var runningCount: Int { runs.filter { $0.status == "running" }.count }
    var doneCount: Int { runs.filter { $0.status == "completed" }.count }
    var failedCount: Int { runs.filter { $0.status == "failed" }.count }

    func setResponder(_ r: Responder, persist: Bool = true) {
        responder = r
        if persist { UserDefaults.standard.set(r.storageKey, forKey: "ask.responder") }
    }

    /// Loads the entities this account may visit and drops a chosen entity that is not among
    /// them (the choice is per watch, the entities are per account).
    func loadEntities() async {
        do {
            entities = try await client.entities()
            if case .entity(let name) = responder, !entities.contains(where: { $0.name == name }) {
                setResponder(.assistant)
                lastError = "\(name.capitalized) isn't available. Asking the Assistant."
            }
        } catch { lastError = Self.say(error) }
    }

    /// One turn with an entity, opening its conversation on first use.
    func entityTurn(_ name: String, text: String) async throws -> String {
        let chatId: String
        if let open = entityChats[name] { chatId = open }
        else { chatId = try await client.openEntityChat(name: name); entityChats[name] = chatId }
        do { return try await client.entityChatTurn(name: name, chatId: chatId, text: text) }
        catch GatewayError.http(let status, let body) where status == 404 || status == 409 {
            // The conversation was closed elsewhere (or a durable visit holds the home): reopen once.
            entityChats[name] = nil
            let fresh = try await client.openEntityChat(name: name); entityChats[name] = fresh
            _ = body
            return try await client.entityChatTurn(name: name, chatId: fresh, text: text)
        }
    }
}

/// Launch arguments: `--mock` (default in Debug), `--live --gateway <url> --token <t>`,
/// `--screen <home|approval|ask|answer|runs|run|automations|settings|pairing|askuser|done>`.
struct LaunchOptions {
    var useMock: Bool
    var screen: String
    var gateway: URL?
    var token: String?
    var testAction: String?
    var testAsk: String?
    var testRead: String?
    var testOpen: String?
    var testListen = false
    var signIn: SavedSignIn?
    var showSignIn = false
    var testIdentify: String?
    var testSecret: String?

    static func parse(_ args: [String] = ProcessInfo.processInfo.arguments) -> LaunchOptions {
        func value(_ flag: String) -> String? {
            guard let i = args.firstIndex(of: flag), i + 1 < args.count else { return nil }
            return args[i + 1]
        }
        let defaults = UserDefaults.standard
        // A pairing passed on the command line is kept: `devicectl device process launch … --gateway U --token T`
        // provisions a watch once from the Mac, without typing on the wrist.
        if let gw = value("--gateway").flatMap(SavedSignIn.normalize), let token = value("--token") {
            SavedSignIn(gateway: gw, user: value("--user"), credential: .token(token)).save(defaults)
        }
        // Screenshot runs: never put the one-time notification question over the screen.
        if args.contains("--no-notification-prompt") { defaults.set(true, forKey: "notify.asked") }
        if args.contains("--forget-gateway") { SavedSignIn.clear(defaults) }
        // Simulator previews: `--orb-design B` picks the orb design (the same key Settings writes).
        if let d = value("--orb-design"), OrbDesign(rawValue: d.uppercased()) != nil {
            defaults.set(d.uppercased(), forKey: OrbDesign.storageKey); defaults.set(true, forKey: OrbDesign.chosenKey)
        }
        // Screenshot runs never stop at the first-launch question; `--ask-orb` asks it again.
        if args.contains("--mock") { defaults.set(true, forKey: OrbDesign.chosenKey) }
        if args.contains("--ask-orb") { defaults.set(false, forKey: OrbDesign.chosenKey) }
        let saved = SavedSignIn.load(defaults)
        // Mock data only when asked (`--mock`: the simulator screenshots). Otherwise a saved
        // sign-in goes live, and without one the sign-in page shows.
        let mock = args.contains("--mock")
        let screen = value("--screen") ?? "home"
        var o = LaunchOptions(useMock: mock, screen: screen, gateway: saved?.gateway, token: nil,
                              testAction: value("--test-action"), testAsk: value("--test-ask"),
                              testRead: value("--test-read"), testOpen: value("--test-open"), testListen: args.contains("--test-listen"))
        o.signIn = saved
        o.showSignIn = screen == "signin" || (!mock && saved == nil)
        #if DEBUG
        o.testIdentify = value("--test-identify"); o.testSecret = value("--test-secret")
        #else
        // Release builds answer no test hook (they auto-approve, auto-sign-in or auto-send).
        o.testAction = nil; o.testAsk = nil; o.testRead = nil; o.testOpen = nil; o.testListen = false
        #endif
        return o
    }

    @MainActor
    func makeModel() -> AppModel {
        let model: AppModel
        if !useMock, let s = signIn {
            model = AppModel(client: LiveGatewayClient(baseURL: s.gateway, credential: s.credential), gatewayHost: s.gateway.host() ?? s.gateway.absoluteString)
        } else {
            model = AppModel(client: MockGatewayClient(), gatewayHost: "mbp")
        }
        model.needsSignIn = showSignIn
        model.testIdentify = testIdentify; model.testSecret = testSecret
        #if DEBUG
        model.testPause = ProcessInfo.processInfo.arguments.contains("--test-pause")
        if let i = ProcessInfo.processInfo.arguments.firstIndex(of: "--test-approve"), i + 1 < ProcessInfo.processInfo.arguments.count {
            model.testApprove = ProcessInfo.processInfo.arguments[i + 1]
        }
        if let i = ProcessInfo.processInfo.arguments.firstIndex(of: "--open-automation"), i + 1 < ProcessInfo.processInfo.arguments.count {
            model.testOpenAutomation = Int(ProcessInfo.processInfo.arguments[i + 1])
        }
        #endif
        return model
    }

    @MainActor
    func initialPath(_ model: AppModel) -> [Route] {
        model.testAction = testAction
        model.testAsk = testAsk
        #if DEBUG
        if testAsk != nil { model.useTestSession() }   // before the orb screen opens on it
        #endif
        model.testRead = testRead
        model.testOpen = testOpen.flatMap(URL.init(string:))
        model.testListen = testListen
        #if DEBUG
        let args = ProcessInfo.processInfo.arguments
        if args.contains("--reset-tools") { ToolPrefs.reset(); model.reloadToolPrefs() }
        if args.contains("--fresh-conversation") { model.useTestSession() }   // a test's own, empty conversation
        // `--test-session <id>`: opens that conversation as a tap on its row does (read-only).
        if let i = args.firstIndex(of: "--test-session"), i + 1 < args.count {
            let sid = args[i + 1]
            Task {
                guard let rows = try? await model.client.turns(ofSession: sid, limit: 100),
                      let s = SessionSummary.group(rows).first else { print("test-session: not found"); return }
                await model.continueSession(s)
            }
        }
        if let i = args.firstIndex(of: "--test-history"), i + 1 < args.count {
            let sid = args[i + 1]
            Task { await model.probeHistory(sid) }
        }
        #endif
        if testListen { return [.ask(.idle)] }
        if !useMock, testAsk != nil { return [.ask(.idle)] }
        // `--screen tools` (defaults) or `--screen tools:<group>` (a group), live or sample data.
        if screen == "tools" { return [.settings, .tools(.defaults)] }
        if screen.hasPrefix("tools:") { return [.settings, .tools(.defaults), .toolGroup(.defaults, String(screen.dropFirst(6)))] }
        if !useMock, screen == "approval" || screen == "askuser" {
            model.pendingScreen = screen   // opened after the first poll with a real wait
            return []
        }
        let waits = MockGatewayClient.sampleWaits
        let approval = waits.first { $0.toolName == "execute_command" }!
        let email = waits.first { $0.isOutreach }!
        let ask = waits.first { $0.kind == .askUser }!
        switch screen {
        case "approval": return [.approval(approval)]
        case "approval-ask": return [.ask(.idle), .approval(approval)]
        case "email": return [.approval(email)]
        case "draft": return [.approval(email), .draft(email)]
        case "picker": return [.ask(.idle), .picker]
        case "askuser": return [.askUser(ask)]
        case "waits": return [.waits]
        case "automation": return [.automations, .automation(MockGatewayClient.sampleAutomations[0])]
        case "automation-new": return [.automations, .newAutomation]
        case "automation-edit": return [.automations, .automation(MockGatewayClient.sampleAutomations[0]), .automationEdit(MockGatewayClient.sampleAutomations[0])]
        case "occurrence":
            let a = MockGatewayClient.sampleAutomations[0]
            return [.automations, .automation(a), .occurrence(title: a.name ?? "", a.lastOccurrence!)]
        case "ask": return [.ask(.idle)]
        case "ask-entity": model.setResponder(.entity("castor"), persist: false); return [.ask(.idle)]
        case "listening": return [.ask(.listening)]
        case "thinking": return [.ask(.thinking)]
        case "answer": return [.ask(.answer)]
        case "runs", "sessions": return [.sessions]
        case "session-long":
            let s = SessionSummary.group(MockGatewayClient.sampleRuns).first { $0.id == "s-qc" }!
            return [.sessions, .session(s)]
        case "session":
            let s = SessionSummary.group(MockGatewayClient.sampleRuns)[1]
            return [.sessions, .session(s)]
        case "automations": return [.automations]
        case "settings": return [.settings]
        case "orblab", "orbstyle": return [.settings, .orbStyle]
        case "about": return [.settings, .about]
        case "voice": return [.settings, .voiceSettings]
        case "link": return [.link(URL(string: "https://abstractframework.ai")!)]
        case "read": return [.read(ReadItem(title: "Answer", text: MockGatewayClient.cannedAnswer, scope: .run("7c1e02aa")))]
        default: return []
        }
    }
}
