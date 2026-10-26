import Foundation
import Testing
import PhoneGatewayClient
import AssistantKit

@Suite struct CycleTimelineTests {
    private func record(_ json: String) throws -> LedgerRecord { try JSONDecoder().decode(LedgerRecord.self, from: Data(json.utf8)) }
    @Test func lanesStaySeparateAndLateToolCompletionKeepsOriginalCycleAndInput() throws {
        var activity = RunActivity()
        let reason = try record(#"{"step_id":"one","node_id":"REASON","status":"completed","effect":{"type":"llm_call"}}"#)
        activity.ingest(reason, runID: "agent-a", cursor: 1); activity.ingest(reason, runID: "agent-b", cursor: 1)
        activity.ingest(try record(#"{"step_id":"tool","status":"started","effect":{"type":"tool_calls","payload":{"tool_calls":[{"name":"read_file","call_id":"0","runtime_call_id":"a","arguments":{"file_path":"notes.md"}}]}}}"#), runID: "agent-a", cursor: 2)
        activity.ingest(try record(#"{"step_id":"tool","status":"started","effect":{"type":"tool_calls","payload":{"tool_calls":[{"name":"read_file","call_id":"0","runtime_call_id":"b","arguments":{}}]}}}"#), runID: "agent-b", cursor: 2)
        activity.ingest(try record(#"{"step_id":"wait","status":"waiting","result":{"wait":{"reason":"user","wait_key":"tool_approval:a"}}}"#), runID: "agent-a", cursor: 3)
        activity.ingest(try record(#"{"step_id":"two","node_id":"reason","status":"completed","effect":{"type":"llm_call"}}"#), runID: "agent-a", cursor: 4)
        activity.ingest(try record(#"{"step_id":"resumed-tool","status":"completed","effect":{"type":"tool_calls","payload":{"tool_calls":[{"name":"read_file","runtime_call_id":"a"}]}},"result":{"results":[{"runtime_call_id":"a","output":"Public file text"}]}}"#), runID: "agent-a", cursor: 5)
        #expect(activity.cycleLanes.count == 2 && activity.toolCalls == 2)
        let lane = try #require(activity.cycleLanes.first { $0.id == "agent-a" })
        #expect(lane.cycles.count == 2 && lane.cycles[0].tools.count == 1 && lane.cycles[1].tools.isEmpty)
        #expect(lane.cycles[0].tools[0].inputText?.contains("notes.md") == true)
        #expect(lane.cycles[0].tools[0].detail == "Public file text")
        #expect(lane.cycles[0].approvals.count == 1 && lane.cycles[0].approvals[0].isToolApproval)
        #expect(activity.cycleLanes.first { $0.id == "agent-b" }?.cycles[0].tools[0].inputText != nil)
    }
    @Test func orphanAndTrimmedCycleCallsRemainVisibleWithoutInventingCycles() throws {
        var activity = RunActivity()
        activity.ingest(try record(#"{"step_id":"t","status":"completed","effect":{"type":"tool_calls","payload":{"tool_calls":[{"name":"read_file","runtime_call_id":"unassigned"}]}}}"#), runID: "r", cursor: 1)
        #expect(activity.cycleLanes.isEmpty && activity.toolsOutsideRecordedCycles.count == 1)
        activity.ingest(try record(#"{"step_id":"reason","node_id":"reason","status":"completed","effect":{"type":"llm_call"}}"#), runID: "r", cursor: 2)
        activity.ingest(try record(#"{"step_id":"failed","status":"completed","effect":{"type":"tool_calls","payload":{"tool_calls":[{"name":"fetch_url","runtime_call_id":"failed"}]}},"result":{"results":[{"runtime_call_id":"failed","success":false,"error":"Unavailable"}]}}"#), runID: "r", cursor: 3)
        for n in 4..<260 {
            activity.ingest(.init(stepId: "m\(n)", nodeId: "route_call", status: "completed", effect: .object(["type": .string("llm_call")])), runID: "r", cursor: n)
        }
        #expect(activity.wasTrimmed && activity.cycleLanes.isEmpty)
        #expect(activity.toolsOutsideRecordedCycles.contains { $0.toolName == "fetch_url" })
    }
    @Test func toolArgumentsAreStructuredRedactedAndBoundedBeforeDisplay() throws {
        let args = try JSONDecoder().decode(JSONValue.self, from: Data(#"{"file_path":"notes.md","Authorization":"bearer private-a","nested":[{"apiKey":"private-b","access_token":"private-c","client_secret":"private-d","imap_password":"private-e","Cookie":"private-f"}],"content":"public"}"#.utf8))
        let text = try #require(ToolCallInput.display(args))
        #expect(text.contains("notes.md") && text.contains("public") && text.contains("[Hidden]"))
        #expect(!text.contains("private-"))
        #expect(ToolCallInput.display(.string(args.displayText)) == text)
        #expect(ToolCallInput.display(.string("Authorization=do-not-show")) == nil)
        #expect(ToolCallInput.display(nil) == nil && ToolCallInput.display(.object([:])) != nil)
        let large = try #require(ToolCallInput.display(.object(["password": .string(String(repeating: "secret", count: 1000)), "content": .string(String(repeating: "x", count: 5000))])))
        #expect(large.count == 4000 && large.hasSuffix("[Truncated for display]"))
        #expect(!large.contains("secretsecret"))
    }
    @Test func firstSeenUnassignedToolIsNotMovedIntoALaterReasonCycle() throws {
        var activity = RunActivity()
        let tool = try record(#"{"step_id":"a","status":"started","effect":{"type":"tool_calls","payload":{"tool_calls":[{"name":"read_file","runtime_call_id":"one"}]}}}"#)
        activity.ingest(tool, runID: "r", cursor: 1)
        activity.ingest(try record(#"{"step_id":"reason","node_id":"reason","status":"completed","effect":{"type":"llm_call"}}"#), runID: "r", cursor: 2)
        var done = tool; done.status = "completed"
        activity.ingest(done, runID: "r", cursor: 3)
        #expect(activity.toolsOutsideRecordedCycles.count == 1 && activity.cycleLanes[0].cycles[0].tools.isEmpty)
    }
    @Test func retentionPreservesActualCycleNumbersAndDoesNotReassignEvictedCalls() throws {
        var activity = RunActivity()
        for n in 1...260 {
            activity.ingest(.init(stepId: "c\(n)", nodeId: "reason", status: "completed", effect: .object(["type": .string("llm_call")])), runID: "r", cursor: n)
        }
        #expect(activity.cycleLanes[0].cycles.first?.model.cycleOrdinal == 11)
        #expect(activity.cycleLanes[0].cycles.last?.model.cycleOrdinal == 260)
        var calls = RunActivity()
        let tool = try record(#"{"step_id":"tool","status":"completed","effect":{"type":"tool_calls","payload":{"tool_calls":[{"name":"read_file","runtime_call_id":"old"}]}}}"#)
        calls.ingest(tool, runID: "r", cursor: 1)
        for n in 2...260 { calls.ingest(.init(stepId: "c\(n)", nodeId: "reason", status: "completed", effect: .object(["type": .string("llm_call")])), runID: "r", cursor: n) }
        calls.ingest(tool, runID: "r", cursor: 261)
        #expect(calls.toolCalls == 1 && calls.toolsOutsideRecordedCycles.count == 1)
    }

}
