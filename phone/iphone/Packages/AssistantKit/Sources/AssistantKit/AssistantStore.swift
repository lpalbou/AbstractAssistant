import Foundation
import Observation
import AbstractGatewayClient

@MainActor @Observable
public final class AssistantStore {
    public enum Phase: String { case ready, sending, working, waiting }
    public var preferences = PhonePreferences()
    public private(set) var contextID = UUID()
    public private(set) var completedReply: ConversationMessage?
    public private(set) var client: (any GatewayClient)?
    public private(set) var connection: SavedConnection?
    public private(set) var principal: Principal?
    public private(set) var phase: Phase = .ready
    public private(set) var messages: [ConversationMessage] = []
    public private(set) var runs: [RunSummary] = []
    public private(set) var waits: [Wait] = []
    public private(set) var automations: [AutomationSummary] = []
    public private(set) var entitiesError: String?
    public private(set) var loadingEntities = false
    public private(set) var entities: [EntitySummary] = []
    public private(set) var sessionID = "iphone-" + UUID().uuidString.lowercased()
    public private(set) var activeRunID: String?
    public private(set) var selectedEntity: String?
    public private(set) var error: String?
    public private(set) var automationsError: String?
    public private(set) var lastRefresh: Date?
    public private(set) var isRefreshing = false
    public private(set) var isOpening = false
    public private(set) var deciding: Set<String> = []
    public private(set) var automationBusy: Set<String> = []
    public private(set) var titles: [String: String] = [:]
    public var isDemo: Bool { client?.isMock == true }
    public var isConnected: Bool { client != nil }
    public var sessions: [SessionSummary] { SessionSummary.group(runs) }
    public var canSend: Bool { client != nil && phase == .ready && !isOpening && restorationID == nil }
    public var isRestoring: Bool { restorationID != nil }
    public var conversationTitle: String { selectedEntity.map { name in entities.first { $0.name == name }?.displayName ?? name.capitalized } ?? "Assistant" }
    @ObservationIgnored private var generation = 0
    @ObservationIgnored private var conversationGeneration = 0
    @ObservationIgnored private var foreground = false
    @ObservationIgnored private var poll: Task<Void, Never>?
    @ObservationIgnored private var turn: Task<Void, Never>?
    @ObservationIgnored private var entityChatIDs: [String: String] = [:]
    private var restorationID: String?
    @ObservationIgnored private let defaults: UserDefaults
    @ObservationIgnored public var onUnauthorized: (@MainActor () -> Void)?

    public init(defaults: UserDefaults = .standard) { self.defaults = defaults }

    public func connect(_ connection: SavedConnection?, client: any GatewayClient) {
        disconnect()
        self.connection = connection; self.client = client
        preferences = PhonePreferences(scope: connection?.scope ?? "demo", defaults: defaults)
        if let connection { restorationID = defaults.string(forKey: "phone.session." + connection.scope) }
        if restorationID == nil { persistSession() }
        if foreground { startPolling() }
    }
    public func disconnect() {
        contextID = UUID()
        generation += 1; conversationGeneration += 1
        poll?.cancel(); poll = nil; turn?.cancel(); turn = nil
        client = nil; connection = nil; principal = nil; messages = []; runs = []; waits = []; automations = []; entities = []
        titles = [:]; entityChatIDs = [:]; activeRunID = nil; selectedEntity = nil; restorationID = nil
        completedReply = nil
        phase = .ready; error = nil; automationsError = nil; entitiesError = nil; loadingEntities = false; lastRefresh = nil; isRefreshing = false; isOpening = false
        deciding = []; automationBusy = []; sessionID = "iphone-" + UUID().uuidString.lowercased()
    }
    public func setForeground(_ value: Bool) {
        foreground = value
        if value { startPolling() } else { poll?.cancel(); poll = nil }
    }
    private func startPolling() {
        guard poll == nil, client != nil else { return }
        poll = Task { [weak self] in
            var ticks = 0
            while !Task.isCancelled, let self, self.client != nil {
                if ticks % 5 == 0 { await self.refresh() }
                await self.followActiveRun()
                ticks += 1
                do { try await Task.sleep(for: .seconds(3)) } catch { break }
            }
        }
    }
    public func refresh() async {
        guard let client, !isRefreshing else { return }
        let epoch = generation
        isRefreshing = true
        defer { if epoch == generation { isRefreshing = false } }
        do {
            let me = try await client.me()
            guard epoch == generation else { return }; principal = me
            let newWaits = try await client.waits()
            guard epoch == generation else { return }; waits = newWaits
            let newRuns = try await client.recentRuns(limit: 60)
            guard epoch == generation else { return }; runs = newRuns
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
                guard epoch == generation else { return }; automations = rows; automationsError = nil
            } catch { guard epoch == generation else { return }; automationsError = say(error); handle(error) }
            guard epoch == generation else { return }
            await loadEntities()
            // Titles are a small, rebuildable cache, never a new source of conversation history.
            for session in sessions.prefix(8) where titles[session.id] == nil {
                guard epoch == generation, !Task.isCancelled else { return }
                if let prompt = try? await client.prompt(ofRun: session.firstRunId), epoch == generation {
                    titles[session.id] = SessionSummary.title(fromPrompt: prompt, limit: 70)
                }
            }
        } catch { if epoch == generation, !(error is CancellationError) { self.error = say(error); handle(error) } }
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
        completedReply = nil
        conversationGeneration += 1; messages = []; selectedEntity = entity; activeRunID = nil; restorationID = nil
        sessionID = "iphone-" + UUID().uuidString.lowercased(); persistSession()
    }
    public func send(_ text: String, attachments: [PhoneArtifact] = []) {
        let prompt = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard (!prompt.isEmpty || !attachments.isEmpty), canSend, let client else { return }
        if selectedEntity != nil && !attachments.isEmpty { error = "Files can be sent to Assistant conversations. Entity file messages are not supported by this gateway interface."; return }
        let epoch = generation, view = conversationGeneration, session = sessionID, entity = selectedEntity
        messages.append(.init(role: .user, text: prompt + (attachments.isEmpty ? "" : "\n" + attachments.map { "📎 " + $0.filename }.joined(separator: "\n")))); phase = .sending; error = nil
        turn = Task {
            do {
                if let entity {
                    let chat: String
                    if let existing = entityChatIDs[entity] { chat = existing }
                    else { chat = try await client.openEntityChat(name: entity) }
                    guard epoch == generation, view == conversationGeneration else { return }
                    entityChatIDs[entity] = chat
                    let answer = try await client.entityChatTurn(name: entity, chatId: chat, text: prompt)
                    guard epoch == generation, view == conversationGeneration else { return }
                    let reply = ConversationMessage(role: .assistant, text: answer)
                    messages.append(reply); completedReply = reply; phase = .ready
                } else {
                    let id = try await client.startRun(prompt: prompt.isEmpty ? "Please review the attached files." : prompt, sessionId: session, attachments: attachments.map(\.ref))
                    guard epoch == generation, view == conversationGeneration else { return }
                    activeRunID = id; phase = .working
                    if foreground { await followActiveRun() }
                }
            } catch {
                guard epoch == generation, view == conversationGeneration else { return }
                phase = .ready
                self.error = say(error) + " Check Conversations before resending: the gateway may already have received your request."
                handle(error)
            }
        }
    }
    public func followActiveRun() async {
        guard foreground, let client, let id = activeRunID else { return }
        let epoch = generation, view = conversationGeneration
        do {
            let run = try await client.run(id: id)
            guard epoch == generation, view == conversationGeneration, activeRunID == id else { return }
            if let output = run.outputText, !output.isEmpty {
                if let index = messages.firstIndex(where: { $0.id == "answer-" + id }) { messages[index].text = output }
                else { messages.append(.init(id: "answer-" + id, role: .assistant, text: output, runID: id)) }
            }
            if run.isTerminal {
                if run.status == "completed", let reply = messages.first(where: { $0.id == "answer-" + id }) { completedReply = reply }
                if run.status == "failed" { error = run.error ?? "The run stopped. Open Conversations for details." }
                if run.status == "cancelled" { messages.append(.init(role: .notice, text: "Run stopped.")) }
                phase = .ready; activeRunID = nil
            } else { phase = run.waitsOnPerson ? .waiting : .working }
            if let wait = run.personWait, !waits.contains(where: { $0.id == wait.id }) { waits.insert(wait, at: 0) }
        } catch { if epoch == generation, !(error is CancellationError) { self.error = say(error); handle(error) } }
    }
    public func stopRun() async {
        guard let id = activeRunID, let client else { return }
        let epoch = generation
        do { try await client.cancel(runId: id); if epoch == generation { await followActiveRun() } }
        catch { if epoch == generation { self.error = say(error); handle(error) } }
    }
    public func openSession(_ session: SessionSummary) async {
        guard phase == .ready, !isOpening, let client else { return }
        let epoch = generation
        isOpening = true
        defer { if epoch == generation { isOpening = false } }
        do {
            let turns = try await client.turns(ofSession: session.id)
            var restored: [ConversationMessage] = []
            for run in turns.reversed() {
                let prompt = try await client.prompt(ofRun: run.runId)
                if let prompt { restored.append(.init(id: "prompt-" + run.runId, role: .user, text: prompt, runID: run.runId)) }
                if let answer = run.outputText { restored.append(.init(id: "answer-" + run.runId, role: .assistant, text: answer, runID: run.runId)) }
            }
            guard epoch == generation else { return }
            conversationGeneration += 1; messages = restored; selectedEntity = nil; sessionID = session.id
            activeRunID = session.latest.isTerminal ? nil : session.latest.runId
            phase = activeRunID == nil ? .ready : .working; persistSession()
        } catch { if epoch == generation { self.error = say(error); handle(error) } }
    }
    @discardableResult public func answer(_ wait: Wait, _ answer: WaitAnswer) async -> Bool {
        guard let client, !deciding.contains(wait.id) else { return false }
        let epoch = generation; deciding.insert(wait.id)
        defer { if epoch == generation { deciding.remove(wait.id) } }
        do {
            try await client.answer(wait, with: answer)
            guard epoch == generation else { return false }
            waits.removeAll { $0.id == wait.id }; await followActiveRun(); return true
        } catch {
            if epoch == generation {
                self.error = say(error)
                if error as? GatewayError == .alreadyHandled { waits.removeAll { $0.id == wait.id } }
                handle(error)
            }
            return false
        }
    }
    public func automationAction(_ automation: AutomationSummary, runNow: Bool) async {
        guard let client, !automationBusy.contains(automation.id) else { return }
        let epoch = generation; automationBusy.insert(automation.id)
        defer { if epoch == generation { automationBusy.remove(automation.id) } }
        do {
            if runNow { try await client.runAutomationNow(id: automation.id) }
            else { try await client.automationCommand(id: automation.id, type: automation.status == "active" ? "automation.pause" : "automation.resume") }
            guard epoch == generation else { return }
            await refresh()
        } catch { if epoch == generation { self.error = say(error); handle(error) } }
    }
    public func rememberAutomation(_ row: AutomationSummary) { automations.removeAll { $0.id == row.id }; automations.insert(row, at: 0) }
    private func persistSession() { if let connection { defaults.set(sessionID, forKey: "phone.session." + connection.scope) } }
    private func handle(_ error: Error) {
        guard error as? GatewayError == .unauthorized else { return }
        disconnect(); self.error = "Your sign-in has expired. Connect again to continue."; onUnauthorized?()
    }
    private func say(_ error: Error) -> String { error.localizedDescription }
}
