import Foundation
import Testing
@testable import AbstractGatewayClient

/// The person's event stream (`GET /me/events`, backlog 1046/1047): the wire page decodes, and the
/// fold tells each approval/question once (time-sensitive), each automation result once (news), an
/// automation's quiet finish once, and nothing that happened before the watch first looked.
struct MeEventsTests {
    /// The gateway's own page shape (L3 contract: CloudEvents names, integer `sequence`).
    static let wire = """
    {"stream":"user:default:alice","events":[
     {"specversion":"1.0","id":"run.started:r1","type":"run.started","source":"/abstractgateway/runs","subject":"r1",
      "time":"2026-10-25T12:00:00Z","data":{"run_id":"r1","session_id":"s1","origin":null},"sequence":1},
     {"specversion":"1.0","id":"attention.raised:a:1","type":"attention.raised","source":"/abstractgateway/automations/a",
      "time":"2026-10-25T12:00:01Z","data":{"record_key":"automation:completed:a:1","automation_id":"a","run_id":"c","index":3,
      "kind":"notify","seq":1,"channels":["console"]},"sequence":2}],
     "next_after":2,"head":2,"more":false}
    """

    private func ev(_ seq: Int, _ type: String, _ data: [String: JSONValue]) -> UserEvent {
        UserEvent(id: "\(type):\(seq)", type: type, sequence: seq, data: .object(data))
    }
    private func page(_ events: [UserEvent], more: Bool = false) -> UserEventsPage {
        UserEventsPage(events: events, nextAfter: events.last?.sequence ?? 0, head: events.last?.sequence ?? 0, more: more)
    }
    /// The gateway's shapes (L3 item 4b): no prompt (the run is the live fact); seen names the step.
    private func wait(_ seq: Int, run: String, key: String, kind: String = "approval", step: String = "st") -> UserEvent {
        ev(seq, "attention.raised", ["kind": .string(kind), "wait_kind": .string(kind == "approval" ? "tool_approval" : "ask_user"),
                                     "run_id": .string(run), "session_id": .string("s"), "wait_key": .string(key),
                                     "step_id": .string(step), "record_key": .string("wait:\(run):\(key):\(step)"),
                                     "prompt_ref": .string("/api/gateway/runs/\(run)")])
    }
    private func waitSeen(_ seq: Int, run: String, key: String, step: String = "st", outcome: String = "approved") -> UserEvent {
        ev(seq, "attention.seen", ["kind": .string("approval"), "run_id": .string(run), "wait_key": .string(key),
                                   "step_id": .string(step), "outcome": .string(outcome)])
    }
    private func result(_ seq: Int, _ aid: String, _ item: Int, index: Int = 1, kind: String = "notify") -> UserEvent {
        ev(seq, "attention.raised", ["automation_id": .string(aid), "seq": .number(Double(item)), "index": .number(Double(index)),
                                     "kind": .string(kind), "record_key": .string("automation:completed:\(aid):\(item)")])
    }
    private func finished(_ seq: Int, _ aid: String, occurrence: Int) -> UserEvent {
        ev(seq, "run.finished", ["run_id": .string("occ\(occurrence)"), "status": .string("completed"),
                                 "origin": .object(["kind": .string("trigger"),
                                                    "ref": .object(["automation_id": .string(aid), "occurrence_index": .number(Double(occurrence))])])])
    }

    @Test func theWirePageDecodes() throws {
        let p = try JSONDecoder().decode(UserEventsPage.self, from: Data(Self.wire.utf8))
        #expect(p.events.map(\.sequence) == [1, 2])
        #expect(p.events[1].string("automation_id") == "a" && p.events[1].int("seq") == 1)
        #expect(p.nextAfter == 2 && p.head == 2 && !p.more)
    }

    @Test func historyOnlyTakesStock() {
        var s = AttentionState()
        let told = s.apply(page([wait(1, run: "r1", key: "k1"), result(2, "a", 1)]))
        #expect(told.isEmpty)
        #expect(s.caughtUp && s.cursor == 2 && s.needYou == 1 && s.newResults == 1)
    }

    @Test func aPageWithMoreKeepsTakingStock() {
        var s = AttentionState()
        #expect(s.apply(page([result(1, "a", 1)], more: true)).isEmpty && !s.caughtUp)
        #expect(s.apply(page([result(2, "a", 2)])).isEmpty && s.caughtUp)
    }

    @Test func newRaisesAreToldOnceEach() {
        var s = AttentionState()
        _ = s.apply(page([]))
        let told = s.apply(page([wait(1, run: "r1", key: "k1"), wait(2, run: "r2", key: "q", kind: "question"),
                                 result(3, "a", 1, kind: "failure")]))
        #expect(told == [.needsYou(runId: "r1", waitKey: "k1", kind: "approval", sessionId: "s", recordKey: "wait:r1:k1:st"),
                         .needsYou(runId: "r2", waitKey: "q", kind: "question", sessionId: "s", recordKey: "wait:r2:q:st"),
                         .news(automationId: "a", seq: 1, failed: true, recordKey: "automation:completed:a:1")])
        #expect(told.map(\.recordKey) == ["wait:r1:k1:st", "wait:r2:q:st", "automation:completed:a:1"])
        #expect(told.map(\.identifier) == ["wait-r1:k1", "wait-r2:q", "attention-a-1"])
        // The same page read again (a retried refresh) tells nothing.
        #expect(s.apply(page([wait(1, run: "r1", key: "k1"), result(3, "a", 1)])).isEmpty)
        #expect(s.needYou == 2 && s.newResults == 1)
    }

    @Test func seenAndFinishedBringTheCountsDown() {
        var s = AttentionState()
        _ = s.apply(page([wait(1, run: "r1", key: "k1"), wait(2, run: "r2", key: "k2"), result(3, "a", 1), result(4, "a", 2)]))
        _ = s.apply(page([waitSeen(5, run: "r1", key: "k1"),
                          ev(6, "run.finished", ["run_id": .string("r2"), "status": .string("completed")]),
                          ev(7, "attention.seen", ["automation_id": .string("a"), "seq": .number(1)])]))
        #expect(s.needYou == 0 && s.newResults == 1)
        // An item already seen never comes back.
        #expect(s.apply(page([result(8, "a", 1)])).isEmpty)
        _ = s.apply(page([ev(9, "attention.seen", ["automation_id": .string("a"), "seq": .number(2)])]))
        #expect(s.newResults == 0)
    }

    @Test func aQuietFinishIsToldButNotTwiceWithItsResult() {
        var s = AttentionState()
        _ = s.apply(page([]))
        let told = s.apply(page([finished(1, "digest", occurrence: 4), result(2, "news", 1, index: 7), finished(3, "news", occurrence: 7)]))
        #expect(told == [.automationFinished(automationId: "digest", occurrence: 4, status: "completed", runId: "occ4"),
                         .news(automationId: "news", seq: 1, failed: false, recordKey: "automation:completed:news:1")])
    }

    @Test func theSameNodeAskingAgainIsANewWait() {
        var s = AttentionState()
        _ = s.apply(page([]))
        _ = s.apply(page([wait(1, run: "r", key: "k", step: "a"), waitSeen(2, run: "r", key: "k", step: "a")]))
        let told = s.apply(page([wait(3, run: "r", key: "k", step: "b")]))
        #expect(told.count == 1 && s.needYou == 1)
        _ = s.apply(page([waitSeen(4, run: "r", key: "k", step: "a")]))        // an old step's seen: still open
        #expect(s.needYou == 1)
        _ = s.apply(page([waitSeen(5, run: "r", key: "k", step: "b", outcome: "answered")]))
        #expect(s.needYou == 0)
    }

    @Test func theStateSurvivesBeingKept() throws {
        var s = AttentionState()
        _ = s.apply(page([wait(1, run: "r1", key: "k1"), result(2, "a", 1)]))
        let kept = try JSONDecoder().decode(AttentionState.self, from: JSONEncoder().encode(s))
        #expect(kept == s)
    }

    @Test func theReportBodyIsTheGatewaysShape() throws {
        let body = try JSONEncoder().encode(NotificationReport(recordKey: "automation:completed:a:1", device: "w1"))
        let object = try JSONSerialization.jsonObject(with: body) as? [String: String]
        #expect(object == ["channel": "watch", "outcome": "sent", "record_key": "automation:completed:a:1", "device": "w1"])
    }

    @Test func theMockServesPagesAfterACursor() async throws {
        let mock = MockGatewayClient()
        for i in 1...3 { await mock.appendEvent(result(i, "a", i)) }
        let p = try await mock.events(after: 1, limit: 1)
        #expect(p.events.map(\.sequence) == [2] && p.more && p.head == 3)
    }
}
