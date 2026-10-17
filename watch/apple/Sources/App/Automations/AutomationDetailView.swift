import AbstractGatewayClient
import SwiftUI
import WatchKit

/// One automation: its schedule, the last occurrence's answer, unseen notifications, Run now, Mark read.
struct AutomationDetailView: View {
    let automation: AutomationSummary
    @EnvironmentObject private var model: AppModel
    @State private var occurrences: [LastOccurrence] = []
    @State private var started = false
    @State private var marked = false
    @State private var error: String?

    private var current: AutomationSummary { model.automations.first { $0.id == automation.id } ?? automation }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 6) {
                Text(current.name ?? current.id).font(.rounded(.headline)).foregroundStyle(Theme.text).lineLimit(2)
                HStack(spacing: 6) {
                    StatusDot(color: current.status == "active" ? Theme.green : Theme.muted)
                    Text([current.status, current.scheduleText].compactMap { $0 }.joined(separator: " · "))
                        .font(.rounded(.caption2)).foregroundStyle(Theme.muted).lineLimit(1)
                }
                if let next = current.nextFireAt { Text("next " + Self.short(next)).font(.mono(.caption2)).foregroundStyle(Theme.muted) }
                if let last = occurrences.first ?? current.lastOccurrence {
                    Card(stroke: last.status == "failed" ? Theme.red.opacity(0.6) : Theme.line) {
                        VStack(alignment: .leading, spacing: 3) {
                            HStack(spacing: 5) {
                                Pill(text: last.status ?? "run", color: Theme.statusColor(last.status ?? ""))
                                if let f = last.firedAt { Text(Self.short(f)).font(.mono(.caption2)).foregroundStyle(Theme.muted) }
                            }
                            MarkdownText(last.answer ?? last.excerpt ?? "no answer recorded")
                        }
                    }
                    if let text = last.answer ?? last.excerpt, let run = last.runId {
                        ReadAloudLink(item: ReadItem(title: current.name ?? "Automation", text: text, scope: .run(run)))
                    }
                }
                if let items = current.attention?.items, !items.isEmpty {
                    Text("UNSEEN").font(.rounded(.caption2, weight: .semibold)).foregroundStyle(Theme.muted)
                    ForEach(items.suffix(3)) { it in
                        HStack(alignment: .top, spacing: 5) {
                            Pill(text: it.kind ?? "note", color: it.kind == "failure" ? Theme.red : Theme.indigo)
                            Text(it.body ?? it.title ?? "").font(.rounded(.caption2)).foregroundStyle(Theme.text2).lineLimit(2)
                        }
                    }
                }
                Button(started ? "Started" : "Run now") { runNow() }
                    .buttonStyle(FilledButtonStyle(fill: Theme.indigoButton)).disabled(started).padding(.top, 4)
                if let cursor = current.attention?.cursor, (current.attention?.unseenCount ?? 0) > 0 || (current.attention?.unread ?? false) {
                    Button(marked ? "Read" : "Mark read") { markRead(cursor) }
                        .buttonStyle(FilledButtonStyle(fill: Theme.neutralButton, foreground: Theme.text2)).disabled(marked)
                }
                if let error { Text(error).font(.rounded(.caption2)).foregroundStyle(Theme.red) }
                Footnote(text: "discuss or edit it on the Mac · same automation", mono: false)
            }
        }
        .screen("Automation")
        .task { occurrences = (try? await model.client.occurrences(automationId: automation.id, limit: 1)) ?? [] }
    }

    private func runNow() {
        started = true
        Task {
            do { try await model.client.runAutomationNow(id: automation.id); WKInterfaceDevice.current().play(.click); await model.refresh() }
            catch { self.error = error.localizedDescription; started = false }
        }
    }

    private func markRead(_ cursor: String) {
        marked = true
        Task {
            do { try await model.client.markSeen(automationId: automation.id, cursor: cursor); await model.refresh() }
            catch { self.error = error.localizedDescription; marked = false }
        }
    }

    /// "2026-10-17T05:04:00Z" → "17 Oct 05:04" in the device locale, else the raw string.
    static func short(_ iso: String) -> String {
        guard let d = ISO8601.date(iso) else { return iso }
        return d.formatted(.dateTime.day().month(.abbreviated).hour().minute())
    }
}
