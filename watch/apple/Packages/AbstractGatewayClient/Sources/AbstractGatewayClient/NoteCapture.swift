import Foundation

/// AbstractNote capture contract; deliberately independent from Assistant chat workflows.
public struct NoteCaptureRequest: Encodable, Sendable {
    public let text: String
    public let sessionID: String
    public let idempotencyKey: String
    public let occurredAt: Date
    public init(text: String, sessionID: String = "note-watch-" + UUID().uuidString.lowercased(),
                idempotencyKey: String = UUID().uuidString.lowercased(), occurredAt: Date = Date()) {
        self.text = text; self.sessionID = sessionID; self.idempotencyKey = idempotencyKey; self.occurredAt = occurredAt
    }
    enum CodingKeys: String, CodingKey { case bundle_id, flow_id, session_id, input_data }
    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode("abstractnote", forKey: .bundle_id)
        try c.encode("note-capture", forKey: .flow_id)
        try c.encode(sessionID, forKey: .session_id)
        try c.encode(["text": JSONValue.string(text), "session_id": .string(sessionID),
                      "idempotency_key": .string(idempotencyKey), "process_inline": .bool(false),
                      "occurred_at": .string(ISO8601DateFormatter().string(from: occurredAt)),
                      "source": .object(["client": .string("watch")])], forKey: .input_data)
    }
}

public enum NoteCaptureOutcome: Equatable, Sendable {
    case pending, needsApproval, saved(String), failed(String)
    public init(_ run: RunSummary) {
        if run.status == "completed" {
            if run.output?["success"] == .bool(false) {
                self = .failed(run.output?["error"]?.stringValue ?? run.output?["response"]?.stringValue ?? "The note wasn’t saved. Try again.")
            } else if let id = run.output?["note_id"]?.stringValue, !id.isEmpty {
                self = .saved(id)
            } else {
                self = .failed("The gateway didn’t confirm a saved note. Try again.")
            }
        } else if run.isTerminal {
            self = .failed("The note wasn’t saved. Try again.")
        } else if run.waitsOnPerson {
            self = .needsApproval
        } else { self = .pending }
    }
}
