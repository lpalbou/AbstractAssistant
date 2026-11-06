import Foundation
import Testing
@testable import AbstractGatewayClient

private final class NoteWire: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var requests: [URLRequest] = []
    nonisolated(unsafe) static var response = 200
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.requests.append(request)
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: Self.response, httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(#"{"run_id":"capture-1"}"#.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
    static func body(_ r: URLRequest) throws -> [String: Any] {
        var data = r.httpBody ?? Data()
        if data.isEmpty, let stream = r.httpBodyStream {
            stream.open(); defer { stream.close() }
            var bytes = [UInt8](repeating: 0, count: 4096)
            while stream.hasBytesAvailable { let n = stream.read(&bytes, maxLength: bytes.count); if n <= 0 { break }; data.append(contentsOf: bytes.prefix(n)) }
        }
        return try JSONSerialization.jsonObject(with: data) as! [String: Any]
    }
}

@Suite(.serialized) struct NoteCaptureTests {
    private func client(_ credential: GatewayCredential) -> LiveGatewayClient {
        NoteWire.requests = []; NoteWire.response = 200
        let config = URLSessionConfiguration.ephemeral; config.protocolClasses = [NoteWire.self]
        return LiveGatewayClient(baseURL: URL(string: "https://gateway.test/mount/")!, credential: credential, session: URLSession(configuration: config), readTries: 1)
    }
    @Test func captureUsesNoteWorkflowCurrentAuthAndNoChatPrompt() async throws {
        let client = client(.session(id: "current-session", csrf: "current-csrf"))
        let capture = NoteCaptureRequest(text: "Remember the lighthouse", occurredAt: Date(timeIntervalSince1970: 1_700_000_000))
        #expect(try await client.startNoteCapture(capture) == "capture-1")
        let request = try #require(NoteWire.requests.first)
        #expect(request.url?.path == "/mount/api/gateway/runs/start")
        #expect(request.httpMethod == "POST")
        #expect(request.value(forHTTPHeaderField: "X-AbstractGateway-Session") == "current-session")
        #expect(request.value(forHTTPHeaderField: "X-AbstractGateway-CSRF") == "current-csrf")
        let body = try NoteWire.body(request), input = try #require(body["input_data"] as? [String: Any])
        #expect(body["bundle_id"] as? String == "abstractnote")
        #expect(body["flow_id"] as? String == "note-capture")
        #expect(body["session_id"] as? String == capture.sessionID)
        #expect(capture.sessionID.hasPrefix("note-watch-"))
        #expect(input["session_id"] as? String == capture.sessionID)
        #expect(input["text"] as? String == capture.text)
        #expect(input["prompt"] == nil)
        #expect(input["process_inline"] as? Bool == false)
        #expect(input["idempotency_key"] as? String == capture.idempotencyKey)
        #expect((input["source"] as? [String: String])?["client"] == "watch")
        #expect(input["user_id"] == nil && input["tenant_id"] == nil)
    }
    @Test func explicitRetryRetainsTheSameNoteIdentity() async throws {
        let client = client(.token("current-token"))
        let capture = NoteCaptureRequest(text: "One note")
        NoteWire.response = 503
        await #expect(throws: (any Error).self) { try await client.startNoteCapture(capture) }
        #expect(NoteWire.requests.count == 1)
        NoteWire.response = 200
        _ = try await client.startNoteCapture(capture)
        #expect(NoteWire.requests.count == 2)
        let a = try NoteWire.body(NoteWire.requests[0]) as NSDictionary
        let b = try NoteWire.body(NoteWire.requests[1]) as NSDictionary
        #expect(a == b)
        #expect(NoteWire.requests[1].value(forHTTPHeaderField: "Authorization") == "Bearer current-token")
    }
    @Test func completedFailureAndMissingReceiptNeverClaimSaved() {
        let failed = RunSummary(runId: "r", workflowId: "note-capture", status: "completed",
            output: .object(["success": .bool(false), "note_id": .string("nt_old"), "error": .string("No readable text")]))
        #expect(NoteCaptureOutcome(failed) == .failed("No readable text"))
        let missing = RunSummary(runId: "r", workflowId: "note-capture", status: "completed", output: .object(["response": .string("Done")]))
        if case .failed = NoteCaptureOutcome(missing) {} else { Issue.record("Missing note receipt claimed success") }
        let saved = RunSummary(runId: "r", workflowId: "note-capture", status: "completed", output: .object(["note_id": .string("nt_new")]))
        #expect(NoteCaptureOutcome(saved) == .saved("nt_new"))
    }
    @Test func mockRetriesResolveToOneNote() async throws {
        let client = MockGatewayClient(world: .watch)
        let capture = NoteCaptureRequest(text: "A thought")
        let first = try await client.startNoteCapture(capture)
        #expect(try await client.startNoteCapture(capture) == first)
        let run = try await client.run(id: first)
        #expect(run.status == "completed")
        #expect(run.output?["note_id"]?.stringValue != nil)
        #expect(run.sessionId != "watch-chat")
    }
}
