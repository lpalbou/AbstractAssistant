import AbstractGatewayClient
import SwiftUI
import WatchKit

/// Your conversations, newest first, grouped Today / Yesterday / Earlier. A tap continues one (the
/// orb opens on its last exchange); swipe for its details. One with an answer you have not seen is
/// outlined. The red button archives one on the gateway (after a confirmation); Archived, at the
/// bottom, lists them and restores one.
struct SessionsView: View {
    @EnvironmentObject private var model: AppModel
    @State private var opening: String?
    @State private var loadingOlder = false
    @State private var archiving: SessionSummary?
    @State private var archiveError: String?

    var body: some View {
        List {
            // One line: New (the orb, in a new conversation) and Search (the keyboard, then the results).
            HStack(spacing: 6) {
                Button {
                    model.newAskSession()
                    model.openOrb()
                } label: {
                    TopAction(symbol: "plus", title: "New", color: Theme.cyan)
                }
                .buttonStyle(.tap)
                .accessibilityLabel("New conversation")
                // Search the questions, answers and artifacts of every conversation (the gateway's index).
                TextFieldLink(prompt: Text("Words to find")) {
                    TopAction(symbol: "magnifyingglass", title: "Search", color: Theme.text2)
                } onSubmit: { text in
                    let q = String(text.trimmingCharacters(in: .whitespacesAndNewlines).prefix(200))   // the gateway's limit
                    if !q.isEmpty { model.path.append(.sessionSearch(q)) }
                }
                .buttonStyle(.tap)
                .accessibilityLabel("Search")
                .accessibilityIdentifier("sessions.search")
            }
            .listRowBackground(Color.clear)
            .listRowInsets(EdgeInsets(top: 2, leading: 0, bottom: 2, trailing: 0))
            if model.sessions.isEmpty {
                if model.lastRefresh == nil && !model.unreachable { ProgressView().frame(maxWidth: .infinity) }
                else {
                    Text(model.unreachable ? "Can't reach your assistant" : "No conversations yet")
                        .font(.rounded(.footnote)).foregroundStyle(Theme.muted)
                }
            }
            ForEach(groups, id: \.0) { label, items in
                Section(label) {
                    ForEach(items) { s in
                        let new = model.isNew(s)
                        HStack(spacing: 6) {
                            Button { open(s) } label: {
                                SessionRow(session: s, title: model.title(of: s),
                                           unreadable: model.unreadablePrompts.contains(s.latest.runId),
                                           opening: opening == s.id, new: new)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .contentShape(Rectangle())
                            }
                            .buttonStyle(.tap)
                            .disabled(opening != nil && opening != s.id)   // one session opens at a time
                            // Discreet, at the row's edge: a soft red symbol, a full-size touch area.
                            Button { archiving = s } label: {
                                Image(systemName: "archivebox").font(.system(size: 12, weight: .medium))
                                    .foregroundStyle(Theme.red.opacity(0.8))
                                    .frame(width: 26, height: 26)
                                    .background(Theme.red.opacity(0.12), in: Circle())
                                    .frame(width: 34, height: 44, alignment: .trailing)
                                    .contentShape(Rectangle())
                            }
                            .buttonStyle(.tap)
                            .disabled(s.isLive)                              // a conversation at work is not archived
                            .opacity(s.isLive ? 0.35 : 1)
                            .accessibilityLabel("Archive")
                            .accessibilityIdentifier("session.archive")
                        }
                        .listRowBackground(SessionRowGround(new: new))
                        .listRowInsets(EdgeInsets(top: 4, leading: 10, bottom: 4, trailing: 4))
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
            NavigationLink(value: Route.archivedSessions) {
                Label("Archived", systemImage: "archivebox").font(.rounded(.footnote)).foregroundStyle(Theme.muted)
            }
            .accessibilityIdentifier("sessions.archived")
        }
        .screen("Sessions")
        // Archiving asks first: the conversation leaves the list on every device (nothing is deleted).
        .sheet(item: $archiving) { s in
            ArchiveConfirm(title: model.title(of: s), what: .conversation) { confirmed in
                archiving = nil
                guard confirmed else { return }
                Task {
                    do { try await model.archive(s); WKInterfaceDevice.current().play(.success) }
                    catch { archiveError = AppModel.say(error) }
                }
            }
        }
        .alert("Couldn't archive", isPresented: Binding(get: { archiveError != nil }, set: { if !$0 { archiveError = nil } })) {
            Button("OK", role: .cancel) {}
        } message: { Text(archiveError ?? "") }
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
    /// Its latest answer has not been seen on this watch.
    var new = false

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 5) {
                if session.needsPerson { StatusDot(color: Theme.amber) }
                else if session.isLive { StatusDot(color: Theme.cyan) }
                else if new { Circle().fill(Theme.cyan).frame(width: 7, height: 7).accessibilityLabel("New answer") }
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
                // How long ago the conversation last changed (its newest turn, usually its answer).
                else if let at = session.updatedAt {
                    SessionStat(symbol: "clock", value: SessionRow.ago(at)).accessibilityLabel("Last activity \(SessionRow.ago(at))")
                }
            }
        }
        .padding(.vertical, 2)
        .accessibilityElement(children: .combine)
    }

    /// "just now", "4 min ago", "2 h ago", "3 d ago".
    static func ago(_ d: Date) -> String {
        let a = age(d)
        return a == "now" ? "just now" : a + " ago"
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
                        .buttonStyle(.tap).font(.rounded(.footnote)).foregroundStyle(Theme.cyan).disabled(loadingOlder)
                }
                ForEach(turns.reversed()) { run in
                    // A finished answer opens whole (it is cut at 6 lines here) and can be read aloud.
                    if let out = run.outputText, !out.isEmpty, run.isTerminal {
                        NavigationLink(value: Route.read(ReadItem(title: model.title(of: session) ?? "", text: out, scope: .run(run.runId)))) { turn(run) }
                            .buttonStyle(.tap)
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
        .task {
            if session.latest.isTerminal { model.markSeen(session: session.id, run: session.latest.runId) }
            await load()
        }
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
                            .buttonStyle(.tap).accessibilityLabel("Stop")
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

/// A conversation row's ground: outlined in cyan while its latest answer is new to you.
struct SessionRowGround: View {
    var new: Bool
    var tint: Color = Theme.cyan
    var body: some View {
        RoundedRectangle(cornerRadius: 14, style: .continuous)
            .fill(new ? tint.opacity(0.10) : Theme.card)
            .overlay {
                if new { RoundedRectangle(cornerRadius: 14, style: .continuous).strokeBorder(tint.opacity(0.75), lineWidth: 1.2) }
            }
    }
}

/// One half of a list's top line: a symbol and a word in a rounded card.
struct TopAction: View {
    let symbol: String
    let title: String
    let color: Color
    var body: some View {
        HStack(spacing: 5) {
            Image(systemName: symbol).font(.system(size: 14, weight: .semibold))
            Text(title).font(.rounded(.footnote, weight: .semibold)).lineLimit(1)
        }
        .foregroundStyle(color)
        .frame(maxWidth: .infinity, minHeight: 44)
        .background(Theme.neutralButton, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .contentShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}

/// "Archive this conversation?" (or automation) before it leaves the list.
struct ArchiveConfirm: View {
    enum What { case conversation, automation }
    let title: String?
    var what: What = .conversation
    let done: (Bool) -> Void
    var body: some View {
        ScrollView {
            VStack(spacing: 8) {
                Image(systemName: "archivebox.fill").font(.system(size: 22, weight: .semibold)).foregroundStyle(Theme.red)
                Text(what == .conversation ? "Archive this conversation?" : "Archive this automation?")
                    .font(.rounded(.headline)).multilineTextAlignment(.center)
                if let title {
                    Text(title).font(.rounded(.footnote)).foregroundStyle(Theme.text2).lineLimit(3).multilineTextAlignment(.center)
                        .accessibilityIdentifier("archive.title")
                }
                Text(what == .conversation ? "It leaves Sessions on all your devices. Nothing is deleted: Archived brings it back."
                     : "It stops running and leaves Automations on all your devices. Nothing is deleted: Archived brings it back.")
                    .font(.rounded(.caption2)).foregroundStyle(Theme.muted).multilineTextAlignment(.center)
                Button("Archive") { done(true) }
                    .buttonStyle(FilledButtonStyle(fill: Theme.redButton))
                    .accessibilityIdentifier("archive.confirm")
                Button("Cancel") { done(false) }
                    .buttonStyle(FilledButtonStyle(fill: Theme.neutralButton))
            }
            .padding(.horizontal, 4)
        }
    }
}

/// Archived conversations (`GET /runs?archived_only=true`), each with Restore.
struct ArchivedSessionsView: View {
    @EnvironmentObject private var model: AppModel
    @State private var sessions: [SessionSummary] = []
    @State private var titles: [String: String] = [:]
    @State private var loading = true
    @State private var failed = false
    @State private var restoring: String?

    var body: some View {
        List {
            if loading && sessions.isEmpty { ProgressView().frame(maxWidth: .infinity) }
            else if failed { Text("Couldn't load the archived conversations").font(.rounded(.footnote)).foregroundStyle(Theme.muted) }
            else if sessions.isEmpty { Text("Nothing archived").font(.rounded(.footnote)).foregroundStyle(Theme.muted) }
            ForEach(sessions) { s in
                VStack(alignment: .leading, spacing: 4) {
                    SessionRow(session: s, title: titles[s.latest.runId], unreadable: titles[s.latest.runId] == nil && !loading)
                    Button(restoring == s.id ? "Restoring…" : "Restore") { restore(s) }
                        .buttonStyle(FilledButtonStyle(fill: Theme.neutralButton, font: .rounded(.footnote, weight: .semibold)))
                        .disabled(restoring != nil)
                        .accessibilityIdentifier("archived.restore")
                }
            }
        }
        .screen("Archived")
        .task { await load() }
    }

    private func load() async {
        loading = true
        defer { loading = false }
        guard let runs = try? await model.client.archivedRuns(limit: 200) else { failed = true; return }
        failed = false
        sessions = SessionSummary.group(runs)
        let client = model.client
        let ids = sessions.map(\.latest.runId)
        let read: [(String, String?)] = await withTaskGroup(of: (String, String?).self) { group in
            for id in ids { group.addTask { (id, (try? await client.prompt(ofRun: id)) ?? nil) } }
            var out: [(String, String?)] = []
            for await x in group { out.append(x) }
            return out
        }
        for (id, p) in read { if let p { titles[id] = SessionSummary.title(fromPrompt: p) } }
    }

    private func restore(_ s: SessionSummary) {
        restoring = s.id
        Task {
            do {
                try await model.unarchive(s.id)
                sessions.removeAll { $0.id == s.id }
                WKInterfaceDevice.current().play(.success)
            } catch { failed = true }
            restoring = nil
        }
    }
}

/// The conversations whose questions or answers hold the words (the gateway's search: words and
/// parts of words, accents ignored, a typo forgiven), best first; a tap continues one.
struct SessionSearchView: View {
    let query: String
    @EnvironmentObject private var model: AppModel
    @State private var page: SessionSearchPage?
    @State private var problem: String?
    @State private var opening: String?

    var body: some View {
        List {
            Text("“\(query)”").font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.text2).lineLimit(2)
                .listRowBackground(Color.clear)
            if let problem {
                Text(problem).font(.rounded(.footnote)).foregroundStyle(Theme.muted)
                Button("Retry") { Task { await load() } }
            } else if let page {
                if page.items.isEmpty { Text("No conversation has these words").font(.rounded(.footnote)).foregroundStyle(Theme.muted) }
                ForEach(page.items) { hit in
                    Button { open(hit) } label: { SessionHitRow(hit: hit, opening: opening == hit.sessionId) }
                        .disabled(opening != nil)
                        .accessibilityIdentifier("search.hit")
                }
                if page.partial {
                    Text("Older conversations are still being indexed: search again in a moment for more.")
                        .font(.rounded(.caption2)).foregroundStyle(Theme.muted)
                }
            } else {
                ProgressView().frame(maxWidth: .infinity)
            }
        }
        .screen("Search")
        .task { await load() }
    }

    private func load() async {
        problem = nil
        do { page = try await model.client.searchSessions(query, limit: 25) }
        catch GatewayError.http(let status, _) where status == 404 {
            problem = "Your gateway can't search conversations yet. Updating it adds search."
        } catch { problem = AppModel.say(error) }
    }

    private func open(_ hit: SessionHit) {
        opening = hit.sessionId
        Task {
            do { try await model.openSession(id: hit.sessionId) } catch { problem = AppModel.say(error) }
            opening = nil
        }
    }
}

/// One result: the conversation's question, then the words in context, found words in bold.
struct SessionHitRow: View {
    let hit: SessionHit
    var opening = false
    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 4) {
                // Found in the question itself: the title carries the marks.
                Text(hit.snippet == hit.prompt && !hit.prompt.isEmpty ? Self.marked(hit, weight: .semibold, size: .footnote)
                     : AttributedString(hit.prompt.isEmpty ? "Conversation" : hit.prompt))
                    .font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.text).lineLimit(2)
                Spacer(minLength: 2)
                if opening { ProgressView().frame(width: 14) }
            }
            if hit.matchedIn == "artifact" {
                // Found in what the turn made or was given: the picture, or the artifact's kind and name.
                HStack(alignment: .top, spacing: 6) {
                    if let media = hit.media, media.kind == .image { MediaThumbnail(item: media, side: 44) }
                    else {
                        Image(systemName: Self.symbol(hit)).font(.system(size: 13, weight: .semibold)).foregroundStyle(Theme.cyan)
                            .frame(width: 20)
                    }
                    Text(Self.marked(hit)).font(.rounded(.caption2)).foregroundStyle(Theme.muted).lineLimit(3)
                }
            } else if hit.matchedIn == "answer" || hit.snippet != hit.prompt {
                Text(Self.marked(hit)).font(.rounded(.caption2)).foregroundStyle(Theme.muted).lineLimit(3)
            }
            if let at = hit.updatedAt.flatMap(ISO8601.date) {
                SessionStat(symbol: hit.matchedIn == "answer" ? "text.bubble" : "questionmark.bubble", value: SessionRow.age(at))
            }
        }
        .padding(.vertical, 2)
        .accessibilityElement(children: .combine)
    }

    static func symbol(_ hit: SessionHit) -> String {
        switch hit.media?.kind {
        case .image: return "photo"
        case .audio: return "waveform"
        case .video: return "film"
        case nil: return hit.artifactKind == "attachment" ? "paperclip" : "doc"
        }
    }

    /// The snippet with each found word in bold cyan (the gateway's places count Unicode scalars).
    static func marked(_ hit: SessionHit, weight: Font.Weight = .bold, size: Font.TextStyle = .caption2) -> AttributedString {
        var out = AttributedString(hit.snippet)
        let scalars = hit.snippet.unicodeScalars.count
        for h in hit.highlights where h.count == 2 && h[0] >= 0 && h[1] > 0 && h[0] + h[1] <= scalars {
            let lo = out.unicodeScalars.index(out.startIndex, offsetBy: h[0])
            let hi = out.unicodeScalars.index(lo, offsetBy: h[1])
            out[lo..<hi].foregroundColor = Theme.cyan
            out[lo..<hi].font = .rounded(size, weight: weight == .semibold ? .heavy : weight)
        }
        return out
    }
}
