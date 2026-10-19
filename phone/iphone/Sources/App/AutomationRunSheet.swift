import SwiftUI
import AssistantKit
import AbstractGatewayClient

struct AutomationRunSheet: View {
    let automationID: String
    @State var occurrence: LastOccurrence
    @Environment(AssistantStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    @State private var runError: String?
    @State private var problem: String?
    @State private var loading = false
    private var activity: AnswerActivity? { occurrence.runId.flatMap { store.answerActivities[$0] } }
    private var explanation: AutomationRunExplanation {
        .init(occurrence: occurrence, runError: runError, stepError: activity?.activity.items.last { $0.kind == .failure }?.detail)
    }
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    Label(explanation.title, systemImage: occurrence.status == "failed" ? "exclamationmark.circle" : occurrence.status == "waiting" ? "hand.raised" : "clock.arrow.circlepath")
                        .font(.title2.weight(.semibold)).foregroundStyle(occurrence.status == "failed" || occurrence.status == "waiting" ? PhoneTheme.amber : PhoneTheme.mint)
                    Text(explanation.message).font(.body).accessibilityIdentifier("automation.run.explanation")
                    if let next = explanation.nextStep { Text(next).font(.subheadline).foregroundStyle(PhoneTheme.secondary) }
                    PhoneCard {
                        VStack(alignment: .leading, spacing: 12) {
                            if let index = occurrence.index { LabeledContent("Run", value: "\(index)") }
                            dateRow("Started", occurrence.firedAt)
                            dateRow("Finished", occurrence.finishedAt)
                            if let attempts = occurrence.attemptCount { LabeledContent("Attempts", value: String(attempts)).accessibilityIdentifier("automation.run.attempts") }
                            if let trigger = occurrence.triggerSummary { Text(trigger).font(.footnote).foregroundStyle(PhoneTheme.secondary) }
                        }.font(.subheadline)
                    }
                    if let detail = explanation.technicalDetail {
                        DisclosureGroup("Recorded error") { Text(detail).font(.footnote.monospaced()).textSelection(.enabled).padding(.top, 8) }
                            .tint(PhoneTheme.amber).accessibilityIdentifier("automation.run.error")
                    }
                    if let answer = occurrence.displayAnswer { QuietLabel(text: "Answer"); PhoneMarkdown(text: answer) }
                    if let task = AutomationRunExplanation.nonempty(occurrence.userTurn) {
                        DisclosureGroup("Task & trigger") { Text(task).font(.footnote).textSelection(.enabled).padding(.top, 8) }
                    }
                    if let problem { ErrorBanner(message: problem) }
                    if loading { ProgressView("Checking run details…") }
                    if let activity {
                        QuietLabel(text: "Recorded activity")
                        ForEach(activity.issues, id: \.self) { Text($0).font(.footnote).foregroundStyle(PhoneTheme.amber) }
                        ForEach(activity.activity.items) { ActivityEventRow(item: $0) }
                        if activity.activity.items.isEmpty { Text("No activity records were returned for this run.").font(.footnote).foregroundStyle(PhoneTheme.secondary) }
                    }
                    Button("Refresh details", systemImage: "arrow.clockwise") { Task { await load() } }.disabled(loading).accessibilityIdentifier("automation.run.refresh")
                    if let id = occurrence.runId {
                        DisclosureGroup("Support details") {
                            Text("Run ID").font(.caption).foregroundStyle(PhoneTheme.secondary)
                            Text(id).font(.caption.monospaced()).textSelection(.enabled)
                            if let code = occurrence.failure?.reasonCode { Text(code).font(.caption.monospaced()).textSelection(.enabled) }
                        }
                    }
                }.frame(maxWidth: .infinity, alignment: .leading).padding(24)
            }.background(PhoneTheme.ground).navigationTitle("Automation run").navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
                .task(id: store.contextID) { await load() }
        }
    }
    @ViewBuilder private func dateRow(_ label: String, _ value: String?) -> some View {
        if let date = value.flatMap(ISO8601.date) {
            LabeledContent(label) { Text(date, format: .dateTime.day().month(.abbreviated).hour().minute().second()).foregroundStyle(PhoneTheme.secondary) }.accessibilityIdentifier("automation.run." + label.lowercased())
        }
    }
    private func load() async {
        guard let client = store.client, !loading else { return }
        let context = store.contextID
        loading = true; defer { loading = false }
        problem = nil
        do {
            let history = try await client.occurrences(automationId: automationID, limit: 20)
            guard context == store.contextID && !Task.isCancelled else { return }
            if let current = history.first(where: { $0.stableID == occurrence.stableID }) { occurrence = current }
            if let id = occurrence.runId {
                let run = try await client.run(id: id)
                guard context == store.contextID && !Task.isCancelled else { return }
                runError = run.error
                // Occurrence status projects waits in descendants; retain it instead of the root's subworkflow wait.
                await store.loadAnswerActivity(runID: id, retry: true)
            }
        } catch is CancellationError {} catch {
            if context == store.contextID {
                problem = "Details could not be refreshed. " + error.localizedDescription
                if error as? GatewayError == .unauthorized { store.authenticationExpired() }
            }
        }
    }
}
