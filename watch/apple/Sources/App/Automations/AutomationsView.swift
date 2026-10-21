import AbstractGatewayClient
import SwiftUI
import WatchKit

/// Your automations, like your conversations: a name, when it runs, how many new results.
struct AutomationsView: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.scenePhase) private var scenePhase
    @State private var archiving: AutomationSummary?
    @State private var problem: String?

    var body: some View {
        List {
            // A new automation (as Sessions starts a new conversation).
            Button { model.path.append(.newAutomation) } label: {
                Label("New automation", systemImage: "plus")
                    .font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.cyan)
            }
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
            ForEach(model.automations) { a in
                AutomationRow(automation: a, archive: { archiving = a })
                    // New results you have not seen: outlined, as a new answer in Sessions.
                    .listRowBackground(SessionRowGround(new: (a.attention?.unseenCount ?? 0) > 0, tint: Theme.amber))
                    .listRowInsets(EdgeInsets(top: 4, leading: 10, bottom: 4, trailing: 4))
            }
            NavigationLink(value: Route.archivedAutomations) {
                Label("Archived", systemImage: "archivebox").font(.rounded(.footnote)).foregroundStyle(Theme.muted)
            }
            .accessibilityIdentifier("automations.archived")
        }
        .screen("Automations")
        .sheet(item: $archiving) { a in
            ArchiveConfirm(title: a.name, what: .automation) { confirmed in
                archiving = nil
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

/// One automation: its name (with a spinner while it runs, its count of new results) and the
/// discreet archive button; its schedule with the switch that turns it on or off. A tap opens it.
struct AutomationRow: View {
    let automation: AutomationSummary
    let archive: () -> Void
    @EnvironmentObject private var model: AppModel
    @State private var switching = false
    @State private var problem: String?

    private var switchable: Bool { automation.status == "active" || automation.status == "paused" }

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
                        else if let n = automation.attention?.unseenCount, n > 0 { Pill(text: "\(n)", color: Theme.amber) }
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
            HStack(spacing: 4) {
                Button { model.path.append(.automation(automation)) } label: {
                    ScheduleLine(automation: automation).frame(maxWidth: .infinity, alignment: .leading).contentShape(Rectangle())
                }
                .buttonStyle(.tap)
                if switchable {
                    Toggle(isOn: Binding(get: { automation.status == "active" }, set: { on in flip(on) })) { EmptyView() }
                        .labelsHidden()
                        .tint(Theme.greenButton)
                        .disabled(switching)
                        .accessibilityLabel(automation.status == "active" ? "On" : "Off")
                        .accessibilityIdentifier("automation.active")
                }
            }
            if let problem { Text(problem).font(.rounded(.caption2)).foregroundStyle(Theme.red) }
        }
        .padding(.vertical, 2)
    }

    private func flip(_ on: Bool) {
        switching = true; problem = nil
        WKInterfaceDevice.current().play(.click)
        Task {
            do { try await model.setActive(automation, on) } catch { problem = AppModel.say(error) }
            switching = false
        }
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
