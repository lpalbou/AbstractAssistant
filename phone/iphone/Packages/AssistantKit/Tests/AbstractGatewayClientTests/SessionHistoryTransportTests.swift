import Foundation
import Testing
@testable import AbstractGatewayClient

private final class HistoryWireStub: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var reply: (URLRequest) -> (Int, String) = { _ in (500, "") }
    nonisolated(unsafe) static var requests: [URLRequest] = []
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.requests.append(request)
        let (status, body) = Self.reply(request)
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil,
            headerFields: ["Content-Type": request.url!.path.hasSuffix("/stream") ? "text/event-stream" : "application/json"])!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(body.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@Suite(.serialized) struct SessionHistoryTransportTests {
    private func client() -> LiveGatewayClient {
        HistoryWireStub.requests = []
        let config = URLSessionConfiguration.ephemeral; config.protocolClasses = [HistoryWireStub.self]
        return LiveGatewayClient(baseURL: URL(string: "https://gateway.test")!, token: "test", session: URLSession(configuration: config))
    }
    @Test func paginationDeduplicatesAndRejectsUnrelatedRows() async throws {
        let client = client()
        HistoryWireStub.reply = { request in
            let query = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)!.queryItems!
            #expect(query.contains(.init(name: "session_id", value: "wanted")))
            #expect(query.contains(.init(name: "limit", value: "100")))
            if query.contains(.init(name: "offset", value: "0")) {
                return (200, #"{"items":[{"run_id":"new","status":"completed","session_id":"wanted"},{"run_id":"other","status":"completed","session_id":"other"},{"run_id":"child","status":"completed","session_id":"wanted","parent_run_id":"new"}],"has_more":true}"#)
            }
            #expect(query.contains(.init(name: "offset", value: "3")))
            return (200, #"{"items":[{"run_id":"new","status":"completed","session_id":"wanted"},{"run_id":"old","status":"completed","session_id":"wanted"},{"run_id":"legacy","status":"completed"},{"run_id":"occurrence","status":"completed","session_id":"wanted","parent_run_id":"controller","session_kind":"occurrence"}],"has_more":false}"#)
        }
        #expect(try await client.turns(ofSession: "wanted").map(\.runId) == ["new", "old", "legacy", "occurrence"])
        #expect(HistoryWireStub.requests.count == 2)
    }
    @Test func ignoredOffsetFailsInsteadOfLooping() async throws {
        let client = client()
        HistoryWireStub.reply = { _ in (200, #"{"items":[{"run_id":"same","status":"completed","session_id":"wanted"}],"has_more":true}"#) }
        do { _ = try await client.turns(ofSession: "wanted"); Issue.record("Expected non-progress failure") }
        catch { #expect(error as? GatewayError == .invalidResponse) }
        #expect(HistoryWireStub.requests.count == 2)
    }
}
