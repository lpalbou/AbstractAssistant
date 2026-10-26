import Foundation
import Testing
@testable import PhoneGatewayClient

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
    #expect(t.hasSuffix("…") && t.count <= 45 && !t.contains("this morning"))
}

@Test func askRunsCarryTheAssistantPersonaAndMetricsDecode() throws {
    let obj = try JSONSerialization.jsonObject(with: JSONEncoder().encode(StartRunRequest(prompt: "hi", sessionId: "s"))) as! [String: Any]
    #expect(((obj["input_data"] as! [String: Any])["system"] as? String)?.contains("You are AbstractAssistant") == true)
    let row = try JSONDecoder().decode(RunSummary.self, from: Data(#"{"run_id":"r","status":"completed","session_id":"s","steps":12,"llm_calls":3,"tool_calls":2,"tokens_total":8244,"session_kind":"chat"}"#.utf8))
    #expect(row.toolCalls == 2 && row.llmCalls == 3 && row.sessionKind == "chat")
    let input = try JSONDecoder().decode(RunInputData.self, from: Data(#"{"run_id":"r","input_data":{"prompt":"What is AbstractFramework?","use_session_history":true}}"#.utf8))
    #expect(input.inputData?.prompt == "What is AbstractFramework?")
}
