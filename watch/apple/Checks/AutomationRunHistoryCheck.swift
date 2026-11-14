import Foundation

@main struct AutomationRunHistoryCheck {
    struct Row: Equatable { let id: String; let answer: String; var excerpt = false }
    static func main() {
        let current = [Row(id: "old", answer: "past"), Row(id: "live", answer: "received"), Row(id: "pending", answer: "")]
        let merge = { (fresh: [Row]) in mergingFollowedRunHistory(fresh: fresh, current: current,
            followed: ["live", "pending"], id: { $0.id }, hasAnswer: { !$0.answer.isEmpty && !$0.excerpt }) }
        precondition(merge([Row(id: "live", answer: "")]) == [Row(id: "live", answer: "received"), Row(id: "pending", answer: "")])
        precondition(merge([Row(id: "live", answer: "server")]).first?.answer == "server")
        precondition(merge([Row(id: "live", answer: "short summary", excerpt: true)]).first?.answer == "received")
        precondition(merge([]).map(\.id) == ["live", "pending"])
        let now = Date(timeIntervalSince1970: 1000)
        func follow(_ run: String, _ index: Int, known: Set<String> = [], current: Bool = false) -> String? {
            automationRunToFollow(currentRun: current ? run : nil, currentIndex: current ? index : nil,
                lastRun: current ? nil : run, lastIndex: current ? nil : index, firedAt: now,
                after: 42, tapped: now, knownRuns: known)
        }
        precondition(follow("old", 42) == nil)
        precondition(follow("old", 41, current: true) == nil)
        precondition(follow("known", 43, known: ["known"]) == nil)
        precondition(follow("new", 43) == "new")
        precondition(follow("new", 43, current: true) == "new")
        precondition(automationRunToFollow(currentRun: "unknown", currentIndex: nil, lastRun: nil, lastIndex: nil,
            firedAt: now, after: 42, tapped: now, knownRuns: []) == nil)
        precondition(automationRunToFollow(currentRun: nil, currentIndex: nil, lastRun: "old clock", lastIndex: 43,
            firedAt: now.addingTimeInterval(-120), after: 42, tapped: now, knownRuns: []) == nil)
        print("Automation history and occurrence-follow checks passed")
    }
}
