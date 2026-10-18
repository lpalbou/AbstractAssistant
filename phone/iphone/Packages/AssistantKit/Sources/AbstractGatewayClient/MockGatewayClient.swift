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
        AutomationSummary(id: "auto-morning", name: "Morning digest", status: "active", scheduleText: "Every 24 hours (UTC)",
                          lastOccurrence: LastOccurrence(status: "completed", excerpt: "Three things today: the assay QC run passed; two new papers on your target; one dependency to pin.",
                                                         runId: "b81f3302", index: 41, firedAt: "2026-10-17T05:04:00Z", finishedAt: "2026-10-17T05:06:10Z",
                                                         answer: "Three things today: the assay QC run passed; two new papers on your target (one with a phase II readout); the dependency check found one update to pin."),
                          cadence: "daily", detail: "every day · last 07:04 · ok", nextFireAt: "2026-10-18T05:00:00Z",
                          attention: Attention(pendingWaits: 0, unread: true, unseenCount: 1, cursor: "att1:41",
                                               items: [.init(kind: "notify", runId: "b81f3302", at: "2026-10-17T05:06:10Z", title: "Morning digest", body: "3 things today", cursor: "att1:41")]),
                          contextMode: "growing", occurrenceCount: 41, triggerSource: "schedule",
                          triggerConfig: ["every": .string("24h"), "anchor": .string("2026-09-07T05:04:00Z")], revision: 2),
        AutomationSummary(id: "auto-lit", name: "Literature watch", status: "active", scheduleText: "every 7 days",
                          lastOccurrence: LastOccurrence(status: "completed", excerpt: "3 new papers"), cadence: "weekly", detail: "every 7 days · 3 new papers"),
        AutomationSummary(id: "auto-qc", name: "Assay QC check", status: "active", scheduleText: "when a file lands",
                          lastOccurrence: LastOccurrence(status: "completed", excerpt: nil), cadence: "on event", detail: "when a file lands · ok"),
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
    public static let cannedAnswer = "Let’s make a little room.\n\n**Start with one protected hour.** Choose a morning this week, silence notifications, and give that time to the idea you keep postponing.\n\n1. Pick one outcome that would make the week feel worthwhile.\n2. Move one meeting or small task out of the way.\n3. Leave ten minutes afterward to capture what changed.\n\nWhat would you most like that hour to be for?"

    private var createdEntities: [EntitySummary] = []
    private let emptyAutomations: Bool
    private var createdAutomations: [AutomationSummary] = []
    private var chosenWorkflow: String?
    private var uploaded: [String: [(PhoneArtifact, Data)]] = [:]
    private var statuses: [String: String] = [:]
    private var pending: [Wait]
    private var started: [String: (Date, String)] = [:]
    private var cancelledRunIDs: Set<String> = []
    private let wordInterval: TimeInterval
    private let activityScenario: String?
    private var activityResolved = false

    public init(waits: [Wait] = MockGatewayClient.sampleWaits, wordInterval: TimeInterval = 0.12, emptyAutomations: Bool = false, activityScenario: String? = nil) {
        self.activityScenario = activityScenario
        self.pending = waits; self.wordInterval = wordInterval; self.emptyAutomations = emptyAutomations
    }

    public func health() async throws -> Bool { true }
    public func me() async throws -> Principal { Principal(userId: "albou", tenantId: "default", roles: ["admin"]) }
    public func waits() async throws -> [Wait] { pending }
    public func recentRuns(limit: Int) async throws -> [RunSummary] { Self.sampleRuns }
    public func automations() async throws -> [AutomationSummary] {
        var out: [AutomationSummary] = []
        for a in (emptyAutomations ? [] : Self.sampleAutomations) + createdAutomations { out.append(try await automation(id: a.id)) }
        return out
    }
    /// Run now: the automation runs for 14 s (`current_occurrence` set, a ledger that moves on).
    private var automationRunStarted: [String: Date] = [:]
    public func runAutomationNow(id: String) async throws { automationRunStarted[id] = Date() }
    public func automation(id: String) async throws -> AutomationSummary {
        guard var a = (Self.sampleAutomations + createdAutomations).first(where: { $0.id == id }) else { throw GatewayError.http(status: 404, body: "") }
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
    public func automationCommand(id: String, type: String) async throws { statuses[id] = type == "automation.pause" ? "paused" : "active" }
    public func reviseAutomation(id: String, changes: [String: JSONValue], expectedRevision: Int?) async throws {}
    public func workflows(forInterface interface: String) async throws -> [WorkflowChoice] {
        [WorkflowChoice(bundleId: "basic-agent", bundleVersion: "0.0.5", flowId: "81795ea9", name: "Basic agent"),
         WorkflowChoice(bundleId: "deep-research", bundleVersion: "0.1.8", flowId: "deep-research", name: "Deep research"),
         WorkflowChoice(bundleId: "memact-agent", bundleVersion: "0.1.0", flowId: "memact", name: "MemAct agent")]
    }
    public func workflowInputs(_ w: WorkflowChoice) async throws -> WorkflowInputs {
        WorkflowInputs(defaults: ["use_context": .bool(false)], required: w.bundleId == "memact-agent" ? ["prompt"] : [])
    }
    public func createAutomation(_ a: NewAutomation) async throws -> AutomationSummary {
        try await Task.sleep(for: .milliseconds(600))
        let row = AutomationSummary(id: "auto-" + a.requestId.prefix(6), name: a.title, status: "active", scheduleText: nil, lastOccurrence: nil,
                                 triggerSource: "schedule", triggerConfig: { switch a.when {
                                     case .every(let e): ["kind": .string("every"), "every": .string(e)]
                                     case .daily(let at): ["kind": .string("daily"), "at": .string(at)] } }(), revision: 1)
        if !createdAutomations.contains(where: { $0.id == row.id }) { createdAutomations.append(row) }
        return row
    }
    public func automationDefinition(id: String) async throws -> AutomationDefinition {
        AutomationDefinition(revision: 2, title: Self.sampleAutomations.first { $0.id == id }?.name, target: [
            "bundle_ref": .string("basic-agent@0.0.5"), "flow_id": .string("81795ea9"),
            "input_data": .object(["prompt": .string("Summarise the overnight assay QC runs, new papers on my target, and dependency updates to pin."),
                                   "tools": .array([.string("web_search")])]),
        ])
    }
    public func voiceCatalog() async throws -> VoiceCatalog {
        VoiceCatalog(voices: [VoiceChoice(provider: "supertonic", model: "supertonic-3", voice: "F2", label: "Supertonic · F2"), VoiceChoice(provider: "supertonic", model: "supertonic-3", voice: "M1", label: "Supertonic · M1")], transcription: [TranscriptionChoice(provider: "faster-whisper", model: "base"), TranscriptionChoice(provider: "faster-whisper", model: "large-v3-turbo")], defaultVoice: "Supertonic · F2", defaultTranscription: "faster-whisper · base")
    }
    public func accountPreferences() async throws -> JSONValue {
        .object(["time_zone": .object(["effective": .string("Europe/Paris")]), "apps": .array([.object([
            "interface": .string("abstractassistant.agent.v1"), "value": chosenWorkflow.map(JSONValue.string) ?? .null,
            "gateway_default_label": .string("Gateway default · Basic agent"),
            "effective": .object(["available": .bool(true)]),
            "choices": .array([.object(["value": .string("basic-agent:root"), "name": .string("Basic agent"), "label": .string("Basic agent")]), .object(["value": .string("deep-research:root"), "name": .string("Deep research"), "label": .string("Deep research")])])
        ])])])
    }
    public func setAssistantWorkflow(_ value: String?) async throws -> JSONValue { chosenWorkflow = value; return try await accountPreferences() }
    public func startRun(prompt: String, sessionId: String?, attachments: [JSONValue]) async throws -> String { try await startRun(prompt: prompt, sessionId: sessionId, toolPolicy: nil) }
    public func upload(data: Data, filename: String, contentType: String, sessionId: String) async throws -> PhoneArtifact {
        let artifact = PhoneArtifact(artifactId: UUID().uuidString, runId: "session_memory_" + sessionId, filename: filename, contentType: contentType, size: data.count)
        uploaded[sessionId, default: []].append((artifact, data)); return artifact
    }
    public func artifacts(sessionId: String) async throws -> [PhoneArtifact] {
        let sample = PhoneArtifact(artifactId: "demo-report", runId: "demo-run", filename: "A little focus.txt", contentType: "text/plain", size: Self.cannedAnswer.utf8.count)
        return [sample] + (uploaded[sessionId] ?? []).map { $0.0 }
    }
    public func download(_ artifact: PhoneArtifact) async throws -> Data {
        if artifact.artifactId == "demo-report" { return Data(Self.cannedAnswer.utf8) }
        for rows in uploaded.values { if let row = rows.first(where: { $0.0.id == artifact.id }) { return row.1 } }
        throw GatewayError.invalidResponse
    }
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

    public static let sampleLedger: [LedgerRecord] = [
        LedgerRecord(nodeId: "plan", status: "completed", effect: .object(["type": .string("llm_call")]), result: .object(["output": .object(["response": .string("plan: KM + Cox by TRT01P")])])),
        LedgerRecord(nodeId: "write_code", status: "completed", effect: .object(["type": .string("llm_call")]), result: .object(["mode": .string("code v1")])),
        LedgerRecord(nodeId: "run", status: "failed", effect: .object(["type": .string("tool_calls")]), error: "KeyError 'ARM'"),
        LedgerRecord(nodeId: "write_code", status: "completed", effect: .object(["type": .string("llm_call")]), result: .object(["mode": .string("code v2 · traceback in context")])),
        LedgerRecord(nodeId: "run", status: "completed", effect: .object(["type": .string("tool_calls")]), result: .object(["tool_calls": .array([.object(["name": .string("python analysis/run.py")])])])),
        LedgerRecord(nodeId: "review", status: "started", effect: .object(["type": .string("llm_call")])),
    ]
    public func ledger(runId: String, after: Int) async throws -> LedgerPage {
        if activityScenario != nil && runId.hasPrefix("activity-") {
            if activityScenario == "offline" { throw GatewayError.http(status: 503, body: "Gateway unavailable") }
            let all = runId == "activity-root" ? [] : activityRecords()
            return LedgerPage(items: Array(all.dropFirst(after).prefix(200)), nextAfter: min(all.count, after + 200))
        }
        if runId == "occ-live" { let all = liveLedger(); return LedgerPage(items: Array(all.dropFirst(min(after, all.count))), nextAfter: all.count) }
        return LedgerPage(items: Array(Self.sampleLedger.dropFirst(min(after, Self.sampleLedger.count))), nextAfter: Self.sampleLedger.count)
    }
    public func cancel(runId: String) async throws {
        cancelledRunIDs.insert(runId); started[runId] = nil; pending.removeAll { $0.runId == runId }
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
                                  answer: failed ? "The run stopped: the model was not reachable." : "Digest \(i): the assay QC run passed; nothing new to pin.")
        }
        return [last] + older
    }
    public func markSeen(automationId: String, cursor: String) async throws {}

    /// Two short synthetic "sentences" (a voiced tone with a syllable envelope), so the read screen and
    /// the orb can be exercised without a gateway.
    public func transcribe(wav: Data, sessionId: String) async throws -> String {
        try await Task.sleep(for: .milliseconds(900))
        return "Help me make room for focused work this week"
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
        if wait.runId == "activity-child" { activityResolved = true }
        pending.removeAll { $0.id == wait.id }
    }

    public func prompt(ofRun id: String) async throws -> String? {
        ["94a436e1": "Clean the build folder and rebuild the app", "7c1e02aa": "What could I move out of the way?",
         "r1a9e0b2": "Help me make room for focused work this week",
         "3e9a10c4": "Did the nightly assay QC pass?", "d0c5a971": "Summarise the open issues in the docs"][id]
    }

    public func turns(ofSession id: String) async throws -> [RunSummary] {
        Self.sampleRuns.filter { ($0.sessionId ?? $0.runId) == id }
    }

    public func automationDefaults() async throws -> Int? { 50_000 }
    public func messageStats(runID: String) async throws -> MessageStats? {
        .init(wallTimeSeconds: 4.8, inputTokens: 1234, outputTokens: 245, toolCalls: 2)
    }
    public func startRun(prompt: String, sessionId: String?, attachments: [JSONValue], tools: ConversationTools?) async throws -> String {
        try await startRun(prompt: prompt, sessionId: sessionId, toolPolicy: tools?.policy)
    }
    public func tools() async throws -> [ToolInfo] {
        var unavailable = ToolInfo(name: "capture_camera", riskTier: "outreach", riskRank: 3, toolset: "camera", description: "Capture a photo from the gateway’s camera.", approvalDefault: "ask", enabled: false)
        unavailable.whyDisabled = "The gateway camera is not enabled."
        return [
            unavailable,
            ToolInfo(name: "read_file", riskTier: "observe", riskRank: 1, toolset: "files", description: "Read a file in your workspace.", approvalDefault: "auto"),
            ToolInfo(name: "fetch_url", riskTier: "act", riskRank: 2, toolset: "web", description: "Read a web page from a URL.", approvalDefault: "ask"),
            ToolInfo(name: "send_email", riskTier: "outreach", riskRank: 3, toolset: "comms", description: "Send an email from your connected account.", approvalDefault: "ask"),
            ToolInfo(name: "execute_command", riskTier: "destroy", riskRank: 4, toolset: "system", description: "Execute a command in the gateway workspace.", approvalDefault: "ask")
        ]
    }

    public func startRun(prompt: String, sessionId: String?, toolPolicy: RunToolPolicy?) async throws -> String {
        if activityScenario != nil {
            if activityScenario == "offline" { return "activity-root" }
            let child = try await activityRun("activity-child")
            if let wait = child.personWait { pending = [wait] }
            return "activity-root"
        }
        let id = "mock-" + UUID().uuidString.prefix(6).lowercased()
        started[id] = (Date(), Self.cannedAnswer)
        return id
    }

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
        let now = ISO8601DateFormatter().string(from: Date())
        let model = JSONValue.object(["type": .string("llm_call")])
        let call: JSONValue = .object(["name": .string("read_file"), "runtime_call_id": .string("host-read")])
        let tool: JSONValue = .object(["type": .string("tool_calls"), "payload": .object(["tool_calls": .array([call])])])
        var rows = [LedgerRecord(stepId: "cycle-1", nodeId: "reason", status: "started", effect: model, startedAt: now),
                    LedgerRecord(stepId: "cycle-1", nodeId: "reason", status: "completed", effect: model, endedAt: now),
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
        if cancelledRunIDs.contains(id) { return RunSummary(runId: id, workflowId: nil, status: "cancelled") }
        if activityScenario != nil && id.hasPrefix("activity-") { return try await activityRun(id) }
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
