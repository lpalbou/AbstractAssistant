import AbstractGatewayClient

/// Whether a new automation will ask before its tools, in words, from the tool modes it is created
/// with (backlog 1081). The create sheet shows it beside Tools, so an automation is never created
/// "ask" by accident: inherited Settings defaults with a tool on Ask make every unattended run wait
/// for an approval (QA 2026-10-29, a run waited 7 h). It derives exactly what `NewAutomation`
/// sends as `policy.tool_approval` ("ask" only when a tool is on Ask).
public struct AutomationApprovalState: Equatable, Sendable {
    /// `policy.tool_approval` will be "ask".
    public var asks: Bool
    /// The tools on Ask, as readable names, sorted.
    public var askingTools: [String]
    public var sentence: String

    public init(tools: ConversationTools) {
        let asking = tools.modes.filter { $0.value == .ask }.keys.map(Self.readable).sorted()
        asks = !asking.isEmpty
        askingTools = asking
        if asking.isEmpty {
            sentence = "Runs without asking: no tool is on Ask."
        } else {
            let shown = asking.prefix(3).joined(separator: ", ")
            let more = asking.count > 3 ? " and \(asking.count - 3) more" : ""
            let them = asking.count == 1 ? "it" : "one of them"
            sentence = "Asks before \(shown)\(more): a run that uses \(them) waits for your approval, even while this iPhone is closed."
        }
    }

    static func readable(_ name: String) -> String {
        name.replacingOccurrences(of: "_", with: " ").capitalized
    }
}
