import Foundation
import Testing
@testable import AbstractGatewayClient

@Suite struct LedgerSSEParserTests {
    @Test func splitBytesMultilineJSONCommentsAndPrivateFrames() throws {
        let wire = ": heartbeat\r\nevent: llm.delta\r\ndata: {\"secret\":\"never expose\"}\r\n\r\nevent: step\ndata: {\"cursor\":3,\ndata: \"record\":{\"step_id\":\"é\",\"status\":\"started\"}}\n\nevent: done\ndata: {}\n\n"
        var parser = LedgerSSEParser()
        var events: [LedgerStreamEvent] = []
        // Split inside UTF-8 code points and fields, just as network chunks can.
        for byte in Data(wire.utf8) { events += try parser.feed(Data([byte])) }
        #expect(events.count == 2)
        if case .record(let cursor, let record) = events[0] { #expect(cursor == 3 && record.stepId == "é") }
        else { Issue.record("Missing durable record") }
        if case .done = events[1] {} else { Issue.record("Missing done") }
    }
    @Test func malformedStepThrowsButUnknownEventDoesNot() throws {
        var parser = LedgerSSEParser()
        #expect(try parser.feed(Data("event: unknown\ndata: not JSON\n\n".utf8)).isEmpty)
        #expect(throws: LedgerStreamError.self) { try parser.feed(Data("event: step\ndata: {}\n\n".utf8)) }
    }
    @Test func overflowFailsInsteadOfSilentlyDroppingRecords() async {
        let stream = AsyncThrowingStream<LedgerStreamEvent, Error>(bufferingPolicy: .bufferingOldest(1)) { continuation in
            do { try yieldLedger(.done, to: continuation); try yieldLedger(.done, to: continuation) }
            catch { continuation.finish(throwing: error) }
        }
        do { for try await _ in stream {}; Issue.record("Expected overflow") }
        catch { #expect(error is LedgerStreamError) }
    }
}

private final class LedgerWireStub: URLProtocol, @unchecked Sendable {
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

@Suite(.serialized) struct LedgerStreamTransportTests {
    private func client() -> LiveGatewayClient {
        LedgerWireStub.requests = []
        let config = URLSessionConfiguration.ephemeral; config.protocolClasses = [LedgerWireStub.self]
        return LiveGatewayClient(baseURL: URL(string: "https://gateway.test")!, token: "test-token", session: URLSession(configuration: config), readTries: 1)
    }
    @Test func authenticatedStreamUsesConsumedCursorAndDone() async throws {
        let client = client()
        LedgerWireStub.reply = { _ in (200, "event: step\ndata: {\"cursor\":8,\"record\":{\"step_id\":\"s\",\"status\":\"completed\"}}\n\nevent: done\ndata: {}\n\n") }
        var events: [LedgerStreamEvent] = []
        for try await event in client.ledgerEvents(runID: "root", after: 7) { events.append(event) }
        #expect(events.count == 2)
        #expect(LedgerWireStub.requests[0].url?.query == "after=7")
        #expect(LedgerWireStub.requests[0].value(forHTTPHeaderField: "Authorization") == "Bearer test-token")
    }
    @Test(arguments: [404, 405]) func oldGatewayFallsBackToExistingLedger(status: Int) async throws {
        let client = client()
        LedgerWireStub.reply = { request in
            if request.url!.path.hasSuffix("/stream") { return (status, "") }
            if request.url!.path.hasSuffix("/ledger") {
                return request.url!.query == "after=0" ? (200, #"{"items":[{"step_id":"s","status":"completed"}],"next_after":1}"#) : (200, #"{"items":[],"next_after":1}"#)
            }
            return (200, #"{"run_id":"root","status":"completed"}"#)
        }
        var events: [LedgerStreamEvent] = []
        for try await event in client.ledgerEvents(runID: "root", after: 0) { events.append(event) }
        #expect(events.count == 2)
        #expect(LedgerWireStub.requests.filter { $0.url!.path.hasSuffix("/ledger") }.count == 2)
    }
    @Test func unauthorizedStreamLocksFurtherRequestsWithoutFallback() async {
        let client = client()
        LedgerWireStub.reply = { _ in (401, "") }
        for _ in 0..<2 {
            do { for try await _ in client.ledgerEvents(runID: "root", after: 0) {}; Issue.record("Expected unauthorized") }
            catch { #expect(error as? GatewayError == .unauthorized) }
        }
        #expect(LedgerWireStub.requests.count == 1)
    }
    @Test func childListingPaginatesAndRejectsUnrelatedRows() async throws {
        let client = client()
        LedgerWireStub.reply = { request in
            if request.url!.query!.contains("offset=0") {
                return (200, #"{"items":[{"run_id":"child-a","parent_run_id":"root","status":"running"},{"run_id":"stranger","parent_run_id":"other","status":"running"}],"has_more":true}"#)
            }
            return (200, #"{"items":[{"run_id":"child-b","parent_run_id":"root","status":"waiting"}],"has_more":false}"#)
        }
        let children = try await client.childRuns(ofRunID: "root")
        #expect(children.map(\.runId) == ["child-a", "child-b"])
        #expect(LedgerWireStub.requests[1].url!.query!.contains("offset=2"))
    }
    @Test func repeatedChildPageCannotLoopForever() async {
        let client = client()
        LedgerWireStub.reply = { _ in (200, #"{"items":[{"run_id":"child","parent_run_id":"root","status":"running"}],"has_more":true}"#) }
        await #expect(throws: LedgerStreamError.self) { try await client.childRuns(ofRunID: "root") }
        #expect(LedgerWireStub.requests.count == 2)
    }
    @Test(arguments: [403, 500]) func otherStreamFailuresDoNotFallBack(status: Int) async {
        let client = client()
        LedgerWireStub.reply = { _ in (status, "") }
        do { for try await _ in client.ledgerEvents(runID: "root", after: 0) {}; Issue.record("Expected failure") }
        catch { #expect(error as? GatewayError == .http(status: status, body: "")) }
        #expect(LedgerWireStub.requests.count == 1)
    }
    @Test func eofWithoutDoneRequestsReconnect() async {
        let client = client()
        LedgerWireStub.reply = { _ in (200, ": heartbeat\n\n") }
        do { for try await _ in client.ledgerEvents(runID: "root", after: 0) {}; Issue.record("Expected incomplete stream") }
        catch { #expect(error as? GatewayError == .invalidResponse) }
    }
    @Test(arguments: [
        #"{"after":4,"records":[{"cursor":6,"record":{"step_id":"s","status":"completed"}}],"next_cursor":5,"total":6}"#,
        #"{"after":4,"records":[],"next_cursor":7,"total":7}"#,
        #"{"after":2,"records":[],"next_cursor":2,"total":2}"#
    ]) func entityLedgerRejectsGapsAndRewoundCursors(body: String) async {
        let client = client()
        LedgerWireStub.reply = { _ in (200, body) }
        await #expect(throws: LedgerStreamError.self) { try await client.entityLedger(name: "helper", runID: "visit", after: 4) }
    }
    @Test func entityLedgerUsesVisitScope() async throws {
        let client = client()
        LedgerWireStub.reply = { _ in (200, #"{"run_id":"visit","status":"running","after":4,"records":[{"cursor":5,"record":{"step_id":"step-five","status":"completed"}}],"next_cursor":5,"total":5,"done":false}"#) }
        let page = try await client.entityLedger(name: "helper", runID: "visit", after: 4)
        #expect(page.items.map(\.stepId) == ["step-five"] && page.nextAfter == 5)
        #expect(LedgerWireStub.requests[0].url!.path == "/api/gateway/entities/helper/visit/visit/ledger")
        #expect(LedgerWireStub.requests[0].url!.query == "after=4&limit=200")
    }
}
