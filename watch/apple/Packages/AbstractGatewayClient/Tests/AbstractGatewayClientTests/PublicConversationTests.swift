import Foundation
import Testing
@testable import AbstractGatewayClient

private final class ConversationWire: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var reply: (URLRequest) -> (Int, String) = { _ in (500, "") }
    nonisolated(unsafe) static var requests: [URLRequest] = []
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.requests.append(request)
        let (status, body) = Self.reply(request)
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil,
                           headerFields: ["Content-Type": "application/json"])!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(body.utf8)); client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@Suite(.serialized) struct PublicConversationTests {
    private func client() -> LiveGatewayClient {
        ConversationWire.requests = []
        let config = URLSessionConfiguration.ephemeral; config.protocolClasses = [ConversationWire.self]
        return LiveGatewayClient(baseURL: URL(string: "https://gateway.test")!, token: "test",
                                 session: URLSession(configuration: config), readTries: 1)
    }
    private func body(_ request: URLRequest) throws -> JSONValue {
        var bytes = request.httpBody ?? Data()
        if bytes.isEmpty, let stream = request.httpBodyStream {
            stream.open(); defer { stream.close() }
            var buffer = [UInt8](repeating: 0, count: 4096)
            while stream.hasBytesAvailable {
                let n = stream.read(&buffer, maxLength: buffer.count); if n <= 0 { break }
                bytes.append(contentsOf: buffer.prefix(n))
            }
        }
        return try JSONDecoder().decode(JSONValue.self, from: bytes)
    }

    @Test func onlyExplicitPublicMessageKindsBecomeSubtitles() throws {
        let data = Data(#"{"messages":[{"kind":"thinking","text":"PRIVATE"},{"kind":"answer","text":"Final"},{"kind":"tool","text":"tool stdout"},{"id":"r:public_update:1","kind":"public_update","text":"The opening hours are not confirmed yet.","run_id":"r","source_call_ids":["read-1"]}],"reasoning":"PRIVATE"}"#.utf8)
        let view = try JSONDecoder().decode(PublicConversationView.self, from: data)
        #expect(view.updates.count == 1)
        #expect(view.updates[0].text == "The opening hours are not confirmed yet.")
        #expect(view.updates[0].sourceCallIds == ["read-1"])
    }

    @Test func replyKeepsTheChosenMessageWhenANewOneArrives() {
        let chosen = PublicConversationUpdate(id: "r:public_update:1", text: "I might set the museum aside.", runId: "r")
        let newer = PublicConversationUpdate(id: "r:public_update:2", text: "I found another museum.", runId: "r")
        let reply = ConversationReply.text("Keep the first one.", to: chosen)
        #expect(reply.contains(chosen.id) && reply.contains(chosen.text))
        #expect(!reply.contains(newer.text))
        #expect(ConversationReply.text("Hello", to: nil) == "Hello")
    }

    @Test func strictQuestionMetadataPreservesDeadlineAndDoesNotCreateConsent() throws {
        let valid = #"{"id":"q1","purpose":"conversation","importance":"clarification","published_at":"2026-11-01T10:00:00+00:00","deadline":"2026-11-01T10:03:00+00:00","fallback":"Keep both options."}"#
        let question = try JSONDecoder().decode(ConversationQuestion.self, from: Data(valid.utf8))
        #expect(question.deadlineDate == ISO8601.date("2026-11-01T10:03:00+00:00"))
        #expect(question.fallback == "Keep both options.")
        for invalid in [valid.replacingOccurrences(of: "10:03:00", with: "10:06:00"),
                        valid.replacingOccurrences(of: "clarification", with: "essential"),
                        valid.replacingOccurrences(of: "Keep both options.", with: ""),
                        valid.replacingOccurrences(of: "conversation", with: "approval")] {
            #expect(throws: (any Error).self) { try JSONDecoder().decode(ConversationQuestion.self, from: Data(invalid.utf8)) }
        }
        let essential = #"{"id":"q2","purpose":"conversation","importance":"essential","published_at":"2026-11-01T10:00:00+00:00","deadline":null,"fallback":null}"#
        #expect(try JSONDecoder().decode(ConversationQuestion.self, from: Data(essential.utf8)).deadlineDate == nil)
    }

    @Test func entityPendingQuestionKeepsActualTargetRunIdentity() throws {
        let state = try JSONDecoder().decode(EntitySessionState.self, from: Data(#"{"run_id":"visit","status":"waiting","turn_n":1,"pending_wait":{"run_id":"child","reason":"user","wait_key":"question:q1","prompt":"Keep it?","choices":["Yes","No"],"details":{"question":{"id":"q1","purpose":"conversation","importance":"essential","published_at":"2026-11-01T10:00:00+00:00"}}},"public_updates":[{"id":"visit:public_update:1","text":"I found an option.","run_id":"visit"}]}"#.utf8))
        #expect(state.personWait?.runId == "child")
        #expect(state.personWait?.question?.id == "q1")
        #expect(state.publicUpdates?.first?.text == "I found an option.")
    }

    @Test func optionalTaskStartSendsStrictBoolAndLegacyShapeStaysUnchanged() async throws {
        let client = client()
        ConversationWire.reply = { _ in (200, #"{"run_id":"r"}"#) }
        _ = try await client.startConversationRun(prompt: "Plan a visit", sessionId: "s", toolPolicy: nil, tools: [], workflow: nil, primaryImage: nil)
        #expect(try body(#require(ConversationWire.requests.last))["conversation"] == .bool(true))
        _ = try await client.startRun(prompt: "Plan a visit", sessionId: "s", toolPolicy: nil, tools: [], workflow: nil, primaryImage: nil)
        #expect(try body(#require(ConversationWire.requests.last))["conversation"] == nil)
    }

    @Test func safeViewAndGuidanceUseDeclaredTaskRoutesAndRequireAcceptance() async throws {
        let client = client()
        ConversationWire.reply = { request in request.httpMethod == "GET"
            ? (200, #"{"messages":[{"kind":"public_update","id":"r:u:1","text":"I am comparing the choices.","run_id":"r"}]}"#)
            : (200, #"{"accepted":true,"seq":7}"#) }
        #expect(try await client.publicConversation(runId: "r").count == 1)
        #expect(ConversationWire.requests.last?.url?.path == "/api/gateway/runs/r/view")
        let receipt = try await client.guideRun(runId: "child", text: "Context wrapper: Keep that option.", displayText: "Keep that option.")
        #expect(receipt.clientMessageId != nil && receipt.id != "child:guidance:7" && receipt.text == "Keep that option.")
        let sent = try body(#require(ConversationWire.requests.last))
        #expect(sent["type"] == .string("inject_guidance") && sent["run_id"] == .string("child"))
        #expect(sent["payload"]?["guidance"] == .string("Context wrapper: Keep that option."))
        #expect(sent["payload"]?["display_text"] == .string("Keep that option."))
        #expect(sent["command_id"]?.stringValue == receipt.clientMessageId)
        ConversationWire.reply = { _ in (200, #"{"accepted":false}"#) }
        await #expect(throws: (any Error).self) { try await client.guideRun(runId: "r", text: "Keep it.") }
    }

    @Test func entityOptInGuidanceAndAnswerNeverUseGenericCommands() async throws {
        let client = client()
        ConversationWire.reply = { request in request.url!.path.hasSuffix("/open")
            ? (200, #"{"run_id":"v","status":"waiting","turn_n":0,"ready_for_input":true}"#)
            : (200, #"{"accepted":true,"seq":7}"#) }
        _ = try await client.openConversationVisit(name: "mira", sessionId: "s")
        #expect(ConversationWire.requests.last?.url?.path == "/api/gateway/entities/mira/visit/open")
        #expect(try body(#require(ConversationWire.requests.last))["conversation"] == .bool(true))
        let receipt = try await client.guideEntityVisit(name: "mira", runId: "v", text: "Context wrapper: Keep it.", displayText: "Keep it.")
        #expect(receipt.id == "v:guidance:7" && receipt.text == "Keep it.")
        let guidance = try body(#require(ConversationWire.requests.last))
        #expect(guidance["text"] == .string("Context wrapper: Keep it."))
        #expect(guidance["display_text"] == .string("Keep it."))
        #expect(ConversationWire.requests.last?.url?.path == "/api/gateway/entities/mira/visit/v/guidance")
        let wait = Wait(runId: "child", waitKey: "question:q1", kind: .askUser)
        try await client.answerEntityQuestion(name: "mira", runId: "v", wait: wait, text: "Yes")
        #expect(ConversationWire.requests.last?.url?.path == "/api/gateway/entities/mira/visit/v/answer")
        let answer = try body(#require(ConversationWire.requests.last))
        #expect(answer["target_run_id"] == .string("child") && answer["wait_key"] == .string("question:q1"))
        #expect(answer["response"] == .string("Yes") && answer["approved"] == nil)
        #expect(!ConversationWire.requests.contains { $0.url?.path.hasSuffix("/commands") == true })
    }

    @Test func recreatedHistoryAndReconnectRestoreAcceptedOriginalWordsWithoutDuplicates() throws {
        let wire = Data(#"{"messages":[{"id":"r:guidance:1","run_id":"r","role":"user","kind":"guidance","source":"user_guidance","guidance_status":"accepted","text":"Keep the museum."},{"id":"r:guidance:2","run_id":"r","role":"user","kind":"guidance","source":"user_guidance","guidance_status":"accepted","text":"Keep the museum."}]}"#.utf8)
        let replay = try JSONDecoder().decode(PublicConversationView.self, from: wire)
        var active = PublicGuidanceHistory()
        active.merge([try .init(runId: "r", seq: 1, text: "Keep the museum.")]) // Accepted local send.
        active.merge(replay.guidance); active.merge(replay.guidance) // Poll, reconnect and repeated page.
        #expect(active.messages.map(\.id) == ["r:guidance:1", "r:guidance:2"])
        var recreated = PublicGuidanceHistory() // All view state was discarded.
        recreated.merge(try JSONDecoder().decode(PublicConversationView.self, from: wire).guidance)
        #expect(recreated.messages == active.messages)
        #expect(recreated.messages.map(\.text) == ["Keep the museum.", "Keep the museum."])
    }

    @Test func actorEventsAndForgedProjectionCannotBecomeHumanSpeech() throws {
        let accepted: [String: Any] = ["id": "r:guidance:1", "run_id": "r", "role": "user", "kind": "guidance",
                                      "source": "user_guidance", "guidance_status": "accepted", "text": "Keep it."]
        var rows: [[String: Any]] = []
        for (key, value) in [("role", "assistant"), ("kind", "public_update"), ("source", "emit_event"),
                             ("guidance_status", "considered"), ("id", "r:guidance:01"), ("id", "other:guidance:1"), ("id", "r:guidance:0")] {
            var fake = accepted; fake[key] = value; rows.append(fake)
        }
        rows.append(["kind": "tool", "text": "PRIVATE"])
        let data = try JSONSerialization.data(withJSONObject: ["messages": rows,
            "records": [["status": "completed", "effect": ["type": "emit_event", "payload": ["name": "user_guidance", "payload": accepted]]]]])
        #expect(try JSONDecoder().decode(PublicConversationView.self, from: data).guidance.isEmpty)
    }

    @Test func entitySafePublicMessagesRestoreWithAcceptedStatusOnly() throws {
        let wire = #"{"run_id":"v","status":"waiting","turn_n":1,"public_messages":[{"id":"v:guidance:4","text":"Keep it.","run_id":"v","role":"user","kind":"guidance","guidance_status":"accepted"}]}"#
        let state = try JSONDecoder().decode(EntitySessionState.self, from: Data(wire.utf8))
        #expect(state.publicMessages?.first?.id == "v:guidance:4")
        #expect(state.publicMessages?.first?.text == "Keep it.")
        #expect(throws: (any Error).self) {
            try JSONDecoder().decode(EntitySessionState.self, from: Data(wire.replacingOccurrences(of: "accepted", with: "considered").utf8))
        }
    }

    @Test func taskRecreationReadsSafeViewRatherThanRawLedger() async throws {
        let client = client()
        ConversationWire.reply = { _ in (200, #"{"messages":[{"id":"r:guidance:3","text":"Keep it.","run_id":"r","role":"user","kind":"guidance","source":"user_guidance","guidance_status":"accepted"}]}"#) }
        let first = try await client.conversationHistory(runId: "r")
        let reopened = try await client.conversationHistory(runId: "r")
        #expect(first.guidance == reopened.guidance)
        #expect(ConversationWire.requests.allSatisfy { $0.url?.path == "/api/gateway/runs/r/view" })
    }


    @Test func commandAdmissionReconcilesOnlyByHostCommandIdentityNeverUnrelatedSequenceOrWords() throws {
        let first = try PublicUserGuidance(acceptedCommand: "command-A", runId: "r", text: "Keep it.")
        let second = try PublicUserGuidance(acceptedCommand: "command-B", runId: "r", text: "Keep it.")
        let durable = try PublicUserGuidance(runId: "r", seq: 91, text: "Keep it.", clientMessageId: "command-A")
        var active = PublicGuidanceHistory(); active.merge([first, second]); active.merge([durable]); active.merge([durable, first])
        #expect(active.messages.map(\.id) == ["r:guidance:91", "r:command:command-B"])
        let data = Data(#"{"messages":[{"id":"r:guidance:91","text":"Keep it.","run_id":"r","role":"user","kind":"guidance","source":"user_guidance","guidance_status":"accepted","client_message_id":"command-A"}]}"#.utf8)
        let replay = try JSONDecoder().decode(PublicConversationView.self, from: data)
        #expect(replay.guidance.first?.clientMessageId == "command-A")
        active.merge(replay.guidance)
        #expect(active.messages.count == 2)
    }


    private func historyRow(id: String, kind: String, role: String, source: String, seq: Int, extra: [String: JSONValue] = [:]) -> JSONValue {
        var row: [String: JSONValue] = ["id": .string("r:" + id), "run_id": .string("r"), "text": .string(id),
            "role": .string(role), "kind": .string(kind), "source": .string(source),
            "order": .array([.string("2026-11-01T10:00:00Z"), .string("r"), .number(Double(seq))])]
        row.merge(extra, uniquingKeysWith: { _, value in value }); return .object(row)
    }

    @Test func answeredExpiredAndLateRepliesRestoreInCanonicalOrderAtTheirOriginalQuestions() throws {
        let q1 = historyRow(id: "z-question", kind: "question", role: "assistant", source: "wait", seq: 1,
            extra: ["wait_key": .string("question:q1"), "question": .object(["id": .string("q1")])])
        let answer = historyRow(id: "a-answer", kind: "answer", role: "user", source: "resume", seq: 2,
            extra: ["wait_key": .string("question:q1"), "question_id": .string("q1")])
        let q2 = historyRow(id: "question-2", kind: "question", role: "assistant", source: "wait", seq: 3,
            extra: ["wait_key": .string("question:q2"), "question": .object(["id": .string("q2")])])
        let expired = historyRow(id: "expired", kind: "question_outcome", role: "system", source: "emit_event", seq: 4,
            extra: ["text": .string("No answer arrived before the deadline. Continuing with: Keep both reports."),
                    "question": .object(["id": .string("q2"), "outcome": .string("expired"), "fallback": .string("Keep both reports.")])])
        let q3 = historyRow(id: "new-question", kind: "question", role: "assistant", source: "wait", seq: 5,
            extra: ["wait_key": .string("question:q3"), "question": .object(["id": .string("q3")])])
        let late = historyRow(id: "late", kind: "retained_reply", role: "user", source: "emit_event", seq: 6,
            extra: ["question_id": .string("q2"), "reply_status": .string("retained")])
        let rows = [late, q3, answer, expired, q2, q1]
        let data = try JSONEncoder().encode(JSONValue.object(["messages": .array(rows)]))
        let replay = try JSONDecoder().decode(PublicConversationView.self, from: data)
        var active = PublicConversationHistory(); active.merge(replay.entries); active.merge(replay.entries)
        #expect(active.entries.map(\.kind) == [.question, .answer, .question, .outcome, .question, .retained])
        #expect(active.originalQuestion(for: try #require(active.entries.first { $0.kind == .answer }))?.questionId == "q1")
        #expect(active.originalQuestion(for: try #require(active.entries.last))?.questionId == "q2")
        #expect(active.entries.filter(\.isHuman).count == 2) // Expiry never invents an answer.
        #expect(active.entries[3].displayText == "No answer arrived before the deadline. Continuing with: Keep both reports.")
        #expect(active.entries.last?.displayText.contains("did not answer") == true)
        var reopened = PublicConversationHistory(); reopened.merge(replay.entries)
        #expect(reopened.entries == active.entries) // Restore is pure; there are no cue/speech callbacks.
        #expect(reopened.latestHostOutcome == nil) // A later question/reply prevents stale expiry captions.
        var atDeadline = PublicConversationHistory(); atDeadline.merge(Array(active.entries.prefix(4)))
        #expect(atDeadline.latestHostOutcome?.kind == .outcome)
    }

    @Test func mixedBriefsGuidanceAndQuestionHistoryUseServerOrderRatherThanCategoryOrID() throws {
        let update = historyRow(id: "z-update", kind: "public_update", role: "assistant", source: "emit_event", seq: 1)
        let guidance = historyRow(id: "guidance:8", kind: "guidance", role: "user", source: "user_guidance", seq: 2,
                                 extra: ["guidance_status": .string("accepted")])
        let question = historyRow(id: "a-question", kind: "question", role: "assistant", source: "wait", seq: 3,
                                 extra: ["wait_key": .string("question:q")])
        var history = PublicConversationHistory()
        history.merge(try [question, guidance, update].map { try PublicConversationEntry(row: $0) })
        #expect(history.entries.map(\.kind) == [.update, .guidance, .question])
    }

    @Test func onlyTrustedTypedQuestionRowsAndNoPrivateFencesReachPublicHistory() throws {
        let fake = historyRow(id: "fake", kind: "question_outcome", role: "assistant", source: "emit_event", seq: 1,
            extra: ["question": .object(["id": .string("q"), "outcome": .string("expired"), "fallback": .string("Keep both")])])
        let privateText = historyRow(id: "private", kind: "question", role: "assistant", source: "wait", seq: 2,
            extra: ["wait_key": .string("q"), "text": .string("<think>PRIVATE</think>")])
        let privateMetadata = historyRow(id: "private-meta", kind: "question", role: "assistant", source: "wait", seq: 3,
            extra: ["wait_key": .string("q"), "question": .object(["fallback": .string("```diary PRIVATE")])])
        let fakeAnswer = historyRow(id: "timeout-as-answer", kind: "answer", role: "system", source: "emit_event", seq: 4,
            extra: ["wait_key": .string("q")])
        let bytes = try JSONEncoder().encode(JSONValue.object(["messages": .array([fake, privateText, privateMetadata, fakeAnswer])]))
        #expect(try JSONDecoder().decode(PublicConversationView.self, from: bytes).entries.isEmpty)
    }

    @Test func omittedAndWindowedPublicHistoryIsExplicitAndCountsAreNotInvented() throws {
        let wire = #"{"run_id":"v","status":"waiting","turn_n":1,"public_updates_omitted":2,"public_messages_omitted":3,"public_questions_omitted":4,"conversation_runs_omitted":5}"#
        let state = try JSONDecoder().decode(EntitySessionState.self, from: Data(wire.utf8))
        #expect(state.omissionNotice == "Some earlier exchanges are not loaded. (2 updates, 3 replies, 4 question entries, 5 runs)")
        let view = try JSONDecoder().decode(PublicConversationView.self, from: Data(#"{"messages":[],"warnings":["run r: records before seq 6 were not folded (windowed history)"]}"#.utf8))
        #expect(view.omissions.notice == "Some earlier exchanges are not loaded.")
        #expect(try JSONDecoder().decode(PublicConversationView.self, from: Data(#"{"messages":[],"warnings":[]}"#.utf8)).omissions.notice == nil)
    }

    @Test func entityStateRestoresScreenedQuestionsAnswersAndOutcomesWithoutHomeLedger() throws {
        let question = historyRow(id: "q:question", kind: "question", role: "assistant", source: "wait", seq: 1,
            extra: ["wait_key": .string("question:q"), "question": .object(["id": .string("q")])])
        let answer = historyRow(id: "reply:answer", kind: "answer", role: "user", source: "resume", seq: 2,
            extra: ["wait_key": .string("question:q")])
        let bytes = try JSONEncoder().encode(JSONValue.object(["run_id": .string("r"), "status": .string("waiting"),
            "turn_n": .number(1), "ready_for_input": .bool(true), "public_questions": .array([question, answer])]))
        let state = try JSONDecoder().decode(EntitySessionState.self, from: bytes)
        #expect(state.publicQuestions?.count == 2)
        #expect(state.conversationEntries.map(\.kind) == [.question, .answer])
        #expect(state.personWait == nil) // History does not recreate a pending interaction.
    }

}
