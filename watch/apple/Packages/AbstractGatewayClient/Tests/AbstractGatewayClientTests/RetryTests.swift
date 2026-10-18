import Foundation
import Testing
@testable import AbstractGatewayClient

/// Answers from a script: each request takes the next status (0 = the connection drops).
final class FlakyStub: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var statuses: [Int] = []
    nonisolated(unsafe) static var methods: [String] = []
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.methods.append(request.httpMethod ?? "")
        let status = Self.statuses.isEmpty ? 200 : Self.statuses.removeFirst()
        if status == 0 { client?.urlProtocol(self, didFailWithError: URLError(.networkConnectionLost)); return }
        let resp = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: "HTTP/1.1", headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: resp, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(#"{"user_id":"alice","roles":["user"]}"#.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@Suite(.serialized) struct RetryTests {
    private func client() -> LiveGatewayClient {
        let cfg = URLSessionConfiguration.ephemeral
        cfg.protocolClasses = [FlakyStub.self]
        return LiveGatewayClient(baseURL: URL(string: "https://gateway.example")!, token: "t", session: URLSession(configuration: cfg))
    }

    @Test func aReadOutlastsADroppedConnectionAndAServerError() async throws {
        FlakyStub.statuses = [0, 503, 200]; FlakyStub.methods = []
        let me = try await client().me()
        #expect(me.userId == "alice")
        #expect(FlakyStub.methods == ["GET", "GET", "GET"])
    }

    @Test func aReadFailsOnlyOnceEveryTryHas() async throws {
        FlakyStub.statuses = [503, 503, 503, 200]; FlakyStub.methods = []
        await #expect(throws: GatewayError.self) { try await client().me() }
        #expect(FlakyStub.methods.count == LiveGatewayClient.readTries)
    }

    @Test func aRefusalIsFinal() async throws {
        FlakyStub.statuses = [404, 200]; FlakyStub.methods = []
        await #expect(throws: GatewayError.self) { try await client().me() }
        #expect(FlakyStub.methods.count == 1)
    }

    @Test func aWriteIsSentOnce() async throws {
        FlakyStub.statuses = [503, 200]; FlakyStub.methods = []
        await #expect(throws: GatewayError.self) { try await client().setArchived(sessionId: "s", true) }
        #expect(FlakyStub.methods == ["POST"])
    }
}
