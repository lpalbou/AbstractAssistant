import Foundation
import Testing
import AssistantKit
import PhoneGatewayClient

@Test func historyBudgetIsInheritedUnlessExplicitAndOnlyForGrowingRuns() {
    func body(_ growing: Bool, _ budget: Int?) -> JSONValue { NewAutomation(task: "Brief me", target: .gatewayDefault(interface: "abstractassistant.agent.v1"), when: .every("1d"), buildsOnEarlierRuns: growing, askBeforeTools: true, growingMaxTokens: budget).body }
    #expect(body(true, nil)["context"] == .object(["mode": .string("growing")]))
    #expect(body(true, 12000)["context"]?["growing"]?["max_tokens"] == .number(12000))
    #expect(body(false, 12000)["context"] == .object(["mode": .string("independent")]))
}

@Test @MainActor func statisticsStayOffByDefaultAndScopedToAnAccount() {
    let defaults = UserDefaults(suiteName: "stats-\(UUID())")!
    let a = PhonePreferences(scope: "a", defaults: defaults)
    #expect(!a.showMessageStats); a.showMessageStats = true
    #expect(PhonePreferences(scope: "a", defaults: defaults).showMessageStats)
    #expect(!PhonePreferences(scope: "b", defaults: defaults).showMessageStats)
}

@Test @MainActor func toolsStayScopedToResponderSessionAndGatewayAccount() async throws {
    let defaults = UserDefaults(suiteName: "tools-\(UUID())")!
    let store = AssistantStore(defaults: defaults), mock = MockGatewayClient()
    let a = SavedConnection(gateway: URL(string: "https://one.example")!, user: "alice", credential: .token("test"))
    store.connect(a, client: mock)
    let policy = ConversationTools(modes: ["read_file": .auto, "send_email": .approve, "execute_command": .off])
    store.setConversationTools(policy)
    #expect(store.conversationTools == policy)
    store.newConversation(entity: "castor"); #expect(store.conversationTools == nil)
    store.setConversationTools(.init(modes: [:])); #expect(store.conversationTools?.allowed == [])
    store.newConversation(); #expect(store.conversationTools == nil)
    store.connect(SavedConnection(gateway: a.gateway, user: "bob", credential: .token("test")), client: mock)
    #expect(store.conversationTools == nil)
}

@Test func aVisitWaitingForApprovalCannotRenderThePreviousAnswerAsComplete() throws {
    let state = try JSONDecoder().decode(EntitySessionState.self, from: Data(#"{"run_id":"v","status":"waiting","turn_n":2,"turn_complete":false,"pending_wait":{"reason":"user","wait_key":"tool_approval:v:act:key","details":{"mode":"approval_required","tool_calls":[{"name":"diary_read","arguments":{}}]}}}"#.utf8))
    #expect(!state.finishedTurn && state.reply == nil)
    #expect(state.personWait?.details?.first?.name == "diary_read")
}
