import Foundation
import Testing
@testable import AssistantKit
import PhoneGatewayClient

@Suite @MainActor struct ActivityStoreTests {
    private func run(_ json: String) throws -> RunSummary {
        try JSONDecoder().decode(RunSummary.self, from: Data(json.utf8))
    }
    private func nestedClient(recordCount: Int = 1) async throws -> ActivityClient {
        let client = ActivityClient()
        let rows = try [
            run(#"{"run_id":"root","status":"waiting","session_id":"root-session","waiting":{"reason":"subworkflow","wait_key":"subworkflow:child"}}"#),
            run(#"{"run_id":"child","parent_run_id":"root","status":"waiting","session_id":"different-child-session","waiting":{"reason":"subworkflow","details":{"sub_run_id":"leaf"}}}"#),
            run(#"{"run_id":"leaf","parent_run_id":"child","status":"waiting","session_id":"different-leaf-session","waiting":{"reason":"user","wait_key":"tool_approval:leaf:act:one","prompt":"Allow read?","details":{"tool_calls":[{"name":"read_file","arguments":{"file_path":"a.txt"}}]}}}"#)
        ]
        let ledger = (0..<recordCount).map { i in LedgerRecord(stepId: "model-\(i)", nodeId: "reason", status: "completed", effect: .object(["type": .string("llm_call")])) }
        await client.configure(rows, records: ["leaf": ledger]); return client
    }
    private func store(_ client: ActivityClient, selection: ConversationTools? = nil) async throws -> AssistantStore {
        let store = AssistantStore(defaults: UserDefaults(suiteName: "activity-store-\(UUID())")!)
        store.connect(nil, client: client)
        if let selection { store.setConversationTools(selection) }
        store.send("Inspect environment")
        for _ in 0..<1000 {
            if store.activeRunID != nil { return store }
            await Task.yield()
        }
        Issue.record("Send did not establish its root ID"); return store
    }
    @Test func nestedChildApprovalSurfacesWithoutMatchingSessionIDs() async throws {
        let client = try await nestedClient()
        let store = try await store(client)
        await store.followActiveRun()
        #expect(store.activeRunID == "root")
        #expect(store.phase == .waiting && store.activityState == .waiting)
        #expect(store.conversationWait?.runId == "leaf")
        #expect(store.activity.modelCalls == 1)
        store.disconnect()
    }
    @Test func externalApprovalClearsConversationWithoutFullRefresh() async throws {
        let client = try await nestedClient()
        let store = try await store(client)
        await store.followActiveRun()
        let wait = try #require(store.conversationWait)
        // Another client answers; do not invoke the store's answer or full refresh paths.
        try await client.answer(wait, with: .approve)
        await store.refreshPendingApprovals()
        #expect(store.conversationWait == nil)
        #expect(!store.waits.contains { $0.id == wait.id })
        #expect(store.activityState != .waiting)
        store.disconnect()
    }

    @Test func approvalAnswersChildAndOnlyRootReplyCompletesConversation() async throws {
        let client = try await nestedClient()
        let store = try await store(client)
        await store.followActiveRun()
        let wait = try #require(store.conversationWait)
        #expect(await store.answer(wait, .approve))
        #expect(await client.answered == ["leaf"])
        #expect(store.activeRunID == nil && store.activityState == .completed)
        #expect(store.messages.filter { $0.role == .assistant }.map(\.text) == ["The root reply"])
        #expect(store.activity.modelCalls == 1)
        #expect(await client.ledgerReads.contains { $0.0 == "leaf" && $0.1 == 1 })
        store.disconnect()
    }
    @Test func parallelChildWaitIsHydratedFromSummaryBeforeDisplay() async throws {
        let client = try await nestedClient()
        let sibling = try run(#"{"run_id":"parallel","parent_run_id":"root","status":"waiting","waiting":{"reason":"user","wait_key":"ask_user:parallel","prompt":"Pick a destination"}}"#)
        await client.addSiblingWithSummaryOnlyListing(sibling)
        let store = try await store(client)
        await store.followActiveRun()
        #expect(store.waits.contains { $0.runId == "parallel" && $0.prompt == "Pick a destination" })
        store.disconnect()
    }
    @Test func terminalDrainIncludesPreviouslyKnownChildrenOnOlderGateway() async throws {
        let client = try await nestedClient()
        let store = try await store(client)
        await store.followActiveRun()
        let wait = try #require(store.conversationWait)
        await client.disableChildListingAndAppendFinalRecord()
        #expect(await store.answer(wait, .approve))
        #expect(store.activity.modelCalls == 2)
        store.disconnect()
    }
    @Test func approveAllKeepsModesAndUsesOrdinaryChildApproval() async throws {
        let client = try await nestedClient()
        let store = try await store(client, selection: .init(modes: ["read_file": .approve, "write_file": .off, "disabled_tool": .approve]))
        await store.followActiveRun()
        let wait = try #require(store.conversationWait)
        #expect(await store.approveAll(wait))
        #expect(await client.answered == ["leaf"])
        #expect(await client.answers == [.approve])
        #expect(store.conversationTools?.modes["read_file"] == .approve)
        #expect(store.sessionApprovalGrants == ["read_file"])
        #expect(store.conversationTools?.modes["write_file"] != .auto)
        #expect(store.conversationTools?.modes["disabled_tool"] != .auto)
        #expect(store.conversationTools == .init(modes: ["read_file": .approve, "write_file": .off, "disabled_tool": .approve]))
        store.disconnect()
    }
    @Test func revokingSessionApprovalsDuringARunPreservesAutoAndOffModes() async throws {
        let client = try await nestedClient()
        await client.keepRunningAfterAnswer()
        let original = ConversationTools(modes: ["read_file": .approve, "write_file": .auto, "disabled_tool": .off])
        let store = try await store(client, selection: original)
        await store.followActiveRun()
        #expect(await store.approveAll(try #require(store.conversationWait)))
        #expect(store.conversationTools == original && store.sessionApprovalGrants == ["read_file"])
        await client.nextApproval(names: ["read_file", "write_file"], key: "mixed")
        await store.followActiveRun()
        #expect(await client.answered.count == 2)
        store.revokeSessionApprovals()
        #expect(store.sessionApprovalGrants.isEmpty && store.conversationTools == original)
        await client.nextApproval(names: ["read_file"], key: "after-revoke")
        await store.followActiveRun()
        #expect(await client.answered.count == 2)
        #expect(store.conversationWait?.details?.first?.name == "read_file")
        store.disconnect()
    }
    @Test func approveAllWithInheritedDefaultsDoesNotCreateAutoOverrides() async throws {
        let client = try await nestedClient(), store = try await store(client)
        store.setAppTools(.init(modes: ["read_file": .approve, "write_file": .auto]))
        let original = store.appTools
        await store.followActiveRun()
        #expect(await store.approveAll(try #require(store.conversationWait)))
        #expect(store.conversationTools == nil && store.appTools == original)
        #expect(store.sessionApprovalGrants == ["read_file"])
        store.revokeSessionApprovals()
        #expect(store.conversationTools == nil && store.appTools == original)
        store.disconnect()
    }
    @Test func revokedGrantCannotApproveAfterInventoryAwait() async throws {
        let client = try await nestedClient()
        await client.keepRunningAfterAnswer()
        let store = try await store(client)
        await store.followActiveRun()
        #expect(await store.approveAll(try #require(store.conversationWait)))
        await client.nextApproval(names: ["read_file"], key: "race")
        await client.gateInventory()
        let follow = Task { await store.followActiveRun() }
        for _ in 0..<1000 { if await client.inventoryWaiting { break }; await Task.yield() }
        #expect(await client.inventoryWaiting)
        store.revokeSessionApprovals()
        await client.releaseInventory(); await follow.value
        #expect(await client.answered.count == 1)
        #expect(store.conversationWait != nil && store.sessionApprovalGrants.isEmpty)
        store.disconnect()
    }
    @Test func failedApprovalDoesNotCreateAGrant() async throws {
        let client = try await nestedClient(), store = try await store(client)
        await store.followActiveRun(); await client.failAnswers()
        #expect(!(await store.approveAll(try #require(store.conversationWait))))
        #expect(store.sessionApprovalGrants.isEmpty && store.conversationTools == nil)
        store.disconnect()
    }
    @Test func grantsSurviveReopenButAreIsolatedFromOtherSessions() async throws {
        let client = try await nestedClient()
        await client.keepRunningAfterAnswer()
        let defaults = UserDefaults(suiteName: "approval-persistence-\(UUID())")!
        let store = AssistantStore(defaults: defaults); store.connect(nil, client: client)
        store.send("Inspect environment")
        for _ in 0..<1000 { if store.activeRunID != nil { break }; await Task.yield() }
        let session = store.sessionID
        await client.setRootSession(session)
        await store.followActiveRun()
        #expect(await store.approveAll(try #require(store.conversationWait)))
        store.disconnect()
        let reopened = AssistantStore(defaults: defaults); reopened.connect(nil, client: client)
        #expect(reopened.sessionApprovalGrants.isEmpty)
        await reopened.openSession(try #require(SessionSummary.group(await client.recentRuns(limit: 10)).first))
        #expect(reopened.sessionID == session && reopened.sessionApprovalGrants.contains("read_file"))
        reopened.revokeSessionApprovals(); reopened.disconnect()
        let again = AssistantStore(defaults: defaults); again.connect(nil, client: client)
        await again.openSession(try #require(SessionSummary.group(await client.recentRuns(limit: 10)).first))
        #expect(again.sessionApprovalGrants.isEmpty)
        again.disconnect()
    }
    @Test func legacyReviewNeverGuessesWhichAutoModesWereIntentional() async throws {
        let client = try await nestedClient(), defaults = UserDefaults(suiteName: "legacy-trust-\(UUID())")!
        let store = AssistantStore(defaults: defaults); store.connect(nil, client: client)
        let key = "phone.tools.demo.assistant." + store.sessionID
        let original = ConversationTools(modes: ["read_file": .auto, "write_file": .auto, "disabled_tool": .off])
        defaults.set(try JSONEncoder().encode(original), forKey: key)
        defaults.set(["read_file", "write_file"], forKey: key + ".grant")
        #expect(store.sessionApprovalGrants.isEmpty && store.legacySessionApprovalNames.count == 2)
        #expect(store.conversationTools == original)
        store.reviewLegacySessionApprovals(askingAgain: ["read_file"])
        #expect(store.conversationTools?.modes["read_file"] == .approve)
        #expect(store.conversationTools?.modes["write_file"] == .auto)
        #expect(store.conversationTools?.modes["disabled_tool"] == .off)
        #expect(store.legacySessionApprovalNames.isEmpty)
        store.disconnect()
    }
    @Test func approveAllCannotAuthorizeAnUnrelatedRun() async throws {
        let client = try await nestedClient()
        let store = try await store(client)
        await store.followActiveRun()
        let stranger = try run(#"{"run_id":"stranger","status":"waiting","waiting":{"reason":"user","wait_key":"tool_approval:stranger","details":{"tool_calls":[{"name":"read_file","arguments":{}}]}}}"#)
        let wait = try #require(stranger.personWait)
        #expect(!(await store.approveAll(wait)))
        #expect(await client.answered.isEmpty)
        #expect(store.conversationTools == nil)
        store.disconnect()
    }
    @Test func grantedNamesAutoApproveLaterChildWaitButOffAndUnknownToolsStillAsk() async throws {
        let client = try await nestedClient()
        await client.keepRunningAfterAnswer()
        let store = try await store(client, selection: .init(modes: ["read_file": .approve, "write_file": .off]))
        await store.followActiveRun()
        let wait = try #require(store.conversationWait)
        #expect(await store.approveAll(wait))
        await client.nextApproval(names: ["read_file"], key: "second")
        await store.followActiveRun()
        #expect(await client.answered.count == 2)
        for name in ["write_file", "unknown_tool", "disabled_tool"] {
            await client.nextApproval(names: [name], key: name)
            await store.followActiveRun()
            #expect(await client.answered.count == 2)
            #expect(store.conversationWait?.details?.first?.name == name)
        }
        store.disconnect()
    }
    @Test func conversationTrustNeverAutoAnswersQuestionsOrNewlyDisabledTools() async throws {
        let client = try await nestedClient()
        await client.keepRunningAfterAnswer()
        let store = try await store(client)
        await store.followActiveRun()
        #expect(await store.approveAll(try #require(store.conversationWait)))
        await client.nextQuestion()
        await store.followActiveRun()
        #expect(await client.answered.count == 1)
        #expect(store.conversationWait?.kind == .askUser)
        await client.disableReadTool()
        await client.nextApproval(names: ["read_file"], key: "disabled-since-grant")
        await store.followActiveRun()
        #expect(await client.answered.count == 1 && store.conversationWait != nil)
        store.disconnect()
    }
    @Test func editingToolSelectionRevokesPriorConversationTrust() async throws {
        let client = try await nestedClient()
        let store = try await store(client)
        await store.followActiveRun()
        #expect(await store.approveAll(try #require(store.conversationWait)))
        #expect(store.canSend)
        store.setConversationTools(.init(modes: ["read_file": .approve]))
        await client.nextApproval(names: ["read_file"], key: "after-edit")
        store.send("Another request")
        for _ in 0..<1000 { if store.activeRunID != nil { break }; await Task.yield() }
        await store.followActiveRun()
        #expect(await client.answered.count == 1)
        #expect(store.conversationWait?.runId == "leaf")
        store.disconnect()
    }
    @Test func trustedWaitKeyCanRecurAfterThePriorOccurrenceDisappears() async throws {
        let client = try await nestedClient()
        await client.keepRunningAfterAnswer()
        let store = try await store(client)
        await store.followActiveRun()
        #expect(await store.approveAll(try #require(store.conversationWait)))
        await client.nextApproval(names: ["read_file"], key: "reused")
        await store.followActiveRun()
        #expect(await client.answered.count == 2)
        await store.followActiveRun() // Observe running: the previous occurrence is gone.
        await client.nextApproval(names: ["read_file"], key: "reused")
        await store.followActiveRun()
        #expect(await client.answered.count == 3)
        store.disconnect()
    }
    @Test func approveAllCannotGrantARequestedToolDisabledSinceThePrompt() async throws {
        let client = try await nestedClient()
        let store = try await store(client)
        await store.followActiveRun()
        let wait = try #require(store.conversationWait)
        await client.disableReadTool()
        #expect(!(await store.approveAll(wait)))
        #expect(await client.answered.isEmpty && store.conversationTools == nil)
        store.disconnect()
    }
    @Test func reopeningFailedHistoryRestoresItsFailureAndActivity() async throws {
        let client = ActivityClient()
        let failed = try run(#"{"run_id":"root","session_id":"saved-session","status":"failed","error":"Gateway provider disconnected"}"#)
        await client.configure([failed], records: ["root": [.init(stepId: "failed-step", nodeId: "reason", status: "failed", effect: .object(["type": .string("llm_call")]), error: "Gateway provider disconnected")]])
        let store = AssistantStore(defaults: UserDefaults(suiteName: "activity-reopen-\(UUID())")!)
        store.connect(nil, client: client)
        await store.openSession(try #require(SessionSummary.group([failed]).first))
        #expect(store.activityState == .failed)
        #expect(store.activityFailure == "Gateway provider disconnected")
        #expect(store.activity.items.contains { $0.kind == .failure && $0.detail == "Gateway provider disconnected" })
        #expect(store.activeRunID == nil && store.completedReply == nil)
        store.disconnect()
    }
    @Test func reopeningCompletedHistoryDoesNotAnnounceOrReadItsReplyAgain() async throws {
        let client = ActivityClient()
        let completed = try run(#"{"run_id":"root","session_id":"saved-session","status":"completed","output":{"response":"An earlier reply"}}"#)
        await client.configure([completed], records: ["root": [.init(stepId: "done-step", nodeId: "reason", status: "completed", effect: .object(["type": .string("llm_call")]))]])
        let store = AssistantStore(defaults: UserDefaults(suiteName: "activity-reopen-\(UUID())")!)
        store.connect(nil, client: client)
        await store.openSession(try #require(SessionSummary.group([completed]).first))
        #expect(store.messages.filter { $0.role == .assistant }.map(\.text) == ["An earlier reply"])
        #expect(store.activityState == .completed && store.activity.modelCalls == 1)
        #expect(store.completedReply == nil && store.activeRunID == nil)
        await store.refreshActivity()
        #expect(store.completedReply == nil && store.activity.modelCalls == 1)
        store.disconnect()
    }
    @Test func terminalFailureRemainsVisibleAfterRefresh() async throws {
        let client = try await nestedClient()
        let store = try await store(client)
        await store.followActiveRun(); await client.failRoot(); await store.followActiveRun()
        #expect(store.activityState == .failed && store.activityFailure == "Provider disconnected")
        await store.refresh()
        #expect(store.activityState == .failed && store.activityFailure == "Provider disconnected")
        #expect(store.activityRootID == "root")
        store.disconnect()
    }
    @Test func childLedgerPaginationDrainsBeyondOnePageWithoutDuplicateCounts() async throws {
        let client = try await nestedClient(recordCount: 405)
        let store = try await store(client)
        await store.followActiveRun(); await store.followActiveRun()
        #expect(store.activity.modelCalls == 405)
        #expect(store.activity.items.count == 250 && store.activity.wasTrimmed)
        let cursors = await client.ledgerReads.filter { $0.0 == "leaf" }.map { $0.1 }
        #expect(cursors.contains(200) && cursors.contains(400))
        store.disconnect()
    }
    @Test func delayedOldAccountSnapshotCannotRepopulateActivity() async throws {
        let client = try await nestedClient()
        let store = try await store(client)
        await client.suspend()
        let pending = Task { await store.followActiveRun() }
        for _ in 0..<1000 { if await client.waiting { break }; await Task.yield() }
        #expect(await client.waiting)
        store.disconnect(); store.connect(nil, client: MockGatewayClient())
        await client.release(); await pending.value
        #expect(store.activityRootID == nil && store.activity.items.isEmpty)
        #expect(store.conversationWait == nil && store.activeRunID == nil)
        store.disconnect()
    }
    @Test func liveCompletionWinsOverAnOlderPendingHistoryReplay() async throws {
        let client = try await nestedClient(), store = AssistantStore()
        store.connect(nil, client: client)
        await client.replaceRecords("root", [.init(stepId: "old", nodeId: "reason", status: "completed", effect: .object(["type": .string("llm_call")]))])
        await client.gateNextLedger(1)
        let old = Task { await store.loadAnswerActivity(runID: "root") }
        await waitForGate(1, client: client)
        await client.replaceRecords("root", [])
        store.send("Inspect environment")
        for _ in 0..<2000 { if store.activeRunID != nil { break }; await Task.yield() }
        await store.followActiveRun()
        let wait = try #require(store.conversationWait)
        #expect(await store.answer(wait, .approve))
        #expect(store.answerActivities["root"]?.activity.modelCalls == 1)
        await client.releaseLedger(1); await old.value
        // Old root+child replay would count two calls and replace live completion.
        #expect(store.answerActivities["root"]?.activity.modelCalls == 1)
        store.disconnect()
    }
    private func historyClient() async -> ActivityClient {
        let client = ActivityClient()
        await client.configure([.init(runId: "history", workflowId: "assistant", status: "completed")], records: ["history": [.init(stepId: "one", nodeId: "reason", status: "completed", effect: .object(["type": .string("llm_call")]))]])
        return client
    }
    private func waitForGate(_ n: Int, client: ActivityClient) async {
        for _ in 0..<2000 { if await client.hasGate(n) { return }; await Task.yield() }
        Issue.record("History request did not reach controlled gate")
    }
    @Test func cancelledOverlappingHistoryRowsStillShareAndPublishOneLoad() async {
        let client = await historyClient(), store = AssistantStore()
        store.connect(nil, client: client)
        await client.gateNextLedger(1)
        let first = Task { await store.loadAnswerActivity(runID: "history") }
        await waitForGate(1, client: client)
        let second = Task { await store.loadAnswerActivity(runID: "history") }
        first.cancel(); second.cancel()
        await client.releaseLedger(1)
        await first.value; await second.value
        #expect(store.answerActivities["history"]?.activity.modelCalls == 1)
        #expect(await client.ledgerReads.count == 1)
        store.disconnect()
    }
    @Test func oldUncooperativeHistoryCannotReplaceOrClearReopenedSessionLoad() async {
        let client = await historyClient(), store = AssistantStore()
        store.connect(nil, client: client)
        await client.gateNextLedger(1)
        let old = Task { await store.loadAnswerActivity(runID: "history") }
        await waitForGate(1, client: client)
        store.disconnect(); store.connect(nil, client: client)
        await client.replaceRecords("history", [.init(stepId: "new", nodeId: "reason", status: "completed", effect: .object(["type": .string("llm_call")])), .init(stepId: "new2", nodeId: "reason", status: "completed", effect: .object(["type": .string("llm_call")]))])
        await client.gateNextLedger(2)
        let new = Task { await store.loadAnswerActivity(runID: "history") }
        await waitForGate(2, client: client)
        await client.releaseLedger(1); await old.value
        #expect(store.answerActivities["history"] == nil)
        let overlapping = Task { await store.loadAnswerActivity(runID: "history") }
        await Task.yield()
        await client.releaseLedger(2); await new.value; await overlapping.value
        #expect(await client.ledgerReads.count == 2)
        #expect(store.answerActivities["history"]?.activity.modelCalls == 2)
        store.disconnect()
    }
    @Test func incompleteHistoryHasAnExplicitRetryWithoutGlobalChatError() async {
        let client = await historyClient(), store = AssistantStore()
        store.connect(nil, client: client)
        await client.failNextLedger(.http(status: 503, body: ""))
        await store.loadAnswerActivity(runID: "history")
        #expect(store.answerActivities["history"]?.issues.isEmpty == false)
        #expect(store.error == nil)
        await store.loadAnswerActivity(runID: "history")
        #expect(await client.ledgerReads.count == 1)
        await store.loadAnswerActivity(runID: "history", retry: true)
        #expect(store.answerActivities["history"]?.issues.isEmpty == true)
        #expect(store.answerActivities["history"]?.activity.modelCalls == 1)
        store.disconnect()
    }
    @Test func staleHistoryAuthenticationFailureCannotDisconnectNewConnection() async {
        let client = await historyClient(), store = AssistantStore()
        store.connect(nil, client: client)
        await client.failNextLedger(.unauthorized); await client.gateNextLedger(1)
        let old = Task { await store.loadAnswerActivity(runID: "history") }
        await waitForGate(1, client: client)
        store.disconnect(); store.connect(nil, client: MockGatewayClient())
        await client.releaseLedger(1); await old.value
        #expect(store.client != nil && store.error == nil && store.answerActivities.isEmpty)
        store.disconnect()
    }

}

private actor ActivityClient: GatewayClient {
    nonisolated let isMock = true
    var waiting = false
    var continuation: CheckedContinuation<Void, Never>?
    let mock = MockGatewayClient()
    var states: [String: RunSummary] = [:]
    var records: [String: [LedgerRecord]] = [:]
    var ledgerReads: [(String, Int)] = []
    private var pendingLedgerGates: [Int] = []
    private var ledgerGates: [Int: CheckedContinuation<Void, Never>] = [:]
    private var ledgerError: GatewayError?
    func gateNextLedger(_ id: Int) { pendingLedgerGates.append(id) }
    func hasGate(_ id: Int) -> Bool { ledgerGates[id] != nil }
    func releaseLedger(_ id: Int) { ledgerGates.removeValue(forKey: id)?.resume() }
    func failNextLedger(_ error: GatewayError) { ledgerError = error }
    func replaceRecords(_ id: String, _ rows: [LedgerRecord]) { records[id] = rows }

    var answered: [String] = []
    var answers: [WaitAnswer] = []
    var finishOnAnswer = true
    var originalStates: [String: RunSummary] = [:]
    var inventory = [ToolInfo(name: "read_file", riskTier: "observe", riskRank: 1),
                     ToolInfo(name: "write_file", riskTier: "act", riskRank: 2),
                     ToolInfo(name: "disabled_tool", riskTier: "act", riskRank: 2, enabled: false)]
    var inventoryWaiting = false
    var inventoryGate = false
    var inventoryContinuation: CheckedContinuation<Void, Never>?
    var answersFail = false
    func failAnswers() { answersFail = true }
    func setRootSession(_ id: String) { states["root"]?.sessionId = id; originalStates["root"]?.sessionId = id }
    func gateInventory() { inventoryGate = true }
    func releaseInventory() { inventoryWaiting = false; inventoryContinuation?.resume(); inventoryContinuation = nil }
    func keepRunningAfterAnswer() { finishOnAnswer = false }
    func disableReadTool() { inventory[0].enabled = false }
    func nextApproval(names: [String], key: String) {
        states = originalStates
        states["leaf"]?.waiting?.waitKey = "tool_approval:leaf:" + key
        states["leaf"]?.waiting?.details = .object(["tool_calls": .array(names.map { .object(["name": .string($0), "arguments": .object([:])]) })])
    }
    func nextQuestion() {
        states = originalStates
        states["leaf"]?.waiting?.waitKey = "ask_user:leaf:question"
        states["leaf"]?.waiting?.details = nil
        states["leaf"]?.waiting?.prompt = "Which folder?"
    }

    var suspendNext = false
    var listingEnabled = true
    var summariesOnly = false
    func addSiblingWithSummaryOnlyListing(_ sibling: RunSummary) { states[sibling.runId] = sibling; summariesOnly = true }
    func disableChildListingAndAppendFinalRecord() {
        listingEnabled = false
        records["leaf", default: []].append(.init(stepId: "final-model", nodeId: "reason", status: "completed", effect: .object(["type": .string("llm_call")])))
    }
    func configure(_ rows: [RunSummary], records: [String: [LedgerRecord]] = [:]) {
        states = Dictionary(uniqueKeysWithValues: rows.map { ($0.runId, $0) }); originalStates = states; self.records = records
    }
    func failRoot() { states["root"]?.status = "failed"; states["root"]?.waiting = nil; states["root"]?.error = "Provider disconnected" }
    func suspend() { suspendNext = true }

    func release() { continuation?.resume(); continuation = nil }
    func me() async throws -> Principal { try await mock.me() }
    func health() async throws -> Bool { true }
    func waits() async throws -> [Wait] { [] }
    func recentRuns(limit: Int) async throws -> [RunSummary] { states.values.filter { $0.parentRunId == nil } }
    func prompt(ofRun id: String) async throws -> String? { try await mock.prompt(ofRun: id) }
    func turns(ofSession id: String) async throws -> [RunSummary] { states.values.filter { $0.parentRunId == nil && $0.sessionId == id } }
    func run(id: String) async throws -> RunSummary {
        let snapshot = states[id]!
        if suspendNext { suspendNext = false; await withCheckedContinuation { continuation = $0; waiting = true } }
        return snapshot
    }
    func childRuns(ofRunID id: String) async throws -> [RunSummary] {
        guard listingEnabled else { throw GatewayError.http(status: 404, body: "") }
        return states.values.filter { $0.parentRunId == id }.map { row in
            var row = row
            if summariesOnly { row.waiting?.waitKey = nil; row.waiting?.details = nil; row.waiting?.prompt = nil }
            return row
        }
    }
    nonisolated func ledgerEvents(runID: String, after: Int) -> AsyncThrowingStream<LedgerStreamEvent, Error> {
        // The store's bounded replay path is deterministic; no background polling races.
        AsyncThrowingStream { $0.finish() }
    }
    func startRun(prompt: String, sessionId: String?, toolPolicy: RunToolPolicy?) async throws -> String { "root" }
    func startRun(prompt: String, sessionId: String?, attachments: [JSONValue], tools: ConversationTools?) async throws -> String { "root" }
    func tools() async throws -> [ToolInfo] {
        if inventoryGate {
            inventoryGate = false; inventoryWaiting = true
            await withCheckedContinuation { inventoryContinuation = $0 }
        }
        return inventory
    }
    func answer(_ wait: Wait, with answer: WaitAnswer) async throws {
        if answersFail { throw GatewayError.http(status: 500, body: "Approval failed") }
        answered.append(wait.runId); answers.append(answer)
        if !finishOnAnswer { states["leaf"]?.status = "running"; states["leaf"]?.waiting = nil; return }
        states["leaf"]?.status = "completed"; states["leaf"]?.waiting = nil
        states["leaf"]?.output = .string("CHILD OUTPUT MUST NOT BE FINAL")
        states["child"]?.status = "completed"; states["child"]?.waiting = nil
        states["root"]?.status = "completed"; states["root"]?.waiting = nil
        states["root"]?.output = .object(["response": .string("The root reply")])
    }
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
    func ledger(runId: String, after: Int) async throws -> LedgerPage {
        ledgerReads.append((runId, after))
        var page = try JSONDecoder().decode(LedgerPage.self, from: Data(#"{"items":[],"next_after":0}"#.utf8))
        page.items = Array((records[runId] ?? []).dropFirst(after).prefix(200))
        page.nextAfter = after + page.items.count
        let error = ledgerError; ledgerError = nil
        if !pendingLedgerGates.isEmpty {
            let id = pendingLedgerGates.removeFirst()
            // Deliberately ignore cancellation: old transports may finish late.
            await withCheckedContinuation { ledgerGates[id] = $0 }
        }
        if let error { throw error }
        return page
    }
    func cancel(runId: String) async throws { try await mock.cancel(runId: runId) }
    func occurrences(automationId: String, limit: Int) async throws -> [LastOccurrence] { try await mock.occurrences(automationId: automationId, limit: limit) }
    func markSeen(automationId: String, cursor: String) async throws { try await mock.markSeen(automationId: automationId, cursor: cursor) }
    nonisolated func speech(text: String, scope: SpeechScope) -> AsyncThrowingStream<Data, Error> { AsyncThrowingStream { $0.finish() } }
    func transcribe(wav: Data, sessionId: String) async throws -> String { try await mock.transcribe(wav: wav, sessionId: sessionId) }
}
