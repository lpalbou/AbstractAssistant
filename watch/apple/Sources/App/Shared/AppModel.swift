import AbstractGatewayClient
import SwiftUI
import WatchKit

enum Route: Hashable {
    /// One of the app's own pages, which a swipe forward may open again: Home's lists, a
    /// conversation, an automation, the settings. A page opened from what is on one of them (a
    /// message, its steps, a picture, a link, a choice, a form, a question) opens with a tap only.
    var revisitable: Bool {
        switch self {
        case .ask, .sessions, .session, .automations, .automation, .automationInfo, .automationSearch, .conversation, .settings, .voiceSettings,
             .orbStyle, .about, .tools, .toolGroup, .connection, .archivedSessions, .sessionSearch,
             .archivedAutomations: true
        // `.answer`: a notification's answer (it would be read aloud again); `.waits`: it closes once empty.
        case .approval, .askUser, .draft, .waits, .answer, .picker, .automationEdit, .newAutomation, .message,
             .read, .link, .orbStylePreview, .workflow, .media, .activity, .filePreview: false
        }
    }
    case approval(Wait), askUser(Wait), draft(Wait), waits
    case ask(AskView.Phase), picker, sessions, session(SessionSummary), automations, automation(AutomationSummary), automationEdit(AutomationSummary), newAutomation, message(title: String, Exchange), voiceSettings, settings
    case read(ReadItem), link(URL), answer(AnswerRef), orbStyle, orbStylePreview(String), about, conversation(String)
    case tools(AppModel.ToolScope), toolGroup(AppModel.ToolScope, String), connection
    case workflow(AppModel.ToolScope), media(MediaItem), activity(String), archivedSessions, sessionSearch(String), archivedAutomations
    case filePreview([SessionFile], Int)
    /// An automation's details (behind (i) on its orb page): when it runs, Edit, Run.
    case automationInfo(AutomationSummary)
    /// The automations whose name or task holds these words.
    case automationSearch(String)

    /// A page with the orb that talks (a conversation or an automation): one is on screen at a time.
    var isOrbPage: Bool {
        switch self { case .ask, .answer, .automation: true; default: false }
    }
}

/// App state: one GatewayClient, foreground polling every 15 s for waits and runs.
/// One exchange of a conversation: the question, the answer, and whose voice reads it (the run that
/// answered, or the entity).
struct Exchange: Identifiable, Hashable {
    let id: String
    var prompt: String
    var answer: String
    var scope: SpeechScope?
    /// The images, recordings and videos the turn made (the Assistant's workflow makes them).
    var media: [MediaItem] = []
    /// It ended without an answer (an automation's failed run).
    var failed = false
    /// When its trigger sent it ("today 07:04"): an automation's runs; nil for what you asked.
    var when: String? = nil
}

@MainActor
final class AppModel: ObservableObject {
    /// (The watch face's complication shows how many, and the first: `FaceSnapshot`.)
    @Published var waits: [Wait] = [] { didSet { if waits != oldValue { FaceSnapshot.waits(waits) } } }
    @Published var runs: [RunSummary] = []
    /// Conversations (turns grouped by session), newest activity first.
    var sessions: [SessionSummary] { SessionSummary.group(runs) }

    // MARK: New answers

    /// The latest turn seen of each conversation, on this watch (the gateway keeps no "seen" for
    /// conversations; automations have their own on the gateway).
    @Published private(set) var seenSessions: [String: String] = (UserDefaults.standard.dictionary(forKey: "sessions.seen") as? [String: String]) ?? [:]
    /// Answers before this watch started counting are not new.
    private var seenSince: Date = {
        if let d = UserDefaults.standard.object(forKey: "sessions.seen.since") as? Date { return d }
        let now = Date(); UserDefaults.standard.set(now, forKey: "sessions.seen.since"); return now
    }()

    func isNew(_ s: SessionSummary) -> Bool { s.isNew(seen: seenSessions, since: seenSince) }

    #if DEBUG
    /// `--reset-seen`: every answer counts as new (tests and screenshots).
    func resetSeen() {
        seenSessions = [:]; seenSince = .distantPast
        UserDefaults.standard.removeObject(forKey: "sessions.seen"); UserDefaults.standard.set(Date.distantPast, forKey: "sessions.seen.since")
    }
    #endif
    var newSessionCount: Int { sessions.filter(isNew).count }

    /// This answer has been on screen (the orb showed it, or its conversation was opened).
    func markSeen(session: String, run: String) {
        guard seenSessions[session] != run else { return }
        seenSessions[session] = run
        if seenSessions.count > 400 {                    // the conversations still listed are kept
            let listed = Set(sessions.map(\.id))
            seenSessions = seenSessions.filter { listed.contains($0.key) }
        }
        UserDefaults.standard.set(seenSessions, forKey: "sessions.seen")
    }

    // MARK: Archive

    /// Archives a conversation on the gateway (out of every device's list; nothing is deleted).
    /// The conversation on the orb starts over when it is the one archived.
    func archive(_ s: SessionSummary) async throws {
        try await client.setArchived(sessionId: s.id, true)
        runs.removeAll { ($0.sessionId ?? $0.runId) == s.id }
        if s.id == askSessionId { newAskSession() }
        await refresh()
    }

    /// An automation on or off (`automation.resume` / `automation.pause`): the switch moves at once,
    /// and back if the gateway refuses.
    func setActive(_ a: AutomationSummary, _ on: Bool) async throws {
        var changed = a; changed.status = on ? "active" : "paused"
        replaceAutomation(changed)
        do {
            try await client.automationCommand(id: a.id, type: on ? "automation.resume" : "automation.pause")
            if let fresh = try? await client.automation(id: a.id) { replaceAutomation(fresh) }
        } catch {
            replaceAutomation(a)
            throw error
        }
    }

    /// Archives an automation on the gateway (it stops and leaves the list; nothing is deleted).
    func archiveAutomation(_ a: AutomationSummary) async throws {
        try await client.automationCommand(id: a.id, type: "automation.archive")
        automations.removeAll { $0.id == a.id }
    }

    func unarchiveAutomation(_ id: String) async throws {
        try await client.automationCommand(id: id, type: "automation.unarchive")
        refreshAutomations()
    }

    // MARK: An automation's details, shared by its pages

    /// Each automation's definition (title, task) and latest results, as last read:
    /// its page and Edit show them at once and refresh behind; a save updates them in place.
    @Published private(set) var definitions: [String: AutomationDefinition] = [:]
    @Published private(set) var results: [String: [LastOccurrence]] = [:]
    /// Edits saved here that the gateway may not have applied yet (it applies them in order, a few
    /// seconds later): a list read meanwhile keeps the saved title. Dropped after 2 min.
    private var savedAt: [String: Date] = [:]

    /// The definition: as known when it is at least the list's revision, else read (and kept). A
    /// read under way is shared (Edit opened while its page still reads it waits for that read).
    func definition(of id: String) async throws -> AutomationDefinition {
        let listed = automations.first { $0.id == id }?.revision ?? 0
        if let d = definitions[id], (d.revision ?? 0) >= listed { return d }
        let reading = definitionReads[id] ?? Task { [client] in try await client.automationDefinition(id: id) }
        definitionReads[id] = reading
        defer { definitionReads[id] = nil }
        let read = try await reading.value
        if (read.revision ?? 0) >= (definitions[id]?.revision ?? 0) { definitions[id] = read }
        return definitions[id] ?? read
    }
    private var definitionReads: [String: Task<AutomationDefinition, Error>] = [:]

    /// The latest results read for an automation (newest first).
    func keep(results list: [LastOccurrence], of id: String) { results[id] = list }

    /// A saved edit: the definition, the list's row and the page show it at once.
    func saved(_ d: AutomationDefinition, of id: String) {
        definitions[id] = d; savedAt[id] = Date()
        if let i = automations.firstIndex(where: { $0.id == id }) {
            automations[i].name = d.title; automations[i].revision = d.revision
        }
        refreshAutomations()
    }

    /// The list as read, with any edit saved here in the last 2 min that the gateway has not applied
    /// yet kept as saved (a rejected edit comes back after 2 min, when the list's own values win).
    private func merged(_ list: [AutomationSummary]) -> [AutomationSummary] {
        list.map { row in
            guard let at = savedAt[row.id], Date().timeIntervalSince(at) < 120, let d = definitions[row.id],
                  (row.revision ?? 0) < (d.revision ?? 0) else {
                if let d = definitions[row.id], (d.revision ?? 0) < (row.revision ?? 0) { definitions[row.id] = nil }   // changed elsewhere
                return row
            }
            var kept = row; kept.name = d.title; kept.revision = d.revision
            return kept
        }
    }

    func unarchive(_ sessionId: String) async throws {
        try await client.setArchived(sessionId: sessionId, false)
        await refresh()
    }
    /// Each session's latest question, by its newest run id (the row's title).
    @Published private(set) var latestPrompts: [String: String] = [:]
    /// Latest runs whose question the gateway could not give (the row says so; nothing is made up).
    @Published private(set) var unreadablePrompts: Set<String> = []
    /// How many turns the session list reads (Show older adds 100).
    private(set) var runsLimit = 80
    func showOlder() async { runsLimit += 100; await refresh() }
    /// Set by "Continue" on a session: Ask opens on its last exchange, in that session.
    struct Resuming { let sessionId, title, prompt, answer, runId, status: String; var media: [MediaItem] = [] }
    var resuming: Resuming?
    /// (The watch face's complication shows the next to run and the results not seen.)
    @Published var automations: [AutomationSummary] = [] { didSet { if automations != oldValue { FaceSnapshot.automations(automations) } } }
    @Published var principal: Principal?
    @Published var lastError: String?
    /// Polls that failed in a row, and since when: a watch's radio takes seconds to come up, so the
    /// gateway is said unreachable only after 3 failures spread over 20 s (until then: Connecting).
    @Published private(set) var failures = 0
    private var failingSince: Date?
    @Published private(set) var unreachable = false
    /// No usable sign-in: the sign-in page replaces everything (first launch, Sign out, a session that ended).
    @Published var needsSignIn = false
    /// Why the sign-in page is back, when it is not the first launch.
    @Published var signInNotice: String?
    /// The automations call failed while waits and runs were fine (shown on the Automations screen only).
    @Published var automationsError: String?
    /// The automations have been read once (they arrive after the conversations: their call is the
    /// slow one), so an empty list means none, not "not read yet".
    @Published private(set) var automationsLoaded = false
    /// A read of the automations is under way (with its retries).
    @Published private(set) var automationsLoading = false
    private var automationsTask: Task<Void, Never>?
    /// When the list was last read: it is the gateway's slowest call (each automation's history is
    /// read for it), so the poll reads it at most once a minute; an action reads it at once.
    private var automationsReadAt: Date?
    static let automationsMaxAge: TimeInterval = 60
    /// Which read is current (a read cancelled for a newer one never clears the newer one's state).
    private var automationsGeneration = 0

    /// The list read again now (after an action): a read under way, started before it, is replaced.
    func refreshAutomations() {
        automationsTask?.cancel(); automationsTask = nil
        loadAutomations()
    }

    /// Reads the automations (the client retries a failed read); one read at a time. A read that
    /// fails leaves the error for the Automations page; Home keeps its spinner until the list is in.
    func loadAutomations() {
        guard automationsTask == nil else { return }
        let client = self.client
        automationsGeneration += 1
        let generation = automationsGeneration
        automationsLoading = true
        automationsTask = Task { [weak self] in
            do {
                let list = try await client.automations()
                guard let self, !Task.isCancelled else { return }
                automations = merged(list); automationsError = nil; automationsLoaded = true; automationsReadAt = Date()
                // An automation finished a run since the last look: its notification, shown as a banner
                // with the app in front (Settings → Notifications), unless its own page is on screen.
                let finished = AutomationNotices.finished(in: list)
                if AutomationNotices.on, !client.isMock || UITestHooks.on {
                    for a in finished where !path.contains(where: { if case .automation(let p) = $0 { p.id == a.id } else { false } }) {
                        Task { await AnswerNotifier.shared.postFinished(a) }
                    }
                }
                #if DEBUG
                if let i = testOpenAutomation, i < automations.count {
                    testOpenAutomation = nil
                    path = [.automations, .automation(automations[i])]
                }
                #endif
            } catch {
                guard let self, !Task.isCancelled else { return }
                automationsError = Self.say(error)
            }
            guard let self, self.automationsGeneration == generation else { return }
            self.automationsTask = nil
            self.automationsLoading = false
        }
    }
    /// The conversations have been read once.
    var sessionsLoaded: Bool { lastRefresh != nil }
    /// The pages open, as a browser's history: going back keeps the pages left (`forward`), and a
    /// swipe forward (the finger moving left) opens them again; opening something else forgets them.
    @Published var path: [Route] = [] {
        didSet {
            if forwarding { forwarding = false; return }   // goForward has used up its page itself
            forward = Self.forward(after: oldValue, now: path, kept: forward)
        }
    }
    private var forwarding = false
    /// The last moment a finger moved sideways (a swipe under way, or one that just ended).
    private var swipedAt: Date?
    /// Settings and its pages, a stack of its own that slides in from the left (the gear is at the
    /// left), over the pages (`nil`: closed; `[]`: Settings itself).
    @Published var settingsPath: [Route]?
    /// Settings' stack is in place (it slides in from the left once it exists, and out before it goes).
    @Published var settingsIn = false
    /// Home, with nothing over it: the corner button is the gear.
    var atHome: Bool { path.isEmpty && !settingsIn }
    func openSettings() {
        guard settingsPath == nil else { return }
        forward = []                                      // opening something else forgets the pages ahead
        settingsPath = []
        Task { @MainActor in withAnimation(.easeInOut(duration: Self.settingsSlide)) { settingsIn = true } }   // once it exists, off screen
    }
    func closeSettings() {
        withAnimation(.easeInOut(duration: Self.settingsSlide)) { settingsIn = false }
        Task { @MainActor in
            try? await Task.sleep(for: .seconds(Self.settingsSlide))
            if !settingsIn { settingsPath = nil }
        }
    }
    /// How long Settings takes to slide in or out.
    static let settingsSlide: Double = 0.3
    /// Opens a page on top of whatever is open (Settings' stack while it is); a row under a swiping
    /// finger opens nothing.
    func push(_ route: Route) {
        if let t = swipedAt, Date().timeIntervalSince(t) < 0.4 { return }
        if settingsPath != nil { settingsPath?.append(route) } else { path.append(route) }
    }
    /// Closes the page on top of whatever is open (`n` pages).
    func pop(_ n: Int = 1) {
        if settingsPath != nil { settingsPath?.removeLast(min(n, settingsPath?.count ?? 0)) }
        else { path.removeLast(min(n, path.count)) }
    }
    /// The page on top of whatever is open.
    var activeTop: Route? { settingsPath != nil ? settingsPath?.last : path.last }
    /// Shows these pages (a notification's, a launch option's), closing Settings if open; pages
    /// starting at Settings open in its stack.
    func show(_ routes: [Route]) {
        if routes.first == .settings { path = []; settingsPath = Array(routes.dropFirst()); settingsIn = true }
        else { settingsIn = false; settingsPath = nil; path = routes }
    }

    /// The navigation stack's changes (a tapped link, the system's Back): a row under a swiping
    /// finger opens nothing, only the swipe moves the history.
    var stackPath: Binding<[Route]> {
        Binding(get: { self.path }, set: { new in
            if new.count > self.path.count, let t = self.swipedAt, Date().timeIntervalSince(t) < 0.4 {
                self.objectWillChange.send(); return       // the stack redraws the path as it is
            }
            self.path = new
        })
    }
    /// The pages a swipe forward opens again, the next one last.
    private(set) var forward: [Route] = []
    /// The Assistant's conversations known to have a message, each with its newest run (only ever
    /// added to: a conversation that has had one keeps it), so that its orb page offers its stats
    /// page whichever page appeared last, before the next poll lists it.
    private var conversationsWithMessages: [String: String?] = [:]
    func noteMessages(in sessionId: String, runId: String?) {
        if let runId { conversationsWithMessages[sessionId] = runId }
        else if conversationsWithMessages[sessionId] == nil { conversationsWithMessages[sessionId] = .some(nil) }
    }
    func hasMessages(_ sessionId: String) -> Bool {
        conversationsWithMessages[sessionId] != nil || (sessions.first { $0.id == sessionId }?.turns ?? 0) > 0
    }
    /// A run of the conversation (its folder is read through it): the newest seen on this watch, else
    /// the listing's.
    func anyRun(of sessionId: String) -> String? {
        conversationsWithMessages[sessionId].flatMap { $0 } ?? sessions.first { $0.id == sessionId }?.latest.runId
            ?? runs.first { $0.sessionId == sessionId }?.runId
    }

    /// A page with something unsaved (a form with changes) asks before a swipe back closes it.
    private var backGuard: (route: Route, ask: () -> Void)?
    func guardBack(of route: Route, _ ask: (() -> Void)?) {
        if let ask { backGuard = (route, ask) } else if backGuard?.route == route { backGuard = nil }
    }
    /// A picture being zoomed into: its pan is not a swipe.
    var swipesPaused = false

    /// Swipe back (the finger moving right): the page before. Home is the first page: nothing is
    /// before it.
    func goBack() {
        if let sp = settingsPath {
            if let top = sp.last {
                if let g = backGuard, g.route == top { g.ask(); return }
                settingsPath?.removeLast()
            } else { closeSettings() }
            return
        }
        guard let top = path.last else { return }
        if let g = backGuard, g.route == top { g.ask(); return }
        path.removeLast()
    }

    /// Swipe forward (the finger moving left): on the Assistant's orb page, the conversation's stats
    /// page and only that (once it has a message); elsewhere the page went back from. Nothing ahead:
    /// nothing happens.
    func goForward() {
        guard settingsPath == nil else { return }
        switch path.last {
        case .automation(let a) where forward.isEmpty:
            forwarding = true
            // Gone on as a conversation about it: that conversation's page; else its details (as a
            // conversation's: its stats page).
            if let d = discussion, d.automation == a.id, d.session == askSessionId { path.append(.conversation(askSessionId)) }
            else { path.append(.automationInfo(a)) }
        case .ask:
            guard responder == .assistant, hasMessages(askSessionId) else { return }
            forwarding = true; forward = []
            path.append(.conversation(askSessionId))
        default:
            guard let next = forward.last else { return }
            forwarding = true; forward.removeLast()
            path.append(next)
        }
    }

    /// The finger moves sideways: until 0.4 s after it last did, a button under it opens nothing (a
    /// button fires when the finger lifts on it, and a swipe across a full-width row ends on it).
    func swiped() { swipedAt = Date() }

    /// How `forward` follows a change of the path other than a swipe forward: back (a shorter path,
    /// the same start) keeps the pages left, the app's own pages only (`Route.revisitable`), and none
    /// above a page that opens with a tap only; anything opened, by a tap or otherwise, forgets them,
    /// as in a browser.
    nonisolated static func forward(after old: [Route], now new: [Route], kept: [Route]) -> [Route] {
        if new.count < old.count, Array(old.prefix(new.count)) == new {
            let left = Array(old[new.count...])
            if left.allSatisfy(\.revisitable) { return kept + left.reversed() }
            return Array(left.prefix { $0.revisitable }.reversed())
        }
        return new == old ? kept : []
    }
    @Published var entities: [EntitySummary] = []
    /// The gateway's tools by name, with their risk tier (observe · act · outreach · destroy).
    @Published var tools: [String: ToolInfo] = [:]
    /// Tool choices (ToolPrefs): defaults for new conversations, and this conversation's changes.
    @Published private(set) var toolDefaults: [String: ToolMode] = ToolPrefs.defaults
    @Published private(set) var sessionTools: [String: ToolMode] = [:]
    /// The tools of the automation being created (its changes on top of the defaults).
    @Published private(set) var draftTools: [String: ToolMode] = [:]
    /// Waits answered from an approval or question screen (Back without deciding is not an answer).
    private(set) var decidedWaits: Set<String> = []
    /// When the last successful refresh happened; nil until the first one.
    @Published var lastRefresh: Date?
    /// The Ask conversation: one gateway session per watch, kept until "New".
    @Published var askSessionId: String = UserDefaults.standard.string(forKey: "ask.session") ?? AppModel.newSessionId() {
        didSet {
            sessionTools = ToolPrefs.session(askSessionId); ToolPrefs.touch(askSessionId)
            sessionWorkflow = WorkflowPrefs.session(askSessionId)
            sessionTrust = ToolPrefs.trust(askSessionId)
        }
    }
    /// Who answers an Ask; kept per watch in UserDefaults.
    @Published private(set) var responder = Responder(storageKey: UserDefaults.standard.string(forKey: "ask.responder"))
    /// Open entity conversations, one per home (`chat/open` is "one live session per home").
    private var entityChats: [String: String] = [:]

    @Published private(set) var client: any GatewayClient
    @Published private(set) var gatewayHost: String
    private var seenWaitIDs: Set<String> = []
    private var pollTask: Task<Void, Never>?
    private var approvalPollTask: Task<Void, Never>?
    private var approvalRevision = 0
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
    /// After a failed poll, until the gateway is said unreachable.
    static let retryInterval: Duration = .seconds(3)

    init(client: any GatewayClient, gatewayHost: String) {
        self.client = client; self.gatewayHost = gatewayHost
        if UserDefaults.standard.string(forKey: "ask.session") == nil { UserDefaults.standard.set(askSessionId, forKey: "ask.session") }
        sessionTools = ToolPrefs.session(askSessionId)
        sessionWorkflow = WorkflowPrefs.session(askSessionId)
        sessionTrust = ToolPrefs.trust(askSessionId)
        UserDefaults.standard.removeObject(forKey: "ask.trusted")   // the first "Accept all" store, unused
    }

    var connected: Bool { principal != nil }
    /// First poll still in flight: no answer yet, but no failure either.
    var connecting: Bool { principal == nil && !unreachable && (failures > 0 || !client.isMock) }

    func startPolling() {
        guard pollTask == nil, !needsSignIn else { return }
        approvalPollTask?.cancel()
        approvalPollTask = Task { [weak self] in
            while !Task.isCancelled {
                guard let self, self.onScreen, !self.needsSignIn else { return }
                let pending = Dictionary(grouping: self.waits, by: \.runId)
                for (id, known) in pending {
                    do {
                        let run = try await self.client.run(id: id)
                        guard !Task.isCancelled else { return }
                        let current = run.isTerminal ? nil : run.personWait?.id
                        let removed = Set(known.filter { $0.id != current }.map(\.id))
                        if !removed.isEmpty {
                            self.approvalRevision += 1
                            self.waits.removeAll { removed.contains($0.id) }
                        }
                    } catch GatewayError.unauthorized {
                        guard !Task.isCancelled else { return }
                        self.signOut(notice: "You were signed out. Please sign in again."); return
                    } catch { /* Keep the approval visible until the server confirms resolution. */ }
                }
                do { try await Task.sleep(for: .seconds(1)) } catch { return }
            }
        }
        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                guard let self else { return }
                let keepGoing = await self.refresh()
                if !keepGoing { break }
                // The screen dimmed (wrist down, always on): this poll ends, no next one. A poll in
                // flight is never cut (a first one takes 10-15 s over the watch's radio).
                guard self.onScreen, !Task.isCancelled else { break }
                try? await Task.sleep(for: self.failures > 0 && !self.unreachable ? Self.retryInterval : Self.pollInterval)
            }
            self?.pollTask = nil
        }
    }

    func stopPolling() { pollTask?.cancel(); pollTask = nil; approvalPollTask?.cancel(); approvalPollTask = nil }

    /// Someone is looking at the screen (the scene is active): polls go on; otherwise the running
    /// one finishes and none follows.
    private(set) var onScreen = false

    /// The scene's phase: active polls; inactive (dimmed, wrist down) lets the poll in flight finish
    /// and stops there; background stops at once.
    func scene(_ phase: ScenePhase) {
        switch phase {
        case .active: onScreen = true; startPolling()
        case .inactive: onScreen = false
        case .background: onScreen = false; stopPolling()
        @unknown default: onScreen = false
        }
    }

    /// Signed in (the sign-in page): saves it, remembers the gateway, replaces the client, clears
    /// the cached state, polls. A sign-in kept for this user on this gateway with another
    /// credential is forgotten: the new one replaces it.
    func connect(_ signIn: SavedSignIn) {
        signIn.save()                                    // into the Keychain, with a new push handle
        // Push (backlog 1049): the token is registered with this sign-in's handle; the one-time
        // permission question comes now, as a closed app's alerts need it.
        WatchPush.start()
        AnswerNotifier.shared.requestPermission()
        GatewayBook.touch(signIn.gateway)
        if let user = signIn.user, let kept = GatewayBook.account(on: signIn.gateway, user: user),
           kept.signIn?.credential != signIn.credential {
            GatewayBook.forget(gateway: signIn.gateway, user: user)
        }
        stopPolling()
        client = LiveGatewayClient(baseURL: signIn.gateway, credential: signIn.credential)
        gatewayHost = signIn.gateway.host() ?? signIn.gateway.absoluteString
        waits = []; runs = []; automations = []; principal = nil; lastError = nil; failures = 0; failingSince = nil; unreachable = false; seenWaitIDs = []; entities = []; automationsLoaded = false; automationsError = nil; automationsTask?.cancel(); automationsTask = nil; automationsLoading = false; automationsReadAt = nil
        definitions = [:]; results = [:]; savedAt = [:]
        forgetTools()                                    // each account has its own tools (email, …)
        workflows = []; workflowsReadAt = nil; MediaStore.shared.clear()
        needsSignIn = false; signInNotice = nil; path = []; forward = []
        startPolling()
    }

    /// Forgets the credential (the gateway address stays as the next default) and shows the sign-in
    /// page; the watch stays signed out, across launches, until someone signs in on it. `keep`: the
    /// account is kept first on its gateway (`GatewayBook`), for a one-tap return from the sign-in
    /// page. Otherwise an account kept for this user on this gateway is forgotten with it: "Sign out
    /// and forget", or the gateway rejecting the credential (a 401), so its row does not come back.
    func signOut(keep: Bool = false, notice: String? = nil) {
        var notice = notice
        // The person signing out: the gateway forgets this watch's push token. A credential the
        // gateway rejected (401, `notice`) sends nothing more (it locks out an address after failures).
        if notice == nil { WatchPush.signedOut(SavedSignIn.current()) }
        if let current = SavedSignIn.load() {
            // The gateway stays in the chooser, whatever signed the watch in there (a launch
            // argument, a build before the chooser).
            GatewayBook.touch(current.gateway)
            if let user = current.user ?? principal?.userId {
                if keep {
                    do { try GatewayBook.keep(current, user: user) }
                    catch { notice = "Your sign-in could not be kept on this watch." }
                } else {
                    GatewayBook.forget(gateway: current.gateway, user: user)
                }
            }
        }
        // Forgotten by hand: the name goes too (the field would offer it again).
        if !keep && notice == nil { UserDefaults.standard.removeObject(forKey: "gateway.user") }
        if !SavedSignIn.clear() { notice = "The sign-in could not be removed from this watch's Keychain." }
        stopPolling()
        client = MockGatewayClient(world: .watch); gatewayHost = "—"
        waits = []; runs = []; automations = []; principal = nil; lastError = nil; failures = 0; failingSince = nil; unreachable = false; seenWaitIDs = []; entities = []; automationsLoaded = false; automationsError = nil; automationsTask?.cancel(); automationsTask = nil; automationsLoading = false; automationsReadAt = nil
        definitions = [:]; results = [:]; savedAt = [:]
        forgetTools()
        workflows = []; workflowsReadAt = nil; MediaStore.shared.clear()
        path = []; forward = []; signInNotice = notice; needsSignIn = true
    }

    /// A fresher row for one automation (its page knows first that it runs or has finished).
    func replaceAutomation(_ a: AutomationSummary) {
        if let i = automations.firstIndex(where: { $0.id == a.id }) { automations[i] = a }
    }

    /// A run that Run on an automation's details saw the gateway start (or already finish), handed to
    /// its orb page, which follows it at once instead of finding it again; `since`: the tap.
    struct StartedRun: Equatable { let runId: String; let since: Date }
    /// By automation id; the orb page takes it (once) when it is back in front.
    var startedRuns: [String: StartedRun] = [:]

    /// Returns false when polling must stop (401: the gateway locks out by address).
    @discardableResult
    func refresh() async -> Bool {
        let approvals = approvalRevision
        do {
            // The three first-poll calls go out together: on the watch's radio each round trip
            // costs seconds, and nothing on Home can be drawn before all three are back.
            async let waitsCall = client.waits()
            async let runsCall = client.recentRuns(limit: runsLimit)
            if principal == nil { principal = try await client.me() }
            let newWaits = await approveTrusted(try await waitsCall)
            if newWaits.contains(where: { !seenWaitIDs.contains($0.id) }) {
                WKInterfaceDevice.current().play(.notification)
            }
            seenWaitIDs.formUnion(newWaits.map(\.id))
            if approvals == approvalRevision { waits = newWaits }
            runs = try await runsCall
            // The fast part is on screen now. Automations is the slow call on a public gateway
            // (~7 s measured) and its own failure never marks the gateway offline.
            lastError = nil; failures = 0; failingSince = nil; unreachable = false
            lastRefresh = Date()
            if let text = testRead, let run = runs.first {
                testRead = nil
                path = [.read(ReadItem(title: "Read", text: text, scope: .run(run.runId)))]
            }
            // The automations (the slow call) load on their own, so the titles below never wait for them,
            // and at most once a minute.
            if automationsReadAt.map({ Date().timeIntervalSince($0) > Self.automationsMaxAge }) ?? true { loadAutomations() }
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
            failures += 1
            let since = failingSince ?? Date()
            failingSince = since
            unreachable = failures >= 3 && Date().timeIntervalSince(since) >= 20
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
    // MARK: Decisions (a conversation or an automation, each with its own tools)

    /// Who a wait is for: the conversation or automation its run belongs to (the gateway says);
    /// without that, the conversation on screen when it was opened from its orb page.
    func owner(of wait: Wait) -> WaitOwner? { wait.owner ?? (approvalFromAsk ? .session(askSessionId) : nil) }

    /// How an owner runs a tool: a conversation with the watch's choices (the defaults and its own
    /// changes); an automation with its own (as it was created: offered, unasked, asked first).
    /// Nil while an automation's definition is not read.
    func mode(of tool: ToolInfo, for owner: WaitOwner) -> ToolMode? {
        switch owner {
        case .session(let id):
            return ToolChoices.mode(of: tool, defaults: toolDefaults, session: id == askSessionId ? sessionTools : ToolPrefs.session(id))
        case .automation(let id):
            guard let d = definitions[id] else { return nil }
            let p = d.toolPolicy
            if p.auto.contains(tool.name) { return .auto }
            if p.ask.contains(tool.name) { return .ask }
            if let offered = p.offered, !offered.contains(tool.name) { return .off }
            return ToolChoices.gatewayDefault(tool)                  // the workflow's own: as the gateway asks
        }
    }

    /// The tools an Approve all allowed for an owner (the watch approves them for you).
    func trust(_ owner: WaitOwner) -> Set<String> {
        if case .session(let id) = owner, id == askSessionId { return sessionTrust }
        return ToolPrefs.trust(owner.key)
    }
    private func setTrust(_ owner: WaitOwner, _ names: Set<String>) {
        ToolPrefs.setTrust(owner.key, names)
        if case .session(let id) = owner, id == askSessionId { sessionTrust = names }
        trustChanged += 1
    }
    /// Bumped when an owner's trust changes (pages showing it read it again).
    @Published private(set) var trustChanged = 0

    /// Approve all can be offered: a tool call, of a known owner whose tools are known, not a send.
    func canTrust(_ wait: Wait) -> Bool {
        guard wait.kind == .toolApproval, !isOutreach(wait), let owner = owner(of: wait) else { return false }
        return wait.details?.allSatisfy { c in tools[c.name].map { mode(of: $0, for: owner) != nil } ?? false } ?? false
    }

    /// Approve all: the owner's tools on Ask, up to the risk of the call approved, are approved by
    /// the watch from now on, for that owner only (a conversation, or an automation's runs). They
    /// stay on Ask for the gateway (a run's permissions are fixed when it starts), so "Ask again"
    /// takes them back at once, from the very next call. Sends to other people always ask.
    func trustAll(approving wait: Wait) {
        guard let owner = owner(of: wait) else { return }
        let approved = (wait.details ?? []).map { tools[$0.name]?.riskRank ?? 4 }.max() ?? 4
        let ceiling = max(ToolChoices.allAutoMaxRank, approved)
        let rise = tools.values.filter { t in
            mode(of: t, for: owner) == .ask && t.riskTier != "outreach" && t.modelControlledDestination != true
                && (t.riskRank ?? 4) <= ceiling
        }
        // The tools of the call approved are allowed too, whatever they are, but sends to other
        // people: the person saw them and chose to allow them all (a web page that keeps asking
        // after Approve all on a web page reads as a broken button).
        let shown = (wait.details ?? []).compactMap { tools[$0.name] }.filter { $0.riskTier != "outreach" }
        setTrust(owner, trust(owner).union(rise.map(\.name) + shown.map(\.name)))
    }

    /// The tools Approve all allowed in the current conversation (its shield, its Tools page).
    @Published private(set) var sessionTrust: Set<String> = []

    /// They ask again, from the next call (also in the run working now).
    func revokeTrust(_ owner: WaitOwner? = nil) { setTrust(owner ?? .session(askSessionId), []) }

    /// The work of answers followed on this watch, by run (an answer card opens it).
    @Published var activities: [String: FinishedWork] = [:]
    func keep(_ work: FinishedWork, for runId: String) {
        activities[runId] = work
        if activities.count > 40, let oldest = activities.min(by: { $0.value.ended < $1.value.ended })?.key { activities[oldest] = nil }
    }

    func markDecided(_ wait: Wait) { decidedWaits.insert(wait.id) }

    /// The watch approves a call itself only when every call in it is a known tool its owner (the
    /// conversation or the automation) runs without asking, or one Approve all allowed for that owner
    /// and that is not Off. Never for a wait whose owner is not known.
    func autoApprovable(_ wait: Wait) -> Bool {
        guard wait.kind == .toolApproval, let owner = wait.owner, let calls = wait.details, !calls.isEmpty else { return false }
        let allowed = trust(owner)
        // The runtime asks for a batch as a whole: every call in it must be allowed.
        return calls.allSatisfy { c in
            guard let t = tools[c.name], let mode = mode(of: t, for: owner) else { return false }
            return mode == .auto || (mode == .ask && allowed.contains(c.name))
        }
    }

    /// The one way the watch approves for the person (the orb page following its run, and the
    /// poll): once, whoever sees the wait first; an approval already on its way counts as given.
    /// `byDefaults`: also what the owner runs unasked (only for a run this watch follows).
    func approveIfAllowed(_ wait: Wait, byDefaults: Bool) async -> Bool {
        if decidedWaits.contains(wait.id) || approving.contains(wait.id) { return true }
        guard byDefaults ? autoApprovable(wait) : allowedByApproveAll(wait) else { return false }
        approving.insert(wait.id)
        defer { approving.remove(wait.id) }
        if await answer(wait, with: .approve) { markDecided(wait); return true }
        return decidedWaits.contains(wait.id)
    }
    private var approving: Set<String> = []

    /// Every call of the wait is one the person allowed for its owner with Approve all (and that the
    /// owner still offers). Unlike `autoApprovable`, the watch's own defaults play no part: this is
    /// what the poll answers, for runs of any client.
    func allowedByApproveAll(_ wait: Wait) -> Bool {
        guard wait.kind == .toolApproval, let owner = wait.owner, let calls = wait.details, !calls.isEmpty else { return false }
        let allowed = trust(owner)
        return calls.allSatisfy { c in
            guard allowed.contains(c.name), let t = tools[c.name], let mode = mode(of: t, for: owner) else { return false }
            return mode != .off
        }
    }

    /// The waits an Approve all covers, answered by the watch as they come (seen by the poll,
    /// whatever page is open): the rest stay for the person. Only what was explicitly allowed for
    /// that owner: a conversation of another device never gets the watch's defaults.
    private func approveTrusted(_ found: [Wait]) async -> [Wait] {
        var left: [Wait] = []
        for w in found {
            if case .automation(let id)? = w.owner, definitions[id] == nil, !ToolPrefs.trust(w.owner!.key).isEmpty {
                _ = try? await definition(of: id)                    // its own tools, to decide by them
            }
            if await approveIfAllowed(w, byDefaults: false) == false { left.append(w) }
        }
        return left
    }

    // MARK: Tools

    /// Where a tool choice applies: the defaults, this conversation, or the automation being created.
    enum ToolScope: Hashable { case defaults, session, draft }

    /// The choices a scope adds on top of the defaults.
    func toolChanges(_ scope: ToolScope) -> [String: ToolMode] {
        switch scope { case .defaults: [:]; case .session: sessionTools; case .draft: draftTools }
    }

    func toolMode(_ tool: ToolInfo, scope: ToolScope) -> ToolMode {
        ToolChoices.mode(of: tool, defaults: toolDefaults, session: toolChanges(scope))
    }

    /// Sets tools' modes in a scope. A default is kept as chosen (the gateway changing its own never
    /// moves it; "Use the gateway's" forgets them); a conversation keeps only what differs from the
    /// defaults, so a later default still reaches it.
    func setTools(_ names: [String], _ mode: ToolMode, scope: ToolScope) {
        switch scope {
        case .defaults:
            var d = toolDefaults
            for n in names where tools[n] != nil { d[n] = mode }
            toolDefaults = d
            ToolPrefs.defaults = d
        case .session, .draft:
            var m = toolChanges(scope)
            for n in names {
                guard let t = tools[n] else { continue }
                m[n] = mode == ToolChoices.mode(of: t, defaults: toolDefaults, session: [:]) ? nil : mode
            }
            if scope == .session {
                setSessionTools(m)
                // A tool turned Off (or set by hand) is no longer one Accept all allowed.
                if !sessionTrust.isDisjoint(with: names) { sessionTrust.subtract(names); ToolPrefs.setTrust(askSessionId, sessionTrust) }
            } else { draftTools = m }
        }
    }

    /// A new automation starts from the defaults.
    func startDraftTools() { draftTools = [:] }
    func resetTools(_ scope: ToolScope) {
        switch scope { case .defaults: resetToolDefaults(); case .session: resetSessionTools(); case .draft: draftTools = [:] }
    }

    /// What a scope's runs receive (nil until the catalog is read).
    func toolPlan(_ scope: ToolScope) -> ToolChoices.Plan? {
        guard !tools.isEmpty else { return nil }
        return ToolChoices.plan(Array(tools.values), defaults: toolDefaults, session: toolChanges(scope))
    }

    private func setSessionTools(_ modes: [String: ToolMode]) {
        sessionTools = modes
        ToolPrefs.setSession(askSessionId, modes)
    }

    /// This conversation uses the defaults again: its tools and its workflow.
    func resetSessionTools() {
        setSessionTools([:])
        sessionWorkflow = nil; WorkflowPrefs.setSession(askSessionId, nil)
    }
    /// This conversation differs from the defaults (its tools or its workflow).
    var sessionDiffers: Bool { !sessionTools.isEmpty || sessionWorkflow != nil }

    /// The defaults follow the gateway again.
    func resetToolDefaults() { toolDefaults = [:]; ToolPrefs.defaults = [:] }

    #if DEBUG
    func reloadToolPrefs() {
        toolDefaults = ToolPrefs.defaults; sessionTools = ToolPrefs.session(askSessionId)
        workflowDefault = WorkflowPrefs.defaultPick; sessionWorkflow = WorkflowPrefs.session(askSessionId)
        sessionTrust = ToolPrefs.trust(askSessionId)
    }
    #endif

    /// What this conversation's next run receives (nil until the catalog is read).
    var toolPlan: ToolChoices.Plan? { toolPlan(.session) }

    // MARK: Workflow

    /// The workflows a conversation can run (the agents', then the Assistant's), read from the gateway.
    @Published private(set) var workflows: [WorkflowChoice] = []
    private var workflowsReadAt: Date?
    /// The workflow for new conversations (Settings → Tools), and this conversation's own choice.
    @Published private(set) var workflowDefault: WorkflowPick = WorkflowPrefs.defaultPick
    @Published private(set) var sessionWorkflow: WorkflowPick?

    func ensureWorkflows(maxAge: TimeInterval = .infinity) async {
        if !workflows.isEmpty, let read = workflowsReadAt, Date().timeIntervalSince(read) < maxAge { return }
        guard let list = try? await client.conversationWorkflows() else { return }
        workflows = list
        workflowsReadAt = Date()
    }

    /// The workflow a scope runs: this conversation's choice, else the one its earlier turns ran
    /// (a conversation started on another device keeps its workflow), else the default.
    func workflowPick(_ scope: ToolScope) -> WorkflowPick {
        guard scope == .session else { return workflowDefault }
        if let pick = sessionWorkflow { return pick }
        if let bundle = inheritedBundle, let w = workflows.first(where: { $0.bundleId == bundle }) {
            return w.isDefault ? .gatewayDefault : WorkflowPick(w)
        }
        return workflowDefault
    }

    /// The bundle this conversation's latest turn ran (any device), when no choice was made here.
    private var inheritedBundle: String? { sessionWorkflow == nil ? ranBundle : nil }
    /// The bundle this conversation's latest turn ran (any device), whatever was chosen here.
    private var ranBundle: String? {
        let latest = runs.filter { $0.sessionId == askSessionId }.max { ($0.createdAt ?? "") < ($1.createdAt ?? "") }
        return latest?.workflowId.flatMap(WorkflowChoice.bundleId(ofRunWorkflow:))
    }

    func setWorkflow(_ pick: WorkflowPick, scope: ToolScope) {
        switch scope {
        case .defaults: workflowDefault = pick; WorkflowPrefs.defaultPick = pick
        // The default picked again: the conversation follows the default (a later change reaches it).
        case .session:
            // (One its earlier turns inherited stays explicit: nil would bring the inherited one back.)
            // The workflow it would run anyway (the one it ran, else the default): nothing to keep.
            let ran = ranBundle.flatMap { b in workflows.first { $0.bundleId == b } }.map { $0.isDefault ? WorkflowPick.gatewayDefault : WorkflowPick($0) }
            let own: WorkflowPick? = pick == (ran ?? workflowDefault) ? nil : pick
            sessionWorkflow = own; WorkflowPrefs.setSession(askSessionId, own)
        case .draft: break
        }
    }

    /// The listed workflow a pick runs (nil for the gateway's default agent, or when not listed).
    func workflowChoice(_ pick: WorkflowPick) -> WorkflowChoice? {
        if pick.isGatewayDefault { return workflows.first(where: \.isDefault) }
        return workflows.first { $0.bundleId == pick.bundleId && $0.interface == pick.interface }
    }

    /// The name of the workflow a scope runs ("Basic agent"); nil until the list is read.
    func workflowName(_ scope: ToolScope) -> String? {
        let pick = workflowPick(scope)
        return workflowChoice(pick)?.name ?? (pick.isGatewayDefault && !workflows.isEmpty ? "Gateway default" : nil)
    }

    enum WorkflowProblem: LocalizedError {
        case unreadable, gone
        var errorDescription: String? {
            switch self {
            case .unreadable: "Couldn't read your workflows. Try again."
            case .gone: "That workflow is no longer on your gateway. Choose another in Tools."
            }
        }
    }

    /// What this conversation's next question starts: nil for the gateway's default agent; a
    /// chosen workflow at its newest version. A chosen workflow the gateway no longer has fails the
    /// question (it never quietly runs another one).
    func runWorkflow() async throws -> WorkflowChoice? {
        let inherited = inheritedBundle
        // The list is needed to run a chosen workflow, and to know which one earlier turns ran.
        if inherited != nil || !workflowPick(.session).isGatewayDefault {
            await ensureWorkflows(maxAge: 600)
            if workflows.isEmpty { throw WorkflowProblem.unreadable }
        }
        if let inherited, !workflows.contains(where: { $0.bundleId == inherited }) { throw WorkflowProblem.gone }
        let pick = workflowPick(.session)
        if pick.isGatewayDefault { return nil }
        guard let w = workflowChoice(pick) else { throw WorkflowProblem.gone }
        return w
    }


    /// The tool's risk tier from the gateway's inventory (the wait payload carries none).
    func tier(of wait: Wait) -> String? { tools[wait.toolName]?.riskTier ?? wait.riskTier }
    func isOutreach(_ wait: Wait) -> Bool { tier(of: wait) == "outreach" || wait.isOutreach }
    func isDestructive(_ wait: Wait) -> Bool { tier(of: wait) == "destroy" || wait.isDestructive }

    /// Opened from Ask (the orb is underneath): answering returns to it.
    var approvalFromAsk: Bool {
        guard path.count >= 2 else { return false }
        switch path[path.count - 2] {
        case .ask, .answer: return true
        // An automation's page only once it goes on as a conversation (its trust is that conversation's).
        case .automation(let a): return discussion?.automation == a.id && discussion?.session == askSessionId
        default: return false
        }
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

    private func forgetTools() { tools = [:]; toolsReadAt = nil }


    /// A conversation's label: its latest question, as the gateway has it (a watch conversation runs
    /// for days; its first question says little about it). Nil until read: never a made-up title.
    func title(of s: SessionSummary) -> String? { latestPrompts[s.latest.runId] }

    /// Reads each listed conversation's latest question (a new turn has a new run id: read again).
    func loadTitles() async {
        // Never read again what has no readable question (it used to be fetched on every poll).
        let missing = sessions.filter { latestPrompts[$0.latest.runId] == nil && !unreadablePrompts.contains($0.latest.runId) }.prefix(40)
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
    /// `--test-session-id <id>`: the conversation the test names (so it can archive it when done).
    func useTestSession() {
        let args = ProcessInfo.processInfo.arguments
        if let i = args.firstIndex(of: "--test-session-id"), i + 1 < args.count { askSessionId = args[i + 1]; return }
        askSessionId = "watch-test-" + UUID().uuidString.lowercased()
    }
    #endif

    /// A session's last exchange: its newest turn's question, answer, state and media (two requests together).
    func lastExchange(of s: SessionSummary) async -> (prompt: String, answer: String, runId: String, status: String, media: [MediaItem]) {
        async let runCall = try? client.run(id: s.latest.runId)
        async let promptCall = try? client.prompt(ofRun: s.latest.runId)
        let (run, prompt) = await (runCall, promptCall)
        return ((prompt ?? nil) ?? "", run?.outputText ?? "", s.latest.runId, run?.status ?? s.latest.status,
                MediaItem.of(output: run?.output, runId: s.latest.runId))
    }

    /// A conversation known by its id only (a search result): its turns, then as a tap on its row.
    func openSession(id: String) async throws {
        let rows = try await client.turns(ofSession: id, limit: 100)
        guard let s = SessionSummary.group(rows).first else { throw GatewayError.http(status: 404, body: "") }
        await continueSession(s)
    }

    /// Tap on a session: read its last exchange, then open the orb in it.
    func continueSession(_ s: SessionSummary) async {
        let last = await lastExchange(of: s)
        resume(s, lastPrompt: last.prompt, lastAnswer: last.answer, runId: last.runId, status: last.status, media: last.media)
    }

    /// "Continue": Ask talks in this session from now on, opening on its last exchange (`runId`:
    /// the exchange shown, when the caller read a fresher one than the listing's).
    func resume(_ s: SessionSummary, lastPrompt: String, lastAnswer: String, runId: String? = nil, status: String? = nil,
                media: [MediaItem] = []) {
        resuming = Resuming(sessionId: s.id, title: title(of: s) ?? "", prompt: lastPrompt, answer: lastAnswer,
                            runId: runId ?? s.latest.runId, status: status ?? s.latest.status, media: media)
        askSessionId = s.id
        UserDefaults.standard.set(askSessionId, forKey: "ask.session")
        setResponder(.assistant)
        openOrb()
    }

    /// The orb page, opened on top of the page it is opened from (Back returns there, as in a
    /// browser). An orb page already open further down is closed first: there is one conversation.
    func openOrb() {
        if let i = path.firstIndex(where: { if case .ask = $0 { true } else if case .answer = $0 { true } else { false } }) {
            path.removeSubrange(i...)
        }
        path.append(.ask(.idle))
    }

    /// The page on screen moves into this conversation (a notification's answer, or a
    /// conversation about the automation `about`): the current one from now on, answered by the
    /// Assistant (who answers new conversations stays as chosen).
    func adopt(_ sessionId: String, about automation: String? = nil) {
        resuming = nil
        askSessionId = sessionId
        UserDefaults.standard.set(askSessionId, forKey: "ask.session")
        setResponder(.assistant, persist: false)
        if let automation { discussion = (automation, sessionId) }
    }
    /// The conversation an automation's orb page went on as (its forward swipe opens that
    /// conversation's page, as a conversation's does).
    private(set) var discussion: (automation: String, session: String)?

    /// The automation an occurrence's run belongs to (the gateway says which; read when not listed).
    func automation(of run: RunSummary) async -> AutomationSummary? {
        guard let id = run.automationId else { return nil }
        if let known = automations.first(where: { $0.id == id }) { return known }
        return try? await client.automation(id: id)
    }

    /// An automation's page, from a notification (read when not listed yet).
    func openAutomation(id: String) {
        if let a = automations.first(where: { $0.id == id }) { show([.automation(a)]); return }
        Task { if let a = try? await client.automation(id: id) { show([.automation(a)]) } }
    }

    func newAskSession() {
        resuming = nil                                   // a pending Continue never lands in a new conversation
        entityChats = [:]                                // an entity's new conversation is new too
        askSessionId = Self.newSessionId()
        UserDefaults.standard.set(askSessionId, forKey: "ask.session")
    }
    /// "updated 12 s ago" / "offline for 3 min".
    var freshness: String? {
        guard let t = lastRefresh else { return nil }
        let s = Int(Date().timeIntervalSince(t))
        let age = s < 60 ? "\(s) s" : s < 3600 ? "\(s / 60) min" : "\(s / 3600) h"
        return unreachable ? "offline for \(age)" : "updated \(age) ago"
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
        #if DEBUG
        // Sign-in page tests: `--reset-signins` forgets the sign-in, the known gateways and the kept
        // sign-ins; `--test-known <url,url>` remembers gateways (oldest first);
        // `--test-kept <user,user>` keeps a sign-in for each user on the default gateway.
        if args.contains("--reset-signins") {
            SavedSignIn.clear(defaults); GatewayBook.clear()
            defaults.removeObject(forKey: "gateway.url"); defaults.removeObject(forKey: "gateway.user")
        }
        if let users = value("--test-kept"), let gw = SavedSignIn.normalize(SavedSignIn.defaultGateway) {
            for user in users.split(separator: ",").map(String.init) {
                try? GatewayBook.keep(SavedSignIn(gateway: gw, user: user, credential: .token("test-kept-token")), user: user)
            }
        }
        // (after the kept ones: the known gateways are the more recent)
        if let list = value("--test-known") {
            for (i, url) in list.split(separator: ",").compactMap({ SavedSignIn.normalize(String($0)) }).enumerated() {
                GatewayBook.touch(url, at: Date().addingTimeInterval(Double(i + 1)))
            }
        }
        // `--test-last-user <name>`: the user signed in last (what the field starts with).
        if let user = value("--test-last-user") { UserDefaults.standard.set(user, forKey: "gateway.user") }
        #endif
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
            // `--slow-automations`: they answer 3 s after the conversations, as on a public gateway;
            // `--flaky-automations`: the first call fails (it times out), the retry answers;
            // `--slow-start`: the first 3 polls fail (a radio coming up); `--offline`: every poll fails;
            // `--slow-definitions`: an automation's definition takes 3 s (Edit shows it at once once read);
            // `--slow-run`: a Run now takes 4 s to be accepted (as a command over the watch's radio).
            let args = ProcessInfo.processInfo.arguments
            model = AppModel(client: MockGatewayClient(world: .watch, automationsDelay: args.contains("--slow-automations") ? .seconds(3) : .zero,
                                                       automationsFailures: args.contains("--flaky-automations") ? 1 : 0,
                                                       pollFailures: args.contains("--offline") ? .max : args.contains("--slow-start") ? 3 : 0,
                                                       definitionDelay: args.contains("--slow-definitions") ? .seconds(3) : .zero,
                                                       runDelay: args.contains("--slow-run") ? .seconds(4) : .zero), gatewayHost: "mbp")
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
        if args.contains("--reset-tools") {
            ToolPrefs.reset(); WorkflowPrefs.reset(); model.reloadToolPrefs()
        }
        if args.contains("--fresh-conversation") { model.useTestSession() }
        if args.contains("--reset-seen") { model.resetSeen() }   // a test's own, empty conversation
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
        case "automation-info": let a = MockGatewayClient.sampleAutomations[0]; return [.automations, .automation(a), .automationInfo(a)]
        case "automation-edit": let a = MockGatewayClient.sampleAutomations[0]; return [.automations, .automation(a), .automationInfo(a), .automationEdit(a)]
        case "ask": return [.ask(.idle)]
        case "ask-entity": model.setResponder(.entity("castor"), persist: false); return [.ask(.idle)]
        case "listening": return [.ask(.listening)]
        case "thinking": return [.ask(.thinking)]
        case "answer": return [.ask(.answer)]
        case "runs", "sessions": return [.sessions]
        case "session-search": return [.sessions, .sessionSearch("assay QC")]
        case "session-search-media": return [.sessions, .sessionSearch("survival curve")]
        case "session-long":
            let s = SessionSummary.group(MockGatewayClient.World.watch.sampleRuns).first { $0.id == "s-qc" }!
            return [.sessions, .session(s)]
        case "session":
            let s = SessionSummary.group(MockGatewayClient.World.watch.sampleRuns)[1]
            return [.sessions, .session(s)]
        case "automations": return [.automations]
        case "settings": return [.settings]
        case "connection": return [.settings, .connection]
        case "orblab", "orbstyle": return [.settings, .orbStyle]
        case "about": return [.settings, .about]
        case "voice": return [.settings, .voiceSettings]
        case "link": return [.link(URL(string: "https://abstractframework.ai")!)]
        case "read": return [.read(ReadItem(title: "Answer", text: MockGatewayClient.World.watch.cannedAnswer, scope: .run("7c1e02aa")))]
        default: return []
        }
    }
}
