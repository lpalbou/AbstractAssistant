import Foundation
import Testing
import AssistantKit
import AbstractGatewayClient

@Suite struct AutomationToolsTests {
    private var inventory: [ToolInfo] { [
        ToolInfo(name: "read_file", riskTier: "observe", riskRank: 1, approvalDefault: "auto"),
        ToolInfo(name: "execute_command", riskTier: "destroy", riskRank: 4, approvalDefault: "ask"),
        ToolInfo(name: "disabled", riskTier: nil, riskRank: nil, approvalDefault: "auto", enabled: false)
    ] }
    @Test func settingsSnapshotRespectsExplicitOffAndUnavailable() {
        let defaults = ConversationTools.snapshot(nil, inventory: inventory)
        #expect(defaults.modes == ["read_file": .auto, "execute_command": .approve, "disabled": .off])
        let explicit = ConversationTools.snapshot(.init(modes: ["read_file": .approve, "disabled": .auto]), inventory: inventory)
        #expect(explicit.modes == ["read_file": .approve, "execute_command": .off, "disabled": .off])
        #expect(ConversationTools.snapshot(.init(modes: [:]), inventory: inventory).allowed.isEmpty)
    }
    @Test func requiredToolsPinIsFilledBeforeWorkflowValidation() throws {
        let input = WorkflowInputs(defaults: ["custom": .number(42)], required: ["prompt", "tools"])
        guard case .success(let values) = input.inputData(task: "Run", tools: []) else { Issue.record("Missing required tools"); return }
        #expect(values["tools"] == .array([]) && values["custom"] == .number(42))
    }
    @Test func savedPolicyUsesIntersectionAndApprovalWins() {
        let definition = AutomationDefinition(revision: 1, title: nil, target: ["input_data": .object([
            "tools": .array([.string("read_file"), .string("execute_command")]),
            "_runtime": .object(["allowed_tools": .array([.string("read_file")])])
        ])], policy: ["tool_policy": .object(["auto_approve_tools": .array([.string("read_file")]), "require_approval_tools": .array([.string("read_file")])])])
        #expect(definition.tools?.modes == ["read_file": .approve])
    }
}
