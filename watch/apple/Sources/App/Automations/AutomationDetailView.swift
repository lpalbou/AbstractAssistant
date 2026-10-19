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
    /// Full answers are heavy on a public gateway (measured 2026-10-17: 1 run 3 s, 5 runs 7 s,
    /// 30 runs 17 s): the latest first, then it and 5 earlier ones, older on demand.
    @State private var limit = 6
    @State private var loading = false
    /// A run in progress (Run now, or a scheduled one found on opening); its id once known.
    @State private var running = false
    @State private var runId: String?
    @State private var watcher: Task<Void, Never>?
    @State private var error: String?
    /// The results could not be read (said so, with Retry; never the cut preview instead).
    @State private var readFailed = false

    private var current: AutomationSummary { model.automations.first { $0.id == automation.id } ?? automation }
    /// Its results and definition as last read (shared with the other pages: shown at once on return).
    private var occurrences: [LastOccurrence] { model.results[automation.id] ?? [] }
    private var definition: AutomationDefinition? { model.definitions[automation.id] }
    /// The results known are the latest ones, and as many as shown: nothing to read.
    private var resultsCurrent: Bool {
        guard let first = occurrences.first else { return false }
        return first.index == current.lastOccurrence?.index && occurrences.count >= min(limit, current.occurrenceCount ?? limit)
    }
    private var title: String { current.name ?? "Automation" }
    /// The latest result as read in full (the list's preview is a cut excerpt: never shown here).
    private var last: LastOccurrence? { occurrences.first }
    /// It has run, but its latest result is still being read.
    private var readingLast: Bool { occurrences.isEmpty && current.lastOccurrence != nil }

    var body: some View {
        ScrollViewReader { proxy in
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                Text(title).font(.rounded(.headline)).foregroundStyle(Theme.text).fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("automation.title")
                // When it runs, then Edit and Run now on the same line (while it runs: stop).
                HStack(spacing: 6) {
                    ScheduleLine(automation: current, stacked: true)
                    Spacer(minLength: 4)
                    NavigationLink(value: Route.automationEdit(current)) { GlassIcon(symbol: "pencil") }
                        .buttonStyle(GlassPress()).accessibilityLabel("Edit")
                    Button { running ? stopRun() : runNow() } label: { GlassIcon(symbol: running ? "stop.fill" : "play.fill") }
                        .buttonStyle(GlassPress()).accessibilityLabel(running ? "Stop this run" : "Run now")
                }
                if let error { Text(error).font(.rounded(.caption2)).foregroundStyle(Theme.red) }
                if let how = definition?.instructions { about("Instructions", how, id: "automation.instructions") }
                if running { RunningCard(progress: progress) }
                if let last { result(last) }
                else if readingLast && readFailed {
                    Button("Couldn't load the latest result. Retry") { Task { await load() } }
                        .buttonStyle(.tap).font(.rounded(.footnote)).foregroundStyle(Theme.amber)
                } else if readingLast {
                    Card { ProgressView().frame(maxWidth: .infinity) }.accessibilityLabel("Loading the latest result")
                }
                if loading || occurrences.count > 1 {
                    HStack(spacing: 6) {
                        Text("Earlier runs").font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.text2)
                        if loading { ProgressView().frame(width: 16, height: 16) }
                    }
                    .padding(.top, 6)
                    ForEach(occurrences.dropFirst(), id: \.self) { o in
                        NavigationLink(value: Route.occurrence(title: title, o)) { OccurrenceRow(occurrence: o) }
                            .buttonStyle(.tap)
                    }
                    if !loading && occurrences.count >= limit {
                        Button("Show older") { limit += 10; Task { await load() } }
                            .buttonStyle(.tap).font(.rounded(.footnote)).foregroundStyle(Theme.cyan)
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
            if occurrences.isEmpty, current.lastOccurrence != nil,
               let one = try? await model.client.occurrences(automationId: automation.id, limit: 1), !one.isEmpty {
                model.keep(results: one, of: automation.id)
            }
            if !resultsCurrent { await load() }
            if let c = current.attention?.cursor, (current.attention?.unseenCount ?? 0) > 0 || (current.attention?.unread ?? false) {
                try? await model.client.markSeen(automationId: automation.id, cursor: c)
                model.refreshAutomations()
            }
        }
        .task { _ = try? await model.definition(of: automation.id) }   // beside the results, never before
        .onDisappear { watcher?.cancel(); watcher = nil; progress.stop(); AnswerNotifier.shared.setShowing(nil) }
    }

    /// The instructions, whole.
    private func about(_ label: String, _ text: String, id: String) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(label).font(.rounded(.caption2)).foregroundStyle(Theme.muted)
            Text(text).font(.rounded(.footnote)).foregroundStyle(Theme.text2).fixedSize(horizontal: false, vertical: true)
        }
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier(id)
    }

    /// The latest result in full: when, failed or not, the markdown answer.
    private func result(_ o: LastOccurrence) -> some View {
        // The date line carries Read aloud (the latest result, with the orb).
        MessageCard(text: o.answer ?? o.excerpt ?? "", failed: o.status == "failed") {
            HStack {
                OccurrenceHeader(occurrence: o)
                Spacer(minLength: 4)
                if let text = o.answer ?? o.excerpt, !text.isEmpty, let run = o.runId {
                    ReadAloudLink(item: ReadItem(title: title, text: text, scope: .run(run)))
                }
            }
        }
    }

    private func load() async {
        loading = true
        defer { loading = false }
        do {
            model.keep(results: try await model.client.occurrences(automationId: automation.id, limit: limit), of: automation.id)
            readFailed = false
        } catch {
            readFailed = true
        }
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
            model.keep(results: one + occurrences.filter { $0.index != one.first?.index }, of: automation.id)
        }
        running = false
        WKInterfaceDevice.current().play(.success)
        model.refreshAutomations()
        await load()
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
        MessageRowCard(text: occurrence.answer ?? occurrence.excerpt ?? "") { OccurrenceHeader(occurrence: occurrence) }
    }
}

/// One run of an automation, opened from the list: when, its answer in full, read it with the orb.
struct OccurrenceView: View {
    let title: String
    let occurrence: LastOccurrence

    var body: some View {
        let text = occurrence.answer ?? occurrence.excerpt ?? ""
        MessagePage(text: text, read: occurrence.runId.flatMap { run in text.isEmpty ? nil : ReadItem(title: title, text: text, scope: .run(run)) }) {
            OccurrenceHeader(occurrence: occurrence)
        }
    }
}
