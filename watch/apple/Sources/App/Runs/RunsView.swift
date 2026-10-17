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
                            SessionRow(session: s, title: model.title(of: s), opening: opening == s.id)
                        }
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
    let title: String
    var opening = false

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 5) {
                if session.needsPerson { StatusDot(color: Theme.amber) }
                else if session.status == "running" { StatusDot(color: Theme.cyan) }
                else if session.status == "failed" { StatusDot(color: Theme.red) }
                Text(title).font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.text).lineLimit(2)
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

/// One conversation: its last exchanges (question, then the answer in markdown), Continue.
struct SessionDetailView: View {
    let session: SessionSummary
    @EnvironmentObject private var model: AppModel
    @State private var turns: [RunSummary] = []
    @State private var prompts: [String: String] = [:]
    @State private var loading = true
    @State private var failed = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 6) {
                // The title is the first question: shown only when that question is not below.
                if max(session.turns, turns.count) > 6 {
                    Text(model.title(of: session)).font(.rounded(.headline)).foregroundStyle(Theme.text).lineLimit(2)
                }
                if loading && turns.isEmpty { ProgressView().frame(maxWidth: .infinity) }
                if failed { Text("Couldn't load this conversation").font(.rounded(.footnote)).foregroundStyle(Theme.muted) }
                ForEach(turns.prefix(6).reversed()) { run in
                    // A finished answer opens whole (it is cut at 6 lines here) and can be read aloud.
                    if let out = run.outputText, !out.isEmpty, run.isTerminal {
                        NavigationLink(value: Route.read(ReadItem(title: model.title(of: session), text: out, scope: .run(run.runId)))) { turn(run) }
                            .buttonStyle(.plain)
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

    private func turn(_ run: RunSummary) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            if let p = prompts[run.runId] {
                Text(p).font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.text2).lineLimit(3)
            }
            Card {
                if let out = run.outputText, !out.isEmpty, run.isTerminal {
                    MarkdownText(out).lineLimit(6)
                } else {
                    HStack {
                        Text(Self.state(run)).font(.rounded(.caption2)).foregroundStyle(Theme.statusColor(run.status))
                        if run.status == "running" {
                            Spacer()
                            Button { Task { try? await model.client.cancel(runId: run.runId); await load() } } label: {
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
        guard let rows = try? await model.client.turns(ofSession: session.id) else { failed = turns.isEmpty; return }
        failed = false
        // Listing rows carry no output: read the shown turns and their prompts, all at once.
        let shown = Array(rows.prefix(6))
        let client = model.client
        let loaded: [(Int, RunSummary, String?)] = await withTaskGroup(of: (Int, RunSummary, String?).self) { group in
            for (i, r) in shown.enumerated() {
                group.addTask {
                    async let full = try? client.run(id: r.runId)
                    async let p = try? client.prompt(ofRun: r.runId)
                    return (i, (await full) ?? r, (await p) ?? nil)
                }
            }
            var out: [(Int, RunSummary, String?)] = []
            for await x in group { out.append(x) }
            return out
        }
        turns = loaded.sorted { $0.0 < $1.0 }.map(\.1)
        for (_, r, p) in loaded { if let p { prompts[r.runId] = p } }
    }

    private func continueHere() {
        guard let last = turns.first else { Task { await model.continueSession(session) }; return }
        model.resume(session, lastPrompt: prompts[last.runId] ?? "", lastAnswer: last.outputText ?? "")
    }
}
