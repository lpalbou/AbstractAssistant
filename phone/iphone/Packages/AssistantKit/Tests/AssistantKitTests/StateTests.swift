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
