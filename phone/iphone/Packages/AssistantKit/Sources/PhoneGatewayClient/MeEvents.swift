import CryptoKit
import Foundation

// The person's own event stream on the gateway (framework backlog 1046/1047):
// `GET /api/gateway/me/events?after=<seq>&limit=<n>` → `{stream, events[], next_after, head, more}`, and
// `GET /api/gateway/me/events/stream` (SSE: `id: <sequence>`, `event: <type>`, `data: <JSON>`), resumed
// with `Last-Event-ID`. Events use the CloudEvents 1.0 names; `sequence` is the gapless cursor.
// The iPhone catches up at launch and on foreground, and follows the SSE tail while in front.
// (Same fold as the watch's AbstractGatewayClient, plus the per-device notification memory.)

/// One event of the stream.
public struct UserEvent: Codable, Hashable, Sendable {
    public var id: String
    public var type: String
    public var source: String?
    public var subject: String?
    public var time: String?
    public var sequence: Int
    public var data: JSONValue?

    public init(id: String, type: String, sequence: Int, data: JSONValue? = nil, source: String? = nil, subject: String? = nil, time: String? = nil) {
        self.id = id; self.type = type; self.sequence = sequence; self.data = data
        self.source = source; self.subject = subject; self.time = time
    }

    /// A string field of `data`.
    public func string(_ key: String) -> String? { data?[key]?.stringValue }
    /// An integer field of `data` (JSON numbers decode as Double).
    public func int(_ key: String) -> Int? {
        if case .number(let n)? = data?[key] { return Int(n) }
        return nil
    }
}

/// One page of `GET /me/events`.
public struct UserEventsPage: Codable, Hashable, Sendable {
    public var stream: String?
    public var events: [UserEvent]
    public var nextAfter: Int
    public var head: Int
    public var more: Bool

    public init(stream: String? = nil, events: [UserEvent], nextAfter: Int, head: Int, more: Bool) {
        self.stream = stream; self.events = events; self.nextAfter = nextAfter; self.head = head; self.more = more
    }
    enum CodingKeys: String, CodingKey { case stream, events, nextAfter = "next_after", head, more }
}

/// What the watch should tell the person about the events it just read.
public enum AttentionNotice: Hashable, Sendable {
    /// A run stopped for the person: an approval or a question (time-sensitive).
    case needsYou(runId: String, waitKey: String, kind: String, sessionId: String?, recordKey: String? = nil)
    /// An automation raised a result (or failed): news (passive).
    case news(automationId: String, seq: Int, failed: Bool, recordKey: String? = nil)
    /// An automation's run finished without raising anything ("Morning digest finished").
    case automationFinished(automationId: String, occurrence: Int, status: String, runId: String?)

    /// The attention record the notice is about (reported back once shown), nil for a quiet finish.
    public var recordKey: String? {
        switch self {
        case .needsYou(_, _, _, _, let r), .news(_, _, _, let r): r
        case .automationFinished: nil
        }
    }

    /// The notification's identifier: one notification per thing, whatever reads it again. An
    /// attention item's is the gateway's push collapse id (`collapseID(record_key)`), the identifier
    /// APNs gives the pushed alert (backlog 1049), so the catch-up never posts it a second time.
    public var identifier: String {
        switch self {
        case .needsYou(let run, let key, _, _, let record): record.map(Self.collapseID) ?? "wait-\(run):\(key)"
        case .news(let a, let seq, _, let record): record.map(Self.collapseID) ?? "attention-\(a)-\(seq)"
        case .automationFinished(let a, let occ, _, _): "automation-\(a)-\(occ)"
        }
    }

    /// `sha256("attention:" + record_key)` cut to 32 hex characters: abstractgateway's
    /// `push/dispatcher.py` `collapse_id`, sent to APNs as `apns-collapse-id`.
    public static func collapseID(_ recordKey: String) -> String {
        String(SHA256.hash(data: Data(("attention:" + recordKey).utf8)).map { String(format: "%02x", $0) }.joined().prefix(32))
    }
}

/// Raised minus seen, folded from the stream and kept between refreshes (Codable, so the background
/// check and the app share it). The first read only takes stock: what happened before the watch
/// first looked never notifies.
public struct AttentionState: Codable, Hashable, Sendable {
    public struct OpenWait: Codable, Hashable, Sendable {
        public var runId: String
        public var waitKey: String
        public var kind: String
        public var sessionId: String?
        public var recordKey: String?
        /// The ledger step that asked: the same node asking again is a new wait.
        public var stepId: String?
    }

    /// The last sequence read.
    public var cursor = 0
    /// False until the first read reached the head (nothing notifies before).
    public var caughtUp = false
    public var waits: [OpenWait] = []
    /// Per automation: the raised item seqs above the latest seen seq, and that seq.
    public var raised: [String: [Int]] = [:]
    public var seen: [String: Int] = [:]
    /// Record keys already seen (a seen read before its raise keeps it closed).
    public var resolved: [String] = []
    /// `notification.sent` by client channels: record key -> [(channel, device, epoch s)].
    public var shown: [String: [ShownNotice]] = [:]

    public struct ShownNotice: Codable, Hashable, Sendable {
        public var channel: String
        public var device: String?
        public var at: Double?
    }

    /// The client channels whose `notification.sent` can silence another client on the same device.
    public static let clientChannels: Set<String> = ["tray", "assistant", "code", "watch", "phone"]

    /// The gateway's rule (`events_stream.already_notified`): another client channel on the SAME device
    /// showed `recordKey` less than `window` seconds ago.
    public func notifiedElsewhere(_ recordKey: String, channel: String, device: String, now: Date = Date(), window: Double = 60) -> Bool {
        guard !device.isEmpty else { return false }
        let clock = now.timeIntervalSince1970
        return (shown[recordKey] ?? []).contains {
            $0.channel != channel && Self.clientChannels.contains($0.channel) && $0.device == device
                && $0.at.map { clock - $0 >= 0 && clock - $0 <= window } == true
        }
    }

    public init() {}

    /// Approvals and questions waiting (the face's "needs you").
    public var needYou: Int { waits.count }
    /// Results not seen yet (the face's "news").
    public var newResults: Int { raised.reduce(0) { n, kv in n + kv.value.filter { $0 > (seen[kv.key] ?? 0) }.count } }

    /// Folds one page; returns what to tell (nothing while taking stock, nothing already told).
    public mutating func apply(_ page: UserEventsPage) -> [AttentionNotice] {
        let notify = caughtUp
        var out: [AttentionNotice] = []
        var raisedOccurrences = Set<String>()
        for e in page.events where e.sequence > cursor {
            cursor = e.sequence
            switch e.type {
            case "attention.raised":
                let kind = e.string("kind") ?? ""
                if let waitKey = e.string("wait_key"), let runId = e.string("run_id") {
                    let record = e.string("record_key")
                    let step = e.string("step_id")
                    if let record, resolved.contains(record) { continue }
                    if let step, resolved.contains("step:\(runId):\(waitKey):\(step)") { continue }
                    guard !waits.contains(where: { $0.runId == runId && $0.waitKey == waitKey && $0.stepId == step }) else { continue }
                    waits.append(OpenWait(runId: runId, waitKey: waitKey, kind: kind.isEmpty ? "approval" : kind,
                                          sessionId: e.string("session_id"), recordKey: record, stepId: step))
                    if notify { out.append(.needsYou(runId: runId, waitKey: waitKey, kind: kind, sessionId: e.string("session_id"), recordKey: record)) }
                } else if let aid = e.string("automation_id"), let seq = e.int("seq"), seq > 0 {
                    if let index = e.int("index") { raisedOccurrences.insert("\(aid)#\(index)") }
                    guard seq > (seen[aid] ?? 0), !(raised[aid] ?? []).contains(seq) else { continue }
                    raised[aid, default: []].append(seq)
                    if notify { out.append(.news(automationId: aid, seq: seq, failed: kind == "failure", recordKey: e.string("record_key"))) }
                }
            case "attention.seen":
                if let record = e.string("record_key") {
                    resolved = Array((resolved + [record]).suffix(200))
                    waits.removeAll { $0.recordKey == record }
                }
                if let run = e.string("run_id"), let key = e.string("wait_key") {
                    // The gateway's seen names the step (`{kind, run_id, wait_key, step_id, outcome}`).
                    let step = e.string("step_id")
                    if let step { resolved = Array((resolved + ["step:\(run):\(key):\(step)"]).suffix(200)) }
                    waits.removeAll { $0.runId == run && $0.waitKey == key && (step == nil || $0.stepId == nil || $0.stepId == step) }
                }
                if let aid = e.string("automation_id") {
                    let s = max(seen[aid] ?? 0, e.int("seq") ?? 0)
                    seen[aid] = s
                    raised[aid] = (raised[aid] ?? []).filter { $0 > s }
                    if raised[aid]?.isEmpty == true { raised[aid] = nil }
                }
            case "notification.sent":
                guard let channel = e.string("channel"), Self.clientChannels.contains(channel) else { continue }
                let record = e.string("record_key") ?? e.string("notice").flatMap { $0.hasPrefix("attention:") ? String($0.dropFirst(10)) : nil }
                guard let record else { continue }
                let at = e.time.flatMap { ISO8601DateFormatter.events.date(from: $0) ?? ISO8601DateFormatter.eventsPlain.date(from: $0) }?.timeIntervalSince1970
                shown[record, default: []].append(ShownNotice(channel: channel, device: e.string("device"), at: at))
                if shown.count > 200, let oldest = shown.keys.sorted().first { shown[oldest] = nil }
            case "run.finished":
                if let run = e.string("run_id") { waits.removeAll { $0.runId == run } }
                guard notify, case .object(let origin)? = e.data?["origin"], origin["kind"]?.stringValue == "trigger",
                      case .object(let ref)? = origin["ref"], let aid = ref["automation_id"]?.stringValue else { continue }
                let occ: Int = { if case .number(let n)? = ref["occurrence_index"] { return Int(n) }; return 0 }()
                out.append(.automationFinished(automationId: aid, occurrence: occ, status: e.string("status") ?? "completed",
                                               runId: e.string("run_id")))
            default: continue
            }
        }
        if !page.more { caughtUp = true }
        // A run that raised a result is told once, as news; its "finished" would say it twice.
        return out.filter {
            if case .automationFinished(let a, let occ, _, _) = $0 { return !raisedOccurrences.contains("\(a)#\(occ)") }
            return true
        }
    }
}

extension ISO8601DateFormatter {
    /// The gateway's event times (`2026-10-25T12:48:44.640530+00:00`).
    nonisolated(unsafe) static let events: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter(); f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]; return f
    }()
    nonisolated(unsafe) static let eventsPlain: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter(); f.formatOptions = [.withInternetDateTime]; return f
    }()
}

/// SSE framing for the person's event stream: one `UserEvent` per complete frame (keep-alives skipped).
public struct UserEventSSEParser: Sendable {
    private var line = Data()
    private var id: String?
    private var data: [String] = []

    public init() {}

    public mutating func feed(byte: UInt8) -> UserEvent? {
        if byte != 10 { line.append(byte); return nil }
        if line.last == 13 { line.removeLast() }
        let text = String(decoding: line, as: UTF8.self)
        line.removeAll(keepingCapacity: true)
        if text.isEmpty {
            defer { id = nil; data = [] }
            guard !data.isEmpty, var event = try? JSONDecoder().decode(UserEvent.self, from: Data(data.joined(separator: "\n").utf8)) else { return nil }
            if event.sequence == 0, let id, let n = Int(id) { event.sequence = n }
            return event
        }
        if text.hasPrefix(":") { return nil }
        let parts = text.split(separator: ":", maxSplits: 1, omittingEmptySubsequences: false)
        var value = parts.count > 1 ? String(parts[1]) : ""
        if value.hasPrefix(" ") { value.removeFirst() }
        switch parts[0] {
        case "id": id = value
        case "data": data.append(value)
        default: break
        }
        return nil
    }
}

/// The body of `POST /me/events/notifications`: this client showed the notice on `device`.
public struct NotificationReport: Encodable, Hashable, Sendable {
    public var channel: String
    public var outcome = "sent"
    public var recordKey: String
    public var device: String
    public init(channel: String = "phone", recordKey: String, device: String) {
        self.channel = channel; self.recordKey = recordKey; self.device = device
    }
    enum CodingKeys: String, CodingKey { case channel, outcome, recordKey = "record_key", device }
}

/// A gateway without the person's event stream answers these (404): the app keeps its polls.
public extension GatewayClient {
    func events(after: Int, limit: Int) async throws -> UserEventsPage { throw GatewayError.http(status: 404, body: "") }
    func reportNotification(_ report: NotificationReport) async throws { throw GatewayError.http(status: 404, body: "") }
    func triggerNames(connections: Bool, mailboxes: Bool) async throws -> TriggerNames { TriggerNames() }
    nonisolated func userEventStream(lastEventID: Int) -> AsyncThrowingStream<UserEvent, Error> {
        AsyncThrowingStream { $0.finish(throwing: GatewayError.http(status: 404, body: "")) }
    }
}
