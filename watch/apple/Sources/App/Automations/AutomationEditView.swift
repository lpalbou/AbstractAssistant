import AbstractGatewayClient
import SwiftUI
import WatchKit

/// Change an automation from the wrist: its title, its task (what it is asked each run) and its
/// instructions (how it works), each in its own field holding the current text so editing starts
/// from it; how often it runs, whether each run builds on the earlier ones, and whether it runs at
/// all. A title that is the task follows the task while the title itself is not edited. Save sends
/// only what changed, with the revision it was read at (a change made elsewhere meanwhile is
/// refused); leaving with changes asks to save or discard them. The definition is the one its page
/// already read (shown at once), and a save updates it for every page.
struct AutomationEditView: View {
    let automation: AutomationSummary
    @EnvironmentObject private var model: AppModel
    @State private var every: String
    @State private var remembers: Bool
    @State private var active: Bool
    @State private var saving = false
    @State private var error: String?
    @State private var choosingEvery = false
    /// The committed definition (the task lives there, not in the list row); nil until read.
    @State private var definition: AutomationDefinition?
    @State private var task = ""
    @State private var title = ""
    @State private var instructions = ""
    /// Back with changes: Save or Discard.
    @State private var leaving = false
    /// The title was typed in (else a title that is the task follows the task).
    @State private var titleEdited = false
    @State private var loadFailed = false

    private static let presets = ["30m", "1h", "2h", "4h", "6h", "8h", "12h", "24h", "7d"]

    init(automation: AutomationSummary) {
        self.automation = automation
        _every = State(initialValue: automation.every ?? "")
        _remembers = State(initialValue: automation.contextMode != "independent")
        _active = State(initialValue: automation.status != "paused")
    }

    private var everyChanged: Bool { automation.every != nil && every != automation.every }
    private var remembersChanged: Bool { remembers != (automation.contextMode != "independent") }
    private var activeChanged: Bool { active != (automation.status != "paused") }
    private var taskChanged: Bool {
        guard let before = definition?.prompt else { return false }
        let t = task.trimmingCharacters(in: .whitespacesAndNewlines)
        return !t.isEmpty && t != before.trimmingCharacters(in: .whitespacesAndNewlines)
    }
    private var titleChanged: Bool {
        let t = title.trimmingCharacters(in: .whitespacesAndNewlines)
        return !t.isEmpty && t != (definition?.title ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    }
    private var instructionsChanged: Bool {
        guard definition != nil else { return false }
        return instructions.trimmingCharacters(in: .whitespacesAndNewlines) != (definition?.instructions ?? "")
    }
    private var changed: Bool { titleChanged || taskChanged || instructionsChanged || everyChanged || remembersChanged || activeChanged }

    var body: some View {
        FitScroll {
            VStack(spacing: 6) {
                // Real text fields: they show the current text, and editing starts from it.
                if definition != nil {
                    field("Title") {
                        TextField("Title", text: Binding(get: { title }, set: { title = $0; titleEdited = true }), axis: .vertical)
                            .lineLimit(1...4).font(.rounded(.footnote)).accessibilityIdentifier("edit.title")
                    }
                    field("Task") {
                        TextField("Task", text: $task, axis: .vertical).lineLimit(1...10)
                            .font(.rounded(.footnote)).accessibilityIdentifier("edit.task")
                    }
                    field("Instructions") {
                        TextField("None", text: $instructions, axis: .vertical).lineLimit(1...10)
                            .font(.rounded(.footnote)).accessibilityIdentifier("edit.instructions")
                    }
                } else if loadFailed {
                    Text("Couldn't load this automation").font(.rounded(.caption2)).foregroundStyle(Theme.muted)
                } else {
                    ProgressView().frame(maxWidth: .infinity, minHeight: 44)
                }
                if automation.every != nil {
                    // A row like the others; the choice opens as a list.
                    Button { choosingEvery = true } label: {
                        Card {
                            HStack {
                                Label(ScheduleLine.compact(every), systemImage: "clock")
                                    .font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.text)
                                Spacer(minLength: 4)
                                Image(systemName: "chevron.right").font(.caption2).foregroundStyle(Theme.muted)
                            }
                        }
                    }
                    .buttonStyle(.tap)
                    .accessibilityLabel(Self.label(every))
                }
                Card { Toggle("Active", isOn: $active).font(.rounded(.footnote, weight: .semibold)).tint(Theme.indigoButton) }
                Card { Toggle("Builds on earlier runs", isOn: $remembers).font(.rounded(.footnote, weight: .semibold)).tint(Theme.indigoButton) }
                if let error { Text(error).font(.rounded(.caption2)).foregroundStyle(Theme.red).multilineTextAlignment(.center) }
                Spacer(minLength: 8)
                Button(saving ? "Saving…" : "Save") { Task { await save() } }
                    .buttonStyle(FilledButtonStyle(fill: Theme.indigoButton))
                    .disabled(!changed || saving)
            }
        }
        .screen("Edit")
        .task {
            do {
                let d = try await model.definition(of: automation.id)
                definition = d
                task = d.prompt ?? ""
                title = d.title ?? automation.name ?? ""
                instructions = d.instructions ?? ""
            } catch { loadFailed = true }
        }
        // Back (the corner button or a swipe) with unsaved changes asks first (they used to vanish
        // without a word).
        .onChange(of: changed, initial: true) { _, c in model.guardBack(of: .automationEdit(automation), c ? { leaving = true } : nil) }
        .onDisappear { model.guardBack(of: .automationEdit(automation), nil) }
        .confirmationDialog("Save your changes?", isPresented: $leaving) {
            Button("Save") { Task { await save() } }
            Button("Discard", role: .destructive) { model.path.removeLast() }
        }
        .onChange(of: task) { _, new in
            guard !titleEdited, let d = definition,
                  let t = AutomationDefinition.title(afterTask: new.trimmingCharacters(in: .whitespacesAndNewlines), oldTitle: d.title, oldTask: d.prompt)
            else { return }
            title = t
        }
        .sheet(isPresented: $choosingEvery) {
            List(options, id: \.self) { e in
                Button { every = e; choosingEvery = false } label: {
                    HStack {
                        Text(Self.label(e)).font(.rounded(.footnote))
                        Spacer()
                        if e == every { Image(systemName: "checkmark").foregroundStyle(Theme.cyan) }
                    }
                }
            }
        }
    }

    /// A small label above its field.
    private func field(_ label: String, @ViewBuilder _ content: () -> some View) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).font(.rounded(.caption2)).foregroundStyle(Theme.muted).padding(.leading, 6)
            content()
        }
    }

    private var options: [String] {
        Self.presets.contains(every) || every.isEmpty ? Self.presets : [every] + Self.presets
    }

    /// "30m" → "Every 30 min", "1h" → "Every hour", "12h" → "Every 12 hours", "24h" → "Every day".
    static func label(_ e: String) -> String {
        switch ScheduleLine.compact(e) {
        case "1h": return "Every hour"
        case "1d": return "Every day"
        case let c where c.hasSuffix("m"): return "Every \(c.dropLast()) min"
        case let c where c.hasSuffix("h"): return "Every \(c.dropLast()) hours"
        case let c where c.hasSuffix("d"): return "Every \(c.dropLast()) days"
        case let c: return "Every \(c)"
        }
    }

    private func save() async {
        saving = true; error = nil
        defer { saving = false }
        var changes: [String: JSONValue] = [:]
        let newTask = task.trimmingCharacters(in: .whitespacesAndNewlines)
        let newInstructions = instructions.trimmingCharacters(in: .whitespacesAndNewlines)
        let newTitle = title.trimmingCharacters(in: .whitespacesAndNewlines)
        var newTarget: [String: JSONValue]?
        if taskChanged || instructionsChanged,
           let target = definition?.target(withPrompt: taskChanged ? newTask : (definition?.prompt ?? ""),
                                           instructions: instructionsChanged ? newInstructions : nil) {
            changes["target"] = .object(target); newTarget = target
        }
        if titleChanged { changes["title"] = .string(newTitle) }
        if everyChanged, let source = automation.triggerSource {
            var config = automation.triggerConfig ?? [:]
            config["every"] = .string(every)
            var trigger: [String: JSONValue] = ["source_id": .string(source), "config": .object(config)]
            if let v = automation.triggerSourceVersion { trigger["source_version"] = .number(Double(v)) }
            changes["trigger"] = .object(trigger)
        }
        if remembersChanged { changes["context"] = .object(["mode": .string(remembers ? "growing" : "independent")]) }
        do {
            if !changes.isEmpty {
                try await model.client.reviseAutomation(id: automation.id, changes: changes,
                                                        expectedRevision: definition?.revision ?? automation.revision)
            }
            if activeChanged {
                try await model.client.automationCommand(id: automation.id, type: active ? "automation.resume" : "automation.pause")
            }
            WKInterfaceDevice.current().play(.success)
            if !changes.isEmpty, let d = definition {
                // Every page shows the edit at once (the gateway applies it a few seconds later).
                var merged = d.target ?? [:]
                for (k, v) in newTarget ?? [:] { merged[k] = v }
                model.saved(AutomationDefinition(revision: (d.revision ?? 0) + 1, title: titleChanged ? newTitle : d.title,
                                                 target: newTarget == nil ? d.target : merged), of: automation.id)
            } else {
                model.refreshAutomations()
            }
            model.path.removeLast()
        } catch GatewayError.http(let status, _) where status == 409 {
            error = "Changed elsewhere meanwhile. Open it again."
        } catch {
            self.error = AppModel.say(error)
        }
    }
}
