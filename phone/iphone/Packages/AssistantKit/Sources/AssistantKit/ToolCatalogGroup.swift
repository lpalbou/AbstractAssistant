import Foundation
import AbstractGatewayClient

/// Categories come from gateway declarations, never from guesses about tool names.
public struct ToolCatalogGroup: Identifiable, Sendable {
    public let id: String
    public let tools: [ToolInfo]
    public var title: String { id.replacingOccurrences(of: "_", with: " ").capitalized }
    public static func groups(_ inventory: [ToolInfo], matching query: String = "") -> [Self] {
        let query = query.trimmingCharacters(in: .whitespacesAndNewlines)
        let categories = Dictionary(grouping: inventory, by: \.categoryID)
        return categories.keys.sorted().compactMap { category in
            let rows = (categories[category] ?? []).sorted { $0.name < $1.name }
            let matching = rows.filter {
                query.isEmpty || category.localizedStandardContains(query) ||
                $0.name.localizedStandardContains(query) || $0.displayName.localizedStandardContains(query) ||
                ($0.description ?? "").localizedStandardContains(query)
            }
            return matching.isEmpty ? nil : Self(id: category, tools: matching)
        }
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
