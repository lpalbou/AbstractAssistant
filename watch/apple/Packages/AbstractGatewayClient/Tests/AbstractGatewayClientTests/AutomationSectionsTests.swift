import Foundation
import Testing
@testable import AbstractGatewayClient

/// ADR 0048: the Apple apps draw the gateway's automations as served — the main rows in the served
/// order, the paused ones behind a folded "Paused" section with the gateway's count — and an older
/// gateway (no `section`) gets today's list.
@Suite struct AutomationSectionsTests {
    private func page(_ json: String) throws -> AutomationsPage {
        try JSONDecoder().decode(AutomationsPage.self, from: Data(json.utf8))
    }

    @Test func aServedPageIsDrawnInItsOrderWithThePausedOnesFolded() throws {
        let p = try page("""
        {"items":[
          {"automation_id":"b","title":"B","status":"active","section":"active","last_activity_at":"2026-11-02T10:00:00+00:00"},
          {"automation_id":"a","title":"A","status":"completed","section":"active","last_activity_at":"2026-11-01T10:00:00+00:00"},
          {"automation_id":"p","title":"P","status":"paused","section":"paused","last_activity_at":"2026-11-02T12:00:00+00:00"}],
         "next_cursor":null,"paused_automations_count":3,"archived_automations_count":1,"archived_automations":1}
        """)
        #expect(p.pausedAutomations == 3 && p.archivedAutomations == 1)
        #expect(archivedLabel(p.archivedAutomations) == "Archived · 1" && archivedLabel(0) == "Archived" && archivedLabel(nil) == "Archived")
        let s = AutomationSections(p)
        #expect(s.main.map(\.id) == ["b", "a"])          // the served order, never re-sorted
        #expect(s.pausedCount == 3 && s.showsPaused)       // the gateway's count, not the page's
        #expect(p.items.map(\.section) == ["active", "active", "paused"])
    }

    @Test func anOlderGatewayGetsTodaysList() throws {
        let p = try page("""
        {"items":[{"automation_id":"p","title":"P","status":"paused"},{"automation_id":"a","title":"A","status":"active"}],
         "next_cursor":null,"archived_automations":2}
        """)
        let s = AutomationSections(p)
        #expect(s.main.map(\.id) == ["p", "a"])           // every row, as it came
        #expect(s.pausedCount == nil && !s.showsPaused)    // no Paused section: never derived from `status`
        #expect(p.archivedAutomations == 2)                 // an older gateway's `archived_automations`
    }

    @Test func noPausedAutomationNoPausedSection() throws {
        let s = AutomationSections(try page(#"{"items":[{"automation_id":"a","status":"active","section":"active"}],"paused_automations_count":0}"#))
        #expect(s.main.map(\.id) == ["a"] && s.pausedCount == 0 && !s.showsPaused)
    }

    @Test func theMockServesTheGatewaysOrder() async throws {
        let mock = MockGatewayClient(world: .watch, pausedSamples: true)
        try await mock.automationCommand(id: "auto-lit", type: "automation.pause")
        let p = try await mock.automationList()
        let s = AutomationSections(p)
        #expect(!s.main.contains { $0.id == "auto-lit" })
        #expect(p.items.suffix(3).map(\.id) == ["auto-lit", "auto-consolidate", "auto-reflect"])
        #expect(s.pausedCount == 3)
        #expect(try await mock.pausedAutomations().map(\.id) == ["auto-lit", "auto-consolidate", "auto-reflect"])
    }
}
