import Foundation
import Observation
import AbstractGatewayClient

@MainActor @Observable
public final class AssistantStore {
    public enum Phase: String { case ready, sending, working, waiting }
    public enum ActivityState: String { case idle, connecting, running, waiting, completed, failed, cancelled }
    public private(set) var activity = RunActivity()
    public private(set) var answerActivities: [String: AnswerActivity] = [:]
    private struct ActivityLoad { var id: UUID; var task: Task<Void, Never> }
    @ObservationIgnored private var answerActivityLoads: [String: ActivityLoad] = [:]
    @ObservationIgnored private var answerActivityEpoch = UUID()
    public func loadAnswerActivity(runID: String, retry: Bool = false) async {
        guard let client else { return }
        if let load = answerActivityLoads[runID] { await load.task.value; return }
        guard retry || answerActivities[runID] == nil else { return }
        let context = contextID, session = sessionID, epoch = answerActivityEpoch, token = UUID()
        // A history row's lifetime does not own its network request. All callers await
        // the same task; scrolling/cancelling any waiter cannot discard its result.
        let task = Task { [weak self] in
            defer {
                if let self, epoch == self.answerActivityEpoch, self.answerActivityLoads[runID]?.id == token {
                    self.answerActivityLoads[runID] = nil
                }
            }
            do {
                let value = try await AnswerActivity.load(runID: runID, client: client)
                guard let self, context == self.contextID, session == self.sessionID,
                      epoch == self.answerActivityEpoch, self.answerActivityLoads[runID]?.id == token,
                      !Task.isCancelled else { return }
                self.answerActivities[runID] = value
            } catch {
                guard let self, context == self.contextID, session == self.sessionID,
                      epoch == self.answerActivityEpoch, self.answerActivityLoads[runID]?.id == token,
                      !(error is CancellationError), !Task.isCancelled else { return }
                self.answerActivities[runID] = .init(activity: RunActivity(), issues: [error.localizedDescription])
                if case GatewayError.unauthorized = error { self.handle(error) }
            }
        }
        answerActivityLoads[runID] = ActivityLoad(id: token, task: task)
        await task.value
    }
    private func clearAnswerActivities() {
        answerActivityEpoch = UUID()
        for load in answerActivityLoads.values { load.task.cancel() }
        answerActivityLoads = [:]; answerActivities = [:]
    }
    private func cacheCompletedActivity(_ value: AnswerActivity, runID: String) {
        answerActivityLoads.removeValue(forKey: runID)?.task.cancel()
        answerActivities[runID] = value
    }
    public private(set) var activityRootID: String?
    public private(set) var activityState: ActivityState = .idle
    public private(set) var activityFailure: String?
    public private(set) var activityIssue: String?
    public private(set) var activityCheckedAt: Date?
    public private(set) var activitySummary: String?
    public var conversationWait: Wait? { activityWaits.first }
    @ObservationIgnored private var activityWaits: [Wait] = []
    @ObservationIgnored private var autoAnsweredWaits: Set<String> = []
    @ObservationIgnored private var activityWaitSteps: [String: String] = [:]
    @ObservationIgnored private var activityRunIDs: Set<String> = []
    @ObservationIgnored private var activityCursors: [String: Int] = [:]
    @ObservationIgnored private var entityActivityCursors: [String: Int] = [:]
    @ObservationIgnored private var activityStreams: [String: Task<Void, Never>] = [:]
    @ObservationIgnored private var activityFinishedStreams: Set<String> = []
    @ObservationIgnored private var activityEpoch = UUID()
    @ObservationIgnored private var activityProblems: [String: String] = [:]
    @ObservationIgnored private var followingID: UUID?
    @ObservationIgnored private var quietActivityRootID: String?
    public var preferences = PhonePreferences()
    public private(set) var contextID = UUID()
    public private(set) var completedReply: ConversationMessage?
    public private(set) var client: (any GatewayClient)?
    public private(set) var connection: SavedConnection?
    public private(set) var principal: Principal?
    public private(set) var phase: Phase = .ready
    public private(set) var messages: [ConversationMessage] = []
    public private(set) var runs: [RunSummary] = []
    public private(set) var archivedRuns: [RunSummary] = []
    public private(set) var recentHistoryMayBePartial = false
    public private(set) var loadingArchived = false
    public private(set) var sessionArchiveBusy: Set<String> = []
    public private(set) var historyError: String?
    @ObservationIgnored private var historyRevision = 0

    public private(set) var waits: [Wait] = []
    public private(set) var automations: [AutomationSummary] = []
    /// The person's event stream (backlog 1047): badges and local notifications.
    public let attention: AttentionFeed
    public private(set) var entitiesError: String?
    public private(set) var loadingEntities = false
    public private(set) var entities: [EntitySummary] = []
    public private(set) var sessionID = "iphone-" + UUID().uuidString.lowercased()
    public private(set) var activeRunID: String?
    public private(set) var activeEntityRunID: String?
    public private(set) var selectedEntity: String?
    public private(set) var error: String?
    public private(set) var automationsError: String?
    public private(set) var lastRefresh: Date?
    public private(set) var isRefreshing = false
    public private(set) var isOpening = false
    public private(set) var isStopping = false
    public var canStop: Bool { client != nil && (phase != .ready || isStopping) }
    public private(set) var deciding: Set<String> = []
    public private(set) var approvingAll: Set<String> = []
    public private(set) var automationBusy: Set<String> = []
    public private(set) var titles: [String: String] = [:]
    public var isDemo: Bool { client?.isMock == true }
    public var isConnected: Bool { client != nil }
    public var sessions: [SessionSummary] { SessionSummary.group(runs) }
    public var canSend: Bool { client != nil && sessionArchiveBusy.isEmpty && phase == .ready && !isOpening && !isStopping && !sendInFlight && restorationID == nil }
    public var isRestoring: Bool { restorationID != nil }
    public var canOpenConversation: Bool { client != nil && sessionArchiveBusy.isEmpty && !isOpening && !isStopping && (phase == .ready || (unknownStart && !sendInFlight)) }
    public var conversationTitle: String { selectedEntity.map { name in entities.first { $0.name == name }?.displayName ?? name.capitalized } ?? "Assistant" }
    @ObservationIgnored private var generation = 0
    @ObservationIgnored private var conversationGeneration = 0
    @ObservationIgnored private var foreground = false
    @ObservationIgnored private var poll: Task<Void, Never>?
    @ObservationIgnored private var approvalPoll: Task<Void, Never>?
    private var approvalRevision = 0
    @ObservationIgnored private var turn: Task<Void, Never>?
    @ObservationIgnored private var stopping: Task<Void, Never>?
    @ObservationIgnored private var stopRequested = false
    @ObservationIgnored private var stopVersion = 0
    private var sendInFlight = false
    @ObservationIgnored private var sendID: UUID?
    @ObservationIgnored private var unknownStart = false
    @ObservationIgnored private var cancelledRunID: String?
    @ObservationIgnored private var entityChatIDs: [String: String] = [:]
    @ObservationIgnored private var entityVisitIDs: [String: String] = [:]
    @ObservationIgnored private var quietEntityRestoreID: String?
    @ObservationIgnored private var measuredMessages: Set<String> = []
    @ObservationIgnored private var toolSelections: [String: ConversationTools] = [:]
    private var restorationID: String?
    @ObservationIgnored private let defaults: UserDefaults
    @ObservationIgnored public var onUnauthorized: (@MainActor () -> Void)?

    public init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        attention = AttentionFeed(defaults: defaults)
        attention.onChange = { [weak self] in
            guard let self, self.client != nil else { return }
            Task { await self.refresh() }
        }
    }

    /// Needs-you for the Inbox badge: the live waits, or the stream's when it already knows more.
    public var inboxBadge: Int { max(waits.count, attention.needYou) }

    public func connect(_ connection: SavedConnection?, client: any GatewayClient) {
        disconnect()
        self.connection = connection; self.client = client
        preferences = PhonePreferences(scope: connection?.scope ?? "demo", defaults: defaults)
        migrateToolDefaults()
        if let connection {
            restorationID = defaults.string(forKey: "phone.session." + connection.scope)
            if let entity = defaults.string(forKey: "phone.entity." + connection.scope), let saved = restorationID {
                selectedEntity = entity; sessionID = saved; restorationID = nil
                if let id = defaults.string(forKey: "phone.visit." + connection.scope + "." + saved) {
                    entityVisitIDs[entity + ":" + saved] = id; activeEntityRunID = id; quietEntityRestoreID = id; phase = .working
                }
            }
        }
        if restorationID == nil { persistSession() }
        attention.start(client: client, scope: connection?.scope ?? "demo", foreground: foreground)
        if foreground { startPolling() }
    }
    public func disconnect() {
        attention.stop()
        clearAnswerActivities(); entityActivityCursors = [:]
        resetActivity()
        recentHistoryMayBePartial = false
        archivedRuns = []; loadingArchived = false; sessionArchiveBusy = []; historyError = nil; historyRevision += 1
        contextID = UUID()
        generation += 1; conversationGeneration += 1
        approvalPoll?.cancel(); approvalPoll = nil
        poll?.cancel(); poll = nil; turn?.cancel(); turn = nil; stopping?.cancel(); stopping = nil
        isStopping = false; stopRequested = false; sendInFlight = false; sendID = nil; unknownStart = false; cancelledRunID = nil
        client = nil; connection = nil; principal = nil; messages = []; runs = []; waits = []; automations = []; entities = []
        titles = [:]; entityChatIDs = [:]; entityVisitIDs = [:]; toolSelections = [:]; measuredMessages = []; activeEntityRunID = nil; activeRunID = nil; selectedEntity = nil; restorationID = nil
        completedReply = nil; quietEntityRestoreID = nil
        phase = .ready; error = nil; automationsError = nil; entitiesError = nil; loadingEntities = false; lastRefresh = nil; isRefreshing = false; isOpening = false
        deciding = []; approvingAll = []; automationBusy = []; sessionID = "iphone-" + UUID().uuidString.lowercased()
    }
    public func setForeground(_ value: Bool) {
        foreground = value
        attention.setForeground(value)
        if value { startPolling() } else { poll?.cancel(); poll = nil; approvalPoll?.cancel(); approvalPoll = nil; pauseActivityStreams() }
    }
    private func startPolling() {
        guard poll == nil, client != nil else { return }
        approvalPoll = Task { [weak self] in
            while !Task.isCancelled {
                guard let self else { return }
                await self.refreshPendingApprovals()
                do { try await Task.sleep(for: .seconds(1)) } catch { return }
            }
        }
        poll = Task { [weak self] in
            var ticks = 0
            while !Task.isCancelled, let self, self.client != nil {
                if self.activeEntityRunID != nil || ticks % 3 == 0 { await self.followActiveRun() }
                if ticks % 15 == 0 { await self.refresh() }
                ticks += 1
                do { try await Task.sleep(for: .seconds(1)) } catch { break }
            }
        }
    }
    /// Reconcile visible waits independently of slow history/automation refreshes.
    /// Read each owning run: an incomplete inbox page must never dismiss an approval.
    func refreshPendingApprovals() async {
        guard let client else { return }
        let epoch = generation
        let pending = Dictionary(grouping: waits + activityWaits, by: \.runId)
        for (id, known) in pending {
            guard !Task.isCancelled, epoch == generation else { return }
            do {
                let run = try await client.run(id: id)
                guard !Task.isCancelled, epoch == generation else { return }
                let current = run.isTerminal ? nil : run.personWait?.id
                let removed = Set(known.filter { $0.id != current }.map(\.id))
                guard !removed.isEmpty else { continue }
                approvalRevision += 1
                waits.removeAll { removed.contains($0.id) }
                activityWaits.removeAll { removed.contains($0.id) }
                if activityWaits.isEmpty, activityState == .waiting {
                    activityState = .running; activitySummary = nil
                    if phase == .waiting { phase = .working }
                }
            } catch { if epoch == generation, !Task.isCancelled { handle(error) } }
        }
    }

    private var automationArchiveRevision = 0

    public func refresh() async {
        guard let client, !isRefreshing else { return }
        let epoch = generation, historyVersion = historyRevision, approvals = approvalRevision, archives = automationArchiveRevision
        isRefreshing = true
        defer { if epoch == generation { isRefreshing = false } }
        do {
            let me = try await client.me()
            guard epoch == generation else { return }; principal = me
            let newWaits = try await client.waits()
            guard epoch == generation else { return }; if approvals == approvalRevision { waits = newWaits + waits.filter { $0.runId == activeEntityRunID } }
            let newRuns = try await client.recentRuns(limit: 60)
            guard epoch == generation else { return }; if historyVersion == historyRevision { runs = newRuns; recentHistoryMayBePartial = newRuns.count >= 60 }
            if let saved = restorationID {
                restorationID = nil
                if let previous = sessions.first(where: { $0.id == saved }) {
                    await openSession(previous)
                    if error != nil { return }
                }
                else { persistSession() }
                guard epoch == generation else { return }
            }
            lastRefresh = Date(); error = nil
            do {
                let rows = try await client.automations()
                guard epoch == generation else { return }; if archives == automationArchiveRevision { automations = rows }; automationsError = nil
            } catch { guard epoch == generation else { return }; automationsError = say(error); handle(error) }
            guard epoch == generation else { return }
            await loadEntities()
            // Titles are a small, rebuildable cache, never a new source of conversation history.
            for session in sessions.prefix(8) where titles[session.id] == nil {
                guard epoch == generation, !Task.isCancelled else { return }
                if let prompt = try? await client.prompt(ofRun: session.firstRunId), epoch == generation {
                    titles[session.id] = SessionSummary.title(fromPrompt: prompt, limit: 180)
                }
            }
        } catch { if epoch == generation, !(error is CancellationError) { self.error = say(error); handle(error) } }
    }
    public var archivedSessions: [SessionSummary] { SessionSummary.group(archivedRuns) }
    public func canArchive(_ session: SessionSummary) -> Bool {
        client != nil && !session.isLive && sessionArchiveBusy.isEmpty && !isOpening &&
            (session.id != sessionID || canSend)
    }
    public func clearHistoryError() { historyError = nil }
    public func loadHistoryTitle(_ session: SessionSummary) async {
        guard titles[session.id] == nil, let client else { return }
        let epoch = generation
        do {
            if let prompt = try await client.prompt(ofRun: session.firstRunId), epoch == generation, !Task.isCancelled {
                titles[session.id] = SessionSummary.title(fromPrompt: prompt, limit: 180)
            }
        } catch { if epoch == generation, error as? GatewayError == .unauthorized { handle(error) } }
    }
    public func loadArchivedConversations() async {
        guard let client, !loadingArchived else { return }
        let epoch = generation, revision = historyRevision
        loadingArchived = true; historyError = nil
        defer { if epoch == generation { loadingArchived = false } }
        do {
            let rows = try await client.archivedRuns(limit: 200)
            guard epoch == generation, revision == historyRevision, !Task.isCancelled else { return }
            archivedRuns = rows
        } catch {
            guard epoch == generation, revision == historyRevision, !(error is CancellationError) else { return }
            historyError = say(error); handle(error)
        }
    }
    @discardableResult public func setArchived(_ session: SessionSummary, _ archived: Bool) async -> Bool {
        guard let client, sessionArchiveBusy.isEmpty, !isOpening,
              !archived || canArchive(session) else { return false }
        let epoch = generation
        sessionArchiveBusy.insert(session.id); historyRevision += 1; historyError = nil
        defer { if epoch == generation { sessionArchiveBusy.remove(session.id) } }
        do {
            // Recheck the gateway before archiving a session that may be working on another device.
            let current = try await client.turns(ofSession: session.id)
            guard epoch == generation, !Task.isCancelled else { return false }
            if archived && current.contains(where: { !$0.isTerminal }) {
                historyError = "This conversation is working. Wait for it to finish before archiving."
                return false
            }
            try await client.setArchived(sessionId: session.id, archived)
            guard epoch == generation else { return false }
            historyRevision += 1
            if archived {
                runs.removeAll { ($0.sessionId ?? $0.runId) == session.id }
                archivedRuns.removeAll { ($0.sessionId ?? $0.runId) == session.id }; archivedRuns += current
                if session.id == sessionID { newConversation(entity: selectedEntity) }
            } else {
                archivedRuns.removeAll { ($0.sessionId ?? $0.runId) == session.id }
                runs.removeAll { ($0.sessionId ?? $0.runId) == session.id }; runs += current
                runs.sort { ($0.updatedAt ?? $0.createdAt ?? "") > ($1.updatedAt ?? $1.createdAt ?? "") }
            }
            return true
        } catch {
            guard epoch == generation, !(error is CancellationError) else { return false }
            historyError = say(error); handle(error); return false
        }
    }
    public func loadEntities() async {
        guard let client, !loadingEntities else { return }
        let epoch = generation; loadingEntities = true
        defer { if epoch == generation { loadingEntities = false } }
        do { let rows = try await client.entities(); guard epoch == generation else { return }; entities = rows; entitiesError = nil }
        catch { if epoch == generation { entitiesError = say(error); handle(error) } }
    }
    public func rememberEntity(_ row: EntitySummary) { entities.removeAll { $0.name == row.name }; entities.append(row) }
    public func dismissError() { error = nil }
    public func authenticationExpired() { handle(GatewayError.unauthorized) }
    public func newConversation(entity: String? = nil) {
        guard phase == .ready, !isOpening else { return }
        if let oldEntity = selectedEntity, let id = entityVisitIDs[oldEntity + ":" + sessionID], let client {
            let epoch = generation, oldSession = sessionID
            isOpening = true
            turn = Task {
                do {
                    try await client.endEntitySession(name: oldEntity, runID: id)
                    guard epoch == generation else { return }
                    entityVisitIDs.removeValue(forKey: oldEntity + ":" + oldSession)
                    if let connection { defaults.removeObject(forKey: "phone.visit." + connection.scope + "." + oldSession) }
                    isOpening = false; resetConversation(entity: entity)
                } catch { if epoch == generation { isOpening = false; self.error = say(error); handle(error) } }
            }
        } else { resetConversation(entity: entity) }
    }
    private func resetConversation(entity: String?) {
        clearAnswerActivities(); entityActivityCursors = [:]
        resetActivity()
        completedReply = nil; quietEntityRestoreID = nil; error = nil
        stopRequested = false; isStopping = false; unknownStart = false; cancelledRunID = nil
        conversationGeneration += 1; measuredMessages = []; messages = []; selectedEntity = entity; activeEntityRunID = nil; activeRunID = nil; restorationID = nil
        sessionID = "iphone-" + UUID().uuidString.lowercased(); persistSession()
    }
    public var canEditToolPreferences: Bool { client != nil && !isOpening && !isRestoring && !isStopping && !sendInFlight }
    private var appToolRevision = 0
    private var approvalTrustRevision = 0
    private var appToolsKey: String { "phone.tools.defaults." + (connection?.scope ?? "demo") }
    private func migrateToolDefaults() {
        let marker = appToolsKey + ".global"
        guard !defaults.bool(forKey: marker) else { return }
        if defaults.data(forKey: appToolsKey) == nil, let legacy = defaults.data(forKey: appToolsKey + ".assistant") {
            defaults.set(legacy, forKey: appToolsKey)
        }
        defaults.set(true, forKey: marker)
    }
    public var appTools: ConversationTools? {
        _ = appToolRevision
        guard let data = defaults.data(forKey: appToolsKey) else { return nil }
        return try? JSONDecoder().decode(ConversationTools.self, from: data)
    }
    public var effectiveTools: ConversationTools? { conversationTools ?? appTools }
    public func setAppTools(_ tools: ConversationTools?) {
        guard canEditToolPreferences else { return }
        if let tools, let data = try? JSONEncoder().encode(tools) { defaults.set(data, forKey: appToolsKey) }
        else { defaults.removeObject(forKey: appToolsKey) }
        appToolRevision += 1; approvalTrustRevision += 1
    }
    private var toolsKey: String { "phone.tools." + (connection?.scope ?? "demo") + "." + (selectedEntity ?? "assistant") + "." + sessionID }
    public var conversationTools: ConversationTools? {
        if let selection = toolSelections[toolsKey] { return selection }
        guard let data = defaults.data(forKey: toolsKey) else { return nil }
        return try? JSONDecoder().decode(ConversationTools.self, from: data)
    }
    public func setConversationTools(_ tools: ConversationTools?) {
        guard canEditToolPreferences else { return }
        revokeSessionApprovals()
        defaults.removeObject(forKey: toolsKey + ".grant")
        toolSelections[toolsKey] = tools
        if let tools, let data = try? JSONEncoder().encode(tools) { defaults.set(data, forKey: toolsKey) }
        else { defaults.removeObject(forKey: toolsKey) }
    }
    /// Temporary Approve grants never change the configured Off / Auto / Approve modes.
    public var sessionApprovalGrants: Set<String> {
        _ = approvalTrustRevision
        return Set(defaults.stringArray(forKey: toolsKey + ".approvalTrust") ?? []).filter {
            effectiveTools == nil || effectiveTools?.modes[$0] == .approve
        }
    }
    public func revokeSessionApprovals() {
        defaults.removeObject(forKey: toolsKey + ".approvalTrust")
        approvalTrustRevision += 1
    }
    /// Older builds overwrote the modes and lost their origin. Never guess which Auto
    /// settings were intentional: the person explicitly chooses which should ask again.
    public var legacySessionApprovalNames: [String] {
        _ = approvalTrustRevision
        return (defaults.stringArray(forKey: toolsKey + ".grant") ?? []).sorted()
    }
    public func reviewLegacySessionApprovals(askingAgain names: Set<String>) {
        guard canEditToolPreferences, !legacySessionApprovalNames.isEmpty,
              names.isSubset(of: Set(legacySessionApprovalNames)), var selection = conversationTools else { return }
        for name in names where selection.modes[name] == .auto { selection.modes[name] = .approve }
        setConversationTools(selection)
    }
    public func loadMessageStats() async {
        guard preferences.showMessageStats, let client else { return }
        let epoch = generation, view = conversationGeneration
        for message in messages where message.role == .assistant && message.stats == nil && message.runID != activeRunID && !measuredMessages.contains(message.id) {
            guard epoch == generation, view == conversationGeneration else { return }
            guard let id = message.runID else { continue }
            do {
                let stats = try await client.messageStats(runID: id)
                guard epoch == generation, view == conversationGeneration else { return }
                measuredMessages.insert(message.id)
                if let index = messages.firstIndex(where: { $0.id == message.id }) { messages[index].stats = stats }
            } catch { if epoch == generation { handle(error) } }
        }
    }
    /// A resend starts a new turn; confirmed history is never rewritten.
    @discardableResult public func resendStoppedRequest(messageID: String, text: String, attachments: [PhoneArtifact], session: String, context: UUID) -> Bool {
        guard context == contextID, session == sessionID, canSend,
              let original = messages.first(where: { $0.id == messageID && $0.role == .user && $0.wasStopped }),
              attachments.allSatisfy({ original.artifacts.contains($0) }),
              !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !attachments.isEmpty else { return false }
        send(text, attachments: attachments)
        return phase == .sending
    }

    public func send(_ text: String, attachments: [PhoneArtifact] = []) {
        let prompt = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard (!prompt.isEmpty || !attachments.isEmpty), canSend, let client else { return }
        if selectedEntity != nil && !attachments.isEmpty { error = "Files can be sent to Assistant conversations. Entity file messages are not supported by this gateway interface."; return }
        let epoch = generation, view = conversationGeneration, session = sessionID, entity = selectedEntity
        let primaryImage = attachments.first(where: \.isImage) ?? messages.reversed().flatMap(\.artifacts).first(where: \.isImage)
        let tools = effectiveTools, requestVersion = stopVersion, requestID = UUID()
        stopRequested = false; isStopping = false; unknownStart = false; cancelledRunID = nil; completedReply = nil; sendInFlight = true; sendID = requestID
        resetActivity(); activityState = .connecting
        let request = ConversationMessage(role: .user, text: prompt + (attachments.isEmpty ? "" : "\n" + attachments.map { "📎 " + $0.filename }.joined(separator: "\n")), artifacts: attachments, requestText: prompt)
        messages.append(request); phase = .sending; error = nil
        turn = Task {
            defer { if epoch == generation, view == conversationGeneration, sendID == requestID { sendInFlight = false; sendID = nil } }
            do {
                guard requestVersion == stopVersion else { return }
                if let entity {
                    let key = entity + ":" + session
                    if let existing = entityVisitIDs[key] {
                        activeEntityRunID = existing
                        try await client.setEntityTools(name: entity, runID: existing, tools: tools)
                        guard epoch == generation, view == conversationGeneration else { return }
                        guard requestVersion == stopVersion else { return }
                        _ = try await client.sendEntityTurn(name: entity, runID: existing, text: prompt)
                        guard epoch == generation, view == conversationGeneration else { return }
                        guard requestVersion == stopVersion else { return }
                        activeEntityRunID = existing; phase = .working
                        beginActivity(existing)
                        await followEntitySession()
                    } else {
                        // Capability discovery precedes the write; older gateways keep ordinary chat,
                        // but explicit policies can never fall through to the legacy ungated API.
                        let supported: Bool
                        do { _ = try await client.entityTools(name: entity); supported = true }
                        catch GatewayError.http(status: 404, body: _) { supported = false }
                        catch PhoneAttachmentError.unsupported { supported = false }
                        guard requestVersion == stopVersion else { return }
                        if supported {
                            unknownStart = true
                            let state = try await client.openEntitySession(name: entity, sessionID: session, tools: tools)
                            guard epoch == generation, view == conversationGeneration else { return }
                            unknownStart = false
                            entityVisitIDs[key] = state.runID
                            if let connection { defaults.set(state.runID, forKey: "phone.visit." + connection.scope + "." + session) }
                            activeEntityRunID = state.runID
                            guard requestVersion == stopVersion else { return }
                            _ = try await client.sendEntityTurn(name: entity, runID: state.runID, text: prompt)
                            guard epoch == generation, view == conversationGeneration else { return }
                            guard requestVersion == stopVersion else { return }
                            activeEntityRunID = state.runID; phase = .working
                            beginActivity(state.runID)
                            await followEntitySession()
                        } else {
                            guard tools == nil else { throw PhoneAttachmentError.unsupported }
                            let chat: String
                            if let existing = entityChatIDs[entity] { chat = existing }
                            else { chat = try await client.openEntityChat(name: entity) }
                            guard epoch == generation, view == conversationGeneration else { return }
                            entityChatIDs[entity] = chat
                            guard requestVersion == stopVersion else { return }
                            let answer = try await client.entityChatTurn(name: entity, chatId: chat, text: prompt)
                            guard epoch == generation, view == conversationGeneration else { return }
                            if requestVersion != stopVersion {
                                messages.append(.init(role: .notice, text: "Reply dismissed. This gateway cannot stop entity work already sent."))
                                finishStop(requestWasStopped: false); return
                            }
                            let reply = ConversationMessage(role: .assistant, text: answer)
                            messages.append(reply); completedReply = reply; phase = .ready
                            activityState = .completed; activityIssue = "Live activity is unavailable for this gateway’s legacy entity chat."
                        }
                    }
                } else {
                    unknownStart = true
                    let id = try await client.startRun(prompt: prompt.isEmpty ? "Please review the attached files." : prompt, sessionId: session, attachments: attachments.map(\.ref), tools: tools, primaryImage: primaryImage?.ref)
                    guard epoch == generation, view == conversationGeneration else { return }
                    unknownStart = false; activeRunID = id; phase = .working
                    if let index = messages.firstIndex(where: { $0.id == request.id }) { messages[index].runID = id }
                    beginActivity(id)
                    if foreground { await followActiveRun() }
                }
            } catch {
                guard epoch == generation, view == conversationGeneration else { return }
                if requestVersion != stopVersion {
                    guard stopRequested else { return }
                    self.error = "Stop is not yet confirmed. " + say(error)
                    handle(error); return
                }
                phase = activeEntityRunID == nil ? .ready : .working
                activityState = .failed; activityFailure = say(error)
                self.error = say(error) + " Check Conversations before resending: the gateway may already have received your request."
                handle(error)
                if let id = activeEntityRunID { quietEntityRestoreID = id; await followEntitySession() }
            }
        }
    }
    public func followActiveRun() async {
        guard followingID == nil else { return }
        let follow = UUID(); followingID = follow
        defer { if followingID == follow { followingID = nil } }
        if activeEntityRunID != nil { await followEntitySession(); return }
        guard let client, let id = activeRunID else { return }
        if activityRootID != id { beginActivity(id) }
        let epoch = activityEpoch, approvals = approvalRevision
        do {
            let run = try await client.run(id: id)
            guard epoch == activityEpoch, activeRunID == id else { return }
            activityCheckedAt = Date(); setActivityProblem("status", nil); setActivityProblem("children", nil)
            let tree = await activityTree(root: run, client: client, epoch: epoch)
            guard epoch == activityEpoch, activeRunID == id else { return }
            guard approvals == approvalRevision else { return }
            activityWaits = stopRequested ? [] : tree.compactMap { $0.isTerminal ? nil : $0.personWait }
            autoAnsweredWaits.formIntersection(Set(activityWaits.map(\.id)))
            waits.removeAll { activityRunIDs.contains($0.runId) }
            waits.insert(contentsOf: activityWaits, at: 0)
            if !run.isTerminal { await applyConversationTrust(epoch: epoch) }
            guard epoch == activityEpoch, activeRunID == id else { return }
            let output = run.conversationText ?? "", artifacts = run.mediaArtifacts
            if !output.isEmpty || !artifacts.isEmpty {
                if let index = messages.firstIndex(where: { $0.id == "answer-" + id }) { messages[index].text = output; messages[index].artifacts = artifacts }
                else { messages.append(.init(id: "answer-" + id, role: .assistant, text: output, runID: id, artifacts: artifacts)) }
            }
            if run.isTerminal {
                pauseActivityStreams()
                for childID in activityRunIDs { await drainActivity(runID: childID, entity: nil, epoch: epoch) }
                guard epoch == activityEpoch, activeRunID == id else { return }
                activityState = run.status == "failed" ? .failed : run.status == "cancelled" ? .cancelled : .completed
                activityFailure = run.status == "failed" ? (run.error ?? "The workflow failed without an error description.") : nil
                activitySummary = nil
                activity.finish(status: run.status)
                cacheCompletedActivity(.init(activity: activity, issues: activityIssue.map { [$0] } ?? []), runID: id)
                activityWaits = []; waits.removeAll { activityRunIDs.contains($0.runId) }
                if !stopRequested, quietActivityRootID != id, run.status == "completed", let reply = messages.first(where: { $0.id == "answer-" + id }) { completedReply = reply }
                if run.status == "failed" { error = activityFailure }
                if run.status == "cancelled" { markStoppedRequest(runID: id); messages.append(.init(role: .notice, text: "Run stopped.")) }
                phase = .ready; activeRunID = nil
                if stopRequested {
                    if let current = try? await client.waits(), epoch == activityEpoch { waits = current }
                    guard epoch == activityEpoch else { return }
                    finishStop(requestWasStopped: run.status == "cancelled"); return
                }
                if preferences.showMessageStats { await loadMessageStats() }
            } else {
                phase = activityWaits.isEmpty ? .working : .waiting
                activityState = activityWaits.isEmpty ? .running : .waiting
                let leaf = tree.last ?? run
                activitySummary = leaf.waiting?.reason == "job" ? "Waiting for a background job" : leaf.waiting?.reason == "event" ? "Waiting for an event" : leaf.runId != id && leaf.isTerminal ? "Finishing workflow" : nil
                for child in tree {
                    guard epoch == activityEpoch, activeRunID == id else { return }
                    if !foreground || child.isTerminal || (activityStreams[child.runId] == nil && activityStreams.count >= 4) {
                        await drainActivity(runID: child.runId, entity: nil, epoch: epoch)
                    } else { startActivityStream(child.runId) }
                }
            }
        } catch {
            if epoch == activityEpoch, activeRunID == id, !(error is CancellationError) {
                setActivityProblem("status", "Status connection lost. Reconnecting… " + say(error))
                if isStopping { self.error = "Stop is not yet confirmed. Tap Stop to retry. " + say(error); isStopping = false }
                handle(error)
            }
        }
    }
    private func followEntitySession() async {
        guard let client, let entity = selectedEntity, let id = activeEntityRunID else { return }
        if activityRootID != id { beginActivity(id) }
        let activityToken = activityEpoch, approvals = approvalRevision
        let epoch = generation, view = conversationGeneration
        do {
            let state = try await client.entitySession(name: entity, runID: id)
            guard epoch == generation, view == conversationGeneration, activeEntityRunID == id else { return }
            activityCheckedAt = Date()
            await drainActivity(runID: id, entity: entity, epoch: activityToken)
            guard activityToken == activityEpoch, approvals == approvalRevision else { return }
            // The stop worker owns entity lifecycle until the server confirms closure.
            guard !stopRequested else { return }
            if let wait = state.personWait {
                waits.removeAll { $0.runId == id }; waits.insert(wait, at: 0); activityWaits = [wait]
                autoAnsweredWaits.formIntersection([wait.id])
                await applyConversationTrust(epoch: activityToken)
                guard activityToken == activityEpoch else { return }
                phase = activityWaits.isEmpty ? .working : .waiting; activityState = activityWaits.isEmpty ? .running : .waiting
            } else if state.finishedTurn {
                activityWaits = []
                activityState = state.status == "failed" ? .failed : state.status == "cancelled" ? .cancelled : .completed
                activityFailure = state.status == "failed" ? (state.error ?? "The entity could not finish its reply.") : nil
                activity.finish(status: state.status == "waiting" ? "completed" : state.status)
                if state.status == "failed" { error = state.error ?? "The entity could not finish its reply." }
                waits.removeAll { $0.runId == id }
                if let text = state.reply, !text.isEmpty {
                    let messageID = id + "-turn-" + String(state.turn)
                    cacheCompletedActivity(.init(activity: activity, issues: activityIssue.map { [$0] } ?? [], scopeTitle: quietEntityRestoreID == id ? "Visit activity" : "Answer activity"), runID: messageID)
                    let reply = ConversationMessage(id: messageID, role: .assistant, text: text, stats: state.stats)
                    if let index = messages.firstIndex(where: { $0.id == messageID }) { messages[index] = reply }
                    else { messages.append(reply) }
                    if quietEntityRestoreID != id { completedReply = reply }
                }
                if ["completed", "failed", "cancelled"].contains(state.status) {
                    entityVisitIDs.removeValue(forKey: entity + ":" + sessionID)
                    if let connection { defaults.removeObject(forKey: "phone.visit." + connection.scope + "." + sessionID) }
                }
                quietEntityRestoreID = nil
                phase = .ready; activeEntityRunID = nil
            } else { activityWaits = []; autoAnsweredWaits = []; phase = .working; activityState = .running }
        } catch {
            if epoch == generation, view == conversationGeneration, activeEntityRunID == id {
                if case GatewayError.http(status: 404, body: _) = error {
                    entityVisitIDs.removeValue(forKey: entity + ":" + sessionID)
                    if let connection { defaults.removeObject(forKey: "phone.visit." + connection.scope + "." + sessionID) }
                    activeEntityRunID = nil; quietEntityRestoreID = nil; phase = .ready
                }
                setActivityProblem("status", "Status connection lost. Reconnecting… " + say(error))
                self.error = say(error); handle(error)
            }
        }
    }
    public func stopRun() async {
        guard canStop else { return }
        if let stopping {
            await stopping.value
            // A new turn can start as the prior stop worker unwinds. Its Stop tap
            // must not disappear into the prior worker's completion.
            if canStop && !stopRequested { await stopRun() }
            return
        }
        // Latch before awaiting: a late start/open response must still be stopped.
        if !stopRequested { stopVersion += 1 }
        stopRequested = true; isStopping = true; completedReply = nil; error = nil
        let epoch = generation, view = conversationGeneration
        let task = Task { [weak self] in
            guard let self else { return }
            defer { if epoch == self.generation, view == self.conversationGeneration { self.stopping = nil } }
            var conflicts = 0
            while !Task.isCancelled, epoch == self.generation, view == self.conversationGeneration, self.stopRequested {
                guard let client = self.client else { return }
                do {
                    if let id = self.activeEntityRunID, let entity = self.selectedEntity {
                        do { try await client.endEntitySession(name: entity, runID: id) }
                        catch GatewayError.http(status: 409, body: _) {
                            // The home writer lease is held during inference. Retry closure
                            // once it yields; never mark the visit stopped on this conflict.
                            conflicts += 1
                            try await Task.sleep(for: .milliseconds(min(2_000, 500 * conflicts))); continue
                        }
                        guard epoch == self.generation, view == self.conversationGeneration else { return }
                        self.waits.removeAll { $0.runId == id }
                        self.entityVisitIDs.removeValue(forKey: entity + ":" + self.sessionID)
                        if let connection = self.connection { self.defaults.removeObject(forKey: "phone.visit." + connection.scope + "." + self.sessionID) }
                        self.activeEntityRunID = nil; self.quietEntityRestoreID = nil
                        self.messages.append(.init(role: .notice, text: "Conversation stopped."))
                        self.finishStop(); return
                    }
                    if let id = self.activeRunID {
                        if self.cancelledRunID != id {
                            try await client.cancel(runId: id)
                            guard epoch == self.generation, view == self.conversationGeneration else { return }
                            self.cancelledRunID = id
                        }
                        await self.followActiveRun()
                        if !self.isStopping { return }
                        if !self.stopRequested { return }
                    } else if !self.sendInFlight {
                        if self.unknownStart {
                            self.isStopping = false
                            self.error = "The gateway did not confirm the request. Check Conversations before sending again; stopping could not be confirmed."
                        } else { self.finishStop() }
                        return
                    }
                    try await Task.sleep(for: .milliseconds(200))
                } catch {
                    guard epoch == self.generation, view == self.conversationGeneration else { return }
                    if error is CancellationError { return }
                    self.isStopping = false
                    self.error = "Stop is not yet confirmed. Tap Stop to retry. " + self.say(error)
                    self.handle(error); return
                }
            }
        }
        stopping = task
        await task.value
    }
    private func markStoppedRequest(runID: String? = nil) {
        if let index = messages.lastIndex(where: { $0.role == .user && (runID == nil || $0.runID == runID) }) { messages[index].wasStopped = true }
    }
    private func finishStop(requestWasStopped: Bool = true) {
        if requestWasStopped { markStoppedRequest() }
        pauseActivityStreams(); activityWaits = []
        activityState = .cancelled; activity.finish(status: "cancelled")
        stopRequested = false; isStopping = false; phase = .ready; cancelledRunID = nil
        sendID = nil; sendInFlight = false; turn?.cancel(); turn = nil
    }
    public func openSession(_ session: SessionSummary) async {
        guard canOpenConversation, let client else { return }
        let epoch = generation
        isOpening = true
        defer { if epoch == generation { isOpening = false } }
        do {
            let turns = try await client.turns(ofSession: session.id)
            // Listings are summaries and can omit output. Hydrate every turn, with
            // bounded concurrency, before replacing visible history atomically.
            let listedIDs = Set(turns.map(\.runId))
            let roots = turns.filter { $0.parentRunId.map { !listedIDs.contains($0) } ?? true }
            let ordered = Array(roots.reversed())
            struct RestoredTurn: Sendable { var index: Int; var run: RunSummary; var input: ConversationInput }
            let hydrated = try await withThrowingTaskGroup(of: RestoredTurn.self) { group in
                func add(_ index: Int) {
                    let row = ordered[index]
                    group.addTask {
                        let detail = try await client.run(id: row.runId)
                        let input = try await client.input(ofRun: row.runId)
                        return RestoredTurn(index: index, run: detail, input: input)
                    }
                }
                var next = min(4, ordered.count), result: [RestoredTurn] = []
                for index in 0..<next { add(index) }
                while let row = try await group.next() {
                    guard epoch == generation else { group.cancelAll(); return [] as [RestoredTurn] }
                    result.append(row)
                    if next < ordered.count { add(next); next += 1 }
                }
                return result.sorted { $0.index < $1.index }
            }
            var restored: [ConversationMessage] = []
            for turn in hydrated {
                let id = turn.run.runId
                if turn.input.prompt != nil || !turn.input.attachments.isEmpty { restored.append(.init(id: "prompt-" + id, role: .user, text: turn.input.prompt ?? "", runID: id, artifacts: turn.input.attachments, requestText: turn.input.prompt ?? "", wasStopped: turn.run.status == "cancelled")) }
                if !(turn.run.conversationText ?? "").isEmpty || !turn.run.mediaArtifacts.isEmpty {
                    restored.append(.init(id: "answer-" + id, role: .assistant, text: turn.run.conversationText ?? "", runID: id, artifacts: turn.run.mediaArtifacts))
                }
                else if turn.run.status == "failed" { restored.append(.init(id: "failed-" + id, role: .notice, text: turn.run.error ?? "This reply could not be completed.", runID: id)) }
            }
            guard epoch == generation else { return }
            if let entity = selectedEntity, let id = entityVisitIDs[entity + ":" + sessionID] {
                let oldSession = sessionID
                try await client.endEntitySession(name: entity, runID: id)
                guard epoch == generation else { return }
                entityVisitIDs.removeValue(forKey: entity + ":" + oldSession)
                if let connection { defaults.removeObject(forKey: "phone.visit." + connection.scope + "." + oldSession) }
            }
            resetActivity(); clearAnswerActivities(); entityActivityCursors = [:]
            activeEntityRunID = nil; quietEntityRestoreID = nil; completedReply = nil
            stopRequested = false; isStopping = false; unknownStart = false; cancelledRunID = nil
            conversationGeneration += 1; measuredMessages = []; messages = restored; selectedEntity = nil; sessionID = session.id
            let newest = hydrated.last?.run ?? session.latest
            activeRunID = newest.isTerminal ? nil : newest.runId
            phase = activeRunID == nil ? .ready : .working; error = nil; persistSession()
            if let id = activeRunID { beginActivity(id) }
            else {
                // A reopened terminal turn keeps its diagnostics without reading history aloud.
                activeRunID = newest.runId
                beginActivity(newest.runId); quietActivityRootID = newest.runId
                await followActiveRun()
                guard epoch == generation else { return }
            }
            if preferences.showMessageStats { await loadMessageStats() }
        } catch { if epoch == generation { self.error = say(error); handle(error) } }
    }
    @discardableResult public func answer(_ wait: Wait, _ answer: WaitAnswer) async -> Bool {
        guard let client, !stopRequested, !deciding.contains(wait.id) else { return false }
        let epoch = generation; deciding.insert(wait.id)
        defer { if epoch == generation { deciding.remove(wait.id) } }
        do {
            if let entity = selectedEntity, activeEntityRunID == wait.runId {
                let approved: Bool
                switch answer { case .approve: approved = true; case .deny: approved = false; case .respond: throw PhoneAttachmentError.unsupported }
                _ = try await client.answerEntity(name: entity, runID: wait.runId, waitKey: wait.waitKey, approved: approved)
            } else { try await client.answer(wait, with: answer) }
            guard epoch == generation else { return false }
            waits.removeAll { $0.id == wait.id }; activityWaits.removeAll { $0.id == wait.id }; await followActiveRun(); return true
        } catch {
            if epoch == generation {
                self.error = say(error)
                if error as? GatewayError == .alreadyHandled { waits.removeAll { $0.id == wait.id } }
                handle(error)
            }
            return false
        }
    }
    public func canApproveAll(_ wait: Wait) -> Bool {
        wait.kind == .toolApproval && activityRunIDs.contains(wait.runId) && !(wait.details ?? []).isEmpty && legacySessionApprovalNames.isEmpty
    }
    /// Like the desktop assistant, conversation trust is client owned. The wire
    /// decision is still approved:true; no invented resume fields or endpoints.
    @discardableResult public func approveAll(_ wait: Wait) async -> Bool {
        guard canApproveAll(wait), !approvingAll.contains(wait.id), let client else { return false }
        approvingAll.insert(wait.id)
        defer { approvingAll.remove(wait.id) }
        let epoch = activityEpoch, key = toolsKey, selected = effectiveTools, revision = approvalTrustRevision
        do {
            let inventory: [ToolInfo]
            if let entity = selectedEntity { inventory = try await client.entityTools(name: entity) }
            else { inventory = try await client.tools() }
            guard epoch == activityEpoch, key == toolsKey, revision == approvalTrustRevision else { return false }
            let selection = ConversationTools.snapshot(selected, inventory: inventory)
            let enabled = Set(selection.allowed)
            guard let calls = wait.details, !calls.isEmpty, calls.allSatisfy({ enabled.contains($0.name) }) else {
                error = "Some requested tools are not enabled in this conversation. Review Tools before approving all."; return false
            }
            guard await answer(wait, .approve), epoch == activityEpoch, key == toolsKey,
                  revision == approvalTrustRevision else { return false }
            autoAnsweredWaits.insert(wait.id)
            let granted = sessionApprovalGrants.union(selection.modes.filter { $0.value == .approve }.keys)
            defaults.set(Array(granted).sorted(), forKey: key + ".approvalTrust")
            approvalTrustRevision += 1
            await followActiveRun()
            return true
        } catch {
            if epoch == activityEpoch { self.error = say(error); handle(error) }
            return false
        }
    }
    private func applyConversationTrust(epoch: UUID) async {
        guard let client else { return }
        let granted = sessionApprovalGrants
        guard !granted.isEmpty else { return }
        let key = toolsKey, revision = approvalTrustRevision
        activityWaits.removeAll { autoAnsweredWaits.contains($0.id) }
        waits.removeAll { activityRunIDs.contains($0.runId) && autoAnsweredWaits.contains($0.id) }
        guard activityWaits.contains(where: { $0.kind == .toolApproval && !($0.details ?? []).isEmpty }) else { return }
        // Refresh availability for every pending batch; trust never enables an Off,
        // unavailable or newly added tool and never answers a question.
        do {
            let inventory: [ToolInfo]
            if let entity = selectedEntity { inventory = try await client.entityTools(name: entity) }
            else { inventory = try await client.tools() }
            guard epoch == activityEpoch, key == toolsKey, revision == approvalTrustRevision else { return }
            let modes = ConversationTools.snapshot(effectiveTools, inventory: inventory).modes
            for wait in activityWaits {
                guard epoch == activityEpoch, key == toolsKey, revision == approvalTrustRevision, !stopRequested else { return }
                guard wait.kind == .toolApproval, let calls = wait.details, !calls.isEmpty,
                      calls.allSatisfy({ modes[$0.name] == .auto || (modes[$0.name] == .approve && granted.contains($0.name)) }) else { continue }
                if !autoAnsweredWaits.contains(wait.id) {
                    guard await answer(wait, .approve), epoch == activityEpoch else { continue }
                    autoAnsweredWaits.insert(wait.id)
                }
                activityWaits.removeAll { $0.id == wait.id }; waits.removeAll { $0.id == wait.id }
            }
        } catch { if epoch == activityEpoch { setActivityProblem("approval", "Automatic approval could not be sent. " + say(error)); handle(error) } }
    }
    public func automationAction(_ automation: AutomationSummary, runNow: Bool) async {
        guard let client, !automationBusy.contains(automation.id) else { return }
        error = nil
        let epoch = generation; automationBusy.insert(automation.id)
        defer { if epoch == generation { automationBusy.remove(automation.id) } }
        do {
            if runNow { try await client.runAutomationNow(id: automation.id) }
            else { try await client.automationCommand(id: automation.id, type: automation.status == "active" ? "automation.pause" : "automation.resume") }
            guard epoch == generation else { return }
            await refresh()
        } catch { if epoch == generation { self.error = say(error); handle(error) } }
    }
    @discardableResult public func setAutomationArchived(_ automation: AutomationSummary, _ archived: Bool) async -> Bool {
        guard let client, !automationBusy.contains(automation.id) else { return false }
        let epoch = generation
        automationBusy.insert(automation.id); automationArchiveRevision += 1; error = nil
        defer { if epoch == generation { automationBusy.remove(automation.id) } }
        do {
            try await client.automationCommand(id: automation.id, type: archived ? "automation.archive" : "automation.unarchive")
            guard epoch == generation else { return false }
            automations.removeAll { $0.id == automation.id }
            automationArchiveRevision += 1
            if !archived {
                let row = try await client.automation(id: automation.id)
                guard epoch == generation else { return false }
                rememberAutomation(row)
            }
            return true
        } catch { if epoch == generation { self.error = say(error); handle(error) }; return false }
    }
    public func rememberAutomation(_ row: AutomationSummary) { automations.removeAll { $0.id == row.id }; automations.insert(row, at: 0) }
    private func setActivityProblem(_ key: String, _ message: String?) {
        activityProblems[key] = message
        activityIssue = activityProblems.keys.sorted().compactMap { activityProblems[$0] }.first
    }
    private func resetActivity() {
        pauseActivityStreams()
        activityEpoch = UUID(); followingID = nil; quietActivityRootID = nil
        activity = RunActivity(); activityRootID = nil; activityState = .idle
        activityFailure = nil; activityIssue = nil; activityProblems = [:]; activityCheckedAt = nil; activitySummary = nil
        activityWaits = []; autoAnsweredWaits = []; activityWaitSteps = [:]; activityRunIDs = []; activityCursors = [:]; activityFinishedStreams = []
    }
    private func beginActivity(_ id: String) {
        if activityRootID == id { return }
        resetActivity(); activityRootID = id; activityRunIDs = [id]; activityState = .running
        startActivityStream(id)
    }
    private func pauseActivityStreams() {
        activityStreams.values.forEach { $0.cancel() }; activityStreams = [:]
    }
    private func ingestActivity(_ record: LedgerRecord, runID: String, cursor: Int) {
        guard cursor > (activityCursors[runID] ?? 0) else { return }
        if let key = record.result?["wait"]?["wait_key"]?.stringValue, let step = record.stepId {
            let id = runID + ":" + key
            if let previous = activityWaitSteps[id], previous != step { autoAnsweredWaits.remove(id) }
            activityWaitSteps[id] = step
        }
        activity.ingest(record, runID: runID, cursor: cursor)
        activityCursors[runID] = cursor
    }
    private func activityTree(root: RunSummary, client: any GatewayClient, epoch: UUID) async -> [RunSummary] {
        var queue: [(RunSummary, Int)] = [(root, 0)], rows: [RunSummary] = [], seen: Set<String> = []
        while !queue.isEmpty, rows.count < 64, epoch == activityEpoch {
            let (run, depth) = queue.removeFirst()
            guard seen.insert(run.runId).inserted else { continue }
            rows.append(run); activityRunIDs.insert(run.runId)
            guard depth < 16 else { setActivityProblem("children", "Some deeply nested activity is not shown."); continue }
            // The explicit child pointer works even on gateways without child-list filtering.
            if let id = run.waitingOnChild, !seen.contains(id) {
                do {
                    let child = try await client.run(id: id)
                    guard epoch == activityEpoch else { return [] }
                    if child.runId == id { queue.append((child, depth + 1)) }
                } catch {
                    guard epoch == activityEpoch else { return [] }
                    setActivityProblem("children", "Some agent activity could not be refreshed. " + say(error)); handle(error)
                }
            }
            do {
                let children = try await client.childRuns(ofRunID: run.runId)
                guard epoch == activityEpoch else { return [] }
                for child in children where child.parentRunId == run.runId && !seen.contains(child.runId) {
                    if queue.count + rows.count < 64 {
                        // Listing rows omit wait keys/details. Hydrate before surfacing decisions.
                        let full = try await client.run(id: child.runId)
                        guard epoch == activityEpoch else { return [] }
                        if full.runId == child.runId { queue.append((full, depth + 1)) }
                    }
                    else { setActivityProblem("children", "Showing the first 64 runs in this workflow."); break }
                }
            } catch GatewayError.http(status: 404, body: _) { /* explicit wait pointers remain supported */ }
            catch GatewayError.http(status: 400, body: _) { }
            catch {
                guard epoch == activityEpoch else { return [] }
                setActivityProblem("children", "Some agent activity could not be refreshed. " + say(error)); handle(error)
            }
        }
        return rows
    }
    private func startActivityStream(_ id: String) {
        guard foreground, selectedEntity == nil, let client, activityStreams[id] == nil, activityStreams.count < 4,
              !activityFinishedStreams.contains(id) else { return }
        let epoch = activityEpoch
        activityStreams[id] = Task { [weak self] in
            var retry = 0
            while !Task.isCancelled {
                guard let self, epoch == self.activityEpoch else { return }
                do {
                    let start = self.activityCursors[id] ?? 0
                    for try await event in client.ledgerEvents(runID: id, after: start) {
                        guard !Task.isCancelled, epoch == self.activityEpoch else { return }
                        switch event {
                        case .record(let cursor, let record):
                            self.ingestActivity(record, runID: id, cursor: cursor)
                            self.setActivityProblem("stream:" + id, nil); retry = 0
                            if record.result?["wait"] != nil {
                                Task { [weak self] in await self?.followActiveRun() }
                            }
                        case .done:
                            self.activityFinishedStreams.insert(id)
                            self.activityStreams.removeValue(forKey: id)
                            Task { [weak self] in await self?.followActiveRun() }
                            return
                        }
                    }
                    throw GatewayError.invalidResponse
                } catch {
                    guard !Task.isCancelled, epoch == self.activityEpoch else { return }
                    self.setActivityProblem("stream:" + id, "Activity connection lost. Reconnecting… " + self.say(error))
                    self.handle(error)
                    guard epoch == self.activityEpoch else { return }
                    retry += 1
                    do { try await Task.sleep(for: .seconds(min(10, retry * 2))) } catch { return }
                }
            }
        }
    }
    private func drainActivity(runID: String, entity: String?, epoch: UUID) async {
        guard let client else { return }
        do {
            // Each page cursor is a consumed record count, independent of step IDs.
            while epoch == activityEpoch, !Task.isCancelled {
                let cursor = activityCursors[runID] ?? (entity != nil ? entityActivityCursors[runID] ?? 0 : 0)
                let page: LedgerPage
                if let entity { page = try await client.entityLedger(name: entity, runID: runID, after: cursor) }
                else { page = try await client.ledger(runId: runID, after: cursor) }
                guard epoch == activityEpoch else { return }
                let next = page.nextAfter ?? cursor + page.items.count
                guard next == cursor + page.items.count else { throw LedgerStreamError.invalidCursor }
                for (index, record) in page.items.enumerated() { ingestActivity(record, runID: runID, cursor: cursor + index + 1) }
                if entity != nil { entityActivityCursors[runID] = next }
                setActivityProblem("drain:" + runID, nil); setActivityProblem("stream:" + runID, nil)
                if page.items.count < 200 { break }
            }
        } catch {
            guard epoch == activityEpoch, !(error is CancellationError) else { return }
            setActivityProblem("drain:" + runID, "Activity could not be loaded. " + say(error)); handle(error)
        }
    }
    public func refreshActivity() async {
        activityProblems = [:]; activityIssue = nil; activityFinishedStreams = []
        if activeRunID != nil || activeEntityRunID != nil { await followActiveRun() }
        else {
            let epoch = activityEpoch
            for id in activityRunIDs { await drainActivity(runID: id, entity: selectedEntity, epoch: epoch) }
        }
    }
    private func persistSession() {
        if let connection {
            defaults.set(sessionID, forKey: "phone.session." + connection.scope)
            if let selectedEntity { defaults.set(selectedEntity, forKey: "phone.entity." + connection.scope) }
            else { defaults.removeObject(forKey: "phone.entity." + connection.scope) }
        }
    }
    private func handle(_ error: Error) {
        guard error as? GatewayError == .unauthorized else { return }
        disconnect(); self.error = "Your sign-in has expired. Connect again to continue."; onUnauthorized?()
    }
    private func say(_ error: Error) -> String { error.localizedDescription }
}
