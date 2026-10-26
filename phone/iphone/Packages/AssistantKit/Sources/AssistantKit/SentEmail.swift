import Foundation
import AbstractGatewayClient

/// A confirmed mail-server submission, projected from the authorized tool ledger.
public struct SentEmail: Identifiable, Equatable, Sendable {
    public let id: String
    public let sender: String
    public let to: [String]
    public let cc: [String]
    public let bcc: [String]
    public let subject: String
    public let body: String
    public let html: String
    public let attachments: [String]
    public let accepted: [String]
    public let refused: [String]
    public let messageID: String
    public let sentAt: Date?
    public let isReply: Bool

    static func object(_ value: JSONValue?) -> JSONValue? {
        guard let value else { return nil }
        if value.objectValue != nil { return value }
        if let text = value.stringValue, let data = text.data(using: .utf8),
           let decoded = try? JSONDecoder().decode(JSONValue.self, from: data), decoded.objectValue != nil { return decoded }
        return nil
    }
    static func strings(_ value: JSONValue?) -> [String] {
        if case .array(let values) = value { return values.compactMap(\.stringValue).filter { !$0.isEmpty } }
        if let text = value?.stringValue, !text.isEmpty { return [text] }
        return []
    }
    static func bounded(_ text: String) -> String {
        text.count > 50_000 ? String(text.prefix(50_000)) + "\n[Truncated for display]" : text
    }
    static func confirmed(key: String, name: String, arguments: JSONValue?, result: JSONValue?, timestamp: Date?) -> SentEmail? {
        guard result?["success"] != .bool(false), result?["error"]?.stringValue?.isEmpty != false,
              let output = object(result?["output"]), output["success"] == .bool(true) else { return nil }
        let messageID = output["message_id"]?.stringValue ?? ""
        let accepted = strings(output["accepted"])
        guard !messageID.isEmpty || !accepted.isEmpty else { return nil }
        func addresses(_ field: String) -> [String] { strings(output[field] ?? arguments?[field]) }
        let attachmentNames = strings(arguments?["attachments"]).map { ($0 as NSString).lastPathComponent }
        return SentEmail(id: messageID.isEmpty ? key : "message:" + messageID,
            sender: output["from"]?.stringValue ?? "", to: addresses("to"), cc: addresses("cc"), bcc: addresses("bcc"),
            subject: output["subject"]?.stringValue ?? arguments?["subject"]?.stringValue ?? "",
            body: bounded(arguments?["body_text"]?.stringValue ?? ""), html: bounded(arguments?["body_html"]?.stringValue ?? ""),
            attachments: attachmentNames, accepted: accepted, refused: output["refused"]?.objectValue?.keys.sorted() ?? [],
            messageID: messageID, sentAt: timestamp, isReply: name == "reply_email")
    }
}
