import Foundation
import Testing
import AssistantKit
import PhoneGatewayClient

@Test func categoryOverridesMaterializeDefaultsAndIgnoreSearchWithoutGrantingDisabledTools() {
    let rows = [ToolInfo(name: "read", riskTier: "observe", riskRank: 0, toolset: "files", approvalDefault: "auto"),
                ToolInfo(name: "write", riskTier: "act", riskRank: 2, toolset: "files", approvalDefault: "ask"),
                ToolInfo(name: "blocked", riskTier: nil, riskRank: nil, toolset: "files", enabled: false),
                ToolInfo(name: "send", riskTier: nil, riskRank: nil, toolset: "comms", approvalDefault: "ask")]
    let inherited = ConversationTools.snapshot(nil, inventory: rows)
    #expect(inherited.categoryMode("files", inventory: rows) == nil)
    let enabled = inherited.settingCategory("files", to: .auto, inventory: rows)
    #expect(enabled.modes == ["read": .auto, "write": .auto, "blocked": .off, "send": .approve])
    #expect(enabled.categoryMode("files", inventory: rows) == .auto)
    let off = enabled.settingCategory("files", to: .off, inventory: rows)
    #expect(off.allowed == ["send"])
    #expect(off.settingCategory("files", to: .approve, inventory: rows).modes["write"] == .approve)
    #expect(ToolCatalogGroup.groups(rows, matching: "read").first?.tools.count == 1)
}

@Test func historyGroupsAtLocalMidnightAndReportsExplicitAges() throws {
    var calendar = Calendar(identifier: .gregorian); calendar.timeZone = TimeZone(secondsFromGMT: 7200)!
    let now = ISO8601.date("2026-10-18T22:05:00Z")!
    func session(_ id: String, _ date: String) throws -> SessionSummary {
        try #require(SessionSummary.group([RunSummary(runId: id, workflowId: nil, status: "completed", sessionId: id, updatedAt: date)]).first)
    }
    let sections = ConversationHistorySection.grouped(try [session("today", "2026-10-18T22:01:00Z"), session("yesterday", "2026-10-18T21:59:00Z"), session("older", "2026-10-16T22:00:00Z")], now: now, calendar: calendar)
    #expect(sections.map(\.id) == ["Today", "Yesterday", "Earlier"])
    #expect(sections.map { $0.sessions.first!.id } == ["today", "yesterday", "older"])
    #expect(ConversationHistorySection.age(now.addingTimeInterval(-540), now: now) == "9 min ago")
    #expect(ConversationHistorySection.age(now.addingTimeInterval(30), now: now) == "just now")
}

@Test func olderActiveTurnMakesTheWholeSessionUnarchivable() throws {
    let rows = [RunSummary(runId: "new", workflowId: nil, status: "completed", sessionId: "s"), RunSummary(runId: "old", workflowId: nil, status: "running", sessionId: "s")]
    #expect(try #require(SessionSummary.group(rows).first).isLive)
}

@Test @MainActor func archiveRestoreAndCurrentConversationResetUseTheGateway() async throws {
    let client = MockGatewayClient(historyFixture: true)
    let store = AssistantStore(defaults: UserDefaults(suiteName: "history-actions-\(UUID())")!)
    store.connect(nil, client: client); await store.refresh()
    let session = try #require(store.sessions.first)
    await store.openSession(session)
    #expect(store.sessionID == session.id && !store.messages.isEmpty)
    #expect(await store.setArchived(session, true))
    #expect(store.sessions.isEmpty && store.sessionID != session.id && store.messages.isEmpty)
    await store.refresh(); #expect(store.sessions.isEmpty)
    await store.loadArchivedConversations()
    #expect(store.archivedSessions.map(\.id) == [session.id])
    #expect(await store.setArchived(session, false))
    #expect(store.archivedSessions.isEmpty && store.sessions.map(\.id) == [session.id])
    await store.refresh(); #expect(store.sessions.map(\.id) == [session.id])
    store.disconnect()
}

@Test @MainActor func activeConversationArchiveIsBlocked() async throws {
    let client = MockGatewayClient()
    let store = AssistantStore(defaults: UserDefaults(suiteName: "history-active-\(UUID())")!)
    store.connect(nil, client: client); await store.refresh()
    let active = try #require(store.sessions.first { $0.isLive })
    #expect(!store.canArchive(active)); #expect(!(await store.setArchived(active, true)))
    #expect(try await client.archivedRuns(limit: 200).isEmpty)
    store.disconnect()
}
