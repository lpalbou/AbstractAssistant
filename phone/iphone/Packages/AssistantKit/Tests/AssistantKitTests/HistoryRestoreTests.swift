import Foundation
import Testing
import AssistantKit
import PhoneGatewayClient

@Suite @MainActor struct HistoryRestoreTests {
    private func fixture() async throws -> (AssistantStore, HistoryClient, SessionSummary) {
        let rows = try [
            #"{"run_id":"turn1","session_id":"history","status":"completed","output":{"response":"First reply","reasoning":"SECRET REASONING"}}"#,
            #"{"run_id":"turn2","session_id":"history","status":"completed","output":{"response":"Second reply"}}"#,
            #"{"run_id":"child","parent_run_id":"turn1","session_id":"history","status":"completed","output":"INTERNAL CHILD"}"#,
            #"{"run_id":"root","session_id":"history","status":"completed","output":{"response":"New reply"}}"#
        ].map { try JSONDecoder().decode(RunSummary.self, from: Data($0.utf8)) }
        let client = HistoryClient(); await client.configure(rows)
        let store = AssistantStore(defaults: UserDefaults(suiteName: "history-restore-\(UUID())")!)
        store.connect(nil, client: client)
        let session = try #require(SessionSummary.group([rows[1], rows[0]]).first)
        return (store, client, session)
    }
    @Test func summaryWithoutOutputHydratesEveryRootAndStaysQuiet() async throws {
        let (store, client, session) = try await fixture()
        await store.openSession(session)
        #expect(store.messages.map(\.text) == ["Question turn1", "First reply", "Question turn2", "Second reply"])
        #expect(store.messages.filter { $0.role == .assistant }.count == 2)
        #expect(Set(await client.detailReads).isSuperset(of: ["turn1", "turn2"]))
        #expect(store.completedReply == nil)
        #expect(!store.messages.contains { $0.text.contains("SECRET") || $0.text.contains("INTERNAL") })
        store.disconnect()
    }
    @Test func staleRunningListUsesHydratedTerminalStateWithoutSpeaking() async throws {
        let (store, _, original) = try await fixture()
        var session = original; session.latest.status = "running"
        await store.openSession(session)
        await store.followActiveRun()
        #expect(store.completedReply == nil)
        #expect(store.phase == .ready)
        #expect(store.messages.map(\.text).suffix(2) == ["Question turn2", "Second reply"])
        store.disconnect()
    }
    @Test func newTurnSinceSessionListIsTheRestoredActivityRoot() async throws {
        let (store, client, session) = try await fixture()
        let newest = try JSONDecoder().decode(RunSummary.self, from: Data(#"{"run_id":"turn3","session_id":"history","status":"completed","output":{"response":"Third reply"}}"#.utf8))
        await client.append(newest)
        await store.openSession(session)
        #expect(store.activityRootID == "turn3")
        #expect(store.messages.last?.text == "Third reply")
        #expect(store.completedReply == nil)
        store.disconnect()
    }
    @Test func nextSendKeepsRestoredConversationAndOnlyNewReplyCompletes() async throws {
        let (store, _, session) = try await fixture()
        await store.openSession(session)
        store.send("Next question")
        for _ in 0..<1000 { if store.activeRunID == "root" { break }; await Task.yield() }
        await store.followActiveRun()
        #expect(store.messages.map(\.text) == ["Question turn1", "First reply", "Question turn2", "Second reply", "Next question", "New reply"])
        #expect(store.completedReply?.text == "New reply")
        store.disconnect()
    }
}

private actor HistoryClient: GatewayClient {
    nonisolated let isMock = true
    let mock = MockGatewayClient()
    var states: [String: RunSummary] = [:]
    func append(_ row: RunSummary) { states[row.runId] = row }
    func configure(_ rows: [RunSummary]) { states = Dictionary(uniqueKeysWithValues: rows.map { ($0.runId, $0) }) }
    func me() async throws -> Principal { try await mock.me() }
    func health() async throws -> Bool { true }
    func waits() async throws -> [Wait] { [] }
    func recentRuns(limit: Int) async throws -> [RunSummary] { states.values.filter { $0.parentRunId == nil } }
    func prompt(ofRun id: String) async throws -> String? { "Question " + id }
    func turns(ofSession id: String) async throws -> [RunSummary] {
        states.values.filter { $0.parentRunId == nil && $0.sessionId == id && $0.runId != "root" }
            .sorted { $0.runId > $1.runId }.map { row in var row = row; row.output = nil; return row }
    }
    var detailReads: [String] = []
    func run(id: String) async throws -> RunSummary {
        detailReads.append(id)
        let snapshot = states[id]!
        return snapshot
    }
    func childRuns(ofRunID id: String) async throws -> [RunSummary] { states.values.filter { $0.parentRunId == id } }
    nonisolated func ledgerEvents(runID: String, after: Int) -> AsyncThrowingStream<LedgerStreamEvent, Error> { AsyncThrowingStream { $0.finish() } }
    func startRun(prompt: String, sessionId: String?, toolPolicy: RunToolPolicy?) async throws -> String { "root" }
    func startRun(prompt: String, sessionId: String?, attachments: [JSONValue], tools: ConversationTools?) async throws -> String { "root" }
    func tools() async throws -> [ToolInfo] { [] }
    func answer(_ wait: Wait, with answer: WaitAnswer) async throws {}
    func automations() async throws -> [AutomationSummary] { try await mock.automations() }
    func runAutomationNow(id: String) async throws { try await mock.runAutomationNow(id: id) }
    func automationCommand(id: String, type: String) async throws { try await mock.automationCommand(id: id, type: type) }
    func automation(id: String) async throws -> AutomationSummary { try await mock.automation(id: id) }
    func workflows(forInterface interface: String) async throws -> [WorkflowChoice] { try await mock.workflows(forInterface: interface) }
    func workflowInputs(_ w: WorkflowChoice) async throws -> WorkflowInputs { try await mock.workflowInputs(w) }
    func createAutomation(_ a: NewAutomation) async throws -> AutomationSummary { try await mock.createAutomation(a) }
    func automationDefinition(id: String) async throws -> AutomationDefinition { try await mock.automationDefinition(id: id) }
    func reviseAutomation(id: String, changes: [String: JSONValue], expectedRevision: Int?) async throws { try await mock.reviseAutomation(id: id, changes: changes, expectedRevision: expectedRevision) }
    func entities() async throws -> [EntitySummary] { try await mock.entities() }
    func openEntityChat(name: String) async throws -> String { try await mock.openEntityChat(name: name) }
    func entityChatTurn(name: String, chatId: String, text: String) async throws -> String { try await mock.entityChatTurn(name: name, chatId: chatId, text: text) }
    func ledger(runId: String, after: Int) async throws -> LedgerPage {
        try JSONDecoder().decode(LedgerPage.self, from: Data(#"{"items":[],"next_after":0}"#.utf8))
    }
    func cancel(runId: String) async throws { try await mock.cancel(runId: runId) }
    func occurrences(automationId: String, limit: Int) async throws -> [LastOccurrence] { try await mock.occurrences(automationId: automationId, limit: limit) }
    func markSeen(automationId: String, cursor: String) async throws { try await mock.markSeen(automationId: automationId, cursor: cursor) }
    nonisolated func speech(text: String, scope: SpeechScope) -> AsyncThrowingStream<Data, Error> { AsyncThrowingStream { $0.finish() } }
    func transcribe(wav: Data, sessionId: String) async throws -> String { try await mock.transcribe(wav: wav, sessionId: sessionId) }
}
