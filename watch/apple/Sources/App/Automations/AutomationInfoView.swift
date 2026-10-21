import AbstractGatewayClient
import SwiftUI
import WatchKit

/// An automation's details, behind (i) on its orb page (or a swipe forward from it): its name, when
/// it runs, Edit and Run now (Stop while it runs), its task and instructions. Its runs are on the orb
/// page, as any conversation's messages; Run now goes back there to follow the run.
struct AutomationInfoView: View {
    let automation: AutomationSummary
    @EnvironmentObject private var model: AppModel
    @State private var error: String?
    @State private var busy = false

    private var current: AutomationSummary { model.automations.first { $0.id == automation.id } ?? automation }
    private var definition: AutomationDefinition? { model.definitions[automation.id] }
    private var running: Bool { current.currentOccurrence != nil }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                Text(current.name ?? "Automation").font(.rounded(.headline)).foregroundStyle(Theme.text)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("automation.title")
                // When it runs, then Edit and Run now on the same line (while it runs: Stop).
                HStack(spacing: 6) {
                    ScheduleLine(automation: current, stacked: true)
                    Spacer(minLength: 4)
                    NavigationLink(value: Route.automationEdit(current)) { GlassIcon(symbol: "pencil") }
                        .buttonStyle(GlassPress()).accessibilityLabel("Edit")
                    Button { running ? stopRun() : runNow() } label: { GlassIcon(symbol: running ? "stop.fill" : "play.fill") }
                        .buttonStyle(GlassPress()).disabled(busy)
                        .accessibilityLabel(running ? "Stop this run" : "Run now")
                }
                if let error { Text(error).font(.rounded(.caption2)).foregroundStyle(Theme.red) }
                // Its task, unless its name already says it (a name made from the task).
                if let task = definition?.prompt, task != current.name { about("Task", task, id: "automation.task") }
                if let how = definition?.instructions { about("Instructions", how, id: "automation.instructions") }
                if current.contextMode == "growing" {
                    Label("Builds on its earlier runs", systemImage: "arrow.triangle.2.circlepath")
                        .font(.rounded(.caption2)).foregroundStyle(Theme.muted)
                }
            }
            .padding(.horizontal, 4)
        }
        .screen("")
        .task { _ = try? await model.definition(of: automation.id) }
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

    /// Starts a run, then back on the orb page, which follows it.
    private func runNow() {
        error = nil; busy = true
        Task {
            defer { busy = false }
            do {
                try await model.client.runAutomationNow(id: automation.id)
                WKInterfaceDevice.current().play(.start)
                var row = current; row.currentOccurrence = row.currentOccurrence ?? CurrentOccurrence(runId: nil)
                model.replaceAutomation(row)
                if case .automation(let a)? = model.path.dropLast().last, a.id == automation.id { model.goBack() }
            } catch {
                self.error = "Couldn't start it"
            }
        }
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
