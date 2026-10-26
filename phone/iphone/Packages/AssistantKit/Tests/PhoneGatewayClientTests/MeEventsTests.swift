import Foundation
import Testing
@testable import PhoneGatewayClient

/// The person's event stream on the iPhone (backlog 1046/1047): the SSE frames and the page decode,
/// the raised-minus-seen fold (the gateway's exact shapes), and the per-device notification memory.
struct PhoneMeEventsTests {
    private func ev(_ seq: Int, _ type: String, _ data: [String: JSONValue], time: String? = nil) -> UserEvent {
        UserEvent(id: "\(type):\(seq)", type: type, sequence: seq, data: .object(data), time: time)
    }
    private func page(_ events: [UserEvent], more: Bool = false) -> UserEventsPage {
        UserEventsPage(events: events, nextAfter: events.last?.sequence ?? 0, head: events.last?.sequence ?? 0, more: more)
    }
    private func result(_ seq: Int, _ aid: String, _ item: Int) -> UserEvent {
        ev(seq, "attention.raised", ["automation_id": .string(aid), "seq": .number(Double(item)), "kind": .string("notify"),
                                     "record_key": .string("automation:completed:\(aid):\(item)")])
    }
    private func wait(_ seq: Int, run: String, key: String, step: String = "st") -> UserEvent {
        ev(seq, "attention.raised", ["kind": .string("approval"), "wait_kind": .string("tool_approval"), "run_id": .string(run),
                                     "session_id": .string("s"), "wait_key": .string(key), "step_id": .string(step),
                                     "record_key": .string("wait:\(run):\(key):\(step)")])
    }
    private func shown(_ seq: Int, _ record: String, channel: String, device: String, ago: Double) -> UserEvent {
        let f = ISO8601DateFormatter(); f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return ev(seq, "notification.sent", ["channel": .string(channel), "notice": .string("attention:\(record)"),
                                             "record_key": .string(record), "device": .string(device)],
                  time: f.string(from: Date().addingTimeInterval(-ago)))
    }

    @Test func theReportBodyIsTheGatewaysShape() throws {
        let body = try JSONEncoder().encode(NotificationReport(recordKey: "automation:completed:a:1", device: "p1"))
        #expect(try JSONSerialization.jsonObject(with: body) as? [String: String]
                == ["channel": "phone", "outcome": "sent", "record_key": "automation:completed:a:1", "device": "p1"])
    }

    /// A notice is posted under the gateway's push collapse id (sha256("attention:" + record_key)[:32]),
    /// the identifier APNs gives the pushed alert: the catch-up skips what a push already showed.
    @Test func noticesUseThePushCollapseID() {
        var s = AttentionState()
        _ = s.apply(page([]))
        let told = s.apply(page([wait(1, run: "r1", key: "k1"), result(2, "a", 1)]))
        #expect(told.map(\.identifier) == ["c9ece7c314e9a39da7d4407c0aa87900", "0b1ddd6269d7d6bb68c9d69cb95e8db3"])
        #expect(AttentionNotice.news(automationId: "a", seq: 1, failed: false).identifier == "attention-a-1")
    }

    @Test func sseFramesBecomeEvents() {
        var p = UserEventSSEParser()
        let text = ": stream user:default:a\n\nid: 3\nevent: run.started\ndata: {\"id\":\"x\",\"type\":\"run.started\",\"sequence\":3,\"data\":{\"run_id\":\"r\"}}\n\n: keep-alive\n\n"
        let out = Array(text.utf8).compactMap { p.feed(byte: $0) }
        #expect(out.map(\.sequence) == [3] && out[0].type == "run.started" && out[0].string("run_id") == "r")
    }

    @Test func historyTakesStockThenEachNewItemIsToldOnce() {
        var s = AttentionState()
        #expect(s.apply(page([result(1, "a", 1), wait(2, run: "r", key: "k")])).isEmpty)
        #expect(s.needYou == 1 && s.newResults == 1)
        let told = s.apply(page([result(3, "a", 2), wait(4, run: "r2", key: "k2")]))
        #expect(told.map(\.recordKey) == ["automation:completed:a:2", "wait:r2:k2:st"])
        _ = s.apply(page([ev(5, "attention.seen", ["kind": .string("approval"), "run_id": .string("r2"), "wait_key": .string("k2"),
                                                   "step_id": .string("st"), "outcome": .string("approved")]),
                          ev(6, "attention.seen", ["automation_id": .string("a"), "seq": .number(2)])]))
        #expect(s.needYou == 1 && s.newResults == 0)
    }

    @Test func onlyAnotherClientOnTheSameDeviceWithinAMinuteSilences() {
        var s = AttentionState()
        _ = s.apply(page([shown(1, "rk", channel: "tray", device: "mac", ago: 5),
                          shown(2, "rk", channel: "phone", device: "me", ago: 5),
                          shown(3, "old", channel: "code", device: "me", ago: 300),
                          shown(4, "mine", channel: "watch", device: "me", ago: 5)]))
        #expect(!s.notifiedElsewhere("rk", channel: "phone", device: "me"), "the tray is on the Mac, not this phone")
        #expect(s.notifiedElsewhere("rk", channel: "phone", device: "mac"))
        #expect(!s.notifiedElsewhere("rk", channel: "phone", device: "me"), "the phone's own report never silences the phone")
        #expect(s.notifiedElsewhere("rk", channel: "tray", device: "me"), "it counts for another client on that same device")
        #expect(!s.notifiedElsewhere("old", channel: "phone", device: "me"), "five minutes ago: not within the minute")
        #expect(s.notifiedElsewhere("mine", channel: "phone", device: "me"))
        #expect(!s.notifiedElsewhere("mine", channel: "phone", device: ""), "no device id: nothing to compare")
    }
}
