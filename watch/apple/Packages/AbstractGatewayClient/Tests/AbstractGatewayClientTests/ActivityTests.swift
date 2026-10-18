import Foundation
import Testing
@testable import AbstractGatewayClient

/// Records shaped like a real basic-agent run's step log (public gateway, 2026-10-18): a thinking
/// step carries the whole conversation (here 230 KB of it), a tool step its calls and results.
private func ledger(_ records: [[String: Any]]) throws -> Data {
    try JSONSerialization.data(withJSONObject: ["items": records, "next_after": records.count])
}
private var conversation: [[String: Any]] { (0..<600).map { i in
    ["role": i % 2 == 0 ? "user" : "assistant", "content": String(repeating: "earlier turn \(i) ", count: 20)]
} }
private func reason(_ status: String, step: String, content: String? = nil) -> [String: Any] {
    var r: [String: Any] = ["step_id": step, "node_id": "reason", "status": status, "started_at": "2026-10-18T12:56:19.398850+00:00",
                            "effect": ["type": "llm_call", "payload": ["prompt": "", "messages": conversation, "tools": [["name": "web_search"]],
                                                                       "params": ["temperature": 0.2]]]]
    if status == "completed" {
        r["ended_at"] = "2026-10-18T12:56:31.000000+00:00"
        r["result"] = ["content": (content as Any?) ?? NSNull(), "raw_response": ["choices": conversation], "usage": ["input_tokens": 24278]]
    }
    return r
}
private func act(_ status: String, step: String, key: String? = nil, calls: Any, results: [[String: Any]]? = nil) -> [String: Any] {
    var r: [String: Any] = ["step_id": step, "idempotency_key": key ?? "key-\(step)", "node_id": "act", "status": status, "started_at": "2026-10-18T12:56:31.100000+00:00",
                            "effect": ["type": "tool_calls", "payload": ["tool_calls": calls, "allowed_tools": ["web_search"]]]]
    if let results { r["result"] = ["mode": "executed", "results": results]; r["ended_at"] = "2026-10-18T12:56:33.600000+00:00" }
    if status == "waiting" { r["result"] = ["wait": ["reason": "user", "wait_key": "tool_approval:\(step)"]] }
    return r
}

@Test func aThinkingStepIsReadWithoutItsConversation() throws {
    let data = try ledger([reason("started", step: "s1"), reason("completed", step: "s1", content: "Let me check the latest **numbers** first.\nThen…")])
    #expect(data.count > 200_000)
    let page = try JSONDecoder().decode(ActivityPage.self, from: data)
    #expect(page.items.count == 2 && page.items[0].type == "llm_call" && page.items[0].nodeId == "reason")
    var log = ActivityLog()
    #expect(log.apply(page.items, runId: "agent") == [.thinking])
    #expect(log.steps.count == 1 && log.steps[0].kind == .thinking && log.steps[0].state == .done)
    #expect(log.steps[0].detail == "Let me check the latest numbers first.")
    #expect(log.steps[0].ended!.timeIntervalSince(log.steps[0].started!) > 11)
}

@Test func toolCallsBecomeStepsWithWhatTheyAreAbout() throws {
    let calls: [[String: Any]] = [
        ["name": "web_search", "arguments": ["query": "Apple Watch Series 11 battery life"], "call_id": "c1"],
        ["name": "skim_url", "arguments": ["url": "https://www.apple.com/watch/battery/?x=1"], "call_id": "c2"],
        ["name": "execute_command", "arguments": ["command": "set -eu\n# list\nls -la /srv/data"], "call_id": "c3"],
    ]
    var log = ActivityLog()
    let started = log.apply(try JSONDecoder().decode(ActivityPage.self, from: try ledger([act("started", step: "a1", calls: calls)])).items, runId: "agent")
    #expect(started == [.tool("web_search"), .tool("skim_url"), .tool("execute_command")])
    #expect(log.runningTools == 3)
    #expect(log.steps.map(\.detail) == ["Apple Watch Series 11 battery life", "www.apple.com/watch/battery/", "ls -la /srv/data"])
    let done = log.apply(try JSONDecoder().decode(ActivityPage.self, from: try ledger([
        act("completed", step: "a1", calls: calls, results: [["success": true, "output": ["stdout": String(repeating: "x", count: 50_000)]],
                                                            ["success": false, "error": "HTTP 403\nForbidden"], ["success": true]])])).items, runId: "agent")
    #expect(done == [.finished(success: true), .finished(success: false), .finished(success: true)])
    #expect(log.steps.map(\.state) == [.done, .failed("HTTP 403"), .done])
    #expect(log.runningTools == 0)
}

@Test func anApprovalWaitIsAStepWaitingOnYou() throws {
    let calls: [[String: Any]] = [["name": "execute_command", "arguments": ["command": "uname -a"]]]
    var log = ActivityLog()
    log.apply(try JSONDecoder().decode(ActivityPage.self, from: try ledger([act("waiting", step: "a2", calls: calls)])).items, runId: "agent")
    #expect(log.steps.first?.state == .waiting && log.steps.first?.detail == "uname -a")
    // The runtime resumes an approved step under a NEW step id; its idempotency key is the same.
    log.apply(try JSONDecoder().decode(ActivityPage.self, from: try ledger([act("completed", step: "a2-resumed", key: "key-a2", calls: calls,
                                                                               results: [["name": "execute_command", "success": true]])])).items, runId: "agent")
    #expect(log.steps.first?.state == .done && log.steps.count == 1)
}

@Test func theAssistantsRouterAndAnImageAreSteps() throws {
    let page = try JSONDecoder().decode(ActivityPage.self, from: try ledger([
        ["step_id": "r", "node_id": "route_call", "status": "started", "effect": ["type": "llm_call", "payload": ["response_schema": ["type": "object"], "messages": []]]],
        ["step_id": "i", "node_id": "generate_image", "status": "started", "effect": ["type": "llm_call", "payload": ["prompt": "An apple", "output": ["modality": "image", "task": "image_generation"]]]],
        ["step_id": "t", "node_id": "title", "status": "started", "effect": ["type": "llm_call", "payload": ["prompt": "Name this"]]],
    ]))
    var log = ActivityLog()
    #expect(log.apply(page.items, runId: "root") == [.media("image")])
    #expect(log.steps.map(\.kind) == [.routing, .media("image")])   // the title note is not shown
}

@Test func aRecordAppliedTwiceIsOneStep() throws {
    let items = try JSONDecoder().decode(ActivityPage.self, from: try ledger([act("started", step: "a1", calls: [["name": "web_search", "arguments": ["query": "q"]]])])).items
    var log = ActivityLog()
    log.apply(items, runId: "agent")
    #expect(log.apply(items, runId: "agent").isEmpty && log.steps.count == 1)
}

@Test func previewsSayWhatAToolIsAbout() {
    #expect(ToolDetail.preview("read_file", .object(["path": .string("/Users/me/notes/plan.md")])) == "plan.md")
    #expect(ToolDetail.preview("send_email", .object(["to": .string("qc@example.org"), "subject": .string("QC")])) == "qc@example.org · QC")
    #expect(ToolDetail.preview("custom_tool", .object(["_sandbox": .string("x"), "topic": .string("tides")])) == "tides")
    #expect(ToolDetail.preview("web_search", .object(["query": .string(String(repeating: "a", count: 200))]))!.count == 90)
    #expect(ToolDetail.preview("web_search", nil) == nil)
}

@Test func theLastThoughtOfAnAnswerIsNotRepeated() throws {
    var log = ActivityLog()
    log.apply(try JSONDecoder().decode(ActivityPage.self, from: try ledger([reason("completed", step: "s1", content: "Checking."),
                                                                           reason("completed", step: "s2", content: "Europe's tallest building is…")])).items, runId: "a")
    log.close(at: Date(), success: true)
    #expect(log.steps.map(\.detail) == ["Checking.", nil])
}

@Test func aCallTrimmedFromItsEndingIsMatchedToItsStart() throws {
    // Over 4 KB, the runtime replaces the finished record's tool_calls with a `$slim` stub.
    let calls: [[String: Any]] = [["name": "write_file", "arguments": ["path": "/tmp/notes.md", "content": String(repeating: "x", count: 5000)]]]
    var log = ActivityLog()
    log.apply(try JSONDecoder().decode(ActivityPage.self, from: try ledger([act("started", step: "w", calls: calls)])).items, runId: "a")
    log.apply(try JSONDecoder().decode(ActivityPage.self, from: try ledger([act("completed", step: "w", calls: ["$slim": ["kind": "list", "bytes": 5100]],
                                                                               results: [["name": "write_file", "success": true]])])).items, runId: "a")
    #expect(log.steps.count == 1 && log.steps[0].state == .done && log.steps[0].detail == "notes.md" && log.runningTools == 0)
}

@Test func aRetriedThoughtThatSucceedsIsNotAFailure() throws {
    var log = ActivityLog()
    let failed = ActivityRecord(stepId: "r1", idempotencyKey: "k", nodeId: "reason", status: "failed", type: "llm_call", error: "timeout")
    let again = ActivityRecord(stepId: "r2", idempotencyKey: "k", nodeId: "reason", status: "started", type: "llm_call")
    let done = ActivityRecord(stepId: "r2", idempotencyKey: "k", nodeId: "reason", status: "completed", type: "llm_call")
    log.apply([ActivityRecord(stepId: "r1", idempotencyKey: "k", nodeId: "reason", status: "started", type: "llm_call"), failed], runId: "a")
    #expect(log.steps.first?.state == .failed("timeout"))
    log.apply([again, done], runId: "a")
    #expect(log.steps.count == 1 && log.steps[0].state == .done)
}

@Test func aCancelledToolSaysStopped() throws {
    var log = ActivityLog()
    log.apply([ActivityRecord(stepId: "t", nodeId: "act", status: "started", type: "tool_calls", calls: [.init(name: "execute_command")]),
               ActivityRecord(stepId: "t", nodeId: "act", status: "cancelled", type: "tool_calls")], runId: "a")
    #expect(log.steps.first?.state == .failed("Stopped"))
}
