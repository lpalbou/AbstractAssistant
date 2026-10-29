import Foundation
import AbstractGatewayClient

/// Categories come from gateway declarations, never from guesses about tool names.
public struct ToolCatalogGroup: Identifiable, Sendable {
    public let id: String
    public let tools: [ToolInfo]
    public let availableCount: Int
    public var isAvailable: Bool { availableCount > 0 }
    public var title: String {
        if id.hasPrefix("mcp:") { return "MCP " + id.dropFirst(4) }
        switch id {
        case "comms.email": return "Email"
        case "comms.telegram": return "Telegram"
        case "comms.whatsapp": return "WhatsApp"
        default: return id.replacingOccurrences(of: "_", with: " ").capitalized
        }
    }
    public static func groups(_ inventory: [ToolInfo], matching query: String = "") -> [Self] {
        let query = query.trimmingCharacters(in: .whitespacesAndNewlines)
        let categories = Dictionary(grouping: inventory, by: \.categoryID)
        return categories.keys.sorted().compactMap { category in
            let rows = (categories[category] ?? []).sorted { ($0.offered ? 0 : 1, $0.name) < ($1.offered ? 0 : 1, $1.name) }
            let matching = rows.filter {
                query.isEmpty || category.localizedStandardContains(query) ||
                $0.name.localizedStandardContains(query) || $0.displayName.localizedStandardContains(query) ||
                ($0.description ?? "").localizedStandardContains(query)
            }
            return matching.isEmpty ? nil : Self(id: category, tools: matching, availableCount: rows.filter(\.offered).count)
        }.sorted { ($0.isAvailable ? 0 : 1, $0.title) < ($1.isAvailable ? 0 : 1, $1.title) }
    }
    /// Entity inventories own availability/defaults. Discovery may supplement display metadata only.
    public static func enriching(_ tools: [ToolInfo], from discovery: [ToolInfo]) -> [ToolInfo] {
        let known = Dictionary(discovery.map { ($0.name, $0) }, uniquingKeysWith: { first, _ in first })
        return tools.map { tool in
            guard let metadata = known[tool.name] else { return tool }
            var tool = tool
            if tool.toolset?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty != false { tool.toolset = metadata.toolset }
            if tool.riskTier == nil { tool.riskTier = metadata.riskTier }
            if tool.riskRank == nil { tool.riskRank = metadata.riskRank }
            return tool
        }
    }
}

/// How the iPhone names a tool and its group (the gateway's toolset; "other" when it gives none).
public extension ToolInfo {
    var categoryID: String {
        let value = toolset?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return value.isEmpty ? "other" : value
    }
    var displayName: String { name.replacingOccurrences(of: "_", with: " ").capitalized }
}

/// The iPhone's words for a tool's mode: the kit's Off / Ask / Auto (the watch and the desktop say the same).
public extension ToolMode {
    var label: String { switch self { case .off: "Off"; case .auto: "Auto"; case .ask: "Ask" } }
}
