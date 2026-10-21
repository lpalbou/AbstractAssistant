import Testing
@testable import AbstractGatewayClient

/// An automation that finished a run since it was last looked at is news; the first look, a run in
/// progress and an older number are not.
struct FinishedRunsTests {
    private func a(_ id: String, _ index: Int?, _ status: String?) -> AutomationSummary {
        AutomationSummary(id: id, name: id, status: "active", scheduleText: nil,
                          lastOccurrence: index.map { LastOccurrence(status: status, excerpt: nil, index: $0) })
    }

    @Test func firstLookIsOnlyNoted() {
        let r = FinishedRuns.since([:], in: [a("x", 4, "completed")])
        #expect(r.finished.isEmpty)
        #expect(r.known == ["x": 4])
    }

    @Test func aNewFinishedRunIsNews() {
        let r = FinishedRuns.since(["x": 4, "y": 2], in: [a("x", 5, "completed"), a("y", 3, "failed"), a("z", nil, nil)])
        #expect(r.finished.map(\.id) == ["x", "y"])
        #expect(r.known == ["x": 5, "y": 3])
    }

    @Test func runningOrOlderIsNot() {
        let r = FinishedRuns.since(["x": 4, "y": 7], in: [a("x", 5, "running"), a("y", 6, "completed")])
        #expect(r.finished.isEmpty)
        #expect(r.known == ["x": 4, "y": 7])
    }
}
