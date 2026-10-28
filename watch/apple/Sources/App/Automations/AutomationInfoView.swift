import AbstractGatewayClient
import SwiftUI
import WatchKit

/// An automation's details, behind (i) on its orb page (or a swipe forward from it): its name, when
/// it runs, Edit and Run (Stop while it runs), its task. Its runs are on the orb page, as any
/// conversation's messages. Run shows at once that it is starting (a spinner on the button, a haptic,
/// "Starting…" then "Running…" with the time), stays here until the gateway has started the run,
/// then goes back to the orb page, which follows that run to its answer.
struct AutomationInfoView: View {
    let automation: AutomationSummary
    @EnvironmentObject private var model: AppModel
    @State private var error: String?
    @State private var busy = false
    /// The tap on Run, until the gateway has started its run (or refused it).
    @State private var starting: Date?
    /// The gateway took the command: the run is on its way.
    @State private var accepted = false

    private var current: AutomationSummary { model.automations.first { $0.id == automation.id } ?? automation }
    private var definition: AutomationDefinition? { model.definitions[automation.id] }
    private var running: Bool { current.currentOccurrence != nil }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                Text(current.name ?? "Automation").font(.rounded(.headline)).foregroundStyle(Theme.text)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("automation.title")
                // When it runs, then Edit and Run on the same line (while it runs: Stop).
                HStack(spacing: 6) {
                    ScheduleLine(automation: current, stacked: true)
                    Spacer(minLength: 4)
                    NavigationLink(value: Route.automationEdit(current)) { GlassIcon(symbol: "pencil", size: CornerButton.size) }
                        .buttonStyle(GlassPress()).accessibilityLabel("Edit")
                    Button { running ? stopRun() : runNow() } label: {
                        let stop = running && starting == nil
                        Label {
                            Text(stop ? "Stop" : "Run")
                        } icon: {
                            // (the icon's width either way: the schedule beside it keeps its room)
                            Group {
                                if starting != nil { ProgressView().controlSize(.mini).tint(Theme.text).scaleEffect(0.75) }
                                else { Image(systemName: stop ? "stop.fill" : "play.fill") }
                            }
                            .frame(width: 16, height: 16)
                        }
                            .font(.rounded(.footnote, weight: .semibold)).foregroundStyle(stop ? Theme.red : Theme.text)
                            .padding(.horizontal, 12).frame(height: 35)
                            .background(Theme.neutralButton, in: Capsule())
                            .overlay(Capsule().strokeBorder(Color.white.opacity(0.12), lineWidth: 0.5))
                    }
                    .buttonStyle(GlassPress()).disabled(busy)
                    .accessibilityLabel(starting != nil ? "Starting the run" : running ? "Stop this run" : "Run")
                    .accessibilityIdentifier("automation.run")
                }
                // From the tap until the gateway has the run: what it is doing, and for how long.
                if let starting {
                    TimelineView(.periodic(from: .now, by: 1)) { ctx in
                        Text((accepted ? "Running… " : "Starting… ") + Clock.text(ctx.date.timeIntervalSince(starting)))
                            .font(.rounded(.caption2, weight: .semibold)).foregroundStyle(Theme.cyan).monospacedDigit()
                    }
                    .accessibilityIdentifier("automation.starting")
                }
                if let error { Text(error).font(.rounded(.caption2)).foregroundStyle(Theme.red) }
                // Its task, unless its name already says it (a name made from the task).
                if let task = definition?.prompt, task != current.name { about("Task", task, id: "automation.task") }
                // After an Approve all on one of its runs: what the watch approves for its runs.
                let allowed = model.trust(.automation(automation.id))
                if !allowed.isEmpty {
                    Card(stroke: Theme.amber.opacity(0.5)) {
                        VStack(alignment: .leading, spacing: 4) {
                            Label("Allowed for its runs", systemImage: "checkmark.shield.fill")
                                .font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.amber)
                            Text(allowed.map(ToolGroup.title(of:)).sorted().joined(separator: ", "))
                                .font(.rounded(.caption2)).foregroundStyle(Theme.text2)
                            Text("Approved by this watch when it sees them.").font(.rounded(.caption2)).foregroundStyle(Theme.muted)
                            Button("Ask again") { model.revokeTrust(.automation(automation.id)); WKInterfaceDevice.current().play(.click) }
                                .buttonStyle(FilledButtonStyle(fill: Theme.neutralButton, font: .rounded(.footnote, weight: .semibold)))
                                .accessibilityIdentifier("automation.trust.revoke")
                        }
                    }
                }
                if current.contextMode == "growing" {
                    Label("Builds on its earlier runs", systemImage: "arrow.triangle.2.circlepath")
                        .font(.rounded(.caption2)).foregroundStyle(Theme.muted)
                }
            }
            .padding(.horizontal, 4)
        }
        .screen("")
        .task { _ = try? await model.definition(of: automation.id) }
        // Read fresh: Run or Stop says what it is doing now (the list is read at most once a minute).
        .task { if let fresh = try? await model.client.automation(id: automation.id) { model.replaceAutomation(fresh) } }
        // While it runs: read again every 3 s, so Stop becomes Run now when it is over.
        .task(id: running) {
            while running, !Task.isCancelled {
                try? await Task.sleep(for: .seconds(3))
                if !Task.isCancelled, let fresh = try? await model.client.automation(id: automation.id) { model.replaceAutomation(fresh) }
            }
        }
    }

    private func about(_ label: String, _ text: String, id: String) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(label).font(.rounded(.caption2)).foregroundStyle(Theme.muted)
            Text(text).font(.rounded(.footnote)).foregroundStyle(Theme.text2).fixedSize(horizontal: false, vertical: true)
        }
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier(id)
    }

    /// Starts a run: felt and shown at once, here until the gateway has started it, then back on the
    /// orb page, handed the run, which it follows from there (its steps, then its answer, spoken).
    private func runNow() {
        guard starting == nil else { return }
        let tapped = Date(), before = current.lastOccurrence?.index ?? 0
        error = nil; busy = true; accepted = false; starting = tapped
        WKInterfaceDevice.current().play(.click)
        Task {
            defer { busy = false; starting = nil; accepted = false }
            do {
                try await model.client.runAutomationNow(id: automation.id)
                accepted = true
                WKInterfaceDevice.current().play(.start)
                var row = current; row.currentOccurrence = row.currentOccurrence ?? CurrentOccurrence(runId: nil)
                model.replaceAutomation(row)
                if let run = await startedRun(after: before, tapped: tapped) { model.startedRuns[automation.id] = .init(runId: run, since: tapped) }
                // Back to its orb page, unless the person has already left these details.
                if case .automationInfo(let i)? = model.path.last, i.id == automation.id,
                   case .automation(let a)? = model.path.dropLast().last, a.id == automation.id { model.goBack() }
            } catch GatewayError.http(let status, let body) where status == 409 && body.contains("automation_busy") {
                // A run is already on its way: it is shown, with Stop.
                self.error = "It is already running."
                if let fresh = try? await model.client.automation(id: automation.id) { model.replaceAutomation(fresh) }
            } catch {
                self.error = "Couldn't start it. " + AppModel.say(error)
                WKInterfaceDevice.current().play(.failure)
            }
        }
    }

    /// The run the gateway started for a Run: read every second until it is there (or a run past
    /// `before` has already ended: a very short run), for at most 20 s; nil then (the orb page goes
    /// on looking for it).
    private func startedRun(after before: Int, tapped: Date) async -> String? {
        let end = Date().addingTimeInterval(20)
        while Date() < end, !Task.isCancelled {
            if let fresh = try? await model.client.automation(id: automation.id) {
                if let run = fresh.currentOccurrence?.runId { model.replaceAutomation(fresh); return run }
                // (fired after the tap, give or take the clocks: never a run the row was too old to know)
                if let last = fresh.lastOccurrence, (last.index ?? 0) > before, let run = last.runId,
                   (last.firedAt.flatMap(ISO8601.date) ?? .distantPast) > tapped.addingTimeInterval(-60) {
                    model.replaceAutomation(fresh); return run
                }
            }
            try? await Task.sleep(for: .seconds(1))
        }
        return nil
    }

    private func stopRun() {
        busy = true
        Task {
            defer { busy = false }
            do { try await model.client.automationCommand(id: automation.id, type: "automation.stop_current"); WKInterfaceDevice.current().play(.click) }
            catch { self.error = "Couldn't stop it" }
        }
    }

    /// "today 07:04", "tomorrow 07:00", "Mon 20, 07:00"; empty when unreadable.
    static func short(_ iso: String) -> String {
        guard let d = ISO8601.date(iso) else { return "" }
        let cal = Calendar.current, t = d.formatted(date: .omitted, time: .shortened)
        if cal.isDateInToday(d) { return "today \(t)" }
        if cal.isDateInTomorrow(d) { return "tomorrow \(t)" }
        if cal.isDateInYesterday(d) { return "yesterday \(t)" }
        return d.formatted(.dateTime.weekday(.abbreviated).day().hour().minute())
    }
}
