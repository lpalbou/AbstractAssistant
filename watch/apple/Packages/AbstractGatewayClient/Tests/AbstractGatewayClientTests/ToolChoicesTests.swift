import Foundation
import Testing
@testable import AbstractGatewayClient

private let web = ToolInfo(name: "web_search", riskTier: "observe", riskRank: 1, enabled: true, toolset: "web", approvalDefault: "auto")
private let cmd = ToolInfo(name: "execute_command", riskTier: "destroy", riskRank: 4, enabled: true, toolset: "system", approvalDefault: "ask")
private let mail = ToolInfo(name: "send_email", riskTier: "outreach", riskRank: 3, enabled: false, toolset: "comms.email", approvalDefault: "ask")

@Test func theGatewayDecidesUntilThePersonChooses() {
    #expect(ToolChoices.mode(of: web, defaults: [:], session: [:]) == .auto)
    #expect(ToolChoices.mode(of: cmd, defaults: [:], session: [:]) == .ask)
    // Defaults for new conversations, then this conversation's change on top.
    #expect(ToolChoices.mode(of: web, defaults: ["web_search": .ask], session: [:]) == .ask)
    #expect(ToolChoices.mode(of: web, defaults: ["web_search": .ask], session: ["web_search": .off]) == .off)
}

@Test func aToolTheGatewayHasNotSetUpIsAlwaysOff() {
    #expect(ToolChoices.mode(of: mail, defaults: ["send_email": .auto], session: ["send_email": .auto]) == .off)
}

@Test func theRunGetsTheOfferedToolsAndWhichAsk() throws {
    let plan = ToolChoices.plan([web, cmd, mail], defaults: [:], session: ["execute_command": .off])
    #expect(plan.offered == ["web_search"] && plan.auto == ["web_search"] && plan.ask.isEmpty)
    let asked = ToolChoices.plan([web, cmd, mail], defaults: ["web_search": .ask], session: [:])
    #expect(asked.offered == ["execute_command", "web_search"] && asked.auto.isEmpty && asked.ask == ["execute_command", "web_search"])
    // On the wire: `_runtime.tool_policy {auto_approve_tools, require_approval_tools}` and the same
    // tools as `tools` and `_runtime.allowed_tools`; no risk ceiling.
    let req = StartRunRequest(prompt: "hi", sessionId: "s", toolPolicy: plan.policy, tools: plan.offered, system: AssistantPersona.watch)
    let json = try JSONSerialization.jsonObject(with: JSONEncoder().encode(req)) as! [String: Any]
    let input = json["input_data"] as! [String: Any], rt = input["_runtime"] as! [String: Any]
    let policy = rt["tool_policy"] as! [String: Any]
    #expect(policy["auto_approve_tools"] as? [String] == ["web_search"])
    #expect(policy["require_approval_tools"] as? [String] == [])
    #expect(policy["auto_approve_max_risk_rank"] == nil)
    #expect(input["tools"] as? [String] == ["web_search"] && rt["allowed_tools"] as? [String] == ["web_search"])
}

@Test func theCatalogRowCarriesItsGroupDescriptionAndDefault() throws {
    let row = #"{"name":"list_files","description":"List files.","toolset":"files","enabled":true,"approval_default":"auto","risk_tier":"observe","risk_rank":1}"#
    let t = try JSONDecoder().decode(ToolInfo.self, from: Data(row.utf8))
    #expect(t.toolset == "files" && t.description == "List files." && t.approvalDefault == "auto" && t.riskRank == 1)
}

private let fetch = ToolInfo(name: "fetch_url", riskTier: "act", riskRank: 2, enabled: true, toolset: "web", approvalDefault: "ask",
                             modelControlledDestination: true)
private let sendSelf = ToolInfo(name: "send_email", riskTier: "outreach", riskRank: 3, enabled: true, toolset: "comms.email",
                                approvalDefault: "ask", refined: true)

/// All auto never reaches a tool whose destination the assistant picks, nor sends or destructive ones.
@Test func allAutoReachesOnlyQuietTools() {
    #expect(ToolChoices.allAutoReaches(web))
    #expect(!ToolChoices.allAutoReaches(fetch) && !ToolChoices.allAutoReaches(cmd) && !ToolChoices.allAutoReaches(mail))
}

/// A tool with a per-call check (an email to yourself runs unasked) is offered and asks, but is not
/// put on the always-ask list, which would switch the check off.
@Test func aRefinedToolAsksWithoutDisablingItsCheck() {
    let plan = ToolChoices.plan([web, sendSelf], defaults: [:], session: [:])
    #expect(plan.offered == ["send_email", "web_search"] && plan.auto == ["web_search"] && plan.ask.isEmpty)
}

@Test func theRowCarriesItsSafetyFacts() throws {
    let row = #"{"name":"fetch_url","toolset":"web","enabled":true,"risk_tier":"act","risk_rank":2,"model_controlled_destination":true,"remote_write_capable":false,"risk_refiner":null}"#
    let t = try JSONDecoder().decode(ToolInfo.self, from: Data(row.utf8))
    #expect(t.modelControlledDestination == true && !t.refined && t.facts == ["the assistant picks where it goes"])
    let mail = try JSONDecoder().decode(ToolInfo.self, from: Data(#"{"name":"send_email","comms_send":true,"risk_refiner":"send_email_recipient@v2"}"#.utf8))
    #expect(mail.refined && mail.facts == ["sends messages for you"])
}
