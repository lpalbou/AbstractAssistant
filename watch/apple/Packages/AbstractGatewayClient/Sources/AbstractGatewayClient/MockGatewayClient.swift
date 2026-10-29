import CoreGraphics
import Foundation
import ImageIO

/// In-memory client reproducing the design mockups. Same protocol as the live client,
/// so the UI code path is identical; only the data is canned. One sample world per app (`world`):
/// the watch's screens and UI tests assert its values, the iPhone's theirs.
public actor MockGatewayClient: GatewayClient {
    public nonisolated let isMock = true

    /// Whose sample data: where the two apps' tests assert different values (an answer, a prompt,
    /// the tools, the automations), each world keeps its own; everything else is shared.
    public enum World: Sendable { case watch, phone }
    public nonisolated let world: World

    public static let sampleWaits: [Wait] = [
        // An outreach send: the gateway always asks before an email to anyone but you.
        Wait(runId: "c17d20e4", waitKey: "tool_approval:3", kind: .toolApproval, reason: "user",
             details: [ToolCallDetail(name: "send_email",
                                      arguments: ["to": .string("qc-team@example.org"),
                                                  "subject": .string("Nightly assay QC: 2 plates to review"),
                                                  "body_text": .string("Hello,\n\nThe nightly QC run flagged two plates (P07, P12): control CV above 15% on the low standard. Raw curves and the flagged wells are attached as qc-2026-10-16.pdf.\n\nCould someone re-read P07 and P12 before the batch is released?\n\nThis message was drafted by the Morning digest automation and sent after approval.")])],
             workflow: "Morning digest", askedAt: Date().addingTimeInterval(-25),
             sessionId: "automation:auto-morning", automationId: "auto-morning"),
        // An automation's run reading a page: its own tools ask first for it (watch world only).
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

    /// Each world's conversations, made once (their times are relative to the first read).
    static let watchRuns = sampleRuns(answer: World.watch.cannedAnswer, olderQC: true)
    static let phoneRuns = sampleRuns(answer: World.phone.cannedAnswer, olderQC: false)
    /// The conversations' turns; `answer` is the ADTTE turn's (each world's `cannedAnswer`).
    static func sampleRuns(answer: String, olderQC: Bool) -> [RunSummary] {
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
            r("r1a9e0b2", "analytics-assistant", "completed", session: "s-adtte", minutesAgo: 9, tools: 4, llm: 3, output: answer),
            r("3e9a10c4", "deep-research", "completed", session: "s-qc", minutesAgo: 12, tools: 9, llm: 6, subtitle: "done · 12 min ago",
              output: "The nightly assay QC passed: all 96 wells within range, CV 3.1 %."),
        ] + (olderQC ? (1...7).map { n in
            r("qc-older-\(n)", "deep-research", "completed", session: "s-qc", minutesAgo: 12 + Double(n) * 1440, tools: 2, llm: 1,
              output: "Night \(n): the assay QC passed, CV \(2 + n % 3).\(n) %.")
        } : []) + [
            r("d0c5a971", "docs-qa", "failed", session: "s-docs", minutesAgo: 95, tools: 1, llm: 1, error: "model timeout", subtitle: "failed · model timeout"),
        ]
    }

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
        // Same name, same task: two automations told apart by their results (watch world only).
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
    /// The task the morning digest's trigger sends.
    public static let morningTask = "Summarise what changed overnight: QC runs, new papers on my target, dependency updates."

    public static var mediaRun: RunSummary {
        RunSummary(runId: "media-demo", workflowId: "abstractassistant-orchestrator", status: "completed", sessionId: "media-history",
            output: .object(["response": .string("A quiet horizon, with a voice to match."), "image_artifact": .object(["$artifact": .string("demo-image"), "run_id": .string("media-demo"), "content_type": .string("image/png"), "filename": .string("Quiet horizon.png")]),
                "audio_artifact": .object(["$artifact": .string("demo-voice"), "run_id": .string("media-demo"), "content_type": .string("audio/wav"), "filename": .string("A moment of calm.wav")])]))
    }
    public static var historyRuns: [RunSummary] {
        (1...3).reversed().map { index in
            RunSummary(runId: "history-" + String(index), workflowId: "basic-agent", status: "completed", sessionId: "restored-history",
                createdAt: "2026-10-18T06:0" + String(index) + ":00Z", output: .object(["response": .string("Restored reply " + String(index) + ": your conversation is here.")]))
        }
    }

    private var pending: [Wait]
    private var started: [String: (Date, String)] = [:]
    private var cancelledRunIDs: Set<String> = []
    private let wordInterval: TimeInterval

    /// How long the automations take to answer (a public gateway's is the slow call, ~7 s), and how
    /// many of the first calls fail (a request that times out over a watch's radio).
    private let automationsDelay: Duration
    private var automationsFailures: Int
    /// How long an automation's definition takes to read (a public gateway's take seconds).
    private let definitionDelay: Duration
    /// How long a Run now takes to be accepted (a command over a watch's radio takes seconds).
    private let runDelay: Duration
    /// How many polls fail before the gateway answers (a watch whose radio is still coming up);
    /// `.max`: it never does.
    private var pollFailures: Int
    // The iPhone's fixtures (its screenshots and tests).
    private let emptyAutomations: Bool
    private nonisolated let speechPreparationDelay: TimeInterval
    private let mediaImage: Data?
    private let mediaVoice: Data?
    private let historyFixture: Bool
    private let conversationListFixture: Bool
    private let categoryFixture: Bool
    private let emailFixture: Bool
    private let accessFixture: Bool
    private let activityScenario: String?
    private var activityResolved = false

    public init(world: World, waits: [Wait]? = nil, wordInterval: TimeInterval = 0.12, automationsDelay: Duration = .zero,
                automationsFailures: Int = 0, pollFailures: Int = 0, definitionDelay: Duration = .zero, runDelay: Duration = .zero,
                emptyAutomations: Bool = false, activityScenario: String? = nil, historyFixture: Bool = false, conversationListFixture: Bool = false,
                categoryFixture: Bool = false, emailFixture: Bool = false, accessFixture: Bool = false, mediaImage: Data? = nil, mediaVoice: Data? = nil,
                speechPreparationDelay: TimeInterval = 0) {
        self.world = world
        self.pending = waits ?? world.sampleWaits; self.wordInterval = wordInterval; self.automationsDelay = automationsDelay
        self.automationsFailures = automationsFailures; self.pollFailures = pollFailures; self.definitionDelay = definitionDelay
        self.runDelay = runDelay
        self.emptyAutomations = emptyAutomations; self.activityScenario = activityScenario
        self.historyFixture = historyFixture; self.conversationListFixture = conversationListFixture; self.categoryFixture = categoryFixture
        self.emailFixture = emailFixture; self.accessFixture = accessFixture
        self.mediaImage = mediaImage; self.mediaVoice = mediaVoice; self.speechPreparationDelay = speechPreparationDelay
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

    // MARK: Conversations

    /// Archived conversations (`POST /sessions/{id}/archive`): out of the listing, nothing deleted.
    private var archived: Set<String> = []
    private var historySource: [RunSummary] {
        if mediaImage != nil { return [Self.mediaRun] }
        if historyFixture { return Self.historyRuns.map { var row = $0; row.output = nil; return row } }
        if conversationListFixture {
            return world.sampleRuns.map { original in
                var row = original
                if row.runId == "d0c5a971" { row.updatedAt = ISO8601DateFormatter().string(from: Calendar.current.date(byAdding: .day, value: -1, to: Date())!) }
                if row.runId == "3e9a10c4" { row.updatedAt = ISO8601DateFormatter().string(from: Date().addingTimeInterval(-4 * 86400)) }
                if row.status == "waiting" { row.waiting = try? JSONDecoder().decode(RunWaiting.self, from: Data(#"{"reason":"user","wait_key":"tool_approval:1"}"#.utf8)) }
                return row
            }
        }
        return world.sampleRuns
    }
    public func recentRuns(limit: Int) async throws -> [RunSummary] {
        Array(historySource.filter { !archived.contains($0.sessionId ?? $0.runId) }.prefix(limit))
    }
    public func setArchived(sessionId: String, _ on: Bool) async throws {
        if world == .watch { try await Task.sleep(for: .milliseconds(300)) }
        if on { archived.insert(sessionId) } else { archived.remove(sessionId) }
    }
    public func archivedRuns(limit: Int) async throws -> [RunSummary] {
        Array(historySource.filter { archived.contains($0.sessionId ?? $0.runId) }.prefix(limit))
    }
    /// Words found in the sample conversations' questions and answers (every word, any case).
    public func searchSessions(_ query: String, limit: Int) async throws -> SessionSearchPage {
        try await Task.sleep(for: .milliseconds(400))
        let words = query.lowercased().split(whereSeparator: { !$0.isLetter && !$0.isNumber }).map(String.init)
        var hits: [String: SessionHit] = [:]
        for r in world.sampleRuns where !archived.contains(r.sessionId ?? "") {
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

    public func prompt(ofRun id: String) async throws -> String? {
        if id.hasPrefix("qc-older-") { return "Did the assay QC pass, \(id.dropFirst(9)) nights ago?" }
        if id == "media-demo", mediaImage != nil { return "Imagine a quiet horizon, and give it a voice." }
        if historyFixture { return "Earlier question " + id.replacingOccurrences(of: "history-", with: "") }
        let watch = world == .watch
        return ["94a436e1": "Clean the build folder and rebuild the app",
                "7c1e02aa": watch ? "Now split it by age group" : "What could I move out of the way?",
                "r1a9e0b2": watch ? "Compare overall survival by treatment arm in the ADTTE I sent you" : "Help me make room for focused work this week",
                "3e9a10c4": "Did the nightly assay QC pass?", "d0c5a971": "Summarise the open issues in the docs"][id]
    }

    public func sessionHistory(latestRun runId: String, limit: Int) async throws -> [SessionTurn] {
        guard let session = world.sampleRuns.first(where: { $0.runId == runId })?.sessionId else { return [] }
        var out: [SessionTurn] = []
        for r in world.sampleRuns where r.sessionId == session {
            out.append(SessionTurn(runId: r.runId, createdAt: r.createdAt, prompt: try await prompt(ofRun: r.runId),
                                   answer: r.outputText, status: r.status))
        }
        return Array(out.sorted { ($0.createdAt ?? "") < ($1.createdAt ?? "") }.suffix(limit))
    }

    public func turns(ofSession id: String, limit: Int) async throws -> [RunSummary] {
        world.sampleRuns.filter { ($0.sessionId ?? $0.runId) == id }
    }

    public func turns(ofSession id: String) async throws -> [RunSummary] {
        if mediaImage != nil, id == "media-history" { return [Self.mediaRun] }
        if historyFixture { return Self.historyRuns.filter { ($0.sessionId ?? $0.runId) == id } }
        return world.sampleRuns.filter { ($0.sessionId ?? $0.runId) == id }
    }

    public func messageStats(runID: String) async throws -> MessageStats? {
        .init(wallTimeSeconds: 4.8, inputTokens: 1234, outputTokens: 245, toolCalls: 2)
    }

    // MARK: Automations

    private var createdAutomations: [AutomationSummary] = []
    private var definitions: [String: AutomationDefinition] = [:]
    /// Pause / resume / archive, as the gateway applies them (the sample automations' state).
    private var statuses: [String: String] = [:]
    private var archivedAutomationIds: Set<String> = []
    public func automations() async throws -> [AutomationSummary] {
        if automationsDelay > .zero { try await Task.sleep(for: automationsDelay) }
        if automationsFailures > 0 { automationsFailures -= 1; throw URLError(.timedOut) }
        var out: [AutomationSummary] = []
        for a in (emptyAutomations ? [] : world.sampleAutomations) + createdAutomations where !archivedAutomationIds.contains(a.id) {
            out.append(try await automation(id: a.id))
        }
        return out.filter { $0.status != "archived" }
    }
    /// Run now: the automation runs for 14 s (`current_occurrence` set, a ledger that moves on).
    private var automationRunStarted: [String: Date] = [:]
    public func runAutomationNow(id: String) async throws {
        if runDelay > .zero { try await Task.sleep(for: runDelay) }
        guard world == .watch else { automationRunStarted[id] = Date(); return }
        // As the gateway: one run at a time.
        if let t = automationRunStarted[id], Date().timeIntervalSince(t) < 14 {
            throw GatewayError.http(status: 409, body: #"{"reason_code":"automation_busy"}"#)
        }
        automationRunStarted[id] = Date()
        // Its run: working for 10 s, then its answer (as the occurrence it is).
        started["occ-live"] = (Date().addingTimeInterval(10), "Digest 42: the assay QC run passed; nothing new to pin.")
    }
    public func discussAutomation(id: String, occurrenceIndex: Int, prompt: String) async throws -> Discussion {
        // As the gateway: only a run that happened can be talked about.
        guard let last = Self.sampleAutomations.first(where: { $0.id == id })?.lastOccurrence?.index, occurrenceIndex <= last
        else { throw GatewayError.http(status: 404, body: "occurrence_not_found") }
        let run = "mock-" + UUID().uuidString.prefix(6).lowercased()
        started[run] = (Date(), "About that run: the QC passed on every plate; the two papers are linked in the digest.")
        return Discussion(sessionId: "discussion-session:" + run, runId: run)
    }
    public func automation(id: String) async throws -> AutomationSummary {
        guard var a = (world.sampleAutomations + createdAutomations).first(where: { $0.id == id }) else { throw GatewayError.http(status: 404, body: "") }
        if let t = revisedTitle[id] { a.name = t }
        if let n = revisions[id] { a.revision = (a.revision ?? 1) + n }
        if let t = automationRunStarted[id], Date().timeIntervalSince(t) < 14 {
            a.currentOccurrence = CurrentOccurrence(index: (a.lastOccurrence?.index ?? 0) + 1, runId: "occ-live", attempt: 1, status: "running")
        } else { automationRunStarted[id] = nil }
        if let status = statuses[id] { a.status = status }
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
    public func automationCommand(id: String, type: String) async throws {
        guard world == .watch else {
            statuses[id] = type == "automation.archive" ? "archived" : (type == "automation.pause" || type == "automation.unarchive") ? "paused" : "active"
            return
        }
        try await Task.sleep(for: .milliseconds(300))
        switch type {
        case "automation.pause": statuses[id] = "paused"
        case "automation.resume": statuses[id] = "active"
        case "automation.archive": archivedAutomationIds.insert(id)
        case "automation.unarchive": archivedAutomationIds.remove(id)
        default: break
        }
    }
    public func automationDefaults() async throws -> AutomationDefaults { AutomationDefaults(growingMaxTokens: 50_000) }
    public func archivedAutomations() async throws -> [AutomationSummary] {
        var out: [AutomationSummary] = []
        for a in world.sampleAutomations + createdAutomations where archivedAutomationIds.contains(a.id) || statuses[a.id] == "archived" {
            out.append(try await automation(id: a.id))
        }
        return out
    }
    /// A revision's new title and task, kept (the list, the page and the next edit show them).
    private var revisedTitle: [String: String] = [:]
    private var revisedTask: [String: String] = [:]
    private var revisions: [String: Int] = [:]
    public func reviseAutomation(id: String, changes: [String: JSONValue], expectedRevision: Int?) async throws {
        guard world == .watch else {
            let old = try await automationDefinition(id: id)
            guard expectedRevision == old.revision else { throw GatewayError.http(status: 409, body: "Revision changed") }
            definitions[id] = AutomationDefinition(revision: (old.revision ?? 0) + 1, title: old.title,
                target: changes["target"]?.objectValue ?? old.target, policy: changes["policy"]?.objectValue ?? old.policy)
            return
        }
        if let t = changes["title"]?.stringValue { revisedTitle[id] = t }
        if let p = changes["target"]?["input_data"]?["prompt"]?.stringValue { revisedTask[id] = p }
        revisions[id, default: 0] += 1
    }
    public func workflows(forInterface interface: String) async throws -> [WorkflowChoice] {
        if world == .phone {
            return [WorkflowChoice(bundleId: "basic-agent", bundleVersion: "0.0.5", flowId: "81795ea9", name: "Basic agent"),
                    WorkflowChoice(bundleId: "deep-research", bundleVersion: "0.1.8", flowId: "deep-research", name: "Deep research"),
                    WorkflowChoice(bundleId: "memact-agent", bundleVersion: "0.1.0", flowId: "memact", name: "MemAct agent")]
                + (interface.isEmpty ? [WorkflowChoice(bundleId: "csv-report", bundleVersion: "1.2.3", flowId: "build-report", name: "CSV report")] : [])
        }
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
    public func workflowInputs(_ w: WorkflowChoice) async throws -> WorkflowInputs {
        if w.bundleId == "csv-report" {
            return WorkflowInputs.parse(.object(["inputs": .array([
                .object(["id": .string("source_url"), "label": .string("Source URL"), "type": .string("string"), "required": .bool(true)]),
                .object(["id": .string("row_limit"), "label": .string("Row limit"), "type": .string("integer"), "required": .bool(true), "default": .number(25)]),
                .object(["id": .string("include_header"), "label": .string("Include header"), "type": .string("boolean"), "default": .bool(true)])
            ])]))!
        }
        return WorkflowInputs(defaults: ["use_context": .bool(false)], required: w.bundleId == "memact-agent" ? ["prompt"] : [])
    }
    public func createAutomation(_ a: NewAutomation) async throws -> AutomationSummary {
        try await Task.sleep(for: .milliseconds(600))
        let row = AutomationSummary(id: "auto-" + a.requestId.prefix(6), name: a.title, status: "active", scheduleText: nil, lastOccurrence: nil,
                                    triggerSource: "schedule", triggerConfig: { switch a.when {
                                        case .every(let e): ["kind": .string("every"), "every": .string(e)]
                                        case .daily(let at): ["kind": .string("daily"), "at": .string(at)] } }(), revision: 1)
        // The iPhone's list and editor show what it created.
        if world == .phone, !createdAutomations.contains(where: { $0.id == row.id }) {
            createdAutomations.append(row)
            definitions[row.id] = AutomationDefinition(revision: 1, title: a.title, target: a.body["target"]?.objectValue, policy: a.body["policy"]?.objectValue)
        }
        return row
    }
    public func automationDefinition(id: String) async throws -> AutomationDefinition {
        if definitionDelay > .zero { try await Task.sleep(for: definitionDelay) }
        if let definition = definitions[id] { return definition }
        guard world == .watch else {
            return AutomationDefinition(revision: 2, title: Self.sampleAutomations.first { $0.id == id }?.name, target: [
                "bundle_ref": .string("basic-agent@0.0.5"), "flow_id": .string("81795ea9"),
                "input_data": .object(["prompt": .string("Summarise the overnight assay QC runs, new papers on my target, and dependency updates to pin."),
                                       "tools": .array([.string("web_search")])]),
            ])
        }
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
    public func occurrences(automationId: String, limit: Int) async throws -> [LastOccurrence] {
        guard let last = world.sampleAutomations.first(where: { $0.id == automationId })?.lastOccurrence else { return [] }
        guard let top = last.index, top > 1 else { return [last] }
        if limit > 1 { try await Task.sleep(for: .seconds(3)) }   // like a public gateway: full answers take seconds
        // Earlier runs, a day apart; one failed.
        let older = (max(1, top - min(limit, 12) + 1)..<top).reversed().map { i -> LastOccurrence in
            let day = Date(timeIntervalSince1970: 1_792_213_440 - Double(top - i) * 86_400)
            let failed = i == top - 2
            if world == .phone {
                return LastOccurrence(status: failed ? "failed" : "completed", excerpt: nil, runId: "occ-\(i)", index: i,
                                      firedAt: ISO8601DateFormatter().string(from: day), finishedAt: ISO8601DateFormatter().string(from: day.addingTimeInterval(90)),
                                      answer: failed ? "" : "Digest \(i): the assay QC run passed; nothing new to pin.",
                                      failure: failed ? .init(reasonCode: "occurrence_failed", message: "OpenAI-compatible server API error (401): Missing or invalid AIRelays bearer token.", attempts: 3) : nil,
                                      attempts: failed ? 3 : 1, userTurn: "Check my emails for important updates.")
            }
            return LastOccurrence(status: failed ? "failed" : "completed", excerpt: nil, runId: "occ-\(i)", index: i,
                                  firedAt: ISO8601DateFormatter().string(from: day),
                                  answer: failed ? "The run stopped: the model was not reachable." : "Digest \(i): the assay QC run passed; nothing new to pin.",
                                  userTurn: Self.morningTask)
        }
        return [last] + older
    }
    public func markSeen(automationId: String, cursor: String) async throws {}

    // MARK: Media and files

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
        var out = Self.sampleMedia.filter { id, _ in world.sampleRuns.contains { $0.runId == id && $0.sessionId == sessionId } }
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

    // The iPhone's files: what the person attached, a conversation's artifacts and its folder.
    private var uploaded: [String: [(PhoneArtifact, Data)]] = [:]
    public func upload(data: Data, filename: String, contentType: String, sessionId: String) async throws -> PhoneArtifact {
        let artifact = PhoneArtifact(artifactId: UUID().uuidString, runId: "session_memory_" + sessionId, filename: filename, contentType: contentType, size: data.count)
        uploaded[sessionId, default: []].append((artifact, data)); return artifact
    }
    public func artifacts(sessionId: String) async throws -> [PhoneArtifact] {
        if mediaImage != nil {
            var playback = PhoneArtifact(artifactId: "demo-playback", runId: "media-demo", filename: "Read-aloud recording.wav", contentType: "audio/wav", size: 100)
            playback.purpose = "voice_playback"; playback.isConversationVoice = true
            return Self.mediaRun.mediaArtifacts + [playback]
        }
        let sample = PhoneArtifact(artifactId: "demo-report", runId: "demo-run", filename: "A little focus.txt", contentType: "text/plain", size: world.cannedAnswer.utf8.count)
        return [sample] + (uploaded[sessionId] ?? []).map { $0.0 }
    }
    public func workspace(runID: String) async throws -> RunWorkspace { .init(runID: runID, root: "/demo/session", kind: "session") }
    public func workspaceFiles(runID: String, path: String, recursive: Bool, limit: Int?) async throws -> WorkspaceListing {
        let entries: [WorkspaceEntry] = [
            .init(name: "discussion-summary.md", path: "discussion-summary.md", size: 180),
            .init(name: "Research", path: "Research", type: "dir"),
            .init(name: "notes.md", path: "Research/notes.md", size: 64)]
        return .init(path: path, entries: entries.filter { recursive || ($0.path as NSString).deletingLastPathComponent == path })
    }
    public func downloadWorkspaceFile(runID: String, entry: WorkspaceEntry, to destination: URL) async throws {
        let text = entry.path == "discussion-summary.md" ? "# Discussion summary\n\nWe explored the environment and saved a useful summary.\n\n## Next steps\n\n- Review the findings.\n- Keep the conversation going." : "# Research notes\n\nA note in a nested folder."
        try Data(text.utf8).write(to: destination, options: .withoutOverwriting)
    }
    public func download(_ artifact: PhoneArtifact) async throws -> Data {
        if artifact.artifactId == "demo-image", let mediaImage { return mediaImage }
        if ["demo-voice", "demo-playback"].contains(artifact.artifactId), let mediaVoice { return mediaVoice }
        if artifact.artifactId == "demo-report" { return Data(world.cannedAnswer.utf8) }
        for rows in uploaded.values { if let row = rows.first(where: { $0.0.id == artifact.id }) { return row.1 } }
        throw GatewayError.invalidResponse
    }

    // MARK: Entities

    private var createdEntities: [EntitySummary] = []
    public func entities() async throws -> [EntitySummary] { Self.sampleEntities + createdEntities }
    public func validateEntity(_ draft: EntityDraft) async throws -> EntityValidation {
        EntityValidation(ok: draft.valid, exists: (Self.sampleEntities + createdEntities).contains { $0.name == draft.slug }, slug: draft.slug)
    }
    public func createEntity(_ draft: EntityDraft) async throws -> CreatedEntity {
        guard draft.valid else { throw GatewayError.invalidResponse }
        let exists = (Self.sampleEntities + createdEntities).contains { $0.name == draft.slug }
        if !exists { createdEntities.append(EntitySummary(name: draft.slug, extra: ["display_name": .string(draft.name)])) }
        return try CreatedEntity(.object(["created": .bool(!exists), "manifest": .object(["slug": .string(draft.slug), "name": .string(draft.name)]), "warnings": .array([])]))
    }
    public func openEntityChat(name: String) async throws -> String { "chat-" + name }
    public func entityChatTurn(name: String, chatId: String, text: String) async throws -> String {
        try await Task.sleep(for: .seconds(1.6))
        return Self.cannedEntityReply
    }

    // MARK: A run's steps

    public static let sampleLedger: [LedgerRecord] = [
        LedgerRecord(nodeId: "plan", status: "completed", effect: .object(["type": .string("llm_call")]), result: .object(["output": .object(["response": .string("plan: KM + Cox by TRT01P")])])),
        LedgerRecord(nodeId: "write_code", status: "completed", effect: .object(["type": .string("llm_call")]), result: .object(["mode": .string("code v1")])),
        LedgerRecord(nodeId: "run", status: "failed", effect: .object(["type": .string("tool_calls")]), error: "KeyError 'ARM'"),
        LedgerRecord(nodeId: "write_code", status: "completed", effect: .object(["type": .string("llm_call")]), result: .object(["mode": .string("code v2 · traceback in context")])),
        LedgerRecord(nodeId: "run", status: "completed", effect: .object(["type": .string("tool_calls")]), result: .object(["tool_calls": .array([.object(["name": .string("python analysis/run.py")])])])),
        LedgerRecord(nodeId: "review", status: "started", effect: .object(["type": .string("llm_call")])),
    ]
    public func ledger(runId: String, after: Int) async throws -> LedgerPage {
        if activityScenario == "cycle-detail", runId == "media-demo" {
            func model(_ id: String, _ second: String, _ content: String) -> LedgerRecord {
                .init(stepId: id, nodeId: "reason", status: "completed", effect: .object(["type": .string("llm_call")]), result: .object(["content": .string(content), "model": .string("assistant-model")]), startedAt: "2026-10-18T17:20:" + second + "Z", endedAt: "2026-10-18T17:20:" + second + ".800Z")
            }
            let read: JSONValue = .object(["name": .string("read_file"), "runtime_call_id": .string("read-notes"), "arguments": .object(["file_path": .string("notes.md"), "apiKey": .string("fixture-private-key")])])
            let write: JSONValue = .object(["name": .string("write_file"), "runtime_call_id": .string("write-summary"), "arguments": .object(["file_path": .string("summary.md"), "content": .string("# Summary\nA clear plan for tomorrow.")])])
            func tool(_ id: String, _ call: JSONValue, _ output: String) -> LedgerRecord {
                .init(stepId: id, nodeId: "act", status: "completed", effect: .object(["type": .string("tool_calls"), "payload": .object(["tool_calls": .array([call])])]), result: .object(["results": .array([.object(["runtime_call_id": call["runtime_call_id"]!, "success": .bool(true), "output": .string(output)])])]), startedAt: id == "write" ? "2026-10-18T17:20:04Z" : "2026-10-18T17:20:02Z", endedAt: id == "write" ? "2026-10-18T17:20:05Z" : "2026-10-18T17:20:02.800Z")
            }
            let rows = [model("cycle-1", "00", "I’ll read the notes and save a short summary."), tool("read", read, "These notes describe the next design review."),
                LedgerRecord(stepId: "approval", nodeId: "act", status: "waiting", result: .object(["wait": .object(["reason": .string("user"), "wait_key": .string("tool_approval:summary"), "prompt": .string("Save summary.md?")])]), startedAt: "2026-10-18T17:20:03Z", endedAt: "2026-10-18T17:20:03Z"),
                tool("write", write, "Successfully written summary.md (45 bytes)."),
                LedgerRecord(stepId: "fetch", nodeId: "act", status: "completed", effect: .object(["type": .string("tool_calls"), "payload": .object(["tool_calls": .array([.object(["name": .string("fetch_url"), "runtime_call_id": .string("fetch-timeout"), "arguments": .object(["url": .string("https://example.com/notes")])])])])]), result: .object(["results": .array([.object(["runtime_call_id": .string("fetch-timeout"), "success": .bool(false), "error": .string("The server timed out.")])])]), startedAt: "2026-10-18T17:20:05Z", endedAt: "2026-10-18T17:20:05.8Z"), model("cycle-2", "06", "The summary is saved and ready to review.")]
            return LedgerPage(items: Array(rows.dropFirst(after)), nextAfter: rows.count)
        }
        if activityScenario == "empty-history", runId == "media-demo" { return LedgerPage(items: [], nextAfter: 0) }
        if activityScenario == "timed-history", runId == "media-demo" {
            let rows: [LedgerRecord] = [
                .init(stepId: "route", nodeId: "route_call", status: "completed", effect: .object(["type": .string("llm_call")]),
                    result: .object(["data": .object(["mode": .string("image"), "assistant_message": .string("Here is your landscape."), "media_prompt": .string("An indigo landscape with a coral sun")]), "model": .string("router-model"), "route": .object(["provider": .string("gateway")]), "usage": .object(["input_tokens": .number(428), "output_tokens": .number(41)]), "finish_reason": .string("stop")]), startedAt: "2026-10-18T17:24:54Z", endedAt: "2026-10-18T17:24:56.4Z"),
                .init(stepId: "image", nodeId: "generate_image", status: "completed", effect: .object(["type": .string("llm_call"), "payload": .object(["output": .object(["modality": .string("image"), "task": .string("text_to_image")])])]),
                    result: Self.mediaRun.output, startedAt: "2026-10-18T17:24:56.5Z", endedAt: "2026-10-18T17:25:14Z")
            ]
            return LedgerPage(items: Array(rows.dropFirst(after)), nextAfter: rows.count)
        }
        if emailFixture || accessFixture, runId == "media-demo" {
            let mail = emailFixture ? Self.emailRecords.filter { row in
                let reading = row.effect?["payload"]?["tool_calls"].flatMap { if case .array(let calls) = $0 { calls.first?["name"]?.stringValue == "read_email" } else { false } } ?? false
                return activityScenario == "mail-sent" ? !reading : activityScenario == "mail-read" ? reading : true
            } : []
            let rows = mail + (accessFixture ? Self.accessRecords : [])
            return LedgerPage(items: Array(rows.dropFirst(after).prefix(200)), nextAfter: min(rows.count, after + 200))
        }
        if activityScenario != nil && runId.hasPrefix("activity-") {
            if activityScenario == "offline" { throw GatewayError.http(status: 503, body: "Gateway unavailable") }
            let all = runId == "activity-root" ? [] : activityRecords()
            return LedgerPage(items: Array(all.dropFirst(after).prefix(200)), nextAfter: min(all.count, after + 200))
        }
        if runId == "occ-live" { let all = liveLedger(); return LedgerPage(items: Array(all.dropFirst(min(after, all.count))), nextAfter: all.count) }
        return LedgerPage(items: Array(Self.sampleLedger.dropFirst(min(after, Self.sampleLedger.count))), nextAfter: Self.sampleLedger.count)
    }
    public func cancel(runId: String) async throws {
        started[runId] = nil; scripted[runId] = nil
        // The iPhone's: a cancelled run reads back as cancelled, its waits gone.
        if world == .phone { cancelledRunIDs.insert(runId); pending.removeAll { $0.runId == runId } }
    }

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

    // MARK: The person's events

    /// The person's event stream (canned: empty unless a test appends to it).
    public private(set) var userEvents: [UserEvent] = []
    public func appendEvent(_ e: UserEvent) { userEvents.append(e) }
    /// How many times the live tail was opened, and with which Last-Event-ID.
    public private(set) var streamOpens: [Int] = []
    func noteStreamOpen(_ id: Int) { streamOpens.append(id) }

    /// The names the mock's triggers are said with.
    public var names = TriggerNames()
    public func setNames(_ value: TriggerNames) { names = value }
    public func triggerNames(connections: Bool, mailboxes: Bool) async throws -> TriggerNames { names }

    /// What the app reported as shown (`POST /me/events/notifications`).
    public private(set) var reports: [NotificationReport] = []
    public func reportNotification(_ report: NotificationReport) async throws { reports.append(report) }

    /// A gateway without the stream (404 on both routes).
    public private(set) var eventsUnsupported = false
    public func setEventsUnsupported(_ value: Bool) { eventsUnsupported = value }

    public func events(after: Int, limit: Int) async throws -> UserEventsPage {
        if eventsUnsupported { throw GatewayError.http(status: 404, body: "") }
        let rest = userEvents.filter { $0.sequence > after }
        let page = Array(rest.prefix(limit))
        return UserEventsPage(stream: "user:default:mock", events: page, nextAfter: page.last?.sequence ?? after,
                              head: userEvents.last?.sequence ?? 0, more: rest.count > limit)
    }

    /// The tail: what is there after `lastEventID`, then whatever is appended within ~1 s; then it closes
    /// (the caller reconnects from its cursor, as with a real server closing the stream).
    public nonisolated func userEventStream(lastEventID: Int) -> AsyncThrowingStream<UserEvent, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                await self.noteStreamOpen(lastEventID)
                var cursor = lastEventID
                for _ in 0..<20 {
                    for e in await self.userEvents where e.sequence > cursor { continuation.yield(e); cursor = e.sequence }
                    try? await Task.sleep(for: .milliseconds(50))
                    if Task.isCancelled { break }
                }
                continuation.finish()
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    public func emailStatus() async throws -> EmailStatus {
        EmailStatus(configured: false, address: nil, agentToolsOn: false, reason: "Connect a mailbox first.")
    }

    // MARK: Voice

    public func voiceCatalog() async throws -> VoiceCatalog {
        guard world == .watch else {
            return VoiceCatalog(entries: libraryVoices(),
                                transcription: [TranscriptionChoice(provider: "faster-whisper", model: "base"), TranscriptionChoice(provider: "faster-whisper", model: "large-v3-turbo")],
                                defaultVoice: "Supertonic · F2", defaultTranscription: "faster-whisper · base", defaultVoiceProvider: "supertonic")
        }
        try await Task.sleep(for: .seconds(4))   // like a slow gateway over a watch's radio
        return VoiceCatalog(entries: libraryVoices(),
                     transcription: ["tiny", "base", "small", "large-v3"].map { TranscriptionChoice(provider: "faster-whisper", model: $0) },
                     defaultVoice: "supertonic-3", defaultTranscription: "faster-whisper base", defaultVoiceProvider: "supertonic")
    }

    // MARK: Voice library (sample: the engine's voices, one of the person's own, two shared)

    private var ownVoices: [VoiceEntry]? = nil
    private var voiceSerial = 0

    private func libraryVoices() -> [VoiceEntry] {
        if ownVoices == nil {
            ownVoices = [VoiceEntry(choice: VoiceChoice(provider: "qwen3-tts", model: "Qwen3-TTS-12Hz-1.7B-Base", voice: "my-narrator", label: "My narrator"),
                                    group: .yours, language: "en", summary: "Calm, warm and slow: for long answers.")]
        }
        let engine: [VoiceEntry] = world == .watch
            ? ["M1", "M2", "F1", "F2"].map { VoiceEntry(choice: VoiceChoice(provider: "supertonic", model: "supertonic-3", voice: $0, label: "Supertonic \($0)",
                                                                          gender: $0.hasPrefix("F") ? "female" : "male"), group: .engine, language: "en") }
            : [VoiceEntry(choice: VoiceChoice(provider: "supertonic", model: "supertonic-3", voice: "F2", label: "Supertonic · F2"), group: .engine, language: "en"),
               VoiceEntry(choice: VoiceChoice(provider: "supertonic", model: "supertonic-3", voice: "M1", label: "Supertonic · M1"), group: .engine, language: "en")]
        let shared = [
            VoiceEntry(choice: VoiceChoice(provider: "qwen3-tts", model: "Qwen3-TTS-12Hz-1.7B-Base", voice: "fr-female-camille", label: "Camille", gender: "female"),
                       group: .shared, language: "fr", summary: "A bright adult female voice, Parisian French."),
            VoiceEntry(choice: VoiceChoice(provider: "qwen3-tts", model: "Qwen3-TTS-12Hz-1.7B-Base", voice: "de-male-jonas", label: "Jonas", gender: "male"),
                       group: .shared, language: "de", summary: "A low, steady adult male voice."),
        ]
        return (ownVoices ?? []) + engine + shared
    }

    private static func refusal(_ status: Int, _ sentence: String) -> GatewayError {
        .http(status: status, body: "{\"detail\":\"\(sentence)\"}")
    }

    public func designVoice(description: String, name: String?, language: String?) async throws -> CreatedVoice {
        try await Task.sleep(for: .seconds(3))   // a design takes a while on a real gateway (a minute on first use)
        voiceSerial += 1
        let created = CreatedVoice(voiceID: "designed-\(voiceSerial)", name: name ?? "Designed voice", engine: "qwen3-tts", language: language)
        ownVoices = (ownVoices ?? []) + [VoiceEntry(choice: VoiceChoice(provider: "qwen3-tts", model: "Qwen3-TTS-12Hz-1.7B-Base", voice: created.voiceID, label: created.name ?? created.voiceID),
                                                    group: .yours, language: language, summary: description)]
        return created
    }

    public func cloneVoice(_ upload: VoiceCloneUpload) async throws -> CreatedVoice {
        guard !upload.audio.isEmpty else { throw Self.refusal(422, "The reference recording is empty.") }
        try await Task.sleep(for: .milliseconds(800))
        voiceSerial += 1
        let engine = upload.provider ?? "omnivoice"
        let created = CreatedVoice(voiceID: "cloned-\(voiceSerial)", name: upload.name ?? "My voice", engine: engine, language: upload.language ?? "en")
        ownVoices = (ownVoices ?? []) + [VoiceEntry(choice: VoiceChoice(provider: engine, model: "", voice: created.voiceID, label: created.name ?? created.voiceID),
                                                    group: .yours, language: created.language)]
        return created
    }

    public func renameVoice(id: String, name: String) async throws {
        _ = libraryVoices()
        guard let i = ownVoices?.firstIndex(where: { $0.voiceID == id }) else { throw Self.refusal(422, "Built-in and shared voices are read-only.") }
        ownVoices?[i].choice.label = name
    }

    public func deleteVoice(id: String) async throws {
        _ = libraryVoices()
        guard let i = ownVoices?.firstIndex(where: { $0.voiceID == id }) else { throw Self.refusal(422, "Built-in and shared voices are read-only.") }
        ownVoices?.remove(at: i)
    }

    public func transcribe(wav: Data, sessionId: String) async throws -> String { try await transcribe(wav: wav, sessionId: sessionId, model: nil) }
    public func transcribe(wav: Data, sessionId: String, model: TranscriptionChoice?) async throws -> String {
        guard world == .watch else {
            try await Task.sleep(for: .seconds(max(0.9, speechPreparationDelay)))
            return "Help me make room for focused work this week"
        }
        try await Task.sleep(for: .milliseconds(900))
        return "Compare overall survival by treatment arm in the ADTTE I sent you"
    }

    /// Two short synthetic "sentences" (a voiced tone with a syllable envelope), so the read screen and
    /// the orb can be exercised without a gateway.
    public nonisolated func speech(text: String, scope: SpeechScope) -> AsyncThrowingStream<Data, Error> { speech(text: text, scope: scope, voice: nil) }
    public nonisolated func speech(text: String, scope: SpeechScope, voice: VoiceChoice?) -> AsyncThrowingStream<Data, Error> {
        guard world == .watch else {
            let delay = speechPreparationDelay
            return AsyncThrowingStream { continuation in
                let task = Task {
                    do {
                        try await Task.sleep(for: .seconds(max(0.6, delay)))
                        continuation.yield(SyntheticSpeech.wav(seconds: 2.4, seed: 1))
                        if delay > 0 { try await Task.sleep(for: .seconds(2.4 + delay)) }
                        continuation.yield(SyntheticSpeech.wav(seconds: 2.0, seed: 2))
                        continuation.finish()
                    } catch { continuation.finish(throwing: error) }
                }
                continuation.onTermination = { _ in task.cancel() }
            }
        }
        // `--failing-sample`: the voice "M2" fails at the gateway (a voice picker must say why, not fall silent).
        if ProcessInfo.processInfo.arguments.contains("--failing-sample"), voice?.voice == "M2" {
            return AsyncThrowingStream { continuation in
                Task {
                    try? await Task.sleep(for: .milliseconds(400))
                    continuation.finish(throwing: GatewayError.http(status: 502, body: "the qwen3-tts engine is not loaded"))
                }
            }
        }
        return AsyncThrowingStream { continuation in
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
        if wait.runId == "activity-child" { activityResolved = true }
        pending.removeAll { $0.id == wait.id }
    }

    // MARK: Tools and starting a turn

    public func tools() async throws -> [ToolInfo] {
        guard world == .watch else {
            var unavailable = ToolInfo(name: "capture_camera", riskTier: "outreach", riskRank: 3, enabled: false, description: "Capture a photo from the gateway’s camera.", toolset: "camera", approvalDefault: "ask")
            unavailable.whyDisabled = "The gateway camera is not enabled."
            let extras: [ToolInfo] = categoryFixture ? [
                ToolInfo(name: "write_file", riskTier: "act", riskRank: 2, description: "Save a document in your workspace.", toolset: "files", approvalDefault: "ask"),
                ToolInfo(name: "blocked_file", riskTier: nil, riskRank: nil, enabled: false, toolset: "files")
            ] : []
            return extras + [
                unavailable,
                ToolInfo(name: "read_file", riskTier: "observe", riskRank: 1, description: "Read a file in your workspace.", toolset: "files", approvalDefault: "auto"),
                ToolInfo(name: "fetch_url", riskTier: "act", riskRank: 2, description: "Read a web page from a URL.", toolset: "web", approvalDefault: "ask"),
                ToolInfo(name: "send_email", riskTier: "outreach", riskRank: 3, description: "Send an email from your connected account.", toolset: "comms", approvalDefault: "ask"),
                ToolInfo(name: "execute_command", riskTier: "destroy", riskRank: 4, description: "Execute a command in the gateway workspace.", toolset: "system", approvalDefault: "ask")
            ]
        }
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
    /// The tools each of the iPhone's turns was started with (tests read them).
    public private(set) var assistantToolSelections: [ConversationTools?] = []
    private var chosenWorkflow: String?

    /// The watch's turn.
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
            started[id] = (Date(), world.cannedAnswer)
        }
        return id
    }

    /// The iPhone's turn (its activity scenarios start a root run waiting on its agent's child).
    public func startRun(prompt: String, sessionId: String?, toolPolicy: RunToolPolicy?) async throws -> String {
        if activityScenario != nil {
            if activityScenario == "offline" { return "activity-root" }
            let child = try await activityRun("activity-child")
            if let wait = child.personWait { pending = [wait] }
            return "activity-root"
        }
        let id = "mock-" + UUID().uuidString.prefix(6).lowercased()
        started[id] = (Date(), world.cannedAnswer)
        return id
    }
    public func startRun(prompt: String, sessionId: String?, attachments: [JSONValue]) async throws -> String { try await startRun(prompt: prompt, sessionId: sessionId, toolPolicy: nil) }
    public func startRun(prompt: String, sessionId: String?, attachments: [JSONValue], tools: ConversationTools?) async throws -> String {
        assistantToolSelections.append(tools)
        return try await startRun(prompt: prompt, sessionId: sessionId, toolPolicy: tools?.policy)
    }
    public func accountPreferences() async throws -> JSONValue {
        .object(["time_zone": .object(["effective": .string("Europe/Paris")]), "apps": .array([.object([
            "interface": .string(WorkflowChoice.assistantInterface), "value": chosenWorkflow.map(JSONValue.string) ?? .null,
            "gateway_default_label": .string("Gateway default · Basic agent"),
            "effective": .object(["available": .bool(true)]),
            "choices": .array([.object(["value": .string("basic-agent:root"), "name": .string("Basic agent"), "label": .string("Basic agent")]), .object(["value": .string("deep-research:root"), "name": .string("Deep research"), "label": .string("Deep research")])])
        ])])])
    }
    public func setAssistantWorkflow(_ value: String?) async throws -> JSONValue { chosenWorkflow = value; return try await accountPreferences() }

    public func childRuns(ofRunID id: String) async throws -> [RunSummary] {
        if activityScenario != nil && id == "activity-root" { return [try await activityRun("activity-child")] }
        return []
    }
    private func activityRun(_ id: String) async throws -> RunSummary {
        if activityScenario == "offline" { throw GatewayError.http(status: 503, body: "Gateway unavailable") }
        if activityScenario == "failure", id == "activity-root" { return RunSummary(runId: id, workflowId: "assistant", status: "failed", error: "The model connection timed out.") }
        if activityResolved { return RunSummary(runId: id, workflowId: "assistant", status: "completed", output: id == "activity-root" ? .string("The host is Linux on arm64.") : nil, parentRunId: id == "activity-child" ? "activity-root" : nil) }
        if id == "activity-root" {
            return RunSummary(runId: id, workflowId: "assistant", status: "waiting", waiting: RunWaiting(reason: "subworkflow", waitKey: "subworkflow:activity-child"))
        }
        let waiting = activityScenario == "approval" ? RunWaiting(reason: "user", waitKey: "tool_approval:host", prompt: "Inspect the host machine?", details: .object(["mode": .string("approval_required"), "tool_calls": .array([.object(["name": .string("execute_command"), "arguments": .object(["command": .string("uname -srm")])])])])) : nil
        return RunSummary(runId: id, workflowId: "assistant", status: waiting == nil ? "running" : "waiting", waiting: waiting, parentRunId: "activity-root")
    }
    private func activityRecords() -> [LedgerRecord] {
        let clock = ISO8601DateFormatter()
        let start = clock.string(from: Date().addingTimeInterval(-8))
        let now = clock.string(from: Date().addingTimeInterval(-5))
        let model = JSONValue.object(["type": .string("llm_call")])
        let call: JSONValue = .object(["name": .string("read_file"), "runtime_call_id": .string("host-read"), "arguments": .object(["file_path": .string("notes/system.md")])])
        let tool: JSONValue = .object(["type": .string("tool_calls"), "payload": .object(["tool_calls": .array([call])])])
        var rows = [LedgerRecord(stepId: "cycle-1", nodeId: "reason", status: "started", effect: model, startedAt: start),
                    LedgerRecord(stepId: "cycle-1", nodeId: "reason", status: "completed", effect: model,
                        result: .object(["content": .string("I’ll inspect the host’s operating system and architecture."), "model": .string("assistant-model"), "route": .object(["provider": .string("gateway")]), "usage": .object(["input_tokens": .number(1254), "output_tokens": .number(32)]), "finish_reason": .string("tool_calls")]), startedAt: start, endedAt: now),
                    LedgerRecord(stepId: "read", nodeId: "act", status: "completed", effect: tool, result: .object(["results": .array([.object(["runtime_call_id": .string("host-read"), "success": .bool(true), "output": .string("Operating system: Linux. Architecture: arm64.")])])]), endedAt: now)]
        if activityScenario == "approval" {
            let effect: JSONValue = .object(["type": .string("tool_calls"), "payload": .object(["tool_calls": .array([.object(["name": .string("execute_command"), "runtime_call_id": .string("host-command")])])])])
            rows.append(LedgerRecord(stepId: "host", nodeId: "act", status: "waiting", effect: effect, result: .object(["wait": .object(["reason": .string("user"), "wait_key": .string("tool_approval:host"), "prompt": .string("Inspect the host machine?")])]), endedAt: now))
            if activityResolved { rows.append(LedgerRecord(stepId: "host", nodeId: "act", status: "completed", effect: effect, result: .object(["results": .array([.object(["runtime_call_id": .string("host-command"), "success": .bool(true), "output": .string("Linux 6.8 arm64")])])]), endedAt: now)) }
        } else if activityScenario == "failure" {
            rows.append(LedgerRecord(stepId: "cycle-2", nodeId: "reason", status: "failed", effect: model, error: "The model connection timed out.", endedAt: now))
        } else { rows.append(LedgerRecord(stepId: "cycle-2", nodeId: "reason", status: "started", effect: model, startedAt: now)) }
        return rows
    }

    /// A started mock run "streams": each poll reveals the words due by now, then completes.
    public func run(id: String) async throws -> RunSummary {
        if world == .phone {
            if id.hasPrefix("occ-") || id == "b81f3302" {
                return RunSummary(runId: id, workflowId: "@default", status: id == "occ-39" ? "failed" : id == "occ-live" ? "running" : "completed",
                                  error: id == "occ-39" ? "OpenAI-compatible server API error (401): Missing or invalid AIRelays bearer token." : nil)
            }
            if id == "media-demo", mediaImage != nil { return Self.mediaRun }
            if historyFixture, let run = Self.historyRuns.first(where: { $0.runId == id }) { return run }
            if cancelledRunIDs.contains(id) { return RunSummary(runId: id, workflowId: nil, status: "cancelled") }
            if activityScenario != nil && id.hasPrefix("activity-") { return try await activityRun(id) }
        }
        if let s = scripted[id] {
            let now = Self.timeline(s, at: Date())
            if now.done {
                return RunSummary(runId: id, workflowId: "basic-agent@0.0.5:81795ea9", status: "completed", output: .object(["response": .string(Self.researchAnswer)]))
            }
            return RunSummary(runId: id, workflowId: "basic-agent@0.0.5:81795ea9", status: now.waiting == nil ? "running" : "waiting",
                              sessionId: runSession[id], waiting: now.waiting)
        }
        guard let (t0, text) = started[id] else {
            return world.sampleRuns.first { $0.runId == id } ?? RunSummary(runId: id, workflowId: nil, status: "failed", error: "unknown run")
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

public extension MockGatewayClient.World {
    /// The waits on a person (the watch's has one more: an automation's page read).
    var sampleWaits: [Wait] {
        self == .watch ? MockGatewayClient.sampleWaits : MockGatewayClient.sampleWaits.filter { $0.runId != "b81f3302-agent" }
    }
    /// The ADTTE conversation's answer (the watch's screenshots and the iPhone's demo differ).
    var cannedAnswer: String {
        switch self {
        case .watch: "Overall survival favoured arm B: HR 0.78 (95% CI 0.61–0.99), n = 412, 287 events. Proportional hazards held (Schoenfeld p = 0.41)."
        case .phone: "Let’s make a little room.\n\n**Start with one protected hour.** Choose a morning this week, silence notifications, and give that time to the idea you keep postponing.\n\n1. Pick one outcome that would make the week feel worthwhile.\n2. Move one meeting or small task out of the way.\n3. Leave ten minutes afterward to capture what changed.\n\nWhat would you most like that hour to be for?"
        }
    }
    /// The conversations (the watch's QC conversation has seven earlier nights).
    var sampleRuns: [RunSummary] { self == .watch ? MockGatewayClient.watchRuns : MockGatewayClient.phoneRuns }
    /// The automations (the watch's: two more with the same name, the morning digest's task and budget).
    var sampleAutomations: [AutomationSummary] {
        guard self == .phone else { return MockGatewayClient.sampleAutomations }
        return MockGatewayClient.sampleAutomations.prefix(3).map {
            var a = $0; a.growingMaxTokens = nil; a.lastOccurrence?.userTurn = nil; return a
        }
    }
}

extension MockGatewayClient {
    private static var emailRecords: [LedgerRecord] {
        func record(_ id: String, name: String, args: JSONValue, output: JSONValue) -> LedgerRecord {
            let call: JSONValue = .object(["name": .string(name), "runtime_call_id": .string(id), "arguments": args])
            return LedgerRecord(stepId: id, nodeId: "act", status: "completed", effect: .object(["type": .string("tool_calls"), "payload": .object(["tool_calls": .array([call])])]), result: .object(["results": .array([.object(["runtime_call_id": .string(id), "success": .bool(true), "output": output])])]), endedAt: "2026-10-18T16:05:00Z")
        }
        func sent(_ id: String, subject: String, reply: Bool = false, many: Bool = false) -> LedgerRecord {
            let recipients: JSONValue = .array((many ? ["alex@example.com", "sam@example.com", "design-team@example.com"] : ["alex@example.com"]).map(JSONValue.string))
            let args: JSONValue = .object(["to": recipients, "subject": .string(subject), "body_text": .string(reply ? "Thanks, Alex. The summary is ready to review." : "Hi Alex,\n\nHere is a short summary of our discussion.\n\nWe reviewed the workspace, explored the available tools, and saved our next steps.\n\nBest,\nYour assistant")])
            let output: JSONValue = .object(["success": .bool(true), "message_id": .string("<" + id + "@example.com>"), "from": .string("you@example.com"), "to": recipients, "cc": .array([]), "bcc": .array([]), "subject": .string(subject), "accepted": recipients, "refused": .object([:])])
            return record(id, name: reply ? "reply_email" : "send_email", args: args, output: output)
        }
        func read(_ uid: String, subject: String, sender: String, htmlOnly: Bool = false, skipped: Bool = false) -> LedgerRecord {
            var output: [String: JSONValue] = ["success": .bool(true), "uid": .string(uid), "uidvalidity": .number(100), "account": .string("default"), "mailbox": .string("INBOX"), "message_id": .string("<read-" + uid + "@example.com>"), "from": .string(sender), "to": .array([.string("you@example.com")]), "cc": .array([]), "subject": .string(subject), "date": .string("Sun, 18 Oct 2026 14:00:00 +0000"), "body_text": .string(htmlOnly || skipped ? "" : "Hi,\n\nThe project notes are ready. Please review the attached summary before our next meeting.\n\nThank you."), "body_html": .string(htmlOnly ? "<p>The design review is ready.</p>" : ""), "attachments": .array([.object(["filename": .string("project-summary.pdf")])])]
            if skipped { output["body_skipped"] = .object(["cause": .string("Message exceeds the reading limit.")]) }
            return record("read-" + uid, name: "read_email", args: .object(["uid": .string(uid)]), output: .object(output))
        }
        return [sent("email-first", subject: "Our discussion"), sent("email-reply", subject: "Re: Our discussion", reply: true),
            sent("email-team", subject: "Project handoff — a longer subject about the next design review and decisions for the whole team", many: true),
            read("1", subject: "Project notes", sender: "Alex <alex@example.com>"),
            read("2", subject: "Design review — updated images and a longer summary of our decisions", sender: "Sam <sam@example.com>", htmlOnly: true),
            read("3", subject: "Large message", sender: "Team <team@example.com>", skipped: true)]
    }
}

extension MockGatewayClient {
    private static var accessRecords: [LedgerRecord] {
        func row(_ id: String, _ name: String, _ args: [String:JSONValue], _ output: JSONValue) -> LedgerRecord {
            .init(stepId:id,nodeId:"act",status:"completed",effect:.object(["type":.string("tool_calls"),"payload":.object(["tool_calls":.array([.object(["name":.string(name),"runtime_call_id":.string(id),"arguments":.object(args)])])])]),result:.object(["results":.array([.object(["runtime_call_id":.string(id),"success":.bool(true),"output":output])])]),endedAt:"2026-10-18T16:05:00Z")
        }
        return [
            row("read-notes","read_file",["file_path":.string("Research/notes.md")],.string("File: Research/notes.md (2 lines)\n\n1: Research notes\n2: Review the available evidence.")),
            row("skim-notes","skim_files",[:],.string("File: Research/notes.md (2 lines) — skim 1 lines (target 8%)\n\n1: Research notes\n\n---\n\nFile: missing.md\n\nError: File does not exist")),
            row("read-plan","read_file",["file_path":.string("plan.md")],.string("File: plan.md (1 lines)\n\n1: Prepare the project handoff.")),
            row("write-summary","write_file",["file_path":.string("discussion-summary.md")],.string("✅ Successfully written to 'discussion-summary.md' (180 bytes, 8 lines)")),
            row("edit-summary","edit_file",["file_path":.string("discussion-summary.md")],.string("Edited discussion-summary.md (+1 -1)\n-1 | Draft\n+1 | Discussion summary")),
            row("search-full","web_search",[:],.string(#"{"success":true,"query":"Swift UI accessibility","results":[{"title":"Accessibility guide","url":"https://example.com/accessibility","snippet":"Design for accessible interactions."}]}"#)),
            row("search-skim","skim_websearch",[:],.string(#"{"success":true,"query":"Swift file previews","results":[]}"#)),
            row("page-skim","skim_url",["url":.string("https://example.com/accessibility")],.string("🌐 URL Skim\nURL: https://example.com/accessibility\nStatus: 200 OK\nContent-Type: text/html\n📄 Preview:\nAccessible interface guidelines.")),
            row("page-full","fetch_url",["url":.string("https://example.com/previews")],.object(["success":.bool(true),"final_url":.string("https://example.com/guide/previews"),"content":.string("A preview lets people inspect a document without leaving their conversation.")]))
        ]
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
