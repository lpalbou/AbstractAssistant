import Testing
import AbstractGatewayClient
@testable import AssistantKit

// Backlog 1081: the create sheet says whether the new automation asks before tools, from the very
// modes it is created with, so it is never created "ask" by accident (QA 2026-10-29).

private func automation(_ modes: [String: ToolMode]) -> NewAutomation {
    NewAutomation(task: "Brief me", target: .gatewayDefault(interface: "abstractassistant.agent.v1"), when: .every("24h"),
                  buildsOnEarlierRuns: false, tools: ConversationTools(modes: modes))
}

@Test func noToolOnAskRunsWithoutAskingAndSendsAuto() {
    let modes: [String: ToolMode] = ["web_search": .auto, "fetch_url": .auto, "write_file": .off]
    let state = AutomationApprovalState(tools: ConversationTools(modes: modes))
    #expect(!state.asks && state.askingTools.isEmpty)
    #expect(state.sentence == "Runs without asking: no tool is on Ask.")
    #expect(automation(modes).body["policy"]?["tool_approval"] == .string("auto"))
}

@Test func aToolOnAskIsNamedAndTheAutomationAsks() {
    let modes: [String: ToolMode] = ["send_email": .ask, "web_search": .auto]
    let state = AutomationApprovalState(tools: ConversationTools(modes: modes))
    #expect(state.asks && state.askingTools == ["Send Email"])
    #expect(state.sentence == "Asks before Send Email: a run that uses it waits for your approval, even while this iPhone is closed.")
    #expect(automation(modes).body["policy"]?["tool_approval"] == .string("ask"))
}

@Test func manyToolsOnAskAreCounted() {
    let modes: [String: ToolMode] = ["a_tool": .ask, "b_tool": .ask, "c_tool": .ask, "d_tool": .ask, "e_tool": .ask]
    let state = AutomationApprovalState(tools: ConversationTools(modes: modes))
    #expect(state.sentence.hasPrefix("Asks before A Tool, B Tool, C Tool and 2 more: a run that uses one of them waits"))
}

@Test func theStateAlwaysMatchesWhatIsSent() {
    for modes: [String: ToolMode] in [[:], ["x": .off], ["x": .auto], ["x": .ask], ["x": .ask, "y": .auto, "z": .off]] {
        let state = AutomationApprovalState(tools: ConversationTools(modes: modes))
        #expect(automation(modes).toolApproval == (state.asks ? "ask" : "auto"), "modes \(modes)")
    }
}

@Test func toolModesUseTheKitWords() {
    #expect(Set(ToolMode.allCases.map(\.label)) == ["Off", "Ask", "Auto"])
    #expect(!ToolMode.allCases.map(\.label).contains("Approve"))
}
