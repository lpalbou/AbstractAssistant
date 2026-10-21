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


@Test func entityAppearanceIsReadFromTheRow() throws {
    let page = try JSONDecoder().decode(EntitiesPage.self, from: Data(##"{"entities":[{"name":"vega","appearance":{"color":"#f59e0b","shape":"kitty"}},{"name":"aster"}]}"##.utf8))
    #expect(page.entities[0].appearanceColor == "#f59e0b" && page.entities[0].appearanceShape == "kitty")
    #expect(page.entities[1].appearanceColor == nil && page.entities[1].appearanceShape == nil)
}

/// The gateway 0.15 automation row: the trigger is kept whole (a revision sends it back with only
/// `every` changed) and the revision travels with it.
@Test func automationRowKeepsItsTriggerAndRevision() throws {
    let json = ##"{"items":[{"automation_id":"07e9","title":"daily research","status":"active","revision":2,"context_mode":"growing","trigger":{"binding_id":"b","source_id":"schedule","source_version":1,"config":{"anchor":"2026-09-27T23:28:21Z","every":"12h"}},"next_fire_at":"2026-10-17T23:28:21Z"}],"next_cursor":null}"##
    let page = try JSONDecoder().decode(AutomationsPage.self, from: Data(json.utf8))
    let a = try #require(page.items.first)
    #expect(a.every == "12h")
    #expect(a.revision == 2)
    #expect(a.triggerSource == "schedule")
    #expect(a.triggerSourceVersion == 1)
    #expect(a.triggerConfig?["anchor"]?.stringValue == "2026-09-27T23:28:21Z")
}

/// An edited task goes back inside the committed target: every other input (tools, model, workspace)
/// unchanged, as the console's form sends it.
@Test func editedTaskKeepsTheRestOfTheTarget() throws {
    let json = ##"{"definition":{"revision":2,"title":"daily research","target":{"workflow_id":"w","bundle_ref":"basic-agent@0.0.5","flow_id":"81795ea9","input_data":{"prompt":"old task","tools":["web_search"],"model":"m"}}},"summary":{}}"##
    let d = try JSONDecoder().decode(AutomationDefinitionResponse.self, from: Data(json.utf8)).definition
    #expect(d.prompt == "old task")
    #expect(d.revision == 2)
    let t = try #require(d.target(withPrompt: "new task"))
    #expect(t["input_data"]?["prompt"]?.stringValue == "new task")
    #expect(t["input_data"]?["model"]?.stringValue == "m")
    #expect(t["input_data"]?["tools"] == .array([.string("web_search")]))
    #expect(t["bundle_ref"]?.stringValue == "basic-agent@0.0.5")
    #expect(t["workflow_id"] == nil)   // the gateway refuses fields it resolves itself
}

/// `GET /automations/{id}` while an occurrence runs: `summary.current_occurrence` carries its run.
@Test func runningAutomationCarriesItsRun() throws {
    let json = ##"{"definition":{},"active_revision":2,"summary":{"automation_id":"07e9","title":"t","status":"active","current_occurrence":{"index":44,"run_id":"r-44","attempt":1,"status":"running"}}}"##
    let a = try JSONDecoder().decode(AutomationSummaryResponse.self, from: Data(json.utf8)).summary
    #expect(a.currentOccurrence?.runId == "r-44")
    #expect(a.currentOccurrence?.index == 44)
    let idle = ##"{"summary":{"automation_id":"07e9","status":"active","current_occurrence":null}}"##
    #expect(try JSONDecoder().decode(AutomationSummaryResponse.self, from: Data(idle.utf8)).summary.currentOccurrence == nil)
}

/// An automation named by its task keeps its name in step with an edited task; its own title stays.
@Test func titleFollowsTheTaskOnlyWhenItWasTheTask() {
    #expect(AutomationDefinition.title(afterTask: "new task", oldTitle: "old task", oldTask: "old task") == "new task")
    let long = String(repeating: "a", count: 150)
    #expect(AutomationDefinition.title(afterTask: "b" + long, oldTitle: String(long.prefix(120)), oldTask: long) == String(("b" + long).prefix(120)))
    #expect(AutomationDefinition.title(afterTask: "new task", oldTitle: "Morning digest", oldTask: "old task") == nil)
}

@Test func explicitAutomationTitleDoesNotReplaceOrTruncateItsTask() {
    let task = "Read the workspace notes.\nReport the important changes and their sources."
    let named = NewAutomation(task: task, target: .gatewayDefault(interface: "abstractassistant.agent.v1"), when: .every("24h"), buildsOnEarlierRuns: false, askBeforeTools: true, title: "  Morning briefing  ")
    #expect(named.body["title"] == .string("Morning briefing"))
    #expect(named.body["target"]?["input_data"]?["prompt"] == .string(task))
    var legacy = named; legacy.customTitle = "  "
    #expect(legacy.title == "Read the workspace notes.")
    legacy.task = String(repeating: "a", count: 200)
    #expect(legacy.title.count == 120)
}
