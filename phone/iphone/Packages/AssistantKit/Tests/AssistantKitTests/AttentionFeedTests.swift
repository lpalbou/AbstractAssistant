import Foundation
import Testing
import AssistantKit
import AbstractGatewayClient

/// The iPhone follows the person's event stream (backlog 1047): catch-up at launch (history never
/// notifies), the SSE tail while in front resuming from the cursor, a local notice per new item,
/// state kept across launches, the lists re-read on change, and a gateway without the stream left alone.
@MainActor
struct AttentionFeedTests {
    private func raised(_ seq: Int, _ aid: String, _ item: Int) -> UserEvent {
        UserEvent(id: "r\(seq)", type: "attention.raised", sequence: seq,
                  data: .object(["automation_id": .string(aid), "seq": .number(Double(item)), "kind": .string("notify"),
                                 "record_key": .string("automation:completed:\(aid):\(item)")]))
    }
    private func until(_ timeout: Double = 5, _ predicate: () async -> Bool) async throws {
        let end = Date().addingTimeInterval(timeout)
        while Date() < end { if await predicate() { return }; try await Task.sleep(for: .milliseconds(20)) }
        Issue.record("condition not reached in time")
    }

    @Test func launchCatchesUpSilentlyThenTheTailNotifiesAndResumesFromTheCursor() async throws {
        let defaults = UserDefaults(suiteName: "attention-feed-\(UUID())")!
        let mock = MockGatewayClient()
        await mock.appendEvent(raised(1, "digest", 1))
        let feed = AttentionFeed(defaults: defaults)
        feed.reconnectDelay = 0.05
        var told: [AttentionNotice] = []
        var changes = 0
        feed.onNotice = { told.append($0) }
        feed.onChange = { changes += 1 }
        feed.start(client: mock, scope: "s", foreground: true)
        try await until { feed.status == .following && feed.state.cursor == 1 }
        #expect(told.isEmpty, "what happened before the first look is never a notification")
        #expect(feed.newResults == 1)

        await mock.appendEvent(raised(2, "digest", 2))
        try await until { told.count == 1 }
        #expect(told.first?.recordKey == "automation:completed:digest:2" && feed.newResults == 2 && changes >= 1)
        // Shown: recorded once on the stream as this iPhone's.
        feed.reportShown(told[0])
        try await until { await mock.reports.count == 1 }
        #expect(await mock.reports == [NotificationReport(channel: "phone", recordKey: "automation:completed:digest:2", device: feed.deviceID)])
        try await until { await mock.streamOpens.count >= 2 }
        let opens = await mock.streamOpens
        #expect(opens.first == 1 && opens.dropFirst().allSatisfy { $0 >= 2 }, "each tail resumes after the last event read: \(opens)")

        // In the background: no tail; a new launch with the kept state never repeats what was told.
        feed.setForeground(false)
        await mock.appendEvent(raised(3, "digest", 3))
        let again = AttentionFeed(defaults: defaults)
        var toldAgain: [AttentionNotice] = []
        again.onNotice = { toldAgain.append($0) }
        again.start(client: mock, scope: "s", foreground: false)
        try await until { again.state.cursor == 3 }
        #expect(toldAgain.map(\.recordKey) == ["automation:completed:digest:3"])
        feed.stop(); again.stop()
    }

    @Test func aGatewayWithoutTheStreamIsLeftToThePolls() async throws {
        let feed = AttentionFeed(defaults: UserDefaults(suiteName: "attention-feed-\(UUID())")!)
        let mock = MockGatewayClient()
        await mock.setEventsUnsupported(true)
        feed.start(client: mock, scope: "s", foreground: true)
        try await until { feed.status == .unsupported }
        #expect(await mock.streamOpens.isEmpty, "no tail is opened on a gateway without the stream")
        feed.stop()
    }

    @Test func theInboxBadgeCountsTheStreamsOpenWaitsBeforeTheListIsReadAgain() async throws {
        let store = AssistantStore(defaults: UserDefaults(suiteName: "attention-store-\(UUID())")!)
        let mock = MockGatewayClient(waits: [])
        await mock.appendEvent(UserEvent(id: "w1", type: "attention.raised", sequence: 1, data: .object([
            "kind": .string("approval"), "run_id": .string("r1"), "session_id": .string("s"), "wait_key": .string("k"),
            "step_id": .string("a"), "record_key": .string("wait:r1:k:a")])))
        store.connect(nil, client: mock)
        try await until { store.attention.state.cursor == 1 }
        #expect(store.waits.isEmpty && store.inboxBadge == 1)
        await mock.appendEvent(UserEvent(id: "s1", type: "attention.seen", sequence: 2, data: .object([
            "kind": .string("approval"), "run_id": .string("r1"), "wait_key": .string("k"), "step_id": .string("a"),
            "outcome": .string("approved")])))
        store.setForeground(true)
        try await until { store.inboxBadge == 0 }
        store.disconnect()
    }
}
