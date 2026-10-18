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

/// A new automation's request is the one the tray app sends for the same choices
/// (`abstractassistant.core.automations.build_create_request`, output pasted here).
@Test func newAutomationBodyMatchesTheTrayApp() throws {
    var a = NewAutomation(task: "Summarise the AI news", target: .gatewayDefault(interface: "abstractcode.agent.v1"),
                          when: .every("24h"), buildsOnEarlierRuns: false, tools: nil)
    a.requestId = "r1"
    let tray1 = ##"{"request_id": "r1", "title": "Summarise the AI news", "target": {"flow_id": "@default", "interface": "abstractcode.agent.v1", "input_data": {"prompt": "Summarise the AI news"}}, "trigger": {"source_id": "schedule", "source_version": 2, "config": {"kind": "every", "every": "24h"}}, "context": {"mode": "independent"}, "policy": {"tool_approval": "auto"}}"##
    #expect(a.body == (try JSONDecoder().decode(JSONValue.self, from: Data(tray1.utf8))))

    let basic = WorkflowChoice(bundleId: "basic-agent", bundleVersion: "0.0.5", flowId: "81795ea9", name: "Basic agent")
    let input = try WorkflowInputs(defaults: ["use_context": .bool(false)], required: []).inputData(task: "Check my inbox").get()
    // The automation's own tools ride in its target: offered (`tools`, `_runtime.allowed_tools`) and
    // what runs unasked or asks (`_runtime.tool_policy`, which the runtime keeps for its runs).
    let plan = ToolChoices.Plan(offered: ["list_emails", "send_email"], auto: ["list_emails"], ask: ["send_email"])
    var b = NewAutomation(task: "Check my inbox", target: .workflow(basic, inputData: input), when: .daily(at: "08:00"),
                          buildsOnEarlierRuns: true, tools: plan)
    b.requestId = "r2"
    let tray2 = ##"{"request_id": "r2", "title": "Check my inbox", "target": {"bundle_ref": "basic-agent@0.0.5", "flow_id": "81795ea9", "input_data": {"use_context": false, "prompt": "Check my inbox", "tools": ["list_emails", "send_email"], "_runtime": {"allowed_tools": ["list_emails", "send_email"], "tool_policy": {"auto_approve_tools": ["list_emails"], "require_approval_tools": ["send_email"]}}}}, "trigger": {"source_id": "schedule", "source_version": 2, "config": {"kind": "daily", "at": "08:00"}}, "context": {"mode": "growing"}, "policy": {"tool_approval": "ask"}}"##
    #expect(b.body == (try JSONDecoder().decode(JSONValue.self, from: Data(tray2.utf8))))
}

/// The workflows a client may offer, from `GET /bundles?executable_for=` (gateway 0.15 shape), and
/// a workflow's inputs from its v1 descriptor: defaults kept, a required input with no default named.
@Test func workflowListAndInputs() throws {
    let page = ##"{"items":[{"bundle_id":"basic-agent","bundle_version":"0.0.5","owner":{"kind":"gateway"},"entrypoints":[{"flow_id":"81795ea9","name":"Basic agent"}]},{"bundle_id":"deep-research","bundle_version":"0.1.8","entrypoints":[{"flow_id":"deep-research","name":"Deep research"}]}],"executable_for":"abstractcode.agent.v1","default_agent_workflows":{"abstractcode.agent.v1":{"workflow_id":"basic-agent@0.0.5:81795ea9","name":"Basic agent"}}}"##
    let choices = WorkflowChoice.choices(from: try JSONDecoder().decode(JSONValue.self, from: Data(page.utf8)), interface: "abstractcode.agent.v1")
    #expect(choices.map(\.name) == ["Basic agent", "Deep research"])
    #expect(choices.map(\.isDefault) == [true, false], "the workflow behind @default is named, not 'Gateway default'")
    #expect(choices.first?.id == "basic-agent@0.0.5:81795ea9")

    let schema = ##"{"bundle_id":"memact-agent","inputs":[{"id":"prompt","required":true},{"id":"provider","required":false,"default":null},{"id":"use_context","required":false,"default":false},{"id":"workspace","required":true}]}"##
    let inputs = try #require(WorkflowInputs.parse(try JSONDecoder().decode(JSONValue.self, from: Data(schema.utf8))))
    #expect(inputs.defaults == ["use_context": .bool(false)])
    #expect(inputs.required == ["prompt", "workspace"])
    #expect(inputs.inputData(task: "t") == .failure(WorkflowInputsMissing(names: ["workspace"])))
    #expect(WorkflowInputs.parse(.object(["nothing": .null])) == nil)
}

/// Voice choices from the gateway 0.15 listings: voices from `items[].params`, transcription models
/// from `models_by_provider` (not the mislabelled `items`), the defaults as words; a chosen voice
/// rides the speech request as provider + model + voice, none when the gateway's default is kept.
@Test func voiceCatalogAndSpeechRequest() throws {
    let v = ##"{"items":[{"profile_id":"F2","label":"Supertonic F2","params":{"provider":"supertonic","model":"supertonic-3","voice":"F2","language":"en"},"tags":{"gender":"female"}}],"gateway_defaults":{"tts":{"provider":"supertonic","model":"supertonic-3","voice":null},"stt":{"provider":"faster-whisper","model":"base"}}}"##
    let t = ##"{"models":["tiny","gpt-4o-transcribe"],"models_by_provider":{"faster-whisper":["tiny","base"]},"items":[{"id":"gpt-4o-transcribe","provider":"faster-whisper"}]}"##
    let c = VoiceCatalog.parse(voices: try JSONDecoder().decode(JSONValue.self, from: Data(v.utf8)),
                               transcription: try JSONDecoder().decode(JSONValue.self, from: Data(t.utf8)))
    #expect(c.voices == [VoiceChoice(provider: "supertonic", model: "supertonic-3", voice: "F2", label: "Supertonic F2", gender: "female")])
    #expect(c.transcription.map(\.model) == ["tiny", "base"])
    #expect(c.defaultVoice == "supertonic-3" && c.defaultTranscription == "faster-whisper base")
    let chosen = try JSONSerialization.jsonObject(with: JSONEncoder().encode(SpeechRequest(text: "hi", provider: "supertonic", model: "supertonic-3", voice: "F2"))) as! [String: Any]
    #expect(chosen["provider"] as? String == "supertonic" && chosen["model"] as? String == "supertonic-3" && chosen["voice"] as? String == "F2")
    let plain = try JSONSerialization.jsonObject(with: JSONEncoder().encode(SpeechRequest(text: "hi"))) as! [String: Any]
    #expect(plain["provider"] == nil && plain["model"] == nil && plain["voice"] == nil)
}
