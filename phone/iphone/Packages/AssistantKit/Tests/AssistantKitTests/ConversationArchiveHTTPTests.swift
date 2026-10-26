import Foundation
import Testing
import AbstractGatewayClient
import AssistantKit

private final class ArchiveWire: URLProtocol, @unchecked Sendable {
    static let lock = NSLock()
    nonisolated(unsafe) static var mode = "normal"
    nonisolated(unsafe) static var requests: [URLRequest] = []
    nonisolated(unsafe) static var held: ArchiveWire?
    static func configure(_ mode: String) { lock.withLock { Self.mode = mode; requests = []; held = nil } }
    static var paths: [String] { lock.withLock { requests.map { $0.url!.path } } }
    static var isHeld: Bool { lock.withLock { held != nil } }
    static func release(status: Int, body: String) {
        let pending = lock.withLock { let value = held; held = nil; return value }
        pending?.finish(status: status, body: body)
    }
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let response: (Int, String)? = Self.lock.withLock {
            Self.requests.append(request)
            let path = request.url!.path
            let q = Dictionary(uniqueKeysWithValues: (URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?.queryItems ?? []).map { ($0.name, $0.value ?? "") })
            if (Self.mode == "holdMutation" && request.httpMethod == "POST") || (Self.mode == "holdList" && q["archived_only"] == "true") { Self.held = self; return nil }
            if path.hasSuffix("/archive") || path.hasSuffix("/unarchive") { return Self.mode == "fail" ? (503, "{}") : (200, "{}") }
            if path.hasSuffix("/me") { return (200, #"{"user_id":"fixture","roles":["user"]}"#) }
            if path.hasSuffix("/runs") {
                if q["session_id"] != nil { return (200, Self.rows(Self.mode == "becameLive" ? "running" : "completed", session: q["session_id"] ?? "session")) }
                if q["archived_only"] == "true" && Self.mode == "pages" {
                    return q["offset"] == "0" ? (200, Self.rows("completed", more: true)) : (200, Self.rows("completed", id: "older", session: "older"))
                }
                if q["archived_only"] == "true" && Self.mode == "repeated" { return (200, Self.rows("completed", more: true)) }
                if Self.mode == "capped" {
                    let rows = (0..<60).map { "{\"run_id\":\"turn\($0)\",\"session_id\":\"session\($0)\",\"status\":\"completed\"}" }.joined(separator: ",")
                    return (200, "{\"items\":[" + rows + "]}")
                }
                return (200, q["archived_only"] == "true" ? #"{"items":[],"has_more":false}"# : Self.rows("completed"))
            }
            return (200, #"{"items":[]}"#)
        }
        if let (status, body) = response { finish(status: status, body: body) }
    }
    static func rows(_ status: String, id: String = "turn", session: String = "session", more: Bool = false) -> String {
        "{\"items\":[{\"run_id\":\"\(id)\",\"session_id\":\"\(session)\",\"status\":\"\(status)\"}],\"has_more\":\(more)}"
    }
    func finish(status: Int, body: String) {
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(body.utf8)); client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@Suite(.serialized) @MainActor struct ConversationArchiveHTTPTests {
    private func client(_ mode: String) -> LiveGatewayClient {
        ArchiveWire.configure(mode)
        let config = URLSessionConfiguration.ephemeral; config.protocolClasses = [ArchiveWire.self]
        return LiveGatewayClient(baseURL: URL(string: "https://gateway.test")!, token: "fixture-key", session: URLSession(configuration: config), readTries: 1)
    }
    private func store(_ api: LiveGatewayClient) async -> AssistantStore {
        let value = AssistantStore(defaults: UserDefaults(suiteName: "archive-wire-\(UUID())")!)
        value.connect(nil, client: api); await value.refresh(); return value
    }
    @Test func archiveAndRestoreUseEstablishedRoutesAndRejectInvalidIdentifiers() async throws {
        let api = client("normal")
        try await api.setArchived(sessionId: "phone-123", true); try await api.setArchived(sessionId: "phone-123", false)
        #expect(ArchiveWire.paths == ["/api/gateway/sessions/phone-123/archive", "/api/gateway/sessions/phone-123/unarchive"])
        do { try await api.setArchived(sessionId: "../other", true); Issue.record("Invalid ID accepted") } catch {}
        #expect(ArchiveWire.paths.count == 2)
    }
    @Test func archivedHistoryTraversesPagesAndDetectsARepeatedPage() async throws {
        let api = client("pages")
        #expect(try await api.archivedRuns(limit: 200).map(\.runId) == ["turn", "older"])
        let queries = ArchiveWire.lock.withLock { ArchiveWire.requests.map { $0.url!.query ?? "" } }
        #expect(queries[0].contains("offset=0") && queries[1].contains("offset=1"))
        do { _ = try await client("repeated").archivedRuns(limit: 1); Issue.record("Repeated page accepted") } catch {}
    }
    @Test func failedArchiveRetainsConversationAndFreshRunningStatePreventsTheWrite() async throws {
        let value = await store(client("fail")); let session = try #require(value.sessions.first)
        #expect(!(await value.setArchived(session, true)))
        #expect(value.sessions.count == 1 && value.historyError != nil && value.sessionArchiveBusy.isEmpty)
        value.disconnect()
        let live = await store(client("becameLive")); let stale = try #require(live.sessions.first)
        #expect(!stale.anyTurnLive); #expect(!(await live.setArchived(stale, true)))
        #expect(!ArchiveWire.paths.contains { $0.hasSuffix("/archive") })
        #expect(live.historyError?.contains("working") == true); live.disconnect()
    }
    @Test func partialCountMetadataSurvivesLocalArchive() async throws {
        let value = await store(client("capped")), session = try #require(value.sessions.first)
        #expect(value.runs.count == 60 && value.recentHistoryMayBePartial)
        #expect(await value.setArchived(session, true))
        #expect(value.runs.count == 59 && value.recentHistoryMayBePartial)
        value.disconnect(); #expect(!value.recentHistoryMayBePartial)
    }
    @Test func lateArchiveCompletionCannotModifyReplacementAccount() async throws {
        let value = await store(client("holdMutation")), session = try #require(SessionSummary.group([RunSummary(runId: "turn", workflowId: nil, status: "completed", sessionId: "session")]).first)
        let task = Task { await value.setArchived(session, true) }
        for _ in 0..<10000 { if ArchiveWire.isHeld { break }; await Task.yield() }
        #expect(ArchiveWire.isHeld); #expect(!value.canSend && !value.canOpenConversation)
        value.connect(nil, client: MockGatewayClient(world: .phone)); let context = value.contextID
        ArchiveWire.release(status: 200, body: "{}")
        #expect(!(await task.value)); #expect(value.contextID == context && value.historyError == nil && value.archivedRuns.isEmpty)
        #expect(value.sessionArchiveBusy.isEmpty); value.disconnect()
    }
    @Test func staleArchivedListFailureCannotOverwriteSuccessfulMutation() async throws {
        let value = await store(client("holdList")), session = try #require(value.sessions.first)
        let load = Task { await value.loadArchivedConversations() }
        for _ in 0..<10000 { if ArchiveWire.isHeld { break }; await Task.yield() }
        #expect(ArchiveWire.isHeld)
        #expect(await value.setArchived(session, true))
        ArchiveWire.release(status: 503, body: "{}")
        await load.value
        #expect(value.historyError == nil && value.archivedSessions.count == 1)
        value.disconnect()
    }
}
