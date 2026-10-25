import Foundation
import Testing
import AssistantKit
import AbstractGatewayClient

@Test func gatewayAddressesCannotCarryCredentialsOrDowngradeInternetTraffic() throws {
    #expect(try SavedConnection.parseURL("gateway.example.org/console").absoluteString == "https://gateway.example.org")
    #expect(try SavedConnection.parseURL("http://192.168.1.50:8080").host == "192.168.1.50")
    for value in ["http://gateway.example.org", "http://10.evil.example", "https://token@gateway.example.org", "https://gateway.example.org?token=secret", "https://gateway.example.org/#secret", "https://gateway.example.org/another/app"] {
        #expect(throws: ConnectionError.self) { try SavedConnection.parseURL(value) }
    }
}

@Test func sessionPreferenceKeysAreScopedToGatewayTenantAndUser() throws {
    let url = try SavedConnection.parseURL("https://one.example.org")
    let alice = SavedConnection(gateway: url, user: "alice", credential: .token("secret"))
    let bob = SavedConnection(gateway: url, user: "bob", credential: .token("secret"))
    #expect(alice.scope != bob.scope)
    #expect(!alice.scope.contains("secret"))
    #expect(alice.scope != SavedConnection(gateway: URL(string: "https://two.example.org")!, user: "alice", credential: .token("secret")).scope)
}

@Test func assistantWorkflowHonorsTheAccountAndFailsClosed() throws {
    let defaultRow: JSONValue = .object(["apps": .array([.object(["interface": .string("abstractassistant.agent.v1"), "value": .null,
        "effective": .object(["available": .bool(true)])])])])
    let inherited = try AssistantWorkflow.request(prompt: "hello", sessionId: "phone-1", toolPolicy: nil, preferences: defaultRow)
    #expect(inherited.flowId == "@default" && inherited.interface == "abstractassistant.agent.v1")
    let explicit: JSONValue = .object(["apps": .array([.object(["interface": .string("abstractassistant.agent.v1"), "value": .string("catalog:personal:agent"),
        "effective": .object(["available": .bool(true), "flow_id": .string("agent"), "bundle_id": .string("personal"), "bundle_version": .string("2.0"), "registry_scope": .string("user_catalog")])])])])
    let chosen = try AssistantWorkflow.request(prompt: "hello", sessionId: "phone-1", toolPolicy: nil, preferences: explicit)
    #expect(chosen.bundleId == "personal" && chosen.registryScope == "user_catalog" && chosen.flowId == "agent")
    #expect(throws: GatewayError.self) { try AssistantWorkflow.request(prompt: "hello", sessionId: nil, toolPolicy: nil, preferences: .object([:])) }
}

@Test @MainActor func restoringAConversationRestoresItsVisibleHistory() async throws {
    let defaults = UserDefaults(suiteName: "phone-test-\(UUID())")!
    let connection = SavedConnection(gateway: URL(string: "https://gateway.example")!, user: "alice", credential: .token("test"))
    defaults.set("s-adtte", forKey: "phone.session." + connection.scope)
    let store = AssistantStore(defaults: defaults)
    store.connect(connection, client: MockGatewayClient())
    #expect(!store.canSend && store.isRestoring)
    await store.refresh()
    #expect(store.sessionID == "s-adtte")
    #expect(!store.messages.isEmpty && !store.isRestoring)
    #expect(store.completedReply == nil)
    store.disconnect()
    #expect(store.messages.isEmpty && store.runs.isEmpty && store.waits.isEmpty)
}

@Test @MainActor func aLateAccountRefreshCannotPopulateTheNextAccount() async {
    let gate = SuspendedClient()
    let store = AssistantStore(defaults: UserDefaults(suiteName: "phone-test-\(UUID())")!)
    store.connect(nil, client: gate)
    let pending = Task { await store.refresh() }
    while !(await gate.waiting) { await Task.yield() }
    store.disconnect(); store.connect(nil, client: MockGatewayClient())
    await gate.release()
    await pending.value
    #expect(store.principal == nil && store.runs.isEmpty && !store.isRefreshing)
    await store.refresh()
    #expect(store.principal?.userId == "albou")
}

@Test @MainActor func expiredSignInInvalidatesTheClientOnce() async {
    let store = AssistantStore()
    store.connect(nil, client: MockGatewayClient())
    var invalidations = 0
    store.onUnauthorized = { invalidations += 1 }
    store.authenticationExpired()
    await store.refresh()
    #expect(invalidations == 1 && !store.isConnected && store.messages.isEmpty)
}

private actor SuspendedClient: GatewayClient {
    nonisolated let isMock = true
    var waiting = false
    var continuation: CheckedContinuation<Void, Never>?
    let mock = MockGatewayClient()
    func release() { continuation?.resume(); continuation = nil }
    func me() async throws -> Principal { await withCheckedContinuation { continuation = $0; waiting = true }; return Principal(userId: "old-account", tenantId: "default", roles: ["user"]) }
    func health() async throws -> Bool { true }
    func waits() async throws -> [Wait] { try await mock.waits() }
    func recentRuns(limit: Int) async throws -> [RunSummary] { try await mock.recentRuns(limit: limit) }
    func prompt(ofRun id: String) async throws -> String? { try await mock.prompt(ofRun: id) }
    func turns(ofSession id: String) async throws -> [RunSummary] { try await mock.turns(ofSession: id) }
    func run(id: String) async throws -> RunSummary { try await mock.run(id: id) }
    func startRun(prompt: String, sessionId: String?, toolPolicy: RunToolPolicy?) async throws -> String { try await mock.startRun(prompt: prompt, sessionId: sessionId, toolPolicy: toolPolicy) }
    func tools() async throws -> [ToolInfo] { try await mock.tools() }
    func answer(_ wait: Wait, with answer: WaitAnswer) async throws { try await mock.answer(wait, with: answer) }
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
    func ledger(runId: String, after: Int) async throws -> LedgerPage { try await mock.ledger(runId: runId, after: after) }
    func cancel(runId: String) async throws { try await mock.cancel(runId: runId) }
    func occurrences(automationId: String, limit: Int) async throws -> [LastOccurrence] { try await mock.occurrences(automationId: automationId, limit: limit) }
    func markSeen(automationId: String, cursor: String) async throws { try await mock.markSeen(automationId: automationId, cursor: cursor) }
    nonisolated func speech(text: String, scope: SpeechScope) -> AsyncThrowingStream<Data, Error> { AsyncThrowingStream { $0.finish() } }
    func transcribe(wav: Data, sessionId: String) async throws -> String { try await mock.transcribe(wav: wav, sessionId: sessionId) }
}

@Test @MainActor func stoppingBeforeRunIDWaitsAndCancelsOnceEvenWithRepeatedTaps() async {
    let client = StoppingClient(stage: "start")
    let store = AssistantStore(defaults: UserDefaults(suiteName: "phone-stop-\(UUID())")!)
    store.connect(nil, client: client); store.send("hello")
    while !(await client.waiting) { await Task.yield() }
    let first = Task { await store.stopRun() }
    while !store.isStopping { await Task.yield() }
    let second = Task { await store.stopRun() }
    #expect(store.canStop && !store.canSend)
    await client.release(); await first.value; await second.value
    #expect(await client.cancels == 1)
    #expect(store.phase == .ready && !store.isStopping && !store.canStop)
    #expect(store.activeRunID == nil && store.completedReply == nil)
    #expect(store.messages.first?.wasStopped == true && store.messages.first?.requestText == "hello")
    #expect(store.messages.first?.runID == "root")
}

@Test @MainActor func stoppedEntityOpenClosesTheVisitWithoutSendingAPrompt() async {
    let client = StoppingClient(stage: "open")
    let store = AssistantStore(defaults: UserDefaults(suiteName: "phone-stop-\(UUID())")!)
    store.connect(nil, client: client); store.newConversation(entity: "atlas"); store.send("hello")
    while !(await client.waiting) { await Task.yield() }
    let stopping = Task { await store.stopRun() }
    while !store.isStopping { await Task.yield() }
    await client.release(); await stopping.value
    #expect(await client.ends == 1)
    #expect(await client.entityTurns == 0)
    #expect(store.activeEntityRunID == nil && store.phase == .ready && store.completedReply == nil)
}

@Test @MainActor func stoppedEntityTurnRetriesLeaseConflictAndLateReplyCannotRestartIt() async throws {
    let client = StoppingClient(stage: "turn", conflictOnce: true)
    let store = AssistantStore(defaults: UserDefaults(suiteName: "phone-stop-\(UUID())")!)
    store.connect(nil, client: client); store.newConversation(entity: "atlas"); store.send("hello")
    while !(await client.waiting) { await Task.yield() }
    let stopping = Task { await store.stopRun() }
    while await client.ends == 0 { await Task.yield() }
    #expect(store.isStopping && store.activeEntityRunID == "visit" && !store.canSend)
    await stopping.value
    #expect(await client.ends == 2)
    await client.release()
    for _ in 0..<30 { await Task.yield() }
    #expect(store.activeEntityRunID == nil && store.phase == .ready && store.completedReply == nil && store.canSend)
    #expect(!store.messages.contains { $0.role == .assistant })
}

@Test @MainActor func stoppedEntityPolicyDoesNotSendAnotherTurn() async {
    let client = StoppingClient(stage: "policy")
    let defaults = UserDefaults(suiteName: "phone-stop-\(UUID())")!
    let connection = SavedConnection(gateway: URL(string: "https://gateway.example")!, user: "alice", credential: .token("test"))
    defaults.set("session", forKey: "phone.session." + connection.scope)
    defaults.set("atlas", forKey: "phone.entity." + connection.scope)
    defaults.set("visit", forKey: "phone.visit." + connection.scope + ".session")
    let store = AssistantStore(defaults: defaults); store.connect(connection, client: client)
    await store.followActiveRun(); store.send("hello")
    while !(await client.waiting) { await Task.yield() }
    let stopping = Task { await store.stopRun() }
    await stopping.value
    await client.release()
    for _ in 0..<20 { await Task.yield() }
    #expect(await client.entityTurns == 0)
    #expect(await client.ends == 1)
    #expect(store.activeEntityRunID == nil && store.completedReply == nil)
}

@Test @MainActor func aReplyThatFinishesBeforeStopIsNotMarkedAsCancelledForEditing() async {
    let client = StoppingClient(stage: "start", completesBeforeStop: true)
    let store = AssistantStore(defaults: UserDefaults(suiteName: "phone-stop-\(UUID())")!)
    store.connect(nil, client: client); store.send("already finished")
    while !(await client.waiting) { await Task.yield() }
    let stopping = Task { await store.stopRun() }
    while !store.isStopping { await Task.yield() }
    await client.release(); await stopping.value
    #expect(store.messages.first?.wasStopped == false)
    #expect(store.canSend)
}

private actor StoppingClient: GatewayClient {
    let stage: String
    var cancels = 0, ends = 0, entityTurns = 0
    var conflictOnce: Bool
    let completesBeforeStop: Bool
    init(stage: String, conflictOnce: Bool = false, completesBeforeStop: Bool = false) { self.stage = stage; self.conflictOnce = conflictOnce; self.completesBeforeStop = completesBeforeStop }
    private func gate(_ point: String) async { if stage == point { await withCheckedContinuation { continuation = $0; waiting = true } } }
    private func state(_ status: String = "waiting") throws -> EntitySessionState {
        try JSONDecoder().decode(EntitySessionState.self, from: Data("{\"run_id\":\"visit\",\"status\":\"\(status)\",\"turn_n\":1,\"turn_complete\":true,\"reply\":\"Late answer\"}".utf8))
    }
    func entityTools(name: String) async throws -> [ToolInfo] { [] }
    func openEntitySession(name: String, sessionID: String, tools: ConversationTools?) async throws -> EntitySessionState { await gate("open"); return try state() }
    func setEntityTools(name: String, runID: String, tools: ConversationTools?) async throws { await gate("policy") }
    func sendEntityTurn(name: String, runID: String, text: String) async throws -> JSONValue { entityTurns += 1; await gate("turn"); return .object([:]) }
    func entitySession(name: String, runID: String) async throws -> EntitySessionState { try state() }
    func endEntitySession(name: String, runID: String) async throws { ends += 1; if conflictOnce { conflictOnce = false; throw GatewayError.http(status: 409, body: "busy") } }
    nonisolated let isMock = true
    var waiting = false
    var continuation: CheckedContinuation<Void, Never>?
    let mock = MockGatewayClient()
    func release() { continuation?.resume(); continuation = nil }
    func me() async throws -> Principal { try await mock.me() }
    func health() async throws -> Bool { true }
    func waits() async throws -> [Wait] { if cancels == 1 { await gate("stop-cleanup") }; return try await mock.waits() }
    func recentRuns(limit: Int) async throws -> [RunSummary] { try await mock.recentRuns(limit: limit) }
    func prompt(ofRun id: String) async throws -> String? { try await mock.prompt(ofRun: id) }
    func turns(ofSession id: String) async throws -> [RunSummary] { try await mock.turns(ofSession: id) }
    func run(id: String) async throws -> RunSummary { RunSummary(runId: id, workflowId: nil, status: cancels > 0 && !completesBeforeStop ? "cancelled" : "completed", output: .string("Late answer")) }
    func startRun(prompt: String, sessionId: String?, toolPolicy: RunToolPolicy?) async throws -> String { if stage.hasPrefix("start") { await gate(stage) }; if stage == "start-fail" { throw GatewayError.invalidResponse }; return "root" }
    func tools() async throws -> [ToolInfo] { try await mock.tools() }
    func answer(_ wait: Wait, with answer: WaitAnswer) async throws { try await mock.answer(wait, with: answer) }
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
    func ledger(runId: String, after: Int) async throws -> LedgerPage { try await mock.ledger(runId: runId, after: after) }
    func cancel(runId: String) async throws { cancels += 1 }
    func occurrences(automationId: String, limit: Int) async throws -> [LastOccurrence] { try await mock.occurrences(automationId: automationId, limit: limit) }
    func markSeen(automationId: String, cursor: String) async throws { try await mock.markSeen(automationId: automationId, cursor: cursor) }
    nonisolated func speech(text: String, scope: SpeechScope) -> AsyncThrowingStream<Data, Error> { AsyncThrowingStream { $0.finish() } }
    func transcribe(wav: Data, sessionId: String) async throws -> String { try await mock.transcribe(wav: wav, sessionId: sessionId) }
}

@Test @MainActor func anUnknownStartCanBeRecoveredFromConversationsAfterStop() async {
    let client = StoppingClient(stage: "start-fail")
    let store = AssistantStore(defaults: UserDefaults(suiteName: "phone-stop-\(UUID())")!)
    store.connect(nil, client: client); store.send("hello")
    while !(await client.waiting) { await Task.yield() }
    let stopping = Task { await store.stopRun() }
    while !store.isStopping { await Task.yield() }
    await client.release(); await stopping.value
    #expect(!store.isStopping && store.canStop && !store.canSend)
    #expect(store.error?.contains("could not be confirmed") == true)
    await store.refresh()
    if let previous = store.sessions.first(where: { $0.latest.isTerminal }) { await store.openSession(previous) }
    #expect(store.phase == .ready && store.canSend && store.error == nil)
}

@Test func mockCancellationRemainsAConfirmedTerminalRun() async throws {
    let client = MockGatewayClient()
    let id = try await client.startRun(prompt: "hello", sessionId: nil, toolPolicy: nil)
    try await client.cancel(runId: id)
    let run = try await client.run(id: id)
    #expect(run.status == "cancelled" && run.isTerminal && run.error == nil)
}

@Test @MainActor func aNewTurnStopIsNotLostWhileThePriorWorkerCompletes() async {
    let client = StoppingClient(stage: "stop-cleanup")
    let store = AssistantStore(defaults: UserDefaults(suiteName: "phone-stop-\(UUID())")!)
    store.connect(nil, client: client); store.send("first")
    while store.activeRunID == nil { await Task.yield() }
    let first = Task { await store.stopRun() }
    while !(await client.waiting) { await Task.yield() }
    #expect(store.isStopping && !store.canSend)
    await client.release()
    while !store.canSend { await Task.yield() }
    store.send("second")
    let second = Task { await store.stopRun() }
    await first.value; await second.value
    #expect(!store.canStop && store.canSend && store.completedReply == nil)
    // Depending on scheduling, Stop precedes the second POST entirely or
    // cancels its returned run; both must leave no new work active.
    #expect(await client.cancels >= 1)
}

@Test @MainActor func automationArchiveAndRestorePreserveTheAutomation() async throws {
    let client = MockGatewayClient()
    let store = AssistantStore(defaults: UserDefaults(suiteName: "automation-archive-" + UUID().uuidString)!)
    store.connect(nil, client: client)
    await store.refresh()
    let row = try #require(store.automations.first)
    #expect(await store.setAutomationArchived(row, true))
    #expect(!store.automations.contains { $0.id == row.id })
    let archived = try await client.archivedAutomations()
    #expect(archived.contains { $0.id == row.id })
    #expect(await store.setAutomationArchived(row, false))
    #expect(store.automations.contains { $0.id == row.id && $0.status == "paused" })
    #expect(try await client.archivedAutomations().isEmpty)
    store.disconnect()
}
