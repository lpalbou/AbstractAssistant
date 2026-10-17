import AbstractGatewayClient
import SwiftUI
import WatchKit

struct AutomationsView: View {
    @EnvironmentObject private var model: AppModel
    @State private var started: String?

    var body: some View {
        ScrollView {
            VStack(spacing: 6) {
                if model.automations.isEmpty {
                    Text(model.automationsError ?? (model.lastRefresh == nil ? "loading…" : "No automations on this gateway"))
                        .font(.rounded(.footnote)).foregroundStyle(model.automationsError == nil ? Theme.muted : Theme.red)
                        .multilineTextAlignment(.center).padding(.top, 8)
                }
                ForEach(model.automations) { a in
                    NavigationLink(value: Route.automation(a)) {
                        Card(stroke: a.needsAttention ? Theme.amber.opacity(0.5) : nil) {
                            HStack(spacing: 6) {
                                StatusDot(color: color(a))
                                VStack(alignment: .leading, spacing: 1) {
                                    Text(a.name ?? a.id).font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.text).lineLimit(1)
                                    Text(a.rowDetail).font(.rounded(.caption2)).foregroundStyle(Theme.muted).lineLimit(1)
                                }
                                Spacer(minLength: 2)
                                if let n = a.attention?.unseenCount, n > 0 { Pill(text: "\(n)", color: Theme.amber) }
                                else if let c = a.cadence { Pill(text: c, color: c == "weekly" ? Theme.cyan : Theme.green) }
                            }
                        }
                    }
                    .buttonStyle(.plain)
                }
                if let first = model.automations.first {
                    Card(fill: Color(hex: 0x131a2e), stroke: Color(hex: 0x1e2a4a)) {
                        HStack {
                            VStack(alignment: .leading, spacing: 1) {
                                Text("Run now").font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.text)
                                Text(started == first.id ? "started" : (first.name ?? first.id))
                                    .font(.rounded(.caption2)).foregroundStyle(Theme.muted).lineLimit(1)
                            }
                            Spacer(minLength: 4)
                            Button("Run") { runNow(first) }
                                .buttonStyle(FilledButtonStyle(fill: Theme.indigoButton)).frame(width: 64)
                        }
                    }
                }
                Footnote(text: "notified only on a question, an approval or a failure")
            }
        }
        .screen("Automations")
    }

    private func color(_ a: AutomationSummary) -> Color {
        Theme.statusColor(a.lastOccurrence?.status ?? a.status ?? "")
    }

    private func runNow(_ a: AutomationSummary) {
        Task {
            do { try await model.client.runAutomationNow(id: a.id); started = a.id; WKInterfaceDevice.current().play(.start) }
            catch { model.lastError = error.localizedDescription }
        }
    }
}
