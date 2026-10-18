import SwiftUI
import AssistantKit
import AbstractGatewayClient

struct NewAutomationScreen: View {
    var onCreated: (AutomationSummary) -> Void
    @Environment(AssistantStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    @State private var task = ""
    @FocusState private var editingTask: Bool
    @State private var workflowID = ""
    @State private var workflows: [WorkflowChoice] = []
    @State private var frequency = "24h"
    @State private var hour = 8
    @State private var minute = 0
    @State private var growing = false
    @State private var historyBudget = ""
    @State private var gatewayHistoryBudget: Int?
    @FocusState private var editingBudget: Bool
    @State private var tools: ConversationTools?
    @State private var showTools = false
    @State private var zone = "your account’s time zone"
    @State private var creating = false
    @State private var loading = true
    @State private var error: String?
    @State private var pending: NewAutomation?
    private var budgetText: String { historyBudget.trimmingCharacters(in: .whitespacesAndNewlines) }
    private var customHistoryBudget: Int? { Int(budgetText).flatMap { $0 > 0 ? $0 : nil } }
    private var invalidHistoryBudget: Bool { growing && !budgetText.isEmpty && customHistoryBudget == nil }
    private var budgetPlaceholder: String { gatewayHistoryBudget.map { "Gateway default · " + $0.formatted() } ?? "Gateway default" }
    private var fingerprint: String { [task, workflowID, frequency, String(hour), String(minute), String(growing), growing ? budgetText : "", tools?.fingerprint ?? (store.appTools?.fingerprint ?? "gateway")].joined(separator: "|") }
    var body: some View {
        NavigationStack {
            Form {
                Section("What should it do?") {
                    TextField("Describe the task…", text: $task, axis: .vertical).lineLimit(3...8).accessibilityIdentifier("automation.task").focused($editingTask)
                }
                Section {
                    Picker("Workflow", selection: $workflowID) {
                        Text("Gateway default").tag("")
                        ForEach(workflows) { w in Text(w.name).tag(w.id) }
                    }
                } footer: { Text("Choose a schedulable Assistant workflow. Gateway default follows the gateway’s Assistant default, independently of your account’s chat selection.") }
                Section("When") {
                    Picker("Repeat", selection: $frequency) {
                        Text("Every 5 minutes").tag("5m"); Text("Every 30 minutes").tag("30m"); Text("Every hour").tag("1h")
                        Text("Every 8 hours").tag("8h"); Text("Every 24 hours").tag("24h"); Text("Every week").tag("7d"); Text("Daily at a time").tag("daily")
                    }
                    if frequency == "daily" {
                        HStack {
                            Picker("Hour", selection: $hour) { ForEach(0..<24) { Text(String(format: "%02d", $0)).tag($0) } }
                            Picker("Minute", selection: $minute) { ForEach(0..<60) { Text(String(format: "%02d", $0)).tag($0) } }
                        }
                        Text("Daily at \(String(format: "%02d:%02d", hour, minute)) · \(zone)").font(.footnote).foregroundStyle(PhoneTheme.secondary)
                    }
                }
                Section {
                    Toggle("Build on earlier runs", isOn: $growing)
                        .accessibilityIdentifier("automation.growing")
                    if growing {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("History token budget").font(.subheadline)
                            TextField(budgetPlaceholder, text: $historyBudget)
                                .keyboardType(.numberPad).focused($editingBudget)
                                .accessibilityLabel("History token budget")
                                .accessibilityIdentifier("automation.historyBudget")
                        }.padding(.vertical, 4)
                        if invalidHistoryBudget { Text("Enter a positive whole number, or leave blank for the gateway default.").font(.footnote).foregroundStyle(PhoneTheme.amber) }
                    }
                } footer: {
                    if growing { Text("Keeps history from earlier runs within this token budget. Leave blank to use the gateway default" + (gatewayHistoryBudget.map { " (" + $0.formatted() + " tokens)." } ?? "; the gateway sets the limit when created.")) }
                }
                Section {
                    Button { editingTask = false; editingBudget = false; showTools = true } label: {
                        HStack { Label("Tools", systemImage: "wrench.and.screwdriver"); Spacer(); Text(tools == nil ? "Settings defaults" : "Custom").foregroundStyle(PhoneTheme.secondary); Image(systemName: "chevron.right").font(.caption) }
                    }.accessibilityIdentifier("automation.tools")
                } footer: { Text("Tool permissions are saved with the automation so it can run while this iPhone is closed.") }
                if let error { Section { ErrorBanner(message: error) } }
                Section { Button(creating ? "Creating…" : pending == nil ? "Create automation" : "Retry creation") { Task { await create() } }.disabled(task.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || invalidHistoryBudget || creating || loading).accessibilityIdentifier("automation.create") }
                if loading { ProgressView("Loading workflows…") }
            }.disabled(creating).scrollContentBackground(.hidden).background(PhoneTheme.ground).navigationTitle("New automation").navigationBarTitleDisplayMode(.inline)
                .scrollDismissesKeyboard(.interactively)
                .background(OutsideInputDismissal(focused: editingTask || editingBudget, dismiss: { editingTask = false; editingBudget = false }))
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() }.disabled(creating) } }
                .interactiveDismissDisabled(creating).task { await load() }.onChange(of: fingerprint) { _, _ in pending = nil }
                .sheet(isPresented: $showTools) {
                    ConversationToolsScreen(scope: .automation, automationSelection: tools) { selection in tools = selection }
                }
        }
    }
    private func load() async {
        guard let client = store.client else { return }; let context = store.contextID; defer { loading = false }
        do {
            let result = try await client.workflows(forInterface: "abstractassistant.agent.v1"); guard context == store.contextID else { return }; workflows = result
            let prefs = try await client.accountPreferences(); guard context == store.contextID else { return }
            zone = prefs["time_zone"]?["effective"]?.stringValue ?? zone
            do {
                let budget = try await client.automationDefaults(); guard context == store.contextID else { return }
                gatewayHistoryBudget = budget.flatMap { $0 > 0 ? $0 : nil }
            } catch {
                guard context == store.contextID else { return }
                gatewayHistoryBudget = nil
                if error as? GatewayError == .unauthorized { fail(error) }
            }
        } catch { if context == store.contextID { fail(error) } }
    }
    private func create() async {
        guard let client = store.client, !creating, !invalidHistoryBudget else { return }; let context = store.contextID; creating = true; error = nil
        defer { creating = false }
        do {
            if pending == nil {
                let inventory = try await client.tools()
                guard context == store.contextID else { return }
                let snapshot = ConversationTools.snapshot(tools ?? store.appTools, inventory: inventory)
                let target: NewAutomation.Target
                let text = task.trimmingCharacters(in: .whitespacesAndNewlines)
                if let w = workflows.first(where: { $0.id == workflowID }) {
                    switch try await client.workflowInputs(w).inputData(task: text, tools: snapshot.allowed) {
                    case .success(let values): target = .workflow(w, inputData: values)
                    case .failure(let missing): error = "This workflow also requires: " + missing.names.joined(separator: ", ") + ". Choose another workflow or configure those inputs in the gateway console."; return
                    }
                } else if workflowID.isEmpty { target = .gatewayDefault(interface: "abstractassistant.agent.v1") }
                else { error = "Choose an available workflow."; return }
                pending = NewAutomation(task: text, target: target, when: frequency == "daily" ? .daily(at: String(format: "%02d:%02d", hour, minute)) : .every(frequency), buildsOnEarlierRuns: growing, askBeforeTools: true, growingMaxTokens: growing ? customHistoryBudget : nil, tools: snapshot)
            }
            guard context == store.contextID, let pending else { return }
            let created = try await client.createAutomation(pending); guard context == store.contextID else { return }
            store.rememberAutomation(created)
            await store.refresh(); guard context == store.contextID else { return }; onCreated(created); dismiss()
        } catch { if context == store.contextID { fail(error) } }
    }
    private func fail(_ e: Error) { error = e.localizedDescription + (pending == nil ? "" : " Check the list before creating another routine. Retry reuses this request to avoid duplicates."); if e as? GatewayError == .unauthorized { store.authenticationExpired() } }
}
