import Foundation
import Testing
@testable import AbstractGatewayClient

@Test func aRiskCeilingTravelsInTheRunToolPolicy() throws {
    let req = StartRunRequest(prompt: "hi", sessionId: "s1", toolPolicy: RunToolPolicy(autoApproveMaxRiskRank: 4, requireApprovalTools: ["send_email"]), system: AssistantPersona.iPhone)
    let obj = try JSONSerialization.jsonObject(with: JSONEncoder().encode(req)) as! [String: Any]
    let input = obj["input_data"] as! [String: Any]
    let policy = (input["_runtime"] as! [String: Any])["tool_policy"] as! [String: Any]
    #expect(policy["auto_approve_max_risk_rank"] as? Int == 4 && policy["require_approval_tools"] as? [String] == ["send_email"])
    let plain = try JSONSerialization.jsonObject(with: JSONEncoder().encode(StartRunRequest(prompt: "hi", sessionId: nil, system: AssistantPersona.iPhone))) as! [String: Any]
    #expect((plain["input_data"] as! [String: Any])["_runtime"] == nil)
    let tools = try JSONDecoder().decode(ToolsPage.self, from: Data(#"{"items":[{"name":"send_email","risk_tier":"outreach","risk_rank":3},{"name":"x","risk":{"tier":"act","rank":2}}]}"#.utf8))
    #expect(tools.items[0].riskTier == "outreach" && tools.items[0].riskRank == 3 && tools.items[1].riskRank == 2)
}

/// What starts an automation is said in words, never by its source id (UX re-review #2).
@Test func aTriggerIsSaidInWordsNeverByItsSourceID() throws {
    func row(_ trigger: String, servedSchedule: String? = nil, text: String? = nil) throws -> AutomationSummary {
        var json = "{\"automation_id\": \"a\", \"title\": \"T\", \"trigger\": \(trigger)"
        if let servedSchedule { json += ", \"schedule_text\": \"\(servedSchedule)\"" }
        if let text { json += ", \"trigger_text\": \"\(text)\"" }
        return try JSONDecoder().decode(AutomationSummary.self, from: Data((json + "}").utf8))
    }
    let names = TriggerNames(connections: ["tc_1": "Python news", "tc_2": "Orders"], mailboxes: ["default": "me@example.test", "work": "work@example.test"])
    let feed = try row(#"{"source_id": "feed.item", "source_version": 1, "config": {"connection_id": "tc_1"}}"#, servedSchedule: "feed.item@1")
    #expect(feed.triggerWords(names) == "When Python news has a new item" && feed.isEventTrigger && feed.scheduleSentence == nil)
    #expect(feed.triggerWords() == "When the feed has a new item")
    #expect(try row(#"{"source_id": "webhook.received", "source_version": 1, "config": {"connection_id": "tc_2"}}"#).triggerWords(names) == "When Orders is called")
    #expect(try row(#"{"source_id": "email.received", "source_version": 1, "config": {"account": "work"}}"#).triggerWords(names) == "When mail arrives in work@example.test")
    #expect(try row(#"{"source_id": "email.received", "source_version": 1, "config": {}}"#).triggerWords(names) == "When mail arrives in me@example.test")
    #expect(try row(#"{"source_id": "manual", "source_version": 1, "config": {}}"#).triggerWords() == "By hand")
    let schedule = try row(#"{"source_id": "schedule", "source_version": 2, "config": {"kind": "daily"}}"#, servedSchedule: "Every day at 08:00 (Europe/Paris)")
    #expect(schedule.triggerWords() == "Every day at 08:00 (Europe/Paris)" && !schedule.isEventTrigger)
    #expect(try row(#"{"source_id": "feed.item", "source_version": 1, "config": {}}"#, text: "When Python Insider posts").triggerWords(names) == "When Python Insider posts")
    for t in [#"{"source_id": "calendar.event", "source_version": 3, "config": {}}"#, #"{"source_id": "feed.item", "source_version": 1, "config": {}}"#] {
        let words = try row(t, servedSchedule: "x.y@3").triggerWords()
        #expect(!words.contains("@") && !words.contains("calendar.event") && !words.contains("feed.item"), "\(words)")
    }
}
