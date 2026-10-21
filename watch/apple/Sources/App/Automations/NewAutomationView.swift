import AbstractGatewayClient
import SwiftUI
import WatchKit

/// A new automation, as the console, the tray app and the terminal create one: the task, the
/// workflow that runs it (the gateway's default, named, then the others it offers this account),
/// the tools its runs may use (the Tools page, from the defaults), when it runs (the shared presets,
/// or daily at a time) and whether each run builds on the earlier ones. Create opens its page.
struct NewAutomationView: View {
    @EnvironmentObject private var model: AppModel
    @State private var task = ""
    @State private var workflow: WorkflowChoice?          // nil: the gateway's default (`@default`)
    @State private var workflows: [WorkflowChoice] = []
    @State private var loadingWorkflows = true
    @State private var when: NewAutomation.When = .every("24h")
    @State private var dailyAt = Calendar.current.date(bySettingHour: 8, minute: 0, second: 0, of: Date()) ?? Date()
    @State private var buildsOnEarlierRuns = false
    /// How much of its earlier runs each run reads (the gateway's default until changed).
    @State private var tokens: Int?
    @State private var choosingWorkflow = false
    @State private var choosingWhen = false
    @State private var creating = false
    @State private var started = false
    @State private var error: String?

    /// The agent interface the watch runs (its Ask uses the same).
    static let interface = "abstractcode.agent.v1"
    /// The presets every client offers (the UI kit's `SCHEDULE_PRESETS`).
    static let presets = ["5m", "30m", "1h", "8h", "24h", "7d"]

    private var ready: Bool { !task.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !creating }

    var body: some View {
        FitScroll {
            VStack(spacing: 6) {
                TextField("What should it do?", text: $task, axis: .vertical)
                    .lineLimit(1...6).font(.rounded(.footnote)).accessibilityIdentifier("new.task")
                Button { choosingWorkflow = true } label: { row("Workflow", symbol: "square.stack.3d.up", value: workflowLabel) }
                    .buttonStyle(.tap)
                    .accessibilityLabel("Workflow: \(workflowLabel)").accessibilityIdentifier("new.workflow")
                // What the agent may do on each run: the Tools page, for this automation.
                NavigationLink(value: Route.tools(.draft)) { row("Tools", symbol: "wrench.and.screwdriver", value: toolsLabel) }
                    .buttonStyle(.tap)
                    .accessibilityLabel("Tools: \(toolsLabel)").accessibilityIdentifier("new.tools")
                Button { choosingWhen = true } label: { row("When", symbol: "clock", value: Self.label(when)) }
                    .buttonStyle(.tap)
                    .accessibilityLabel("When: \(Self.label(when))")
                MemoryCard(remembers: $buildsOnEarlierRuns, tokens: $tokens, id: "new.tokens")
                if let error { Text(error).font(.rounded(.caption2)).foregroundStyle(Theme.red).multilineTextAlignment(.center) }
                Spacer(minLength: 8)
                Button(creating ? "Creating…" : "Create") { Task { await create() } }
                    .buttonStyle(FilledButtonStyle(fill: Theme.indigoButton))
                    .disabled(!ready)
            }
        }
        .screen("New automation")
        .task { await loadWorkflows() }
        .task { await model.ensureTools(maxAge: 600) }
        // The gateway's default memory, shown until a number is typed.
        .task { if tokens == nil { tokens = try? await model.client.automationDefaults().growingMaxTokens } }
        // A new automation starts from the defaults (once: coming back from its Tools keeps them).
        .onAppear { if !started { started = true; model.startDraftTools() } }
        .sheet(isPresented: $choosingWorkflow) { workflowList }
        .sheet(isPresented: $choosingWhen) { whenList }
    }

    /// One choice: what it is (small), then what is chosen.
    private func row(_ title: String, symbol: String, value: String) -> some View {
        Card {
            HStack(spacing: 8) {
                Image(systemName: symbol).font(.system(size: 13, weight: .semibold)).foregroundStyle(Theme.cyan).frame(width: 18)
                VStack(alignment: .leading, spacing: 1) {
                    Text(title).font(.rounded(.caption2)).foregroundStyle(Theme.muted)
                    Text(value).font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.text).lineLimit(2).fixedSize(horizontal: false, vertical: true)
                        .minimumScaleFactor(0.85)
                }
                Spacer(minLength: 4)
                Image(systemName: "chevron.right").font(.caption2).foregroundStyle(Theme.muted)
            }
        }
    }

    /// The gateway's default by its name (the workflow behind `@default`), or the one chosen.
    private var defaultWorkflow: WorkflowChoice? { workflows.first(where: \.isDefault) }
    private var workflowLabel: String {
        if let w = workflow { return w.name }
        if let d = defaultWorkflow { return "\(d.name) · default" }
        return loadingWorkflows ? "Loading…" : "Default workflow"
    }

    private var toolsLabel: String {
        guard model.toolPlan(.draft) != nil else { return "Loading…" }
        let modes = model.tools.values.filter(\.offered).map { model.toolMode($0, scope: .draft) }
        let summary = ToolGroup.counts(modes)
        return model.draftTools.isEmpty ? summary : summary + " · changed"
    }

    /// The default first (choosing it follows the gateway's default), then the others.
    private var workflowList: some View {
        List {
            if let d = defaultWorkflow {
                choice(d.name, detail: "Default", selected: workflow == nil) { workflow = nil }
            } else if !loadingWorkflows {
                choice("Default workflow", selected: workflow == nil) { workflow = nil }
            }
            ForEach(workflows.filter { !$0.isDefault }) { w in choice(w.name, selected: workflow == w) { workflow = w } }
            if loadingWorkflows { ProgressView().frame(maxWidth: .infinity) }
        }
    }

    private var whenList: some View {
        List {
            ForEach(Self.presets, id: \.self) { e in
                choice(AutomationEditView.label(e), selected: when == .every(e)) { when = .every(e) }
            }
            DatePicker("Daily at", selection: $dailyAt, displayedComponents: .hourAndMinute)
                .font(.rounded(.footnote))
            choice("Every day at \(Self.clock(dailyAt))", selected: when == .daily(at: Self.clock(dailyAt))) {
                when = .daily(at: Self.clock(dailyAt))
            }
        }
    }

    private func choice(_ text: String, detail: String? = nil, selected: Bool, pick: @escaping () -> Void) -> some View {
        Button {
            pick(); choosingWorkflow = false; choosingWhen = false
        } label: {
            HStack {
                VStack(alignment: .leading, spacing: 1) {
                    Text(text).font(.rounded(.footnote))
                    if let detail { Text(detail).font(.rounded(.caption2)).foregroundStyle(Theme.muted) }
                }
                Spacer()
                if selected { Image(systemName: "checkmark").foregroundStyle(Theme.cyan) }
            }
        }
    }

    private func loadWorkflows() async {
        defer { loadingWorkflows = false }
        workflows = (try? await model.client.workflows(forInterface: Self.interface)) ?? []
    }

    private func create() async {
        creating = true; error = nil
        defer { creating = false }
        let text = task.trimmingCharacters(in: .whitespacesAndNewlines)
        do {
            let target: NewAutomation.Target
            if let w = workflow {
                switch try await model.client.workflowInputs(w).inputData(task: text) {
                case .success(let input): target = .workflow(w, inputData: input)
                case .failure(let missing):
                    error = "\(w.name) also needs \(missing.names.joined(separator: ", ")). Create it on your Mac."
                    return
                }
            } else {
                target = .gatewayDefault(interface: Self.interface)
            }
            // Its tools, read fresh: without them it is not created (the workflow's own tools and the
            // gateway's grant would ignore what was turned off).
            await model.ensureTools(maxAge: 600)
            guard let tools = model.toolPlan(.draft) else {
                error = "Couldn't read your tools. Try again."
                return
            }
            var new = NewAutomation(task: text, target: target, when: when, buildsOnEarlierRuns: buildsOnEarlierRuns, tools: tools)
            new.growingMaxTokens = tokens
            let created = try await model.client.createAutomation(new)
            WKInterfaceDevice.current().play(.success)
            model.refreshAutomations()
            model.path.removeLast()
            model.path.append(.automation(created))
        } catch {
            self.error = AppModel.say(error)
        }
    }

    static func label(_ w: NewAutomation.When) -> String {
        switch w {
        case .every(let e): AutomationEditView.label(e)
        case .daily(let at): "Every day at \(at)"
        }
    }

    /// "08:00": the time the gateway reads in the account's time zone.
    static func clock(_ d: Date) -> String {
        let c = Calendar.current.dateComponents([.hour, .minute], from: d)
        return String(format: "%02d:%02d", c.hour ?? 0, c.minute ?? 0)
    }
}
