import Foundation
import Testing
@testable import AbstractGatewayClient

/// The live wait block of a tool approval (GET /runs/{id}, gateway 0.14, 2026-10-16):
/// `details: {mode, tool_calls: [{name, arguments}]}` and a `tool_approval:` key.
@Test func liveToolApprovalBlockProjectsToAWait() throws {
    let json = #"""
    {"run_id":"e54aedc8","workflow_id":"visual_react_agent","status":"waiting",
     "waiting":{"reason":"user","wait_key":"tool_approval:e54aedc8:act:c736","until":null,"prompt":null,"choices":null,
                "allow_free_text":true,
                "details":{"mode":"approval_required","tool_calls":[{"name":"execute_command",
                  "arguments":{"command":"ls -la .","working_directory":"/w","timeout":30,"_sandbox":{"posture":"x"}}}]}}}
    """#
    let wait = try #require(try JSONDecoder().decode(RunSummary.self, from: Data(json.utf8)).personWait)
    #expect(wait.kind == .toolApproval)
    #expect(wait.toolName == "execute_command")
    #expect(wait.details?.first?.arguments["command"] == .string("ls -la ."))
    #expect(wait.details?.first?.arguments["_sandbox"] == nil)   // host data is dropped
    #expect(!wait.isOutreach)
}

@Test func outreachWaitExposesRecipientAndSubject() throws {
    let json = #"""
    {"run_id":"c17d","workflow_id":"Morning digest","status":"waiting",
     "waiting":{"reason":"user","wait_key":"tool_approval:c17d:act:1",
                "details":{"mode":"approval_required","tool_calls":[{"name":"send_email",
                  "arguments":{"to":"qc-team@example.org","subject":"QC: 2 plates","body_text":"Hello"}}]}}}
    """#
    let wait = try #require(try JSONDecoder().decode(RunSummary.self, from: Data(json.utf8)).personWait)
    #expect(wait.isOutreach)
    #expect(wait.recipient == "qc-team@example.org")
    #expect(wait.subject == "QC: 2 plates")
}

@Test func rowsWaitingOnSomethingElseAreNotPersonWaits() throws {
    let sub = #"{"run_id":"c559","status":"waiting","waiting":{"reason":"subworkflow","wait_key":"subworkflow:e54a"}}"#
    let run = try JSONDecoder().decode(RunSummary.self, from: Data(sub.utf8))
    #expect(!run.waitsOnPerson)
    let listRow = #"{"run_id":"e54a","status":"waiting","waiting":{"reason":"user"}}"#   // list rows carry only the reason
    let row = try JSONDecoder().decode(RunSummary.self, from: Data(listRow.utf8))
    #expect(row.waitsOnPerson)
    #expect(row.personWait == nil)   // the full block comes from GET /runs/{id}
}

@Test func entitiesPageDecodesNamesAndKeepsExtras() throws {
    let json = #"{"entities":[{"name":"castor","phase":"work","age":"long-lived"},{"name":"mira"},{"id":"x"},{"name":"pollux","state":{"state":"asleep","changed_at":"2026-10-17T00:00:00Z"},"created_at":"2026-10-06T10:00:00Z"}]}"#
    let page = try JSONDecoder().decode(EntitiesPage.self, from: Data(json.utf8))
    #expect(page.entities.map(\.name) == ["castor", "mira", "x", "pollux"])
    #expect(page.entities[0].detail == "work · long-lived")
    #expect(page.entities[1].detail == nil)
    // gateway 0.15 shape: `state` is an object; the row reads its inner `state` and the birth date (locale-formatted)
    let pollux = page.entities[3].detail ?? ""
    #expect(pollux.hasPrefix("asleep · born ") && pollux.contains("6") && pollux.contains("Oct"))
    #expect(try JSONDecoder().decode(ChatOpenResponse.self, from: Data(#"{"chat_id":"c1","entity":"castor"}"#.utf8)).chatId == "c1")
    #expect(try JSONDecoder().decode(ChatTurnResponse.self, from: Data(#"{"reply":"hi","tools_ran":[]}"#.utf8)).reply == "hi")
}

@Test func responderRoundTripsThroughItsStorageKey() {
    #expect(Responder(storageKey: Responder.entity("castor").storageKey) == .entity("castor"))
    #expect(Responder(storageKey: nil) == .assistant)
    #expect(Responder.entity("castor").title == "Castor")
}
