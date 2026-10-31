import Foundation

/// The server's canonical ordering tuple. No ordering is inferred from message IDs or prose.
public struct PublicConversationOrder: Codable, Hashable, Sendable, Comparable {
    public let timestamp: String
    public let runId: String
    public let seq: Int
    public init(timestamp: String, runId: String, seq: Int) { self.timestamp = timestamp; self.runId = runId; self.seq = seq }
    public init(from decoder: Decoder) throws {
        var c = try decoder.unkeyedContainer()
        timestamp = try c.decode(String.self); runId = try c.decode(String.self); seq = try c.decode(Int.self)
        guard c.isAtEnd, ISO8601.date(timestamp) != nil, !runId.isEmpty, seq >= 0 else { throw GatewayError.invalidResponse }
    }
    public func encode(to encoder: Encoder) throws {
        var c = encoder.unkeyedContainer(); try c.encode(timestamp); try c.encode(runId); try c.encode(seq)
    }
    public static func < (a: Self, b: Self) -> Bool { (a.timestamp, a.runId, a.seq) < (b.timestamp, b.runId, b.seq) }
}

/// Only explicitly public communication and actual control-plane question interactions.
public struct PublicConversationEntry: Decodable, Hashable, Sendable, Identifiable {
    public enum Kind: String, Sendable { case update = "public_update", guidance, question, answer, outcome = "question_outcome", retained = "retained_reply" }
    public let id: String
    public let runId: String
    public let text: String
    public let kind: Kind
    public let order: PublicConversationOrder?
    public let questionId: String?
    public let waitKey: String?
    public let clientMessageId: String?
    public let fallback: String?
    public var isHuman: Bool { kind == .guidance || kind == .answer || kind == .retained }
    public var displayText: String {
        switch kind {
        case .guidance, .answer: return "You: " + text
        case .retained: return "You: " + text + "\nKept as context; this did not answer the question."
        case .outcome: return text // Exact trusted host communication; no claim the model consumed the fallback.
        default: return text
        }
    }
    public init(update: PublicConversationUpdate) {
        id = update.id; runId = update.runId; text = update.text; kind = .update; order = update.order
        questionId = nil; waitKey = nil; clientMessageId = nil; fallback = nil
    }
    public init(guidance: PublicUserGuidance) {
        id = guidance.id; runId = guidance.runId; text = guidance.text; kind = .guidance; order = guidance.order
        questionId = nil; waitKey = nil; clientMessageId = guidance.clientMessageId; fallback = nil
    }
    public init(from decoder: Decoder) throws { try self.init(row: JSONValue(from: decoder)) }
    public init(row: JSONValue) throws {
        guard let id = row["id"]?.stringValue, let run = row["run_id"]?.stringValue, !run.isEmpty,
              id.hasPrefix(run + ":"), let text = row["text"]?.stringValue,
              !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              let name = row["kind"]?.stringValue, let kind = Kind(rawValue: name),
              !Self.containsPrivateFence(row) else { throw GatewayError.invalidResponse }
        let role = row["role"]?.stringValue, source = row["source"]?.stringValue
        let qid = row["question"]?["id"]?.stringValue ?? row["question_id"]?.stringValue
        let key = row["wait_key"]?.stringValue
        let fallback = row["question"]?["fallback"]?.stringValue
        switch kind {
        case .update: guard role == "assistant", source == "emit_event" else { throw GatewayError.invalidResponse }
        case .guidance:
            guard role == "user", source == "user_guidance", row["guidance_status"]?.stringValue == "accepted",
                  PublicUserGuidance.validIdentity(id, runId: run) else { throw GatewayError.invalidResponse }
        case .question: guard role == "assistant", source == "wait", key?.isEmpty == false else { throw GatewayError.invalidResponse }
        case .answer: guard role == "user", source == "resume", key?.isEmpty == false else { throw GatewayError.invalidResponse }
        case .outcome:
            guard role == "system", source == "emit_event", row["question"]?["outcome"]?.stringValue == "expired",
                  qid?.isEmpty == false, fallback?.isEmpty == false else { throw GatewayError.invalidResponse }
        case .retained:
            guard role == "user", source == "emit_event", row["reply_status"]?.stringValue == "retained",
                  qid?.isEmpty == false else { throw GatewayError.invalidResponse }
        }
        self.id = id; runId = run; self.text = text; self.kind = kind; questionId = qid; waitKey = key
        clientMessageId = row["client_message_id"]?.stringValue; self.fallback = fallback
        order = row["order"].flatMap { try? JSONDecoder().decode(PublicConversationOrder.self, from: JSONEncoder().encode($0)) }
    }
    public static func containsPrivateFence(_ value: JSONValue) -> Bool {
        value.displayText.range(of: #"```\s*diary\b|<\s*diary\b|<\s*think\b"#, options: [.regularExpression, .caseInsensitive]) != nil
    }
}

/// A replay merge is silent. It never emits a cue, starts speech or reopens a resolved question.
public struct PublicConversationHistory: Sendable {
    public private(set) var entries: [PublicConversationEntry] = []
    public init() {}
    public mutating func merge(_ incoming: [PublicConversationEntry]) {
        for entry in incoming {
            if let i = entries.firstIndex(where: { existing in
                existing.id == entry.id || (entry.kind == .guidance && existing.kind == .guidance && entry.clientMessageId != nil
                    && existing.runId == entry.runId && existing.clientMessageId == entry.clientMessageId)
            }) {
                if !entry.id.hasPrefix(entry.runId + ":command:") { entries[i] = entry }
            } else { entries.append(entry) }
        }
        entries = entries.enumerated().sorted { a, b in
            if let x = a.element.order, let y = b.element.order, x != y { return x < y }
            if (a.element.order != nil) != (b.element.order != nil) { return a.element.order != nil }
            return a.offset < b.offset
        }.map(\.element)
    }
    public var latestHostOutcome: PublicConversationEntry? { entries.last?.kind == .outcome ? entries.last : nil }
    public func originalQuestion(for entry: PublicConversationEntry) -> PublicConversationEntry? {
        guard entry.kind != .question else { return nil }
        return entries.first { question in
            question.kind == .question && question.runId == entry.runId &&
                ((entry.questionId != nil && question.questionId == entry.questionId) || (entry.waitKey != nil && question.waitKey == entry.waitKey))
        }
    }
}

public struct PublicHistoryOmissions: Decodable, Sendable {
    public let counts: [String: Int]
    public let windowed: Bool
    public var notice: String? {
        guard windowed || counts.values.contains(where: { $0 > 0 }) else { return nil }
        let labels = [("public_updates_omitted", "updates"), ("public_messages_omitted", "replies"),
                      ("public_questions_omitted", "question entries"), ("conversation_runs_omitted", "runs")]
        let detail = labels.compactMap { key, label -> String? in
            guard let n = counts[key], n > 0 else { return nil }; return "\(n) \(label)"
        }.joined(separator: ", ")
        return "Some earlier exchanges are not loaded." + (detail.isEmpty ? "" : " (\(detail))")
    }
    public init(counts: [String: Int] = [:], windowed: Bool = false) { self.counts = counts; self.windowed = windowed }
    public init(from decoder: Decoder) throws {
        let row = try JSONValue(from: decoder)
        let keys = ["public_updates_omitted", "public_messages_omitted", "public_questions_omitted", "conversation_runs_omitted"]
        counts = Dictionary(uniqueKeysWithValues: keys.compactMap { key in
            guard case .number(let n) = row[key], n > 0, n.rounded() == n, n < Double(Int.max) else { return nil }
            return (key, Int(n))
        })
        let warnings = row["warnings"]?.arrayValue ?? []
        windowed = row["truncated"] == .bool(true) || row["history_truncated"] == .bool(true)
            || warnings.contains { warning in
                guard let text = warning.stringValue?.lowercased() else { return false }
                return ["windowed", "omitted", "truncat", "not folded"].contains(where: text.contains)
            }
    }
}
