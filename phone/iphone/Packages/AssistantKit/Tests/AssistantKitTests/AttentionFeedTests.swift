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
    private func seen(_ seq: Int, _ aid: String, _ item: Int) -> UserEvent {
        UserEvent(id: "seen\(seq)", type: "attention.seen", sequence: seq,
                  data: .object(["automation_id": .string(aid), "seq": .number(Double(item))]))
    }
    private func keep(_ state: AttentionState, in defaults: UserDefaults, scope: String = "s") throws {
        defaults.set(try JSONEncoder().encode(state), forKey: "phone.attention." + scope)
    }
    private func until(_ timeout: Double = 5, _ predicate: () async -> Bool) async throws {
        let end = Date().addingTimeInterval(timeout)
        while Date() < end { if await predicate() { return }; try await Task.sleep(for: .milliseconds(20)) }
        Issue.record("condition not reached in time")
    }

    @Test func launchCatchesUpSilentlyThenTheTailNotifiesAndResumesFromTheCursor() async throws {
        let defaults = UserDefaults(suiteName: "attention-feed-\(UUID())")!
        let mock = MockGatewayClient(world: .phone)
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
        let mock = MockGatewayClient(world: .phone)
        await mock.setEventsUnsupported(true)
        feed.start(client: mock, scope: "s", foreground: true)
        try await until { feed.status == .unsupported }
        #expect(await mock.streamOpens.isEmpty, "no tail is opened on a gateway without the stream")
        feed.stop()
    }

    @Test func replayReconcilesSeenOnLaterPagesBeforeAnnouncingPendingAttention() async throws {
        let defaults = UserDefaults(suiteName: "attention-feed-\(UUID())")!
        var state = AttentionState(); state.caughtUp = true
        try keep(state, in: defaults)
        let client = GatedWaitsClient()
        await client.configureEvents(pageSize: 1)
        for event in [raised(1, "old", 1), seen(2, "old", 1), raised(3, "pending", 1)] {
            await client.mock.appendEvent(event)
        }
        let feed = AttentionFeed(defaults: defaults)
        var told: [AttentionNotice] = []
        feed.onNotice = { told.append($0) }
        feed.start(client: client, scope: "s", foreground: false)
        try await until { feed.state.cursor == 3 }
        #expect(told.map(\.recordKey) == ["automation:completed:pending:1"])
        #expect(feed.newResults == 1)
        #expect(feed.state.resolvedNotificationIdentifiers.contains(AttentionNotice.collapseID("automation:completed:old:1")))
        feed.stop()
    }

    @Test func aFailedReplayDoesNotCommitItsCursorOrLoseAnUnreadCandidate() async throws {
        let defaults = UserDefaults(suiteName: "attention-feed-\(UUID())")!
        var state = AttentionState(); state.caughtUp = true
        try keep(state, in: defaults)
        let client = GatedWaitsClient()
        await client.configureEvents(pageSize: 1, failOnceAfter: 1)
        await client.mock.appendEvent(raised(1, "pending", 1))
        await client.mock.appendEvent(UserEvent(id: "start", type: "run.started", sequence: 2))
        let feed = AttentionFeed(defaults: defaults)
        feed.reconnectDelay = 0.2
        var told: [AttentionNotice] = []
        feed.onNotice = { told.append($0) }
        feed.start(client: client, scope: "s", foreground: true)
        try await until { await client.failedEventRead }
        #expect(feed.state.cursor == 0 && told.isEmpty)
        let persisted = try JSONDecoder().decode(AttentionState.self, from: defaults.data(forKey: "phone.attention.s")!)
        #expect(persisted.cursor == 0)
        try await until { feed.state.cursor == 2 }
        #expect(told.map(\.recordKey) == ["automation:completed:pending:1"])
        feed.stop()
    }

    @Test func reconnectReconcilesRestBeforeReopeningAnSSETail() async throws {
        let client = GatedWaitsClient()
        await client.configureEvents(pageSize: 1)
        let finished = UserEvent(id: "finished", type: "run.finished", sequence: 1, data: .object([
            "run_id": .string("r"), "status": .string("completed"),
            "origin": .object(["kind": .string("trigger"), "ref": .object([
                "automation_id": .string("digest"), "occurrence_index": .number(1)])])]))
        await client.injectOnNextTail([finished, raised(2, "digest", 1), seen(3, "digest", 1), raised(4, "new", 1)])
        let feed = AttentionFeed(defaults: UserDefaults(suiteName: "attention-feed-\(UUID())")!)
        feed.reconnectDelay = 0.01
        var told: [AttentionNotice] = []
        feed.onNotice = { told.append($0) }
        feed.start(client: client, scope: "s", foreground: true)
        try await until { await client.tailStarts.count >= 2 }
        #expect(await client.tailStarts.prefix(2) == [0, 4], "the second tail starts after the reconciled head")
        #expect(await client.eventReads.count >= 5)
        #expect(told.map(\.recordKey) == ["automation:completed:new:1"], "neither the quiet finish nor the seen result alerts")
        feed.stop()
    }

    @Test func legacyCacheRebuildDismissesHistoryAndStillNotifiesANewOfflineItem() async throws {
        let defaults = UserDefaults(suiteName: "attention-feed-\(UUID())")!
        defaults.set(Data(#"{"cursor":10,"caughtUp":true,"waits":[],"raised":{},"seen":{"old":1},"resolved":[],"shown":{}}"#.utf8),
                     forKey: "phone.attention.s")
        let client = GatedWaitsClient()
        await client.configureEvents(pageSize: 1)
        for event in [raised(1, "old", 1), seen(2, "old", 1), raised(11, "new", 1)] {
            await client.mock.appendEvent(event)
        }
        let feed = AttentionFeed(defaults: defaults)
        var told: [AttentionNotice] = []
        feed.onNotice = { told.append($0) }
        feed.start(client: client, scope: "s", foreground: false)
        try await until { feed.state.cursor == 11 }
        #expect(told.map(\.recordKey) == ["automation:completed:new:1"])
        #expect(feed.state.resolvedNotificationIdentifiers.contains(AttentionNotice.collapseID("automation:completed:old:1")))
        feed.stop()
    }

    @Test func queuedNoticeValidationWaitsForReconciliationEvenWhenCatchupIsCanceled() async throws {
        let client = GatedWaitsClient()
        await client.mock.appendEvent(raised(1, "digest", 1))
        let feed = AttentionFeed(defaults: UserDefaults(suiteName: "attention-feed-\(UUID())")!)
        feed.start(client: client, scope: "s", foreground: true)
        try await until { feed.status == .following && feed.state.cursor == 1 }
        let notice = AttentionNotice.news(automationId: "digest", seq: 1, failed: false,
                                         recordKey: "automation:completed:digest:1")
        let valid = feed.noticeValidator(notice)
        #expect(await valid())
        feed.setForeground(false)
        var resumed = false
        let queued = Task { let result = await valid(); resumed = true; return result }
        await client.mock.appendEvent(seen(2, "digest", 1))
        await client.gateEvents(after: 1)
        feed.setForeground(true)
        try await until { await client.eventsGated }
        #expect(!resumed && !feed.isCurrent(notice), "validation waits while a seen page is staged")
        feed.setForeground(false)
        #expect(!resumed && !feed.isCurrent(notice), "canceling the catch-up must not revalidate its stale snapshot")
        await client.releaseEvents()
        feed.setForeground(true)
        try await until { feed.status == .following && feed.state.cursor == 2 }
        #expect(await queued.value == false)
        feed.stop()
    }

    @Test func queuedNoticeResumesAfterAReconciledHeadIfItIsStillUnread() async throws {
        let client = GatedWaitsClient()
        await client.mock.appendEvent(raised(1, "digest", 1))
        let feed = AttentionFeed(defaults: UserDefaults(suiteName: "attention-feed-\(UUID())")!)
        feed.start(client: client, scope: "s", foreground: true)
        try await until { feed.status == .following && feed.state.cursor == 1 }
        let notice = AttentionNotice.news(automationId: "digest", seq: 1, failed: false,
                                         recordKey: "automation:completed:digest:1")
        let valid = feed.noticeValidator(notice)
        feed.setForeground(false)
        var resumed = false
        let queued = Task { let result = await valid(); resumed = true; return result }
        await client.gateEvents(after: 1)
        feed.setForeground(true)
        try await until { await client.eventsGated }
        #expect(!resumed)
        await client.releaseEvents()
        #expect(await queued.value)
        feed.stop()
    }

    @Test func cancelingAQueuedValidationDoesNotLeaveItWaitingForAnotherForeground() async throws {
        let mock = MockGatewayClient(world: .phone)
        let feed = AttentionFeed(defaults: UserDefaults(suiteName: "attention-feed-\(UUID())")!)
        feed.start(client: mock, scope: "s", foreground: true)
        try await until { feed.status == .following }
        feed.setForeground(false)
        let valid = feed.noticeValidator(.news(automationId: "a", seq: 1, failed: false))
        let queued = Task { await valid() }
        await Task.yield()
        queued.cancel()
        #expect(await queued.value == false)
        feed.stop()
    }

    @Test func validatorsNeverCrossAccountSwitchesEvenWhenTheRecordIdentityIsTheSame() async throws {
        let feed = AttentionFeed(defaults: UserDefaults(suiteName: "attention-feed-\(UUID())")!)
        let a = MockGatewayClient(world: .phone), b = MockGatewayClient(world: .phone)
        await a.appendEvent(raised(1, "same", 1)); await b.appendEvent(raised(1, "same", 1))
        let notice = AttentionNotice.news(automationId: "same", seq: 1, failed: false,
                                         recordKey: "automation:completed:same:1")
        feed.start(client: a, scope: "a", foreground: true)
        try await until { feed.status == .following && feed.state.cursor == 1 }
        let original = feed.noticeValidator(notice)
        #expect(await original())
        feed.start(client: b, scope: "b", foreground: true)
        try await until { feed.status == .following && feed.state.cursor == 1 }
        #expect(await original() == false)
        #expect(await feed.noticeValidator(notice)())
        feed.start(client: a, scope: "a", foreground: true)
        try await until { feed.status == .following && feed.state.cursor == 1 }
        #expect(await original() == false)
        #expect(await feed.noticeValidator(notice)())
        feed.stop()
        #expect(await feed.noticeValidator(notice)() == false)
    }

    /// The gateway's `attention.raised` for a question (live shape, `events_stream.record_wait_raised`).
    private func question(_ seq: Int, run: String) -> UserEvent {
        UserEvent(id: "q\(seq)", type: "attention.raised", sequence: seq, data: .object([
            "kind": .string("question"), "wait_kind": .string("ask_user"), "run_id": .string(run), "session_id": .string("editor"),
            "wait_key": .string("user:\(run):node-2"), "step_id": .string("a477de2d"), "record_key": .string("dc3bcd00"),
            "prompt_ref": .string("/api/gateway/runs/\(run)")]))
    }

    /// The screenshot of 2026-10-26: "Nothing needs you" over an Inbox tab badged "1". The stream held an
    /// open question for a flow editor's draft-test run (parked since June), which `GET /runs?status=waiting`
    /// leaves out (`include_drafts` is false by default), so the list the Inbox shows never had it.
    /// The badge is the number of rows the Inbox shows, never the stream's own count.
    @Test func theInboxBadgeNeverCountsAWaitTheInboxDoesNotShow() async throws {
        let store = AssistantStore(defaults: UserDefaults(suiteName: "attention-store-\(UUID())")!)
        let mock = MockGatewayClient(world: .phone, waits: [])
        await mock.appendEvent(question(1, run: "af48c76f"))
        store.connect(nil, client: mock)
        try await until { store.attention.state.cursor == 1 }
        await store.refresh()  // a no-op when the stream's change already started one: wait for it
        try await until { store.lastRefresh != nil && !store.isRefreshing }
        #expect(store.lastRefresh != nil && store.waits.isEmpty, "the Inbox reads \"Nothing needs you\"")
        #expect(store.attention.state.needYou == 1, "the stream does hold the draft run's question")
        #expect(store.inboxBadge == store.waits.count && store.inboxBadge == 0, "badge \(store.inboxBadge), rows \(store.waits.count)")
        store.disconnect()
    }

    /// A raise on the stream reads the list again: the badge follows as soon as the row is there to open.
    @Test func aRaiseOnTheStreamReadsTheListAgainAndTheBadgeCountsItsRows() async throws {
        let store = AssistantStore(defaults: UserDefaults(suiteName: "attention-store-\(UUID())")!)
        let wait = MockGatewayClient.sampleWaits[0]
        let mock = MockGatewayClient(world: .phone, waits: [wait])
        await mock.appendEvent(UserEvent(id: "w1", type: "attention.raised", sequence: 1, data: .object([
            "kind": .string("approval"), "run_id": .string(wait.runId), "session_id": .string("s"), "wait_key": .string(wait.waitKey),
            "step_id": .string("a"), "record_key": .string("wait:\(wait.runId):\(wait.waitKey):a")])))
        #expect(store.inboxBadge == 0)
        store.connect(nil, client: mock)
        try await until { store.waits.map(\.id) == [wait.id] }
        #expect(store.inboxBadge == 1)
        store.disconnect()
    }

    /// A raise read while a refresh is already reading the list (which then returns the list from
    /// before the raise) reads it once more, instead of leaving the Inbox and its badge stale until the
    /// next 15-second poll.
    @Test func aRaiseDuringARefreshReadsTheListOnceMore() async throws {
        let store = AssistantStore(defaults: UserDefaults(suiteName: "attention-store-\(UUID())")!)
        let client = GatedWaitsClient()
        store.connect(nil, client: client)
        let first = Task { await store.refresh() }
        try await until { await client.gated }
        let wait = MockGatewayClient.sampleWaits[0]
        await client.setWaits([wait])
        await client.mock.appendEvent(UserEvent(id: "w1", type: "attention.raised", sequence: 1, data: .object([
            "kind": .string("approval"), "run_id": .string(wait.runId), "wait_key": .string(wait.waitKey), "step_id": .string("a")])))
        store.attention.setForeground(true)
        try await until { store.attention.state.cursor == 1 }
        await client.release(); await first.value
        try await until { store.waits.map(\.id) == [wait.id] }
        #expect(store.inboxBadge == 1 && store.waits.count == 1)
        store.disconnect()
    }
}

/// The mock, except that the first `waits()` returns the list as it was when asked, and only once released.
actor GatedWaitsClient: GatewayClient {
    nonisolated let isMock = true
    let mock = MockGatewayClient(world: .phone, waits: [])
    private var current: [Wait] = []
    private var calls = 0
    private var continuation: CheckedContinuation<Void, Never>?
    private var pageSize = 1000
    private var failAfter: Int?
    private var gateAfter: Int?
    private var eventContinuation: CheckedContinuation<Void, Never>?
    private var injectedTail: [UserEvent]?
    private var immediateTail = false
    private(set) var failedEventRead = false
    private(set) var eventReads: [Int] = []
    private(set) var tailStarts: [Int] = []
    var eventsGated: Bool { eventContinuation != nil }
    func configureEvents(pageSize: Int, failOnceAfter: Int? = nil) { self.pageSize = pageSize; failAfter = failOnceAfter }
    func gateEvents(after: Int) { gateAfter = after }
    func releaseEvents() { eventContinuation?.resume(); eventContinuation = nil }
    func injectOnNextTail(_ events: [UserEvent]) { injectedTail = events }
    func closeEveryTailImmediately() { immediateTail = true }
    private func openTail(_ cursor: Int) -> [UserEvent]? {
        tailStarts.append(cursor)
        defer { injectedTail = nil }
        if immediateTail { return [] }
        return injectedTail
    }
    var gated: Bool { continuation != nil }
    func setWaits(_ waits: [Wait]) { current = waits }
    func release() { continuation?.resume(); continuation = nil }
    func waits() async throws -> [Wait] {
        calls += 1
        let snapshot = current
        if calls == 1 { await withCheckedContinuation { continuation = $0 } }
        return snapshot
    }
    func me() async throws -> Principal { try await mock.me() }
    func health() async throws -> Bool { true }
    func reportNotification(_ report: NotificationReport) async throws { try await mock.reportNotification(report) }
    func events(after: Int, limit: Int) async throws -> UserEventsPage {
        eventReads.append(after)
        if failAfter == after {
            failAfter = nil; failedEventRead = true
            throw URLError(.networkConnectionLost)
        }
        let page = try await mock.events(after: after, limit: min(limit, pageSize))
        if gateAfter == after {
            gateAfter = nil
            await withCheckedContinuation { eventContinuation = $0 }
        }
        return page
    }
    nonisolated func userEventStream(lastEventID: Int) -> AsyncThrowingStream<UserEvent, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                if let injected = await self.openTail(lastEventID) {
                    for event in injected { await self.mock.appendEvent(event) }
                    continuation.finish(); return
                }
                do {
                    for try await event in self.mock.userEventStream(lastEventID: lastEventID) { continuation.yield(event) }
                    continuation.finish()
                } catch { continuation.finish(throwing: error) }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }
    func recentRuns(limit: Int) async throws -> [RunSummary] { try await mock.recentRuns(limit: limit) }
    func prompt(ofRun id: String) async throws -> String? { try await mock.prompt(ofRun: id) }
    func turns(ofSession id: String) async throws -> [RunSummary] { try await mock.turns(ofSession: id) }
    func run(id: String) async throws -> RunSummary { try await mock.run(id: id) }
    func startRun(prompt: String, sessionId: String?, toolPolicy: RunToolPolicy?) async throws -> String { try await mock.startRun(prompt: prompt, sessionId: sessionId, toolPolicy: toolPolicy) }
    func tools() async throws -> [ToolInfo] { try await mock.tools() }
    func answer(_ wait: Wait, with answer: WaitAnswer) async throws { try await mock.answer(wait, with: answer) }
    func automations() async throws -> [AutomationSummary] { try await mock.automations() }
    func runAutomationNow(id: String) async throws { try await mock.runAutomationNow(id: id) }
    func automationCommand(id: String, type: String) async throws { try await mock.automationCommand(id: id, type: type) }
    func automation(id: String) async throws -> AutomationSummary { try await mock.automation(id: id) }
    func workflows(forInterface interface: String) async throws -> [WorkflowChoice] { try await mock.workflows(forInterface: interface) }
    func workflowInputs(_ w: WorkflowChoice) async throws -> WorkflowInputs { try await mock.workflowInputs(w) }
    func createAutomation(_ a: NewAutomation) async throws -> AutomationSummary { try await mock.createAutomation(a) }
    func automationDefinition(id: String) async throws -> AutomationDefinition { try await mock.automationDefinition(id: id) }
    func reviseAutomation(id: String, changes: [String: JSONValue], expectedRevision: Int?) async throws { try await mock.reviseAutomation(id: id, changes: changes, expectedRevision: expectedRevision) }
    func entities() async throws -> [EntitySummary] { try await mock.entities() }
    func openEntityChat(name: String) async throws -> String { try await mock.openEntityChat(name: name) }
    func entityChatTurn(name: String, chatId: String, text: String) async throws -> String { try await mock.entityChatTurn(name: name, chatId: chatId, text: text) }
    func ledger(runId: String, after: Int) async throws -> LedgerPage { try await mock.ledger(runId: runId, after: after) }
    func cancel(runId: String) async throws { try await mock.cancel(runId: runId) }
    func occurrences(automationId: String, limit: Int) async throws -> [LastOccurrence] { try await mock.occurrences(automationId: automationId, limit: limit) }
    func markSeen(automationId: String, cursor: String) async throws { try await mock.markSeen(automationId: automationId, cursor: cursor) }
    nonisolated func speech(text: String, scope: SpeechScope) -> AsyncThrowingStream<Data, Error> { AsyncThrowingStream { $0.finish() } }
    func transcribe(wav: Data, sessionId: String) async throws -> String { try await mock.transcribe(wav: wav, sessionId: sessionId) }
}
