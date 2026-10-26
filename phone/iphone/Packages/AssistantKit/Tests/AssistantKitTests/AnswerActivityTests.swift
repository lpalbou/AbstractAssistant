import Foundation
import Testing
import PhoneGatewayClient
import AssistantKit

private final class ActivityWire: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var requests: [URLRequest] = []
    nonisolated(unsafe) static var refused = false
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.requests.append(request)
        let path = request.url!.path, query = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?.queryItems ?? []
        let parent = query.first { $0.name == "parent_run_id" }?.value
        var json = #"{"items":[],"has_more":false}"#
        if path.hasSuffix("/ledger") {
            if path.contains("/root/") {
                json = #"{"items":[{"step_id":"one","node_id":"reason","status":"completed","effect":{"type":"llm_call"}}],"next_after":1}"#
            } else if path.contains("/child/") {
                json = #"{"items":[{"step_id":"tool","status":"completed","effect":{"type":"tool_calls","payload":{"tool_calls":[{"name":"read_file","runtime_call_id":"call"}]}},"result":{"results":[{"runtime_call_id":"call","success":true,"output":"Saved summary"}]}}],"next_after":1}"#
            } else {
                json = #"{"items":[{"step_id":"a","node_id":"reason","status":"completed","effect":{"type":"llm_call"}},{"step_id":"b","node_id":"reason","status":"started","effect":{"type":"llm_call"}}],"next_after":2}"#
            }
        } else if path == "/api/gateway/runs", parent == "root" {
            json = #"{"items":[{"run_id":"child","parent_run_id":"root","status":"completed"},{"run_id":"foreign","parent_run_id":"elsewhere","status":"completed"}],"has_more":false}"#
        } else if path == "/api/gateway/runs/root" { json = #"{"run_id":"root","status":"completed"}"# }
        else if path == "/api/gateway/runs/other" { json = #"{"run_id":"other","status":"cancelled"}"# }
        let data = Data(json.utf8)
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: Self.refused ? 401 : 200, httpVersion: nil, headerFields: [:])!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: data); client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}
@Suite(.serialized) struct AnswerActivityTests {
    private func client(refused: Bool = false) -> LiveGatewayClient {
        ActivityWire.requests = []; ActivityWire.refused = refused
        let cfg = URLSessionConfiguration.ephemeral; cfg.protocolClasses = [ActivityWire.self]
        return .init(baseURL: URL(string: "https://gateway.test")!, token: "fixture-key", session: .init(configuration: cfg))
    }
    @Test func replayIncludesOwnedChildrenAndKeepsDifferentAnswersSeparate() async throws {
        let api = client(), first = try await AnswerActivity.load(runID: "root", client: api)
        let other = try await AnswerActivity.load(runID: "other", client: api)
        #expect(first.activity.cycleCount == 1 && first.activity.toolCalls == 1 && first.issues.isEmpty)
        #expect(other.activity.cycleCount == 2 && other.activity.toolCalls == 0 && other.issues.isEmpty)
        #expect(first.activity.items.contains { $0.detail == "Saved summary" })
        #expect(!ActivityWire.requests.contains { $0.url?.path.contains("foreign") == true })
        #expect(other.activity.items.last?.status == .cancelled)
        #expect(first.activity.items.allSatisfy { $0.status == .completed })
    }
    @Test func replayPropagatesAuthenticationFailureWithoutFurtherReads() async throws {
        let api = client(refused: true)
        await #expect(throws: GatewayError.unauthorized) { _ = try await AnswerActivity.load(runID: "root", client: api) }
        #expect(ActivityWire.requests.count == 1)
    }
}
