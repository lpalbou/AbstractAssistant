import Foundation
import Testing
@testable import AbstractGatewayClient

private final class AutomationWireStub: URLProtocol, @unchecked Sendable {
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

@Suite(.serialized) struct AutomationToolsTransportTests {
    private func client() -> LiveGatewayClient {
        AutomationWireStub.requests = []
        let config = URLSessionConfiguration.ephemeral; config.protocolClasses = [AutomationWireStub.self]
        return LiveGatewayClient(baseURL: URL(string: "https://gateway.test")!, token: "test", session: URLSession(configuration: config))
    }
    private static func body(_ request: URLRequest) -> JSONValue {
        var data = request.httpBody ?? Data()
        if data.isEmpty, let stream = request.httpBodyStream {
            stream.open(); defer { stream.close() }
            var buffer = [UInt8](repeating: 0, count: 4096)
            while stream.hasBytesAvailable { let n = stream.read(&buffer, maxLength: buffer.count); if n <= 0 { break }; data.append(contentsOf: buffer.prefix(n)) }
        }
        return (try? JSONDecoder().decode(JSONValue.self, from: data)) ?? .null
    }
    private let oldWire = #"{"definition":{"revision":1,"target":{"bundle_ref":"custom@1","flow_id":"flow","workflow_id":"server-owned","input_data":{"custom":42,"_runtime":{"model":"chosen"}}}}}"#
    private let newWire = #"{"definition":{"revision":2,"target":{"bundle_ref":"custom@1","flow_id":"flow","input_data":{"custom":42,"tools":["read_file"],"_runtime":{"model":"chosen","allowed_tools":["read_file"]}}},"policy":{"tool_policy":{"auto_approve_tools":["read_file"],"require_approval_tools":[]}}}}"#
    private func definition() throws -> AutomationDefinition { try JSONDecoder().decode(AutomationDefinitionResponse.self, from: Data(oldWire.utf8)).definition }
    @Test(arguments: [false, true]) func createSendsMixedOrDenyAllSnapshot(denyAll: Bool) async throws {
        let client = client(), selection = ConversationTools(modes: denyAll ? [:] : ["read_file": .auto, "execute_command": .approve, "write_file": .off])
        AutomationWireStub.reply = { request in
            #expect(request.httpMethod == "POST")
            let body = Self.body(request), input = body["target"]?["input_data"]
            #expect(input?["custom"] == .number(42))
            #expect(input?["_runtime"]?["model"] == .string("chosen"))
            #expect(input?["_runtime"]?["tool_policy"] == nil)
            #expect(input?["tools"] == .array(selection.allowed.map(JSONValue.string)))
            #expect(input?["_runtime"]?["allowed_tools"] == input?["tools"])
            #expect(body["policy"]?["tool_policy"] == selection.automationPolicy)
            #expect(body["target"]?["bundle_ref"] == .string("custom@1"))
            return (200, #"{"summary":{"automation_id":"a","status":"active"}}"#)
        }
        _ = try await client.createAutomation(.init(task: "Task", target: .workflow(.init(bundleId: "custom", bundleVersion: "1", flowId: "flow", name: "Custom"), inputData: ["custom": .number(42), "_runtime": .object(["model": .string("chosen"), "tool_policy": .object(["forged": .bool(true)])])]), when: .every("1h"), buildsOnEarlierRuns: false, askBeforeTools: true, tools: selection))
        #expect(AutomationWireStub.requests.count == 1)
    }
    @Test func saveWaitsForCommittedRevisionBeforeCallerRuns() async throws {
        let client = client(), oldWire = oldWire, newWire = newWire
        let selection = ConversationTools(modes: ["read_file": .auto, "off": .off])
        AutomationWireStub.reply = { request in
            if request.httpMethod == "PATCH" {
                let body = Self.body(request)
                #expect(body["expected_revision"] == .number(1))
                #expect(body["changes"]?["target"]?["workflow_id"] == nil)
                #expect(body["changes"]?["target"]?["input_data"]?["custom"] == .number(42))
                #expect(body["changes"]?["policy"]?["tool_policy"] == selection.automationPolicy)
                return (200, #"{"accepted":true}"#)
            }
            if request.httpMethod == "GET" { return (200, AutomationWireStub.requests.filter { $0.httpMethod == "GET" }.count == 1 ? oldWire : newWire) }
            #expect(AutomationWireStub.requests.filter { $0.httpMethod == "GET" }.count == 2)
            return (200, "{}")
        }
        let saved = try await client.saveAutomationTools(id: "a", definition: definition(), tools: selection)
        #expect(saved.revision == 2)
        #expect(!AutomationWireStub.requests.contains { $0.url!.path.hasSuffix("/commands") })
        try await client.runAutomationNow(id: "a")
        #expect(AutomationWireStub.requests.map { $0.httpMethod! } == ["PATCH", "GET", "GET", "POST"])
    }
    @Test(arguments: [false, true]) func legacyRejectionNeverDropsPolicy(create: Bool) async throws {
        let client = client()
        AutomationWireStub.reply = { _ in (422, #"{"detail":{"field":"policy.tool_policy"}}"#) }
        do {
            if create { _ = try await client.createAutomation(.init(task: "Task", target: .gatewayDefault(interface: "abstractcode.agent.v1"), when: .every("1h"), buildsOnEarlierRuns: false, askBeforeTools: false, tools: .init(modes: [:]))) }
            else { _ = try await client.saveAutomationTools(id: "a", definition: definition(), tools: .init(modes: [:])) }
            Issue.record("Expected unsupported gateway")
        } catch AutomationToolsError.unsupported {} catch { Issue.record("Unexpected error: \(error)") }
        #expect(AutomationWireStub.requests.count == 1)
    }
    @Test func conflictingRevisionStopsWithoutRunNow() async throws {
        let client = client(), conflicting = newWire
        AutomationWireStub.reply = { request in request.httpMethod == "PATCH" ? (200, "{}") : (200, conflicting) }
        do { _ = try await client.saveAutomationTools(id: "a", definition: definition(), tools: .init(modes: [:])); Issue.record("Expected conflict") }
        catch AutomationToolsError.conflict {} catch { Issue.record("Unexpected error: \(error)") }
        #expect(AutomationWireStub.requests.map { $0.httpMethod! } == ["PATCH", "GET"])
    }
    @Test func httpRevisionConflictDoesNotPollOrRun() async throws {
        let client = client()
        AutomationWireStub.reply = { _ in (409, "revision conflict") }
        do { _ = try await client.saveAutomationTools(id: "a", definition: definition(), tools: .init(modes: [:])); Issue.record("Expected revision conflict") }
        catch GatewayError.http(let status, _) { #expect(status == 409) }
        catch { Issue.record("Unexpected error: \(error)") }
        #expect(AutomationWireStub.requests.map { $0.httpMethod! } == ["PATCH"])
    }

    @Test func sameToolsButConcurrentWorkflowChangeIsConflict() async throws {
        let client = client(), changed = newWire.replacingOccurrences(of: "custom@1", with: "different@2")
        AutomationWireStub.reply = { request in request.httpMethod == "PATCH" ? (200, "{}") : (200, changed) }
        do { _ = try await client.saveAutomationTools(id: "a", definition: definition(), tools: .init(modes: ["read_file": .auto])); Issue.record("Must not launch a concurrently changed workflow") }
        catch AutomationToolsError.conflict {} catch { Issue.record("Unexpected error: \(error)") }
        #expect(!AutomationWireStub.requests.contains { $0.url!.path.hasSuffix("/commands") })
    }

    @Test func skippedRevisionIsConflictEvenWithMatchingToolsAndTarget() async throws {
        let client = client(), changed = newWire.replacingOccurrences(of: "\"revision\":2", with: "\"revision\":3")
        AutomationWireStub.reply = { request in request.httpMethod == "PATCH" ? (200, "{}") : (200, changed) }
        do { _ = try await client.saveAutomationTools(id: "a", definition: definition(), tools: .init(modes: ["read_file": .auto])); Issue.record("Expected skipped-revision conflict") }
        catch AutomationToolsError.conflict {} catch { Issue.record("Unexpected error: \(error)") }
    }

}
