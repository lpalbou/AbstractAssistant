import AbstractGatewayClient
import SwiftUI
import WatchKit

/// Your automations, like your conversations: New and Search on one line, then each with its name,
/// when it runs, and the runs you have not seen yet.
struct AutomationsView: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.scenePhase) private var scenePhase
    @State private var archiving: AutomationSummary?

    var body: some View {
        List {
            // One line, as in Sessions: New (an automation) and Search (the keyboard, then the results).
            HStack(spacing: 6) {
                Button { model.path.append(.newAutomation) } label: {
                    TopAction(symbol: "plus", title: "New", color: Theme.cyan)
                }
                .buttonStyle(.tap)
                .accessibilityLabel("New automation")
                TextFieldLink(prompt: Text("Words to find")) {
                    TopAction(symbol: "magnifyingglass", title: "Search", color: Theme.text2)
                } onSubmit: { text in
                    let q = text.trimmingCharacters(in: .whitespacesAndNewlines)
                    if !q.isEmpty { model.path.append(.automationSearch(q)) }
                }
                .buttonStyle(.tap)
                .accessibilityLabel("Search")
                .accessibilityIdentifier("automations.search")
            }
            .listRowBackground(Color.clear)
            .listRowInsets(EdgeInsets(top: 2, leading: 0, bottom: 2, trailing: 0))
            if model.automations.isEmpty {
                if !model.automationsLoaded && (model.automationsLoading || model.automationsError == nil) {
                    ProgressView().frame(maxWidth: .infinity)
                } else if !model.automationsLoaded {
                    // Every retry failed: say so, and offer another.
                    Text("Can't load automations").font(.rounded(.footnote)).foregroundStyle(Theme.muted)
                    Button("Retry") { model.loadAutomations() }
                } else {
                    Text("No automations yet").font(.rounded(.footnote)).foregroundStyle(Theme.muted)
                }
            }
            ForEach(model.automations) { a in AutomationListRow(automation: a) { archiving = a } }
            NavigationLink(value: Route.archivedAutomations) {
                Label("Archived", systemImage: "archivebox").font(.rounded(.footnote)).foregroundStyle(Theme.muted)
            }
            .accessibilityIdentifier("automations.archived")
        }
        .screen("Automations")
        .archivingAutomation($archiving)
        .containerBackground(Theme.ground, for: .navigation)
        .refreshable { model.refreshAutomations(); await model.refresh() }
        // While one runs, its row is read again every 5 s: the spinner goes when it is done.
        .task {
            #if DEBUG
            if ProcessInfo.processInfo.arguments.contains("--run-first"), model.client.isMock {
                while model.automations.isEmpty { try? await Task.sleep(for: .milliseconds(200)) }
            }
            if ProcessInfo.processInfo.arguments.contains("--run-first"), model.client.isMock, let a = model.automations.first {
                try? await model.client.runAutomationNow(id: a.id); model.refreshAutomations()
            }
            #endif
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(5))
                guard scenePhase == .active else { continue }          // dimmed or away: nothing to show
                for a in model.automations where a.currentOccurrence != nil {
                    if let fresh = try? await model.client.automation(id: a.id) { model.replaceAutomation(fresh) }
                }
            }
        }
    }
}

/// An automation's row in a list (the automations, a search): outlined when it has runs you have
/// not seen, as a new answer in Sessions.
struct AutomationListRow: View {
    let automation: AutomationSummary
    let archive: () -> Void
    var body: some View {
        AutomationRow(automation: automation, archive: archive)
            .listRowBackground(SessionRowGround(new: (automation.attention?.unseenCount ?? 0) > 0, tint: Theme.amber))
            .listRowInsets(EdgeInsets(top: 4, leading: 10, bottom: 4, trailing: 4))
    }
}

/// One automation: its name (with a spinner while it runs) and the discreet archive button; when it
/// runs, and the runs you have not seen yet in an orange badge. A tap opens it. (On or off is in Edit.)
struct AutomationRow: View {
    let automation: AutomationSummary
    let archive: () -> Void
    @EnvironmentObject private var model: AppModel

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(alignment: .top, spacing: 4) {
                Button { model.path.append(.automation(automation)) } label: {
                    HStack(spacing: 5) {
                        if automation.lastOccurrence?.status == "failed" { StatusDot(color: Theme.red) }
                        Text(automation.name ?? "Automation").font(.rounded(.footnote, weight: .semibold))
                            .foregroundStyle(Theme.text).lineLimit(2).fixedSize(horizontal: false, vertical: true)
                        Spacer(minLength: 2)
                        if automation.currentOccurrence != nil { ProgressView().frame(width: 18, height: 18).accessibilityLabel("Running") }
                    }
                    .contentShape(Rectangle())
                }
                .buttonStyle(.tap)
                Button(action: archive) {
                    Image(systemName: "archivebox").font(.system(size: 12, weight: .medium))
                        .foregroundStyle(Theme.red.opacity(0.8))
                        .frame(width: 26, height: 26)
                        .background(Theme.red.opacity(0.12), in: Circle())
                        .frame(width: 34, height: 34, alignment: .trailing)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.tap)
                .accessibilityLabel("Archive")
                .accessibilityIdentifier("automation.archive")
            }
            Button { model.path.append(.automation(automation)) } label: {
                HStack(spacing: 4) {
                    ScheduleLine(automation: automation).frame(maxWidth: .infinity, alignment: .leading)
                    if let n = automation.attention?.unseenCount, n > 0 {
                        CountBadge(count: n).padding(.trailing, 6).accessibilityIdentifier("automation.unseen")
                    }
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.tap)
        }
        .padding(.vertical, 2)
    }
}

/// The automations whose name or task holds every word searched (as they are on this watch).
struct AutomationSearchView: View {
    let query: String
    @EnvironmentObject private var model: AppModel
    @State private var archiving: AutomationSummary?

    private var matches: [AutomationSummary] {
        let words = query.split(whereSeparator: \.isWhitespace).map(String.init)
        return model.automations.filter { a in
            let text = (a.name ?? "") + " " + (model.definitions[a.id]?.prompt ?? "")
            return words.allSatisfy { text.localizedCaseInsensitiveContains($0) }
        }
    }

    var body: some View {
        List {
            Text("“\(query)”").font(.rounded(.footnote)).foregroundStyle(Theme.text2).listRowBackground(Color.clear)
            if matches.isEmpty {
                Text("No automation holds these words").font(.rounded(.footnote)).foregroundStyle(Theme.muted)
            }
            ForEach(matches) { a in AutomationListRow(automation: a) { archiving = a } }
        }
        .screen("Search")
        .archivingAutomation($archiving)
        .containerBackground(Theme.ground, for: .navigation)
    }
}

extension View {
    /// "Archive this automation?" for the one set, then it leaves the lists (Archived restores it).
    func archivingAutomation(_ automation: Binding<AutomationSummary?>) -> some View { modifier(ArchivingAutomation(item: automation)) }
}

private struct ArchivingAutomation: ViewModifier {
    @Binding var item: AutomationSummary?
    @EnvironmentObject private var model: AppModel
    @State private var problem: String?
    func body(content: Content) -> some View {
        content
            .sheet(item: $item) { a in
                ArchiveConfirm(title: a.name, what: .automation) { confirmed in
                    item = nil
                    guard confirmed else { return }
                    Task {
                        do { try await model.archiveAutomation(a); WKInterfaceDevice.current().play(.success) }
                        catch { problem = AppModel.say(error) }
                    }
                }
            }
            .alert("That didn't work", isPresented: Binding(get: { problem != nil }, set: { if !$0 { problem = nil } })) {
                Button("OK", role: .cancel) {}
            } message: { Text(problem ?? "") }
    }
}

/// Archived automations (`GET /automations?archived_only=true`), each with Restore.
struct ArchivedAutomationsView: View {
    @EnvironmentObject private var model: AppModel
    @State private var items: [AutomationSummary] = []
    @State private var loading = true
    @State private var failed = false
    @State private var restoring: String?

    var body: some View {
        List {
            if loading && items.isEmpty { ProgressView().frame(maxWidth: .infinity) }
            else if failed { Text("Couldn't load the archived automations").font(.rounded(.footnote)).foregroundStyle(Theme.muted) }
            else if items.isEmpty { Text("Nothing archived").font(.rounded(.footnote)).foregroundStyle(Theme.muted) }
            ForEach(items) { a in
                VStack(alignment: .leading, spacing: 4) {
                    Text(a.name ?? "Automation").font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.text).lineLimit(2)
                    Button(restoring == a.id ? "Restoring…" : "Restore") { restore(a) }
                        .buttonStyle(FilledButtonStyle(fill: Theme.neutralButton, font: .rounded(.footnote, weight: .semibold)))
                        .disabled(restoring != nil)
                        .accessibilityIdentifier("archived.automation.restore")
                }
            }
        }
        .screen("Archived")
        .task {
            defer { loading = false }
            do { items = try await model.client.archivedAutomations(); failed = false } catch { failed = true }
        }
    }

    private func restore(_ a: AutomationSummary) {
        restoring = a.id
        Task {
            do { try await model.unarchiveAutomation(a.id); items.removeAll { $0.id == a.id }; WKInterfaceDevice.current().play(.success) }
            catch { failed = true }
            restoring = nil
        }
    }
}
