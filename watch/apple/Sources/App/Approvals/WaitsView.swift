import AbstractGatewayClient
import SwiftUI

/// Everything waiting for the person, oldest first. One tap opens the approval or the question.
struct WaitsView: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        ScrollView {
            VStack(spacing: 6) {
                if model.waits.isEmpty { Text("Nothing waiting for you").font(.rounded(.footnote)).foregroundStyle(Theme.muted) }
                ForEach(model.waits) { w in
                    NavigationLink(value: w.kind == .askUser ? Route.askUser(w) : Route.approval(w)) {
                        Card(stroke: Theme.amber.opacity(0.5)) {
                            HStack(spacing: 6) {
                                Pill(text: w.kind == .askUser ? "question" : w.isOutreach ? "send" : "approval",
                                     color: w.kind == .askUser ? Theme.indigo : w.isOutreach ? Theme.amber : Theme.cyan)
                                VStack(alignment: .leading, spacing: 1) {
                                    Text(w.kind == .askUser ? (w.prompt ?? "question") : w.toolName)
                                        .font(w.kind == .askUser ? .rounded(.footnote, weight: .semibold) : .mono(.footnote, weight: .semibold))
                                        .foregroundStyle(Theme.text).lineLimit(w.kind == .askUser ? 2 : 1).truncationMode(.middle)
                                    Text(w.workflow ?? String(w.runId.prefix(8))).font(.rounded(.caption2)).foregroundStyle(Theme.muted).lineLimit(1)
                                }
                                Spacer(minLength: 2)
                                Image(systemName: "chevron.right").font(.caption2).foregroundStyle(Theme.amber)
                            }
                        }
                    }
                    .buttonStyle(.plain)
                }
                Footnote(text: "each answer is a record on the run's ledger")
            }
        }
        .screen("Waiting for you")
        .refreshable { await model.refresh() }
    }
}
