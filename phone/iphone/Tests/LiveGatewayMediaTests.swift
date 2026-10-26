import XCTest
import AVFoundation
import UIKit
import AssistantKit
import PhoneGatewayClient
@testable import AbstractAssistantPhone

/// Explicit device-only verification. It uses the host app's sealed sign-in in place;
/// credentials are never exported, logged, passed through launch arguments or stored in a report.
final class LiveGatewayMediaTests: XCTestCase {
    /// Read-only investigation: no commands, email content, generation or credential export.
    @MainActor func testInspectFailedAutomationsReadOnly() async throws {
        #if LIVE_MEDIA_VERIFICATION && !targetEnvironment(simulator)
        let connection = try XCTUnwrap(ConnectionVault.read())
        let client = LiveGatewayClient(baseURL: connection.gateway, credential: connection.credential, session: PhoneTransport.makeSession())
        _ = try await client.me() // Stop on the first authentication failure.
        let rows = try await client.automations()
        var findings: [JSONValue] = []
        for automation in rows.prefix(20) {
            let page = try await raw(connection, path: "api/gateway/automations/\(automation.id)/occurrences")
            guard case .array(let occurrences)? = page["items"] else { continue }
            for row in occurrences where row["status"]?.stringValue == "failed" {
                var finding: [String: JSONValue] = [:]
                for key in ["run_id", "index", "status", "fired_at", "finished_at", "attempts", "failure"] { finding[key] = row[key] }
                if let id = row["run_id"]?.stringValue {
                    let run = try await client.run(id: id)
                    finding["run_error"] = run.error.map(JSONValue.string)
                }
                findings.append(.object(finding))
            }
        }
        try write(["read_only": .bool(true), "beta_update_app_available": .bool(UIApplication.shared.canOpenURL(URL(string: "itms-beta://")!)), "failed_occurrences": .array(findings)], name: "automation-failures.json")
        #else
        throw XCTSkip("Read-only automation investigation is opt-in and device-only.")
        #endif
    }

    @MainActor func testInspectProviderConnectionReadOnly() async throws {
        #if LIVE_MEDIA_VERIFICATION && !targetEnvironment(simulator)
        let connection = try XCTUnwrap(ConnectionVault.read())
        let client = LiveGatewayClient(baseURL: connection.gateway, credential: connection.credential, session: PhoneTransport.makeSession())
        _ = try await client.me()
        var report: [String: JSONValue] = ["configuration_changed": .bool(false), "automation_started": .bool(false)]
        defer { try? write(report, name: "provider-connection.json") }
        let profiles = try await raw(connection, path: "api/gateway/config/provider-endpoint-profiles")
        if case .array(let rows)? = profiles["profiles"], let profile = rows.first(where: { $0["id"]?.stringValue == "airelays" }) {
            var visible: [String: JSONValue] = [:]
            for key in ["id", "scope", "enabled", "provider_family", "api_key_set"] { visible[key] = profile[key] }
            report["profile"] = .object(visible)
            let body = try JSONEncoder().encode(JSONValue.object(["profile_id": .string("airelays")]))
            let discovery = try await raw(connection, path: "api/gateway/config/provider-endpoint-profiles/discover-models", method: "POST", data: body, contentType: "application/json")
            report["discovery_ok"] = discovery["ok"]
            report["effective_key_configured"] = discovery["api_key_set"]
            report["discovery_error_mentions_401"] = .bool(discovery["error"]?.stringValue?.contains("401") == true)
        } else { report["profile_found"] = .bool(false) }
        var targets: [JSONValue] = []
        for automation in try await client.automations() where automation.name?.lowercased().contains("email") == true {
            let definition = try await client.automationDefinition(id: automation.id)
            var fields: [String: JSONValue] = ["automation_id": .string(automation.id)]
            for key in ["kind", "interface", "bundle_id", "bundle_version", "flow_id", "bundle_ref", "provider", "model"] { fields[key] = definition.target?[key] }
            for key in ["provider", "model"] { fields["input_" + key] = definition.target?["input_data"]?[key] }
            fields["latest_status"] = automation.lastOccurrence?.status.map(JSONValue.string)
            fields["latest_index"] = automation.lastOccurrence?.index.map { .number(Double($0)) }
            fields["latest_fired_at"] = automation.lastOccurrence?.firedAt.map(JSONValue.string)
            fields["current_status"] = automation.currentOccurrence?.status.map(JSONValue.string)
            targets.append(.object(fields))
        }
        report["email_automation_targets"] = .array(targets)
        report["available_assistant_workflows"] = .array(try await client.workflows(forInterface: "abstractassistant.agent.v1").filter { $0.bundleId == "abstractassistant-orchestrator" }.map {
            .object(["bundle": .string($0.bundleId), "version": .string($0.bundleVersion), "flow_id": .string($0.flowId)])
        })
        #else
        throw XCTSkip("Provider inventory verification is opt-in and device-only.")
        #endif
    }

    @MainActor func testCompareAutomationWorkflowsWithoutTools() async throws {
        #if LIVE_MEDIA_VERIFICATION && !targetEnvironment(simulator)
        let connection = try XCTUnwrap(ConnectionVault.read())
        let client = LiveGatewayClient(baseURL: connection.gateway, credential: connection.credential, session: PhoneTransport.makeSession())
        _ = try await client.me()
        var results: [JSONValue] = []
        defer { try? write(["email_task_started": .bool(false), "configuration_changed": .bool(false), "results": .array(results)], name: "workflow-route-check.json") }
        for version in ["0.0.0", "0.0.15"] {
            let session = "iphone-provider-check-" + UUID().uuidString.lowercased()
            var body = StartRunRequest(prompt: "Reply exactly: OK. Do not use any tools.", sessionId: session,
                                       toolPolicy: .init(requireApprovalTools: [], autoApproveTools: []), system: "Reply only OK. Tools are unavailable.")
            body.bundleId = "abstractassistant-orchestrator"; body.bundleVersion = version; body.flowId = "d5d4e5a1"
            body.inputData.tools = []; body.inputData.runtime?.allowedTools = []; body.inputData.useSessionHistory = false
            var result: [String: JSONValue] = ["version": .string(version), "tools_enabled": .bool(false)]
            do {
                let id = try await client.startRun(body)
                result["run_id"] = .string(id)
                let deadline = Date().addingTimeInterval(60)
                var final: RunSummary?
                while Date() < deadline {
                    let run = try await client.run(id: id)
                    if run.isTerminal { final = run; break }
                    try await Task.sleep(for: .milliseconds(500))
                }
                if let final {
                    result["status"] = .string(final.status)
                    result["model_error_is_401"] = .bool(final.error?.contains("401") == true)
                    result["reply_is_ok"] = .bool(final.conversationText?.trimmingCharacters(in: .whitespacesAndNewlines).uppercased() == "OK")
                    try await client.setArchived(sessionId: session, true)
                    result["diagnostic_session_archived"] = .bool(true)
                } else {
                    try await client.cancel(runId: id)
                    result["status"] = .string("cancel_requested_after_timeout")
                }
            } catch GatewayError.unauthorized { throw GatewayError.unauthorized }
            catch GatewayError.http(let status, _) { result["gateway_http_status"] = .number(Double(status)) }
            catch { result["verification_problem"] = .string("Diagnostic request could not complete") }
            results.append(.object(result))
        }
        #else
        throw XCTSkip("Tool-free generation-route comparison is opt-in and device-only.")
        #endif
    }

    /// Inspect routing metadata in place; never export prompts, mailbox content or credentials.
    @MainActor func testCompareRecordedAutomationRoutingReadOnly() async throws {
        #if LIVE_MEDIA_VERIFICATION && !targetEnvironment(simulator)
        let connection = try XCTUnwrap(ConnectionVault.read())
        let client = LiveGatewayClient(baseURL: connection.gateway, credential: connection.credential, session: PhoneTransport.makeSession())
        _ = try await client.me()
        var report: [String: JSONValue] = ["read_only": .bool(true)]
        defer { try? write(report, name: "recorded-routing.json") }
        let automationID = "2de2f21d-0340-5148-8173-600babbb34b0"
        let definition = try await client.automationDefinition(id: automationID)
        report["target_routing"] = routingMetadata(.object(definition.target ?? [:]))
        var rows: [JSONValue] = []
        for root in [automationID, "1ed3d7f3-4371-5629-815c-3fd95d0c5572", "9f42432d-c4f6-5c16-be26-e57370baf1f7", "c7fec42f-69ce-4aa9-9707-b3d8b5de33e4", "39ddef44-aeed-4e61-a5fe-7ec9cdcae773"] {
            var queue = [root]; var seen = Set<String>()
            while let id = queue.first, seen.count < 25 {
                queue.removeFirst(); guard seen.insert(id).inserted else { continue }
                var item: [String: JSONValue] = ["root": .string(root), "run_id": .string(id)]
                let run = try await client.run(id: id)
                item["status"] = .string(run.status); item["error"] = run.error.map(JSONValue.string)
                item["workflow_id"] = run.workflowId.map(JSONValue.string)
                do {
                    let input = try await raw(connection, path: "api/gateway/runs/\(id)/input_data")
                    item["input_routing"] = routingMetadata(input)
                    let ledger = try await raw(connection, path: "api/gateway/runs/\(id)/ledger")
                    item["ledger_routing"] = routingMetadata(ledger)
                } catch GatewayError.unauthorized { throw GatewayError.unauthorized }
                catch GatewayError.http(let status, _) { item["inspection_http_status"] = .number(Double(status)) }
                let children = try await client.childRuns(ofRunID: id)
                queue.append(contentsOf: children.map(\.runId))
                rows.append(.object(item))
            }
        }
        report["runs"] = .array(rows)
        #else
        throw XCTSkip("Recorded routing inspection is opt-in and device-only.")
        #endif
    }

    @MainActor func testAutomationControllerWithoutTools() async throws {
        #if LIVE_MEDIA_VERIFICATION && !targetEnvironment(simulator)
        let connection = try XCTUnwrap(ConnectionVault.read())
        let client = LiveGatewayClient(baseURL: connection.gateway, credential: connection.credential, session: PhoneTransport.makeSession())
        _ = try await client.me()
        let original = try await client.automationDefinition(id: "2de2f21d-0340-5148-8173-600babbb34b0")
        var runtime: [String: JSONValue] = ["allowed_tools": .array([])]
        for key in ["provider", "model"] { runtime[key] = original.target?["input_data"]?["_runtime"]?[key] }
        var input: [String: JSONValue] = ["prompt": .string("Reply exactly: OK. Tools are unavailable."), "tools": .array([]), "_runtime": .object(runtime)]
        for key in ["provider", "model"] { input[key] = original.target?["input_data"]?[key] }
        let body: JSONValue = .object([
            "request_id": .string(UUID().uuidString.lowercased()), "title": .string("Temporary tool-free routing verification"),
            "target": .object(["bundle_ref": original.target?["bundle_ref"] ?? .string("abstractassistant-orchestrator@0.0.0"), "flow_id": original.target?["flow_id"] ?? .string("d5d4e5a1"), "input_data": .object(input)]),
            "trigger": .object(["source_id": .string("manual"), "source_version": .number(1), "config": .object([:])]),
            "context": .object(["mode": .string("independent")]),
            "policy": .object(["tool_approval": .string("ask"), "retry": .object(["max_attempts": .number(1)])]),
            "notify": .object(["channels": .array([.string("console")])])
        ])
        let created = try await raw(connection, path: "api/gateway/automations", method: "POST", data: JSONEncoder().encode(body), contentType: "application/json")
        let id = try XCTUnwrap(created["automation_id"]?.stringValue)
        var report: [String: JSONValue] = ["diagnostic_automation_id": .string(id), "tools_enabled": .bool(false), "email_task_started": .bool(false)]
        defer { try? write(report, name: "controller-route-check.json") }
        do {
            try await client.automationCommand(id: id, type: "automation.run_now")
            let deadline = Date().addingTimeInterval(90)
            while Date() < deadline {
                let page = try await raw(connection, path: "api/gateway/automations/\(id)/occurrences")
                if case .array(let items)? = page["items"], let row = items.first {
                    if ["completed", "failed", "cancelled"].contains(row["status"]?.stringValue ?? "") {
                        for key in ["run_id", "status", "failure", "attempts"] { report[key] = row[key] }
                        report["reply_is_ok"] = .bool(row["answer"]?.stringValue?.trimmingCharacters(in: .whitespacesAndNewlines).uppercased() == "OK")
                        break
                    }
                }
                try await Task.sleep(for: .seconds(1))
            }
            if report["status"] == nil { try await client.automationCommand(id: id, type: "automation.stop_current"); report["status"] = .string("timeout_stop_requested") }
            try await client.automationCommand(id: id, type: "automation.archive")
            report["archive_requested"] = .bool(true)
        } catch {
            try? await client.automationCommand(id: id, type: "automation.stop_current")
            try? await client.automationCommand(id: id, type: "automation.archive")
            throw error
        }
        #else
        throw XCTSkip("Tool-free automation controller verification is opt-in and device-only.")
        #endif
    }

    @MainActor func testAutomationToolCallingReadOnlyMetadata() async throws {
        #if LIVE_MEDIA_VERIFICATION && !targetEnvironment(simulator)
        let connection = try XCTUnwrap(ConnectionVault.read())
        let client = LiveGatewayClient(baseURL: connection.gateway, credential: connection.credential, session: PhoneTransport.makeSession())
        _ = try await client.me()
        let originalID = "2de2f21d-0340-5148-8173-600babbb34b0"
        let original = try await client.automationDefinition(id: originalID)
        let inventory = try await client.tools()
        guard inventory.contains(where: { $0.name == "list_email_accounts" && $0.isAvailable }) else { throw VerificationError.message("Read-only account metadata tool is unavailable") }
        var runtime: [String: JSONValue] = ["allowed_tools": .array([.string("list_email_accounts")])]
        for key in ["provider", "model"] { runtime[key] = original.target?["input_data"]?["_runtime"]?[key] }
        var input: [String: JSONValue] = ["prompt": .string("Call list_email_accounts once to verify access to account metadata. Then reply exactly OK. Do not read email bodies or send messages."), "tools": .array([.string("list_email_accounts")]), "_runtime": .object(runtime)]
        for key in ["provider", "model"] { input[key] = original.target?["input_data"]?[key] }
        let body: JSONValue = .object([
            "request_id": .string(UUID().uuidString.lowercased()), "title": .string("Temporary read-only tool routing verification"),
            "target": .object(["bundle_ref": original.target?["bundle_ref"] ?? .string("abstractassistant-orchestrator@0.0.0"), "flow_id": original.target?["flow_id"] ?? .string("d5d4e5a1"), "input_data": .object(input)]),
            "trigger": .object(["source_id": .string("manual"), "source_version": .number(1), "config": .object([:])]),
            "context": .object(["mode": .string("independent")]),
            "policy": .object(["tool_approval": .string("auto"), "retry": .object(["max_attempts": .number(1)])]),
            "notify": .object(["channels": .array([.string("console")])])
        ])
        let created = try await raw(connection, path: "api/gateway/automations", method: "POST", data: JSONEncoder().encode(body), contentType: "application/json")
        let id = try XCTUnwrap(created["automation_id"]?.stringValue)
        var report: [String: JSONValue] = ["diagnostic_automation_id": .string(id), "allowed_tools": .array([.string("list_email_accounts")]), "email_task_started": .bool(false)]
        defer { try? write(report, name: "controller-tool-check.json") }
        do {
            try await client.automationCommand(id: id, type: "automation.run_now")
            let deadline = Date().addingTimeInterval(90)
            while Date() < deadline {
                let page = try await raw(connection, path: "api/gateway/automations/\(id)/occurrences")
                if case .array(let items)? = page["items"], let row = items.first,
                   ["completed", "failed", "cancelled"].contains(row["status"]?.stringValue ?? "") {
                    for key in ["run_id", "status", "failure", "attempts"] { report[key] = row[key] }
                    report["reply_is_ok"] = .bool(row["answer"]?.stringValue?.trimmingCharacters(in: .whitespacesAndNewlines).uppercased() == "OK")
                    if let root = row["run_id"]?.stringValue {
                        var queue = [root]; var visited = Set<String>(); var calls = 0
                        while let run = queue.first, visited.count < 12 {
                            queue.removeFirst(); guard visited.insert(run).inserted else { continue }
                            let page = try await client.ledger(runId: run, after: 0)
                            for record in page.items {
                                if record.effect?["type"]?.stringValue == "tool_calls", record.status == "completed" { calls += 1 }
                            }
                            queue.append(contentsOf: try await client.childRuns(ofRunID: run).map(\.runId))
                        }
                        report["completed_tool_batches"] = .number(Double(calls))
                    }
                    break
                }
                try await Task.sleep(for: .seconds(1))
            }
            if report["status"] == nil { try await client.automationCommand(id: id, type: "automation.stop_current"); report["status"] = .string("timeout_stop_requested") }
            try await client.automationCommand(id: id, type: "automation.archive")
            for _ in 0..<10 {
                let state = try await raw(connection, path: "api/gateway/automations/\(id)")
                if state["summary"]?["status"]?.stringValue == "archived" { report["archived"] = .bool(true); break }
                try await Task.sleep(for: .milliseconds(300))
            }
            let state = try await raw(connection, path: "api/gateway/automations/\(originalID)")
            var originalStatus: [String: JSONValue] = [:]
            for key in ["status", "revision", "next_fire_at", "next_run_at"] { originalStatus[key] = state["summary"]?[key] }
            for key in ["run_id", "index", "status", "fired_at", "finished_at", "attempts"] { originalStatus["last_" + key] = state["summary"]?["last_occurrence"]?[key] }
            report["original_automation"] = .object(originalStatus)
        } catch {
            try? await client.automationCommand(id: id, type: "automation.stop_current")
            try? await client.automationCommand(id: id, type: "automation.archive")
            throw error
        }
        #else
        throw XCTSkip("Read-only tool-calling verification is opt-in and device-only.")
        #endif
    }

    private func routingMetadata(_ value: JSONValue) -> JSONValue {
        switch value {
        case .object(let fields):
            var output: [String: JSONValue] = [:]
            for (key, field) in fields {
                if ["provider", "model", "provider_family", "workflow_id", "effect_type", "status", "error"].contains(key) {
                    if case .string = field { output[key] = field }
                    else if key == "error", let message = field["message"]?.stringValue { output[key] = .object(["message": .string(message)]) }
                } else if key == "base_url", let text = field.stringValue, let url = URLComponents(string: text) {
                    output[key] = .string((url.host ?? "") + url.path)
                } else if key == "api_key" || key == "bearer_token" {
                    output[key + "_present"] = .bool(!(field.stringValue ?? "").isEmpty)
                } else {
                    let nested = routingMetadata(field)
                    if nested != .null { output[key] = nested }
                }
            }
            return output.isEmpty ? .null : .object(output)
        case .array(let items):
            let visible = items.map(routingMetadata).filter { $0 != .null }
            return visible.isEmpty ? .null : .array(visible)
        default: return .null
        }
    }

    @MainActor func testDiscoverSavedGateway() async throws {
        #if LIVE_MEDIA_VERIFICATION && !targetEnvironment(simulator)
        var report: [String: JSONValue] = ["stage": .string("discovery")]
        defer { try? write(report, name: "discovery.json") }
        guard let connection = try ConnectionVault.read() else {
            report["outcome"] = .string("no_saved_connection"); XCTFail("This iPhone has no saved gateway connection."); return
        }
        report["gateway"] = .string(connection.gateway.absoluteString)
        let client = LiveGatewayClient(baseURL: connection.gateway, credential: connection.credential, session: PhoneTransport.makeSession())
        do {
            _ = try await client.me()
            report["voice_defaults"] = try await raw(connection, path: "api/gateway/voice/defaults")
            let profiles = try await raw(connection, path: "api/gateway/config/provider-endpoint-profiles")
            if case .array(let rows)? = profiles["profiles"] {
                report["profiles"] = .array(rows.map { row in .object(Dictionary(uniqueKeysWithValues:
                    ["id", "virtual_provider", "provider_family", "scope", "enabled", "allowed_models"].compactMap { key in row[key].map { (key, $0) } })) })
            }
            let defaults = try await raw(connection, path: "api/gateway/config/capability-defaults")
            report["capability_defaults"] = safeRoutes(defaults)
            report["health"] = try await raw(connection, path: "api/health")
            report["versions"] = try await raw(connection, path: "api/gateway/about")
            let choices = try await client.workflows(forInterface: "abstractassistant.agent.v1")
            report["orchestrators"] = .array(choices.filter { $0.bundleId == "abstractassistant-orchestrator" }.map {
                .object(["version": .string($0.bundleVersion), "flow_id": .string($0.flowId)])
            })
            report["outcome"] = .string("authenticated")
        } catch { report["outcome"] = .string("failed"); report["error"] = .string(error.localizedDescription); throw error }
        #else
        throw XCTSkip("Run explicitly with scripts/build.py --live-media-test DEVICE --team TEAM.")
        #endif
    }

    @MainActor func testInspectSavedVoiceIncident() async throws {
        #if LIVE_MEDIA_VERIFICATION && !targetEnvironment(simulator)
        let connection = try XCTUnwrap(ConnectionVault.read())
        let session = try XCTUnwrap(UserDefaults.standard.string(forKey: "phone.session." + connection.scope))
        let client = LiveGatewayClient(baseURL: connection.gateway, credential: connection.credential, session: PhoneTransport.makeSession())
        _ = try await client.me()
        let turns = try await client.turns(ofSession: session)
        var target: String?
        for turn in turns.reversed().prefix(32) {
            let input = try await client.input(ofRun: turn.runId)
            if input.prompt?.lowercased().contains("hamlet") == true { target = turn.runId; break }
        }
        let root = try XCTUnwrap(target, "No saved Hamlet request found in the active conversation.")
        func publicValue(_ value: JSONValue?) -> JSONValue {
            guard let value else { return .null }
            if let text = value.stringValue { return .string(String(text.prefix(1200))) }
            let fields: Set<String> = ["mode", "seconds", "assistant_message", "media_prompt", "prompt", "response", "artifact", "audio_artifact", "image_artifact", "modality", "task", "content_type", "$artifact", "run_id"]
            if case .object(let object) = value { return .object(object.filter { fields.contains($0.key) }.mapValues { publicValue($0) }) }
            return .null
        }
        var queue = [root], seen: Set<String> = [], traces: [JSONValue] = []
        while !queue.isEmpty && seen.count < 32 {
            let id = queue.removeFirst(); guard seen.insert(id).inserted else { continue }
            let run = try await client.run(id: id)
            let input = try await raw(connection, path: "api/gateway/runs/" + id + "/input_data")
            let selection = input["workflow_selection"] ?? input["input_data"]?["workflow_selection"]
            let fields = ["bundle_id", "bundle_version", "flow_id", "source", "registry_scope", "requested_flow_id", "resolved_bundle_id", "resolved_bundle_version", "resolved_flow_id"]
            var events: [JSONValue] = [], cursor = 0
            for _ in 0..<5 {
                let page = try await client.ledger(runId: id, after: cursor)
                for r in page.items {
                    let payload = r.effect?["payload"], result = r.result
                    let params = payload?["params"]
                    var item: [String: JSONValue] = ["node": .string(r.nodeId ?? ""), "step": .string(r.stepId ?? ""), "type": .string(r.effectType ?? ""), "status": .string(r.status ?? ""), "started_at": .string(r.startedAt ?? ""), "ended_at": .string(r.endedAt ?? ""), "result_keys": .array((result?.objectValue?.keys.sorted() ?? []).map(JSONValue.string)), "content": publicValue(result?["content"]), "data": publicValue(result?["data"]), "output": publicValue(result?["output"])]
                    if let error = r.error { item["error"] = .string(String(error.prefix(500))) }
                    item["provider"] = result?["route"]?["provider"] ?? payload?["provider"] ?? .null
                    item["model"] = result?["route"]?["served_model"] ?? result?["model"] ?? payload?["model"] ?? .null
                    item["requested_output"] = publicValue(payload?["output"] ?? params?["output"])
                    events.append(.object(item))
                }
                cursor += page.items.count; if page.items.count < 200 { break }
            }
            let children = try await client.childRuns(ofRunID: id)
            queue += children.filter { $0.parentRunId == id }.map(\.runId)
            traces.append(.object(["run_id": .string(id), "workflow_id": .string(run.workflowId ?? ""), "status": .string(run.status), "selection": .object(Dictionary(uniqueKeysWithValues: fields.compactMap { key in selection?[key].map { (key, $0) } })), "output": publicValue(run.output), "events": .array(events), "children": .array(children.map { .string($0.runId) })]))
        }
        try write(["root": .string(root), "traces": .array(traces), "outcome": .string("inspected")], name: "voice-incident.json")
        #else
        throw XCTSkip("Read-only voice incident inspection is opt-in and device-only.")
        #endif
    }

    @MainActor func testConversationArchiveInventoryReadOnly() async throws {
        #if LIVE_MEDIA_VERIFICATION && !targetEnvironment(simulator)
        let connection = try XCTUnwrap(ConnectionVault.read())
        let client = LiveGatewayClient(baseURL: connection.gateway, credential: connection.credential, session: PhoneTransport.makeSession())
        _ = try await client.me()
        let recent = try await client.recentRuns(limit: 60)
        let archived = try await client.archivedRuns(limit: 200)
        let inventory = try await client.tools()
        let selection = ConversationTools.snapshot(nil, inventory: inventory)
        for category in ToolCatalogGroup.groups(inventory) {
            let allAuto = selection.settingCategory(category.id, to: .auto, inventory: inventory)
            XCTAssertTrue(inventory.filter { $0.categoryID == category.id && !$0.isAvailable }.allSatisfy { allAuto.modes[$0.name] == .off })
        }
        try write(["outcome": .string("passed"), "recent_sessions": .number(Double(SessionSummary.group(recent).count)), "recent_roots": .number(Double(recent.count)), "archived_sessions": .number(Double(SessionSummary.group(archived).count)), "archived_roots": .number(Double(archived.count)), "categories": .number(Double(ToolCatalogGroup.groups(inventory).count)), "disabled_tools": .number(Double(inventory.filter { !$0.isAvailable }.count))], name: "conversation-history-inventory.json")
        #else
        throw XCTSkip("Read-only conversation inventory verification is opt-in and device-only.")
        #endif
    }

    @MainActor func testSavedRichConversationExport() async throws {
        #if LIVE_MEDIA_VERIFICATION && !targetEnvironment(simulator)
        let connection = try XCTUnwrap(ConnectionVault.read())
        let session = try XCTUnwrap(UserDefaults.standard.string(forKey: "phone.session." + connection.scope))
        let client = LiveGatewayClient(baseURL: connection.gateway, credential: connection.credential, session: PhoneTransport.makeSession())
        _ = try await client.me()
        let turns = try await client.turns(ofSession: session)
        var messages: [ConversationMessage] = []
        for turn in turns.prefix(64) {
            let input = try await client.input(ofRun: turn.runId), run = try await client.run(id: turn.runId)
            messages.append(.init(role: .user, text: input.prompt ?? "", artifacts: input.attachments))
            messages.append(.init(role: .assistant, text: run.outputText ?? "", runID: run.runId, artifacts: run.mediaArtifacts))
        }
        let export = try await ConversationExportBuilder().prepare(messages: messages, responder: "Assistant", client: client)
        defer { try? PhoneTemporaryStorage().discard(export.folder) }
        let rich = try RichConversation(export: export)
        let imageCount = export.files.filter { $0.contentType.hasPrefix("image/") }.count
        let documents = export.files.filter { ["md", "txt", "pdf"].contains($0.url.pathExtension.lowercased()) }.count
        XCTAssertFalse(export.turns.isEmpty); XCTAssertFalse(rich.rtfd.isEmpty)
        XCTAssertGreaterThan(export.files.count, 0)
        XCTAssertEqual(rich.configuration(export: export).itemProvidersForActivityItemsConfiguration.count, export.files.count + 1)
        let lease = PreparedConversationShare(export: export, rich: rich); lease.close()
        XCTAssertFalse(FileManager.default.fileExists(atPath: export.folder.path))
        try write(["messages": .number(Double(export.turns.count)), "files": .number(Double(export.files.count)), "images": .number(Double(imageCount)), "documents": .number(Double(documents)), "html_bytes": .number(Double(rich.html.count)), "rtfd_bytes": .number(Double(rich.rtfd.count)), "cleanup": .bool(true), "outcome": .string("passed")], name: "rich-share-history.json")
        #else
        throw XCTSkip("Read-only saved conversation export verification is opt-in and device-only.")
        #endif
    }

    @MainActor func testSavedCycleGraphAndToolInputs() async throws {
        #if LIVE_MEDIA_VERIFICATION && !targetEnvironment(simulator)
        let connection = try XCTUnwrap(ConnectionVault.read())
        let savedSession = try XCTUnwrap(UserDefaults.standard.string(forKey: "phone.session." + connection.scope))
        let client = LiveGatewayClient(baseURL: connection.gateway, credential: connection.credential, session: PhoneTransport.makeSession())
        _ = try await client.me()
        let turns = try await client.turns(ofSession: savedSession)
        var cycles = 0, tools = 0, inputs = 0, approvals = 0, issues = 0
        for turn in turns.prefix(64) {
            let summary = try await AnswerActivity.load(runID: turn.runId, client: client)
            cycles += summary.activity.cycleCount; tools += summary.activity.toolCalls; issues += summary.issues.count
            for lane in summary.activity.cycleLanes {
                for cycle in lane.cycles { XCTAssertTrue(cycle.tools.allSatisfy { $0.runID == lane.runID && $0.cycleID == cycle.id }) }
            }
            inputs += summary.activity.items.filter { $0.kind == .tool && $0.inputText != nil }.count
            approvals += summary.activity.items.filter(\.isToolApproval).count
        }
        XCTAssertGreaterThan(cycles, 0); XCTAssertGreaterThan(tools, 0); XCTAssertGreaterThan(inputs, 0); XCTAssertGreaterThan(approvals, 0); XCTAssertEqual(issues, 0)
        try write(["cycles": .number(Double(cycles)), "tool_calls": .number(Double(tools)), "calls_with_input": .number(Double(inputs)), "approvals": .number(Double(approvals)), "issues": .number(Double(issues)), "outcome": .string("passed")], name: "cycle-tools-history.json")
        #else
        throw XCTSkip("Read-only cycle and tool history inspection is opt-in and device-only.")
        #endif
    }

    @MainActor func testReloadSavedAnswerCountsAfterRowCancellation() async throws {
        #if LIVE_MEDIA_VERIFICATION && !targetEnvironment(simulator)
        let connection = try XCTUnwrap(ConnectionVault.read())
        let savedSession = try XCTUnwrap(UserDefaults.standard.string(forKey: "phone.session." + connection.scope))
        let client = LiveGatewayClient(baseURL: connection.gateway, credential: connection.credential, session: PhoneTransport.makeSession())
        _ = try await client.me()
        let turns = try await client.turns(ofSession: savedSession)
        let store = AssistantStore(); store.connect(connection, client: client)
        defer { store.disconnect() }
        var sent = 0, changed = 0, resolved = 0, issues = 0
        for turn in turns.prefix(64) {
            let row = Task { await store.loadAnswerActivity(runID: turn.runId) }
            row.cancel() // A disappearing lazy row must not own the shared request.
            await row.value
            let summary = try XCTUnwrap(store.answerActivities[turn.runId])
            sent += summary.activity.sentEmailCount; changed += summary.activity.access.count(.filesChanged)
            resolved += 1; issues += summary.issues.count
        }
        try write(["resolved_answers": .number(Double(resolved)), "sent_emails": .number(Double(sent)), "changed_files": .number(Double(changed)), "issues": .number(Double(issues)), "outcome": .string("passed")], name: "history-counts.json")
        XCTAssertGreaterThan(resolved, 0); XCTAssertGreaterThan(sent, 0); XCTAssertGreaterThan(changed, 0); XCTAssertEqual(issues, 0)
        #else
        throw XCTSkip("Read-only saved history verification is opt-in and device-only.")
        #endif
    }

    @MainActor func testReplaySavedSentEmailReceipts() async throws {
        #if LIVE_MEDIA_VERIFICATION && !targetEnvironment(simulator)
        let connection = try XCTUnwrap(ConnectionVault.read())
        let session = try XCTUnwrap(UserDefaults.standard.string(forKey: "phone.session." + connection.scope))
        let client = LiveGatewayClient(baseURL: connection.gateway, credential: connection.credential, session: PhoneTransport.makeSession())
        _ = try await client.me()
        let turns = try await client.turns(ofSession: session)
        var count = 0, complete = 0, reads = 0, issues = 0
        var sourceCounts: [String: Int] = [:]
        for turn in turns.prefix(64) {
            let summary = try await AnswerActivity.load(runID: turn.runId, client: client)
            count += summary.activity.sentEmailCount; reads += summary.activity.readEmailCount; issues += summary.issues.count
            for kind in AccessKind.allCases { sourceCounts[kind.rawValue, default: 0] += summary.activity.access.count(kind) }
            for mail in summary.activity.sentEmails {
                if !mail.sender.isEmpty && !(mail.to + mail.cc + mail.bcc).isEmpty && !mail.subject.isEmpty && !mail.body.isEmpty && mail.sentAt != nil { complete += 1 }
            }
        }
        // Store counts only: no body, subject, recipient, credential or message ID is exported.
        try write(["source_counts": .object(sourceCounts.mapValues { .number(Double($0)) }), "confirmed_reads": .number(Double(reads)), "confirmed_sends": .number(Double(count)), "complete_receipts": .number(Double(complete)), "issues": .number(Double(issues)), "outcome": .string(count > 0 && complete > 0 ? "passed" : "missing_receipt")], name: "sent-email-receipts.json")
        XCTAssertGreaterThan(count, 0, "The saved conversation should contain its previously confirmed send.")
        XCTAssertGreaterThan(complete, 0, "At least one receipt must include sender, recipients, subject, body and recorded time.")
        #else
        throw XCTSkip("Read-only sent-email verification is opt-in and device-only.")
        #endif
    }

    @MainActor func testBrowseSavedConversationWorkspace() async throws {
        #if LIVE_MEDIA_VERIFICATION && !targetEnvironment(simulator)
        let connection = try XCTUnwrap(ConnectionVault.read())
        let session = try XCTUnwrap(UserDefaults.standard.string(forKey: "phone.session." + connection.scope))
        let client = LiveGatewayClient(baseURL: connection.gateway, credential: connection.credential, session: PhoneTransport.makeSession())
        _ = try await client.me()
        let turns = try await client.turns(ofSession: session)
        let files = SessionFilesController(); files.bind(connection.scope + session)
        var explicitFiles: Set<String> = []
        for turn in turns {
            let detail = try await client.run(id: turn.runId), input = try await client.input(ofRun: turn.runId)
            explicitFiles.formUnion((detail.mediaArtifacts + input.attachments).map(\.artifactId))
        }
        await files.refresh(client: client, sessionID: session, runIDs: turns.map(\.runId), explicitFileIDs: explicitFiles)
        let match = files.workspaces.compactMap { root in root.inventory.entries.first(where: { $0.name == "discussion-summary.md" }).map { (root.workspace, $0) } }.first
        var report: [String: JSONValue] = ["outcome": .string("workspace_listed"), "session_id": .string(session), "workspaces": .number(Double(files.workspaces.count)), "visible_attachments": .number(Double(files.visibleArtifacts.count)), "hidden_conversation_audio": .number(Double(files.artifacts.count - files.visibleArtifacts.count)), "issues": .array(files.issues.map(JSONValue.string))]
        defer { try? write(report, name: "session-files.json") }
        let inventory = try await raw(connection, path: "api/gateway/sessions/" + session + "/artifacts")
        if case .array(let rows)? = inventory["items"] {
            func safe(_ value: JSONValue, depth: Int = 0) -> JSONValue {
                guard depth < 8 else { return .null }
                if case .array(let items) = value { return .array(items.map { safe($0, depth: depth + 1) }) }
                guard case .object(let row) = value else { return value }
                let allowed: Set<String> = ["artifact_id", "run_id", "filename", "content_type", "semantic_kind", "render_kind", "source_path", "kind", "modality", "task", "purpose", "path", "artifact_space", "source", "capability_route", "role", "chunk_format", "tags", "producer", "source_refs", "descriptor", "metadata", "raw_metadata", "capability_metadata", "stream", "artifact_envelope_v1"]
                return .object(row.filter { allowed.contains($0.key) }.mapValues { safe($0, depth: depth + 1) })
            }
            try write(["artifacts": .array(rows.map { safe($0) })], name: "session-artifact-provenance.json")
        }
        let (workspace, entry) = try XCTUnwrap(match, "The conversation's discussion-summary.md must be discoverable through a run workspace.")
        files.open(entry, workspace: workspace, client: client)
        for _ in 0..<600 where files.downloading { try await Task.sleep(for: .milliseconds(100)) }
        let url = try XCTUnwrap(files.preview, files.error ?? "No file preview")
        let bytes = try Data(contentsOf: url)
        XCTAssertNotNil(String(data: bytes, encoding: .utf8)); XCTAssertGreaterThan(bytes.count, 0)
        report["outcome"] = .string("passed"); report["file"] = .string(entry.path); report["bytes"] = .number(Double(bytes.count)); report["run_id"] = .string(workspace.runID)
        files.preview = nil
        XCTAssertFalse(FileManager.default.fileExists(atPath: url.path))
        #else
        throw XCTSkip("Read-only live workspace verification is opt-in and device-only.")
        #endif
    }

    @MainActor func testGenerateImageAndEdit() async throws { try await verifyMedia(voiceOnly: false) }
    @MainActor func testGenerateVoice() async throws { try await verifyMedia(voiceOnly: true) }

    @MainActor func testGenerateHamletVoice() async throws { try await verifyMedia(voiceOnly: true, hamlet: true) }

    @MainActor private func verifyMedia(voiceOnly: Bool, hamlet: Bool = false) async throws {
        #if LIVE_MEDIA_VERIFICATION && !targetEnvironment(simulator)
        let reportName = hamlet ? "hamlet-voice-generation.json" : voiceOnly ? "voice-generation.json" : "generation.json"
        var report: [String: JSONValue] = ["stage": .string(voiceOnly ? "voice" : "images")]
        defer { try? write(report, name: reportName) }
        let connection = try XCTUnwrap(ConnectionVault.read())
        report["gateway"] = .string(connection.gateway.absoluteString)
        let transport = PhoneTransport.makeSession()
        let client = LiveGatewayClient(baseURL: connection.gateway, credential: connection.credential, session: transport)
        do {
            _ = try await client.me() // One auth failure stops here; never retry credentials.
            var choices = try await client.workflows(forInterface: "abstractassistant.agent.v1")
            if !choices.contains(where: { $0.bundleId == "abstractassistant-orchestrator" && $0.bundleVersion == "0.0.15" }) {
                let url = try XCTUnwrap(Bundle(for: Self.self).url(forResource: "AssistantOrchestrator", withExtension: "flow"))
                let boundary = "media-proof-" + UUID().uuidString
                var body = Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\nfalse\r\n--\(boundary)\r\nContent-Disposition: form-data; name=\"reload\"\r\n\r\ntrue\r\n--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"abstractassistant-orchestrator@0.0.15.flow\"\r\nContent-Type: application/octet-stream\r\n\r\n".utf8)
                body.append(try Data(contentsOf: url)); body.append(Data("\r\n--\(boundary)--\r\n".utf8))
                let result = try await raw(connection, path: "api/gateway/bundles/upload", method: "POST", data: body, contentType: "multipart/form-data; boundary=\(boundary)")
                report["bundle_uploaded"] = .bool(true)
                report["gateway_reloaded"] = result["gateway_reloaded"]
                choices = try await client.workflows(forInterface: "abstractassistant.agent.v1")
            }
            let choice = try XCTUnwrap(choices.first { $0.bundleId == "abstractassistant-orchestrator" && $0.bundleVersion == "0.0.15" && $0.flowId == "c53b1579" })
            func assistantPreference(_ preferences: JSONValue) -> JSONValue? {
                guard case .array(let apps)? = preferences["apps"] else { return nil }
                return apps.first { $0["interface"]?.stringValue == "abstractassistant.agent.v1" }
            }
            let initialPreference = hamlet ? assistantPreference(try await client.accountPreferences()) : nil

            if let saved = try? Data(contentsOf: evidenceDirectory().appending(path: reportName)),
               let previous = try? JSONDecoder().decode([String: JSONValue].self, from: saved),
               previous["gateway"]?.stringValue == connection.gateway.absoluteString,
               previous["bundle_version"]?.stringValue == choice.bundleVersion,
               previous["session_id"]?.stringValue?.hasPrefix("iphone-media-verification-") == true {
                report = previous
            }
            let session = report["session_id"]?.stringValue ?? "iphone-media-verification-" + UUID().uuidString.lowercased()
            report["session_id"] = .string(session)
            report["bundle_version"] = .string(choice.bundleVersion)
            func generate(_ name: String, _ prompt: String, source: PhoneArtifact? = nil) async throws -> PhoneArtifact {
                var body = StartRunRequest(prompt: prompt, sessionId: session, system: nil)
                body.bundleId = choice.bundleId; body.bundleVersion = choice.bundleVersion; body.flowId = choice.flowId
                body.inputData.tools = []
                if let source {
                    body.inputData.primaryImageArtifact = source.ref; body.inputData.hasPrimaryImageContext = true
                    body.inputData.context = .object(["primary_image_artifact": source.ref])
                }
                // Resume our own saved proof run after a Watch-priority interruption, avoiding duplicate generation.
                let id: String
                if let existing = report[name]?["run_id"]?.stringValue { id = existing }
                else { id = try await client.startRun(body) }
                report[name] = .object(["run_id": .string(id), "status": .string("running")]); try write(report, name: reportName)
                let deadline = Date().addingTimeInterval(600)
                var final: RunSummary?
                while Date() < deadline {
                    let run = try await client.run(id: id)
                    if run.isTerminal { final = run; break }
                    if run.waitsOnPerson { throw VerificationError.message("Unexpected approval required during media generation.") }
                    try await Task.sleep(for: .seconds(2))
                }
                guard let final, final.status == "completed" else {
                    try? await client.cancel(runId: id)
                    throw VerificationError.message(final?.error ?? "Generation did not complete within ten minutes.")
                }
                let file = try XCTUnwrap(final.mediaArtifacts.first { name == "voice" ? $0.isAudio : $0.isImage })
                let folder = FileManager.default.temporaryDirectory.appending(path: UUID().uuidString)
                try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
                defer { try? FileManager.default.removeItem(at: folder) }
                let url = folder.appending(path: file.filename)
                try await client.download(file, to: url)
                let bytes = try Data(contentsOf: url)
                if file.isImage { XCTAssertNotNil(UIImage(data: bytes), "Generated image must decode on iPhone") }
                else {
                    let duration = try await Task.detached(priority: .utility) { try AVAudioPlayer(contentsOf: url).duration }.value
                    XCTAssertGreaterThan(duration, 0.1)
                }
                // Keep only our own test image for visual inspection; voice is checked then discarded.
                if file.isImage { try bytes.write(to: evidenceDirectory().appending(path: name + ".png"), options: .atomic) }
                if hamlet {
                    let activity = try await AnswerActivity.load(runID: id, client: client)
                    XCTAssertTrue(activity.issues.isEmpty)
                    XCTAssertTrue(activity.activity.items.contains { $0.nodeID == "generate_voice" })
                    XCTAssertTrue(activity.activity.items.contains { $0.nodeID == "route_call" && $0.detail.contains("voice") })
                    XCTAssertFalse(activity.activity.items.contains { $0.nodeID == "reason" }, "Explicit recording must reach generation, not chat")
                    report["timed_steps"] = .number(Double(activity.activity.items.filter { $0.duration != nil }.count))
                    report["public_model_details"] = .number(Double(activity.activity.items.filter { !$0.detail.isEmpty }.count))
                }
                let restored = try await client.run(id: id)
                XCTAssertEqual(restored.mediaArtifacts, final.mediaArtifacts)
                let sessionFiles = try await client.artifacts(sessionId: session)
                XCTAssertTrue(sessionFiles.contains { $0.id == file.id })
                report[name] = .object(["run_id": .string(id), "status": .string(final.status), "artifact_id": .string(file.artifactId), "content_type": .string(file.contentType), "bytes": .number(Double(bytes.count)), "decoded_on_iphone": .bool(true)])
                try write(report, name: reportName)
                return file
            }
            if voiceOnly {
                _ = try await generate("voice", hamlet ? "generate a voice reciting a scene of hamlet" : "Generate a voice audio file speaking exactly these words: Hello Laurent. Images and voice are ready in your assistant.")
            } else {
                let image = try await generate("image", "Generate an image: a minimalist indigo and mint landscape with one coral sun. No text. Wide composition.")
                _ = try await generate("edit", "Edit the attached image: make the sun bright gold and add a second small moon. Preserve the landscape.", source: image)
            }
            if hamlet, let initialPreference {
                let beforeWrite = assistantPreference(try await client.accountPreferences())
                if beforeWrite?["value"] == initialPreference["value"], beforeWrite?["effective"] == initialPreference["effective"],
                   beforeWrite?["effective"]?["bundle_id"]?.stringValue == choice.bundleId,
                   ["0.0.13", "0.0.15"].contains(beforeWrite?["effective"]?["bundle_version"]?.stringValue ?? "") {
                    // Repair this account's existing orchestrator selection after proving audio.
                    // Other app keys are merged/preserved by the existing preferences endpoint.
                    let confirmed = try await client.setAssistantWorkflow(choice.id)
                    let effective = assistantPreference(confirmed)?["effective"]
                    XCTAssertEqual(effective?["bundle_version"]?.stringValue, choice.bundleVersion)
                    XCTAssertEqual(effective?["registry_scope"]?.stringValue, "private")
                    report["account_workflow"] = effective?["value"]
                    let regularID = try await client.startRun(prompt: "Reply exactly: Ready.", sessionId: session + "-account-selection", attachments: [], tools: ConversationTools(modes: [:]))
                    let deadline = Date().addingTimeInterval(120)
                    var state = try await client.run(id: regularID)
                    while !state.isTerminal && Date() < deadline { try await Task.sleep(for: .seconds(1)); state = try await client.run(id: regularID) }
                    XCTAssertEqual(state.status, "completed")
                    XCTAssertEqual(state.workflowId, choice.id)
                    let input = try await raw(connection, path: "api/gateway/runs/" + regularID + "/input_data")
                    let selection = input["workflow_selection"] ?? input["input_data"]?["workflow_selection"]
                    report["regular_start"] = .object(["run_id": .string(regularID), "workflow_id": .string(state.workflowId ?? ""), "source": selection?["source"] ?? .null, "bundle_version": selection?["bundle_version"] ?? .null, "status": .string(state.status)])
                } else { report["account_selection"] = .string("preserved_intervening_or_different_workflow_selection") }
            }
            report["outcome"] = .string("passed")
        } catch { report["outcome"] = .string("failed"); report["error"] = .string(error.localizedDescription); throw error }
        #else
        throw XCTSkip("Live media generation is opt-in and device-only.")
        #endif
    }
    private func safeRoutes(_ value: JSONValue) -> JSONValue {
        switch value {
        case .array(let rows): return .array(rows.map(safeRoutes))
        case .object(let row): return .object(row.reduce(into: [String: JSONValue]()) { result, item in
            let (key, value) = item
            if ["routes", "default", "effective", "value", "defaults", "provider", "model", "source", "kind", "modality", "task", "route", "configured", "available", "id", "name", "warnings", "errors"].contains(key) { result[key] = safeRoutes(value) }
        })
        default: return value
        }
    }
    private enum VerificationError: LocalizedError { case message(String); var errorDescription: String? { if case .message(let value) = self { value } else { "Verification failed" } } }
    @MainActor private func raw(_ connection: SavedConnection, path: String, method: String = "GET", data: Data? = nil, contentType: String? = nil) async throws -> JSONValue {
        var request = URLRequest(url: connection.gateway.appending(path: path)); request.httpMethod = method; request.httpBody = data; request.timeoutInterval = 120
        connection.credential.apply(to: &request, write: method != "GET")
        if let contentType { request.setValue(contentType, forHTTPHeaderField: "Content-Type") }
        let (bytes, response) = try await PhoneTransport.makeSession().data(for: request)
        guard let http = response as? HTTPURLResponse else { throw GatewayError.invalidResponse }
        if http.statusCode == 401 { throw GatewayError.unauthorized }
        guard (200..<300).contains(http.statusCode) else { throw GatewayError.http(status: http.statusCode, body: "") }
        return try JSONDecoder().decode(JSONValue.self, from: bytes)
    }
    private func evidenceDirectory() throws -> URL {
        let folder = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appending(path: "media-verification")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true); return folder
    }
    private func write(_ report: [String: JSONValue], name: String) throws {
        let encoder = JSONEncoder(); encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        try encoder.encode(report).write(to: evidenceDirectory().appending(path: name), options: .atomic)
    }
}
