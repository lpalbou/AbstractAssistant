import SwiftUI
import AssistantKit
import AbstractGatewayClient

struct NewAutomationScreen: View {
    var onCreated: (AutomationSummary) -> Void
    @Environment(AssistantStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    @State private var title = ""
    @FocusState private var editingTitle: Bool
    @State private var task = ""
    @FocusState private var editingTask: Bool
    @FocusState private var editingInput: String?
    @State private var workflowID = ""
    @State private var workflows: [WorkflowChoice] = []
    @State private var inputSpec: WorkflowInputs?
    @State private var inputText: [String: String] = [:]
    @State private var inputsLoading = false
    @State private var inputError: String?
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
    private var needsTask: Bool { workflowID.isEmpty || inputSpec?.fields == nil || inputSpec?.fields?.contains(where: { $0.id == "prompt" }) == true }
    private var budgetText: String { historyBudget.trimmingCharacters(in: .whitespacesAndNewlines) }
    private var customHistoryBudget: Int? { Int(budgetText).flatMap { $0 > 0 ? $0 : nil } }
    private var invalidHistoryBudget: Bool { growing && !budgetText.isEmpty && customHistoryBudget == nil }
    private var budgetPlaceholder: String { gatewayHistoryBudget.map { "Gateway default · " + $0.formatted() } ?? "Gateway default" }
    private var fingerprint: String { [title, task, workflowID, frequency, String(hour), String(minute), String(growing), growing ? budgetText : "", inputText.keys.sorted().map { $0 + ":" + (inputText[$0] ?? "") }.joined(separator: "|"), tools?.fingerprint ?? (store.appTools?.fingerprint ?? "gateway")].joined(separator: "|") }
    var body: some View {
        NavigationStack {
            Form {
                Section("Title") {
                    TextField("Morning briefing", text: $title)
                        .focused($editingTitle).submitLabel(.next)
                        .accessibilityIdentifier("automation.title")
                        .onSubmit { editingTitle = false; editingTask = true }
                    if title.trimmingCharacters(in: .whitespacesAndNewlines).count > 120 {
                        Text("Use 120 characters or fewer.").font(.footnote).foregroundStyle(PhoneTheme.amber)
                    }
                }
                if needsTask {
                    Section("What should it do?") {
                        TextField("Describe the task…", text: $task, axis: .vertical).lineLimit(3...8).accessibilityIdentifier("automation.task").focused($editingTask)
                    }
                }
                Section {
                    Picker("Workflow", selection: $workflowID) {
                        Text("Gateway default").tag("")
                        ForEach(workflows) { w in Text(w.name).tag(w.id) }
                    }.accessibilityIdentifier("automation.workflow")
                } footer: { Text("Choose any runnable workflow available on your gateway. Gateway default uses its Assistant workflow, independently of your chat selection.") }
                if inputsLoading { Section { ProgressView("Loading workflow inputs…") } }
                if let inputError { Section { ErrorBanner(message: inputError); Button("Retry loading inputs") { Task { await loadInputs() } } } }
                if let inputSpec, !inputSpec.editableFields.isEmpty {
                    Section("Workflow inputs") {
                        ForEach(inputSpec.editableFields) { field in workflowField(field) }
                    }
                }
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
                    Button { editingTitle = false; editingTask = false; editingBudget = false; editingInput = nil; showTools = true } label: {
                        HStack { Label("Tools", systemImage: "wrench.and.screwdriver").foregroundStyle(PhoneTheme.tool); Spacer(); Text(tools == nil ? "Settings defaults" : "Custom").foregroundStyle(PhoneTheme.secondary); Image(systemName: "chevron.right").font(.caption) }
                    }.accessibilityIdentifier("automation.tools")
                } footer: { Text("Tool permissions are saved with the automation so it can run while this iPhone is closed.") }
                if let error { Section { ErrorBanner(message: error) } }
                Section {
                    Button { Task { await create() } } label: {
                        HStack(spacing: 10) {
                            if creating { ProgressView().tint(PhoneTheme.ground) }
                            else { Image(systemName: pending == nil ? "plus.circle.fill" : "arrow.clockwise") }
                            Text(creating ? "Creating…" : pending == nil ? "Create automation" : "Retry creation").fontWeight(.semibold)
                        }.frame(maxWidth: .infinity).padding(.vertical, 8)
                    }.buttonStyle(.borderedProminent).tint(PhoneTheme.mint).foregroundStyle(PhoneTheme.ground)
                    .disabled(inputsLoading || inputError != nil || title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || title.trimmingCharacters(in: .whitespacesAndNewlines).count > 120 || (needsTask && task.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty) || invalidHistoryBudget || creating || loading).accessibilityIdentifier("automation.create")
                }.listRowBackground(Color.clear).listRowInsets(EdgeInsets())
                if loading { ProgressView("Loading workflows…") }
            }.disabled(creating).scrollContentBackground(.hidden).background(PhoneTheme.ground).navigationTitle("New automation").navigationBarTitleDisplayMode(.inline)
                .scrollDismissesKeyboard(.interactively)
                .background(OutsideInputDismissal(focused: editingTitle || editingTask || editingBudget || editingInput != nil, dismiss: { editingTitle = false; editingTask = false; editingBudget = false; editingInput = nil }))
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() }.disabled(creating) } }
                .interactiveDismissDisabled(creating).task { await load() }.task(id: workflowID) { await loadInputs() }.onChange(of: fingerprint) { _, _ in pending = nil }
                .sheet(isPresented: $showTools) {
                    ConversationToolsScreen(scope: .automation, automationSelection: tools) { selection in tools = selection }
                }
        }
    }
    @ViewBuilder private func workflowField(_ field: WorkflowInput) -> some View {
        let binding = Binding(get: { inputText[field.id] ?? "" }, set: { inputText[field.id] = $0 })
        VStack(alignment: .leading, spacing: 6) {
            if ["boolean", "bool"].contains(field.type) {
                Toggle(field.label, isOn: Binding(get: { binding.wrappedValue == "true" }, set: { binding.wrappedValue = $0 ? "true" : "false" }))
                    .accessibilityIdentifier("automation.input." + field.id)
            } else if let choices = field.choices {
                Picker(field.label, selection: binding) {
                    Text(field.required ? "Choose a value" : "Workflow default").tag("")
                    ForEach(choices, id: \.self) { choice in Text(WorkflowInput.text(choice)).tag(WorkflowInput.text(choice)) }
                }.accessibilityIdentifier("automation.input." + field.id)
            } else {
                Text(field.label + (field.required ? " · Required" : "")).font(.subheadline)
                TextField(["object", "dict", "array", "list", "any", "unknown", "json"].contains(field.type) ? "JSON " + field.type : field.label, text: binding, axis: .vertical)
                    .lineLimit(1...6).focused($editingInput, equals: field.id).textInputAutocapitalization(.never).autocorrectionDisabled()
                    .accessibilityIdentifier("automation.input." + field.id)
            }
            if let description = field.description, !description.isEmpty { Text(description).font(.caption).foregroundStyle(PhoneTheme.secondary) }
        }.padding(.vertical, 3)
    }
    private func loadInputs() async {
        let selected = workflowID, context = store.contextID
        inputSpec = nil; inputText = [:]; inputError = nil; inputsLoading = false
        guard let client = store.client, let workflow = workflows.first(where: { $0.id == selected }) else { return }
        inputsLoading = true
        do {
            let spec = try await client.workflowInputs(workflow)
            guard !Task.isCancelled, context == store.contextID, selected == workflowID else { return }
            inputSpec = spec
            for field in spec.editableFields {
                if let value = spec.defaults[field.id] { inputText[field.id] = WorkflowInput.text(value) }
                else if field.required && ["boolean", "bool"].contains(field.type) { inputText[field.id] = "false" }
            }
            inputsLoading = false
        } catch {
            guard !Task.isCancelled, context == store.contextID, selected == workflowID else { return }
            inputsLoading = false; inputError = error.localizedDescription
            if error as? GatewayError == .unauthorized { store.authenticationExpired() }
        }
    }
    private func load() async {
        guard let client = store.client else { return }; let context = store.contextID; defer { loading = false }
        do {
            let result = try await client.workflows(forInterface: ""); guard context == store.contextID else { return }; workflows = result
            let prefs = try await client.accountPreferences(); guard context == store.contextID else { return }
            zone = prefs["time_zone"]?["effective"]?.stringValue ?? zone
            do {
                let budget = try await client.defaultGrowingMaxTokens(); guard context == store.contextID else { return }
                gatewayHistoryBudget = budget.flatMap { $0 > 0 ? $0 : nil }
            } catch {
                guard context == store.contextID else { return }
                gatewayHistoryBudget = nil
                if error as? GatewayError == .unauthorized { fail(error) }
            }
        } catch { if context == store.contextID { fail(error) } }
    }
    private func create() async {
        guard let client = store.client, !creating, !invalidHistoryBudget, !needsTask || !task.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, !title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, title.trimmingCharacters(in: .whitespacesAndNewlines).count <= 120 else { return }; let context = store.contextID; creating = true; error = nil
        defer { creating = false }
        do {
            if pending == nil {
                let inventory = try await client.tools()
                guard context == store.contextID else { return }
                let snapshot = ConversationTools.snapshot(tools ?? store.appTools, inventory: inventory)
                let target: NewAutomation.Target
                let text = task.trimmingCharacters(in: .whitespacesAndNewlines)
                if let w = workflows.first(where: { $0.id == workflowID }) {
                    guard let inputSpec, !inputsLoading, inputError == nil else { error = "Wait for the workflow inputs to load."; return }
                    let overrides = try inputSpec.overrides(from: inputText)
                    switch inputSpec.inputData(task: text, tools: snapshot.allowed, overrides: overrides) {
                    case .success(let values): target = .workflow(w, inputData: values)
                    case .failure(let missing): error = "This workflow also requires: " + missing.names.joined(separator: ", ") + ". Complete its workflow inputs above."; return
                    }
                } else if workflowID.isEmpty { target = .gatewayDefault(interface: "abstractassistant.agent.v1") }
                else { error = "Choose an available workflow."; return }
                pending = NewAutomation(task: text, target: target, when: frequency == "daily" ? .daily(at: String(format: "%02d:%02d", hour, minute)) : .every(frequency), buildsOnEarlierRuns: growing, askBeforeTools: true, growingMaxTokens: growing ? customHistoryBudget : nil, tools: snapshot, title: title)
            }
            guard context == store.contextID, let pending else { return }
            let created = try await client.createAutomation(pending); guard context == store.contextID else { return }
            store.rememberAutomation(created)
            await store.refresh(); guard context == store.contextID else { return }; onCreated(created); dismiss()
        } catch { if context == store.contextID { fail(error) } }
    }
    private func fail(_ e: Error) { error = e.localizedDescription + (pending == nil ? "" : " Check the list before creating another routine. Retry reuses this request to avoid duplicates."); if e as? GatewayError == .unauthorized { store.authenticationExpired() } }
}
