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
            : (200, #"{"accepted":true}"#) }
        #expect(try await client.publicConversation(runId: "r").count == 1)
        #expect(ConversationWire.requests.last?.url?.path == "/api/gateway/runs/r/view")
        try await client.guideRun(runId: "child", text: "Keep that option.")
        let sent = try body(#require(ConversationWire.requests.last))
        #expect(sent["type"] == .string("inject_guidance") && sent["run_id"] == .string("child"))
        #expect(sent["payload"]?["guidance"] == .string("Keep that option."))
        ConversationWire.reply = { _ in (200, #"{"accepted":false}"#) }
        await #expect(throws: (any Error).self) { try await client.guideRun(runId: "r", text: "Keep it.") }
    }

    @Test func entityOptInGuidanceAndAnswerNeverUseGenericCommands() async throws {
        let client = client()
        ConversationWire.reply = { request in request.url!.path.hasSuffix("/open")
            ? (200, #"{"run_id":"v","status":"waiting","turn_n":0,"ready_for_input":true}"#)
            : (200, #"{"accepted":true}"#) }
        _ = try await client.openConversationVisit(name: "mira", sessionId: "s")
        #expect(ConversationWire.requests.last?.url?.path == "/api/gateway/entities/mira/visit/open")
        #expect(try body(#require(ConversationWire.requests.last))["conversation"] == .bool(true))
        try await client.guideEntityVisit(name: "mira", runId: "v", text: "Keep it.")
        #expect(ConversationWire.requests.last?.url?.path == "/api/gateway/entities/mira/visit/v/guidance")
        let wait = Wait(runId: "child", waitKey: "question:q1", kind: .askUser)
        try await client.answerEntityQuestion(name: "mira", runId: "v", wait: wait, text: "Yes")
        #expect(ConversationWire.requests.last?.url?.path == "/api/gateway/entities/mira/visit/v/answer")
        let answer = try body(#require(ConversationWire.requests.last))
        #expect(answer["target_run_id"] == .string("child") && answer["wait_key"] == .string("question:q1"))
        #expect(answer["response"] == .string("Yes") && answer["approved"] == nil)
        #expect(!ConversationWire.requests.contains { $0.url?.path.hasSuffix("/commands") == true })
    }
}
