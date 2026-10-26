import Foundation
import Testing
@testable import AbstractGatewayClient

@Test func explicitAutomationTitleDoesNotReplaceOrTruncateItsTask() {
    let task = "Read the workspace notes.\nReport the important changes and their sources."
    let named = NewAutomation(task: task, target: .gatewayDefault(interface: "abstractassistant.agent.v1"), when: .every("24h"), buildsOnEarlierRuns: false, askBeforeTools: true, title: "  Morning briefing  ")
    #expect(named.body["title"] == .string("Morning briefing"))
    #expect(named.body["target"]?["input_data"]?["prompt"] == .string(task))
    var legacy = named; legacy.customTitle = "  "
    #expect(legacy.title == "Read the workspace notes.")
    legacy.task = String(repeating: "a", count: 200)
    #expect(legacy.title.count == 120)
}
