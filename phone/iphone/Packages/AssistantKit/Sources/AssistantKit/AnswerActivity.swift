import Foundation
import PhoneGatewayClient

public struct AnswerActivity: Sendable {
    public var activity: RunActivity
    public var issues: [String]
    public var scopeTitle: String
    public init(activity: RunActivity, issues: [String] = [], scopeTitle: String = "Answer activity") { self.activity = activity; self.issues = issues; self.scopeTitle = scopeTitle }
    public static func load(runID: String, client: any GatewayClient) async throws -> AnswerActivity {
        var result = RunActivity(), queue = [runID], seen: Set<String> = [], issues: [String] = []
        while !queue.isEmpty, seen.count < 64 {
            try Task.checkCancellation()
            let id = queue.removeFirst(); guard seen.insert(id).inserted else { continue }
            do {
                var cursor = 0
                while cursor < 20_000 {
                    let page = try await client.ledger(runId: id, after: cursor)
                    guard (page.nextAfter ?? cursor + page.items.count) == cursor + page.items.count else { throw LedgerStreamError.invalidCursor }
                    for (index, record) in page.items.enumerated() { result.ingest(record, runID: id, cursor: cursor + index + 1) }
                    cursor += page.items.count
                    if page.items.count < 200 { break }
                }
                if cursor >= 20_000 { issues.append("Some events are beyond the 20,000-record history limit.") }
                let children = try await client.childRuns(ofRunID: id)
                for child in children where child.parentRunId == id && !seen.contains(child.runId) && !queue.contains(child.runId) { queue.append(child.runId) }
            } catch GatewayError.unauthorized { throw GatewayError.unauthorized }
            catch is CancellationError { throw CancellationError() }
            catch { issues.append("Some activity could not be loaded. " + error.localizedDescription) }
        }
        if !queue.isEmpty { issues.append("Showing the first 64 runs in this workflow.") }
        let root = try await client.run(id: runID)
        if root.isTerminal { result.finish(status: root.status) }
        return .init(activity: result, issues: Array(Set(issues)).sorted())
    }
}
