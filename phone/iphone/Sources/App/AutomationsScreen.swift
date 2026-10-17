import SwiftUI
import AssistantKit
import AbstractGatewayClient

struct AutomationsScreen: View {
    @Environment(AssistantStore.self) private var store
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    Text("A rhythm\nof your own.").font(.system(.largeTitle, design: .rounded, weight: .semibold)).tracking(-0.8).padding(.vertical, 12)
                    Text("The little things, taken care of.\nYour gateway keeps them running.").foregroundStyle(PhoneTheme.secondary).lineSpacing(4)
                    if let error = store.automationsError ?? store.error { ErrorBanner(message: error) }
                    if store.lastRefresh == nil { ProgressView("Checking your gateway…").padding(.vertical, 18) }
                    if store.automations.isEmpty && store.lastRefresh != nil && store.automationsError == nil {
                        ContentUnavailableView("Make room for a routine", systemImage: "clock.arrow.circlepath", description: Text("Create an automation in your gateway console. Follow its results here."))
                        if let url = store.connection?.gateway.appending(path: "console") { Link("Open gateway console", destination: url).frame(maxWidth: .infinity) }
                    }
                    ForEach(store.automations) { automation in NavigationLink { AutomationDetailScreen(automationID: automation.id) } label: { automationCard(automation) }.buttonStyle(.plain) }
                }.padding(22)
            }.background(PhoneTheme.ground).navigationTitle("Automations").navigationBarTitleDisplayMode(.inline).refreshable { await store.refresh() }
                .toolbar { ToolbarItem(placement: .principal) { NavigationCaption(title: "Automations", demo: store.isDemo) } }
        }
    }
    private func automationCard(_ a: AutomationSummary) -> some View {
        PhoneCard {
            VStack(alignment: .leading, spacing: 15) {
                HStack { Image(systemName: "clock").foregroundStyle(PhoneTheme.lavender); Spacer(); QuietLabel(text: (a.status ?? "Unknown").capitalized, color: a.status == "active" ? PhoneTheme.mint : PhoneTheme.secondary) }
                Text(a.name ?? "Automation").font(.system(.title3, design: .rounded, weight: .semibold))
                Text(a.scheduleText ?? a.rowDetail).font(.footnote).foregroundStyle(PhoneTheme.secondary)
                if let excerpt = a.lastOccurrence?.excerpt { Text(excerpt).font(.subheadline).foregroundStyle(PhoneTheme.secondary).lineLimit(3) }
                HStack { if let next = a.nextFireAt.flatMap(ISO8601.date) { Text("Next "); Text(next, style: .relative) }; Spacer(); Image(systemName: "arrow.up.right") }.font(.caption).foregroundStyle(PhoneTheme.lavender)
            }
        }
    }
}

struct AutomationDetailScreen: View {
    let automationID: String
    @Environment(AssistantStore.self) private var store
    @State private var occurrences: [LastOccurrence] = []
    @State private var error: String?
    @State private var requestedRun = false
    private var row: AutomationSummary? { store.automations.first { $0.id == automationID } }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                if let a = row {
                    QuietLabel(text: (a.status ?? "Unknown").capitalized, color: PhoneTheme.mint)
                    Text(a.name ?? "Automation").font(.system(.largeTitle, design: .rounded, weight: .semibold))
                    Text(a.scheduleText ?? a.rowDetail).foregroundStyle(PhoneTheme.secondary)
                    if a.status == "active" || a.status == "paused" { HStack {
                        Button { Task { await store.automationAction(a, runNow: true); if store.error == nil { requestedRun = true }; await load() } } label: { Label("Run now", systemImage: "play.fill") }.buttonStyle(.borderedProminent)
                        Button(a.status == "active" ? "Pause" : "Resume") { Task { await store.automationAction(a, runNow: false) } }.buttonStyle(.bordered)
                    }.controlSize(.large).disabled(store.automationBusy.contains(a.id)) }
                    if requestedRun { Label("Run requested. Pull down to check its result.", systemImage: "checkmark.circle").font(.footnote).foregroundStyle(PhoneTheme.mint) }
                    if let current = a.currentOccurrence { Label("Run \(current.index ?? 0) · \(current.status ?? "working")", systemImage: "circle.dotted").foregroundStyle(PhoneTheme.amber) }
                    if let error = error ?? store.error { ErrorBanner(message: error) }
                    if let answer = a.lastOccurrence?.answer ?? a.lastOccurrence?.excerpt { QuietLabel(text: "Latest result"); PhoneMarkdown(text: answer) }
                    if !occurrences.isEmpty { QuietLabel(text: "Earlier runs") }
                    ForEach(Array(occurrences.enumerated()), id: \.offset) { _, occurrence in
                        PhoneCard { VStack(alignment: .leading, spacing: 10) { QuietLabel(text: occurrence.status ?? "Run"); if let text = occurrence.answer ?? occurrence.excerpt { PhoneMarkdown(text: text) } } }
                    }
                    if let url = store.connection?.gateway.appending(path: "console") { Link("Edit in gateway console", destination: url).font(.footnote) }
                }
            }.padding(24)
        }.background(PhoneTheme.ground).navigationBarTitleDisplayMode(.inline).task { await load() }.refreshable { await store.refresh(); await load() }
    }
    private func load() async {
        guard let client = store.client else { return }
        do { occurrences = try await client.occurrences(automationId: automationID, limit: 5); error = nil }
        catch { self.error = error.localizedDescription }
    }
}
