import CoreGraphics
import Foundation
import ImageIO

/// In-memory client reproducing the design mockups. Same protocol as the live client,
/// so the UI code path is identical; only the data is canned.
public actor MockGatewayClient: GatewayClient {
    public nonisolated let isMock = true

    public static let sampleWaits: [Wait] = [
        // An outreach send: the gateway always asks before an email to anyone but you.
        Wait(runId: "c17d20e4", waitKey: "tool_approval:3", kind: .toolApproval, reason: "user",
             details: [ToolCallDetail(name: "send_email",
                                      arguments: ["to": .string("qc-team@example.org"),
                                                  "subject": .string("Nightly assay QC: 2 plates to review"),
                                                  "body_text": .string("Hello,\n\nThe nightly QC run flagged two plates (P07, P12): control CV above 15% on the low standard. Raw curves and the flagged wells are attached as qc-2026-10-16.pdf.\n\nCould someone re-read P07 and P12 before the batch is released?\n\nThis message was drafted by the Morning digest automation and sent after approval.")])],
             workflow: "Morning digest", askedAt: Date().addingTimeInterval(-25),
             sessionId: "automation:auto-morning", automationId: "auto-morning"),
        // An automation's run reading a page: its own tools ask first for it.
        Wait(runId: "b81f3302-agent", waitKey: "tool_approval:7", kind: .toolApproval, reason: "user",
             details: [ToolCallDetail(name: "fetch_url", arguments: ["url": .string("https://www.globenewswire.com/news-release/2026/10/21/pharma")])],
             workflow: "Morning digest", askedAt: Date().addingTimeInterval(-30),
             sessionId: "automation:auto-morning", automationId: "auto-morning"),
        Wait(runId: "94a436e1", waitKey: "tool_approval:1", kind: .toolApproval, reason: "user",
             details: [ToolCallDetail(name: "execute_command",
                                      arguments: ["command": .string("rm -rf build/ && make"),
                                                  "cwd": .string("~/projects/assay-pipeline")])],
             workflow: "coding-agent", riskTier: "Destructive", askedAt: Date().addingTimeInterval(-40), sessionId: "s-build"),
        Wait(runId: "3e9a10c4", waitKey: "ask_user:1", kind: .askUser, reason: "user",
             prompt: "Two sources disagree on the phase II endpoint. Which one should I treat as primary?",
             choices: ["EMA assessment report (2025)", "Company press release", "Cite both, flag the conflict"],
             allowFreeText: true, workflow: "deep-research", askedAt: Date().addingTimeInterval(-120), sessionId: "s-qc"),
    ]

    public static let sampleRuns: [RunSummary] = {
        func r(_ id: String, _ wf: String, _ status: String, session: String, minutesAgo: Double, tools: Int, llm: Int,
               error: String? = nil, subtitle: String? = nil, output: String? = nil) -> RunSummary {
            let at = ISO8601DateFormatter().string(from: Date().addingTimeInterval(-minutesAgo * 60))
            var run = RunSummary(runId: id, workflowId: wf, status: status, sessionId: session, createdAt: at, updatedAt: at, error: error,
                                 output: output.map { .object(["response": .string($0)]) }, subtitle: subtitle)
            run.toolCalls = tools; run.llmCalls = llm; run.sessionKind = "chat"
            return run
        }
        return [
            r("94a436e1", "coding-agent", "waiting", session: "s-build", minutesAgo: 1, tools: 6, llm: 4, subtitle: "waiting for you · 40 s"),
            r("7c1e02aa", "analytics-assistant", "running", session: "s-adtte", minutesAgo: 3, tools: 3, llm: 2, subtitle: "step 4 · running the analysis"),
            r("r1a9e0b2", "analytics-assistant", "completed", session: "s-adtte", minutesAgo: 9, tools: 4, llm: 3, output: MockGatewayClient.cannedAnswer),
            r("3e9a10c4", "deep-research", "completed", session: "s-qc", minutesAgo: 12, tools: 9, llm: 6, subtitle: "done · 12 min ago",
              output: "The nightly assay QC passed: all 96 wells within range, CV 3.1 %."),
        ] + (1...7).map { n in
            r("qc-older-\(n)", "deep-research", "completed", session: "s-qc", minutesAgo: 12 + Double(n) * 1440, tools: 2, llm: 1,
              output: "Night \(n): the assay QC passed, CV \(2 + n % 3).\(n) %.")
        } + [
            r("d0c5a971", "docs-qa", "failed", session: "s-docs", minutesAgo: 95, tools: 1, llm: 1, error: "model timeout", subtitle: "failed · model timeout"),
        ]
    }()

    public static let sampleAutomations: [AutomationSummary] = [
        AutomationSummary(id: "auto-morning", name: "Morning digest", status: "active", scheduleText: "Every 24 hours (UTC)",
                          lastOccurrence: LastOccurrence(status: "completed", excerpt: "Three things today: the assay QC run passed; two new papers on your target; one dependency to pin.",
                                                         runId: "b81f3302", index: 41, firedAt: "2026-10-17T05:04:00Z", finishedAt: "2026-10-17T05:06:10Z",
                                                         answer: "Three things today: the assay QC run passed; two new papers on your target (one with a phase II readout); the dependency check found one update to pin.",
                                                         userTurn: MockGatewayClient.morningTask),
                          cadence: "daily", detail: "every day · last 07:04 · ok", nextFireAt: "2026-10-18T05:00:00Z",
                          attention: Attention(pendingWaits: 0, unread: true, unseenCount: 1, cursor: "att1:41",
                                               items: [.init(kind: "notify", runId: "b81f3302", at: "2026-10-17T05:06:10Z", title: "Morning digest", body: "3 things today", cursor: "att1:41")]),
                          contextMode: "growing", occurrenceCount: 41, triggerSource: "schedule",
                          triggerConfig: ["every": .string("24h"), "anchor": .string("2026-09-07T05:04:00Z")], revision: 2,
                          growingMaxTokens: 50_000),
        AutomationSummary(id: "auto-lit", name: "Literature watch", status: "active", scheduleText: "every 7 days",
                          lastOccurrence: LastOccurrence(status: "completed", excerpt: "3 new papers"), cadence: "weekly", detail: "every 7 days · 3 new papers"),
        AutomationSummary(id: "auto-qc", name: "Assay QC check", status: "active", scheduleText: "when a file lands",
                          lastOccurrence: LastOccurrence(status: "completed", excerpt: nil), cadence: "on event", detail: "when a file lands · ok"),
        // Same name, same task: two automations told apart by their results.
        AutomationSummary(id: "auto-news-ai", name: "investigate today's news.", status: "active", scheduleText: "Every 12 hours (UTC)",
                          lastOccurrence: LastOccurrence(status: "completed", excerpt: "AI news digest"), nextFireAt: "2026-10-18T23:21:00Z",
                          occurrenceCount: 44, triggerSource: "schedule", triggerConfig: ["every": .string("12h")], revision: 1),
        AutomationSummary(id: "auto-news-world", name: "investigate today's news.", status: "active", scheduleText: "Every 12 hours (UTC)",
                          lastOccurrence: LastOccurrence(status: "completed", excerpt: "International news digest"), nextFireAt: "2026-10-18T23:21:00Z",
                          occurrenceCount: 42, triggerSource: "schedule", triggerConfig: ["every": .string("12h")], revision: 1),
    ]

    public static let sampleEntities: [EntitySummary] = [
        EntitySummary(name: "castor", extra: ["phase": .string("work"), "age": .string("long-lived"),
                                              "appearance": .object(["color": .string("#f59e0b"), "shape": .string("kitty")])]),
        EntitySummary(name: "mira", extra: ["phase": .string("personal"),
                                            "appearance": .object(["color": .string("#f472b6"), "shape": .string("face")])]),
        EntitySummary(name: "nerin", extra: ["phase": .string("sleep"),
                                             "appearance": .object(["color": .string("#2dd4bf"), "shape": .string("wave")])]),
    ]
    public static let cannedEntityReply = "Yes. The nightly QC finished at 02:14 and passed on 10 of 12 plates; P07 and P12 are flagged for a re-read, and I drafted a note to the QC team that is waiting for your approval."

    /// A markdown answer, as agents write them (screenshots of the renderer).
    public static let markdownAnswer = """
    ## Survival by arm
    Overall survival **favoured arm B**: HR *0.78* (95% CI 0.61–0.99).

    - n = 412, `287` events
    - Proportional hazards held (p = 0.41)
      - checked with Schoenfeld residuals

    | Arm | Median OS |
    |---|---|
    | A | 14.2 mo |
    | B | 17.9 mo |

    > Exploratory: not adjusted for multiplicity.

    Source: [the SAP](https://example.org/sap) · https://clinicaltrials.gov
    """
    public static let cannedAnswer = "Overall survival favoured arm B: HR 0.78 (95% CI 0.61–0.99), n = 412, 287 events. Proportional hazards held (Schoenfeld p = 0.41)."

    private var pending: [Wait]
    private var started: [String: (Date, String)] = [:]
    private let wordInterval: TimeInterval

    /// How long the automations take to answer (a public gateway's is the slow call, ~7 s), and how
    /// many of the first calls fail (a request that times out over a watch's radio).
    private let automationsDelay: Duration
    private var automationsFailures: Int
    /// How long an automation's definition takes to read (a public gateway's take seconds).
    private let definitionDelay: Duration
    /// How many polls fail before the gateway answers (a watch whose radio is still coming up);
    /// `.max`: it never does.
    private var pollFailures: Int

    public init(waits: [Wait] = MockGatewayClient.sampleWaits, wordInterval: TimeInterval = 0.12, automationsDelay: Duration = .zero,
                automationsFailures: Int = 0, pollFailures: Int = 0, definitionDelay: Duration = .zero) {
        self.definitionDelay = definitionDelay
        self.pending = waits; self.wordInterval = wordInterval; self.automationsDelay = automationsDelay
        self.automationsFailures = automationsFailures; self.pollFailures = pollFailures
    }

    public func health() async throws -> Bool { true }
    public func me() async throws -> Principal {
        if pollFailures > 0 { throw URLError(.notConnectedToInternet) }
        return Principal(userId: "albou", tenantId: "default", roles: ["admin"])
    }
    public func waits() async throws -> [Wait] {
        if pollFailures > 0 {
            if pollFailures != .max { pollFailures -= 1 }
            throw URLError(.notConnectedToInternet)
        }
        return pending
    }
    public func recentRuns(limit: Int) async throws -> [RunSummary] { Self.sampleRuns.filter { !archived.contains($0.sessionId ?? "") } }
    /// Archived conversations (`POST /sessions/{id}/archive`): out of the listing, nothing deleted.
    private var archived: Set<String> = []
    public func setArchived(sessionId: String, _ on: Bool) async throws {
        try await Task.sleep(for: .milliseconds(300))
        if on { archived.insert(sessionId) } else { archived.remove(sessionId) }
    }
    public func archivedRuns(limit: Int) async throws -> [RunSummary] { Self.sampleRuns.filter { archived.contains($0.sessionId ?? "") } }
    /// Words found in the sample conversations' questions and answers (every word, any case).
    public func searchSessions(_ query: String, limit: Int) async throws -> SessionSearchPage {
        try await Task.sleep(for: .milliseconds(400))
        let words = query.lowercased().split(whereSeparator: { !$0.isLetter && !$0.isNumber }).map(String.init)
        var hits: [String: SessionHit] = [:]
        for r in Self.sampleRuns where !archived.contains(r.sessionId ?? "") {
            let prompt = (try await self.prompt(ofRun: r.runId)) ?? "", answer = r.outputText ?? ""
            for (text, place) in [(prompt, "question"), (answer, "answer")] {
                let low = text.lowercased()
                guard !words.isEmpty, words.allSatisfy(low.contains), let sid = r.sessionId, hits[sid] == nil else { continue }
                let marks = words.compactMap { w in low.range(of: w).map { [low.distance(from: low.startIndex, to: $0.lowerBound), w.count] } }
                hits[sid] = SessionHit(sessionId: sid, runId: r.runId, prompt: prompt, snippet: text, matchedIn: place, highlights: marks, updatedAt: r.updatedAt)
            }
            // What the turn made: its media, by what each was made from.
            for m in Self.sampleMedia[r.runId] ?? [] {
                let made = Self.samplePrompts[m.artifactId] ?? "", low = made.lowercased()
                guard !words.isEmpty, words.allSatisfy(low.contains), let sid = r.sessionId, hits[sid] == nil else { continue }
                let marks = words.compactMap { w in low.range(of: w).map { [low.distance(from: low.startIndex, to: $0.lowerBound), w.count] } }
                hits[sid] = SessionHit(sessionId: sid, runId: r.runId, prompt: prompt, snippet: made, matchedIn: "artifact", highlights: marks,
                                       updatedAt: r.updatedAt, media: m, artifactKind: "image")
            }
        }
        return SessionSearchPage(items: Array(hits.values.prefix(limit)))
    }
    public func automations() async throws -> [AutomationSummary] {
        if automationsDelay > .zero { try await Task.sleep(for: automationsDelay) }
        if automationsFailures > 0 { automationsFailures -= 1; throw URLError(.timedOut) }
        var out: [AutomationSummary] = []
        for a in Self.sampleAutomations where !archivedAutomationIds.contains(a.id) { out.append(try await automation(id: a.id)) }
        return out
    }
    /// Run now: the automation runs for 14 s (`current_occurrence` set, a ledger that moves on).
    private var automationRunStarted: [String: Date] = [:]
    public func runAutomationNow(id: String) async throws {
        // As the gateway: one run at a time.
        if let t = automationRunStarted[id], Date().timeIntervalSince(t) < 14 {
            throw GatewayError.http(status: 409, body: #"{"reason_code":"automation_busy"}"#)
        }
        automationRunStarted[id] = Date()
        // Its run: working for 10 s, then its answer (as the occurrence it is).
        started["occ-live"] = (Date().addingTimeInterval(10), "Digest 42: the assay QC run passed; nothing new to pin.")
    }
    /// The task the morning digest's trigger sends.
    public static let morningTask = "Summarise what changed overnight: QC runs, new papers on my target, dependency updates."
    public func discussAutomation(id: String, occurrenceIndex: Int, prompt: String) async throws -> Discussion {
        // As the gateway: only a run that happened can be talked about.
        guard let last = Self.sampleAutomations.first(where: { $0.id == id })?.lastOccurrence?.index, occurrenceIndex <= last
        else { throw GatewayError.http(status: 404, body: "occurrence_not_found") }
        let run = "mock-" + UUID().uuidString.prefix(6).lowercased()
        started[run] = (Date(), "About that run: the QC passed on every plate; the two papers are linked in the digest.")
        return Discussion(sessionId: "discussion-session:" + run, runId: run)
    }
    public func automation(id: String) async throws -> AutomationSummary {
        guard var a = Self.sampleAutomations.first(where: { $0.id == id }) else { throw GatewayError.http(status: 404, body: "") }
        if let status = automationStatus[id] { a.status = status }
        if let t = revisedTitle[id] { a.name = t }
        if let n = revisions[id] { a.revision = (a.revision ?? 1) + n }
        if let t = automationRunStarted[id], Date().timeIntervalSince(t) < 14 {
            a.currentOccurrence = CurrentOccurrence(index: (a.lastOccurrence?.index ?? 0) + 1, runId: "occ-live", attempt: 1, status: "running")
        } else { automationRunStarted[id] = nil }
        return a
    }
    /// The live occurrence's agent steps, by seconds since Run now.
    private func liveLedger() -> [LedgerRecord] {
        let s = Date().timeIntervalSince(automationRunStarted.values.first ?? Date())
        func call(_ n: [String]) -> JSONValue { .object(["type": .string("tool_calls"), "payload": .object(["tool_calls": .array(n.map { .object(["name": .string($0)]) })])]) }
        let llm: JSONValue = .object(["type": .string("llm_call")])
        var out = [LedgerRecord(nodeId: "reason", status: "started", effect: llm)]
        if s > 3 { out.append(LedgerRecord(nodeId: "act", status: "started", effect: call(["skim_websearch", "skim_websearch", "skim_websearch"]))) }
        if s > 6 { out.append(LedgerRecord(nodeId: "act", status: "started", effect: call(["skim_url", "skim_url", "skim_url", "skim_url"]))) }
        if s > 9 { out.append(LedgerRecord(nodeId: "reason", status: "started", effect: llm)) }
        return out
    }
    /// Pause / resume / archive, as the gateway applies them (the sample automations' state).
    private var automationStatus: [String: String] = [:]
    private var archivedAutomationIds: Set<String> = []
    public func automationCommand(id: String, type: String) async throws {
        try await Task.sleep(for: .milliseconds(300))
        switch type {
        case "automation.pause": automationStatus[id] = "paused"
        case "automation.resume": automationStatus[id] = "active"
        case "automation.archive": archivedAutomationIds.insert(id)
        case "automation.unarchive": archivedAutomationIds.remove(id)
        default: break
        }
    }
    public func automationDefaults() async throws -> AutomationDefaults { AutomationDefaults(growingMaxTokens: 50_000) }
    public func archivedAutomations() async throws -> [AutomationSummary] {
        var out: [AutomationSummary] = []
        for a in Self.sampleAutomations where archivedAutomationIds.contains(a.id) { out.append(try await automation(id: a.id)) }
        return out
    }
    /// A revision's new title and task, kept (the list, the page and the next edit show them).
    private var revisedTitle: [String: String] = [:]
    private var revisedTask: [String: String] = [:]
    private var revisions: [String: Int] = [:]
    public func reviseAutomation(id: String, changes: [String: JSONValue], expectedRevision: Int?) async throws {
        if let t = changes["title"]?.stringValue { revisedTitle[id] = t }
        if let p = changes["target"]?["input_data"]?["prompt"]?.stringValue { revisedTask[id] = p }
        revisions[id, default: 0] += 1
    }
    public func workflows(forInterface interface: String) async throws -> [WorkflowChoice] {
        if interface == WorkflowChoice.assistantInterface {
            return [WorkflowChoice(bundleId: "abstractassistant-orchestrator", bundleVersion: "0.0.0", flowId: "d5d4e5a1",
                                   name: "AbstractAssistant Orchestrator", isDefault: true, interface: interface, registryScope: "private")]
        }
        return [WorkflowChoice(bundleId: "basic-agent", bundleVersion: "0.0.5", flowId: "81795ea9", name: "Basic agent", isDefault: true),
                WorkflowChoice(bundleId: "deep-research", bundleVersion: "0.1.8", flowId: "deep-research", name: "Deep research"),
                WorkflowChoice(bundleId: "memact-agent", bundleVersion: "0.1.0", flowId: "memact", name: "MemAct agent")]
    }
    public func conversationWorkflows() async throws -> [WorkflowChoice] {
        WorkflowChoice.conversation(agents: try await workflows(forInterface: WorkflowChoice.agentInterface),
                                    assistant: try await workflows(forInterface: WorkflowChoice.assistantInterface))
    }

    /// The media of the sample conversations: an image made in the ADTTE session's earlier turn.
    /// What each sample artifact was made from (search finds them by it).
    static let samplePrompts: [String: String] = ["img-km-curve": "Kaplan–Meier survival curve by treatment arm, two lines"]
    public static let sampleMedia: [String: [MediaItem]] = [
        "r1a9e0b2": [MediaItem(artifactId: "img-km-curve", runId: "r1a9e0b2", contentType: "image/png", kind: .image, sizeBytes: 40_000)],
        // An earlier QC answer with a recording (its row on the message page has a player of its own).
        "qc-older-1": [MediaItem(artifactId: "wav-qc-older-1", runId: "qc-older-1", contentType: "audio/wav", kind: .audio, sizeBytes: 96_044)],
    ]
    public func sessionMedia(sessionId: String) async throws -> [String: [MediaItem]] {
        try await Task.sleep(for: .milliseconds(300))
        var out = Self.sampleMedia.filter { id, _ in Self.sampleRuns.contains { $0.runId == id && $0.sessionId == sessionId } }
        for (id, media) in startedMedia { out[id] = media }
        return out
    }
    /// A conversation's files: its turns' media, a report the QC conversation was given, and the
    /// chart its assistant wrote into its folder.
    public func sessionFiles(sessionId: String, folderRunId: String?) async throws -> SessionFiles {
        try await Task.sleep(for: .milliseconds(300))
        var files = try await sessionMedia(sessionId: sessionId).values.flatMap { $0 }.map {
            SessionFile(artifactId: $0.artifactId, runId: $0.runId, contentType: $0.contentType, sizeBytes: $0.sizeBytes,
                        createdAt: Date().addingTimeInterval(-3600), origin: .made)
        }
        if sessionId == "s-qc" {
            files.append(SessionFile(artifactId: "doc-qc-report", runId: "3e9a10c4", contentType: "application/pdf", name: "qc-report.pdf",
                                     sizeBytes: 182_400, createdAt: Date().addingTimeInterval(-7200), origin: .attached))
        }
        if sessionId == "s-qc", let run = folderRunId {
            for (k, (path, type)) in [("charts/cv-by-plate.svg", "image/svg+xml"), ("hero.svg", "image/svg+xml"), ("notes.md", "text/markdown")].enumerated() {
                files.append(SessionFile(artifactId: "", runId: run, contentType: type, name: path, sizeBytes: Self.folderFiles[path]?.utf8.count,
                                         createdAt: Date().addingTimeInterval(-1800 - Double(k) * 60), origin: .made, folderPath: path))
            }
        }
        return SessionFiles(files: Array(Set(files)), spokenQuestions: sessionId == "s-qc" ? 3 : 0).adding([])
    }
    /// What the QC conversation's assistant wrote into its folder: a chart, a drawing an agent made
    /// (verbatim), and notes.
    static let folderFiles: [String: String] = [
        "charts/cv-by-plate.svg": #"""
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300">
          <defs><linearGradient id="bar" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#22d3ee"/><stop offset="1" stop-color="#6366f1"/></linearGradient></defs>
          <rect width="400" height="300" rx="18" fill="#0f172a"/>
          <text x="24" y="42" font-family="Helvetica" font-size="22" font-weight="bold" fill="#e2e8f0">CV by plate</text>
          <g fill="url(#bar)"><rect x="40" y="150" width="44" height="110" rx="6"/><rect x="110" y="110" width="44" height="150" rx="6"/>
          <rect x="180" y="170" width="44" height="90" rx="6"/><rect x="250" y="90" width="44" height="170" rx="6"/><rect x="320" y="130" width="44" height="130" rx="6"/></g>
          <path d="M24 260H380" stroke="#475569" stroke-width="2"/>
          <path d="M40 120 Q 120 60 200 100 T 360 80" fill="none" stroke="#f472b6" stroke-width="4" stroke-linecap="round" stroke-dasharray="10 8"/>
          <circle cx="360" cy="80" r="7" fill="#f472b6"/>
          <path d="M330 40 a 18 18 0 1 1 36 0 a 18 18 0 1 1 -36 0z" fill="none" stroke="#facc15" stroke-width="3"/>
        </svg>
        """#,
        "hero.svg": #"""
        <svg xmlns="http://www.w3.org/2000/svg" width="1600" height="1000" viewBox="0 0 1600 1000" role="img" aria-label="Abstract AI orchestration modules">
          <defs>
            <linearGradient id="bg" x2="1" y2="1"><stop stop-color="#05081a"/><stop offset=".48" stop-color="#0b1234"/><stop offset="1" stop-color="#17092f"/></linearGradient>
            <radialGradient id="glow"><stop stop-color="#77f7ff" stop-opacity=".72"/><stop offset=".34" stop-color="#6366ff" stop-opacity=".2"/><stop offset="1" stop-color="#09112b" stop-opacity="0"/></radialGradient>
            <linearGradient id="glass" x2="1" y2="1"><stop stop-color="#e9ffff" stop-opacity=".22"/><stop offset="1" stop-color="#6671ff" stop-opacity=".06"/></linearGradient>
            <linearGradient id="line" x2="1"><stop stop-color="#62f6ff" stop-opacity="0"/><stop offset=".5" stop-color="#9f8cff"/><stop offset="1" stop-color="#62f6ff" stop-opacity="0"/></linearGradient>
            <filter id="blur"><feGaussianBlur stdDeviation="24"/></filter><filter id="shadow"><feDropShadow dx="0" dy="22" stdDeviation="24" flood-color="#00051a" flood-opacity=".75"/></filter>
          </defs>
          <rect width="1600" height="1000" fill="url(#bg)"/>
          <ellipse cx="800" cy="490" rx="640" ry="520" fill="url(#glow)"/>
          <g opacity=".22" stroke="#8ccfff" fill="none"><path d="M0 160H1600M0 360H1600M0 560H1600M0 760H1600"/><path d="M220 0V1000M520 0V1000M820 0V1000M1120 0V1000M1420 0V1000"/></g>
          <g fill="none" stroke="url(#line)" stroke-width="3" opacity=".9"><path d="M260 660C390 660 380 490 528 490"/><path d="M1070 490c160 0 130-190 270-190"/><path d="M520 750c160 0 135-135 278-135"/><path d="M1040 650c120 0 110 120 260 120"/></g>
          <g fill="#8dffff"><circle cx="260" cy="660" r="6"/><circle cx="528" cy="490" r="7"/><circle cx="1340" cy="300" r="6"/><circle cx="1300" cy="770" r="6"/></g>
          <g filter="url(#shadow)" stroke="#c2f8ff" stroke-opacity=".35">
            <g transform="translate(510 280)"><rect width="265" height="185" rx="20" fill="url(#glass)"/><path d="M28 47h73M28 72h119M28 129h206" stroke="#bdffff" stroke-opacity=".65" stroke-width="4" stroke-linecap="round"/><circle cx="214" cy="55" r="21" fill="#7df5ff" fill-opacity=".82" stroke="none"/></g>
            <g transform="translate(842 390)"><rect width="285" height="210" rx="22" fill="url(#glass)"/><path d="M32 50h83M32 78h178M32 145h220M32 169h142" stroke="#d6d7ff" stroke-opacity=".64" stroke-width="4" stroke-linecap="round"/><path d="M220 50l25 25-25 25-25-25z" fill="#a78bfa" fill-opacity=".85" stroke="none"/></g>
            <g transform="translate(585 590)"><rect width="305" height="198" rx="22" fill="url(#glass)"/><path d="M34 55h104M34 82h194M34 146h239" stroke="#d2ffff" stroke-opacity=".62" stroke-width="4" stroke-linecap="round"/><circle cx="242" cy="66" r="24" fill="#6a72ff" fill-opacity=".8" stroke="none"/></g>
          </g>
          <g transform="translate(800 505)" filter="url(#shadow)"><circle r="115" fill="#111c49" stroke="#9bfbff" stroke-width="2"/><circle r="84" fill="none" stroke="#806cff" stroke-width="2" stroke-dasharray="6 10"/><path d="M-42-24L0-50 42-24v48L0 50-42 24z" fill="#91faff" fill-opacity=".9"/><circle r="14" fill="#151c53"/></g>
          <g fill="#e8ffff" font-family="Arial, sans-serif" text-anchor="middle"><text x="800" y="890" font-size="22" letter-spacing="9" opacity=".72">ORCHESTRATE · GENERATE · DEPLOY</text></g>
          <g fill="#88efff" opacity=".8"><circle cx="102" cy="120" r="2"/><circle cx="180" cy="800" r="3"/><circle cx="1450" cy="190" r="3"/><circle cx="1510" cy="690" r="2"/><circle cx="1210" cy="870" r="3"/></g>
        </svg>
        """#,
        "notes.md": "# Nightly QC\n\nAll 96 wells within range. CV 3.1 % (target under 5 %).\n\n- Plate 4 ran warm: re-check the incubator log.\n- Next run: Tuesday 02:00.\n",
    ]
    public func fileData(_ file: SessionFile) async throws -> Data {
        if let path = file.folderPath {
            try await Task.sleep(for: .milliseconds(300))
            guard let text = Self.folderFiles[path] else { throw GatewayError.http(status: 404, body: "") }
            return Data(text.utf8)
        }
        if let media = file.media { return try await mediaData(media) }
        try await Task.sleep(for: .milliseconds(300))
        return Data("%PDF-1.4 sample".utf8)
    }
    public func mediaData(_ item: MediaItem) async throws -> Data {
        try await Task.sleep(for: .milliseconds(500))
        switch item.kind {
        case .image: return SyntheticImage.png(seed: item.artifactId.count)
        case .audio: return SyntheticSpeech.wav(seconds: 3.0, seed: 3)
        case .video: throw GatewayError.http(status: 404, body: "")
        }
    }
    public func workflowInputs(_ w: WorkflowChoice) async throws -> WorkflowInputs {
        WorkflowInputs(defaults: ["use_context": .bool(false)], required: w.bundleId == "memact-agent" ? ["prompt"] : [])
    }
    public func createAutomation(_ a: NewAutomation) async throws -> AutomationSummary {
        try await Task.sleep(for: .milliseconds(600))
        return AutomationSummary(id: "auto-" + a.requestId.prefix(6), name: a.title, status: "active", scheduleText: nil, lastOccurrence: nil,
                                 triggerSource: "schedule", triggerConfig: { switch a.when {
                                     case .every(let e): ["kind": .string("every"), "every": .string(e)]
                                     case .daily(let at): ["kind": .string("daily"), "at": .string(at)] } }(), revision: 1)
    }
    public func automationDefinition(id: String) async throws -> AutomationDefinition {
        if definitionDelay > .zero { try await Task.sleep(for: definitionDelay) }
        let base = Self.sampleAutomations.first { $0.id == id }
        return AutomationDefinition(revision: (base?.revision ?? 1) + (revisions[id] ?? 0), title: revisedTitle[id] ?? base?.name, target: [
            "bundle_ref": .string("basic-agent@0.0.5"), "flow_id": .string("81795ea9"),
            "input_data": .object(["prompt": .string(revisedTask[id] ?? (id.hasPrefix("auto-news") ? "investigate today's news." : "Summarise the overnight assay QC runs, new papers on my target, and dependency updates to pin.")),
                                   // The morning digest's own tools: the web, a page read asks first.
                                   "tools": .array(id == "auto-morning" ? [.string("web_search"), .string("fetch_url")] : [.string("web_search")])]
                                   .merging(id == "auto-morning" ? ["_runtime": .object([
                                       "allowed_tools": .array([.string("web_search"), .string("fetch_url")]),
                                       "tool_policy": .object(["auto_approve_tools": .array([.string("web_search")]),
                                                               "require_approval_tools": .array([.string("fetch_url")])])])] : [:]) { a, _ in a }),
        ])
    }
    public func entities() async throws -> [EntitySummary] { Self.sampleEntities }
    public func openEntityChat(name: String) async throws -> String { "chat-" + name }
    public func entityChatTurn(name: String, chatId: String, text: String) async throws -> String {
        try await Task.sleep(for: .seconds(1.6))
        return Self.cannedEntityReply
    }

    public static let sampleLedger: [LedgerRecord] = [
        LedgerRecord(nodeId: "plan", status: "completed", effect: .object(["type": .string("llm_call")]), result: .object(["output": .object(["response": .string("plan: KM + Cox by TRT01P")])])),
        LedgerRecord(nodeId: "write_code", status: "completed", effect: .object(["type": .string("llm_call")]), result: .object(["mode": .string("code v1")])),
        LedgerRecord(nodeId: "run", status: "failed", effect: .object(["type": .string("tool_calls")]), error: "KeyError 'ARM'"),
        LedgerRecord(nodeId: "write_code", status: "completed", effect: .object(["type": .string("llm_call")]), result: .object(["mode": .string("code v2 · traceback in context")])),
        LedgerRecord(nodeId: "run", status: "completed", effect: .object(["type": .string("tool_calls")]), result: .object(["tool_calls": .array([.object(["name": .string("python analysis/run.py")])])])),
        LedgerRecord(nodeId: "review", status: "started", effect: .object(["type": .string("llm_call")])),
    ]
    public func ledger(runId: String, after: Int) async throws -> LedgerPage {
        if runId == "occ-live" { let all = liveLedger(); return LedgerPage(items: Array(all.dropFirst(min(after, all.count))), nextAfter: all.count) }
        return LedgerPage(items: Array(Self.sampleLedger.dropFirst(min(after, Self.sampleLedger.count))), nextAfter: Self.sampleLedger.count)
    }
    public func cancel(runId: String) async throws { started[runId] = nil; scripted[runId] = nil }

    public func activity(runId: String, after: Int) async throws -> ActivityPage {
        guard let s = scripted[runId] else { return ActivityPage(items: [], nextAfter: after) }
        let all = Self.timeline(s, at: Date()).records
        return ActivityPage(items: Array(all.dropFirst(min(after, all.count))), nextAfter: all.count)
    }

    // MARK: A scripted run ("look up", "research", "check")

    /// Thinks, searches, reads two pages, asks to run a command (waits for you), thinks, asks to
    /// run a second one, then answers: the activity a person follows on the orb page.
    private struct Scripted { let t0: Date; var answered: [Int: Date] = [:]; var segs: [Seg] = MockGatewayClient.script }
    private var scripted: [String: Scripted] = [:]
    /// The conversation each run started here belongs to (a wait says whose it is).
    private var runSession: [String: String] = [:]
    public static let researchAnswer = "Your disk has 42 GB free; the two largest folders are caches you can clear."
    private enum Seg {
        case think(Double, String?)
        case tools([(String, JSONValue)], Double)
        case approve(String, JSONValue, Double)
    }
    private static let script: [Seg] = [
        .think(1.4, "I'll look for what usually fills a disk first."),
        .tools([("web_search", .object(["query": .string("what fills a Mac disk caches logs")]))], 1.2),
        .think(1.0, "Two guides look useful; reading them."),
        .tools([("skim_url", .object(["url": .string("https://support.apple.com/en-us/102624")])),
                ("skim_url", .object(["url": .string("https://example.org/guides/disk-space")]))], 1.6),
        .approve("execute_command", .object(["command": .string("df -h /")]), 1.0),
        .think(3.0, "Now the largest folders."),
        .approve("execute_command", .object(["command": .string("du -sh ~/Library/Caches")]), 1.0),
        .think(1.2, nil),
    ]
    /// "Read the news": it asks twice to open a web page (a tool whose destination the assistant
    /// picks), so an Accept all on the first must spare the second.
    private static let pagesScript: [Seg] = [
        .think(1.0, "Opening the front page."),
        .approve("fetch_url", .object(["url": .string("https://www.franceinfo.fr/")]), 1.0),
        .think(1.5, "One story needs a closer read."),
        .approve("fetch_url", .object(["url": .string("https://www.franceinfo.fr/france/nouvelle-aquitaine/")]), 1.0),
        .think(1.0, nil),
    ]

    private static func iso(_ d: Date) -> String {
        let f = ISO8601DateFormatter(); f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]; return f.string(from: d)
    }

    /// The records due at `now`, the wait (if one is open) and whether the run is done.
    private static func timeline(_ s: Scripted, at now: Date) -> (records: [ActivityRecord], waiting: RunWaiting?, done: Bool) {
        var out: [ActivityRecord] = []
        var t = s.t0.addingTimeInterval(1.0)                       // the gateway starts the agent
        for (i, seg) in s.segs.enumerated() {
            guard now >= t else { return (out, nil, false) }
            let step = "s\(i)"
            switch seg {
            case .think(let d, let text):
                out.append(ActivityRecord(stepId: step, nodeId: "reason", status: "started", type: "llm_call", startedAt: iso(t)))
                guard now >= t + d else { return (out, nil, false) }
                out.append(ActivityRecord(stepId: step, nodeId: "reason", status: "completed", type: "llm_call", startedAt: iso(t), endedAt: iso(t + d), text: text))
                t += d
            case .tools(let calls, let d):
                let c = calls.map { ActivityRecord.Call(name: $0.0, detail: ToolDetail.preview($0.0, $0.1)) }
                out.append(ActivityRecord(stepId: step, nodeId: "act", status: "started", type: "tool_calls", startedAt: iso(t), calls: c))
                guard now >= t + d else { return (out, nil, false) }
                out.append(ActivityRecord(stepId: step, nodeId: "act", status: "completed", type: "tool_calls", startedAt: iso(t), endedAt: iso(t + d),
                                          calls: c, outcomes: c.map { _ in .init(success: true) }))
                t += d
            case .approve(let name, let args, let d):
                let c = [ActivityRecord.Call(name: name, detail: ToolDetail.preview(name, args))]
                let key = "tool_approval:\(i)"
                out.append(ActivityRecord(stepId: step, nodeId: "act", status: "waiting", type: "tool_calls", startedAt: iso(t), calls: c,
                                          waitReason: "user", waitKey: key))
                guard let yes = s.answered[i] else {
                    let details: JSONValue = .object(["mode": .string("approval_required"),
                                                      "tool_calls": .array([.object(["name": .string(name), "arguments": args])])])
                    return (out, RunWaiting(reason: "user", waitKey: key, details: details), false)
                }
                let start = max(t, yes)
                guard now >= start + d else { return (out, nil, false) }
                out.append(ActivityRecord(stepId: step, nodeId: "act", status: "completed", type: "tool_calls", startedAt: iso(start), endedAt: iso(start + d),
                                          calls: c, outcomes: [.init(success: true)]))
                t = start + d
            }
        }
        return (out, nil, now >= t)
    }
    public func occurrences(automationId: String, limit: Int) async throws -> [LastOccurrence] {
        guard let last = Self.sampleAutomations.first(where: { $0.id == automationId })?.lastOccurrence else { return [] }
        guard let top = last.index, top > 1 else { return [last] }
        if limit > 1 { try await Task.sleep(for: .seconds(3)) }   // like a public gateway: full answers take seconds
        // Earlier runs, a day apart; one failed.
        let older = (max(1, top - min(limit, 12) + 1)..<top).reversed().map { i -> LastOccurrence in
            let day = Date(timeIntervalSince1970: 1_792_213_440 - Double(top - i) * 86_400)
            let failed = i == top - 2
            return LastOccurrence(status: failed ? "failed" : "completed", excerpt: nil, runId: "occ-\(i)", index: i,
                                  firedAt: ISO8601DateFormatter().string(from: day),
                                  answer: failed ? "The run stopped: the model was not reachable." : "Digest \(i): the assay QC run passed; nothing new to pin.",
                                  userTurn: Self.morningTask)
        }
        return [last] + older
    }
    public func markSeen(automationId: String, cursor: String) async throws {}

    /// Two short synthetic "sentences" (a voiced tone with a syllable envelope), so the read screen and
    /// the orb can be exercised without a gateway.
    /// The person's event stream (canned: empty unless a test appends to it).
    public var userEvents: [UserEvent] = []
    public func appendEvent(_ e: UserEvent) { userEvents.append(e) }

    public func events(after: Int, limit: Int) async throws -> UserEventsPage {
        let rest = userEvents.filter { $0.sequence > after }
        let page = Array(rest.prefix(limit))
        return UserEventsPage(stream: "user:default:mock", events: page, nextAfter: page.last?.sequence ?? after,
                              head: userEvents.last?.sequence ?? 0, more: rest.count > limit)
    }

    public func emailStatus() async throws -> EmailStatus {
        EmailStatus(configured: false, address: nil, agentToolsOn: false, reason: "Connect a mailbox first.")
    }

    public func voiceCatalog() async throws -> VoiceCatalog {
        try await Task.sleep(for: .seconds(4))   // like a slow gateway over a watch's radio
        return VoiceCatalog(voices: ["M1", "M2", "F1", "F2"].map { VoiceChoice(provider: "supertonic", model: "supertonic-3", voice: $0, label: "Supertonic \($0)",
                                                                        gender: $0.hasPrefix("F") ? "female" : "male") },
                     transcription: ["tiny", "base", "small", "large-v3"].map { TranscriptionChoice(provider: "faster-whisper", model: $0) },
                     defaultVoice: "supertonic-3", defaultTranscription: "faster-whisper base")
    }

    public func transcribe(wav: Data, sessionId: String, model: TranscriptionChoice?) async throws -> String {
        try await Task.sleep(for: .milliseconds(900))
        return "Compare overall survival by treatment arm in the ADTTE I sent you"
    }

    public nonisolated func speech(text: String, scope: SpeechScope, voice: VoiceChoice?) -> AsyncThrowingStream<Data, Error> {
        AsyncThrowingStream { continuation in
            Task {
                // The public gateway's timeline (measured 2026-10-17): a first piece of two words
                // (1.3 s of audio) after about 1 s, the rest of the sentence about 3.4 s later.
                try? await Task.sleep(for: .milliseconds(900))
                continuation.yield(SyntheticSpeech.wav(seconds: 1.3, seed: 1))
                try? await Task.sleep(for: .milliseconds(3400))
                continuation.yield(SyntheticSpeech.wav(seconds: 8.0, seed: 2))
                // `--long-voice`: a reading long enough to outlast a detour (four more sentences).
                if ProcessInfo.processInfo.arguments.contains("--long-voice") {
                    for k in 3..<7 { try? await Task.sleep(for: .milliseconds(1500)); continuation.yield(SyntheticSpeech.wav(seconds: 8.0, seed: k)) }
                }
                continuation.finish()
            }
        }
    }

    public func answer(_ wait: Wait, with answer: WaitAnswer) async throws {
        if var s = scripted[wait.runId], let i = Int(wait.waitKey.split(separator: ":").last ?? "") {
            s.answered[i] = Date(); scripted[wait.runId] = s
            approvals.append(wait.waitKey)
            return
        }
        pending.removeAll { $0.id == wait.id }
    }

    public func prompt(ofRun id: String) async throws -> String? {
        if id.hasPrefix("qc-older-") { return "Did the assay QC pass, \(id.dropFirst(9)) nights ago?" }
        return ["94a436e1": "Clean the build folder and rebuild the app", "7c1e02aa": "Now split it by age group",
         "r1a9e0b2": "Compare overall survival by treatment arm in the ADTTE I sent you",
         "3e9a10c4": "Did the nightly assay QC pass?", "d0c5a971": "Summarise the open issues in the docs"][id]
    }

    public func sessionHistory(latestRun runId: String, limit: Int) async throws -> [SessionTurn] {
        guard let session = Self.sampleRuns.first(where: { $0.runId == runId })?.sessionId else { return [] }
        var out: [SessionTurn] = []
        for r in Self.sampleRuns where r.sessionId == session {
            out.append(SessionTurn(runId: r.runId, createdAt: r.createdAt, prompt: try await prompt(ofRun: r.runId),
                                   answer: r.outputText, status: r.status))
        }
        return Array(out.sorted { ($0.createdAt ?? "") < ($1.createdAt ?? "") }.suffix(limit))
    }

    public func turns(ofSession id: String, limit: Int) async throws -> [RunSummary] {
        Self.sampleRuns.filter { ($0.sessionId ?? $0.runId) == id }
    }

    public func tools() async throws -> [ToolInfo] {
        // Shaped like a real gateway's catalog: files, web and system set up; email and agora not.
        func t(_ name: String, _ tier: String, _ rank: Int, _ set: String, _ on: Bool, _ approval: String, _ about: String,
               destination: Bool = false, refined: Bool = false) -> ToolInfo {
            ToolInfo(name: name, riskTier: tier, riskRank: rank, enabled: on, description: about, toolset: set, approvalDefault: approval,
                     modelControlledDestination: destination, refined: refined)
        }
        return [
            t("list_files", "observe", 1, "files", true, "auto", "List files and folders by name or path."),
            t("read_file", "observe", 1, "files", true, "auto", "Read a text file, or a range of its lines."),
            t("search_files", "observe", 1, "files", true, "auto", "Search inside files for a pattern."),
            t("write_file", "act", 2, "files", true, "ask", "Write a file in the workspace, creating its folders."),
            t("edit_file", "act", 2, "files", true, "ask", "Change part of a file in the workspace."),
            t("web_search", "observe", 1, "web", true, "auto", "Search the web and return the top results."),
            t("fetch_url", "act", 2, "web", true, "ask", "Read a web page or a document from a URL.", destination: true),
            t("skim_url", "observe", 1, "web", true, "auto", "Skim a page: its title and a short preview."),
            t("execute_command", "destroy", 4, "system", true, "ask", "Run a command on the gateway's computer."),
            t("list_email_accounts", "observe", 1, "comms.email", false, "ask", "Show the connected email account."),
            t("send_email", "outreach", 3, "comms.email", false, "ask", "Send an email from the connected account.", refined: true),
            t("agora_check_inbox", "destroy", 4, "agora", false, "ask", "Fetch unread messages from the agora hub."),
        ]
    }

    /// The workflow of the last question, and the media each mock run made (the Assistant's
    /// workflow makes an image for "image"/"draw"/"picture", a recording for "voice"/"record").
    public private(set) var lastWorkflow: WorkflowChoice?
    /// The approvals answered on scripted runs, in order (tests read who answered what).
    public private(set) var approvals: [String] = []
    private var startedMedia: [String: [MediaItem]] = [:]

    public func startRun(prompt: String, sessionId: String?, toolPolicy: RunToolPolicy?, tools: [String]?, workflow: WorkflowChoice?, primaryImage: MediaItem?) async throws -> String {
        let id = "mock-" + UUID().uuidString.prefix(6).lowercased()
        lastWorkflow = workflow
        runSession[id] = sessionId
        let p = prompt.lowercased()
        if ["look up", "research", "check"].contains(where: p.contains) {
            scripted[id] = Scripted(t0: Date())
            return id
        }
        if p.contains("read the news") {
            scripted[id] = Scripted(t0: Date(), segs: Self.pagesScript)
            return id
        }
        if workflow?.interface == WorkflowChoice.assistantInterface, ["image", "draw", "picture"].contains(where: p.contains) {
            started[id] = (Date(), "Here is your picture.")
            startedMedia[id] = [MediaItem(artifactId: "img-" + id, runId: id, contentType: "image/png", kind: .image, sizeBytes: 40_000)]
        } else if workflow?.interface == WorkflowChoice.assistantInterface, ["voice", "record"].contains(where: p.contains) {
            started[id] = (Date(), "Here is the recording.")
            startedMedia[id] = [MediaItem(artifactId: "wav-" + id, runId: id, contentType: "audio/wav", kind: .audio, sizeBytes: 96_044)]
        } else {
            started[id] = (Date(), Self.cannedAnswer)
        }
        return id
    }

    /// A started mock run "streams": each poll reveals the words due by now, then completes.
    public func run(id: String) async throws -> RunSummary {
        if let s = scripted[id] {
            let now = Self.timeline(s, at: Date())
            if now.done {
                return RunSummary(runId: id, workflowId: "basic-agent@0.0.5:81795ea9", status: "completed", output: .object(["response": .string(Self.researchAnswer)]))
            }
            return RunSummary(runId: id, workflowId: "basic-agent@0.0.5:81795ea9", status: now.waiting == nil ? "running" : "waiting",
                              sessionId: runSession[id], waiting: now.waiting)
        }
        guard let (t0, text) = started[id] else {
            return Self.sampleRuns.first { $0.runId == id } ?? RunSummary(runId: id, workflowId: nil, status: "failed", error: "unknown run")
        }
        let words = text.split(separator: " ")
        let thinking = 1.2
        let elapsed = Date().timeIntervalSince(t0) - thinking
        let n = elapsed <= 0 ? 0 : min(words.count, Int(elapsed / wordInterval) + 1)
        let done = n >= words.count
        if done, let media = startedMedia[id] {
            // As the Assistant's workflow ends a media branch: the reply, the artifact, the outputs.
            func ref(_ m: MediaItem) -> JSONValue {
                .object(["$artifact": .string(m.artifactId), "content_type": .string(m.contentType), "size_bytes": .number(Double(m.sizeBytes ?? 0))])
            }
            let modality = media[0].kind == .image ? "image" : "voice"
            return RunSummary(runId: id, workflowId: lastWorkflow?.id, status: "completed",
                              output: .object(["response": .string(text), "success": .bool(true), "artifact": ref(media[0]),
                                               "outputs": .object([modality: .array(media.map { .object(["artifact_ref": ref($0)]) })])]))
        }
        return RunSummary(runId: id, workflowId: "@default", status: done ? "completed" : "running",
                          output: n == 0 ? nil : .string(words.prefix(n).joined(separator: " ")))
    }
}


/// A small generated picture (a glowing disc on a dark gradient), so image previews can be
/// exercised without a gateway.
public enum SyntheticImage {
    public static func png(width: Int = 480, height: Int = 360, seed: Int = 0) -> Data {
        let space = CGColorSpaceCreateDeviceRGB()
        guard let ctx = CGContext(data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: 0, space: space,
                                  bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return Data() }
        let hue = Double(seed % 7) / 7
        let colors = [CGColor(red: 0.05, green: 0.07, blue: 0.16, alpha: 1), CGColor(red: 0.2 + hue * 0.3, green: 0.12, blue: 0.45, alpha: 1)] as CFArray
        if let g = CGGradient(colorsSpace: space, colors: colors, locations: [0, 1]) {
            ctx.drawLinearGradient(g, start: .zero, end: CGPoint(x: width, y: height), options: [])
        }
        ctx.setFillColor(CGColor(red: 0.95, green: 0.3, blue: 0.25, alpha: 1))
        ctx.fillEllipse(in: CGRect(x: width / 2 - 90, y: height / 2 - 90, width: 180, height: 180))
        ctx.setFillColor(CGColor(red: 0.35, green: 0.75, blue: 0.3, alpha: 1))
        ctx.fillEllipse(in: CGRect(x: width / 2 - 10, y: height / 2 + 80, width: 40, height: 22))
        guard let image = ctx.makeImage() else { return Data() }
        let out = NSMutableData()
        guard let dest = CGImageDestinationCreateWithData(out, "public.png" as CFString, 1, nil) else { return Data() }
        CGImageDestinationAddImage(dest, image, nil)
        CGImageDestinationFinalize(dest)
        return out as Data
    }
}
