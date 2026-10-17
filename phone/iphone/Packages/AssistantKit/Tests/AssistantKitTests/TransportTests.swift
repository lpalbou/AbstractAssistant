import Foundation
import Testing
import AbstractGatewayClient

private final class WireStub: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var requests: [URLRequest] = []
    nonisolated(unsafe) static var response: (URLRequest) -> (Int, String) = { _ in (500, "{}") }
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.requests.append(request)
        let (status, body) = Self.response(request)
        let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: "HTTP/1.1", headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(body.utf8)); client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@Suite(.serialized) struct TransportTests {
    private func client() -> LiveGatewayClient {
        WireStub.requests = []
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
}
