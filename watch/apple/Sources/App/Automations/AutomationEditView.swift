import AbstractGatewayClient
import SwiftUI
import WatchKit

/// Change an automation from the wrist: its task (what it does each run; one field, holding the
/// current text so editing starts from it), how often it runs, whether each run builds on the
/// earlier ones, and whether it runs at all. An automation named by its task keeps its name in step. Save sends only
/// what changed, with the revision it was read at (a change made elsewhere meanwhile is refused).
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
    private var changed: Bool { taskChanged || everyChanged || remembersChanged || activeChanged }

    var body: some View {
        FitScroll {
            VStack(spacing: 6) {
                // Real text fields: they show the current text, and editing starts from it.
                // One field: the task, as it is now (editing starts from it).
                if definition != nil {
                    TextField("Task", text: $task, axis: .vertical).lineLimit(1...10)
                        .font(.rounded(.footnote)).accessibilityIdentifier("edit.task")
                } else if loadFailed {
                    Text("Couldn't load the task").font(.rounded(.caption2)).foregroundStyle(Theme.muted)
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
                    .buttonStyle(.plain)
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
                let d = try await model.client.automationDefinition(id: automation.id)
                definition = d
                task = d.prompt ?? ""
            } catch { loadFailed = true }
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
        if taskChanged, let target = definition?.target(withPrompt: newTask) {
            changes["target"] = .object(target)
            if let t = AutomationDefinition.title(afterTask: newTask, oldTitle: definition?.title, oldTask: definition?.prompt) {
                changes["title"] = .string(t)
            }
        }
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
            await model.refresh()
            model.path.removeLast()
        } catch GatewayError.http(let status, _) where status == 409 {
            error = "Changed elsewhere meanwhile. Open it again."
        } catch {
            self.error = AppModel.say(error)
        }
    }
}
