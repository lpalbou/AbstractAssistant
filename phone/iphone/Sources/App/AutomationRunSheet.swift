import SwiftUI
import AssistantKit
import AbstractGatewayClient

struct AutomationRunSheet: View {
    let automationID: String
    @State var occurrence: LastOccurrence
    @Environment(AssistantStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    @Environment(\.scenePhase) private var scenePhase
    /// The run's answer read aloud, as in a conversation: in pieces, paused and resumed here or on
    /// the lock screen, going on with the iPhone locked; it stops when the sheet closes.
    @State private var voice = VoiceController.forApp()
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
                    if let answer = occurrence.displayAnswer {
                        HStack(spacing: 18) {
                            QuietLabel(text: "Answer")
                            Spacer()
                            if let runID = occurrence.runId { readControls(answer, runID: runID) }
                        }.foregroundStyle(PhoneTheme.secondary).buttonStyle(.plain)
                        if let problem = voice.error { Text(problem).font(.footnote).foregroundStyle(PhoneTheme.amber) }
                        PhoneMarkdown(text: answer)
                    }
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
                .onChange(of: scenePhase) { _, phase in voice.scene(visible: phase != .background) }
                .onDisappear { voice.stop() }
        }
    }
    /// Read aloud, pause / resume, and Stop while it reads: the conversation's controls.
    @ViewBuilder private func readControls(_ answer: String, runID: String) -> some View {
        Button {
            if voice.speaking { voice.togglePause() }
            else if let client = store.client {
                voice.read(answer, client: client, scope: .run(runID), choice: store.preferences.voice, speed: store.preferences.speed,
                           messageID: occurrence.stableID, title: store.automations.first { $0.id == automationID }?.name ?? "Automation run")
            }
        } label: { Image(systemName: voice.speaking ? (voice.paused ? "speaker.wave.2.fill" : "pause.fill") : "speaker.wave.2").frame(width: 44, height: 44).contentShape(Rectangle()) }
            .accessibilityLabel(voice.speaking ? "Pause or resume reading" : "Read answer aloud")
            .accessibilityIdentifier("automation.run.read")
        if voice.speaking {
            Button { voice.stop() } label: { Image(systemName: "stop.fill").frame(width: 44, height: 44).contentShape(Rectangle()) }
                .accessibilityLabel("Stop reading").accessibilityIdentifier("automation.run.stop")
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
            let current = history.first(where: { $0.occurrenceKey == occurrence.occurrenceKey })
            if let current { occurrence = current }
            if let id = occurrence.runId {
                let run = try await client.run(id: id)
                guard context == store.contextID && !Task.isCancelled else { return }
                runError = run.error
                if current == nil && run.isTerminal { occurrence.status = run.status; occurrence.finishedAt = occurrence.finishedAt ?? run.updatedAt }
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
