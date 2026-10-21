import Foundation
import Testing
import AssistantKit
import AbstractGatewayClient

@Suite @MainActor struct MediaConversationTests {
    private func fixture() async throws -> (AssistantStore, MediaClient, SessionSummary) {
        let rows = try [
            #"{"run_id":"turn1","session_id":"history","status":"completed","output":{"response":"First image","image_artifact":{"$artifact":"first","run_id":"turn1","content_type":"image/png"}}}"#,
            #"{"run_id":"turn2","session_id":"history","status":"completed","output":{"audio_artifact":{"$artifact":"voice","run_id":"turn2","content_type":"audio/wav"}}}"#,
            #"{"run_id":"root","session_id":"history","status":"completed","output":{"image_artifact":{"$artifact":"edited","run_id":"root","content_type":"image/png"}}}"#
        ].map { try JSONDecoder().decode(RunSummary.self, from: Data($0.utf8)) }
        let client = MediaClient(); await client.configure(rows)
        let store = AssistantStore(defaults: UserDefaults(suiteName: "media-test-\(UUID())")!); store.connect(nil, client: client)
        return (store, client, try #require(SessionSummary.group([rows[1], rows[0]]).first))
    }
    @Test func reloadKeepsMediaOnItsOwnReplyIncludingEmptyTextAndStaysQuiet() async throws {
        let (store, _, session) = try await fixture(); await store.openSession(session)
        let replies = store.messages.filter { $0.role == .assistant }
        #expect(replies.map { $0.artifacts.map(\.id) } == [["turn1:first"], ["turn2:voice"]])
        #expect(replies.last?.text == "")
        #expect(store.completedReply == nil)
        store.disconnect()
    }
    @Test func nextEditReusesRestoredImageAndMediaOnlyCompletionSurvives() async throws {
        let (store, client, session) = try await fixture(); await store.openSession(session)
        store.send("Make it blue")
        for _ in 0..<1000 { if store.activeRunID == "root" { break }; await Task.yield() }
        await store.followActiveRun()
        #expect(await client.primaryImages.first??["$artifact"] == .string("first"))
        #expect(store.messages.last?.artifacts.map(\.id) == ["root:edited"])
        #expect(store.completedReply?.artifacts.map(\.id) == ["root:edited"])
        store.disconnect()
    }
    @Test func uploadedSourceSurvivesReloadWhenAssistantOnlyReturnedText() async throws {
        let (store, client, session) = try await fixture()
        await client.restoreUploadedOnlyHistory()
        await store.openSession(session)
        #expect(store.messages.first?.artifacts.map(\.id) == ["session_memory_history:source"])
        store.send("Edit the photo")
        for _ in 0..<1000 { if store.activeRunID == "root" { break }; await Task.yield() }
        #expect(await client.primaryImages.first??["$artifact"] == .string("source"))
        store.disconnect()
    }
    @Test func cancelledHistoryRestoresAnEditablePromptAndResendsItsOriginalAttachments() async throws {
        let (store, client, session) = try await fixture()
        await client.restoreUploadedOnlyHistory()
        var cancelled = try await client.run(id: "turn1"); cancelled.status = "cancelled"
        await client.append(cancelled)
        await store.openSession(session)
        let original = try #require(store.messages.first(where: { $0.runID == "turn1" && $0.role == .user }))
        #expect(original.wasStopped && original.requestText == "Question turn1")
        #expect(original.artifacts.count == 1)
        #expect(store.messages.first(where: { $0.runID == "turn2" && $0.role == .user })?.wasStopped == false)
        #expect(!store.resendStoppedRequest(messageID: original.id, text: "Revised", attachments: original.artifacts, session: "other", context: store.contextID))
        #expect(!store.resendStoppedRequest(messageID: original.id, text: "Revised", attachments: original.artifacts, session: store.sessionID, context: UUID()))
        let foreign = PhoneArtifact(artifactId: "foreign", runId: "other", filename: "other.png", contentType: "image/png")
        #expect(!store.resendStoppedRequest(messageID: original.id, text: "Revised", attachments: [foreign], session: store.sessionID, context: store.contextID))
        #expect(store.resendStoppedRequest(messageID: original.id, text: "Revised", attachments: original.artifacts, session: store.sessionID, context: store.contextID))
        #expect(!store.resendStoppedRequest(messageID: original.id, text: "Duplicate", attachments: [], session: store.sessionID, context: store.contextID))
        #expect(store.messages.first(where: { $0.id == original.id }) == original)
        let resent = try #require(store.messages.last(where: { $0.role == .user }))
        #expect(resent.requestText == "Revised" && resent.artifacts == original.artifacts)
        #expect(resent.text.components(separatedBy: "📎").count == 2)
        for _ in 0..<1000 { if store.activeRunID == "root" { break }; await Task.yield() }
        #expect(await client.primaryImages.first??["$artifact"] == .string("source"))
        store.disconnect()
    }
    @Test func newUploadWinsOverOldGeneratedImage() async throws {
        let (store, client, session) = try await fixture(); await store.openSession(session)
        store.send("Edit this", attachments: [.init(artifactId: "upload", runId: "session_memory_history", filename: "new.png", contentType: "image/png")])
        for _ in 0..<1000 { if store.activeRunID == "root" { break }; await Task.yield() }
        #expect(await client.primaryImages.first??["$artifact"] == .string("upload"))
        store.disconnect()
    }
}

private actor MediaClient: GatewayClient {
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
    var restoredUpload: PhoneArtifact?
    func restoreUploadedOnlyHistory() {
        states["turn1"]?.output = .object(["response": .string("I see the photo")])
        restoredUpload = .init(artifactId: "source", runId: "session_memory_history", filename: "source.png", contentType: "image/png")
    }
    func input(ofRun id: String) async throws -> ConversationInput {
        .init(prompt: "Question " + id, attachments: id == "turn1" ? restoredUpload.map { [$0] } ?? [] : [])
    }
    var primaryImages: [JSONValue?] = []
    func startRun(prompt: String, sessionId: String?, attachments: [JSONValue], tools: ConversationTools?) async throws -> String { "root" }
    func startRun(prompt: String, sessionId: String?, attachments: [JSONValue], tools: ConversationTools?, primaryImage: JSONValue?) async throws -> String { primaryImages.append(primaryImage); return "root" }
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
