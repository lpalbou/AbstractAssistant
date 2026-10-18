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
    public private(set) var activeEntityRunID: String?
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
    @ObservationIgnored private var entityVisitIDs: [String: String] = [:]
    @ObservationIgnored private var quietEntityRestoreID: String?
    @ObservationIgnored private var measuredMessages: Set<String> = []
    @ObservationIgnored private var toolSelections: [String: ConversationTools] = [:]
    private var restorationID: String?
    @ObservationIgnored private let defaults: UserDefaults
    @ObservationIgnored public var onUnauthorized: (@MainActor () -> Void)?

    public init(defaults: UserDefaults = .standard) { self.defaults = defaults }

    public func connect(_ connection: SavedConnection?, client: any GatewayClient) {
        disconnect()
        self.connection = connection; self.client = client
        preferences = PhonePreferences(scope: connection?.scope ?? "demo", defaults: defaults)
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
        if foreground { startPolling() }
    }
    public func disconnect() {
        contextID = UUID()
        generation += 1; conversationGeneration += 1
        poll?.cancel(); poll = nil; turn?.cancel(); turn = nil
        client = nil; connection = nil; principal = nil; messages = []; runs = []; waits = []; automations = []; entities = []
        titles = [:]; entityChatIDs = [:]; entityVisitIDs = [:]; toolSelections = [:]; measuredMessages = []; activeEntityRunID = nil; activeRunID = nil; selectedEntity = nil; restorationID = nil
        completedReply = nil; quietEntityRestoreID = nil
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
            guard epoch == generation else { return }; waits = newWaits + waits.filter { $0.runId == activeEntityRunID }
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
        completedReply = nil; quietEntityRestoreID = nil; error = nil
        conversationGeneration += 1; measuredMessages = []; messages = []; selectedEntity = entity; activeEntityRunID = nil; activeRunID = nil; restorationID = nil
        sessionID = "iphone-" + UUID().uuidString.lowercased(); persistSession()
    }
    private var toolsKey: String { "phone.tools." + (connection?.scope ?? "demo") + "." + (selectedEntity ?? "assistant") + "." + sessionID }
    public var conversationTools: ConversationTools? {
        if let selection = toolSelections[toolsKey] { return selection }
        guard let data = defaults.data(forKey: toolsKey) else { return nil }
        return try? JSONDecoder().decode(ConversationTools.self, from: data)
    }
    public func setConversationTools(_ tools: ConversationTools?) {
        guard canSend else { return }
        toolSelections[toolsKey] = tools
        if let tools, let data = try? JSONEncoder().encode(tools) { defaults.set(data, forKey: toolsKey) }
        else { defaults.removeObject(forKey: toolsKey) }
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
    public func send(_ text: String, attachments: [PhoneArtifact] = []) {
        let prompt = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard (!prompt.isEmpty || !attachments.isEmpty), canSend, let client else { return }
        if selectedEntity != nil && !attachments.isEmpty { error = "Files can be sent to Assistant conversations. Entity file messages are not supported by this gateway interface."; return }
        let epoch = generation, view = conversationGeneration, session = sessionID, entity = selectedEntity
        let tools = conversationTools
        messages.append(.init(role: .user, text: prompt + (attachments.isEmpty ? "" : "\n" + attachments.map { "📎 " + $0.filename }.joined(separator: "\n")))); phase = .sending; error = nil
        turn = Task {
            do {
                if let entity {
                    let key = entity + ":" + session
                    if let existing = entityVisitIDs[key] {
                        activeEntityRunID = existing
                        try await client.setEntityTools(name: entity, runID: existing, tools: tools)
                        guard epoch == generation, view == conversationGeneration else { return }
                        activeEntityRunID = existing
                        _ = try await client.sendEntityTurn(name: entity, runID: existing, text: prompt)
                        guard epoch == generation, view == conversationGeneration else { return }
                        activeEntityRunID = existing; phase = .working
                        await followEntitySession()
                    } else {
                        // Capability discovery precedes the write; older gateways keep ordinary chat,
                        // but explicit policies can never fall through to the legacy ungated API.
                        let supported: Bool
                        do { _ = try await client.entityTools(name: entity); supported = true }
                        catch GatewayError.http(status: 404, body: _) { supported = false }
                        catch PhoneAttachmentError.unsupported { supported = false }
                        if supported {
                            let state = try await client.openEntitySession(name: entity, sessionID: session, tools: tools)
                            guard epoch == generation, view == conversationGeneration else { return }
                            entityVisitIDs[key] = state.runID
                            if let connection { defaults.set(state.runID, forKey: "phone.visit." + connection.scope + "." + session) }
                            activeEntityRunID = state.runID
                            _ = try await client.sendEntityTurn(name: entity, runID: state.runID, text: prompt)
                            guard epoch == generation, view == conversationGeneration else { return }
                            activeEntityRunID = state.runID; phase = .working
                            await followEntitySession()
                        } else {
                            guard tools == nil else { throw PhoneAttachmentError.unsupported }
                            let chat: String
                            if let existing = entityChatIDs[entity] { chat = existing }
                            else { chat = try await client.openEntityChat(name: entity) }
                            guard epoch == generation, view == conversationGeneration else { return }
                            entityChatIDs[entity] = chat
                            let answer = try await client.entityChatTurn(name: entity, chatId: chat, text: prompt)
                            guard epoch == generation, view == conversationGeneration else { return }
                            let reply = ConversationMessage(role: .assistant, text: answer)
                            messages.append(reply); completedReply = reply; phase = .ready
                        }
                    }
                } else {
                    let id = try await client.startRun(prompt: prompt.isEmpty ? "Please review the attached files." : prompt, sessionId: session, attachments: attachments.map(\.ref), tools: tools)
                    guard epoch == generation, view == conversationGeneration else { return }
                    activeRunID = id; phase = .working
                    if foreground { await followActiveRun() }
                }
            } catch {
                guard epoch == generation, view == conversationGeneration else { return }
                phase = activeEntityRunID == nil ? .ready : .working
                self.error = say(error) + " Check Conversations before resending: the gateway may already have received your request."
                handle(error)
                if let id = activeEntityRunID { quietEntityRestoreID = id; await followEntitySession() }
            }
        }
    }
    public func followActiveRun() async {
        if activeEntityRunID != nil { await followEntitySession(); return }
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
                if preferences.showMessageStats { await loadMessageStats() }
            } else { phase = run.waitsOnPerson ? .waiting : .working }
            if let wait = run.personWait, !waits.contains(where: { $0.id == wait.id }) { waits.insert(wait, at: 0) }
        } catch { if epoch == generation, !(error is CancellationError) { self.error = say(error); handle(error) } }
    }
    private func followEntitySession() async {
        guard let client, let entity = selectedEntity, let id = activeEntityRunID else { return }
        let epoch = generation, view = conversationGeneration
        do {
            let state = try await client.entitySession(name: entity, runID: id)
            guard epoch == generation, view == conversationGeneration, activeEntityRunID == id else { return }
            if let wait = state.personWait {
                waits.removeAll { $0.runId == id }; waits.insert(wait, at: 0); phase = .waiting
            } else if state.finishedTurn {
                if state.status == "failed" { error = state.error ?? "The entity could not finish its reply." }
                waits.removeAll { $0.runId == id }
                if let text = state.reply, !text.isEmpty {
                    let messageID = id + "-turn-" + String(state.turn)
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
            } else { phase = .working }
        } catch {
            if epoch == generation, view == conversationGeneration, activeEntityRunID == id {
                if case GatewayError.http(status: 404, body: _) = error {
                    entityVisitIDs.removeValue(forKey: entity + ":" + sessionID)
                    if let connection { defaults.removeObject(forKey: "phone.visit." + connection.scope + "." + sessionID) }
                    activeEntityRunID = nil; quietEntityRestoreID = nil; phase = .ready
                }
                self.error = say(error); handle(error)
            }
        }
    }
    public func stopRun() async {
        if let id = activeEntityRunID, let entity = selectedEntity, let client {
            let epoch = generation, view = conversationGeneration
            do {
                try await client.endEntitySession(name: entity, runID: id)
                guard epoch == generation, view == conversationGeneration else { return }
                waits.removeAll { $0.runId == id }; entityVisitIDs.removeValue(forKey: entity + ":" + sessionID)
                if let connection { defaults.removeObject(forKey: "phone.visit." + connection.scope + "." + sessionID) }
                activeEntityRunID = nil; phase = .ready
                messages.append(.init(role: .notice, text: "Conversation stopped."))
            } catch { if epoch == generation { self.error = say(error); handle(error) } }
            return
        }
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
            if let entity = selectedEntity, let id = entityVisitIDs[entity + ":" + sessionID] {
                let oldSession = sessionID
                try await client.endEntitySession(name: entity, runID: id)
                guard epoch == generation else { return }
                entityVisitIDs.removeValue(forKey: entity + ":" + oldSession)
                if let connection { defaults.removeObject(forKey: "phone.visit." + connection.scope + "." + oldSession) }
            }
            activeEntityRunID = nil; quietEntityRestoreID = nil; completedReply = nil
            conversationGeneration += 1; measuredMessages = []; messages = restored; selectedEntity = nil; sessionID = session.id
            activeRunID = session.latest.isTerminal ? nil : session.latest.runId
            phase = activeRunID == nil ? .ready : .working; persistSession()
            if preferences.showMessageStats { await loadMessageStats() }
        } catch { if epoch == generation { self.error = say(error); handle(error) } }
    }
    @discardableResult public func answer(_ wait: Wait, _ answer: WaitAnswer) async -> Bool {
        guard let client, !deciding.contains(wait.id) else { return false }
        let epoch = generation; deciding.insert(wait.id)
        defer { if epoch == generation { deciding.remove(wait.id) } }
        do {
            if let entity = selectedEntity, activeEntityRunID == wait.runId {
                let approved: Bool
                switch answer { case .approve: approved = true; case .deny: approved = false; case .respond: throw PhoneAttachmentError.unsupported }
                _ = try await client.answerEntity(name: entity, runID: wait.runId, waitKey: wait.waitKey, approved: approved)
            } else { try await client.answer(wait, with: answer) }
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
