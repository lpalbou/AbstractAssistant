import Foundation
import Testing
import AbstractGatewayClient
import AssistantKit

@Suite struct RunActivityTests {
    private func record(_ json: String) throws -> LedgerRecord {
        try JSONDecoder().decode(LedgerRecord.self, from: Data(json.utf8))
    }
    @Test func legacyEntityReasonNodeCountsAsACycle() throws {
        var activity = RunActivity()
        let item = try record(#"{"step_id":"legacy","node_id":"REASON","status":"completed","effect":{"type":"llm_call"},"result":{"content":"not rendered"}}"#)
        activity.ingest(item, runID: "visit", cursor: 1)
        #expect(activity.cycleCount == 1 && activity.modelCalls == 1)
        #expect(activity.items.first?.title == "Agent cycle")
        #expect(activity.items.first?.detail.isEmpty == true)
    }
    @Test func modelCyclesCountOnceAndNeverExposePromptsOrReasoning() throws {
        var activity = RunActivity()
        let started = try record(#"{"step_id":"s","node_id":"reason","status":"started","started_at":"2026-10-18T12:00:00Z","effect":{"type":"llm_call","payload":{"messages":[{"content":"PRIVATE PROMPT"}],"system":"PRIVATE SYSTEM"}}}"#)
        let finished = try record(#"{"step_id":"s","node_id":"reason","status":"completed","effect":{"type":"llm_call"},"result":{"content":"model content","reasoning":"PRIVATE THOUGHT"}}"#)
        activity.ingest(started, runID: "child", cursor: 0)
        activity.ingest(started, runID: "child", cursor: 0)
        activity.ingest(finished, runID: "child", cursor: 1)
        #expect(activity.modelCalls == 1 && activity.cycleCount == 1)
        #expect(activity.items.count == 1 && activity.items[0].status == .completed)
        #expect(activity.items[0].detail.isEmpty && activity.lastEventAt != nil)
        activity.ingest(started, runID: "another-child", cursor: 0)
        #expect(activity.modelCalls == 2)
    }
    @Test func toolResultsPairByRuntimeIdentityAcrossApprovalAndRepeatedModelIDs() throws {
        var activity = RunActivity()
        let start = try record(#"{"step_id":"a","status":"started","effect":{"type":"tool_calls","payload":{"tool_calls":[{"name":"web_search","call_id":"0","runtime_call_id":"one","arguments":{"private":"NEVER SHOW"}}]}}}"#)
        let finish = try record(#"{"step_id":"after-approval","status":"completed","effect":{"type":"tool_calls","payload":{"tool_calls":[{"name":"web_search","call_id":"0","runtime_call_id":"one"}]}},"result":{"results":[{"runtime_call_id":"one","success":true,"output":{"rendered":"Found source https://example.com"}}]}}"#)
        let secondCall = try record(#"{"step_id":"next","status":"completed","effect":{"type":"tool_calls","payload":{"tool_calls":[{"name":"web_search","call_id":"0","runtime_call_id":"two"}]}},"result":{"results":[{"runtime_call_id":"two","success":false,"error":"Search unavailable"}]}}"#)
        activity.ingest(start, runID: "r", cursor: 0)
        activity.ingest(finish, runID: "r", cursor: 1)
        activity.ingest(secondCall, runID: "r", cursor: 2)
        #expect(activity.toolCalls == 2 && activity.items.count == 2)
        #expect(activity.items[0].detail == "Found source https://example.com")
        #expect(activity.items[0].status == .completed)
        #expect(activity.items[1].status == .failed && activity.items[1].detail == "Search unavailable")
    }
    @Test func legacyRepeatedIDsAcrossStepsStaySeparateAndResumeIsHidden() throws {
        var activity = RunActivity()
        for (cursor, step) in ["a", "b"].enumerated() {
            let item = try record("""
            {"step_id":"\(step)","status":"completed","effect":{"type":"tool_calls","payload":{"tool_calls":[{"name":"list_files","call_id":"0"}]}},"result":{"results":[{"success":true,"output":"files"}]}}
            """)
            activity.ingest(item, runID: "r", cursor: cursor)
        }
        activity.ingest(try record(#"{"status":"completed","effect":{"type":"resume"},"result":{"resumed":true}}"#), runID: "r", cursor: 2)
        #expect(activity.toolCalls == 2 && activity.items.count == 2)
    }
    @Test func waitsAndFailuresKeepOnlyPublicDetails() throws {
        var activity = RunActivity()
        activity.ingest(try record(#"{"step_id":"w","status":"waiting","result":{"wait":{"reason":"user","wait_key":"tool_approval:r:act:a","prompt":"Allow this action?","details":{"tool_calls":[{"arguments":{"token":"SECRET"}}]}}}}"#), runID: "r", cursor: 0)
        #expect(activity.items[0].kind == .wait && activity.items[0].title == "Approval needed")
        #expect(activity.items[0].detail == "Allow this action?")
        activity.ingest(try record(#"{"step_id":"f","status":"failed","error":"Provider disconnected"}"#), runID: "r", cursor: 1)
        #expect(activity.items.last?.detail == "Provider disconnected")
        #expect(activity.items.last?.kind == .failure)
    }
    @Test func retainedRowsAndTextAreBoundedButCountersStayCumulative() {
        var activity = RunActivity()
        let large = String(repeating: "x", count: 5000)
        for i in 0..<260 {
            activity.ingest(.init(stepId: "s\(i)", nodeId: "act", status: "completed",
                effect: .object(["type": .string("tool_calls"), "payload": .object(["tool_calls": .array([.object(["name": .string("read_file")])])])]),
                result: .object(["results": .array([.object(["output": .string(large)])])])), runID: "r", cursor: i)
        }
        #expect(activity.toolCalls == 260 && activity.items.count == 250 && activity.wasTrimmed)
        #expect(activity.items.last?.detail.count == 4000)
        #expect(activity.items.last?.detail.hasSuffix("[Truncated for display]") == true)
    }
}
