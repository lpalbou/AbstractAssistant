import SwiftUI
import AssistantKit
import PhoneGatewayClient

struct AutomationsScreen: View {
    @Environment(AssistantStore.self) private var store
    @State private var archiving: AutomationSummary?
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
                    NavigationLink { ArchivedAutomationsScreen() } label: {
                        Label("Archived", systemImage: "archivebox").foregroundStyle(PhoneTheme.secondary)
                    }.accessibilityIdentifier("automations.archived")
                    ForEach(store.automations) { automation in
                        PhoneCard {
                            ZStack(alignment: .topTrailing) {
                                NavigationLink { AutomationDetailScreen(automationID: automation.id) } label: { automationCard(automation) }
                                    .buttonStyle(.plain).accessibilityIdentifier("automation.open." + automation.id)
                                Button { archiving = automation } label: {
                                    Image(systemName: "archivebox").foregroundStyle(PhoneTheme.lavender)
                                        .frame(width: 44, height: 44).background(PhoneTheme.lavender.opacity(0.08), in: Circle())
                                }.buttonStyle(.plain).disabled(store.automationBusy.contains(automation.id))
                                    .accessibilityLabel("Archive automation").accessibilityIdentifier("automation.archive." + automation.id)
                            }
                        }
                    }
                }.padding(22)
            }.background(PhoneTheme.ground).navigationTitle("Automations").navigationBarTitleDisplayMode(.inline).refreshable { await store.refresh() }
                .toolbar { ToolbarItem(placement: .principal) { NavigationCaption(title: "Automations", demo: store.isDemo) }; ToolbarItem(placement: .topBarTrailing) { if !store.automations.isEmpty { Button("New automation", systemImage: "plus") { creating = true } } } }
                .sheet(isPresented: $creating, onDismiss: { if let id = pendingCreatedID { pendingCreatedID = nil; createdID = id } }) { NewAutomationScreen { pendingCreatedID = $0.id } }
                .confirmationDialog("Archive automation?", isPresented: Binding(get: { archiving != nil }, set: { if !$0 { archiving = nil } }), titleVisibility: .visible) {
                    if let automation = archiving {
                        Button("Archive") { archiving = nil; Task { await store.setAutomationArchived(automation, true) } }
                    }
                    Button("Cancel", role: .cancel) { archiving = nil }
                } message: { Text("This stops future scheduled runs and hides the automation on all your devices. Its history is kept. You can restore it from Archived.") }
                .navigationDestination(item: $createdID) { id in AutomationDetailScreen(automationID: id) }
        }
    }
    private func automationCard(_ a: AutomationSummary) -> some View {
        VStack(alignment: .leading, spacing: 15) {
                HStack { Image(systemName: "clock").foregroundStyle(PhoneTheme.lavender); Spacer(); QuietLabel(text: (a.status ?? "Unknown").capitalized, color: a.status == "active" ? PhoneTheme.mint : PhoneTheme.secondary) }
                    .padding(.trailing, 56).frame(minHeight: 44)
                Text(a.name ?? "Automation").font(.system(.title3, design: .rounded, weight: .semibold))
                Text(a.triggerWords(store.triggerNames)).font(.footnote).foregroundStyle(PhoneTheme.secondary)
                if let excerpt = a.lastOccurrence?.excerpt {
                    AutomationMarkdownPreview(text: excerpt)
                }
                HStack { if !a.isEventTrigger, let next = a.nextFireAt.flatMap(ISO8601.date) { Text("Next "); Text(next, style: .relative) }; Spacer(); Image(systemName: "arrow.up.right") }.font(.caption).foregroundStyle(PhoneTheme.lavender)
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// One compact text flow lets the preview wrap and truncate at a complete line.
/// Full report typography belongs in the run sheet, not inside a height-clipped card.
private struct AutomationMarkdownPreview: View {
    let text: String
    private var formatted: AttributedString {
        var result = AttributedString()
        for block in MarkdownBlock.parse(text) {
            let source: String
            var heading = false
            switch block {
            case .heading(_, let value): source = value; heading = true
            case .paragraph(let value), .quote(let value), .code(let value): source = value
            case .item(let marker, _, let value): source = marker + " " + value
            case .table(let rows): source = rows.prefix(2).map { $0.joined(separator: " · ") }.joined(separator: "\n")
            case .rule: continue
            }
            if !result.characters.isEmpty { result.append(AttributedString("\n")) }
            var line = (try? AttributedString(markdown: source, options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace))) ?? AttributedString(source)
            line.font = heading ? .subheadline.weight(.semibold) : .footnote
            result.append(line)
        }
        return result
    }
    var body: some View {
        Text(formatted).foregroundStyle(PhoneTheme.secondary)
            .lineSpacing(3).lineLimit(5).truncationMode(.tail)
            .multilineTextAlignment(.leading).fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            .allowsHitTesting(false)
    }
}

private struct ArchivedAutomationsScreen: View {
    @Environment(AssistantStore.self) private var store
    @State private var rows: [AutomationSummary] = []
    @State private var loading = true
    @State private var error: String?
    var body: some View {
        List {
            if loading { ProgressView("Loading archived automations…") }
            if let error { Text(error).foregroundStyle(PhoneTheme.amber) }
            if !loading && rows.isEmpty && error == nil { Text("Nothing archived") }
            ForEach(rows) { automation in
                HStack {
                    Text(automation.name ?? "Automation"); Spacer()
                    Button { Task {
                        if await store.setAutomationArchived(automation, false) { rows.removeAll { $0.id == automation.id } }
                        else { error = store.error }
                    } } label: { Image(systemName: "arrow.uturn.backward").frame(width: 44, height: 44) }
                        .buttonStyle(.plain).disabled(store.automationBusy.contains(automation.id))
                        .accessibilityLabel("Restore automation").accessibilityIdentifier("automation.restore." + automation.id)
                }
            }
        }.navigationTitle("Archived").task { await load() }.refreshable { await load() }
    }
    private func load() async {
        guard let client = store.client else { return }
        loading = true; defer { loading = false }
        do { rows = try await client.archivedAutomations(); error = nil }
        catch { self.error = error.localizedDescription }
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
                    Text(a.triggerWords(store.triggerNames)).foregroundStyle(PhoneTheme.secondary)
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
