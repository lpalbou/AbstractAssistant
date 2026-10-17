import Foundation

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
             workflow: "Morning digest", askedAt: Date().addingTimeInterval(-25)),
        Wait(runId: "94a436e1", waitKey: "tool_approval:1", kind: .toolApproval, reason: "user",
             details: [ToolCallDetail(name: "execute_command",
                                      arguments: ["command": .string("rm -rf build/ && make"),
                                                  "cwd": .string("~/projects/assay-pipeline")])],
             workflow: "coding-agent", riskTier: "Destructive", askedAt: Date().addingTimeInterval(-40)),
        Wait(runId: "3e9a10c4", waitKey: "ask_user:1", kind: .askUser, reason: "user",
             prompt: "Two sources disagree on the phase II endpoint. Which one should I treat as primary?",
             choices: ["EMA assessment report (2025)", "Company press release", "Cite both, flag the conflict"],
             allowFreeText: true, workflow: "deep-research", askedAt: Date().addingTimeInterval(-120)),
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
            r("d0c5a971", "docs-qa", "failed", session: "s-docs", minutesAgo: 95, tools: 1, llm: 1, error: "model timeout", subtitle: "failed · model timeout"),
        ]
    }()

    public static let sampleAutomations: [AutomationSummary] = [
        AutomationSummary(id: "auto-morning", name: "Morning digest", status: "active", scheduleText: "every day",
                          lastOccurrence: LastOccurrence(status: "completed", excerpt: "Three things today: the assay QC run passed; two new papers on your target; one dependency to pin.",
                                                         runId: "b81f3302", index: 41, firedAt: "2026-10-17T05:04:00Z", finishedAt: "2026-10-17T05:06:10Z",
                                                         answer: "Three things today: the assay QC run passed; two new papers on your target (one with a phase II readout); the dependency check found one update to pin."),
                          cadence: "daily", detail: "every day · last 07:04 · ok", nextFireAt: "2026-10-18T05:00:00Z",
                          attention: Attention(pendingWaits: 0, unread: true, unseenCount: 1, cursor: "att1:41",
                                               items: [.init(kind: "notify", runId: "b81f3302", at: "2026-10-17T05:06:10Z", title: "Morning digest", body: "3 things today", cursor: "att1:41")])),
        AutomationSummary(id: "auto-lit", name: "Literature watch", status: "active", scheduleText: "every 7 days",
                          lastOccurrence: LastOccurrence(status: "completed", excerpt: "3 new papers"), cadence: "weekly", detail: "every 7 days · 3 new papers"),
        AutomationSummary(id: "auto-qc", name: "Assay QC check", status: "active", scheduleText: "when a file lands",
                          lastOccurrence: LastOccurrence(status: "completed", excerpt: nil), cadence: "on event", detail: "when a file lands · ok"),
    ]

    public static let sampleEntities: [EntitySummary] = [
        EntitySummary(name: "castor", extra: ["phase": .string("work"), "age": .string("long-lived")]),
        EntitySummary(name: "mira", extra: ["phase": .string("personal")]),
        EntitySummary(name: "nerin", extra: ["phase": .string("sleep")]),
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

    public init(waits: [Wait] = MockGatewayClient.sampleWaits, wordInterval: TimeInterval = 0.12) {
        self.pending = waits; self.wordInterval = wordInterval
    }

    public func health() async throws -> Bool { true }
    public func me() async throws -> Principal { Principal(userId: "albou", tenantId: "default", roles: ["admin"]) }
    public func waits() async throws -> [Wait] { pending }
    public func recentRuns(limit: Int) async throws -> [RunSummary] { Self.sampleRuns }
    public func automations() async throws -> [AutomationSummary] { Self.sampleAutomations }
    public func runAutomationNow(id: String) async throws {}
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
        LedgerPage(items: Array(Self.sampleLedger.dropFirst(min(after, Self.sampleLedger.count))), nextAfter: Self.sampleLedger.count)
    }
    public func cancel(runId: String) async throws { started[runId] = nil }
    public func occurrences(automationId: String, limit: Int) async throws -> [LastOccurrence] {
        Self.sampleAutomations.first { $0.id == automationId }?.lastOccurrence.map { [$0] } ?? []
    }
    public func markSeen(automationId: String, cursor: String) async throws {}

    /// Two short synthetic "sentences" (a voiced tone with a syllable envelope), so the read screen and
    /// the orb can be exercised without a gateway.
    public func transcribe(wav: Data, sessionId: String) async throws -> String {
        try await Task.sleep(for: .milliseconds(900))
        return "Compare overall survival by treatment arm in the ADTTE I sent you"
    }

    public nonisolated func speech(text: String, scope: SpeechScope) -> AsyncThrowingStream<Data, Error> {
        AsyncThrowingStream { continuation in
            Task {
                try? await Task.sleep(for: .milliseconds(600))
                continuation.yield(SyntheticSpeech.wav(seconds: 2.4, seed: 1))
                continuation.yield(SyntheticSpeech.wav(seconds: 2.0, seed: 2))
                continuation.finish()
            }
        }
    }

    public func answer(_ wait: Wait, with answer: WaitAnswer) async throws {
        pending.removeAll { $0.id == wait.id }
    }

    public func prompt(ofRun id: String) async throws -> String? {
        ["94a436e1": "Clean the build folder and rebuild the app", "7c1e02aa": "Now split it by age group",
         "r1a9e0b2": "Compare overall survival by treatment arm in the ADTTE I sent you",
         "3e9a10c4": "Did the nightly assay QC pass?", "d0c5a971": "Summarise the open issues in the docs"][id]
    }

    public func turns(ofSession id: String) async throws -> [RunSummary] {
        Self.sampleRuns.filter { ($0.sessionId ?? $0.runId) == id }
    }

    public func tools() async throws -> [ToolInfo] {
        [ToolInfo(name: "read_file", riskTier: "observe", riskRank: 1), ToolInfo(name: "fetch_url", riskTier: "act", riskRank: 2),
         ToolInfo(name: "send_email", riskTier: "outreach", riskRank: 3), ToolInfo(name: "execute_command", riskTier: "destroy", riskRank: 4)]
    }

    public func startRun(prompt: String, sessionId: String?, toolPolicy: RunToolPolicy?) async throws -> String {
        let id = "mock-" + UUID().uuidString.prefix(6).lowercased()
        started[id] = (Date(), Self.cannedAnswer)
        return id
    }

    /// A started mock run "streams": each poll reveals the words due by now, then completes.
    public func run(id: String) async throws -> RunSummary {
        guard let (t0, text) = started[id] else {
            return Self.sampleRuns.first { $0.runId == id } ?? RunSummary(runId: id, workflowId: nil, status: "failed", error: "unknown run")
        }
        let words = text.split(separator: " ")
        let thinking = 1.2
        let elapsed = Date().timeIntervalSince(t0) - thinking
        let n = elapsed <= 0 ? 0 : min(words.count, Int(elapsed / wordInterval) + 1)
        let done = n >= words.count
        return RunSummary(runId: id, workflowId: "@default", status: done ? "completed" : "running",
                          output: n == 0 ? nil : .string(words.prefix(n).joined(separator: " ")))
    }
}
