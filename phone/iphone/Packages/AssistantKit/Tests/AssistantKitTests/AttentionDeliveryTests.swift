import Testing
import AbstractGatewayClient
import Foundation
@testable import AssistantKit

@MainActor struct AttentionDeliveryTests {
    private func until(_ predicate: () async -> Bool) async throws -> Bool {
        let end = Date().addingTimeInterval(3)
        while Date() < end {
            if await predicate() { return true }
            try await Task.sleep(for: .milliseconds(10))
        }
        return false
    }

    @Test(arguments: [false, true])
    func permissionPauseReconcilesBeforePostingEvenWithImmediatelyClosingSSETails(_ consumedOnDesktop: Bool) async throws {
        let client = GatedWaitsClient()
        await client.closeEveryTailImmediately()
        let feed = AttentionFeed(defaults: UserDefaults(suiteName: "delivery-feed-\(UUID())")!)
        feed.reconnectDelay = 0.01
        var enqueued = 0, withdrawn = 0, prepared = 0
        var result: Bool?
        var delivery: Task<Void, Never>?
        defer { delivery?.cancel(); feed.stop() }
        feed.onNotice = { notice in
            let validator = feed.noticeValidator(notice)
            delivery = Task {
                let posted = await AttentionDelivery.post(isCurrent: validator, prepare: {
                    prepared += 1
                    // The system permission sheet backgrounds the app. Desktop consumption may
                    // arrive during that pause; resumption must reconcile before deciding.
                    feed.setForeground(false)
                    if consumedOnDesktop {
                        await client.mock.appendEvent(UserEvent(id: "read", type: "attention.seen", sequence: 2,
                            data: .object(["automation_id": .string("digest"), "seq": .number(1)])))
                    }
                    feed.setForeground(true)
                    return true
                }, enqueue: { enqueued += 1 }, withdraw: { withdrawn += 1 })
                if posted { feed.reportShown(notice) }
                result = posted
            }
        }
        feed.start(client: client, scope: "s", foreground: true)
        #expect(try await until { await client.tailStarts.count >= 1 })
        await client.mock.appendEvent(UserEvent(id: "new", type: "attention.raised", sequence: 1,
            data: .object(["kind": .string("notify"), "automation_id": .string("digest"), "seq": .number(1),
                           "record_key": .string("fresh-unread-record")])))
        let completed = try await until { result != nil }
        #expect(completed, "a healthy REST head must release delivery despite immediate SSE EOF")
        if !completed { delivery?.cancel(); feed.stop(); return }
        #expect(result == !consumedOnDesktop)
        #expect(prepared == 1 && withdrawn == 0)
        #expect(enqueued == (consumedOnDesktop ? 0 : 1))
        if !consumedOnDesktop { #expect(try await until { await client.mock.reports.count == 1 }) }
        #expect(await client.mock.reports.count == (consumedOnDesktop ? 0 : 1))
        #expect(await client.tailStarts.count >= 2)
    }

    @Test func anAlreadyConsumedNoticeNeverEvenAsksPermission() async {
        var prepared = false, posted = false
        let delivered = await AttentionDelivery.post(isCurrent: { false }, prepare: { prepared = true; return true },
            enqueue: { posted = true }, withdraw: { })
        #expect(!delivered && !prepared && !posted)
    }

    @Test func consumedWhilePermissionOrDeliveredStatusWasAwaitedDoesNotPost() async throws {
        var state = AttentionState()
        state.caughtUp = true
        let raised = UserEvent(id: "ask", type: "attention.raised", sequence: 1,
            data: .object(["run_id": .string("r1"), "wait_key": .string("approval"), "record_key": .string("an-opaque-record")]))
        let notice = try #require(state.apply(.init(events: [raised], nextAfter: 1, head: 1, more: false)).first)
        var posted = false
        let delivered = await AttentionDelivery.post(isCurrent: { state.isCurrent(notice) }, prepare: {
            await Task.yield()
            let seen = UserEvent(id: "read-on-desktop", type: "attention.seen", sequence: 2,
                data: .object(["record_key": .string("an-opaque-record")]))
            _ = state.apply(.init(events: [seen], nextAfter: 2, head: 2, more: false))
            return true
        }, enqueue: { posted = true }, withdraw: { })
        #expect(!delivered && !posted)
    }

    @Test func consumedWhileEnqueueWasAwaitedWithdrawsWithoutReportingShown() async {
        var current = true, posted = false, withdrawn = false
        let delivered = await AttentionDelivery.post(isCurrent: { current }, prepare: { true }, enqueue: {
            posted = true
            await Task.yield()
            current = false
        }, withdraw: { withdrawn = true })
        #expect(!delivered && posted && withdrawn)
    }

    @Test func anAlreadyDeliveredItemIsNotPostedAgain() async {
        var posted = false
        let delivered = await AttentionDelivery.post(isCurrent: { true }, prepare: { false },
            enqueue: { posted = true }, withdraw: { })
        #expect(!delivered && !posted)
    }

    @Test func aFreshCurrentNoticePostsOnce() async {
        var count = 0, withdrawn = false
        let delivered = await AttentionDelivery.post(isCurrent: { true }, prepare: { true },
            enqueue: { count += 1 }, withdraw: { withdrawn = true })
        #expect(delivered && count == 1 && !withdrawn)
    }

    @Test func anEnqueueFailureIsNotReportedShown() async {
        struct Refused: Error { }
        let delivered = await AttentionDelivery.post(isCurrent: { true }, prepare: { true },
            enqueue: { throw Refused() }, withdraw: { Issue.record("Nothing was enqueued") })
        #expect(!delivered)
    }
}
