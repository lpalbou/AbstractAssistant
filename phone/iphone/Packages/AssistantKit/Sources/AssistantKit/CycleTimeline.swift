import Foundation

public struct ActivityCycle: Identifiable, Sendable {
    public let model: RunActivityItem
    public let tools: [RunActivityItem]
    public let approvals: [RunActivityItem]
    public var id: String { model.id }
}
public struct CycleLane: Identifiable, Sendable {
    public let runID: String
    public let cycles: [ActivityCycle]
    public var id: String { runID }
}
public extension RunActivity {
    /// Group by the most recent reason observed in the SAME ledger run. This is
    /// local presentation grouping, not a runtime causal ID or cross-agent edge.
    var cycleLanes: [CycleLane] {
        let models = items.filter(\.isAgentCycle)
        var order: [String] = []
        for model in models where !order.contains(model.runID) { order.append(model.runID) }
        return order.map { run in
            CycleLane(runID: run, cycles: models.filter { $0.runID == run }.map { model in
                ActivityCycle(model: model,
                    tools: items.filter { $0.kind == .tool && $0.cycleID == model.id },
                    approvals: items.filter { $0.isToolApproval && $0.cycleID == model.id })
            })
        }
    }
    var toolsOutsideRecordedCycles: [RunActivityItem] {
        let retained = Set(items.filter(\.isAgentCycle).map(\.id))
        return items.filter { $0.kind == .tool && ($0.cycleID == nil || !retained.contains($0.cycleID!)) }
    }
    var approvalsOutsideRecordedCycles: [RunActivityItem] {
        let retained = Set(items.filter(\.isAgentCycle).map(\.id))
        return items.filter { $0.isToolApproval && ($0.cycleID == nil || !retained.contains($0.cycleID!)) }
    }
}
