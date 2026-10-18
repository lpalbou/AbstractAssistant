import Foundation

public extension ConversationTools {
    /// Freeze defaults against fresh discovery so an unattended automation owns a durable grant.
    static func snapshot(_ selection: ConversationTools?, inventory: [ToolInfo]) -> ConversationTools {
        ConversationTools(modes: Dictionary(inventory.map { tool in
            let mode: ToolMode
            if !tool.isAvailable { mode = .off }
            else if let selection { mode = selection.modes[tool.name] ?? .off }
            else { mode = ["off", "disabled"].contains(tool.approvalDefault ?? "") ? .off : tool.approvalDefault == "auto" ? .auto : .approve }
            return (tool.name, mode)
        }, uniquingKeysWith: { _, new in new }))
    }
    var fingerprint: String {
        let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys]
        return (try? encoder.encode(self)).flatMap { String(data: $0, encoding: .utf8) } ?? ""
    }
    var automationPolicy: JSONValue {
        .object(["auto_approve_tools": .array(modes.filter { $0.value == .auto }.keys.sorted().map(JSONValue.string)),
                 "require_approval_tools": .array(modes.filter { $0.value == .approve }.keys.sorted().map(JSONValue.string))])
    }
    func automationInput(_ existing: [String: JSONValue]) -> [String: JSONValue] {
        var input = existing, runtime = existing["_runtime"]?.objectValue ?? [:]
        // Automation approval policy belongs to definition.policy, not caller-controlled runtime vars.
        runtime.removeValue(forKey: "tool_policy")
        runtime["allowed_tools"] = .array(allowed.map(JSONValue.string))
        input["tools"] = .array(allowed.map(JSONValue.string)); input["_runtime"] = .object(runtime)
        return input
    }
}

public extension JSONValue {
    var objectValue: [String: JSONValue]? { if case .object(let value) = self { value } else { nil } }
}

public extension AutomationDefinition {
    var tools: ConversationTools? {
        let input = target?["input_data"]
        let top = input?["tools"], ceiling = input?["_runtime"]?["allowed_tools"]
        guard top != nil || ceiling != nil else { return nil }
        func names(_ value: JSONValue?) -> Set<String> { if case .array(let values) = value { Set(values.compactMap(\.stringValue)) } else { [] } }
        let allowed = top != nil && ceiling != nil ? names(top).intersection(names(ceiling)) : names(ceiling ?? top)
        let nested = policy?["tool_policy"]
        let auto = names(nested?["auto_approve_tools"]), ask = names(nested?["require_approval_tools"])
        return ConversationTools(modes: Dictionary(uniqueKeysWithValues: allowed.map { name in
            (name, nested == nil ? (policy?["tool_approval"] == .string("auto") ? .auto : .approve) : auto.contains(name) && !ask.contains(name) ? .auto : .approve)
        }))
    }
    func changes(tools: ConversationTools) throws -> [String: JSONValue] {
        guard let target, let flow = target["flow_id"] else { throw GatewayError.invalidResponse }
        var updated: [String: JSONValue] = ["flow_id": flow, "input_data": .object(tools.automationInput(target["input_data"]?.objectValue ?? [:]))]
        if let bundle = target["bundle_ref"] { updated["bundle_ref"] = bundle }
        if let interface = target["interface"] { updated["interface"] = interface }
        var policy = self.policy ?? [:]; policy["tool_policy"] = tools.automationPolicy
        return ["target": .object(updated), "policy": .object(policy)]
    }
}

public enum AutomationToolsError: LocalizedError {
    case unsupported, notConfirmed, conflict
    public var errorDescription: String? {
        switch self {
        case .unsupported: "This gateway needs the automation tool-policy update to save per-tool permissions. Your choices have been kept."
        case .notConfirmed: "The gateway has not confirmed the tool changes yet. Refresh before running this automation."
        case .conflict: "The automation changed elsewhere. Reopen its tools before saving again."
        }
    }
}

public extension GatewayClient {
    func saveAutomationTools(id: String, definition: AutomationDefinition, tools: ConversationTools) async throws -> AutomationDefinition {
        guard let revision = definition.revision else { throw GatewayError.invalidResponse }
        let changes = try definition.changes(tools: tools)
        do { try await reviseAutomation(id: id, changes: changes, expectedRevision: revision) }
        catch GatewayError.http(let status, let body) where status == 422 && body.contains("tool_policy") { throw AutomationToolsError.unsupported }
        for attempt in 0..<40 {
            try Task.checkCancellation()
            let current = try await automationDefinition(id: id)
            if (current.revision ?? -1) > revision {
                guard current.revision == revision + 1,
                      changes["target"]?.objectValue?.allSatisfy({ current.target?[$0.key] == $0.value }) == true,
                      current.tools == ConversationTools(modes: tools.modes.filter { $0.value != .off }),
                      current.policy?["tool_policy"] == tools.automationPolicy else { throw AutomationToolsError.conflict }
                return current
            }
            if attempt < 39 { try await Task.sleep(for: .milliseconds(250)) }
        }
        throw AutomationToolsError.notConfirmed
    }
}
