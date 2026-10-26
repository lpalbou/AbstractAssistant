import Foundation
import Testing
@testable import PhoneGatewayClient

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
    @Test func runnableWorkflowsDoNotFilterForAssistantAndRetainVersionAndEntrypoints() async throws {
        let client = client()
        AutomationWireStub.reply = { _ in (200, #"{"items":[{"bundle_id":"reports","bundle_version":"1.2.3","actions":{"can_run":true},"entrypoints":[{"flow_id":"csv","name":"CSV report","interfaces":[]},{"flow_id":"old","deprecated":true}]},{"bundle_id":"blocked","bundle_version":"1","actions":{"can_run":false},"entrypoints":[{"flow_id":"no"}]},{"bundle_id":"archived","bundle_version":"1","archived":true,"entrypoints":[{"flow_id":"no"}]}]}"#) }
        let workflows = try await client.workflows(forInterface: "")
        #expect(workflows.map(\.id) == ["reports@1.2.3:csv"])
        let request = try #require(AutomationWireStub.requests.first)
        #expect(request.url?.path == "/api/gateway/bundles")
        #expect(URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?.queryItems?.contains(where: { $0.name == "executable_for" }) != true)
        _ = try await client.workflows(forInterface: "abstractassistant.agent.v1")
        #expect(AutomationWireStub.requests.last?.url?.query?.contains("abstractassistant.agent.v1") == true)
    }

    @Test func nonAssistantInputsAreTypedAndSentToTheSelectedWorkflow() async throws {
        let descriptor = try JSONDecoder().decode(JSONValue.self, from: Data(#"{"inputs":[{"id":"source","label":"Source URL","type":"string","required":true},{"id":"limit","type":"integer","required":true,"default":25},{"id":"header","type":"boolean","default":true},{"id":"options","type":"object"},{"id":"format","type":"string","schema":{"type":"string","enum":["csv","json"]}}]}"#.utf8))
        let spec = try #require(WorkflowInputs.parse(descriptor))
        guard case .failure(let missing) = spec.inputData(task: "Description") else { Issue.record("Missing source accepted"); return }
        #expect(missing.names == ["source"])
        let overrides = try spec.overrides(from: ["source":"https://example.org/data.csv", "limit":"50", "header":"false", "options":#"{"sort":true}"#, "format":"csv"])
        guard case .success(let input) = spec.inputData(task: "Description", tools: [], overrides: overrides) else { Issue.record("Valid inputs refused"); return }
        #expect(input["prompt"] == nil && input["tools"] == nil)
        #expect(input["limit"] == .number(50) && input["header"] == .bool(false))
        #expect(input["options"] == .object(["sort":.bool(true)]))
        #expect(throws: WorkflowInputError.self) { try spec.overrides(from: ["limit":"1.5"]) }
        #expect(throws: WorkflowInputError.self) { try spec.overrides(from: ["header":"yes"]) }
        #expect(throws: WorkflowInputError.self) { try spec.overrides(from: ["format":"pdf"]) }
        let workflow = WorkflowChoice(bundleId: "reports", bundleVersion: "1.2.3", flowId: "csv", name: "CSV report")
        let automation = NewAutomation(task: "Report description", target: .workflow(workflow, inputData: input), when: .every("1h"), buildsOnEarlierRuns: false, askBeforeTools: true, title: "Hourly report")
        let client = client()
        AutomationWireStub.reply = { _ in (200, #"{"summary":{"automation_id":"new","title":"Hourly report","status":"active"}}"#) }
        _ = try await client.createAutomation(automation)
        let target = Self.body(try #require(AutomationWireStub.requests.last))["target"]
        #expect(target?["bundle_ref"] == .string("reports@1.2.3"))
        #expect(target?["flow_id"] == .string("csv"))
        #expect(target?["input_data"] == .object(input))
    }

    @Test func schemaDefaultsAndRequiredZeroFalseValuesArePreserved() throws {
        let json = try JSONDecoder().decode(JSONValue.self, from: Data(#"{"defaults":{"hidden":42},"input_data_schema":{"properties":{"count":{"type":"integer","default":0},"enabled":{"type":"boolean","default":false}},"required":["count","enabled"]}}"#.utf8))
        let spec = try #require(WorkflowInputs.parse(json))
        guard case .success(let input) = spec.inputData(task: "Description") else { Issue.record("Zero/false mistaken for missing"); return }
        #expect(input == ["hidden":.number(42), "count":.number(0), "enabled":.bool(false)])
    }

    @Test func unionAndArtifactInputsStayConfigurableAndNullCanBeExplicit() throws {
        let descriptor = try JSONDecoder().decode(JSONValue.self, from: Data(#"{"inputs":[{"id":"image","type":"artifact_image","required":true,"schema":{"anyOf":[{"type":"string"},{"type":"object"}]}},{"id":"caption","required":true,"schema":{"type":["string","null"]}}]}"#.utf8))
        let spec = try #require(WorkflowInputs.parse(descriptor))
        #expect(spec.fields?.first?.type == "json")
        #expect(WorkflowInput.type(in: .object(["type":.string("file")])) == "string")
        #expect(WorkflowInput.type(in: .object(["type":.string("custom-schema-pin")])) == "json")
        var values = try spec.overrides(from: ["image":#"{"$artifact":"img","run_id":"r"}"#])
        values["caption"] = .null
        guard case .success(let input) = spec.inputData(task: "", overrides: values) else { Issue.record("Valid artifact/nullable inputs refused"); return }
        #expect(input["image"]?["$artifact"] == .string("img"))
        #expect(input["caption"] == .null && input["prompt"] == nil)
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
