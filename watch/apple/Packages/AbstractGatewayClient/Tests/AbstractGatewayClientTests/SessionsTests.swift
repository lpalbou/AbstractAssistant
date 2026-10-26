import Foundation
import Testing
@testable import AbstractGatewayClient

@Test func turnsGroupIntoSessionsNewestFirst() {
    func r(_ id: String, _ s: String, _ status: String, tools: Int) -> RunSummary {
        var x = RunSummary(runId: id, workflowId: "basic-agent@0.0.5", status: status, sessionId: s); x.toolCalls = tools; x.llmCalls = 1; return x
    }
    let sessions = SessionSummary.group([r("c", "s2", "waiting", tools: 1), r("b", "s1", "completed", tools: 2), r("a", "s2", "completed", tools: 3)])
    #expect(sessions.map(\.id) == ["s2", "s1"])
    #expect(sessions[0].turns == 2 && sessions[0].toolCalls == 4 && sessions[0].firstRunId == "a" && sessions[0].latest.runId == "c")
}

@Test func sessionTitlesAreTheFirstLineCutAtAWord() {
    #expect(SessionSummary.title(fromPrompt: "Did the QC pass?\nmore") == "Did the QC pass?")
    let t = SessionSummary.title(fromPrompt: "Compare overall survival by treatment arm in the ADTTE dataset I sent you this morning")
    #expect(t.hasSuffix("…") && t.count <= 61 && !t.contains("this morning"))
    // Long enough to tell sessions apart that start alike (32 characters merged them).
    #expect(SessionSummary.title(fromPrompt: "In one sentence: what is your name and who built you?") == "In one sentence: what is your name and who built you?")
}

/// The listing is ordered by last update: a turn answered late must not become the session's
/// newest, nor title it. Grouping goes by creation time.
@Test func sessionsGoByCreationTimeNotLastUpdate() {
    func r(_ id: String, created: String) -> RunSummary {
        var x = RunSummary(runId: id, workflowId: "w", status: "completed", sessionId: "s"); x.createdAt = created; return x
    }
    // Listed newest-updated first: "old" (created first, updated last) comes first.
    let s = SessionSummary.group([r("old", created: "2026-10-17T01:00:00Z"), r("new", created: "2026-10-17T03:00:00Z"), r("mid", created: "2026-10-17T02:00:00Z")])
    #expect(s[0].latest.runId == "new" && s[0].firstRunId == "old")
}

@Test func askRunsCarryTheAssistantPersonaAndMetricsDecode() throws {
    let obj = try JSONSerialization.jsonObject(with: JSONEncoder().encode(StartRunRequest(prompt: "hi", sessionId: "s", system: AssistantPersona.watch))) as! [String: Any]
    #expect(((obj["input_data"] as! [String: Any])["system"] as? String)?.contains("You are AbstractAssistant") == true)
    let row = try JSONDecoder().decode(RunSummary.self, from: Data(#"{"run_id":"r","status":"completed","session_id":"s","steps":12,"llm_calls":3,"tool_calls":2,"tokens_total":8244,"session_kind":"chat"}"#.utf8))
    #expect(row.toolCalls == 2 && row.llmCalls == 3 && row.sessionKind == "chat")
    let input = try JSONDecoder().decode(RunInputData.self, from: Data(#"{"run_id":"r","input_data":{"prompt":"What is AbstractFramework?","use_session_history":true}}"#.utf8))
    #expect(input.inputData?.prompt == "What is AbstractFramework?")
}

/// The live `history_bundle` shape (public gateway, 2026-10-17): `session.turns` beside many other
/// keys; a turn's answer can be null, and keys the watch does not read are ignored.
@Test func sessionHistoryReadsTheBundlesTurns() throws {
    let json = """
    {"version": 1, "run": {"run_id": "r3"}, "ledgers": {}, "session": {"session_id": "s", "turns": [
      {"run_id": "r2", "created_at": "2026-10-17T17:45:29Z", "prompt": "Second", "answer": null, "status": "running",
       "answer_meta": {"tools": [1, 2]}, "stats": {"tokens": 3}},
      {"run_id": "r1", "created_at": "2026-10-17T01:14:06Z", "prompt": "In one sentence: what is the tallest mountain on Earth?",
       "answer": "Mount Everest.", "status": "completed", "attachments": []}
    ]}, "warnings": []}
    """
    let turns = try JSONDecoder().decode(HistoryBundle.self, from: Data(json.utf8)).session?.turns ?? []
    #expect(turns.map(\.runId) == ["r2", "r1"])
    #expect(turns[0].answer == nil && turns[0].status == "running")
    #expect(turns[1].prompt == "In one sentence: what is the tallest mountain on Earth?")
    #expect(turns[1].answer == "Mount Everest.")
}

@Test func aSessionIsNewUntilItsLatestAnswerIsSeen() {
    func run(_ id: String, _ status: String, minutesAgo: Double) -> RunSummary {
        let at = ISO8601DateFormatter().string(from: Date().addingTimeInterval(-minutesAgo * 60))
        return RunSummary(runId: id, workflowId: nil, status: status, sessionId: "s", createdAt: at, updatedAt: at)
    }
    let since = Date().addingTimeInterval(-3600)
    let answered = SessionSummary.group([run("r2", "completed", minutesAgo: 5), run("r1", "completed", minutesAgo: 30)])[0]
    #expect(answered.isNew(seen: [:], since: since))
    #expect(!answered.isNew(seen: ["s": "r2"], since: since))           // its latest answer was seen
    #expect(answered.isNew(seen: ["s": "r1"], since: since))            // an older one was
    #expect(!answered.isNew(seen: [:], since: Date()))                  // before this watch counted
    #expect(!SessionSummary.group([run("r3", "running", minutesAgo: 1)])[0].isNew(seen: [:], since: since))   // still working
}

@Test func aSearchPageDecodesTheGatewaysShape() throws {
    let json = #"""
    {"query": "survival", "count": 1, "fuzzy": true, "indexing": {"complete": false, "pending_sessions": 3, "turns": 120},
                 "items": [{"session_id": "s-km", "run_id": "r1", "prompt": "Compare overall survival", "snippet": "Compare overall survival by arm",
                            "matched_in": "question", "highlights": [[16, 8]], "score": 3.2, "created_at": null, "updated_at": "2026-10-18T10:01:00+00:00",
                            "session_kind": "chat", "archived": false, "fuzzy": false}]}
    """#
    let page = try JSONDecoder().decode(SessionSearchPage.self, from: Data(json.utf8))
    #expect(page.items.map(\.sessionId) == ["s-km"] && page.items[0].highlights == [[16, 8]] && page.partial)
}

@Test func theMockFindsWordsInQuestionsAndAnswers() async throws {
    let mock = MockGatewayClient(world: .watch)
    #expect(try await mock.searchSessions("assay QC", limit: 10).items.map(\.sessionId) == ["s-qc"])
    #expect(try await mock.searchSessions("arm B", limit: 10).items.first?.sessionId == "s-adtte")
    #expect(try await mock.searchSessions("nothing like this", limit: 10).items.isEmpty)
}

@Test func aHitOnAnImageCarriesItAsMedia() throws {
    let json = #"""
    {"items": [{"session_id": "s", "run_id": "t1", "prompt": "Draw", "snippet": "A red apple", "matched_in": "artifact", "highlights": [[6, 5]],
                "artifact": {"artifact_id": "d0c9a50ce4a51cb207e8c3e0a430cc06", "run_id": "t1", "kind": "image", "content_type": "image/png",
                             "name": null, "prompt": "A red apple"}},
               {"session_id": "s2", "run_id": "t2", "prompt": "Read", "snippet": "budget.pdf", "matched_in": "artifact", "highlights": [],
                "artifact": {"artifact_id": "a2", "run_id": "session_memory_s2", "kind": "attachment", "content_type": "application/pdf", "name": "budget.pdf"}}],
     "indexing": {"complete": true}}
    """#
    let page = try JSONDecoder().decode(SessionSearchPage.self, from: Data(json.utf8))
    #expect(page.items[0].media?.kind == .image && page.items[0].media?.runId == "t1")
    #expect(page.items[1].media == nil && page.items[1].artifactName == "budget.pdf")
}
