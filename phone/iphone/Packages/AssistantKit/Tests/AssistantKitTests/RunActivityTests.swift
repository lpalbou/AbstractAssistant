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
        #expect(activity.items.first?.detail == "not rendered")
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
        #expect(activity.items[0].detail == "model content" && activity.lastEventAt != nil)
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
    @Test func timedPublicModelDetailsAreWhitelistedAndSortedByStartAcrossRuns() throws {
        var activity = RunActivity()
        let route = try record(#"{"step_id":"router","node_id":"route_call","status":"completed","started_at":"2026-10-18T17:24:54.351569+00:00","ended_at":"2026-10-18T17:24:56.730989+00:00","effect":{"type":"llm_call","payload":{"provider":"endpoint:shared","model":"requested","system":"PRIVATE SYSTEM","messages":[{"content":"PRIVATE MESSAGE"}]}},"result":{"data":{"mode":"chat","reasoning":"PRIVATE THOUGHT"},"model":"served","route":{"provider":"openai","served_model":"gpt-example","base_url":"PRIVATE URL"},"usage":{"input_tokens":120,"output_tokens":13},"finish_reason":"stop","metadata":{"llm_generate_kwargs":{"api_key":"PRIVATE KEY"}},"raw_response":"PRIVATE RAW"}}"#)
        let child = try record(#"{"step_id":"cycle","node_id":"reason","status":"completed","started_at":"2026-10-18T17:24:57Z","ended_at":"2026-10-18T17:25:00Z","effect":{"type":"llm_call"},"result":{"content":"Public answer","usage":{"prompt_tokens":9,"completion_tokens":5}}}"#)
        // Parent-first BFS must not override chronological order.
        activity.ingest(child, runID: "child", cursor: 1)
        activity.ingest(route, runID: "parent", cursor: 1)
        #expect(activity.items.map(\.title) == ["Choose response type", "Agent cycle"])
        let item = activity.items[0]
        #expect(item.duration != nil && abs(item.duration! - 2.37942) < 0.001)
        #expect(item.provider == "openai" && item.model == "gpt-example")
        #expect(item.inputTokens == 120 && item.outputTokens == 13 && item.finishReason == "stop")
        #expect(item.outputLabel == "Routing decision" && item.detail.contains("chat"))
        #expect(!item.detail.contains("PRIVATE"))
        #expect(activity.items[1].inputTokens == 9 && activity.items[1].outputTokens == 5)
    }
    @Test func updatesKeepOriginalStartAndApprovalHistoryIsPastTense() throws {
        var activity = RunActivity()
        activity.ingest(try record(#"{"step_id":"s","node_id":"reason","status":"started","started_at":"2026-10-18T12:00:00Z","effect":{"type":"llm_call"}}"#), runID: "r", cursor: 1)
        activity.ingest(try record(#"{"step_id":"s","node_id":"reason","status":"completed","ended_at":"2026-10-18T12:00:03Z","effect":{"type":"llm_call"},"result":{"content":"Done"}}"#), runID: "r", cursor: 2)
        #expect(activity.items.count == 1 && activity.items[0].duration == 3)
        activity.ingest(try record(#"{"step_id":"w","node_id":"act","status":"waiting","started_at":"2026-10-18T12:00:03Z","result":{"wait":{"reason":"user","wait_key":"tool_approval:r","prompt":"Allow?"}}}"#), runID: "r", cursor: 3)
        activity.ingest(try record(#"{"step_id":"next","node_id":"reason","status":"started","started_at":"2026-10-18T12:00:13Z","effect":{"type":"llm_call"}}"#), runID: "r", cursor: 4)
        let approval = try #require(activity.items.first { $0.kind == .wait })
        #expect(approval.title == "Approval resolved" && approval.status == .completed && approval.duration == 10)
    }
    @Test func workflowResumeClosesBoundaryWithoutFakeResumeStep() throws {
        var activity = RunActivity()
        activity.ingest(try record(#"{"step_id":"child","node_id":"assistant_agent","status":"waiting","started_at":"2026-10-18T12:00:00Z","ended_at":"2026-10-18T12:00:00.100Z","effect":{"type":"start_subworkflow"},"result":{"wait":{"reason":"subworkflow"}}}"#), runID: "r", cursor: 1)
        activity.ingest(try record(#"{"step_id":"resume","node_id":"assistant_agent","status":"completed","started_at":"2026-10-18T12:00:03Z","ended_at":"2026-10-18T12:00:03Z","effect":{"type":"resume"},"result":{"resumed":true}}"#), runID: "r", cursor: 2)
        #expect(activity.items.count == 1 && activity.items[0].kind == .workflow)
        #expect(activity.items[0].status == .completed && activity.items[0].duration == 3)
        #expect(activity.items[0].nodeID == "assistant_agent")
    }
    @Test func missingAndInvalidTimesRemainUnknownAndCancellationIsNotFailure() throws {
        var activity = RunActivity()
        activity.ingest(try record(#"{"step_id":"a","status":"cancelled","effect":{"type":"llm_call"},"started_at":"bad","ended_at":"bad"}"#), runID: "r", cursor: 1)
        #expect(activity.items[0].status == .cancelled && activity.items[0].duration == nil)
        #expect(activity.items[0].startedAt == nil && activity.items[0].timestamp == nil)
    }

    @Test func approvalTimingStartsAtRequestAndEndsAtResumeNotNextStep() throws {
        var activity = RunActivity()
        activity.ingest(try record(#"{"step_id":"w","node_id":"act","status":"waiting","started_at":"2026-10-18T12:00:00Z","ended_at":"2026-10-18T12:00:05Z","result":{"wait":{"reason":"user","wait_key":"tool_approval:r"}}}"#), runID: "r", cursor: 1)
        activity.ingest(try record(#"{"step_id":"resume","node_id":"act","status":"completed","started_at":"2026-10-18T12:00:15Z","ended_at":"2026-10-18T12:00:15Z","effect":{"type":"resume"},"result":{"resumed":true}}"#), runID: "r", cursor: 2)
        activity.ingest(try record(#"{"step_id":"next","node_id":"reason","status":"started","started_at":"2026-10-18T12:00:30Z","effect":{"type":"llm_call"}}"#), runID: "r", cursor: 3)
        let wait = try #require(activity.items.first { $0.kind == .wait })
        #expect(wait.duration == 10 && wait.title == "Approval resolved")
    }
    @Test func canonicalMediaRequestIsVisibleWithoutInventingAnAttachment() throws {
        var activity = RunActivity()
        activity.ingest(try record(#"{"step_id":"v","node_id":"generate_voice","status":"completed","effect":{"type":"llm_call","payload":{"output":{"modality":"voice","task":"tts"},"params":{}}},"result":{"content":"","data":null}}"#), runID: "r", cursor: 1)
        #expect(activity.items[0].title == "Generate voice")
        #expect(activity.items[0].detail.contains("Requested output: voice · tts"))
        #expect(activity.items[0].detail.contains("No stored media attachment"))
    }

    @Test func structuredMediaRetainsModalityAndStoredArtifactEvidence() throws {
        var activity = RunActivity()
        activity.ingest(try record(#"{"step_id":"v","node_id":"generate_voice","status":"completed","effect":{"type":"llm_call","payload":{"output":{"modality":"voice","task":"tts"}}},"result":{"data":{"caption":"Here is the recording"},"outputs":{"voice":[{"artifact_id":"voice-public","run_id":"r","filename":"Scene.wav","content_type":"audio/wav"}]}}}"#), runID: "r", cursor: 1)
        #expect(activity.items[0].detail.contains("Requested output: voice · tts"))
        #expect(activity.items[0].detail.contains("Here is the recording"))
        #expect(activity.items[0].detail.contains("Stored media: Scene.wav"))
    }

}
