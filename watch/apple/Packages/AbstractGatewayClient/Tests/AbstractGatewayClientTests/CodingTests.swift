import Foundation
import Testing
@testable import AbstractGatewayClient

@Test func decodesToolApprovalWait() throws {
    let json = #"""
    {"run_id":"94a436","wait_key":"tool_approval:1","kind":"tool_approval","reason":"user",
     "details":[{"name":"execute_command","arguments":{"command":"rm -rf build/ && make","timeout":30},"call_id":"c1"}]}
    """#
    let wait = try JSONDecoder().decode(Wait.self, from: Data(json.utf8))
    #expect(wait.runId == "94a436")
    #expect(wait.kind == .toolApproval)
    #expect(wait.toolName == "execute_command")
    #expect(wait.details?.first?.arguments["command"] == .string("rm -rf build/ && make"))
    #expect(wait.details?.first?.callId == "c1")
    #expect(wait.riskTier == nil)  // the real payload carries no risk tier
}

@Test func decodesAskUserWaitAndUnknownKind() throws {
    let json = #"{"run_id":"3e9a10","wait_key":"k","kind":"ask_user","prompt":"Which?","choices":["A","B","C"]}"#
    let wait = try JSONDecoder().decode(Wait.self, from: Data(json.utf8))
    #expect(wait.kind == .askUser)
    #expect(wait.choices == ["A", "B", "C"])
    let other = try JSONDecoder().decode(Wait.self, from: Data(#"{"run_id":"r","wait_key":"k","kind":"until"}"#.utf8))
    #expect(other.kind == .other("until"))
}

@Test func runSummaryWaitingProjectsToWait() throws {
    let json = #"""
    {"run_id":"r1","workflow_id":"coding-agent","status":"waiting",
     "waiting":{"reason":"user","wait_key":"wk","prompt":null,"choices":null,"allow_free_text":null,
                "details":[{"name":"write_file","arguments":{"path":"a.md"}}]}}
    """#
    let run = try JSONDecoder().decode(RunSummary.self, from: Data(json.utf8))
    let wait = try #require(run.personWait)
    #expect(wait.kind == .toolApproval && wait.waitKey == "wk" && wait.workflow == "coding-agent")
}

@Test func encodesResumeCommands() throws {
    func object(_ c: ResumeCommand) throws -> [String: Any] {
        try #require(JSONSerialization.jsonObject(with: JSONEncoder().encode(c)) as? [String: Any])
    }
    let allow = try object(ResumeCommand(commandId: "cmd-1", runId: "r1", waitKey: "wk", answer: .approve))
    #expect(allow["command_id"] as? String == "cmd-1")
    #expect(allow["run_id"] as? String == "r1")
    #expect(allow["type"] as? String == "resume")
    let payload = try #require(allow["payload"] as? [String: Any])
    #expect(payload["wait_key"] as? String == "wk")
    #expect((payload["payload"] as? [String: Any])?["approved"] as? Bool == true)

    let deny = try object(ResumeCommand(runId: "r1", waitKey: "wk", answer: .deny))
    #expect(((deny["payload"] as? [String: Any])?["payload"] as? [String: Any])?["approved"] as? Bool == false)

    let reply = try object(ResumeCommand(runId: "r1", waitKey: "wk", answer: .respond("EMA")))
    let inner = try #require((reply["payload"] as? [String: Any])?["payload"] as? [String: Any])
    #expect(inner["response"] as? String == "EMA" && inner["approved"] == nil)
}
