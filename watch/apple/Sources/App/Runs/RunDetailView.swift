import AbstractGatewayClient
import SwiftUI
import WatchKit

/// One run: its last ledger records (live from `GET /runs/{id}/ledger`), its output, and Cancel.
struct RunDetailView: View {
    let run: RunSummary
    @EnvironmentObject private var model: AppModel
    @State private var detail: RunSummary?
    @State private var records: [LedgerRecord] = []
    @State private var cursor = 0
    @State private var cancelling = false
    @State private var error: String?

    private static let shown = 8
    private static let words: [String: String] = [
        "llm_call": "thought", "tool_calls": "tools", "start_subworkflow": "agent", "resume": "resumed",
        "ask_user": "question", "answer_user": "answer", "wait_event": "wait", "wait_until": "timer",
        "completed": "done", "failed": "failed", "waiting": "waiting", "running": "running",
    ]

    var body: some View {
        let current = detail ?? run
        ScrollView {
            VStack(alignment: .leading, spacing: 6) {
                Text(current.workflowId ?? "run").font(.rounded(.headline)).foregroundStyle(Theme.text).lineLimit(1)
                HStack(spacing: 6) {
                    StatusDot(color: Theme.statusColor(current.status))
                    Text("run \(current.runId.prefix(6)) · \(Theme.statusLabel(current.status))").font(.mono(.caption2)).foregroundStyle(Theme.muted)
                }
                if records.isEmpty {
                    Text(model.client.isMock ? "" : "reading the ledger…").font(.rounded(.caption2)).foregroundStyle(Theme.muted)
                }
                ForEach(Array(records.suffix(Self.shown).enumerated()), id: \.element.id) { i, rec in
                    recordRow(index: records.count - min(records.count, Self.shown) + i + 1, rec)
                }
                if let out = current.outputText, !out.isEmpty, current.isTerminal {
                    Card { MarkdownText(out) }
                    ReadAloudLink(item: ReadItem(title: "Run output", text: out, scope: .run(current.runId)))
                }
                if let err = current.error ?? error { Text(err).font(.rounded(.caption2)).foregroundStyle(Theme.red) }
                if !current.isTerminal {
                    Button(cancelling ? "Cancelling…" : "Cancel") { cancel() }
                        .buttonStyle(FilledButtonStyle(fill: Theme.redButton)).disabled(cancelling).padding(.top, 4)
                }
                Footnote(text: records.isEmpty ? "" : "\(records.count) ledger records · same run on every client", mono: true)
            }
        }
        .screen("Run")
        .task { await follow() }
    }

    private func recordRow(index: Int, _ rec: LedgerRecord) -> some View {
        let kind = rec.effectType ?? rec.status ?? ""
        let color: Color = rec.status == "failed" ? Theme.red : rec.status == "waiting" ? Theme.amber
            : kind.contains("tool") ? Theme.cyan : kind == "llm_call" ? Theme.indigo : Theme.green
        return Card {
            HStack(alignment: .top, spacing: 5) {
                Text("#\(index)").font(.mono(.caption2)).foregroundStyle(Theme.muted)
                Pill(text: Self.words[kind] ?? (kind.isEmpty ? "step" : kind.replacingOccurrences(of: "_", with: " ")), color: color)
                VStack(alignment: .leading, spacing: 1) {
                    Text(rec.nodeId ?? "").font(.mono(.caption2)).foregroundStyle(Theme.text2).lineLimit(1)
                    Text(MarkdownText.inline(rec.summary)).font(.rounded(.caption2)).foregroundStyle(Theme.muted).lineLimit(2)
                }
            }
        }
    }

    /// Replays the ledger from the cursor, then follows it every 2 s while the run is live.
    private func follow() async {
        repeat {
            do {
                let page = try await model.client.ledger(runId: run.runId, after: cursor)
                if !page.items.isEmpty { records.append(contentsOf: page.items) }
                cursor = page.nextAfter ?? (cursor + page.items.count)
                detail = try await model.client.run(id: run.runId)
            } catch { self.error = error.localizedDescription; return }
            if (detail ?? run).isTerminal { return }
            try? await Task.sleep(for: .seconds(2))
        } while !Task.isCancelled
    }

    private func cancel() {
        cancelling = true
        Task {
            do { try await model.client.cancel(runId: run.runId); WKInterfaceDevice.current().play(.click) }
            catch { self.error = error.localizedDescription }
            cancelling = false
        }
    }
}
