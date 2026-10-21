import SwiftUI
import AssistantKit
import AbstractGatewayClient

struct AutomationsScreen: View {
    @Environment(AssistantStore.self) private var store
    @State private var creating = false
    @State private var createdID: String?
    @State private var pendingCreatedID: String?
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    if let error = store.automationsError ?? store.error { ErrorBanner(message: error) }
                    if store.lastRefresh == nil { ProgressView("Checking your gateway…").padding(.vertical, 18) }
                    if store.automations.isEmpty && store.lastRefresh != nil && store.automationsError == nil {
                        VStack(spacing: 12) {
                            Image(systemName: "clock.arrow.circlepath").font(.system(size: 32, weight: .light)).foregroundStyle(PhoneTheme.lavender).padding(.bottom, 4)
                            Text("No automations yet").font(.title3.weight(.semibold))
                            Text("Schedule a task. It runs even while the app is closed.").font(.subheadline).foregroundStyle(PhoneTheme.secondary).multilineTextAlignment(.center)
                            Button { creating = true } label: {
                                Label("New automation", systemImage: "plus").font(.subheadline.weight(.semibold))
                                    .frame(maxWidth: .infinity).frame(minHeight: 52)
                                    .foregroundStyle(PhoneTheme.ground).background(PhoneTheme.lavender, in: Capsule())
                            }.buttonStyle(.plain).padding(.top, 12).accessibilityIdentifier("automations.create")
                        }.frame(maxWidth: .infinity).padding(.horizontal, 8).padding(.vertical, 32)
                    }
                    ForEach(store.automations) { automation in NavigationLink { AutomationDetailScreen(automationID: automation.id) } label: { automationCard(automation) }.buttonStyle(.plain).accessibilityIdentifier("automation.open." + automation.id) }
                }.padding(22)
            }.background(PhoneTheme.ground).navigationTitle("Automations").navigationBarTitleDisplayMode(.inline).refreshable { await store.refresh() }
                .toolbar { ToolbarItem(placement: .principal) { NavigationCaption(title: "Automations", demo: store.isDemo) }; ToolbarItem(placement: .topBarTrailing) { if !store.automations.isEmpty { Button("New automation", systemImage: "plus") { creating = true } } } }
                .sheet(isPresented: $creating, onDismiss: { if let id = pendingCreatedID { pendingCreatedID = nil; createdID = id } }) { NewAutomationScreen { pendingCreatedID = $0.id } }
                .navigationDestination(item: $createdID) { id in AutomationDetailScreen(automationID: id) }
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
    @Environment(\.scenePhase) private var scenePhase
    @State private var occurrences: [LastOccurrence] = []
    @State private var freshRow: AutomationSummary?
    @State private var selectedRun: AutomationRunSelection?
    @State private var error: String?
    @State private var requestedRun = false
    @State private var definition: AutomationDefinition?
    @State private var showingTools = false
    @State private var savingTools = false
    @State private var launching = false
    @State private var loading = false
    @State private var requestedAfterID: String?
    private var row: AutomationSummary? { freshRow ?? store.automations.first { $0.id == automationID } }
    private var runs: [LastOccurrence] {
        var values = occurrences
        if let last = row?.lastOccurrence, !values.contains(where: { $0.occurrenceKey == last.occurrenceKey }) { values.insert(last, at: 0) }
        if let current = row?.currentOccurrence, !values.contains(where: { $0.runId == current.runId }) {
            values.insert(LastOccurrence(status: current.status, excerpt: nil, runId: current.runId, index: current.index, attempts: current.attempt), at: 0)
        }
        var seen: Set<String> = []
        return values.filter { seen.insert($0.occurrenceKey).inserted }
    }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                if let a = row {
                    QuietLabel(text: (a.status ?? "Unknown").capitalized, color: a.status == "active" ? PhoneTheme.mint : PhoneTheme.secondary)
                    Text(a.name ?? "Automation").font(.system(.largeTitle, design: .rounded, weight: .semibold))
                    Text(a.scheduleText ?? a.rowDetail).foregroundStyle(PhoneTheme.secondary)
                    if a.status == "active" || a.status == "paused" { HStack {
                        Button { Task { await runNow(a) } } label: { Label("Run now", systemImage: "play.fill") }
                            .buttonStyle(.borderedProminent).tint(PhoneTheme.mint).foregroundStyle(PhoneTheme.ground).disabled(a.currentOccurrence != nil)
                        Button(a.status == "active" ? "Pause" : "Resume") { Task { await store.automationAction(a, runNow: false); await load() } }.buttonStyle(.bordered)
                    }.controlSize(.large).disabled(store.automationBusy.contains(a.id) || savingTools || launching || definition == nil) }
                    Button { showingTools = true } label: {
                        HStack { Label("Tools", systemImage: "wrench.and.screwdriver").foregroundStyle(PhoneTheme.tool); Spacer(); Text(definition?.tools == nil ? "Settings defaults" : "Custom").foregroundStyle(PhoneTheme.secondary); Image(systemName: "chevron.right").font(.caption) }
                            .font(.subheadline).padding(16).background(PhoneTheme.surface, in: RoundedRectangle(cornerRadius: 18))
                    }.buttonStyle(.plain).disabled(definition == nil || savingTools || launching).accessibilityIdentifier("automation.tools")
                    if requestedRun { Label("Request sent. Checking for the new run…", systemImage: "clock").font(.footnote).foregroundStyle(PhoneTheme.secondary) }
                }
                if let error = error ?? store.error { ErrorBanner(message: error); Button("Try again") { Task { await load() } } }
                if row == nil && loading { ProgressView("Loading automation…") }
                if let first = runs.first {
                    QuietLabel(text: first.isActive ? "Current run" : "Latest run")
                    runCard(first)
                    if runs.count > 1 { QuietLabel(text: "Earlier runs") }
                    ForEach(Array(runs.dropFirst().enumerated()), id: \.element.stableID) { _, occurrence in runCard(occurrence) }
                    Text("Latest 20 runs · Newest first · Times on this iPhone").font(.caption).foregroundStyle(PhoneTheme.secondary)
                } else if !loading && error == nil { Text("No runs yet. Run this automation now or wait for its next scheduled time.").font(.subheadline).foregroundStyle(PhoneTheme.secondary) }
            }.frame(maxWidth: .infinity, alignment: .leading).padding(24)
        }.frame(maxWidth: .infinity, maxHeight: .infinity).background(PhoneTheme.ground).navigationBarTitleDisplayMode(.inline)
        .task(id: store.contextID) {
            freshRow = nil; occurrences = []; definition = nil; requestedRun = false; error = nil
            await load()
            while !Task.isCancelled {
                do { try await Task.sleep(for: .seconds(5)) } catch { return }
                if scenePhase == .active && selectedRun == nil && !showingTools { await load() }
            }
        }
        .refreshable { await load() }
        .sheet(isPresented: $showingTools) {
            ConversationToolsScreen(scope: .automation, automationSelection: definition?.tools) { selected in try await saveTools(selected) }
        }
        .sheet(item: $selectedRun) { selection in AutomationRunSheet(automationID: automationID, occurrence: selection.occurrence) }
    }
    private func runCard(_ occurrence: LastOccurrence) -> some View {
        let explanation = AutomationRunExplanation(occurrence: occurrence)
        let needsAttention = ["failed", "waiting", "backoff"].contains(occurrence.status ?? "")
        return Button { selectedRun = .init(occurrence: occurrence) } label: {
            PhoneCard {
                VStack(alignment: .leading, spacing: 12) {
                    HStack(spacing: 10) {
                        Image(systemName: occurrence.status == "failed" ? "exclamationmark.circle" : occurrence.status == "waiting" ? "hand.raised" : occurrence.isActive ? "circle.dotted" : "checkmark.circle")
                        Text(explanation.title).font(.subheadline.weight(.semibold))
                        Spacer()
                        Image(systemName: "chevron.right").font(.caption)
                    }.foregroundStyle(needsAttention ? PhoneTheme.amber : PhoneTheme.mint)
                    HStack(spacing: 12) {
                        if let date = occurrence.firedAt.flatMap(ISO8601.date) {
                            Text(date, format: .dateTime.day().month(.abbreviated).hour().minute())
                        }
                        if let attempts = occurrence.attemptCount { Text("\(attempts) " + (attempts == 1 ? "attempt" : "attempts")) }
                    }.font(.caption).foregroundStyle(PhoneTheme.secondary)
                    Text(occurrence.status == "failed" || occurrence.isActive ? explanation.message : occurrence.displayAnswer ?? explanation.message)
                        .font(.subheadline).foregroundStyle(PhoneTheme.ink).lineLimit(3).multilineTextAlignment(.leading)
                    Text("View details & activity").font(.caption).foregroundStyle(PhoneTheme.lavender)
                }.frame(maxWidth: .infinity, alignment: .leading)
            }
        }.buttonStyle(.plain).accessibilityIdentifier("automation.run." + occurrence.stableID)
    }
    private func load() async {
        guard let client = store.client, !loading else { return }
        let context = store.contextID
        loading = true; defer { loading = false }
        do {
            async let fetched = client.automationDefinition(id: automationID)
            async let summary = client.automation(id: automationID)
            async let history = client.occurrences(automationId: automationID, limit: 20)
            let (d, a, rows) = try await (fetched, summary, history)
            guard context == store.contextID && !Task.isCancelled else { return }
            definition = d; freshRow = a; occurrences = rows; error = nil
            if a.currentOccurrence != nil || (requestedRun && runs.first?.stableID != requestedAfterID) { requestedRun = false }
            store.rememberAutomation(a)
        } catch is CancellationError {} catch { if context == store.contextID { self.error = error.localizedDescription; if error as? GatewayError == .unauthorized { store.authenticationExpired() } } }
    }
    private func saveTools(_ selected: ConversationTools?) async throws {
        guard let client = store.client, let definition else { throw GatewayError.invalidResponse }
        let context = store.contextID
        savingTools = true; defer { savingTools = false }
        let inventory = try await client.tools()
        guard context == store.contextID else { throw CancellationError() }
        let snapshot = ConversationTools.snapshot(selected ?? store.appTools, inventory: inventory)
        let committed = try await client.saveAutomationTools(id: automationID, definition: definition, tools: snapshot)
        guard context == store.contextID else { throw CancellationError() }
        self.definition = committed; error = nil
    }
    private func runNow(_ automation: AutomationSummary) async {
        guard !launching else { return }
        launching = true; defer { launching = false }
        let context = store.contextID
        let previousID = runs.first?.stableID
        requestedAfterID = previousID
        do {
            guard let client = store.client else { return }
            let latest = try await client.automationDefinition(id: automationID)
            guard context == store.contextID else { return }
            definition = latest
            if latest.tools == nil { try await saveTools(nil) }
            guard context == store.contextID else { return }
            await store.automationAction(automation, runNow: true)
            guard context == store.contextID else { return }
            requestedRun = store.error == nil
            await load()
            if runs.first?.stableID != previousID { requestedRun = false }
        } catch { if context == store.contextID { self.error = error.localizedDescription } }
    }
}

private struct AutomationRunSelection: Identifiable {
    var occurrence: LastOccurrence
    var id: String { occurrence.stableID }
}
