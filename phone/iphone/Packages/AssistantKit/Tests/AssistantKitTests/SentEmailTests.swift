import Foundation
import Testing
import PhoneGatewayClient
@testable import AssistantKit

@Suite struct SentEmailTests {
    private func record(_ id: String = "mail", name: String = "send_email", status: String = "completed", output: JSONValue? = nil, outerSuccess: Bool = true, body: String? = "Hello Alex") -> LedgerRecord {
        var args: [String: JSONValue] = ["subject": .string("Summary"), "to": .array([.string("alex@example.com")]), "headers": .object(["Authorization": .string("NEVER RETAIN")])]
        if let body { args["body_text"] = .string(body) }
        let call: JSONValue = .object(["name": .string(name), "runtime_call_id": .string(id), "call_id": .string("0"), "arguments": .object(args)])
        let out = output ?? .object(["success": .bool(true), "message_id": .string("<" + id + ">"), "from": .string("me@example.com"), "to": .array([.string("alex@example.com")]), "subject": .string("Summary"), "accepted": .array([.string("alex@example.com")])])
        return .init(stepId: id, nodeId: "act", status: status,
            effect: .object(["type": .string("tool_calls"), "payload": .object(["tool_calls": .array([call])])]),
            result: .object(["results": .array([.object(["runtime_call_id": .string(id), "success": .bool(outerSuccess), "output": out])])]), endedAt: "2026-10-18T16:05:00Z")
    }
    @Test func completedSubmissionKeepsReceiptFieldsAndDoesNotPutBodyInGenericActivity() {
        var a = RunActivity(); a.ingest(record(), runID: "r", cursor: 1)
        #expect(a.sentEmailCount == 1)
        let mail = a.sentEmails[0]
        #expect(mail.sender == "me@example.com" && mail.to == ["alex@example.com"])
        #expect(mail.subject == "Summary" && mail.body == "Hello Alex" && mail.sentAt != nil)
        #expect(mail.messageID == "<mail>" && !mail.isReply)
        #expect(!a.items[0].detail.contains("Hello Alex") && !a.items[0].detail.contains("NEVER RETAIN"))
    }
    @Test func waitingDeniedFailedAndUnconfirmedOutputsNeverCount() {
        var a = RunActivity()
        let cases = [record("pending", status: "waiting"), record("failed", outerSuccess: false), record("inner-failed", output: .object(["success": .bool(false), "message_id": .string("fake")])), record("empty", output: .object(["success": .bool(true)])), record("generic", name: "read_email")]
        for (i, r) in cases.enumerated() { a.ingest(r, runID: "r", cursor: i) }
        a.finish(status: "completed")
        #expect(a.sentEmailCount == 0 && a.sentEmails.isEmpty)
    }
    @Test func repeatedLedgerRowsAndDuplicateMessageIDsDoNotDuplicateReceipt() {
        var a = RunActivity()
        a.ingest(record(), runID: "r", cursor: 1); a.ingest(record(), runID: "r", cursor: 1)
        a.ingest(record(), runID: "r", cursor: 2); a.ingest(record(), runID: "another-child", cursor: 1)
        #expect(a.sentEmailCount == 1 && a.sentEmails.count == 1 && a.sentEmails[0].body == "Hello Alex")
    }
    @Test func approvalCompletionCanRecoverBodyFromEarlierCall() {
        var a = RunActivity(); a.ingest(record(status: "waiting"), runID: "r", cursor: 1)
        var done = record(body: nil)
        done.effect = .object(["type": .string("tool_calls"), "payload": .object(["tool_calls": .array([.object(["name": .string("send_email"), "runtime_call_id": .string("mail"), "arguments": .object(["subject": .string("Summary")])])])])])
        a.ingest(done, runID: "r", cursor: 2)
        #expect(a.sentEmails.first?.body == "Hello Alex")
    }
    @Test func stringEncodedResultAndReplyUseComputedRecipientsAndSubject() {
        let output = #"{"success":true,"message_id":"<reply>","from":"me@example.com","to":["reply-to@example.com"],"cc":["cc@example.com"],"bcc":["bcc@example.com"],"subject":"Re: Computed","accepted":["reply-to@example.com"],"refused":{"cc@example.com":[550,"Refused"]}}"#
        var a = RunActivity(); a.ingest(record(name: "reply_email", output: .string(output)), runID: "r", cursor: 1)
        #expect(a.sentEmails.first?.isReply == true && a.sentEmails.first?.subject == "Re: Computed")
        #expect(a.sentEmails.first?.to == ["reply-to@example.com"] && a.sentEmails.first?.refused == ["cc@example.com"])
        #expect(a.sentEmails.first?.cc == ["cc@example.com"] && a.sentEmails.first?.bcc == ["bcc@example.com"])
    }
    @Test func conflictingRuntimeIdentityCannotAttachAnUnrelatedSuccess() {
        var a = RunActivity(); var r = record()
        r.result = .object(["results": .array([.object(["runtime_call_id": .string("other-call"), "call_id": .string("0"), "success": .bool(true), "output": .object(["success": .bool(true), "message_id": .string("<other>")])])])])
        a.ingest(r, runID: "r", cursor: 1)
        #expect(a.sentEmailCount == 0)
    }
    @Test func newAnswerStartsWithoutEarlierReceiptsAndLargeBodiesAreExplicitlyBounded() {
        var first = RunActivity(); first.ingest(record(body: String(repeating: "x", count: 60_000)), runID: "r", cursor: 1)
        let second = RunActivity()
        #expect(second.sentEmailCount == 0 && second.sentEmails.isEmpty)
        #expect(first.sentEmails[0].body.hasSuffix("[Truncated for display]"))
    }
    @Test func restoredReceiptsStayWithTheirAnswer() async throws {
        let withMail = MockGatewayClient(emailFixture: true, mediaImage: Data([1]))
        let sent = try await AnswerActivity.load(runID: "media-demo", client: withMail)
        let other = try await AnswerActivity.load(runID: "media-demo", client: MockGatewayClient(mediaImage: Data([1])))
        #expect(sent.activity.sentEmailCount == 3 && sent.issues.isEmpty)
        #expect(other.activity.sentEmailCount == 0 && other.activity.sentEmails.isEmpty)
    }
    @Test func htmlOnlyAndAttachmentsRemainInertSourceAndBasenames() throws {
        var a = RunActivity(); var r = record(body: nil)
        let args: JSONValue = .object(["body_html": .string("<p>Hello</p><img src='https://example.invalid/tracker'>"), "attachments": .array([.string("/private/workspace/summary.pdf")])])
        let encoded = String(data: try JSONEncoder().encode(args), encoding: .utf8)!
        r.effect = .object(["type": .string("tool_calls"), "payload": .object(["tool_calls": .array([.object(["name": .string("send_email"), "runtime_call_id": .string("mail"), "arguments": .string(encoded)])])])])
        a.ingest(r, runID: "r", cursor: 1)
        #expect(a.sentEmails[0].body.isEmpty && a.sentEmails[0].html.contains("<p>Hello</p>"))
        #expect(a.sentEmails[0].attachments == ["summary.pdf"])
    }
    @Test func retainedReceiptLimitDoesNotLoseTheConfirmedCount() {
        var a = RunActivity()
        for i in 0..<105 { a.ingest(record("m\(i)"), runID: "r", cursor: i) }
        #expect(a.sentEmailCount == 105 && a.sentEmails.count == 100)
    }
}
