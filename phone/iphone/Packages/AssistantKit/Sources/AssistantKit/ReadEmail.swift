import Foundation
import AbstractGatewayClient

/// A message opened by read_email, rather than an inbox/search result or mailbox Seen flag.
public struct ReadEmail: Identifiable, Equatable, Sendable {
    public let id: String
    public let sender: String
    public let to: [String]
    public let cc: [String]
    public let subject: String
    public let body: String
    public let html: String
    public let attachments: [String]
    public let messageID: String
    public let messageDate: String
    public let readAt: Date?
    public let bodyNotice: String?

    static func confirmed(arguments: JSONValue?, result: JSONValue?, timestamp: Date?) -> ReadEmail? {
        guard result?["success"] != .bool(false), result?["error"]?.stringValue?.isEmpty != false,
              let output = SentEmail.object(result?["output"]), output["success"] == .bool(true) else { return nil }
        let messageID = output["message_id"]?.stringValue ?? ""
        let uid = output["uid"]?.stringValue ?? arguments?["uid"]?.stringValue ?? ""
        guard !uid.isEmpty || !messageID.isEmpty else { return nil }
        let account = output["account"]?.stringValue ?? arguments?["account"]?.stringValue ?? "default"
        let mailbox = output["mailbox"]?.stringValue ?? arguments?["mailbox"]?.stringValue ?? ""
        let validity = output["uidvalidity"].flatMap { $0 == .null ? nil : $0.displayText } ?? ""
        // JSON-array identity avoids delimiter collisions in mailbox/account names.
        let parts = uid.isEmpty ? [account, "message", messageID] : [account, mailbox, validity, uid]
        let id = (try? JSONEncoder().encode(parts)).map { String(decoding: $0, as: UTF8.self) } ?? parts.description
        var attachments: [String] = []
        if case .array(let values) = output["attachments"] {
            attachments = values.compactMap { $0["filename"]?.stringValue }.map { ($0 as NSString).lastPathComponent }
        }
        let skipped = output["body_skipped"]
        let bodyNotice: String? = skipped == nil || skipped == .null ? nil :
            "Only headers were read. " + (skipped?["cause"]?.stringValue ?? "The message body exceeded the gateway’s reading limit.")
        return ReadEmail(id: id, sender: output["from"]?.stringValue ?? output["from_address"]?.stringValue ?? "",
            to: SentEmail.strings(output["to"]), cc: SentEmail.strings(output["cc"]),
            subject: output["subject"]?.stringValue ?? "", body: SentEmail.bounded(output["body_text"]?.stringValue ?? ""),
            html: SentEmail.bounded(output["body_html"]?.stringValue ?? ""), attachments: attachments,
            messageID: messageID, messageDate: output["date"]?.stringValue ?? "", readAt: timestamp, bodyNotice: bodyNotice)
    }
}
