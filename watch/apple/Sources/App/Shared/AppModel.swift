import AbstractGatewayClient
import SwiftUI
import WatchKit

enum Route: Hashable {
    case approval(Wait), askUser(Wait), draft(Wait), waits
    case ask(AskView.Phase), picker, sessions, session(SessionSummary), automations, automation(AutomationSummary), automationEdit(AutomationSummary), settings
    case occurrence(title: String, LastOccurrence)
    case read(ReadItem), link(URL), answer(AnswerRef), orbStyle, about
}

/// App state: one GatewayClient, foreground polling every 15 s for waits and runs.
@MainActor
final class AppModel: ObservableObject {
    @Published var waits: [Wait] = []
    @Published var runs: [RunSummary] = []
    /// Conversations (turns grouped by session), newest activity first.
    var sessions: [SessionSummary] { SessionSummary.group(runs) }
    /// Session titles from each session's first prompt (immutable, so cached per watch).
    @Published private(set) var sessionTitles: [String: String] = (UserDefaults.standard.dictionary(forKey: "session.titles") as? [String: String]) ?? [:]
    /// How many turns the session list reads (Show older adds 100).
    private(set) var runsLimit = 80
    func showOlder() async { runsLimit += 100; await refresh() }
    /// Set by "Continue" on a session: Ask opens on its last exchange, in that session.
    var resuming: (title: String, prompt: String, answer: String, runId: String)?
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
    /// Ask sessions where the person allowed every tool (outreach still asks); kept per watch.
    /// Oldest first; the newest 20 are kept.
    @Published private(set) var trustedSessions: [String] = UserDefaults.standard.stringArray(forKey: "ask.trusted") ?? []
    /// Waits answered from an approval or question screen (Back without deciding is not an answer).
    private(set) var decidedWaits: Set<String> = []
    /// When the last successful refresh happened; nil until the first one.
    @Published var lastRefresh: Date?
    /// The Ask conversation: one gateway session per watch, kept until "New".
    @Published var askSessionId: String = UserDefaults.standard.string(forKey: "ask.session") ?? AppModel.newSessionId()
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
            if tools.isEmpty, let list = try? await client.tools() {
                tools = Dictionary(list.map { ($0.name, $0) }, uniquingKeysWith: { a, _ in a })
            }
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
    /// "Allow all in this session": the current Ask session runs every tool without asking,
    /// except sends to someone else (outreach), which always ask.
    var sessionTrusted: Bool { trustedSessions.contains(askSessionId) }

    func trustSession() {
        trustedSessions.removeAll { $0 == askSessionId }
        trustedSessions.append(askSessionId)
        trustedSessions = Array(trustedSessions.suffix(20))
        UserDefaults.standard.set(trustedSessions, forKey: "ask.trusted")
    }

    func markDecided(_ wait: Wait) { decidedWaits.insert(wait.id) }

    /// A trusted session approves a call itself only when its tier is KNOWN and is not a send:
    /// with the inventory missing it asks, never the reverse.
    func autoApprovable(_ wait: Wait) -> Bool {
        guard sessionTrusted, wait.kind == .toolApproval, let tier = tools[wait.toolName]?.riskTier else { return false }
        return tier != "outreach" && !wait.isOutreach
    }

    /// The run policy for a new Ask run in a trusted session: every tier runs, outreach tools ask.
    var runToolPolicy: RunToolPolicy? {
        guard sessionTrusted, !tools.isEmpty else { return nil }
        let outreach = tools.values.filter { $0.riskTier == "outreach" }.map(\.name).sorted()
        return RunToolPolicy(autoApproveMaxRiskRank: 4, requireApprovalTools: outreach)
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

    func title(of s: SessionSummary) -> String { sessionTitles[s.id] ?? "Conversation" }

    /// Titles the sessions that have none yet from their oldest listed prompt (8 at a time).
    func loadTitles() async {
        let missing = sessions.filter { sessionTitles[$0.id] == nil }.prefix(30)
        guard !missing.isEmpty else { return }
        let found: [(String, String)] = await withTaskGroup(of: (String, String)?.self) { group in
            for s in missing {
                group.addTask { [client] in
                    guard let p = try? await client.prompt(ofRun: s.firstRunId), !p.isEmpty else { return nil }
                    return (s.id, SessionSummary.title(fromPrompt: p))
                }
            }
            var out: [(String, String)] = []
            for await x in group { if let x { out.append(x) } }
            return out
        }
        for (k, v) in found { sessionTitles[k] = v }
        UserDefaults.standard.set(sessionTitles, forKey: "session.titles")
    }

    /// Tap on a session: read its last exchange (two requests together), then open the orb in it.
    func continueSession(_ s: SessionSummary) async {
        async let runCall = try? client.run(id: s.latest.runId)
        async let promptCall = try? client.prompt(ofRun: s.latest.runId)
        let (run, prompt) = await (runCall, promptCall)
        resume(s, lastPrompt: (prompt ?? nil) ?? "", lastAnswer: run?.outputText ?? "")
    }

    /// "Continue": Ask talks in this session from now on, opening on its last exchange.
    func resume(_ s: SessionSummary, lastPrompt: String, lastAnswer: String) {
        askSessionId = s.id
        UserDefaults.standard.set(askSessionId, forKey: "ask.session")
        setResponder(.assistant)
        resuming = (title(of: s), lastPrompt, lastAnswer, s.latest.runId)
        path = [.ask(.idle)]
    }

    func newAskSession() {
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
        model.testRead = testRead
        model.testOpen = testOpen.flatMap(URL.init(string:))
        model.testListen = testListen
        if testListen { return [.ask(.idle)] }
        if !useMock, testAsk != nil { return [.ask(.idle)] }
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
        case "session":
            let s = SessionSummary.group(MockGatewayClient.sampleRuns)[1]
            return [.sessions, .session(s)]
        case "automations": return [.automations]
        case "settings": return [.settings]
        case "orblab", "orbstyle": return [.settings, .orbStyle]
        case "about": return [.settings, .about]
        case "read": return [.read(ReadItem(title: "Answer", text: MockGatewayClient.cannedAnswer, scope: .run("7c1e02aa")))]
        default: return []
        }
    }
}
