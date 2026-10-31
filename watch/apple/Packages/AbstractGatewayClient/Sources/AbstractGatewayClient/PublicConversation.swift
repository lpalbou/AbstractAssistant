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

/// A server-admitted human correction. Acceptance does not claim the actor considered it.
public struct PublicUserGuidance: Codable, Hashable, Sendable, Identifiable {
    public let id: String
    public let text: String
    public let runId: String
    public let clientMessageId: String?
    enum CodingKeys: String, CodingKey { case id, text, runId = "run_id", role, kind, guidanceStatus = "guidance_status", clientMessageId = "client_message_id" }
    public init(runId: String, seq: Int, text: String, clientMessageId: String? = nil) throws {
        guard seq > 0, !runId.isEmpty, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { throw GatewayError.invalidResponse }
        self.id = "\(runId):guidance:\(seq)"; self.runId = runId; self.text = text; self.clientMessageId = clientMessageId
    }
    /// Command admission precedes the runtime sidecar receipt. Command-store seq is NOT its identity.
    public init(acceptedCommand id: String, runId: String, text: String) throws {
        guard !id.isEmpty, !runId.isEmpty, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { throw GatewayError.invalidResponse }
        self.id = runId + ":command:" + id; self.text = text; self.runId = runId; self.clientMessageId = id
    }
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id); text = try c.decode(String.self, forKey: .text)
        runId = try c.decode(String.self, forKey: .runId)
        clientMessageId = try c.decodeIfPresent(String.self, forKey: .clientMessageId)
        guard try c.decode(String.self, forKey: .role) == "user", try c.decode(String.self, forKey: .kind) == "guidance",
              try c.decode(String.self, forKey: .guidanceStatus) == "accepted", Self.validIdentity(id, runId: runId),
              !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { throw GatewayError.invalidResponse }
    }
    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(id, forKey: .id); try c.encode(text, forKey: .text); try c.encode(runId, forKey: .runId)
        try c.encode("user", forKey: .role); try c.encode("guidance", forKey: .kind); try c.encode("accepted", forKey: .guidanceStatus)
        try c.encodeIfPresent(clientMessageId, forKey: .clientMessageId)
    }
    static func validIdentity(_ id: String, runId: String) -> Bool {
        let prefix = runId + ":guidance:"
        guard !runId.isEmpty, id.hasPrefix(prefix), let seq = Int(id.dropFirst(prefix.count)), seq > 0 else { return false }
        return id == prefix + String(seq)
    }
}

/// Identity-based reconciliation survives replay, reconnect and a newly created view.
public struct PublicGuidanceHistory: Sendable {
    public private(set) var messages: [PublicUserGuidance] = []
    public init() {}
    public mutating func merge(_ incoming: [PublicUserGuidance]) {
        for message in incoming {
            if let i = messages.firstIndex(where: { existing in
                existing.id == message.id || (message.clientMessageId != nil && existing.runId == message.runId && existing.clientMessageId == message.clientMessageId)
            }) {
                // A late command ACK must not replace its already-published runtime receipt.
                if !message.id.hasPrefix(message.runId + ":command:") { messages[i] = message }
            } else { messages.append(message) }
        }
    }
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
    public let guidance: [PublicUserGuidance]
    public init(updates: [PublicConversationUpdate], guidance: [PublicUserGuidance]) { self.updates = updates; self.guidance = guidance }
    private enum K: String, CodingKey { case messages }
    private struct Message: Decodable {
        var id: String?; var kind: String?; var text: String?; var run_id: String?; var source_call_ids: [String]?
        var role: String?; var source: String?; var guidance_status: String?; var client_message_id: String?
    }
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: K.self)
        let messages = try c.decode([Message].self, forKey: .messages)
        guidance = messages.compactMap { m in
            guard m.role == "user", m.kind == "guidance", m.source == "user_guidance", m.guidance_status == "accepted",
                  let id = m.id, let run = m.run_id, PublicUserGuidance.validIdentity(id, runId: run),
                  let text = m.text, let seq = Int(id.dropFirst((run + ":guidance:").count)) else { return nil }
            return try? .init(runId: run, seq: seq, text: text, clientMessageId: m.client_message_id)
        }
        updates = messages.compactMap { m in
            guard m.kind == "public_update", let id = m.id, !id.isEmpty,
                  let text = m.text, !text.isEmpty, let run = m.run_id, !run.isEmpty else { return nil }
            return .init(id: id, text: text, runId: run, sourceCallIds: m.source_call_ids)
        }
    }
}

public extension GatewayClient {
    func publicConversation(runId: String) async throws -> [PublicConversationUpdate] { throw GatewayError.invalidResponse }
    func conversationHistory(runId: String) async throws -> PublicConversationView { .init(updates: try await publicConversation(runId: runId), guidance: []) }
    func guideRun(runId: String, text: String) async throws { throw GatewayError.invalidResponse }
    func guideRun(runId: String, text: String, displayText: String) async throws -> PublicUserGuidance { throw GatewayError.invalidResponse }
    func startConversationRun(prompt: String, sessionId: String?, toolPolicy: RunToolPolicy?, tools: [String]?, workflow: WorkflowChoice?, primaryImage: MediaItem?) async throws -> String { throw GatewayError.invalidResponse }
    func openConversationVisit(name: String, sessionId: String) async throws -> EntitySessionState { throw GatewayError.invalidResponse }
    func guideEntityVisit(name: String, runId: String, text: String) async throws { throw GatewayError.invalidResponse }
    func guideEntityVisit(name: String, runId: String, text: String, displayText: String) async throws -> PublicUserGuidance { throw GatewayError.invalidResponse }
    func answerEntityQuestion(name: String, runId: String, wait: Wait, text: String) async throws { throw GatewayError.invalidResponse }
}
