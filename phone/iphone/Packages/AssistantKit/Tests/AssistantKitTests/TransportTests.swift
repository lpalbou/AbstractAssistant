import Foundation
import Testing
import PhoneGatewayClient
import AssistantKit

private final class WireStub: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var requests: [URLRequest] = []
    nonisolated(unsafe) static var bodies: [Data] = []
    nonisolated(unsafe) static var response: @Sendable (URLRequest) -> (Int, String) = { _ in (500, "{}") }
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.requests.append(request)
        var body = request.httpBody ?? Data()
        if let stream = request.httpBodyStream {
            stream.open(); defer { stream.close() }; var buffer = [UInt8](repeating: 0, count: 4096)
            while stream.hasBytesAvailable { let n = stream.read(&buffer, maxLength: buffer.count); if n <= 0 { break }; body.append(buffer, count: n) }
        }
        Self.bodies.append(body)
        let (status, responseText) = Self.response(request)
        let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: "HTTP/1.1", headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(responseText.utf8)); client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@Suite(.serialized) struct TransportTests {
    private func client() -> LiveGatewayClient {
        WireStub.requests = []; WireStub.bodies = []
        let config = URLSessionConfiguration.ephemeral; config.protocolClasses = [WireStub.self]
        return LiveGatewayClient(baseURL: URL(string: "https://gateway.example")!, token: "test-token", session: URLSession(configuration: config))
    }
    @Test func expiredCredentialMakesNoFurtherWireRequests() async {
        let client = client(); WireStub.response = { _ in (401, "{}") }
        await #expect(throws: GatewayError.unauthorized) { try await client.me() }
        await #expect(throws: GatewayError.unauthorized) { try await client.health() }
        #expect(WireStub.requests.count == 1)
    }
    @Test func answeringAStaleWaitNeverPostsAResume() async {
        let client = client()
        WireStub.response = { _ in (200, #"{"run_id":"run","status":"waiting","waiting":{"reason":"user","wait_key":"new-key"}}"#) }
        let old = Wait(runId: "run", waitKey: "old-key", kind: .toolApproval)
        await #expect(throws: GatewayError.alreadyHandled) { try await client.answer(old, with: .approve) }
        #expect(WireStub.requests.count == 1 && WireStub.requests[0].httpMethod == "GET")
    }
    @Test func unavailableWorkflowNeverStartsADifferentAgent() async {
        let client = client()
        WireStub.response = { _ in (200, #"{"apps":[{"interface":"abstractassistant.agent.v1","value":null,"effective":{"available":false}}]}"#) }
        await #expect(throws: GatewayError.self) { try await client.startRun(prompt: "hello", sessionId: "phone", toolPolicy: nil) }
        #expect(WireStub.requests.count == 1 && WireStub.requests[0].url?.path == "/api/gateway/accounts/me/preferences")
    }
    @Test func workflowSettingChangesOnlyTheAssistantPreference() async throws {
        let client = client(); WireStub.response = { _ in (200, "{}") }
        _ = try await client.setAssistantWorkflow("catalog:personal:agent")
        let body = try JSONSerialization.jsonObject(with: WireStub.bodies[0]) as! [String: Any]
        #expect(Set(body.keys) == ["default_workflow"])
        #expect((body["default_workflow"] as? [String: String]) == ["abstractassistant.agent.v1": "catalog:personal:agent"])
        #expect(WireStub.requests[0].httpMethod == "PUT")
        #expect(WireStub.requests[0].value(forHTTPHeaderField: "Authorization") == "Bearer test-token")
    }
    @Test func attachmentsKeepOwnerAndReachTheAgentContext() async throws {
        let client = client()
        WireStub.response = { request in
            if request.url!.path.hasSuffix("/discovery/tools") { return (200, #"{"items":[{"name":"read_file"}]}"#) }
            return request.httpMethod == "GET" ? (200, #"{"apps":[{"interface":"abstractassistant.agent.v1","value":null,"effective":{"available":true}}]}"#) : (200, #"{"run_id":"new-run"}"#)
        }
        let artifact = PhoneArtifact(artifactId: "photo", runId: "session_memory_original", filename: "photo.jpg", contentType: "image/jpeg")
        #expect(try await client.startRun(prompt: "Describe this", sessionId: "original", attachments: [artifact.ref]) == "new-run")
        let body = try JSONDecoder().decode(JSONValue.self, from: WireStub.bodies[2])
        #expect(body["input_data"]?["attachments"] == .array([artifact.ref]))
        #expect(body["input_data"]?["context"]?["attachments"] == .array([artifact.ref]))
        #expect(body["input_data"]?["context"]?["media"] == .array([artifact.ref]))
    }
    @Test func uploadPreservesReturnedProvenanceAndRealByteCount() async throws {
        let client = client(); WireStub.response = { _ in (200, #"{"run_id":"session_memory_sha_123","artifact":{"$artifact":"asset1"}}"#) }
        let data = Data("contents".utf8)
        let artifact = try await client.upload(data: data, filename: "../report.pdf", contentType: "application/pdf", sessionId: "chat:123")
        #expect(artifact.runId == "session_memory_sha_123" && artifact.size == data.count && artifact.filename == "report.pdf")
        let body = String(decoding: WireStub.bodies[0], as: UTF8.self)
        #expect(body.contains("chat:123") && body.contains("application/pdf"))
        #expect(!body.contains("../report.pdf"))
    }
    @Test func invalidArtifactIdsNeverMakeAnAuthenticatedRequest() async {
        let client = client()
        let artifact = PhoneArtifact(artifactId: "../secret", runId: "run", filename: "file", contentType: "text/plain")
        await #expect(throws: GatewayError.invalidResponse) { try await client.download(artifact) }
        #expect(WireStub.requests.isEmpty)
    }

    @Test func entityCreationUsesAuthenticatedValidatedRoutesAndKeepsPartialSuccess() async throws {
        let client = client(), draft = EntityDraft(name: "Atlas One")
        WireStub.response = { request in request.url!.path.hasSuffix("validate") ? (200, #"{"ok":true,"errors":[],"warnings":[],"exists":false,"slug":"atlas-one"}"#) : (201, #"{"created":true,"manifest":{"name":"Atlas One","slug":"atlas-one"},"warnings":["Setup note"],"skills_warning":"Skills unavailable"}"#) }
        #expect(try await client.validateEntity(draft).ok)
        let created = try await client.createEntity(draft)
        #expect(created.entity.name == "atlas-one" && created.warnings.count == 2)
        #expect(WireStub.requests.map { $0.url!.path } == ["/api/gateway/entities/atlas-one/validate", "/api/gateway/entities"])
        #expect(WireStub.requests.allSatisfy { $0.httpMethod == "POST" && $0.value(forHTTPHeaderField: "Authorization") == "Bearer test-token" })
        let bodies = try WireStub.bodies.map { try JSONDecoder().decode(JSONValue.self, from: $0) }
        #expect(bodies == [draft.body, draft.body])
    }
    @Test func invalidEntityNameNeverMakesARequestAndQuotaErrorStaysReadable() async throws {
        let client = client()
        do { _ = try await client.validateEntity(EntityDraft(name: "../bad")); Issue.record("Expected rejection") } catch { }
        #expect(WireStub.requests.isEmpty)
        WireStub.response = { _ in (429, #"{"detail":"Entity limit reached. Contact your administrator."}"#) }
        do { _ = try await client.createEntity(EntityDraft(name: "Atlas")); Issue.record("Expected quota rejection") }
        catch { #expect(error.localizedDescription == "Entity limit reached. Contact your administrator.") }
    }

    @Test func toolModesAndAttachmentsTravelTogetherAndEmptyIsDenyAll() async throws {
        let client = client()
        WireStub.response = { request in
            switch request.url!.path {
            case "/api/gateway/discovery/tools": (200, #"{"items":[{"name":"read_file"},{"name":"send_email"},{"name":"execute_command"}]}"#)
            case "/api/gateway/accounts/me/preferences": (200, #"{"apps":[{"interface":"abstractassistant.agent.v1","value":null,"effective":{"available":true}}]}"#)
            case "/api/gateway/runs/start": (200, #"{"run_id":"new-run"}"#)
            default: (404, "{}")
            }
        }
        let tools = ConversationTools(modes: ["read_file": .auto, "send_email": .approve, "execute_command": .off])
        let file = PhoneArtifact(artifactId: "file", runId: "owner", filename: "a.txt", contentType: "text/plain")
        _ = try await client.startRun(prompt: "Review", sessionId: "s", attachments: [file.ref], tools: tools)
        let body = try JSONDecoder().decode(JSONValue.self, from: WireStub.bodies[2])
        #expect(body["input_data"]?["tools"] == .array([.string("read_file"), .string("send_email")]))
        #expect(body["input_data"]?["_runtime"]?["allowed_tools"] == body["input_data"]?["tools"])
        #expect(body["input_data"]?["_runtime"]?["tool_policy"]?["auto_approve_tools"] == .array([.string("read_file")]))
        #expect(body["input_data"]?["_runtime"]?["tool_policy"]?["require_approval_tools"] == .array([.string("send_email")]))
        #expect(body["input_data"]?["attachments"] == .array([file.ref]))
        _ = try await client.startRun(prompt: "No tools", sessionId: "s", attachments: [], tools: .init(modes: [:]))
        let empty = try JSONDecoder().decode(JSONValue.self, from: WireStub.bodies[5])
        #expect(empty["input_data"]?["tools"] == .array([]))
        #expect(empty["input_data"]?["_runtime"]?["allowed_tools"] == .array([]))
    }
    @Test(arguments: [true, false]) func entityPolicyUsesAdvertisedVisitRoutesOrExistingAliases(canonical: Bool) async throws {
        let client = client()
        WireStub.response = { request in
            if request.url!.path.hasSuffix("/session-tools") {
                return canonical ? (200, #"{"items":[],"visit_routes":true}"#) : (200, #"{"items":[]}"#)
            }
            return (200, #"{"run_id":"visit","status":"waiting","turn_n":0,"reply":null}"#)
        }
        _ = try await client.openEntitySession(name: "castor", sessionID: "local", tools: .init(modes: ["diary_read": .approve]))
        #expect(WireStub.requests[1].url!.path == "/api/gateway/entities/castor/" + (canonical ? "visit/open" : "sessions"))
        let open = try JSONDecoder().decode(JSONValue.self, from: WireStub.bodies[1])
        #expect(open["session_id"] == .string("local"))
        #expect(open["tool_policy"]?["modes"]?["diary_read"] == .string("approve"))
        _ = try await client.answerEntity(name: "castor", runID: "visit", waitKey: "exact-key", approved: true)
        let decision = try JSONDecoder().decode(JSONValue.self, from: WireStub.bodies[2])
        #expect(decision == .object(["wait_key": .string("exact-key"), "approved": .bool(true)]))
        try await client.setEntityTools(name: "castor", runID: "visit", tools: nil)
        #expect(try JSONDecoder().decode(JSONValue.self, from: WireStub.bodies[3]) == .object(["modes": .null]))
        try await client.endEntitySession(name: "castor", runID: "visit")
        #expect(WireStub.requests[4].url!.path == "/api/gateway/entities/castor/visit/visit/" + (canonical ? "close" : "end"))
        #expect(try JSONDecoder().decode(JSONValue.self, from: WireStub.bodies[4]) == .object(canonical ? ["closed_by": .string("pause")] : [:]))
        _ = try await client.openEntitySession(name: "castor", sessionID: "inherit", tools: nil)
        let inherited = try JSONDecoder().decode(JSONValue.self, from: WireStub.bodies[5])
        #expect(inherited["tool_policy"] == .object(["modes": .null]))
        _ = try await client.openEntitySession(name: "castor", sessionID: "deny", tools: .init(modes: [:]))
        let deny = try JSONDecoder().decode(JSONValue.self, from: WireStub.bodies[6])
        #expect(deny["tool_policy"] == .object(["modes": .object([:])]))
    }
    @Test func optionalMeasurementsAndDefaultsHandleOlderGatewaysWithoutInventedValues() async throws {
        let client = client(); WireStub.response = { _ in (404, "{}") }
        #expect(try await client.messageStats(runID: "old") == nil)
        #expect(try await client.automationDefaults() == nil)
        WireStub.response = { _ in (403, "{}") }
        await #expect(throws: GatewayError.self) { try await client.automationDefaults() }
    }

    @Test func establishedAssistantRoutesSupportToolsWithoutAnyNewCapabilityEndpoint() async throws {
        let client = client()
        WireStub.response = { request in
            switch request.url!.path {
            case "/api/gateway/discovery/tools": (200, #"{"items":[{"name":"read_file","description":"Read a file","approval_default":"auto"},{"name":"send_email","approval_default":"ask"}]}"#)
            case "/api/gateway/accounts/me/preferences": (200, #"{"apps":[{"interface":"abstractassistant.agent.v1","value":null,"effective":{"available":true}}]}"#)
            case "/api/gateway/runs/start": (200, #"{"run_id":"established-run"}"#)
            default: (404, "{}") // Includes the unnecessary capability probe.
            }
        }
        #expect(try await client.tools().map(\.name) == ["read_file", "send_email"])
        let choices = ConversationTools(modes: ["read_file": .auto, "send_email": .approve, "execute_command": .off])
        #expect(try await client.startRun(prompt: "Hi", sessionId: "s", attachments: [], tools: choices) == "established-run")
        let body = try JSONDecoder().decode(JSONValue.self, from: WireStub.bodies[3])
        #expect(body["input_data"]?["tools"] == .array([.string("read_file"), .string("send_email")]))
        #expect(body["input_data"]?["_runtime"]?["tool_policy"]?["require_approval_tools"] == .array([.string("send_email")]))
        #expect(WireStub.requests.map { $0.url!.path } == ["/api/gateway/discovery/tools", "/api/gateway/accounts/me/preferences", "/api/gateway/discovery/tools", "/api/gateway/runs/start"])
        _ = try await client.startRun(prompt: "Inherit", sessionId: "s", attachments: [], tools: nil)
        let inherited = try JSONDecoder().decode(JSONValue.self, from: WireStub.bodies[6])
        #expect(inherited["input_data"]?["tools"] == .array([.string("read_file"), .string("send_email")]))
        #expect(inherited["input_data"]?["_runtime"]?["allowed_tools"] == inherited["input_data"]?["tools"])
        #expect(inherited["input_data"]?["_runtime"]?["tool_policy"] == nil)
    }
    @Test(arguments: [0, 1, 2]) func everyAssistantStartSuppliesInheritedToolsWithoutChangingApprovalDefaults(overload: Int) async throws {
        let client = client()
        WireStub.response = { request in
            switch request.url!.path {
            case "/api/gateway/accounts/me/preferences": (200, #"{"apps":[{"interface":"abstractassistant.agent.v1","value":null,"effective":{"available":true}}]}"#)
            case "/api/gateway/discovery/tools": (200, #"{"items":[{"name":"read_file","approval_default":"auto"},{"name":"send_email","approval_default":"ask"},{"name":"unknown_default"},{"name":"off_by_default","approval_default":"off"},{"name":"host_disabled","enabled":false},{"name":"unavailable","available":false}]}"#)
            case "/api/gateway/runs/start": (200, #"{"run_id":"inherited"}"#)
            default: (404, "{}")
            }
        }
        switch overload {
        case 0: _ = try await client.startRun(prompt: "Use tools", sessionId: "s", toolPolicy: nil)
        case 1: _ = try await client.startRun(prompt: "Use tools", sessionId: "s", attachments: [])
        default: _ = try await client.startRun(prompt: "Use tools", sessionId: "s", attachments: [], tools: nil)
        }
        let body = try JSONDecoder().decode(JSONValue.self, from: WireStub.bodies[2])
        let expected: JSONValue = .array([.string("read_file"), .string("send_email"), .string("unknown_default")])
        #expect(body["input_data"]?["tools"] == expected)
        #expect(body["input_data"]?["_runtime"]?["allowed_tools"] == expected)
        #expect(body["input_data"]?["_runtime"]?["tool_policy"] == nil)
        #expect(WireStub.requests.count == 3 && WireStub.requests.last?.httpMethod == "POST")
    }

    @Test func savedChoicesCannotOfferToolsThatTheGatewayDisabledSinceTheyWereSaved() async throws {
        let client = client()
        WireStub.response = { request in
            switch request.url!.path {
            case "/api/gateway/accounts/me/preferences": (200, #"{"apps":[{"interface":"abstractassistant.agent.v1","value":null,"effective":{"available":true}}]}"#)
            case "/api/gateway/discovery/tools": (200, #"{"items":[{"name":"read_file"},{"name":"send_email","enabled":false},{"name":"execute_command"}]}"#)
            case "/api/gateway/runs/start": (200, #"{"run_id":"restricted"}"#)
            default: (404, "{}")
            }
        }
        let saved = ConversationTools(modes: ["read_file": .approve, "send_email": .auto, "execute_command": .off, "removed_tool": .auto])
        _ = try await client.startRun(prompt: "Use tools", sessionId: "s", attachments: [], tools: saved)
        let body = try JSONDecoder().decode(JSONValue.self, from: WireStub.bodies[2])
        #expect(body["input_data"]?["tools"] == .array([.string("read_file")]))
        #expect(body["input_data"]?["_runtime"]?["tool_policy"]?["auto_approve_tools"] == .array([]))
        #expect(body["input_data"]?["_runtime"]?["tool_policy"]?["require_approval_tools"] == .array([.string("read_file")]))
    }

    @Test(arguments: [404, 403, 503, 200]) func failedDiscoveryNeverStartsAnApparentlyToolFreeAssistant(status: Int) async throws {
        let client = client()
        WireStub.response = { request in
            if request.url!.path.hasSuffix("/preferences") { return (200, #"{"apps":[{"interface":"abstractassistant.agent.v1","value":null,"effective":{"available":true}}]}"#) }
            return (status, #"{"items":[],"error":"tool registry unavailable"}"#)
        }
        await #expect(throws: GatewayError.self) { try await client.startRun(prompt: "Use tools", sessionId: "s", attachments: [], tools: nil) }
        #expect(WireStub.requests.count == 2 && WireStub.requests.allSatisfy { $0.httpMethod == "GET" })
    }

    @Test func entityToolDiscoveryFailureNeverSendsAPolicyThroughLegacyVisitOpen() async throws {
        for status in [404, 403] {
            let client = client(); WireStub.response = { _ in (status, "{}") }
            await #expect(throws: GatewayError.self) { try await client.openEntitySession(name: "castor", sessionID: "s", tools: .init(modes: [:])) }
            #expect(WireStub.requests.count == 1 && WireStub.requests[0].httpMethod == "GET")
        }
    }
    @Test @MainActor func restoredEntityHistoryStaysQuietAndTerminalVisitsAreForgotten() async throws {
        let client = client(), defaults = UserDefaults(suiteName: "entity-restore-\(UUID())")!
        let connection = SavedConnection(gateway: URL(string: "https://gateway.example")!, user: "alice", credential: .token("test"))
        defaults.set("saved-session", forKey: "phone.session." + connection.scope)
        defaults.set("castor", forKey: "phone.entity." + connection.scope)
        let key = "phone.visit." + connection.scope + ".saved-session"
        defaults.set("visit", forKey: key)
        WireStub.response = { _ in (200, #"{"run_id":"visit","status":"waiting","turn_n":1,"reply":"An earlier answer","turn_complete":true}"#) }
        let store = AssistantStore(defaults: defaults); store.connect(connection, client: client)
        await store.followActiveRun()
        #expect(store.messages.last?.text == "An earlier answer" && store.completedReply == nil)
        #expect(store.canSend && defaults.string(forKey: key) == "visit")
        // Reconnecting to a terminal visit must not leave an unusable cached visit id.
        store.connect(connection, client: client)
        WireStub.response = { _ in (200, #"{"run_id":"visit","status":"cancelled","turn_n":1,"turn_complete":false}"#) }
        await store.followActiveRun()
        #expect(store.canSend && defaults.string(forKey: key) == nil)
        #expect(store.activeEntityRunID == nil && store.completedReply == nil)
    }

    @Test @MainActor func lostEntityTurnResponseRecoversItsApprovalWithoutResending() async throws {
        let client = client(), defaults = UserDefaults(suiteName: "lost-turn-\(UUID())")!
        let connection = SavedConnection(gateway: URL(string: "https://gateway.example")!, user: "alice", credential: .token("test"))
        defaults.set("s", forKey: "phone.session." + connection.scope)
        defaults.set("castor", forKey: "phone.entity." + connection.scope)
        defaults.set("v", forKey: "phone.visit." + connection.scope + ".s")
        WireStub.response = { request in
            if request.url!.path.hasSuffix("/tool-policy") { return (200, "{}") }
            if request.url!.path.hasSuffix("/turn") { return (503, "{}") }
            let first = WireStub.requests.filter { $0.url!.path.hasSuffix("/state") }.count == 1
            return first ? (200, #"{"run_id":"v","status":"waiting","turn_n":1,"reply":"Earlier","turn_complete":true,"ready_for_input":true}"#) : (200, #"{"run_id":"v","status":"waiting","turn_n":2,"turn_complete":false,"ready_for_input":false,"pending_wait":{"reason":"user","wait_key":"tool_approval:v:key","details":{"mode":"approval_required","tool_calls":[{"name":"read_memory","arguments":{}}]}}}"#)
        }
        let store = AssistantStore(defaults: defaults); store.connect(connection, client: client)
        await store.followActiveRun(); store.send("Next answer")
        for _ in 0..<200 { if store.phase == .waiting { break }; try await Task.sleep(for: .milliseconds(10)) }
        #expect(store.phase == .waiting && store.activeEntityRunID == "v")
        #expect(store.waits.first?.waitKey == "tool_approval:v:key" && !store.canSend)
        #expect(WireStub.requests.filter { $0.url!.path.hasSuffix("/turn") }.count == 1)
        #expect(store.completedReply == nil)
    }
    @Test @MainActor func openingAssistantHistoryEndsTheOwnedEntityVisitFirst() async throws {
        for successfulEnd in [false, true] {
            let client = client(), defaults = UserDefaults(suiteName: "switch-visit-\(UUID())")!
            let connection = SavedConnection(gateway: URL(string: "https://gateway.example")!, user: "alice", credential: .token("test"))
            defaults.set("s", forKey: "phone.session." + connection.scope)
            defaults.set("castor", forKey: "phone.entity." + connection.scope)
            defaults.set("v", forKey: "phone.visit." + connection.scope + ".s")
            WireStub.response = { request in
                if request.url!.path.hasSuffix("/session-tools") { return (200, #"{"items":[]}"#) }
                if request.url!.path.hasSuffix("/state") { return (200, #"{"run_id":"v","status":"waiting","turn_n":1,"reply":"Earlier","turn_complete":true}"#) }
                if request.url!.path.hasSuffix("/end") { return (successfulEnd ? 200 : 409, "{}") }
                return (200, #"{"items":[]}"#)
            }
            let store = AssistantStore(defaults: defaults); store.connect(connection, client: client)
            await store.followActiveRun()
            let session = SessionSummary.group([RunSummary(runId: "r", workflowId: nil, status: "completed", sessionId: "history")])[0]
            await store.openSession(session)
            #expect(WireStub.requests.filter { $0.url!.path.hasSuffix("/end") }.count == 1)
            #expect(store.selectedEntity == (successfulEnd ? nil : "castor"))
            #expect(store.sessionID == (successfulEnd ? "history" : "s"))
            #expect(store.canSend)
        }
    }

}
