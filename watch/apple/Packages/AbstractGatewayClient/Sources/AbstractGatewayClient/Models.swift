import Foundation

// Wire models for the AbstractGateway HTTP API (abstractgateway docs/api.md,
// service.py `run_summary`). Field names are snake_case on the wire; every
// model maps them explicitly so a renamed field fails decoding loudly.

/// Any JSON value. Tool-call `arguments` and run `output` are free-form.
public enum JSONValue: Codable, Hashable, Sendable {
    case string(String), number(Double), bool(Bool), object([String: JSONValue]), array([JSONValue]), null

    public init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self = .null }
        else if let b = try? c.decode(Bool.self) { self = .bool(b) }
        else if let n = try? c.decode(Double.self) { self = .number(n) }
        else if let s = try? c.decode(String.self) { self = .string(s) }
        else if let a = try? c.decode([JSONValue].self) { self = .array(a) }
        else { self = .object(try c.decode([String: JSONValue].self)) }
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .string(let s): try c.encode(s)
        case .number(let n): try c.encode(n)
        case .bool(let b): try c.encode(b)
        case .object(let o): try c.encode(o)
        case .array(let a): try c.encode(a)
        case .null: try c.encodeNil()
        }
    }

    public var stringValue: String? { if case .string(let s) = self { s } else { nil } }
    public subscript(key: String) -> JSONValue? { if case .object(let o) = self { o[key] } else { nil } }

    /// Compact one-line rendering for display.
    public var displayText: String {
        switch self {
        case .string(let s): return s
        case .number(let n): return n.rounded() == n ? String(Int(n)) : String(n)
        case .bool(let b): return b ? "true" : "false"
        case .null: return "null"
        case .array, .object:
            let enc = JSONEncoder(); enc.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
            return (try? enc.encode(self)).flatMap { String(data: $0, encoding: .utf8) } ?? ""
        }
    }
}

/// Kind of a wait. Tolerant: an unknown value decodes as `.other` instead of failing the page.
public enum WaitKind: Codable, Hashable, Sendable {
    case askUser, toolApproval, event, other(String)

    public init(rawValue: String) {
        switch rawValue {
        case "ask_user": self = .askUser
        case "tool_approval": self = .toolApproval
        case "event": self = .event
        default: self = .other(rawValue)
        }
    }
    public var rawValue: String {
        switch self {
        case .askUser: "ask_user"
        case .toolApproval: "tool_approval"
        case .event: "event"
        case .other(let s): s
        }
    }
    public init(from decoder: Decoder) throws { self.init(rawValue: try decoder.singleValueContainer().decode(String.self)) }
    public func encode(to encoder: Encoder) throws { var c = encoder.singleValueContainer(); try c.encode(rawValue) }
}

/// One tool call inside a `tool_approval` wait: `details: [{name, arguments, call_id?}]`.
public struct ToolCallDetail: Codable, Hashable, Sendable {
    public var name: String
    public var arguments: [String: JSONValue]
    public var callId: String?

    public init(name: String, arguments: [String: JSONValue], callId: String? = nil) {
        self.name = name; self.arguments = arguments; self.callId = callId
    }
    enum CodingKeys: String, CodingKey { case name, arguments, callId = "call_id" }
}

/// A wait on a person: `{run_id, wait_key, kind, reason?, prompt?, choices?, details?}`
/// (automations.md "waits on a person").
public struct Wait: Codable, Hashable, Sendable, Identifiable {
    public var runId: String
    public var waitKey: String
    public var kind: WaitKind
    public var reason: String?
    public var prompt: String?
    public var choices: [String]?
    public var allowFreeText: Bool?
    public var details: [ToolCallDetail]?

    // --- Display-only fields, NOT part of the gateway wait payload. ---
    /// Workflow label shown on the watch (from the run row's `workflow_id` in live mode).
    public var workflow: String?
    /// DEMO ONLY: the real wait payload has no risk tier yet (gateway-api-brief.md C).
    /// The mock sets it so the UI can show "Destructive" and gate Double Tap.
    public var riskTier: String?
    public var askedAt: Date?

    public var id: String { "\(runId):\(waitKey)" }
    public var isDestructive: Bool { ["destructive", "destroy"].contains(riskTier?.lowercased() ?? "") }
    public var toolName: String { kind == .askUser ? "ask_user" : (details?.first?.name ?? kind.rawValue) }

    public init(runId: String, waitKey: String, kind: WaitKind, reason: String? = nil, prompt: String? = nil,
                choices: [String]? = nil, allowFreeText: Bool? = nil, details: [ToolCallDetail]? = nil,
                workflow: String? = nil, riskTier: String? = nil, askedAt: Date? = nil) {
        self.runId = runId; self.waitKey = waitKey; self.kind = kind; self.reason = reason; self.prompt = prompt
        self.choices = choices; self.allowFreeText = allowFreeText; self.details = details
        self.workflow = workflow; self.riskTier = riskTier; self.askedAt = askedAt
    }

    enum CodingKeys: String, CodingKey {
        case runId = "run_id", waitKey = "wait_key", kind, reason, prompt, choices
        case allowFreeText = "allow_free_text", details, workflow, riskTier = "risk_tier", askedAt = "asked_at"
    }
}

/// `waiting` block of a run summary (service.py run_summary). It carries `reason`
/// (runtime WaitReason: user|event|until|job|subworkflow), not `kind`.
public struct RunWaiting: Codable, Hashable, Sendable {
    public var reason: String?
    public var waitKey: String?
    public var prompt: String?
    public var choices: [String]?
    public var allowFreeText: Bool?
    public var details: JSONValue?
    enum CodingKeys: String, CodingKey {
        case reason, waitKey = "wait_key", prompt, choices, allowFreeText = "allow_free_text", details
    }
}

/// Row of `GET /api/gateway/runs` and body of `GET /api/gateway/runs/{id}`.
public struct RunSummary: Codable, Hashable, Sendable, Identifiable {
    public var runId: String
    public var workflowId: String?
    public var status: String
    public var sessionId: String?
    public var createdAt: String?
    public var updatedAt: String?
    public var error: String?
    public var waiting: RunWaiting?
    public var output: JSONValue?
    public var kind: String?
    /// Display-only subtitle used by the mock (live mode derives one from status).
    public var subtitle: String?
    /// `include_metrics=true`: totals of the run and every sub-run below it.
    public var steps: Int?
    public var llmCalls: Int?
    public var toolCalls: Int?
    public var tokensTotal: Int?
    /// chat · discussion · automation · occurrence
    public var sessionKind: String?

    public var id: String { runId }
    public var isTerminal: Bool { ["completed", "failed", "cancelled"].contains(status) }

    public init(runId: String, workflowId: String?, status: String, sessionId: String? = nil, createdAt: String? = nil,
                updatedAt: String? = nil, error: String? = nil, waiting: RunWaiting? = nil, output: JSONValue? = nil,
                kind: String? = nil, subtitle: String? = nil) {
        self.runId = runId; self.workflowId = workflowId; self.status = status; self.sessionId = sessionId
        self.createdAt = createdAt; self.updatedAt = updatedAt; self.error = error; self.waiting = waiting
        self.output = output; self.kind = kind; self.subtitle = subtitle
    }

    enum CodingKeys: String, CodingKey {
        case runId = "run_id", workflowId = "workflow_id", status, sessionId = "session_id"
        case createdAt = "created_at", updatedAt = "updated_at", error, waiting, output, kind, subtitle
        case steps, llmCalls = "llm_calls", toolCalls = "tool_calls", tokensTotal = "tokens_total", sessionKind = "session_kind"
    }

    /// The run's final text. The exact output field for agent workflows is unverified
    /// (gateway-api-brief.md B): a string output is used as is; for an object the first
    /// of `response`, `answer`, `text`, `output` that is a string; else the JSON itself.
    public var outputText: String? {
        guard let output else { return nil }
        if let s = output.stringValue { return s }
        for key in ["response", "answer", "text", "output"] { if let s = output[key]?.stringValue { return s } }
        return output.displayText
    }

    /// True when the row's `waiting.reason` says a person must act (`user`). Rows waiting on a
    /// `subworkflow`, a timer (`until`), a `job` or an `event` are not shown to the person.
    public var waitsOnPerson: Bool { status == "waiting" && waiting?.reason == "user" }
    /// The child run a root waits on (`subworkflow:<child run id>`), if any.
    public var waitingOnChild: String? {
        guard status == "waiting", let key = waiting?.waitKey, key.hasPrefix("subworkflow:") else { return nil }
        let id = String(key.dropFirst("subworkflow:".count))
        return id.isEmpty ? nil : id
    }

    /// A wait on a person derived from this run's `waiting` block, if any.
    ///
    /// Verified against a live gateway (0.14): the runs LIST row carries only
    /// `waiting: {reason}`; the full block (`wait_key`, `prompt`, `choices`, `details`) is on
    /// `GET /runs/{id}`. For a tool approval the block is
    /// `details: {mode: "approval_required", tool_calls: [{name, arguments}]}` and the key is
    /// `tool_approval:<run>:act:<hash>`; for a question the key is `ask_user:...` with `prompt`
    /// and `choices`. The approval lives on the agent's CHILD run; the root waits on `subworkflow`.
    public var personWait: Wait? {
        guard status == "waiting", let w = waiting, let key = w.waitKey else { return nil }
        // A root run waiting on its agent (`subworkflow:<child>`) or on an event is not a person's wait.
        guard w.reason == "user" || key.hasPrefix("tool_approval:") || key.hasPrefix("ask_user:") else { return nil }
        var calls: [JSONValue] = []
        if case .array(let items)? = w.details { calls = items }
        else if case .object(let obj)? = w.details, case .array(let items)? = obj["tool_calls"] { calls = items }
        let details: [ToolCallDetail] = calls.compactMap { item in
            guard let name = item["name"]?.stringValue else { return nil }
            var args: [String: JSONValue] = [:]
            if case .object(let a)? = item["arguments"] { args = a.filter { !$0.key.hasPrefix("_") } }  // `_sandbox` is host data
            return ToolCallDetail(name: name, arguments: args, callId: item["call_id"]?.stringValue)
        }
        let kind: WaitKind
        if key.hasPrefix("tool_approval:") || !details.isEmpty { kind = .toolApproval }
        else if key.hasPrefix("ask_user:") || w.prompt != nil { kind = .askUser }
        else if w.reason == "event" { kind = .event }
        else { kind = .other(w.reason ?? "user") }
        return Wait(runId: runId, waitKey: key, kind: kind, reason: w.reason, prompt: w.prompt, choices: w.choices,
                    allowFreeText: w.allowFreeText, details: details.isEmpty ? nil : details, workflow: workflowId,
                    askedAt: updatedAt.flatMap(ISO8601.date))
    }
}

public struct RunsPage: Codable, Sendable {
    public var items: [RunSummary]
    public var count: Int?
    public var hasMore: Bool?
    enum CodingKeys: String, CodingKey { case items, count, hasMore = "has_more" }
}

public struct StartRunResponse: Codable, Sendable {
    public var runId: String
    enum CodingKeys: String, CodingKey { case runId = "run_id" }
}

public struct CommandAck: Codable, Sendable {
    public var accepted: Bool?
    public var duplicate: Bool?
}

/// `GET /api/gateway/me`.
/// `GET /api/gateway/me` answers `{ok, principal: {user_id, tenant_id, roles, ...}, auth, routing}`
/// (verified live 2026-10-16); older shapes put the fields at the top level, so both are read.
public struct Principal: Codable, Hashable, Sendable {
    public var userId: String?
    public var tenantId: String?
    public var roles: [String]?
    public var admin: Bool?
    enum CodingKeys: String, CodingKey { case userId = "user_id", tenantId = "tenant_id", roles, principal, admin }
    public init(userId: String?, tenantId: String?, roles: [String]?) { self.userId = userId; self.tenantId = tenantId; self.roles = roles }
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        if let inner = try? c.nestedContainer(keyedBy: CodingKeys.self, forKey: .principal) {
            userId = try inner.decodeIfPresent(String.self, forKey: .userId)
            tenantId = try inner.decodeIfPresent(String.self, forKey: .tenantId)
            roles = try inner.decodeIfPresent([String].self, forKey: .roles)
            admin = try inner.decodeIfPresent(Bool.self, forKey: .admin)
        } else {
            userId = try c.decodeIfPresent(String.self, forKey: .userId)
            tenantId = try c.decodeIfPresent(String.self, forKey: .tenantId)
            roles = try c.decodeIfPresent([String].self, forKey: .roles)
        }
    }
    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encodeIfPresent(userId, forKey: .userId); try c.encodeIfPresent(tenantId, forKey: .tenantId); try c.encodeIfPresent(roles, forKey: .roles)
    }
}

/// `last_occurrence` of an automation row, and the rows of `GET /automations/{id}/occurrences`.
public struct LastOccurrence: Codable, Hashable, Sendable {
    public var status: String?
    public var excerpt: String?
    public var runId: String?
    public var index: Int?
    public var firedAt: String?
    public var finishedAt: String?
    public var answer: String?
    public var triggerSummary: String?
    public init(status: String?, excerpt: String?, runId: String? = nil, index: Int? = nil, firedAt: String? = nil,
                finishedAt: String? = nil, answer: String? = nil, triggerSummary: String? = nil) {
        self.status = status; self.excerpt = excerpt; self.runId = runId; self.index = index
        self.firedAt = firedAt; self.finishedAt = finishedAt; self.answer = answer; self.triggerSummary = triggerSummary
    }
    enum CodingKeys: String, CodingKey { case status, excerpt, runId = "run_id", index, firedAt = "fired_at", finishedAt = "finished_at", answer, trigger }
    enum TriggerKeys: String, CodingKey { case summary }
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        status = try c.decodeIfPresent(String.self, forKey: .status)
        excerpt = try c.decodeIfPresent(String.self, forKey: .excerpt)
        runId = try c.decodeIfPresent(String.self, forKey: .runId)
        index = try c.decodeIfPresent(Int.self, forKey: .index)
        firedAt = try c.decodeIfPresent(String.self, forKey: .firedAt)
        finishedAt = try c.decodeIfPresent(String.self, forKey: .finishedAt)
        answer = try c.decodeIfPresent(String.self, forKey: .answer)
        if let t = try? c.nestedContainer(keyedBy: TriggerKeys.self, forKey: .trigger) { triggerSummary = try t.decodeIfPresent(String.self, forKey: .summary) }
    }
    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encodeIfPresent(status, forKey: .status); try c.encodeIfPresent(excerpt, forKey: .excerpt); try c.encodeIfPresent(runId, forKey: .runId)
        try c.encodeIfPresent(index, forKey: .index); try c.encodeIfPresent(firedAt, forKey: .firedAt); try c.encodeIfPresent(finishedAt, forKey: .finishedAt); try c.encodeIfPresent(answer, forKey: .answer)
    }
}

public struct OccurrencesPage: Codable, Sendable {
    public var items: [LastOccurrence]
    public var nextCursor: String?
    enum CodingKeys: String, CodingKey { case items, nextCursor = "next_cursor" }
}

/// `attention` of an automation row: what the person has not seen yet.
public struct Attention: Codable, Hashable, Sendable {
    public struct Item: Codable, Hashable, Sendable, Identifiable {
        public var kind: String?
        public var runId: String?
        public var at: String?
        public var title: String?
        public var body: String?
        public var cursor: String?
        public var id: String { cursor ?? "\(runId ?? "")-\(at ?? "")" }
        enum CodingKeys: String, CodingKey { case kind, runId = "run_id", at, title, body, cursor }
    }
    public var pendingWaits: Int?
    public var unread: Bool?
    public var unseenCount: Int?
    public var cursor: String?
    public var items: [Item]?
    public init(pendingWaits: Int? = nil, unread: Bool? = nil, unseenCount: Int? = nil, cursor: String? = nil, items: [Item]? = nil) {
        self.pendingWaits = pendingWaits; self.unread = unread; self.unseenCount = unseenCount; self.cursor = cursor; self.items = items
    }
    enum CodingKeys: String, CodingKey { case pendingWaits = "pending_waits", unread, unseenCount = "unseen_count", cursor, items }
}

/// Row of `GET /api/gateway/automations` (verified on gateway 0.15, 2026-10-17): `automation_id`, `title`,
/// `status`, `trigger {source_id, config {every | kind…}}`, `next_fire_at`, `last_occurrence`, `attention`,
/// `context_mode`, `occurrence_count`. Older/mock rows use `id` and `name`; both are read.
public struct AutomationSummary: Codable, Hashable, Sendable, Identifiable {
    public var id: String
    public var name: String?
    public var status: String?
    public var scheduleText: String?
    public var lastOccurrence: LastOccurrence?
    public var nextFireAt: String?
    public var attention: Attention?
    public var contextMode: String?
    public var occurrenceCount: Int?
    /// Display-only cadence pill used by the mock ("daily", "weekly", "on event").
    public var cadence: String?
    public var detail: String?

    public init(id: String, name: String?, status: String?, scheduleText: String?, lastOccurrence: LastOccurrence?,
                cadence: String? = nil, detail: String? = nil, nextFireAt: String? = nil, attention: Attention? = nil,
                contextMode: String? = nil, occurrenceCount: Int? = nil) {
        self.id = id; self.name = name; self.status = status; self.scheduleText = scheduleText
        self.lastOccurrence = lastOccurrence; self.cadence = cadence; self.detail = detail
        self.nextFireAt = nextFireAt; self.attention = attention; self.contextMode = contextMode; self.occurrenceCount = occurrenceCount
    }

    enum CodingKeys: String, CodingKey {
        case id, automationId = "automation_id", name, title, status, scheduleText = "schedule_text", lastOccurrence = "last_occurrence"
        case nextFireAt = "next_fire_at", attention, contextMode = "context_mode", occurrenceCount = "occurrence_count", trigger, cadence, detail
    }
    enum TriggerKeys: String, CodingKey { case sourceId = "source_id", config, summary }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        guard let ident = try c.decodeIfPresent(String.self, forKey: .automationId) ?? c.decodeIfPresent(String.self, forKey: .id) else {
            throw DecodingError.keyNotFound(CodingKeys.automationId, .init(codingPath: decoder.codingPath, debugDescription: "automation row without automation_id"))
        }
        id = ident
        name = try c.decodeIfPresent(String.self, forKey: .title) ?? c.decodeIfPresent(String.self, forKey: .name)
        status = try c.decodeIfPresent(String.self, forKey: .status)
        lastOccurrence = try c.decodeIfPresent(LastOccurrence.self, forKey: .lastOccurrence)
        nextFireAt = try c.decodeIfPresent(String.self, forKey: .nextFireAt)
        attention = try c.decodeIfPresent(Attention.self, forKey: .attention)
        contextMode = try c.decodeIfPresent(String.self, forKey: .contextMode)
        occurrenceCount = try c.decodeIfPresent(Int.self, forKey: .occurrenceCount)
        cadence = try c.decodeIfPresent(String.self, forKey: .cadence)
        detail = try c.decodeIfPresent(String.self, forKey: .detail)
        var text = try c.decodeIfPresent(String.self, forKey: .scheduleText)
        if text == nil, let t = try? c.nestedContainer(keyedBy: TriggerKeys.self, forKey: .trigger) {
            let source = try t.decodeIfPresent(String.self, forKey: .sourceId) ?? ""
            let config = (try? t.decodeIfPresent(JSONValue.self, forKey: .config)) ?? nil
            if let every = config?["every"]?.stringValue { text = "every \(every)" }
            else if let kind = config?["kind"]?.stringValue { text = kind }
            else if let summary = try t.decodeIfPresent(String.self, forKey: .summary) { text = summary }
            else if source.hasPrefix("email") { text = "when an email arrives" }
            else if !source.isEmpty { text = source }
        }
        scheduleText = text
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(id, forKey: .automationId); try c.encodeIfPresent(name, forKey: .title); try c.encodeIfPresent(status, forKey: .status)
        try c.encodeIfPresent(scheduleText, forKey: .scheduleText); try c.encodeIfPresent(lastOccurrence, forKey: .lastOccurrence)
        try c.encodeIfPresent(nextFireAt, forKey: .nextFireAt); try c.encodeIfPresent(attention, forKey: .attention)
        try c.encodeIfPresent(cadence, forKey: .cadence); try c.encodeIfPresent(detail, forKey: .detail)
    }

    /// Short second line for a row: schedule, last result, unseen count.
    public var rowDetail: String {
        if let detail { return detail }
        var parts: [String] = []
        if let s = scheduleText { parts.append(s) }
        if let st = lastOccurrence?.status { parts.append("last " + st) }
        if let n = attention?.unseenCount, n > 0 { parts.append("\(n) unseen") }
        return parts.joined(separator: " · ")
    }
    public var needsAttention: Bool { (attention?.pendingWaits ?? 0) > 0 || (attention?.unread ?? false) }
}

public struct AutomationsPage: Codable, Sendable {
    public var items: [AutomationSummary]
    public var nextCursor: String?
    enum CodingKeys: String, CodingKey { case items, nextCursor = "next_cursor" }
}

// MARK: - Commands

/// Answer to a wait, encoded as the inner `payload.payload`.
public enum WaitAnswer: Sendable, Hashable {
    case approve, deny, respond(String)
}

/// `POST /api/gateway/commands` body for `type: "resume"`:
/// `{command_id, run_id, type:"resume", payload:{wait_key, payload:{approved}|{response}}}`.
public struct ResumeCommand: Encodable, Sendable {
    public var commandId: String
    public var runId: String
    public var waitKey: String
    public var answer: WaitAnswer

    public init(commandId: String = UUID().uuidString.lowercased(), runId: String, waitKey: String, answer: WaitAnswer) {
        self.commandId = commandId; self.runId = runId; self.waitKey = waitKey; self.answer = answer
    }

    enum Top: String, CodingKey { case commandId = "command_id", runId = "run_id", type, payload }
    enum Outer: String, CodingKey { case waitKey = "wait_key", payload }
    enum Inner: String, CodingKey { case approved, response }

    public func encode(to encoder: Encoder) throws {
        var top = encoder.container(keyedBy: Top.self)
        try top.encode(commandId, forKey: .commandId)
        try top.encode(runId, forKey: .runId)
        try top.encode("resume", forKey: .type)
        var outer = top.nestedContainer(keyedBy: Outer.self, forKey: .payload)
        try outer.encode(waitKey, forKey: .waitKey)
        var inner = outer.nestedContainer(keyedBy: Inner.self, forKey: .payload)
        switch answer {
        case .approve: try inner.encode(true, forKey: .approved)
        case .deny: try inner.encode(false, forKey: .approved)
        case .respond(let text): try inner.encode(text, forKey: .response)
        }
    }
}

/// `POST /api/gateway/runs/start` body for one chat turn.
/// The run's own approval policy (`_runtime.tool_policy`, read by the runtime per run): tools at or
/// below `autoApproveMaxRiskRank` run without asking; a name in `requireApprovalTools` always asks.
public struct RunToolPolicy: Encodable, Sendable, Equatable {
    public var autoApproveMaxRiskRank: Int?
    public var requireApprovalTools: [String]
    public init(autoApproveMaxRiskRank: Int?, requireApprovalTools: [String]) {
        self.autoApproveMaxRiskRank = autoApproveMaxRiskRank; self.requireApprovalTools = requireApprovalTools
    }
    enum CodingKeys: String, CodingKey { case autoApproveMaxRiskRank = "auto_approve_max_risk_rank", requireApprovalTools = "require_approval_tools" }
}

/// One tool of `GET /api/gateway/discovery/tools`, with the gateway's risk tier
/// (observe 1 · act 2 · outreach 3 · destroy 4).
public struct ToolInfo: Decodable, Sendable, Hashable {
    public var name: String
    public var riskTier: String?
    public var riskRank: Int?
    enum CodingKeys: String, CodingKey { case name, riskTier = "risk_tier", riskRank = "risk_rank", risk }
    struct Risk: Decodable { var rank: Int?; var tier: String? }
    public init(name: String, riskTier: String?, riskRank: Int?) { self.name = name; self.riskTier = riskTier; self.riskRank = riskRank }
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        name = try c.decode(String.self, forKey: .name)
        let risk = try? c.decodeIfPresent(Risk.self, forKey: .risk)
        riskTier = (try? c.decodeIfPresent(String.self, forKey: .riskTier)) ?? risk?.tier
        riskRank = (try? c.decodeIfPresent(Int.self, forKey: .riskRank)) ?? risk?.rank
    }
}

struct ToolsPage: Decodable { let items: [ToolInfo] }

public struct StartRunRequest: Encodable, Sendable {
    public struct InputData: Encodable, Sendable {
        public struct Runtime: Encodable, Sendable {
            public var toolPolicy: RunToolPolicy
            enum CodingKeys: String, CodingKey { case toolPolicy = "tool_policy" }
        }
        public var prompt: String
        public var useSessionHistory = true
        /// The agent's system prompt (the default agent has no persona of its own).
        public var system: String?
        public var runtime: Runtime?
        enum CodingKeys: String, CodingKey { case prompt, useSessionHistory = "use_session_history", system, runtime = "_runtime" }
    }
    public var flowId = "@default"
    public var interface = "abstractcode.agent.v1"
    public var sessionId: String?
    public var inputData: InputData

    public init(prompt: String, sessionId: String?, toolPolicy: RunToolPolicy? = nil, system: String? = AssistantPersona.system) {
        self.sessionId = sessionId
        self.inputData = InputData(prompt: prompt, system: system, runtime: toolPolicy.map { .init(toolPolicy: $0) })
    }
    enum CodingKeys: String, CodingKey { case flowId = "flow_id", interface, sessionId = "session_id", inputData = "input_data" }
}


/// Gateway timestamps are ISO-8601 with fractional seconds and an offset.
public enum ISO8601 {
    nonisolated(unsafe) private static let fractional: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter(); f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]; return f
    }()
    nonisolated(unsafe) private static let plain = ISO8601DateFormatter()
    public static func date(_ s: String) -> Date? { fractional.date(from: s) ?? plain.date(from: s) }
}


// MARK: - Entities and the responder

/// Row of `GET /api/gateway/entities` (`{entities: [...]}`): the homes the signed-in account may
/// visit. Only `name` is relied on; other keys are kept for display.
public struct EntitySummary: Codable, Hashable, Sendable, Identifiable {
    public var name: String
    public var extra: [String: JSONValue]
    public var id: String { name }
    /// "asleep · born 6 Oct": the list row carries `created_at`; `state` may be a string or `{state, …}`.
    public var detail: String? {
        var parts: [String] = []
        if let s = extra["state"]?.stringValue ?? extra["state"]?["state"]?.stringValue { parts.append(s) }
        else if let p = extra["phase"]?.stringValue { parts.append(p) }
        if let c = extra["created_at"]?.stringValue, let d = ISO8601.date(c) {
            parts.append("born " + d.formatted(.dateTime.day().month(.abbreviated)))
        } else if let age = extra["age"]?.stringValue { parts.append(age) }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }
    public init(name: String, extra: [String: JSONValue] = [:]) { self.name = name; self.extra = extra }
    public init(from decoder: Decoder) throws {
        let all = try decoder.singleValueContainer().decode([String: JSONValue].self)
        guard let n = all["name"]?.stringValue ?? all["id"]?.stringValue ?? all["entity"]?.stringValue else {
            throw DecodingError.dataCorrupted(.init(codingPath: decoder.codingPath, debugDescription: "entity row without a name"))
        }
        name = n; extra = all.filter { $0.key != "name" }
    }
    public func encode(to encoder: Encoder) throws {
        var all = extra; all["name"] = .string(name)
        var c = encoder.singleValueContainer(); try c.encode(all)
    }
}

public struct EntitiesPage: Codable, Sendable { public var entities: [EntitySummary] }

/// Who answers an Ask.
public enum Responder: Hashable, Sendable {
    case assistant
    case entity(String)
    public var title: String {
        switch self { case .assistant: "Assistant"; case .entity(let n): n.capitalized }
    }
    public var storageKey: String {
        switch self { case .assistant: "assistant"; case .entity(let n): "entity:" + n }
    }
    public init(storageKey: String?) {
        if let k = storageKey, k.hasPrefix("entity:") { self = .entity(String(k.dropFirst(7))) } else { self = .assistant }
    }
}

/// `POST /entities/{name}/chat/open` answers `{chat_id, ...}`; `.../turn` answers `{reply, tools_ran, ...}`.
public struct ChatOpenResponse: Codable, Sendable {
    public var chatId: String
    enum CodingKeys: String, CodingKey { case chatId = "chat_id" }
}
public struct ChatTurnResponse: Codable, Sendable {
    public var reply: String?
    public var toolsRan: [JSONValue]?
    enum CodingKeys: String, CodingKey { case reply, toolsRan = "tools_ran" }
}
public struct ChatTurnRequest: Encodable, Sendable { public var text: String; public init(text: String) { self.text = text } }
public struct ChatOpenRequest: Encodable, Sendable { public init() {} }

// MARK: - Tool classes a card can render differently

extension Wait {
    /// An outreach tool: the gateway's approval gate always asks before a send to anyone but you
    /// (abstractgateway/docs/email.md). Derived from the tool name, not from a gateway tier.
    public var isOutreach: Bool {
        let n = toolName.lowercased()
        return n.hasPrefix("send_") || n == "send_message" || n.contains("whatsapp") || n.contains("telegram")
    }
    public var recipient: String? { details?.first?.arguments["to"]?.displayText }
    public var subject: String? { details?.first?.arguments["subject"]?.stringValue }
    /// The one argument a person needs to decide: the command, the URL, the path, the query…
    public var primaryArgument: (key: String, value: String)? {
        let args = details?.first?.arguments ?? [:]
        for k in ["command", "url", "path", "file_path", "query", "to", "name"] {
            if let v = args[k]?.stringValue, !v.isEmpty { return (k, v) }
        }
        return nil
    }
    /// Arguments worth a glance after the primary one: no host plumbing, no flags, no long blobs.
    public var secondaryArguments: [(String, String)] {
        let hide: Set<String> = ["command", "url", "path", "file_path", "query", "to", "subject", "body_text", "body_html",
                                 "timeout", "capture_output", "headers", "user_agent", "method", "include_binary_preview",
                                 "include_full_content", "keep_links", "render_js", "working_directory"]
        return (details?.first?.arguments ?? [:]).filter { !hide.contains($0.key) && !$0.key.hasPrefix("_") }
            .sorted { $0.key < $1.key }.prefix(4).map { ($0.key, $0.value.displayText) }
    }
}


// MARK: - Ledger and commands

/// One record of `GET /api/gateway/runs/{id}/ledger?after=N` (`{items, next_after}`); verified on gateway 0.15:
/// `node_id, status (started|completed|waiting|failed|cancelled), effect {type…}?, result, error, started_at, ended_at, step_id`.
public struct LedgerRecord: Codable, Hashable, Sendable, Identifiable {
    public var stepId: String?
    public var nodeId: String?
    public var status: String?
    public var effect: JSONValue?
    public var result: JSONValue?
    public var error: String?
    public var startedAt: String?
    public var endedAt: String?
    public var id: String { "\(stepId ?? "")|\(status ?? "")|\(nodeId ?? "")" }
    enum CodingKeys: String, CodingKey { case stepId = "step_id", nodeId = "node_id", status, effect, result, error, startedAt = "started_at", endedAt = "ended_at" }
    public init(stepId: String? = nil, nodeId: String?, status: String?, effect: JSONValue? = nil, result: JSONValue? = nil,
                error: String? = nil, startedAt: String? = nil, endedAt: String? = nil) {
        self.stepId = stepId; self.nodeId = nodeId; self.status = status; self.effect = effect; self.result = result
        self.error = error; self.startedAt = startedAt; self.endedAt = endedAt
    }
    public var effectType: String? { effect?["type"]?.stringValue ?? effect?.stringValue }
    /// One line a person can read on a watch.
    public var summary: String {
        if let error, !error.isEmpty { return error }
        if let r = result {
            if let w = r["wait"], let reason = w["reason"]?.stringValue { return "waiting · " + reason }
            if r["resumed"]?.stringValue != nil || (r["resumed"].map { if case .bool(true) = $0 { true } else { false } } ?? false) { return "resumed" }
            if let out = r["output"]?["response"]?.stringValue { return out }
            if let tools = r["tool_calls"], case .array(let calls) = tools, let name = calls.first?["name"]?.stringValue { return name }
            if let mode = r["mode"]?.stringValue { return mode }
        }
        return effectType ?? status ?? ""
    }
}

public struct LedgerPage: Codable, Sendable {
    public var items: [LedgerRecord]
    public var nextAfter: Int?
    enum CodingKeys: String, CodingKey { case items, nextAfter = "next_after" }
}

/// `POST /api/gateway/commands` `{command_id, run_id, type: "cancel", payload: {}}`.
public struct CancelCommand: Encodable, Sendable {
    public var commandId = UUID().uuidString.lowercased()
    public var runId: String
    public var type = "cancel"
    public var payload: [String: String] = [:]
    public init(runId: String) { self.runId = runId }
    enum CodingKeys: String, CodingKey { case commandId = "command_id", runId = "run_id", type, payload }
}

/// `POST /api/gateway/automations/{id}/seen` `{attention_cursor}`.
public struct SeenRequest: Encodable, Sendable {
    public var attentionCursor: String
    public init(attentionCursor: String) { self.attentionCursor = attentionCursor }
    enum CodingKeys: String, CodingKey { case attentionCursor = "attention_cursor" }
}


/// Where a text's voice comes from: a run's session (the gateway's voice) or an entity (its own voice).
public enum SpeechScope: Hashable, Sendable {
    case run(String)
    case entity(String)
}

struct SpeechRequest: Encodable {
    let text: String
    let format = "wav"
}

struct SpeechEvent: Decodable {
    let type: String
    let audioB64: String?
    let error: String?
    enum CodingKeys: String, CodingKey { case type, audioB64 = "audio_b64", error }
}

/// A 16-bit mono WAV of a voiced tone with a syllable-rate envelope (mock speech).
public enum SyntheticSpeech {
    public static func wav(seconds: Double, seed: Int, rate: Int = 16_000) -> Data {
        let n = Int(seconds * Double(rate))
        var pcm = Data(capacity: n * 2)
        for i in 0..<n {
            let t = Double(i) / Double(rate)
            let syllable = max(0, sin(t * 2 * .pi * (3.1 + Double(seed) * 0.4)))
            let phrase = 0.5 * (1 + sin(t * 2 * .pi * 0.45 + Double(seed)))
            let pitch = 140 + 25 * sin(t * 2 * .pi * 0.7)
            let v = 0.35 * syllable * phrase * (sin(t * 2 * .pi * pitch) + 0.4 * sin(t * 4 * .pi * pitch))
            var sample = Int16(max(-1, min(1, v)) * 32_000).littleEndian
            withUnsafeBytes(of: &sample) { pcm.append(contentsOf: $0) }
        }
        var header = Data()
        func u32(_ v: UInt32) { var x = v.littleEndian; withUnsafeBytes(of: &x) { header.append(contentsOf: $0) } }
        func u16(_ v: UInt16) { var x = v.littleEndian; withUnsafeBytes(of: &x) { header.append(contentsOf: $0) } }
        header.append(contentsOf: Array("RIFF".utf8)); u32(UInt32(36 + pcm.count)); header.append(contentsOf: Array("WAVE".utf8))
        header.append(contentsOf: Array("fmt ".utf8)); u32(16); u16(1); u16(1); u32(UInt32(rate)); u32(UInt32(rate * 2)); u16(2); u16(16)
        header.append(contentsOf: Array("data".utf8)); u32(UInt32(pcm.count))
        return header + pcm
    }
}

struct AttachmentUploadResponse: Decodable {
    struct Ref: Decodable {
        let artifact: String?
        let runId: String?
        enum CodingKeys: String, CodingKey { case artifact = "$artifact", runId = "run_id" }
    }
    let runId: String?
    let artifact: Ref?
    let attachment: Ref?
    enum CodingKeys: String, CodingKey { case runId = "run_id", artifact, attachment }
}

struct TranscribeRequest: Encodable {
    let audioArtifact: [String: String]
    enum CodingKeys: String, CodingKey { case audioArtifact = "audio_artifact" }
}

struct TranscribeResponse: Decodable { let text: String }


/// Who answers on the watch. The gateway's default agent has no persona ("I'm ChatGPT, made by
/// OpenAI" when asked, 2026-10-17), so every Ask run carries this as its `system` pin, the same pin
/// the gateway's own Telegram bridge uses; the agent keeps its tools (verified live).
public enum AssistantPersona {
    public static let system = """
    You are AbstractAssistant, the user's personal AI assistant, built on AbstractFramework and running on their own AbstractGateway. \
    When asked your name or who you are, you are AbstractAssistant. \
    The user is talking to you from their Apple Watch, often by voice, and your answer is read aloud: lead with the answer in one or two short sentences, \
    then add detail only when it helps. Use your tools when they help.
    """
}

/// One conversation: the turns (root runs) that share a `session_id`, newest first.
public struct SessionSummary: Hashable, Sendable, Identifiable {
    public var id: String
    /// Oldest turn seen (its prompt titles the session) and newest turn (its state is the session's).
    public var firstRunId: String
    public var latest: RunSummary
    public var turns: Int
    public var toolCalls: Int
    public var llmCalls: Int
    public var kind: String?
    public var updatedAt: Date?

    public var status: String { latest.status }
    public var needsPerson: Bool { latest.waitsOnPerson }

    /// Groups root runs (newest first, as listed) into sessions, newest activity first.
    public static func group(_ runs: [RunSummary]) -> [SessionSummary] {
        var order: [String] = []
        var bucket: [String: [RunSummary]] = [:]
        for r in runs {
            let key = r.sessionId ?? r.runId
            if bucket[key] == nil { order.append(key) }
            bucket[key, default: []].append(r)
        }
        return order.compactMap { key in
            guard let rows = bucket[key], let newest = rows.first, let oldest = rows.last else { return nil }
            return SessionSummary(id: key, firstRunId: oldest.runId, latest: newest, turns: rows.count,
                                  toolCalls: rows.compactMap(\.toolCalls).reduce(0, +), llmCalls: rows.compactMap(\.llmCalls).reduce(0, +),
                                  kind: newest.sessionKind,
                                  updatedAt: (newest.updatedAt ?? newest.createdAt).flatMap(ISO8601.date))
        }
    }

    /// "Compare overall survival by arm in the ADTTE" from a prompt: its first line, cut at a word
    /// boundary near `limit` characters.
    public static func title(fromPrompt prompt: String, limit: Int = 32) -> String {
        let line = prompt.split(whereSeparator: \.isNewline).first.map(String.init)?.trimmingCharacters(in: .whitespaces) ?? ""
        guard line.count > limit else { return line }
        let cut = line.prefix(limit)
        let atWord = cut.lastIndex(of: " ").map { cut[..<$0] } ?? cut
        return atWord.trimmingCharacters(in: CharacterSet(charactersIn: " ,;:-")) + "…"
    }
}

struct RunInputData: Decodable {
    struct Inner: Decodable { let prompt: String? }
    let inputData: Inner?
    enum CodingKeys: String, CodingKey { case inputData = "input_data" }
}
