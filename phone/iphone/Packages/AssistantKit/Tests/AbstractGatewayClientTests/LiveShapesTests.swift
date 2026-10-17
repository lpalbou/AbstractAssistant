import Foundation
import Testing
@testable import AbstractGatewayClient

/// Shapes captured from gateway.abstractframework.ai (0.15) on 2026-10-17.
@Test func automationRowDecodesRealKeys() throws {
    let json = #"""
    {"automation_id":"07e91ea8","title":"do your daily research","status":"active","context_mode":"growing","occurrence_count":40,
     "trigger":{"source_id":"schedule","config":{"every":"12h","anchor":"2026-09-27T23:28:21Z"}},
     "next_fire_at":"2026-10-17T11:28:21Z",
     "last_occurrence":{"run_id":"e154562b","index":40,"status":"failed","fired_at":"2026-10-16T23:28:21Z","excerpt":"The agent stopped"},
     "attention":{"pending_waits":0,"unread":true,"unseen_count":12,"cursor":"att1:13","items":[{"kind":"failure","run_id":"58cb5739","at":"2026-10-05T11:29:53Z","title":"x failed","body":"completed","cursor":"att1:2"}]}}
    """#
    let a = try JSONDecoder().decode(AutomationSummary.self, from: Data(json.utf8))
    #expect(a.id == "07e91ea8" && a.name == "do your daily research")
    #expect(a.scheduleText == "every 12h")
    #expect(a.lastOccurrence?.status == "failed" && a.lastOccurrence?.runId == "e154562b")
    #expect(a.attention?.unseenCount == 12 && a.attention?.cursor == "att1:13" && a.attention?.items?.first?.kind == "failure")
    #expect(a.needsAttention)
    #expect(a.rowDetail.contains("every 12h") && a.rowDetail.contains("12 unseen"))
}

@Test func automationRowStillDecodesMockKeys() throws {
    let a = try JSONDecoder().decode(AutomationSummary.self, from: Data(#"{"id":"auto-x","name":"Morning digest","status":"active","schedule_text":"every day"}"#.utf8))
    #expect(a.id == "auto-x" && a.name == "Morning digest" && a.scheduleText == "every day")
}

@Test func ledgerPageDecodesAndSummarises() throws {
    let json = #"""
    {"items":[
      {"node_id":"node-4","status":"waiting","effect":{"type":"start_subworkflow"},"result":{"wait":{"reason":"subworkflow","wait_key":"subworkflow:3efc"}}},
      {"node_id":"node-4","status":"completed","effect":{"type":"resume"},"result":{"resumed":true}},
      {"node_id":"act","status":"failed","effect":{"type":"tool_calls"},"error":"KeyError 'ARM'"},
      {"node_id":"end","status":"completed","effect":null,"result":{"completed":true,"output":{"response":"done"}}}],
     "next_after":11}
    """#
    let page = try JSONDecoder().decode(LedgerPage.self, from: Data(json.utf8))
    #expect(page.nextAfter == 11 && page.items.count == 4)
    #expect(page.items[0].summary == "waiting · subworkflow")
    #expect(page.items[1].summary == "resumed")
    #expect(page.items[2].summary == "KeyError 'ARM'")
    #expect(page.items[3].summary == "done")
}

@Test func occurrencesAndCommandsEncode() throws {
    let occ = try JSONDecoder().decode(OccurrencesPage.self, from: Data(#"{"items":[{"run_id":"e1","index":40,"status":"failed","fired_at":"2026-10-16T23:28:21Z","answer":"stopped","trigger":{"source_id":"schedule","summary":"every 12 hours"}}],"next_cursor":null}"#.utf8))
    #expect(occ.items.first?.triggerSummary == "every 12 hours" && occ.items.first?.answer == "stopped")
    let cancel = try JSONSerialization.jsonObject(with: JSONEncoder().encode(CancelCommand(runId: "r1"))) as! [String: Any]
    #expect(cancel["type"] as? String == "cancel" && cancel["run_id"] as? String == "r1" && (cancel["payload"] as? [String: Any])?.isEmpty == true)
    let seen = try JSONSerialization.jsonObject(with: JSONEncoder().encode(SeenRequest(attentionCursor: "att1:13"))) as! [String: Any]
    #expect(seen["attention_cursor"] as? String == "att1:13")
    let me = try JSONDecoder().decode(Principal.self, from: Data(#"{"ok":true,"principal":{"user_id":"admin","roles":["admin","user"],"admin":true}}"#.utf8))
    #expect(me.userId == "admin" && me.admin == true)
}

@Test func rootWaitingOnItsAgentIsNotAPersonsWait() throws {
    let json = #"{"run_id":"r1","workflow_id":"basic-agent@0.0.5","status":"waiting","waiting":{"reason":"subworkflow","wait_key":"subworkflow:c42"}}"#
    let run = try JSONDecoder().decode(RunSummary.self, from: Data(json.utf8))
    #expect(run.personWait == nil)
    #expect(run.waitingOnChild == "c42")
    let child = try JSONDecoder().decode(RunSummary.self, from: Data(#"{"run_id":"c42","status":"waiting","waiting":{"reason":"user","wait_key":"tool_approval:c42:act:9f","details":{"tool_calls":[{"name":"fetch_url","arguments":{"url":"https://x"}}]}}}"#.utf8))
    #expect(child.personWait?.kind == .toolApproval && child.waitingOnChild == nil)
}

@Test func sessionTrustTravelsAsTheRunToolPolicy() throws {
    let req = StartRunRequest(prompt: "hi", sessionId: "s1", toolPolicy: RunToolPolicy(autoApproveMaxRiskRank: 4, requireApprovalTools: ["send_email"]))
    let obj = try JSONSerialization.jsonObject(with: JSONEncoder().encode(req)) as! [String: Any]
    let input = obj["input_data"] as! [String: Any]
    let policy = (input["_runtime"] as! [String: Any])["tool_policy"] as! [String: Any]
    #expect(policy["auto_approve_max_risk_rank"] as? Int == 4 && policy["require_approval_tools"] as? [String] == ["send_email"])
    let plain = try JSONSerialization.jsonObject(with: JSONEncoder().encode(StartRunRequest(prompt: "hi", sessionId: nil))) as! [String: Any]
    #expect((plain["input_data"] as! [String: Any])["_runtime"] == nil)
    let tools = try JSONDecoder().decode(ToolsPage.self, from: Data(#"{"items":[{"name":"send_email","risk_tier":"outreach","risk_rank":3},{"name":"x","risk":{"tier":"act","rank":2}}]}"#.utf8))
    #expect(tools.items[0].riskTier == "outreach" && tools.items[0].riskRank == 3 && tools.items[1].riskRank == 2)
}
