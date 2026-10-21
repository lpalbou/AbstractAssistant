import AbstractGatewayClient
import SwiftUI
import WatchKit

/// Change an automation from the wrist: its title and its task (what it is asked each run), each in
/// its own field holding the current text so editing starts from it; whether it runs at all and how
/// often; whether each run builds on the earlier ones, and how much of them it reads. A title that is the task follows the task while the title itself is not edited. Save sends
/// only what changed, with the revision it was read at (a change made elsewhere meanwhile is
/// refused); leaving with changes asks to save or discard them. The definition is the one its page
/// already read (shown at once), and a save updates it for every page.
struct AutomationEditView: View {
    let automation: AutomationSummary
    @EnvironmentObject private var model: AppModel
    @State private var every: String
    @State private var remembers: Bool
    @State private var active: Bool
    /// How much of its earlier runs a run reads, in tokens (the gateway's value; nil: not given).
    @State private var tokens: Int?
    @State private var saving = false
    @State private var error: String?
    @State private var choosingEvery = false
    /// The committed definition (the task lives there, not in the list row); nil until read.
    @State private var definition: AutomationDefinition?
    @State private var task = ""
    @State private var title = ""
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
        _tokens = State(initialValue: automation.growingMaxTokens)
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
    private var tokensChanged: Bool { remembers && tokens != nil && tokens != automation.growingMaxTokens }
    private var changed: Bool { titleChanged || taskChanged || everyChanged || remembersChanged || tokensChanged || activeChanged }

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
                } else if loadFailed {
                    Text("Couldn't load this automation").font(.rounded(.caption2)).foregroundStyle(Theme.muted)
                } else {
                    ProgressView().frame(maxWidth: .infinity, minHeight: 44)
                }
                // When: on or off, and how often.
                field("Runs") {
                    Card {
                        VStack(spacing: 8) {
                            Toggle("Active", isOn: $active).font(.rounded(.footnote, weight: .semibold)).tint(Theme.indigoButton)
                                .accessibilityIdentifier("edit.active")
                            if automation.every != nil {
                                Divider().overlay(Theme.line)
                                // The choice opens as a list.
                                Button { choosingEvery = true } label: {
                                    HStack {
                                        Label(Self.label(every), systemImage: "clock")
                                            .font(.rounded(.footnote, weight: .semibold)).foregroundStyle(active ? Theme.text : Theme.muted)
                                        Spacer(minLength: 4)
                                        Image(systemName: "chevron.right").font(.caption2).foregroundStyle(Theme.muted)
                                    }
                                    .contentShape(Rectangle())
                                }
                                .buttonStyle(.tap)
                                .accessibilityLabel(Self.label(every))
                            }
                        }
                    }
                }
                // Memory: whether a run reads the earlier ones, and how much of them.
                field("Memory") {
                    MemoryCard(remembers: $remembers, tokens: $tokens, id: "edit.tokens")
                }
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
        let newTitle = title.trimmingCharacters(in: .whitespacesAndNewlines)
        var newTarget: [String: JSONValue]?
        if taskChanged, let target = definition?.target(withPrompt: newTask) {
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
        if remembersChanged || tokensChanged {
            var context: [String: JSONValue] = ["mode": .string(remembers ? "growing" : "independent")]
            if remembers, let tokens { context["growing"] = .object(["max_tokens": .number(Double(tokens))]) }
            changes["context"] = .object(context)
        }
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

/// Whether each run reads the automation's earlier runs, and how much of them ("Reads up to 50,000
/// tokens": its own value, else the gateway's default); a new number is a whole number only. The
/// same card in New automation and Edit.
struct MemoryCard: View {
    @Binding var remembers: Bool
    @Binding var tokens: Int?
    let id: String
    @State private var problem: String?

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: 8) {
                Toggle("Builds on earlier runs", isOn: $remembers).font(.rounded(.footnote, weight: .semibold)).tint(Theme.indigoButton)
                if remembers {
                    Divider().overlay(Theme.line)
                    TextFieldLink(prompt: Text("Tokens (numbers only)")) {
                        HStack {
                            Text("Reads up to").font(.rounded(.footnote)).foregroundStyle(Theme.text2)
                            Spacer(minLength: 4)
                            Text(tokens.map(Self.text) ?? "—").font(.rounded(.footnote, weight: .semibold)).monospacedDigit()
                                .foregroundStyle(Theme.cyan)
                            Image(systemName: "chevron.right").font(.caption2).foregroundStyle(Theme.muted)
                        }
                        .contentShape(Rectangle())
                    } onSubmit: { set($0) }
                    .buttonStyle(.tap)
                    .accessibilityLabel("Reads up to \(tokens.map(Self.text) ?? "the gateway's default")")
                    .accessibilityIdentifier(id)
                    Text(problem ?? "of its earlier runs, in tokens.").font(.rounded(.caption2))
                        .foregroundStyle(problem == nil ? Theme.muted : Theme.red)
                }
            }
        }
    }

    /// What was typed: a whole number of tokens (spaces and thousands separators allowed), else it
    /// says numbers only and keeps the value.
    private func set(_ text: String) {
        let digits = text.filter { !$0.isWhitespace && $0 != "," && $0 != "." && $0 != "\u{2019}" && $0 != "'" }
        guard !digits.isEmpty, digits.allSatisfy(\.isASCII), digits.allSatisfy(\.isNumber), let n = Int(digits), n > 0 else {
            problem = "Numbers only, more than 0."
            WKInterfaceDevice.current().play(.failure)
            return
        }
        problem = nil
        tokens = n
    }

    /// "50,000 tokens".
    static func text(_ n: Int) -> String { n.formatted(.number.grouping(.automatic)) + " tokens" }
}
