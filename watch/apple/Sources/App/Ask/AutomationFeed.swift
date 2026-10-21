import AbstractGatewayClient
import Foundation

/// What the orb page talks in: the current conversation (the Assistant or an entity), or an
/// automation, a conversation whose messages its trigger sends. The page is the same for both; an
/// automation adds its details behind (i).
enum Conversation: Hashable {
    case chat
    case automation(AutomationSummary)
}

/// An automation on the orb page: its runs as the conversation's messages (what its trigger sent,
/// then the answer), the run in progress, Stop, Seen, and talking about it. Talking never writes
/// into the automation's own conversation (its next runs would read it): it opens a conversation
/// about it, seeded with its runs, which the page then continues as a chat.
@MainActor final class AutomationFeed: ObservableObject {
    @Published private(set) var automation: AutomationSummary
    init(_ automation: AutomationSummary) { self.automation = automation }

    var id: String { automation.id }
    var title: String { automation.name ?? "Automation" }

    /// Its runs, oldest first: the latest `limit` of them.
    func exchanges(_ model: AppModel, limit: Int = 30) async throws -> [Exchange] {
        let runs = try await model.client.occurrences(automationId: id, limit: limit)
        model.keep(results: runs, of: id)
        return runs.reversed().map(Self.exchange)
    }

    /// One run as a message: what its trigger sent, the answer (or that it failed), when.
    static func exchange(_ o: LastOccurrence) -> Exchange {
        Exchange(id: o.runId ?? "occurrence-\(o.index ?? 0)", prompt: o.userTurn ?? "",
                 answer: o.answer ?? o.excerpt ?? "", scope: o.runId.map { .run($0) },
                 failed: o.status == "failed", when: o.firedAt.map(AutomationInfoView.short))
    }

    /// Reads it again; the run in progress, once the gateway has started it (nil: none, or not yet).
    @discardableResult func refresh(_ model: AppModel) async -> String? {
        guard let fresh = try? await model.client.automation(id: id) else { return nil }
        automation = fresh
        model.replaceAutomation(fresh)
        return fresh.currentOccurrence?.runId
    }

    /// The run a Run now (or a trigger) just started: read until its id is known; nil once it is
    /// seen over (a very short run), or never seen within 45 s.
    func liveRun(_ model: AppModel) async -> String? {
        let begun = Date()
        var seen = false
        while !Task.isCancelled, Date().timeIntervalSince(begun) < 45 {
            if let run = await refresh(model) { return run }
            if automation.currentOccurrence != nil { seen = true } else if seen { return nil }
            try? await Task.sleep(for: .seconds(3))
        }
        return nil
    }

    /// Its new results are seen (the gateway's attention, shared by every device), up to its newest
    /// (read fresh: the cursor known before a run ended would leave that run new).
    func markSeen(_ model: AppModel) async {
        await refresh(model)
        guard let c = automation.attention?.cursor,
              (automation.attention?.unseenCount ?? 0) > 0 || (automation.attention?.unread ?? false) else { return }
        try? await model.client.markSeen(automationId: id, cursor: c)
        await refresh(model)
    }

    /// Stops the run in progress (the automation goes on with its schedule).
    func stop(_ model: AppModel) async throws { try await model.client.automationCommand(id: id, type: "automation.stop_current") }

    /// Talking about it: a conversation seeded with its runs up to the latest, its first turn
    /// already started on the gateway. Nil when it has never run (nothing to talk about yet).
    func discuss(_ model: AppModel, _ text: String) async throws -> Discussion? {
        await refresh(model)                                    // its newest run (one just heard included)
        let latest = [automation.lastOccurrence?.index, model.results[id]?.first?.index].compactMap { $0 }.max()
        guard let index = latest else { return nil }
        return try await model.client.discussAutomation(id: id, occurrenceIndex: index, prompt: text)
    }
}
