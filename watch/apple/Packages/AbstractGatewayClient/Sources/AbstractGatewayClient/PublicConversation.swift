import Foundation

/// Explicit, server-published communication. Never reconstructed from model reasoning or tools.
public struct PublicConversationUpdate: Codable, Hashable, Sendable, Identifiable {
    public var id: String
    public var text: String
    public var runId: String
    public var sourceCallIds: [String]?
    public init(id: String, text: String, runId: String, sourceCallIds: [String]? = nil) {
        self.id = id; self.text = text; self.runId = runId; self.sourceCallIds = sourceCallIds
    }
    enum CodingKeys: String, CodingKey { case id, text, runId = "run_id", sourceCallIds = "source_call_ids" }
}

/// A reply pins the displayed idea, even when another update arrives while the person speaks.
public enum ConversationReply {
    public static func text(_ text: String, to update: PublicConversationUpdate?) -> String {
        guard let update else { return text }
        return "Regarding your message [\(update.id)]:\n\(update.text)\n\nMy reply:\n\(text)"
    }
}

/// Authoritative question metadata. Malformed timing is never presented as a valid countdown.
public struct ConversationQuestion: Codable, Hashable, Sendable, Identifiable {
    public let id: String
    public let importance: String
    public let publishedAt: String
    public let deadline: String?
    public let fallback: String?
    enum CodingKeys: String, CodingKey { case id, purpose, importance, publishedAt = "published_at", deadline, fallback }
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        importance = try c.decode(String.self, forKey: .importance)
        publishedAt = try c.decode(String.self, forKey: .publishedAt)
        deadline = try c.decodeIfPresent(String.self, forKey: .deadline)
        fallback = try c.decodeIfPresent(String.self, forKey: .fallback)
        guard try c.decode(String.self, forKey: .purpose) == "conversation", !id.isEmpty,
              let published = ISO8601.date(publishedAt) else { throw GatewayError.invalidResponse }
        if importance == "essential" {
            guard deadline == nil, fallback == nil else { throw GatewayError.invalidResponse }
        } else if importance == "clarification" {
            guard let deadline, let end = ISO8601.date(deadline),
                  (120...300).contains(end.timeIntervalSince(published)),
                  let fallback, !fallback.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { throw GatewayError.invalidResponse }
        } else { throw GatewayError.invalidResponse }
    }
    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(id, forKey: .id); try c.encode("conversation", forKey: .purpose)
        try c.encode(importance, forKey: .importance); try c.encode(publishedAt, forKey: .publishedAt)
        try c.encodeIfPresent(deadline, forKey: .deadline); try c.encodeIfPresent(fallback, forKey: .fallback)
    }
    public static func parse(_ value: JSONValue?) -> Self? {
        guard let value, let bytes = try? JSONEncoder().encode(value) else { return nil }
        return try? JSONDecoder().decode(Self.self, from: bytes)
    }
    public var deadlineDate: Date? { deadline.flatMap(ISO8601.date) }
}

public struct PublicConversationView: Decodable, Sendable {
    public let updates: [PublicConversationUpdate]
    private enum K: String, CodingKey { case messages }
    private struct Message: Decodable {
        var id: String?; var kind: String?; var text: String?; var run_id: String?; var source_call_ids: [String]?
    }
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: K.self)
        let messages = try c.decode([Message].self, forKey: .messages)
        updates = messages.compactMap { m in
            guard m.kind == "public_update", let id = m.id, !id.isEmpty,
                  let text = m.text, !text.isEmpty, let run = m.run_id, !run.isEmpty else { return nil }
            return .init(id: id, text: text, runId: run, sourceCallIds: m.source_call_ids)
        }
    }
}

public extension GatewayClient {
    func publicConversation(runId: String) async throws -> [PublicConversationUpdate] { throw GatewayError.invalidResponse }
    func guideRun(runId: String, text: String) async throws { throw GatewayError.invalidResponse }
    func startConversationRun(prompt: String, sessionId: String?, toolPolicy: RunToolPolicy?, tools: [String]?, workflow: WorkflowChoice?, primaryImage: MediaItem?) async throws -> String { throw GatewayError.invalidResponse }
    func openConversationVisit(name: String, sessionId: String) async throws -> EntitySessionState { throw GatewayError.invalidResponse }
    func guideEntityVisit(name: String, runId: String, text: String) async throws { throw GatewayError.invalidResponse }
    func answerEntityQuestion(name: String, runId: String, wait: Wait, text: String) async throws { throw GatewayError.invalidResponse }
}
