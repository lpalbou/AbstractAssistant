import AbstractGatewayClient
import SwiftUI
import WatchKit

/// One automation: its name, how often and when next, three glass icons (read the latest result
/// with the orb, edit, run now / stop), the latest result in full (or, while it runs, what it is
/// doing now), then its earlier runs. Opening it marks its new results as seen.
struct AutomationDetailView: View {
    let automation: AutomationSummary
    @EnvironmentObject private var model: AppModel
    @StateObject private var progress = RunProgress()
    @State private var occurrences: [LastOccurrence] = []
    /// Full answers are heavy on a public gateway (measured 2026-10-17: 1 run 3 s, 5 runs 7 s,
    /// 30 runs 17 s): the latest first, then it and 5 earlier ones, older on demand.
    @State private var limit = 6
    @State private var loading = true
    /// A run in progress (Run now, or a scheduled one found on opening); its id once known.
    @State private var running = false
    @State private var runId: String?
    @State private var watcher: Task<Void, Never>?
    @State private var error: String?

    private var current: AutomationSummary { model.automations.first { $0.id == automation.id } ?? automation }
    private var title: String { current.name ?? "Automation" }
    private var last: LastOccurrence? { occurrences.first ?? current.lastOccurrence }

    var body: some View {
        ScrollViewReader { proxy in
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                Text(title).font(.rounded(.headline)).foregroundStyle(Theme.text).lineLimit(3)
                // When it runs, and Run now at the far right of the same line (while it runs: stop).
                HStack(spacing: 6) {
                    ScheduleLine(automation: current)
                    Spacer(minLength: 4)
                    Button { running ? stopRun() : runNow() } label: { GlassIcon(symbol: running ? "stop.fill" : "play.fill") }
                        .buttonStyle(.plain).accessibilityLabel(running ? "Stop this run" : "Run now")
                }
                HStack(spacing: 10) {
                    if let last, let text = last.answer ?? last.excerpt, let run = last.runId {
                        ReadAloudLink(item: ReadItem(title: title, text: text, scope: .run(run)))
                    }
                    NavigationLink(value: Route.automationEdit(current)) { GlassIcon(symbol: "pencil") }
                        .buttonStyle(.plain).accessibilityLabel("Edit")
                }
                if let error { Text(error).font(.rounded(.caption2)).foregroundStyle(Theme.red) }
                if running { RunningCard(progress: progress) }
                if let last { result(last) }
                if loading || occurrences.count > 1 {
                    HStack(spacing: 6) {
                        Text("Earlier runs").font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.text2)
                        if loading { ProgressView().frame(width: 16, height: 16) }
                    }
                    .padding(.top, 6)
                    ForEach(occurrences.dropFirst(), id: \.self) { o in
                        NavigationLink(value: Route.occurrence(title: title, o)) { OccurrenceRow(occurrence: o) }
                            .buttonStyle(.plain)
                    }
                    if !loading && occurrences.count >= limit {
                        Button("Show older") { limit += 10; Task { await load() } }
                            .buttonStyle(.plain).font(.rounded(.footnote)).foregroundStyle(Theme.cyan)
                    }
                }
            }
            .padding(.horizontal, 4)
            Color.clear.frame(height: 1).id("end")
        }
        #if DEBUG
        .task {   // screenshots: --scroll-bottom (end of the page), --run-now (the running state)
            let args = ProcessInfo.processInfo.arguments
            if args.contains("--run-now") { try? await Task.sleep(for: .seconds(1)); runNow() }
            if args.contains("--scroll-end-now") { try? await Task.sleep(for: .seconds(1.5)); proxy.scrollTo("end", anchor: .bottom); return }
            guard args.contains("--scroll-bottom") else { return }
            while occurrences.count < 2 { try? await Task.sleep(for: .milliseconds(300)) }
            try? await Task.sleep(for: .seconds(1)); proxy.scrollTo("end", anchor: .bottom)
        }
        #endif
        }
        .screen("")
        .task {
            if current.currentOccurrence != nil { running = true; watch() }
            if occurrences.isEmpty, let one = try? await model.client.occurrences(automationId: automation.id, limit: 1), !one.isEmpty {
                occurrences = one
            }
            await load()
            if let c = current.attention?.cursor, (current.attention?.unseenCount ?? 0) > 0 || (current.attention?.unread ?? false) {
                try? await model.client.markSeen(automationId: automation.id, cursor: c)
                await model.refresh()
            }
        }
        .onDisappear { watcher?.cancel(); watcher = nil; progress.stop(); AnswerNotifier.shared.setShowing(nil) }
    }

    /// The latest result in full: when, failed or not, the markdown answer.
    private func result(_ o: LastOccurrence) -> some View {
        Card(stroke: o.status == "failed" ? Theme.red.opacity(0.6) : nil) {
            VStack(alignment: .leading, spacing: 4) {
                OccurrenceHeader(occurrence: o)
                MarkdownText(o.answer ?? o.excerpt ?? "No answer")
            }
        }
    }

    private func load() async {
        loading = true
        defer { loading = false }
        if let list = try? await model.client.occurrences(automationId: automation.id, limit: limit) { occurrences = list }
    }

    private func runNow() {
        error = nil
        running = true
        Task {
            do {
                try await model.client.runAutomationNow(id: automation.id)
                WKInterfaceDevice.current().play(.start)
                // The list shows it running at once (its own poll catches up later).
                var row = current; row.currentOccurrence = row.currentOccurrence ?? CurrentOccurrence(runId: nil)
                model.replaceAutomation(row)
                watch()
            } catch {
                self.error = "Couldn't start it"; running = false
            }
        }
    }

    private func stopRun() {
        Task {
            do { try await model.client.automationCommand(id: automation.id, type: "automation.stop_current"); WKInterfaceDevice.current().play(.click) }
            catch { self.error = "Couldn't stop it" }
        }
    }

    /// While it runs: learn the run's id (then follow its steps, and be notified at the end if
    /// the person left), and notice the end (the new result comes in at the top).
    private func watch() {
        guard watcher == nil else { return }
        watcher = Task {
            var seenRunning = false
            let begun = Date()
            while !Task.isCancelled {
                if let a = try? await model.client.automation(id: automation.id) {
                    if a.currentOccurrence != nil || seenRunning { model.replaceAutomation(a) }
                    if let occ = a.currentOccurrence {
                        seenRunning = true
                        if runId == nil, let id = occ.runId {
                            runId = id
                            progress.follow(runId: id, client: model.client)
                            if !model.client.isMock {
                                AnswerNotifier.shared.watch(runId: id, title: title, prompt: "")
                                AnswerNotifier.shared.setShowing(id)
                            }
                        }
                    } else if seenRunning || Date().timeIntervalSince(begun) > 45 {
                        break   // finished (or never seen running: a very short run, or refused)
                    }
                }
                try? await Task.sleep(for: .seconds(3))
            }
            guard !Task.isCancelled else { return }
            await finished()
        }
    }

    private func finished() async {
        progress.stop(); watcher = nil; runId = nil
        if let one = try? await model.client.occurrences(automationId: automation.id, limit: 1), !one.isEmpty {
            occurrences = one + occurrences.filter { $0.index != one.first?.index }
        }
        running = false
        WKInterfaceDevice.current().play(.success)
        await load()
        await model.refresh()
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

/// "today 1:28 PM", and "Failed" in red when it failed.
struct OccurrenceHeader: View {
    let occurrence: LastOccurrence
    var body: some View {
        HStack(spacing: 6) {
            if let f = occurrence.firedAt {
                Text(AutomationDetailView.short(f)).font(.rounded(.caption2)).foregroundStyle(Theme.muted)
                    .lineLimit(1).minimumScaleFactor(0.7)
            }
            if occurrence.status == "failed" {
                Text("Failed").font(.rounded(.caption2, weight: .semibold)).foregroundStyle(Theme.red).fixedSize()
            }
        }
    }
}

/// One earlier run in the list: when, failed or not, the first words of its answer.
struct OccurrenceRow: View {
    let occurrence: LastOccurrence
    var body: some View {
        Card {
            HStack(spacing: 6) {
                VStack(alignment: .leading, spacing: 2) {
                    OccurrenceHeader(occurrence: occurrence)
                    if let a = occurrence.answer ?? occurrence.excerpt {
                        Text(SpeechText.plain(a)).font(.rounded(.footnote)).foregroundStyle(Theme.text2).lineLimit(2)
                    }
                }
                Spacer(minLength: 2)
                Image(systemName: "chevron.right").font(.caption2).foregroundStyle(Theme.muted)
            }
        }
    }
}

/// One run of an automation, opened from the list: when, its answer in full, read it with the orb.
struct OccurrenceView: View {
    let title: String
    let occurrence: LastOccurrence

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    OccurrenceHeader(occurrence: occurrence)
                    Spacer(minLength: 4)
                    if let text = occurrence.answer ?? occurrence.excerpt, let run = occurrence.runId {
                        ReadAloudLink(item: ReadItem(title: title, text: text, scope: .run(run)))
                    }
                }
                MarkdownText(occurrence.answer ?? occurrence.excerpt ?? "No answer")
            }
            .padding(.horizontal, 4)
        }
        .screen("")
    }
}
