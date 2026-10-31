import Foundation

/// One immutable, actually displayed revision. Seeing a request never consumes its later answer.
public struct SessionReadReceipt: Codable, Hashable, Sendable {
    public let sessionID: String
    public let runID: String
    public let status: String
    public init(sessionID: String, runID: String, status: String) {
        self.sessionID = sessionID; self.runID = runID; self.status = status
    }
    public init?(run: RunSummary) {
        guard run.isConversation, let sessionID = run.sessionId, !sessionID.isEmpty else { return nil }
        self.init(sessionID: sessionID, runID: run.runId, status: run.isTerminal ? run.status : "request")
    }
    public var isValid: Bool { !sessionID.isEmpty && !runID.isEmpty && ["request", "completed", "failed", "cancelled"].contains(status) }
    enum CodingKeys: String, CodingKey { case sessionID = "session_id", runID = "run_id", status }
}

/// Account-scoped projection of the Gateway's read log; no local first-use baseline is uploaded.
public struct SessionReadState: Sendable {
    public private(set) var loaded = false
    private var receipts: Set<SessionReadReceipt> = []
    public init() {}
    public mutating func merge(_ values: [SessionReadReceipt]) throws {
        guard values.allSatisfy(\.isValid) else { throw GatewayError.invalidResponse }
        receipts.formUnion(values); loaded = true
    }
    public func contains(_ value: SessionReadReceipt) -> Bool { receipts.contains(value) }
    public func isUnread(_ run: RunSummary) -> Bool {
        guard loaded, run.isTerminal, let receipt = SessionReadReceipt(run: run) else { return false }
        return !receipts.contains(receipt)
    }
}

struct SessionReadPage: Decodable {
    struct Event: Decodable {
        let receipt: SessionReadReceipt
        let sequence: Int
        let at: String
        let eventID: String
        enum CodingKeys: String, CodingKey { case sequence, at, eventID = "event_id" }
        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            sequence = try c.decode(Int.self, forKey: .sequence)
            at = try c.decode(String.self, forKey: .at)
            eventID = try c.decode(String.self, forKey: .eventID)
            receipt = try SessionReadReceipt(from: decoder)
        }
    }
    let items: [Event]
    let more: Bool?
    func checked() throws -> [SessionReadReceipt] {
        guard more != true, items.allSatisfy({ $0.receipt.isValid && $0.sequence > 0 && !$0.eventID.isEmpty && !$0.at.isEmpty }) else { throw GatewayError.invalidResponse }
        return items.map(\.receipt)
    }
}
