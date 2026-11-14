import Foundation

/// A history read can have started before a locally followed run delivered its answer.
/// Preserve that answer until the gateway's history includes it, retaining server order.
func mergingFollowedRunHistory<Row>(fresh: [Row], current: [Row], followed: Set<String>,
                                    id: (Row) -> String, hasAnswer: (Row) -> Bool) -> [Row] {
    let answered = Dictionary(current.filter { followed.contains(id($0)) && hasAnswer($0) }
        .map { (id($0), $0) }, uniquingKeysWith: { first, _ in first })
    let ids = Set(fresh.map(id))
    return fresh.map { hasAnswer($0) ? $0 : answered[id($0)] ?? $0 }
        + current.filter { !ids.contains(id($0)) && followed.contains(id($0)) }
}

/// A Run tap follows an occurrence newer than the immediately preceding read, never
/// a completed occurrence already displayed on the conversation page.
func automationRunToFollow(currentRun: String?, currentIndex: Int?, lastRun: String?, lastIndex: Int?,
                           firedAt: Date?, after before: Int, tapped: Date, knownRuns: Set<String>) -> String? {
    if let run = currentRun, !knownRuns.contains(run), let index = currentIndex, index > before { return run }
    if let run = lastRun, !knownRuns.contains(run), let index = lastIndex, index > before,
       let firedAt, firedAt > tapped.addingTimeInterval(-60) { return run }
    return nil
}
