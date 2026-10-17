import AbstractGatewayClient
import SwiftUI
import WatchKit

/// A new automation, as the console, the tray app and the terminal create one: the task, the
/// workflow that runs it (the gateway's default first, then the workflows the gateway offers this
/// account), when it runs (the shared presets, or daily at a time), whether each run builds on the
/// earlier ones, and whether it asks before using tools. Create opens its page.
struct NewAutomationView: View {
    @EnvironmentObject private var model: AppModel
    @State private var task = ""
    @State private var workflow: WorkflowChoice?          // nil: the gateway's default
    @State private var workflows: [WorkflowChoice] = []
    @State private var loadingWorkflows = true
    @State private var when: NewAutomation.When = .every("24h")
    @State private var dailyAt = Calendar.current.date(bySettingHour: 8, minute: 0, second: 0, of: Date()) ?? Date()
    @State private var buildsOnEarlierRuns = false
    @State private var askBeforeTools = false
    @State private var choosingWorkflow = false
    @State private var choosingWhen = false
    @State private var creating = false
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
                row(symbol: "square.stack.3d.up", text: workflow?.name ?? "Gateway default") { choosingWorkflow = true }
                    .accessibilityLabel("Workflow: \(workflow?.name ?? "Gateway default")")
                row(symbol: "clock", text: Self.label(when)) { choosingWhen = true }
                    .accessibilityLabel("When: \(Self.label(when))")
                Card { Toggle("Builds on earlier runs", isOn: $buildsOnEarlierRuns).font(.rounded(.footnote, weight: .semibold)).tint(Theme.indigoButton) }
                Card { Toggle("Ask before using tools", isOn: $askBeforeTools).font(.rounded(.footnote, weight: .semibold)).tint(Theme.indigoButton) }
                if let error { Text(error).font(.rounded(.caption2)).foregroundStyle(Theme.red).multilineTextAlignment(.center) }
                Spacer(minLength: 8)
                Button(creating ? "Creating…" : "Create") { Task { await create() } }
                    .buttonStyle(FilledButtonStyle(fill: Theme.indigoButton))
                    .disabled(!ready)
            }
        }
        .screen("New automation")
        .task { await loadWorkflows() }
        .sheet(isPresented: $choosingWorkflow) { workflowList }
        .sheet(isPresented: $choosingWhen) { whenList }
    }

    private func row(symbol: String, text: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Card {
                HStack {
                    Label(text, systemImage: symbol).font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.text).lineLimit(1)
                    Spacer(minLength: 4)
                    Image(systemName: "chevron.right").font(.caption2).foregroundStyle(Theme.muted)
                }
            }
        }
        .buttonStyle(.plain)
    }

    private var workflowList: some View {
        List {
            choice("Gateway default", selected: workflow == nil) { workflow = nil }
            ForEach(workflows) { w in choice(w.name, selected: workflow == w) { workflow = w } }
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

    private func choice(_ text: String, selected: Bool, pick: @escaping () -> Void) -> some View {
        Button {
            pick(); choosingWorkflow = false; choosingWhen = false
        } label: {
            HStack {
                Text(text).font(.rounded(.footnote))
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
            let new = NewAutomation(task: text, target: target, when: when,
                                    buildsOnEarlierRuns: buildsOnEarlierRuns, askBeforeTools: askBeforeTools)
            let created = try await model.client.createAutomation(new)
            WKInterfaceDevice.current().play(.success)
            await model.refresh()
            model.path.removeLast()
            model.path.append(.automation(model.automations.first { $0.id == created.id } ?? created))
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
