import Foundation
import Testing
@testable import AbstractGatewayClient

private final class SessionReadWire: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var reply: (URLRequest) -> (Int, String) = { _ in (500, "") }
    nonisolated(unsafe) static var requests: [URLRequest] = []
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.requests.append(request)
        let (status, body) = Self.reply(request)
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(body.utf8)); client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@Suite(.serialized) struct SessionReadsTests {
    private func client() -> LiveGatewayClient {
        SessionReadWire.requests = []
        let config = URLSessionConfiguration.ephemeral; config.protocolClasses = [SessionReadWire.self]
        return LiveGatewayClient(baseURL: URL(string: "https://gateway.test/prefix/")!, token: "test", session: URLSession(configuration: config), readTries: 1)
    }
    @Test func requestsNeverConsumeAnswersAndLateOlderTurnsRemainNew() throws {
        var state = SessionReadState()
        var newest = RunSummary(runId: "new", workflowId: nil, status: "running", sessionId: "chat")
        #expect(!state.isUnread(newest))
        try state.merge([.init(run: newest)!])
        newest.status = "completed"
        #expect(state.isUnread(newest))
        try state.merge([.init(run: newest)!])
        #expect(!state.isUnread(newest))
        newest.updatedAt = "2030-01-01T00:00:00Z"
        #expect(!state.isUnread(newest))
        let older = RunSummary(runId: "old", workflowId: nil, status: "completed", sessionId: "chat")
        #expect(state.isUnread(older))
        var nextAccount = SessionReadState(); try nextAccount.merge([])
        #expect(nextAccount.isUnread(newest))
        #expect(throws: GatewayError.invalidResponse) { try state.merge([.init(sessionID: "chat", runID: "old", status: "running")]) }
        #expect(state.isUnread(older))
    }
    @Test func readsUseBoundedUniqueRunFiltersAndKeepTheMountPath() async throws {
        let client = client()
        SessionReadWire.reply = { request in
            #expect(request.url!.path == "/prefix/api/gateway/me/session-reads")
            #expect(request.httpMethod == "GET")
            #expect(request.value(forHTTPHeaderField: "Authorization") == "Bearer test")
            let query = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)!.queryItems!
            #expect(query.contains(.init(name: "limit", value: "1000")))
            #expect(query.filter { $0.name == "run_id" }.count <= 100)
            return (200, #"{"items":[],"more":false}"#)
        }
        _ = try await client.sessionReads(runIDs: (0..<101).map { "r\($0)" } + ["r0"])
        #expect(SessionReadWire.requests.count == 2)
        _ = try await client.sessionReads(runIDs: [])
        #expect(SessionReadWire.requests.count == 2)
    }
    @Test func writesAreBoundedAndOnlyServerCommittedRevisionsAreAccepted() async throws {
        let client = client()
        SessionReadWire.reply = { request in
            #expect(request.httpMethod == "POST")
            var bytes = request.httpBody ?? Data()
            if bytes.isEmpty, let stream = request.httpBodyStream {
                stream.open(); defer { stream.close() }
                var buffer = [UInt8](repeating: 0, count: 4096)
                while stream.hasBytesAvailable {
                    let count = stream.read(&buffer, maxLength: buffer.count)
                    if count <= 0 { break }; bytes.append(buffer, count: count)
                }
            }
            let body = try! JSONSerialization.jsonObject(with: bytes) as! [String: [[String: String]]]
            let receipts = body["receipts"]!
            #expect(receipts.count <= 100)
            #expect(receipts.allSatisfy { $0["status"] == "completed" && $0["session_id"] == "chat" })
            let events: [[String: Any]] = receipts.enumerated().map { index, receipt in
                var value = receipt as [String: Any]; value["sequence"] = index + 1; value["at"] = "2026-10-31T20:00:00Z"; value["event_id"] = "event-\(index)"; return value
            }
            return (200, String(data: try! JSONSerialization.data(withJSONObject: ["items": events]), encoding: .utf8)!)
        }
        let values = (0..<101).map { SessionReadReceipt(sessionID: "chat", runID: "r\($0)", status: "completed") }
        #expect(try await client.markSessionReads(values) == values)
        #expect(SessionReadWire.requests.count == 2)
        SessionReadWire.reply = { _ in (200, #"{"items":[]}"#) }
        await #expect(throws: GatewayError.invalidResponse) { try await client.markSessionReads([values[0]]) }
        SessionReadWire.reply = { _ in (503, "unavailable") }
        await #expect(throws: GatewayError.self) { try await client.markSessionReads([values[0]]) }
    }
    @Test func truncatedAndInvalidReadPagesFailInsteadOfClearingBadges() async throws {
        let client = client()
        SessionReadWire.reply = { _ in (200, #"{"items":[],"more":true}"#) }
        await #expect(throws: GatewayError.invalidResponse) { try await client.sessionReads(runIDs: ["r"]) }
        SessionReadWire.reply = { _ in (200, #"{"items":[{"session_id":"chat","run_id":"r","status":"running","sequence":1,"at":"2026-10-31T20:00:00Z","event_id":"e"}],"more":false}"#) }
        await #expect(throws: GatewayError.invalidResponse) { try await client.sessionReads(runIDs: ["r"]) }
    }
    @Test func sharedMockReplaysIdempotentReceipts() async throws {
        let client = MockGatewayClient(world: .watch)
        let value = SessionReadReceipt(sessionID: "chat", runID: "r", status: "completed")
        #expect(try await client.sessionReads(runIDs: ["r"]).isEmpty)
        _ = try await client.markSessionReads([value, value])
        #expect(try await client.sessionReads(runIDs: ["r"]) == [value])
        #expect(try await client.sessionReads(runIDs: ["other"]).isEmpty)
    }
}
