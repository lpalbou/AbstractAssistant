import Foundation
import Testing
import AssistantKit
import AbstractGatewayClient

@Suite @MainActor struct ToolDefaultsTests {
    private let base = ConversationTools(modes: ["read_file": .auto, "fetch_url": .approve, "execute_command": .off])
    private func store(_ defaults: UserDefaults = UserDefaults(suiteName: "tool-defaults-\(UUID())")!) -> AssistantStore {
        let result = AssistantStore(defaults: defaults); result.connect(nil, client: MockGatewayClient()); return result
    }
    @Test func defaultsSurviveNewConversationsButConversationChoicesWin() {
        let store = store()
        store.setAppTools(base)
        #expect(store.conversationTools == nil && store.effectiveTools == base)
        let local = ConversationTools(modes: ["read_file": .off])
        store.setConversationTools(local)
        #expect(store.effectiveTools == local)
        store.setAppTools(.init(modes: [:]))
        #expect(store.effectiveTools == local) // An explicit conversation is not widened by defaults.
        store.setConversationTools(nil)
        #expect(store.effectiveTools?.allowed == [])
        store.setAppTools(base); store.newConversation()
        #expect(store.effectiveTools == base && store.conversationTools == nil)
        store.setAppTools(nil)
        #expect(store.effectiveTools == nil)
    }
    @Test func defaultsPersistAndStayScopedToGatewayAccountAcrossResponders() async {
        let defaults = UserDefaults(suiteName: "tool-defaults-\(UUID())")!
        let connection = SavedConnection(gateway: URL(string: "https://one.example")!, user: "alice", credential: .token("test"))
        let store = AssistantStore(defaults: defaults); store.connect(connection, client: MockGatewayClient())
        store.setAppTools(base); store.newConversation(entity: "castor")
        #expect(store.appTools == base)
        store.setAppTools(.init(modes: [:])); store.newConversation()
        #expect(store.appTools?.allowed == [])
        store.setAppTools(base)
        store.disconnect()
        let restored = AssistantStore(defaults: defaults); restored.connect(connection, client: MockGatewayClient())
        #expect(restored.appTools == base)
        restored.connect(.init(gateway: connection.gateway, user: "bob", credential: .token("test")), client: MockGatewayClient())
        #expect(restored.appTools == nil)
        restored.connect(.init(gateway: URL(string: "https://two.example")!, user: "alice", credential: .token("test")), client: MockGatewayClient())
        #expect(restored.appTools == nil)
    }
    @Test func legacyAssistantDefaultMigratesOnceForEveryResponder() throws {
        let defaults = UserDefaults(suiteName: "tool-migration-\(UUID())")!
        defaults.set(try JSONEncoder().encode(base), forKey: "phone.tools.defaults.demo.assistant")
        let first = store(defaults)
        #expect(first.appTools == base)
        first.newConversation(entity: "castor"); #expect(first.appTools == base)
        first.setAppTools(nil); first.disconnect()
        let reopened = store(defaults); #expect(reopened.appTools == nil)
        reopened.disconnect()
    }
    @Test func effectiveDefaultsActuallyTravelOnTheNextAssistantRequest() async {
        let client = MockGatewayClient(), store = AssistantStore(defaults: UserDefaults(suiteName: "tool-defaults-\(UUID())")!)
        store.connect(nil, client: client); store.setAppTools(base); store.send("Use my choices")
        for _ in 0..<1000 { if await !client.assistantToolSelections.isEmpty { break }; await Task.yield() }
        #expect(await client.assistantToolSelections == [base])
        store.disconnect()
    }
    @Test func editingWhileWorkingChangesTheNextTurnWithoutResendingTheActiveOne() async {
        let client = MockGatewayClient(), store = AssistantStore(defaults: UserDefaults(suiteName: "tool-defaults-\(UUID())")!)
        store.connect(nil, client: client); store.send("First request")
        for _ in 0..<1000 { if store.activeRunID != nil && store.canEditToolPreferences { break }; await Task.yield() }
        #expect(store.phase == .working && store.canEditToolPreferences)
        store.setAppTools(base)
        #expect(store.appTools == base)
        #expect(await client.assistantToolSelections.count == 1)
        #expect(await client.assistantToolSelections.first! == nil)
        store.disconnect()
    }
}
