import Foundation

/// One record of a run's step log (`GET /runs/{id}/ledger`), read for what the watch shows while
/// the run works: its kind, the tools it calls and how they ended, the media it makes, the wait it
/// is on, and a thinking step's own words. Everything else in a record (a thinking step carries the
/// whole conversation, 100–250 KB) is skipped while decoding.
public struct ActivityRecord: Decodable, Sendable, Equatable {
    public struct Call: Sendable, Equatable {
        public var name: String
        public var detail: String?
        public init(name: String, detail: String? = nil) { self.name = name; self.detail = detail }
    }
    public struct Outcome: Sendable, Equatable {
        public var name: String?
        public var success: Bool?
        public var error: String?
        public init(name: String? = nil, success: Bool?, error: String? = nil) { self.name = name; self.success = success; self.error = error }
    }

    public var stepId: String?
    /// The same for every record of one step (started, waiting, completed, a retry); a step resumed
    /// after an approval gets a new `step_id`.
    public var idempotencyKey: String?
    public var nodeId: String?
    public var status: String?
    public var startedAt: String?
    public var endedAt: String?
    public var error: String?
    /// `effect.type`: `llm_call`, `tool_calls`, `ask_user`, `start_subworkflow`, …
    public var type: String?
    public var calls: [Call] = []
    public var outcomes: [Outcome] = []
    /// A media step's `output.modality` (image, voice, video, music, sound).
    public var modality: String?
    /// A structured call (the Assistant's router answers in a schema).
    public var structured = false
    /// A finished thinking step's own words (`result.content`), when it wrote any.
    public var text: String?
    public var waitReason: String?
    public var waitKey: String?

    public init(stepId: String? = nil, idempotencyKey: String? = nil, nodeId: String?, status: String?, type: String?, startedAt: String? = nil, endedAt: String? = nil,
                calls: [Call] = [], outcomes: [Outcome] = [], modality: String? = nil, structured: Bool = false, text: String? = nil,
                waitReason: String? = nil, waitKey: String? = nil, error: String? = nil) {
        self.stepId = stepId; self.idempotencyKey = idempotencyKey; self.nodeId = nodeId; self.status = status; self.type = type; self.startedAt = startedAt
        self.endedAt = endedAt; self.calls = calls; self.outcomes = outcomes; self.modality = modality; self.structured = structured
        self.text = text; self.waitReason = waitReason; self.waitKey = waitKey; self.error = error
    }

    private enum K: String, CodingKey {
        case step_id, idempotency_key, node_id, status, started_at, ended_at, error, effect, result, type, payload, tool_calls, name, arguments
        case output, params, modality, response_schema, results, success, content, wait, reason, wait_key
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: K.self)
        stepId = try? c.decode(String.self, forKey: .step_id)
        idempotencyKey = try? c.decode(String.self, forKey: .idempotency_key)
        nodeId = try? c.decode(String.self, forKey: .node_id)
        status = try? c.decode(String.self, forKey: .status)
        startedAt = try? c.decode(String.self, forKey: .started_at)
        endedAt = try? c.decode(String.self, forKey: .ended_at)
        error = try? c.decode(String.self, forKey: .error)
        if let e = try? c.nestedContainer(keyedBy: K.self, forKey: .effect) {
            type = try? e.decode(String.self, forKey: .type)
            if let p = try? e.nestedContainer(keyedBy: K.self, forKey: .payload) {
                if var list = try? p.nestedUnkeyedContainer(forKey: .tool_calls) {
                    while !list.isAtEnd {
                        guard let call = try? list.nestedContainer(keyedBy: K.self) else { _ = try? list.decode(JSONValue.self); continue }
                        let name = (try? call.decode(String.self, forKey: .name)) ?? "tool"
                        calls.append(Call(name: name, detail: ToolDetail.preview(name, (try? call.decode(JSONValue.self, forKey: .arguments)))))
                    }
                }
                structured = p.contains(.response_schema) && (try? p.decodeNil(forKey: .response_schema)) == false
                let output = (try? p.nestedContainer(keyedBy: K.self, forKey: .output))
                    ?? (try? p.nestedContainer(keyedBy: K.self, forKey: .params)).flatMap { try? $0.nestedContainer(keyedBy: K.self, forKey: .output) }
                modality = output.flatMap { try? $0.decode(String.self, forKey: .modality) }
            }
        }
        if let r = try? c.nestedContainer(keyedBy: K.self, forKey: .result) {
            if var list = try? r.nestedUnkeyedContainer(forKey: .results) {
                while !list.isAtEnd {
                    guard let o = try? list.nestedContainer(keyedBy: K.self) else { _ = try? list.decode(JSONValue.self); continue }
                    outcomes.append(Outcome(name: try? o.decode(String.self, forKey: .name), success: try? o.decode(Bool.self, forKey: .success),
                                            error: try? o.decode(String.self, forKey: .error)))
                }
            }
            if let s = try? r.decode(String.self, forKey: .content) { text = s }
            if let w = try? r.nestedContainer(keyedBy: K.self, forKey: .wait) {
                waitReason = try? w.decode(String.self, forKey: .reason)
                waitKey = try? w.decode(String.self, forKey: .wait_key)
            }
        }
    }
}

public struct ActivityPage: Decodable, Sendable {
    public var items: [ActivityRecord]
    public var nextAfter: Int?
    enum CodingKeys: String, CodingKey { case items, nextAfter = "next_after" }
    public init(items: [ActivityRecord], nextAfter: Int?) { self.items = items; self.nextAfter = nextAfter }
}

/// What a tool call is about, in a few words: the search, the page, the file, the command.
public enum ToolDetail {
    public static func preview(_ name: String, _ args: JSONValue?) -> String? {
        guard let args else { return nil }
        func s(_ keys: String...) -> String? {
            for k in keys { if let v = args[k]?.stringValue?.trimmingCharacters(in: .whitespacesAndNewlines), !v.isEmpty { return v } }
            return nil
        }
        let raw: String?
        switch name {
        case "web_search", "skim_websearch", "search_web": raw = s("query", "q", "search")
        case "fetch_url", "skim_url", "render_url_html", "read_url":
            raw = s("url").map { u in URL(string: u).map { ($0.host() ?? "") + $0.path() }.flatMap { $0.isEmpty ? nil : $0 } ?? u }
        case "read_file", "write_file", "edit_file", "skim_files", "delete_file":
            raw = s("path", "file_path", "filename").map { ($0 as NSString).lastPathComponent }
        case "list_files", "search_files", "skim_folders": raw = s("pattern", "query", "path", "directory")
        case "execute_command", "shell_exec":
            raw = s("command", "cmd").map { cmd in
                cmd.split(separator: "\n").map { $0.trimmingCharacters(in: .whitespaces) }
                    .first { !$0.isEmpty && !$0.hasPrefix("#") && !$0.hasPrefix("set -") } ?? cmd
            }
        case "send_email", "reply_email": raw = [s("to"), s("subject")].compactMap { $0 }.joined(separator: " · ")
        default:
            if case .object(let o) = args {
                raw = o.keys.sorted().lazy.compactMap { k in k.hasPrefix("_") ? nil : o[k]?.stringValue }.first { !$0.isEmpty }
            } else { raw = nil }
        }
        guard let r = raw?.replacingOccurrences(of: "\n", with: " "), !r.isEmpty else { return nil }
        return r.count > 90 ? String(r.prefix(89)) + "…" : r
    }
}

/// A run's work as a list of steps, built from its step log (and its agent's): thinking, each tool
/// call, media being made, a wait on you. `apply` returns what just happened, for the orb.
public struct ActivityLog: Sendable, Equatable {
    public enum Kind: Hashable, Sendable {
        case thinking, routing, tool(String), media(String), question
    }
    public enum State: Hashable, Sendable { case running, done, failed(String?), waiting }
    public struct Step: Identifiable, Hashable, Sendable {
        public var id: String
        public var kind: Kind
        public var detail: String?
        public var started: Date?
        public var ended: Date?
        public var state: State
        public init(id: String, kind: Kind, detail: String? = nil, started: Date? = nil, ended: Date? = nil, state: State = .running) {
            self.id = id; self.kind = kind; self.detail = detail; self.started = started; self.ended = ended; self.state = state
        }
        public var toolName: String? { if case .tool(let n) = kind { n } else { nil } }
    }
    public enum Event: Equatable, Sendable { case thinking, tool(String), media(String), finished(success: Bool) }

    public private(set) var steps: [Step] = []
    /// Each step's calls as it started them: a finished or waiting record carries a call over 4 KB
    /// trimmed (`$slim`), and is matched to these.
    private var started: [String: [ActivityRecord.Call]] = [:]
    public init() {}

    @discardableResult
    public mutating func apply(_ records: [ActivityRecord], runId: String) -> [Event] {
        var events: [Event] = []
        for r in records {
            let base = "\(runId)|\(r.idempotencyKey ?? r.stepId ?? r.nodeId ?? "?")"
            let started = r.startedAt.flatMap(ISO8601.date), ended = r.endedAt.flatMap(ISO8601.date)
            switch r.type {
            case "llm_call":
                let kind: Kind
                if let m = r.modality { kind = .media(m) }
                else if r.structured { kind = .routing }
                else if r.nodeId == "reason" { kind = .thinking }
                else { continue }                      // a title or a memory note, not the work
                switch r.status {
                case "started":
                    if upsert(Step(id: base, kind: kind, started: started)) {
                        if case .media(let m) = kind { events.append(.media(m)) } else if kind == .thinking { events.append(.thinking) }
                    } else {
                        set(base) { if case .failed = $0.state { $0.state = .running; $0.ended = nil } }   // a retry
                    }
                case "completed":
                    let thought = r.text.map(Self.firstLine).flatMap { $0.isEmpty ? nil : $0 }
                    finish(base, kind: kind, started: started, ended: ended, state: .done, detail: kind == .thinking ? thought : nil)
                case "failed", "cancelled":
                    let why = r.status == "cancelled" ? "Stopped" : r.error.map(Self.firstLine)
                    finish(base, kind: kind, started: started, ended: ended, state: .failed(why), detail: nil)
                    if case .media = kind { events.append(.finished(success: false)) }
                default: break
                }
            case "tool_calls":
                var calls = r.calls
                if calls.isEmpty { calls = self.started[base] ?? r.outcomes.map { .init(name: $0.name ?? "tool") } }
                else if r.status == "started" || self.started[base] == nil { self.started[base] = calls }
                for (i, call) in calls.enumerated() {
                    let id = "\(base)|\(i)"
                    switch r.status {
                    case "started":
                        if upsert(Step(id: id, kind: .tool(call.name), detail: call.detail, started: started)) { events.append(.tool(call.name)) }
                    case "waiting":
                        upsert(Step(id: id, kind: .tool(call.name), detail: call.detail, started: started, state: .waiting))
                        set(id) { $0.state = .waiting }
                    case "completed", "failed", "cancelled":
                        let o = i < r.outcomes.count ? r.outcomes[i] : nil
                        let ok = r.status == "completed" && o?.success != false
                        let why = r.status == "cancelled" ? "Stopped" : (o?.error ?? r.error).map(Self.firstLine)
                        upsert(Step(id: id, kind: .tool(call.name), detail: call.detail, started: started))
                        set(id) { $0.state = ok ? .done : .failed(why); $0.ended = ended ?? $0.ended }
                        events.append(.finished(success: ok))
                    default: break
                    }
                }
            case "ask_user":
                if r.status == "waiting" { upsert(Step(id: base, kind: .question, started: started, state: .waiting)); set(base) { $0.state = .waiting } }
                if r.status == "completed" { set(base) { $0.state = .done; $0.ended = ended } }
            default: break
            }
        }
        return events
    }

    /// Adds a step once; true when it is new.
    @discardableResult
    private mutating func upsert(_ step: Step) -> Bool {
        if steps.contains(where: { $0.id == step.id }) { return false }
        steps.append(step)
        return true
    }

    private mutating func set(_ id: String, _ change: (inout Step) -> Void) {
        if let i = steps.firstIndex(where: { $0.id == id }) { change(&steps[i]) }
    }

    private mutating func finish(_ id: String, kind: Kind, started: Date?, ended: Date?, state: State, detail: String?) {
        upsert(Step(id: id, kind: kind, started: started))
        set(id) { s in
            s.state = state; s.ended = ended ?? s.ended
            if let detail { s.detail = detail }
        }
    }

    /// A step that never got its ending (the run ended): it ended with the run.
    public mutating func close(at date: Date, success: Bool) {
        for i in steps.indices where steps[i].state == .running || steps[i].state == .waiting {
            steps[i].state = success ? .done : .failed(nil)
            steps[i].ended = steps[i].ended ?? date
        }
        // The last thought of a finished run is its answer, shown in full above: not again here.
        if success, let i = steps.indices.last, steps[i].kind == .thinking { steps[i].detail = nil }
    }

    static func firstLine(_ s: String) -> String {
        let line = s.split(whereSeparator: \.isNewline).map { $0.trimmingCharacters(in: .whitespaces) }.first { !$0.isEmpty } ?? ""
        let plain = line.replacingOccurrences(of: "**", with: "").replacingOccurrences(of: "`", with: "")
        return plain.count > 140 ? String(plain.prefix(139)) + "…" : plain
    }

    /// How many tools are running now (the orb's satellites).
    public var runningTools: Int { steps.filter { $0.state == .running && $0.toolName != nil }.count }
    public var toolCount: Int { steps.filter { $0.toolName != nil }.count }
}
