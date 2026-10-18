import Foundation
import Testing
import AssistantKit
import AbstractGatewayClient

@Test func gatewayCategoriesAvailabilityAndRiskArePreserved() throws {
    let rows = try JSONDecoder().decode([ToolInfo].self, from: Data(#"[{"name":"get_email_attachment","toolset":"comms","approval_default":"ask","risk_tier":"act","risk_rank":2,"enabled":true},{"name":"capture_camera","toolset":"camera","available":false,"why_disabled":"Camera is off"},{"name":"send_telegram","toolset":"comms","enabled":false},{"name":"custom_plugin","toolset":"  "}]"#.utf8))
    #expect(rows[0].toolset == "comms" && rows[0].riskTier == "act" && rows[0].isAvailable)
    #expect(!rows[1].isAvailable && rows[1].whyDisabled == "Camera is off")
    #expect(!rows[2].isAvailable && rows[3].categoryID == "other")
    let groups = ToolCatalogGroup.groups(rows)
    #expect(groups.map(\.id) == ["camera", "comms", "other"])
    #expect(groups[1].tools.map(\.name) == ["get_email_attachment", "send_telegram"])
    // An unrelated name never invents a category.
    #expect(groups[2].tools.first?.categoryID == "other")
}
@Test func categorySearchShowsOnlyMatchingToolsWithoutDroppingTheirCategories() {
    let rows = [ToolInfo(name: "read_file", riskTier: "observe", riskRank: 1, toolset: "files", description: "Read workspace text"),
                ToolInfo(name: "write_file", riskTier: "act", riskRank: 2, toolset: "files"),
                ToolInfo(name: "send_email", riskTier: "outreach", riskRank: 3, toolset: "comms")]
    #expect(ToolCatalogGroup.groups(rows, matching: " Files ").first?.tools.count == 2)
    #expect(ToolCatalogGroup.groups(rows, matching: "workspace").first?.tools.map(\.name) == ["read_file"])
    #expect(ToolCatalogGroup.groups(rows, matching: "SEND EMAIL").first?.id == "comms")
    #expect(ToolCatalogGroup.groups(rows, matching: "missing").isEmpty)
}
@Test func entityCategoriesCanBeEnrichedWithoutChangingItsPermissionsOrDefaults() {
    let entity = ToolInfo(name: "send_email", riskTier: nil, riskRank: nil, approvalDefault: "auto", enabled: true)
    let discovery = ToolInfo(name: "send_email", riskTier: "outreach", riskRank: 3, toolset: "comms", approvalDefault: "ask", enabled: false)
    let enriched = ToolCatalogGroup.enriching([entity], from: [discovery])[0]
    #expect(enriched.categoryID == "comms" && enriched.riskTier == "outreach")
    #expect(enriched.isAvailable && enriched.approvalDefault == "auto")
    #expect(ToolCatalogGroup.enriching([entity], from: []).first?.categoryID == "other")
}
