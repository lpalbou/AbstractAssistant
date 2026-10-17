import AbstractGatewayClient
import SwiftUI

/// Follows a run while it works and says, in plain words, what it is doing now ("Searching the
/// web", "Reading 4 web pages", "Thinking"). An automation's run starts the agent as a child run
/// (and that one may start others): the step shown is the newest one of the deepest run still
/// working, read from the runs' step logs every 2 s (each read ~0.2 s on the public gateway).
@MainActor
final class RunProgress: ObservableObject {
    @Published private(set) var step = "Starting"
    @Published private(set) var since = Date()

    private var task: Task<Void, Never>?
    private var cursors: [String: Int] = [:]
    private var last: [String: LedgerRecord] = [:]

    func follow(runId: String, client: any GatewayClient) {
        guard task == nil else { return }
        since = Date(); step = "Starting"
        task = Task { [weak self] in
            while !Task.isCancelled {
                guard let self else { return }
                if let words = await self.describe(runId, client: client, depth: 0) { self.step = words }
                try? await Task.sleep(for: .seconds(2))
            }
        }
    }

    func stop() { task?.cancel(); task = nil; cursors = [:]; last = [:] }

    /// The newest step of the deepest run still working under `runId`.
    private func describe(_ runId: String, client: any GatewayClient, depth: Int) async -> String? {
        if let page = try? await client.ledger(runId: runId, after: cursors[runId] ?? 0) {
            cursors[runId] = page.nextAfter ?? ((cursors[runId] ?? 0) + page.items.count)
            if let newest = page.items.last { last[runId] = newest }
        }
        guard let r = last[runId] else { return nil }
        if r.status == "waiting", r.effectType == "start_subworkflow", depth < 4,
           let child = r.result?["wait"]?["details"]?["sub_run_id"]?.stringValue {
            return await describe(child, client: client, depth: depth + 1)
        }
        return Self.words(for: r)
    }

    static func words(for r: LedgerRecord) -> String? {
        if r.status == "waiting" {
            let reason = r.result?["wait"]?["reason"]?.stringValue ?? ""
            return reason == "subworkflow" ? nil : "Needs you"
        }
        switch r.effectType {
        case "llm_call": return "Thinking"
        case "tool_calls":
            var names: [String] = []
            if case .array(let calls)? = r.effect?["payload"]?["tool_calls"] { names = calls.compactMap { $0["name"]?.stringValue } }
            return ToolWords.doing(names)
        case "start_subworkflow": return r.effect?["payload"]?["vars"]?["state"]?.stringValue.map { $0.replacingOccurrences(of: "...", with: "") }
        default: return r.status == "completed" && (r.nodeId == "done" || r.nodeId == "end") ? "Writing the result" : nil
        }
    }
}

/// What tools are doing, as a person would say it.
enum ToolWords {
    static func doing(_ names: [String]) -> String {
        guard let first = names.first else { return "Working" }
        let n = names.filter { $0 == first }.count
        switch first {
        case "web_search", "skim_websearch": return "Searching the web"
        case "skim_url", "fetch_url", "render_url_html": return n > 1 ? "Reading \(n) web pages" : "Reading a web page"
        case "read_file", "skim_files": return n > 1 ? "Reading \(n) files" : "Reading a file"
        case "list_files", "search_files", "skim_folders": return "Looking through files"
        case "write_file", "edit_file": return "Writing a file"
        case "execute_command", "shell_exec": return "Running a command"
        case "send_email", "reply_email": return "Sending an email"
        case "read_email", "list_emails", "search_emails": return "Reading email"
        default:
            let w = first.replacingOccurrences(of: "_", with: " ")
            return "Using " + w
        }
    }
}

/// The run in progress, in place of the result: a spinner, what it is doing now, for how long, and
/// that leaving is fine (a notification says when it is done).
struct RunningCard: View {
    @ObservedObject var progress: RunProgress

    var body: some View {
        Card(stroke: Theme.cyan.opacity(0.5)) {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 8) {
                    ProgressView().frame(width: 18, height: 18)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(progress.step + "…").font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.cyan).lineLimit(2)
                        TimelineView(.periodic(from: .now, by: 1)) { ctx in
                            Text("Running · " + Self.clock(ctx.date.timeIntervalSince(progress.since)))
                                .font(.rounded(.caption2)).foregroundStyle(Theme.muted).monospacedDigit()
                        }
                    }
                }
                Text("You can leave: you'll be notified when it's done.")
                    .font(.rounded(.caption2)).foregroundStyle(Theme.muted)
            }
        }
    }

    static func clock(_ s: Double) -> String { String(format: "%d:%02d", Int(max(0, s)) / 60, Int(max(0, s)) % 60) }
}
