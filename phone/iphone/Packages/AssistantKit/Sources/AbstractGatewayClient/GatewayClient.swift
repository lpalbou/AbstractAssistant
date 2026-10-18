import Foundation

public enum GatewayError: Error, Equatable, Sendable, LocalizedError {
    /// 401: the token is wrong. The gateway locks out by client address after 5 failures,
    /// so the client stops sending until the user enters a new token.
    case unauthorized
    case http(status: Int, body: String)
    case invalidResponse
    /// The wait was answered elsewhere (or the run moved on) between showing it and answering.
    case alreadyHandled

    public var errorDescription: String? {
        switch self {
        // Shown to people as is: plain words, no codes (the body stays on the value for logs).
        case .unauthorized: "Please sign in again."
        case .http(let s, let body): GatewaySignIn.detail(Data(body.utf8)) ?? (s >= 500 ? "Your assistant is having trouble. Try again." : "That didn't work. Try again.")
        case .invalidResponse: "Can't reach your assistant."
        case .alreadyHandled: "Already answered on another device."
        }
    }
}

/// The calls the watch makes (gateway-api-brief.md section I).
public protocol GatewayClient: Sendable {
    var isMock: Bool { get }
    /// `GET /api/health`
    func health() async throws -> Bool
    func automationDefaults() async throws -> Int?
    func messageStats(runID: String) async throws -> MessageStats?
    func entityTools(name: String) async throws -> [ToolInfo]
    func openEntitySession(name: String, sessionID: String, tools: ConversationTools?) async throws -> EntitySessionState
    func sendEntityTurn(name: String, runID: String, text: String) async throws -> JSONValue
    func endEntitySession(name: String, runID: String) async throws
    func entitySession(name: String, runID: String) async throws -> EntitySessionState
    func setEntityTools(name: String, runID: String, tools: ConversationTools?) async throws
    func answerEntity(name: String, runID: String, waitKey: String, approved: Bool) async throws -> EntitySessionState
    func startRun(prompt: String, sessionId: String?, attachments: [JSONValue], tools: ConversationTools?) async throws -> String
    func startRun(prompt: String, sessionId: String?, attachments: [JSONValue], tools: ConversationTools?, primaryImage: JSONValue?) async throws -> String
    func download(_ artifact: PhoneArtifact, to destination: URL) async throws
    /// `GET /api/gateway/me`
    func me() async throws -> Principal
    /// `GET /api/gateway/runs?status=waiting`, projected to waits on a person.
    func waits() async throws -> [Wait]
    /// `GET /api/gateway/runs?root_only=true&limit=20`
    func recentRuns(limit: Int) async throws -> [RunSummary]
    /// `GET /api/gateway/runs/{id}/input_data`: what the person asked in that turn.
    func input(ofRun id: String) async throws -> ConversationInput
    func prompt(ofRun id: String) async throws -> String?
    /// `GET /api/gateway/runs?session_id=…&root_only=true&include_metrics=true`: one session's turns, newest first.
    func turns(ofSession id: String) async throws -> [RunSummary]
    /// `GET /api/gateway/runs/{id}`
    func run(id: String) async throws -> RunSummary
    /// `POST /api/gateway/runs/start`; returns the run id.
    func startRun(prompt: String, sessionId: String?, toolPolicy: RunToolPolicy?) async throws -> String
    /// `GET /api/gateway/discovery/tools`: the tools with their risk tiers.
    func tools() async throws -> [ToolInfo]
    /// `POST /api/gateway/commands` with `type: "resume"`.
    func answer(_ wait: Wait, with answer: WaitAnswer) async throws
    /// `GET /api/gateway/automations` (first page).
    func automations() async throws -> [AutomationSummary]
    /// `POST /api/gateway/automations/{id}/commands` `{type: "automation.run_now"}`.
    func runAutomationNow(id: String) async throws
    /// `POST /automations/{id}/commands` (`automation.pause`, `automation.resume`, …).
    func automationCommand(id: String, type: String) async throws
    /// `GET /automations/{id}` → `summary`: one automation's row, fresh (e.g. its run in progress).
    func automation(id: String) async throws -> AutomationSummary
    /// `GET /bundles?executable_for=<interface>`: the workflows this account may schedule.
    func workflows(forInterface interface: String) async throws -> [WorkflowChoice]
    /// `GET /bundles/{b}/flows/{f}/input_schema?bundle_version=`: a workflow's inputs.
    func workflowInputs(_ w: WorkflowChoice) async throws -> WorkflowInputs
    /// `POST /automations`: creates it; returns its row.
    func createAutomation(_ a: NewAutomation) async throws -> AutomationSummary
    /// `GET /automations/{id}`: the committed definition (its task and target).
    func automationDefinition(id: String) async throws -> AutomationDefinition
    /// `PATCH /automations/{id}`: only what changed, with the revision it was read at.
    func reviseAutomation(id: String, changes: [String: JSONValue], expectedRevision: Int?) async throws
    /// `GET /api/gateway/entities`: the entities this account may visit.
    func validateEntity(_ draft: EntityDraft) async throws -> EntityValidation
    func createEntity(_ draft: EntityDraft) async throws -> CreatedEntity
    func entities() async throws -> [EntitySummary]
    /// `POST /api/gateway/entities/{name}/chat/open` → chat id (one live session per home).
    func openEntityChat(name: String) async throws -> String
    /// `POST /api/gateway/entities/{name}/chat/{chat_id}/turn` `{text}` → the reply.
    func entityChatTurn(name: String, chatId: String, text: String) async throws -> String
    /// `GET /api/gateway/runs/{id}/ledger?after=N` → records after the cursor.
    func ledger(runId: String, after: Int) async throws -> LedgerPage
    nonisolated func ledgerEvents(runID: String, after: Int) -> AsyncThrowingStream<LedgerStreamEvent, Error>
    func entityLedger(name: String, runID: String, after: Int) async throws -> LedgerPage
    func childRuns(ofRunID: String) async throws -> [RunSummary]
    /// `POST /api/gateway/commands` `{type: "cancel"}`.
    func cancel(runId: String) async throws
    /// `GET /api/gateway/automations/{id}/occurrences?limit=N`.
    func occurrences(automationId: String, limit: Int) async throws -> [LastOccurrence]
    /// `POST /api/gateway/automations/{id}/seen` `{attention_cursor}`.
    func markSeen(automationId: String, cursor: String) async throws
    /// Speech for `text`, as complete WAV files in reading order: `POST /api/gateway/runs/{id}/voice/tts/stream`
    /// for a run's text, `POST /api/gateway/entities/{name}/voice/tts/stream` for an entity's (its own voice).
    /// The gateway's configured voice answers; the first chunk arrives after the first sentence is synthesized.
    nonisolated func speech(text: String, scope: SpeechScope) -> AsyncThrowingStream<Data, Error>
    /// What the person said: uploads the WAV as a session attachment (`POST /api/gateway/attachments/upload`)
    /// and transcribes it with the gateway's STT (`POST /api/gateway/runs/{session owner}/audio/transcribe`).
    func transcribe(wav: Data, sessionId: String) async throws -> String
    func voiceCatalog() async throws -> VoiceCatalog
    func accountPreferences() async throws -> JSONValue
    func setAssistantWorkflow(_ value: String?) async throws -> JSONValue
    func startRun(prompt: String, sessionId: String?, attachments: [JSONValue]) async throws -> String
    func upload(data: Data, filename: String, contentType: String, sessionId: String) async throws -> PhoneArtifact
    func artifacts(sessionId: String) async throws -> [PhoneArtifact]
    func download(_ artifact: PhoneArtifact) async throws -> Data
    nonisolated func speech(text: String, scope: SpeechScope, voice: VoiceChoice?) -> AsyncThrowingStream<Data, Error>
    func transcribe(wav: Data, sessionId: String, model: TranscriptionChoice?) async throws -> String
}

/// Live client over URLSession: `Authorization: Bearer <token>`, or a gateway session from an
/// emailed sign-in code (`X-AbstractGateway-Session`, plus `X-AbstractGateway-CSRF` on writes).
public actor LiveGatewayClient: GatewayClient {
    public nonisolated let isMock = false
    private let baseURL: URL
    private let credential: GatewayCredential
    private let session: URLSession
    private var lockedOut = false
    private var entityVisitRoutes: [String: Bool] = [:]
    private func requireSignIn() throws { if lockedOut { throw GatewayError.unauthorized } }
    private func lockSignIn() { lockedOut = true }

    public init(baseURL: URL, credential: GatewayCredential, session: URLSession = .shared) {
        self.baseURL = baseURL; self.credential = credential; self.session = session
    }

    public init(baseURL: URL, token: String, session: URLSession = .shared) {
        self.init(baseURL: baseURL, credential: .token(token), session: session)
    }

    private func request(_ method: String, _ path: String, query: [URLQueryItem] = [], body: (any Encodable)? = nil,
                         timeout: TimeInterval = 20) async throws -> Data {
        if lockedOut { throw GatewayError.unauthorized }
        var comps = URLComponents(url: baseURL.appending(path: path), resolvingAgainstBaseURL: false)!
        if !query.isEmpty { comps.queryItems = query }
        var req = URLRequest(url: comps.url!)
        req.httpMethod = method
        req.timeoutInterval = timeout
        credential.apply(to: &req, write: method != "GET")
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        if let body {
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = try JSONEncoder().encode(body)
        }
        let (data, resp) = try await session.data(for: req)
        guard let http = resp as? HTTPURLResponse else { throw GatewayError.invalidResponse }
        if http.statusCode == 401 { lockedOut = true; throw GatewayError.unauthorized }
        guard (200..<300).contains(http.statusCode) else {
            throw GatewayError.http(status: http.statusCode, body: String(decoding: data, as: UTF8.self))
        }
        return data
    }

    private func get<T: Decodable>(_ path: String, query: [URLQueryItem] = [], as: T.Type) async throws -> T {
        try JSONDecoder().decode(T.self, from: try await request("GET", path, query: query))
    }

    public func health() async throws -> Bool {
        _ = try await request("GET", "api/health"); return true
    }

    public func me() async throws -> Principal { try await get("api/gateway/me", as: Principal.self) }

    /// Person waits: list the waiting runs, keep the rows whose `waiting.reason` is `user`,
    /// then read each run's detail, which carries the full wait block (see `RunSummary.personWait`).
    public func waits() async throws -> [Wait] {
        let page = try await get("api/gateway/runs", query: [.init(name: "status", value: "waiting")], as: RunsPage.self)
        let candidates = page.items.filter(\.waitsOnPerson).prefix(12)
        return try await withThrowingTaskGroup(of: Wait?.self) { group in
            for row in candidates {
                group.addTask { try await self.run(id: row.runId).personWait }
            }
            var out: [Wait] = []
            for try await w in group { if let w { out.append(w) } }
            return out.sorted { ($0.askedAt ?? .distantPast) < ($1.askedAt ?? .distantPast) }
        }
    }

    public func prompt(ofRun id: String) async throws -> String? { try await input(ofRun: id).prompt }
    public func input(ofRun id: String) async throws -> ConversationInput {
        let value = try await get("api/gateway/runs/\(id)/input_data", as: JSONValue.self)["input_data"]
        let inputs = value?["attachments"] ?? value?["context"]?["attachments"] ?? .array([])
        let refs = RunSummary(runId: id, workflowId: nil, status: "completed", output: .object(["artifacts": inputs])).mediaArtifacts
        return ConversationInput(prompt: value?["prompt"]?.stringValue, attachments: refs)
    }

    public func turns(ofSession id: String) async throws -> [RunSummary] {
        var offset = 0
        var rows: [RunSummary] = []
        var seen: Set<String> = []
        while true {
            let page = try await get("api/gateway/runs", query: [.init(name: "session_id", value: id), .init(name: "root_only", value: "true"),
                .init(name: "limit", value: "100"), .init(name: "offset", value: String(offset)), .init(name: "include_metrics", value: "true")], as: RunsPage.self)
            let fresh = page.items.filter { seen.insert($0.runId).inserted }
            // Retain legacy rows with absent session metadata, but reject explicit
            // unrelated sessions and descendants if an old gateway ignores filters.
            rows.append(contentsOf: fresh.filter {
                ($0.sessionId == nil || $0.sessionId == id) && ($0.parentRunId == nil || $0.sessionKind == "occurrence")
            })
            guard page.hasMore ?? (page.items.count == 100) else { return rows }
            guard !fresh.isEmpty else { throw GatewayError.invalidResponse }
            offset += page.items.count
        }
    }

    /// The conversations' turns (chats and discussions; automations have their own screen), with metrics.
    public func recentRuns(limit: Int) async throws -> [RunSummary] {
        try await get("api/gateway/runs", query: [.init(name: "root_only", value: "true"), .init(name: "limit", value: String(limit)),
                                                   .init(name: "include_metrics", value: "true"), .init(name: "session_kind", value: "chat,discussion")],
                      as: RunsPage.self).items
    }

    public func run(id: String) async throws -> RunSummary { try await get("api/gateway/runs/\(id)", as: RunSummary.self) }

    public func tools() async throws -> [ToolInfo] {
        let page = try await get("api/gateway/discovery/tools", as: ToolsPage.self)
        guard page.error?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty != false else {
            throw GatewayError.http(status: 503, body: "{\"detail\":\"Your gateway’s tools could not be loaded. Try again before sending.\"}")
        }
        return page.items
    }

    public func startRun(prompt: String, sessionId: String?, toolPolicy: RunToolPolicy?) async throws -> String {
        try await startAssistantRun(prompt: prompt, sessionId: sessionId, attachments: [], selection: nil, toolPolicy: toolPolicy)
    }

    /// Answers a wait. The run is re-read first: if it no longer waits on the same key, the wait
    /// was handled elsewhere and nothing is sent (a stale approval must never resume another step).
    public func answer(_ wait: Wait, with answer: WaitAnswer) async throws {
        let current = try await run(id: wait.runId)
        guard current.status == "waiting", current.waiting?.waitKey == wait.waitKey else { throw GatewayError.alreadyHandled }
        _ = try await request("POST", "api/gateway/commands", body: ResumeCommand(runId: wait.runId, waitKey: wait.waitKey, answer: answer))
    }

    public func automations() async throws -> [AutomationSummary] {
        try await get("api/gateway/automations", as: AutomationsPage.self).items
    }

    private struct RunNow: Encodable {
        var command_id = UUID().uuidString.lowercased()
        var type = "automation.run_now"
    }

    public func runAutomationNow(id: String) async throws {
        _ = try await request("POST", "api/gateway/automations/\(id)/commands", body: RunNow())
    }

    private struct Command: Encodable {
        var command_id = UUID().uuidString.lowercased()
        let type: String
    }

    public func automationCommand(id: String, type: String) async throws {
        _ = try await request("POST", "api/gateway/automations/\(id)/commands", body: Command(type: type))
    }

    private struct Revise: Encodable {
        var command_id = UUID().uuidString.lowercased()
        let expected_revision: Int?
        let changes: [String: JSONValue]
    }

    public func automation(id: String) async throws -> AutomationSummary {
        try await get("api/gateway/automations/\(id)", as: AutomationSummaryResponse.self).summary
    }

    public func workflows(forInterface interface: String) async throws -> [WorkflowChoice] {
        WorkflowChoice.choices(from: try await get("api/gateway/bundles", query: [.init(name: "executable_for", value: interface)], as: JSONValue.self))
    }

    public func workflowInputs(_ w: WorkflowChoice) async throws -> WorkflowInputs {
        let v = try await get("api/gateway/bundles/\(w.bundleId)/flows/\(w.flowId)/input_schema",
                              query: [.init(name: "bundle_version", value: w.bundleVersion)], as: JSONValue.self)
        guard let inputs = WorkflowInputs.parse(v) else { throw GatewayError.invalidResponse }
        return inputs
    }

    public func createAutomation(_ a: NewAutomation) async throws -> AutomationSummary {
        do {
            let data = try await request("POST", "api/gateway/automations", body: a.body, timeout: 60)
            return try JSONDecoder().decode(CreatedAutomation.self, from: data).summary
        } catch GatewayError.http(let status, let body) where status == 422 && body.contains("tool_policy") { throw AutomationToolsError.unsupported }
    }

    public func automationDefinition(id: String) async throws -> AutomationDefinition {
        try await get("api/gateway/automations/\(id)", as: AutomationDefinitionResponse.self).definition
    }

    public func reviseAutomation(id: String, changes: [String: JSONValue], expectedRevision: Int?) async throws {
        _ = try await request("PATCH", "api/gateway/automations/\(id)", body: Revise(expected_revision: expectedRevision, changes: changes))
    }

    public func validateEntity(_ draft: EntityDraft) async throws -> EntityValidation {
        guard draft.valid else { throw GatewayError.http(status: 400, body: "{\"detail\":\"Use a name of up to 64 letters, numbers, spaces, hyphens or underscores.\"}") }
        let data = try await request("POST", "api/gateway/entities/\(draft.slug)/validate", body: draft.body)
        return try JSONDecoder().decode(EntityValidation.self, from: data)
    }
    public func createEntity(_ draft: EntityDraft) async throws -> CreatedEntity {
        guard draft.valid else { throw GatewayError.invalidResponse }
        let data = try await request("POST", "api/gateway/entities", body: draft.body, timeout: 120)
        return try CreatedEntity(JSONDecoder().decode(JSONValue.self, from: data))
    }

    public func entities() async throws -> [EntitySummary] {
        try await get("api/gateway/entities", as: EntitiesPage.self).entities
    }

    public func openEntityChat(name: String) async throws -> String {
        let data = try await request("POST", "api/gateway/entities/\(name)/chat/open", body: ChatOpenRequest())
        return try JSONDecoder().decode(ChatOpenResponse.self, from: data).chatId
    }

    public func entityChatTurn(name: String, chatId: String, text: String) async throws -> String {
        let data = try await request("POST", "api/gateway/entities/\(name)/chat/\(chatId)/turn", body: ChatTurnRequest(text: text))
        return try JSONDecoder().decode(ChatTurnResponse.self, from: data).reply ?? ""
    }

    public func ledger(runId: String, after: Int) async throws -> LedgerPage {
        try await get("api/gateway/runs/\(runId)/ledger", query: [.init(name: "after", value: String(after))], as: LedgerPage.self)
    }

    public func childRuns(ofRunID id: String) async throws -> [RunSummary] {
        struct Page: Decodable { var items: [RunSummary]; var has_more: Bool? }
        var offset = 0
        var rows: [RunSummary] = []
        var seen: Set<String> = []
        while true {
            let page = try await get("api/gateway/runs", query: [.init(name: "parent_run_id", value: id), .init(name: "limit", value: "100"), .init(name: "offset", value: String(offset))], as: Page.self)
            // Old gateways may ignore an unknown parent filter. Never adopt unrelated runs.
            let children = page.items.filter { $0.parentRunId == id }
            let fresh = children.filter { seen.insert($0.runId).inserted }
            rows.append(contentsOf: fresh)
            guard page.has_more == true else { return rows }
            guard !page.items.isEmpty, !fresh.isEmpty else { throw LedgerStreamError.invalidCursor }
            offset += page.items.count
        }
    }

    public func entityLedger(name: String, runID: String, after: Int) async throws -> LedgerPage {
        struct Entry: Decodable { var cursor: Int; var record: LedgerRecord }
        struct VisitPage: Decodable {
            var after: Int; var records: [Entry]; var next_cursor: Int; var total: Int
        }
        let page = try await get("api/gateway/entities/\(name)/visit/\(runID)/ledger",
            query: [.init(name: "after", value: String(after)), .init(name: "limit", value: "200")], as: VisitPage.self)
        // The visit endpoint wraps each row and can clamp an overshot cursor.
        // Refuse a rewind or gap rather than silently attributing the wrong rows.
        guard after >= 0, page.after == after, page.next_cursor == after + page.records.count,
              page.total >= page.next_cursor,
              page.records.enumerated().allSatisfy({ $0.element.cursor == after + $0.offset + 1 }) else {
            throw LedgerStreamError.invalidCursor
        }
        return LedgerPage(items: page.records.map(\.record), nextAfter: page.next_cursor)
    }

    public nonisolated func ledgerEvents(runID: String, after: Int) -> AsyncThrowingStream<LedgerStreamEvent, Error> {
        var url = URLComponents(url: baseURL.appending(path: "api/gateway/runs/\(runID)/ledger/stream"), resolvingAgainstBaseURL: false)!
        url.queryItems = [.init(name: "after", value: String(after))]
        var request = URLRequest(url: url.url!)
        request.timeoutInterval = 60
        request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        credential.apply(to: &request, write: false)
        let streamRequest = request
        let session = self.session
        return AsyncThrowingStream(bufferingPolicy: .bufferingOldest(128)) { continuation in
            let task = Task {
                do {
                    try await self.requireSignIn()
                    let (bytes, response) = try await session.bytes(for: streamRequest, delegate: LedgerRedirectGuard())
                    defer { bytes.task.cancel() }
                    guard let http = response as? HTTPURLResponse else { throw GatewayError.invalidResponse }
                    if http.statusCode == 401 { await self.lockSignIn(); throw GatewayError.unauthorized }
                    if [404, 405].contains(http.statusCode) {
                        bytes.task.cancel()
                        try await pollLedger(client: self, runID: runID, after: after, continuation: continuation)
                        continuation.finish(); return
                    }
                    guard (200..<300).contains(http.statusCode) else { throw GatewayError.http(status: http.statusCode, body: "") }
                    var parser = LedgerSSEParser()
                    for try await byte in bytes {
                        try Task.checkCancellation()
                        if let event = try parser.feed(byte: byte) {
                            try yieldLedger(event, to: continuation)
                            if case .done = event { continuation.finish(); return }
                        }
                    }
                    // EOF without done is reconnectable, never proof of completion.
                    throw GatewayError.invalidResponse
                } catch { continuation.finish(throwing: error) }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    public func cancel(runId: String) async throws {
        _ = try await request("POST", "api/gateway/commands", body: CancelCommand(runId: runId))
    }

    public func occurrences(automationId: String, limit: Int) async throws -> [LastOccurrence] {
        try await get("api/gateway/automations/\(automationId)/occurrences", query: [.init(name: "limit", value: String(limit))], as: OccurrencesPage.self).items
    }

    public func markSeen(automationId: String, cursor: String) async throws {
        _ = try await request("POST", "api/gateway/automations/\(automationId)/seen", body: SeenRequest(attentionCursor: cursor))
    }

    public func voiceCatalog() async throws -> VoiceCatalog {
        async let voices = get("api/gateway/voice/voices", as: JSONValue.self)
        async let models = get("api/gateway/audio/transcriptions/models", as: JSONValue.self)
        return VoiceCatalog.parse(voices: try await voices, transcription: try await models)
    }
    public func accountPreferences() async throws -> JSONValue { try await get("api/gateway/accounts/me/preferences", as: JSONValue.self) }
    public func setAssistantWorkflow(_ value: String?) async throws -> JSONValue {
        let data = try await request("PUT", "api/gateway/accounts/me/preferences", body: JSONValue.object(["default_workflow": .object(["abstractassistant.agent.v1": value.map(JSONValue.string) ?? .null])]))
        return try JSONDecoder().decode(JSONValue.self, from: data)
    }
    public func startRun(prompt: String, sessionId: String?, attachments: [JSONValue]) async throws -> String {
        try await startAssistantRun(prompt: prompt, sessionId: sessionId, attachments: attachments, selection: nil, toolPolicy: nil)
    }
    public func automationDefaults() async throws -> Int? {
        struct Defaults: Decodable { var growing_max_tokens: Int }
        do { return try await get("api/gateway/automations/defaults", as: Defaults.self).growing_max_tokens }
        catch GatewayError.http(status: 404, body: _) { return nil }
    }
    public func messageStats(runID: String) async throws -> MessageStats? {
        do { return try await get("api/gateway/runs/\(runID)/message-stats", as: MessageStats.self) }
        catch GatewayError.http(status: 404, body: _) { return nil }
    }
    public func entityTools(name: String) async throws -> [ToolInfo] {
        struct Inventory: Decodable { var items: [ToolInfo]; var visit_routes: Bool? }
        let inventory = try await get("api/gateway/entities/\(name)/session-tools", as: Inventory.self)
        entityVisitRoutes[name] = inventory.visit_routes == true
        return inventory.items
    }
    private func usesEntityVisitRoutes(name: String) async throws -> Bool {
        if let known = entityVisitRoutes[name] { return known }
        _ = try await entityTools(name: name)
        return entityVisitRoutes[name] == true
    }
    public func openEntitySession(name: String, sessionID: String, tools: ConversationTools?) async throws -> EntitySessionState {
        let suffix = try await usesEntityVisitRoutes(name: name) ? "visit/open" : "sessions"
        // An explicit modes:null opts into an owned visit with inherited home grants.
        let policy: JSONValue = .object(["modes": tools.map { .object($0.modes.mapValues { .string($0.rawValue) }) } ?? .null])
        let body: JSONValue = .object(["session_id": .string(sessionID), "tool_policy": policy])
        let data = try await request("POST", "api/gateway/entities/\(name)/\(suffix)", body: body, timeout: 120)
        return try JSONDecoder().decode(EntitySessionState.self, from: data)
    }
    public func sendEntityTurn(name: String, runID: String, text: String) async throws -> JSONValue {
        let data = try await request("POST", "api/gateway/entities/\(name)/visit/\(runID)/turn", body: ChatTurnRequest(text: text), timeout: 120)
        return try JSONDecoder().decode(JSONValue.self, from: data)
    }
    public func endEntitySession(name: String, runID: String) async throws {
        let canonical = try await usesEntityVisitRoutes(name: name)
        _ = try await request("POST", "api/gateway/entities/\(name)/visit/\(runID)/\(canonical ? "close" : "end")",
                              body: JSONValue.object(canonical ? ["closed_by": .string("pause")] : [:]), timeout: 120)
    }
    public func entitySession(name: String, runID: String) async throws -> EntitySessionState {
        try await get("api/gateway/entities/\(name)/visit/\(runID)/state", as: EntitySessionState.self)
    }
    public func setEntityTools(name: String, runID: String, tools: ConversationTools?) async throws {
        // Null restores home defaults; an empty map disables every tool.
        let body: JSONValue = tools.map { .object(["modes": .object($0.modes.mapValues { .string($0.rawValue) })]) } ?? .object(["modes": .null])
        _ = try await request("PUT", "api/gateway/entities/\(name)/visit/\(runID)/tool-policy", body: body)
    }
    public func answerEntity(name: String, runID: String, waitKey: String, approved: Bool) async throws -> EntitySessionState {
        struct Body: Encodable { var wait_key: String; var approved: Bool }
        let data = try await request("POST", "api/gateway/entities/\(name)/visit/\(runID)/decision", body: Body(wait_key: waitKey, approved: approved), timeout: 120)
        return try JSONDecoder().decode(EntitySessionState.self, from: data)
    }
    public func startRun(prompt: String, sessionId: String?, attachments: [JSONValue], tools: ConversationTools?) async throws -> String {
        try await startAssistantRun(prompt: prompt, sessionId: sessionId, attachments: attachments, selection: tools, toolPolicy: tools?.policy)
    }
    public func startRun(prompt: String, sessionId: String?, attachments: [JSONValue], tools: ConversationTools?, primaryImage: JSONValue?) async throws -> String {
        try await startAssistantRun(prompt: prompt, sessionId: sessionId, attachments: attachments, selection: tools, toolPolicy: tools?.policy, primaryImage: primaryImage)
    }
    public func startRun(_ body: StartRunRequest) async throws -> String {
        try JSONDecoder().decode(StartRunResponse.self, from: await request("POST", "api/gateway/runs/start", body: body)).runId
    }
    private func startAssistantRun(prompt: String, sessionId: String?, attachments: [JSONValue], selection: ConversationTools?, toolPolicy: RunToolPolicy?, primaryImage: JSONValue? = nil) async throws -> String {
        var body = try AssistantWorkflow.request(prompt: prompt, sessionId: sessionId, toolPolicy: toolPolicy, preferences: try await accountPreferences())
        let inventory = try await tools()
        let catalog = Dictionary(inventory.map { ($0.name, $0) }, uniquingKeysWith: { _, latest in latest })
        let available = Set(catalog.values.filter(\.isAvailable).map(\.name))
        let allowed: [String]
        if let selection {
            let current = ConversationTools(modes: selection.modes.filter { available.contains($0.key) })
            allowed = current.allowed; body.inputData.runtime?.toolPolicy = current.policy
        } else {
            // Discovery approval defaults are not workflow Tools-pin defaults. Like the
            // tray, supply the actual enabled list on every turn, including inheritance.
            allowed = catalog.values.filter {
                $0.isAvailable && !["off", "disabled"].contains($0.approvalDefault?.lowercased() ?? "")
            }.map(\.name).sorted()
        }
        body.inputData.tools = allowed
        if body.inputData.runtime == nil { body.inputData.runtime = .init(toolPolicy: toolPolicy) }
        body.inputData.runtime?.allowedTools = allowed
        var context: [String: JSONValue] = [:]
        if !attachments.isEmpty {
            body.inputData.attachments = attachments
            context = ["attachments": .array(attachments), "media": .array(attachments)]
        }
        let image = attachments.first { $0["content_type"]?.stringValue?.lowercased().hasPrefix("image/") == true } ?? primaryImage
        body.inputData.primaryImageArtifact = image
        body.inputData.hasPrimaryImageContext = image != nil
        if let image { context["primary_image_artifact"] = image }
        if !context.isEmpty { body.inputData.context = .object(context) }
        return try await startRun(body)
    }
    public func upload(data: Data, filename: String, contentType: String, sessionId: String) async throws -> PhoneArtifact {
        try requireSignIn()
        guard data.count <= PhoneArtifact.byteLimit else { throw PhoneAttachmentError.tooLarge }
        let boundary = "iphone-" + UUID().uuidString
        let filename = PhoneArtifact.safeFilename(filename)
        var body = Data()
        for (key, value) in [("session_id", sessionId), ("filename", filename), ("content_type", contentType)] {
            body.append(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(key)\"\r\n\r\n\(value)\r\n".utf8))
        }
        body.append(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"\(filename)\"\r\nContent-Type: application/octet-stream\r\n\r\n".utf8)); body.append(data); body.append(Data("\r\n--\(boundary)--\r\n".utf8))
        var req = URLRequest(url: baseURL.appending(path: "api/gateway/attachments/upload")); req.httpMethod = "POST"; req.timeoutInterval = 120
        credential.apply(to: &req, write: true); req.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type"); req.httpBody = body
        let originalSize = data.count
        let (data, response) = try await session.data(for: req)
        guard let http = response as? HTTPURLResponse else { throw GatewayError.invalidResponse }
        if http.statusCode == 401 { lockedOut = true; throw GatewayError.unauthorized }
        guard (200..<300).contains(http.statusCode) else { throw GatewayError.http(status: http.statusCode, body: String(decoding: data, as: UTF8.self)) }
        let v = try JSONDecoder().decode(JSONValue.self, from: data)
        guard let artifact = PhoneArtifact.upload(v, filename: filename, contentType: contentType, size: originalSize) else { throw GatewayError.invalidResponse }
        return artifact
    }
    public func artifacts(sessionId: String) async throws -> [PhoneArtifact] {
        let v = try await get("api/gateway/sessions/\(sessionId)/artifacts", query: [.init(name: "limit", value: "100")], as: JSONValue.self)
        guard case .array(let items)? = v["items"] else { throw GatewayError.invalidResponse }
        return items.compactMap(PhoneArtifact.parse)
    }
    public func download(_ artifact: PhoneArtifact) async throws -> Data {
        var data = Data()
        try await readArtifact(artifact, limit: PhoneArtifact.byteLimit) { data.append($0) }
        return data
    }
    public func download(_ artifact: PhoneArtifact, to destination: URL) async throws {
        guard destination.isFileURL, !FileManager.default.fileExists(atPath: destination.path),
              FileManager.default.createFile(atPath: destination.path, contents: nil) else { throw GatewayError.invalidResponse }
        var handle: FileHandle?
        do {
            let opened = try FileHandle(forWritingTo: destination); handle = opened
            try await readArtifact(artifact, limit: PhoneArtifact.previewByteLimit) { try opened.write(contentsOf: $0) }
            try opened.close()
        } catch {
            try? handle?.close(); try? FileManager.default.removeItem(at: destination); throw error
        }
    }
    private func readArtifact(_ artifact: PhoneArtifact, limit: Int, consume: (Data) throws -> Void) async throws {
        try requireSignIn()
        guard PhoneArtifact.validID(artifact.runId), PhoneArtifact.validID(artifact.artifactId) else { throw GatewayError.invalidResponse }
        guard artifact.size <= limit else { throw limit == PhoneArtifact.byteLimit ? PhoneAttachmentError.tooLarge : PhoneAttachmentError.previewTooLarge }
        // Only Gateway-owned routes receive credentials. Stream large previews to disk in chunks.
        var req = URLRequest(url: baseURL.appending(path: "api/gateway/runs/\(artifact.runId)/artifacts/\(artifact.artifactId)/content")); req.timeoutInterval = 120
        credential.apply(to: &req, write: false)
        let (bytes, response) = try await session.bytes(for: req, delegate: LedgerRedirectGuard())
        defer { bytes.task.cancel() }
        guard let http = response as? HTTPURLResponse else { throw GatewayError.invalidResponse }
        if http.statusCode == 401 { lockedOut = true; throw GatewayError.unauthorized }
        guard (200..<300).contains(http.statusCode) else { throw GatewayError.http(status: http.statusCode, body: "") }
        guard response.expectedContentLength <= limit else { throw PhoneAttachmentError.previewTooLarge }
        var count = 0, chunk = Data(); chunk.reserveCapacity(65_536)
        for try await byte in bytes {
            try Task.checkCancellation(); guard count < limit else { throw PhoneAttachmentError.previewTooLarge }
            chunk.append(byte); count += 1
            if chunk.count == 65_536 { try consume(chunk); chunk.removeAll(keepingCapacity: true) }
        }
        if !chunk.isEmpty { try consume(chunk) }
    }

    public func transcribe(wav: Data, sessionId: String) async throws -> String { try await transcribe(wav: wav, sessionId: sessionId, model: nil) }
    public func transcribe(wav: Data, sessionId: String, model: TranscriptionChoice?) async throws -> String {
        if lockedOut { throw GatewayError.unauthorized }
        let boundary = "watch-" + UUID().uuidString
        var body = Data()
        func field(_ name: String, _ value: String) {
            body.append(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(name)\"\r\n\r\n\(value)\r\n".utf8))
        }
        field("session_id", sessionId); field("content_type", "audio/wav"); field("filename", "ask.wav")
        body.append(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"ask.wav\"\r\nContent-Type: audio/wav\r\n\r\n".utf8))
        body.append(wav)
        body.append(Data("\r\n--\(boundary)--\r\n".utf8))
        var req = URLRequest(url: baseURL.appending(path: "api/gateway/attachments/upload"))
        req.httpMethod = "POST"; req.timeoutInterval = 60; req.httpBody = body
        credential.apply(to: &req, write: true)
        req.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        let (data, resp) = try await session.data(for: req)
        guard let http = resp as? HTTPURLResponse else { throw GatewayError.invalidResponse }
        if http.statusCode == 401 { lockedOut = true; throw GatewayError.unauthorized }
        guard (200..<300).contains(http.statusCode) else { throw GatewayError.http(status: http.statusCode, body: String(decoding: data, as: UTF8.self)) }
        let upload = try JSONDecoder().decode(AttachmentUploadResponse.self, from: data)
        guard let ref = upload.artifact ?? upload.attachment, let id = ref.artifact else { throw GatewayError.invalidResponse }
        let owner = upload.runId ?? ref.runId ?? "session_memory_\(sessionId)"
        let out = try await request("POST", "api/gateway/runs/\(owner)/audio/transcribe",
                                    body: TranscribeRequest(audioArtifact: ["$artifact": id], provider: model?.provider, model: model?.model), timeout: 120)
        return try JSONDecoder().decode(TranscribeResponse.self, from: out).text.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    public nonisolated func speech(text: String, scope: SpeechScope) -> AsyncThrowingStream<Data, Error> { speech(text: text, scope: scope, voice: nil) }
    public nonisolated func speech(text: String, scope: SpeechScope, voice: VoiceChoice?) -> AsyncThrowingStream<Data, Error> {
        let path: String
        switch scope {
        case .run(let id): path = "api/gateway/runs/\(id)/voice/tts/stream"
        case .entity(let name): path = "api/gateway/entities/\(name)/voice/tts/stream"
        }
        var req = URLRequest(url: baseURL.appending(path: path))
        req.httpMethod = "POST"
        req.timeoutInterval = 90
        credential.apply(to: &req, write: true)
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONEncoder().encode(SpeechRequest(text: text, provider: voice?.provider, model: voice?.model, voice: voice?.voice))
        let session = self.session
        let request = req
        return AsyncThrowingStream { continuation in
            let task = Task { @Sendable in
                do {
                    try await self.requireSignIn()
                    let (bytes, resp) = try await session.bytes(for: request)
                    defer { bytes.task.cancel() }
                    guard let http = resp as? HTTPURLResponse else { throw GatewayError.invalidResponse }
                    if http.statusCode == 401 { await self.lockSignIn(); throw GatewayError.unauthorized }
                    guard (200..<300).contains(http.statusCode) else {
                        var body = ""
                        for try await line in bytes.lines { body += line; if body.count > 400 { break } }
                        throw GatewayError.http(status: http.statusCode, body: body)
                    }
                    for try await line in bytes.lines {
                        guard let event = try? JSONDecoder().decode(SpeechEvent.self, from: Data(line.utf8)) else { continue }
                        switch event.type {
                        case "audio":
                            if let b64 = event.audioB64, let wav = Data(base64Encoded: b64) { continuation.yield(wav) }
                        case "error":
                            throw GatewayError.http(status: 502, body: event.error ?? "speech failed")
                        case "done":
                            continuation.finish(); return
                        default: continue
                        }
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }
}
