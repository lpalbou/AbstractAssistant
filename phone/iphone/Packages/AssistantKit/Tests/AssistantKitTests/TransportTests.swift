import Foundation
import Testing
import AbstractGatewayClient

private final class WireStub: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var requests: [URLRequest] = []
    nonisolated(unsafe) static var bodies: [Data] = []
    nonisolated(unsafe) static var response: (URLRequest) -> (Int, String) = { _ in (500, "{}") }
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
        WireStub.response = { request in request.httpMethod == "GET" ? (200, #"{"apps":[{"interface":"abstractassistant.agent.v1","value":null,"effective":{"available":true}}]}"#) : (200, #"{"run_id":"new-run"}"#) }
        let artifact = PhoneArtifact(artifactId: "photo", runId: "session_memory_original", filename: "photo.jpg", contentType: "image/jpeg")
        #expect(try await client.startRun(prompt: "Describe this", sessionId: "original", attachments: [artifact.ref]) == "new-run")
        let body = try JSONDecoder().decode(JSONValue.self, from: WireStub.bodies[1])
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

}
