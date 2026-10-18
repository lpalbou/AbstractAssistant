import AbstractGatewayClient
import SwiftUI

/// Your conversations, newest first, grouped Today / Yesterday / Earlier. A tap continues one (the
/// orb opens on its last exchange); swipe for its details. Titled by the first question.
struct SessionsView: View {
    @EnvironmentObject private var model: AppModel
    @State private var opening: String?
    @State private var loadingOlder = false

    var body: some View {
        List {
            // A fresh conversation: the orb, in a new session (the current one stays listed here).
            Button {
                model.newAskSession()
                model.path = [.ask(.idle)]
            } label: {
                Label("New conversation", systemImage: "plus")
                    .font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.cyan)
            }
            if model.sessions.isEmpty {
                if model.lastRefresh == nil && model.lastError == nil { ProgressView().frame(maxWidth: .infinity) }
                else {
                    Text(model.lastError == nil ? "No conversations yet" : "Can't reach your assistant")
                        .font(.rounded(.footnote)).foregroundStyle(Theme.muted)
                }
            }
            ForEach(groups, id: \.0) { label, items in
                Section(label) {
                    ForEach(items) { s in
                        Button { open(s) } label: {
                            SessionRow(session: s, title: model.title(of: s),
                                       unreadable: model.unreadablePrompts.contains(s.latest.runId),
                                       opening: opening == s.id)
                        }
                        .disabled(opening != nil && opening != s.id)   // one session opens at a time
                        .swipeActions {
                            Button { model.path.append(.session(s)) } label: { Label("Details", systemImage: "list.bullet") }
                                .tint(Theme.indigoButton)
                        }
                    }
                }
            }
            if model.runs.count >= model.runsLimit {
                Button(loadingOlder ? "Loading…" : "Show older") {
                    loadingOlder = true
                    Task { await model.showOlder(); loadingOlder = false }
                }
                .font(.rounded(.footnote)).foregroundStyle(Theme.cyan)
                .disabled(loadingOlder)
            }
        }
        .navigationTitle("Sessions")
        .containerBackground(Theme.ground, for: .navigation)
        .refreshable { await model.refresh() }
    }

    private func open(_ s: SessionSummary) {
        guard opening == nil else { return }
        opening = s.id
        Task { await model.continueSession(s); opening = nil }
    }

    private var groups: [(String, [SessionSummary])] {
        let cal = Calendar.current
        var today: [SessionSummary] = [], yesterday: [SessionSummary] = [], earlier: [SessionSummary] = []
        for s in model.sessions {
            guard let d = s.updatedAt else { earlier.append(s); continue }
            if cal.isDateInToday(d) { today.append(s) } else if cal.isDateInYesterday(d) { yesterday.append(s) } else { earlier.append(s) }
        }
        return [("Today", today), ("Yesterday", yesterday), ("Earlier", earlier)].filter { !$0.1.isEmpty }
    }
}

struct SessionRow: View {
    let session: SessionSummary
    /// The latest question (nil while it is read: a placeholder shape, never made-up words).
    let title: String?
    /// The gateway could not give the latest question.
    var unreadable = false
    var opening = false

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 5) {
                if session.needsPerson { StatusDot(color: Theme.amber) }
                else if session.isLive { StatusDot(color: Theme.cyan) }
                else if session.status == "failed" { StatusDot(color: Theme.red) }
                if let title {
                    Text(title).font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.text).lineLimit(2)
                } else if unreadable {
                    Text("Question not available").font(.rounded(.footnote)).foregroundStyle(Theme.muted).lineLimit(1)
                } else {
                    Text("Reading the latest question").font(.rounded(.footnote, weight: .semibold)).lineLimit(2)
                        .redacted(reason: .placeholder)
                }
                Spacer(minLength: 2)
                if opening { ProgressView().frame(width: 14) }
            }
            HStack(spacing: 8) {
                SessionStat(symbol: "bubble.left.and.bubble.right", value: "\(session.turns)")
                if session.toolCalls > 0 { SessionStat(symbol: "wrench.and.screwdriver", value: "\(session.toolCalls)") }
                if session.needsPerson { Text("Needs you").font(.rounded(.caption2)).foregroundStyle(Theme.amber) }
                else if let at = session.updatedAt { SessionStat(symbol: "clock", value: SessionRow.age(at)) }
            }
        }
        .padding(.vertical, 2)
        .accessibilityElement(children: .combine)
    }

    /// "now", "4 min", "2 h", "3 d".
    static func age(_ d: Date) -> String {
        let s = max(0, Int(Date().timeIntervalSince(d)))
        return s < 60 ? "now" : s < 3600 ? "\(s / 60) min" : s < 86_400 ? "\(s / 3600) h" : "\(s / 86_400) d"
    }
}

struct SessionStat: View {
    let symbol: String
    let value: String
    var body: some View {
        HStack(spacing: 2) {
            Image(systemName: symbol).font(.rounded(.caption2))
            Text(value).font(.rounded(.caption2)).lineLimit(1)
        }
        .foregroundStyle(Theme.muted)
        .accessibilityElement(children: .combine)
    }
}

/// One conversation: its title with Read aloud for the latest answer, its last 5 exchanges in
/// order (question, then the answer in markdown; a finished answer opens whole), Show older when
/// there are more, and Continue floating at the bottom.
struct SessionDetailView: View {
    let session: SessionSummary
    @EnvironmentObject private var model: AppModel
    /// Every turn the listing gives (newest first, by creation); only the shown ones are read in full.
    @State private var rows: [RunSummary] = []
    @State private var full: [String: RunSummary] = [:]
    @State private var prompts: [String: String] = [:]
    @State private var shown = 5
    @State private var loading = true
    @State private var loadingOlder = false
    @State private var failed = false

    /// The shown turns, newest first, each in full once read.
    private var turns: [RunSummary] { rows.prefix(shown).map { full[$0.runId] ?? $0 } }
    private var latest: RunSummary? { turns.first }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 6) {
                HStack(alignment: .top) {
                    Text(model.title(of: session) ?? "").font(.rounded(.headline)).foregroundStyle(Theme.text).lineLimit(2)
                    Spacer(minLength: 4)
                    // Read the latest answer aloud, as on an automation's page.
                    if let last = latest, let out = last.outputText, !out.isEmpty, last.isTerminal {
                        ReadAloudLink(item: ReadItem(title: model.title(of: session) ?? "", text: out, scope: .run(last.runId)))
                    }
                }
                if loading && rows.isEmpty { ProgressView().frame(maxWidth: .infinity) }
                if failed { Text("Couldn't load this conversation").font(.rounded(.footnote)).foregroundStyle(Theme.muted) }
                if rows.count > shown {
                    Button(loadingOlder ? "Loading…" : "Show older") { Task { await showOlder() } }
                        .buttonStyle(.plain).font(.rounded(.footnote)).foregroundStyle(Theme.cyan).disabled(loadingOlder)
                }
                ForEach(turns.reversed()) { run in
                    // A finished answer opens whole (it is cut at 6 lines here) and can be read aloud.
                    if let out = run.outputText, !out.isEmpty, run.isTerminal {
                        NavigationLink(value: Route.read(ReadItem(title: model.title(of: session) ?? "", text: out, scope: .run(run.runId)))) { turn(run) }
                            .buttonStyle(.plain)
                        // What the turn made, under its answer (each opens or plays on its own).
                        let media = MediaItem.of(output: run.output, runId: run.runId)
                        if !media.isEmpty { MediaStrip(items: media) }
                    } else { turn(run) }
                }
            }
            .padding(.bottom, 44)                  // clear of the floating Continue
        }
        .screen("")
        // Always at the bottom, however long the exchanges: talk in this conversation again.
        .toolbar {
            ToolbarItem(placement: .bottomBar) {
                Button { continueHere() } label: {
                    Label("Continue", systemImage: "waveform").labelStyle(.titleAndIcon).foregroundStyle(Theme.text)
                }
                .tint(Theme.indigoButton)
            }
        }
        .task { await load() }
    }

    /// One exchange: a finished answer as the shared message card (the question as its caption);
    /// a turn still working, or with no answer, says so (a running one can be stopped).
    @ViewBuilder private func turn(_ run: RunSummary) -> some View {
        if let out = run.outputText, !out.isEmpty, run.isTerminal {
            MessageCard(text: out, failed: run.status == "failed") { QuestionCaption(text: prompts[run.runId] ?? "") }
        } else {
            Card {
                VStack(alignment: .leading, spacing: 4) {
                    QuestionCaption(text: prompts[run.runId] ?? "")
                    HStack {
                        Text(Self.state(run)).font(.rounded(.caption2)).foregroundStyle(Theme.statusColor(run.status))
                        if run.status == "running" {
                            Spacer()
                            Button { Task { try? await model.client.cancel(runId: run.runId); full[run.runId] = nil; await load() } } label: {
                                Image(systemName: "stop.fill").foregroundStyle(Theme.red)
                            }
                            .buttonStyle(.plain).accessibilityLabel("Stop")
                        }
                    }
                }
            }
        }
    }

    static func state(_ r: RunSummary) -> String {
        switch r.status {
        case "waiting": "Needs you"
        case "running": "Working…"
        case "failed": "Didn't finish"
        case "cancelled": "Stopped"
        default: "No answer"
        }
    }

    private func load() async {
        defer { loading = false }
        guard let listed = try? await model.client.turns(ofSession: session.id, limit: 100) else { failed = rows.isEmpty; return }
        failed = false
        rows = listed.sorted { ($0.createdAt ?? "") > ($1.createdAt ?? "") }
        await readInFull(rows.prefix(shown))
    }

    private func showOlder() async {
        loadingOlder = true
        defer { loadingOlder = false }
        let more = rows.dropFirst(shown).prefix(5)
        await readInFull(more)
        shown += more.count
    }

    /// Listing rows carry neither the output nor the prompt: read them for these turns, all at once.
    private func readInFull(_ some: ArraySlice<RunSummary>) async {
        let client = model.client
        let loaded: [(RunSummary, String?)] = await withTaskGroup(of: (RunSummary, String?).self) { group in
            for r in some where full[r.runId] == nil {
                group.addTask {
                    async let f = try? client.run(id: r.runId)
                    async let p = try? client.prompt(ofRun: r.runId)
                    return ((await f) ?? r, (await p) ?? nil)
                }
            }
            var out: [(RunSummary, String?)] = []
            for await x in group { out.append(x) }
            return out
        }
        for (r, p) in loaded {
            full[r.runId] = r
            if let p { prompts[r.runId] = p }
        }
    }

    private func continueHere() {
        guard let last = latest else { Task { await model.continueSession(session) }; return }
        model.resume(session, lastPrompt: prompts[last.runId] ?? "", lastAnswer: last.outputText ?? "",
                     runId: last.runId, status: last.status)
    }
}
