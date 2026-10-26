import PhoneGatewayClient

public extension ConversationTools {
    /// Nil means the available tools have mixed choices, or none are available.
    func categoryMode(_ category: String, inventory: [ToolInfo]) -> ToolMode? {
        let values = Set(inventory.filter { $0.categoryID == category && $0.isAvailable }.map { modes[$0.name] ?? .off })
        return values.count == 1 ? values.first : nil
    }
    func settingCategory(_ category: String, to mode: ToolMode, inventory: [ToolInfo]) -> ConversationTools {
        var updated = modes
        for tool in inventory where tool.categoryID == category { updated[tool.name] = tool.isAvailable ? mode : .off }
        return ConversationTools(modes: updated)
    }
}
