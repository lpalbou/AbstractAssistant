import Foundation
import Testing
import AbstractGatewayClient
import AssistantKit

@Suite struct ReadEmailTests {
    private func record(_ uid: String = "42", mailbox: String = "INBOX", validity: Int = 7, name: String = "read_email", status: String = "completed", success: Bool = true, outerSuccess: Bool = true, encoded: Bool = false, skipped: Bool = false) throws -> LedgerRecord {
        var output: [String: JSONValue] = ["success": .bool(success), "account": .string("default"), "mailbox": .string(mailbox), "uidvalidity": .number(Double(validity)), "uid": .string(uid), "message_id": .string("<" + uid + ">"), "from": .string("Alex <alex@example.com>"), "to": .string("me@example.com"), "cc": .array([.string("team@example.com")]), "subject": .string("Project notes"), "body_text": .string(String(repeating: "Body ", count: 11_000)), "body_html": .string("<img src='https://invalid.test/pixel'>"), "date": .string("Sun, 18 Oct 2026 14:00:00 +0000"), "attachments": .array([.object(["filename": .string("/private/project.pdf")])])]
        if skipped { output["body_text"] = .null; output["body_html"] = .null; output["body_skipped"] = .object(["cause": .string("Too large.")]) }
        let value = JSONValue.object(output)
        let call: JSONValue = .object(["name": .string(name), "runtime_call_id": .string(mailbox + uid), "arguments": .object(["uid": .string(uid)])])
        return .init(stepId: mailbox + uid, nodeId: "act", status: status, effect: .object(["type": .string("tool_calls"), "payload": .object(["tool_calls": .array([call])])]), result: .object(["results": .array([.object(["runtime_call_id": .string(mailbox + uid), "success": .bool(outerSuccess), "output": encoded ? .string(String(data: try JSONEncoder().encode(value), encoding: .utf8)!) : value])])]), endedAt: "2026-10-18T16:05:00Z")
    }
    @Test func successfulReadPreservesFieldsAndKeepsHTMLInert() throws {
        var a = RunActivity(); a.ingest(try record(encoded: true), runID: "r", cursor: 1)
        #expect(a.readEmailCount == 1 && a.sentEmailCount == 0)
        let mail = a.readEmails[0]
        #expect(mail.sender == "Alex <alex@example.com>" && mail.to == ["me@example.com"] && mail.cc == ["team@example.com"])
        #expect(mail.subject == "Project notes" && mail.readAt != nil && !mail.messageDate.isEmpty)
        #expect(mail.attachments == ["project.pdf"] && mail.body.hasSuffix("[Truncated for display]"))
        #expect(mail.html.contains("<img") && mail.bodyNotice == nil)
    }
    @Test func replayAndRepeatedReadsCountOneMessageButDifferentMailboxAndValidityStayDistinct() throws {
        var a = RunActivity()
        a.ingest(try record(), runID: "r", cursor: 1); a.ingest(try record(), runID: "r", cursor: 2)
        a.ingest(try record(), runID: "another-child", cursor: 1)
        #expect(a.readEmailCount == 1)
        a.ingest(try record(mailbox: "Archive"), runID: "r", cursor: 3)
        a.ingest(try record(validity: 8), runID: "r", cursor: 4)
        #expect(a.readEmailCount == 3)
    }
    @Test func pendingFailedListingAndSearchNeverCountAsReads() throws {
        var a = RunActivity()
        let cases = [try record(status: "waiting"), try record(success: false), try record(outerSuccess: false), try record(name: "list_emails"), try record(name: "search_emails")]
        for (i, row) in cases.enumerated() { a.ingest(row, runID: "r", cursor: i) }
        #expect(a.readEmailCount == 0 && a.readEmails.isEmpty)
    }
    @Test func skippedBodyIsExplicitAndLaterFullReadImprovesReceiptWithoutDoubleCounting() throws {
        var a = RunActivity(); a.ingest(try record(skipped: true), runID: "r", cursor: 1)
        #expect(a.readEmails[0].body.isEmpty && a.readEmails[0].bodyNotice?.contains("Only headers were read") == true)
        a.ingest(try record(), runID: "r", cursor: 2)
        #expect(a.readEmailCount == 1 && a.readEmails[0].bodyNotice == nil && !a.readEmails[0].body.isEmpty)
    }
    @Test func retainedReadLimitKeepsCumulativeCount() throws {
        var a = RunActivity()
        for i in 0..<105 { a.ingest(try record(String(i), skipped: true), runID: "r", cursor: i) }
        #expect(a.readEmailCount == 105 && a.readEmails.count == 100)
    }
    @Test func replayIsolatesSeveralReadAndSentMessages() async throws {
        let first = try await AnswerActivity.load(runID: "media-demo", client: MockGatewayClient(emailFixture: true, mediaImage: Data([1])))
        let other = try await AnswerActivity.load(runID: "media-demo", client: MockGatewayClient(mediaImage: Data([1])))
        #expect(first.activity.readEmailCount == 3 && first.activity.sentEmailCount == 3)
        #expect(other.activity.readEmailCount == 0 && other.activity.sentEmailCount == 0)
    }
}
