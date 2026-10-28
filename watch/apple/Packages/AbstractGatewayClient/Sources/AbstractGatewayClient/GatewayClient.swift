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
        // Shown to people as is: the gateway's own words when it gave some, else plain words, no codes
        // (the body stays on the value for logs).
        case .unauthorized: "Please sign in again."
        case .http(let s, let body): GatewaySignIn.detail(Data(body.utf8)) ?? (s >= 500 ? "Your assistant is having trouble. Try again." : "That didn't work. Try again.")
        case .invalidResponse: "Can't reach your assistant."
        case .alreadyHandled: "Already answered on another device."
        }
    }
}

/// The calls the watch and the iPhone make (gateway-api-brief.md section I). A call one app does not
/// make has a default below for test doubles (a gateway without the route: 404, or `unsupported`).
public protocol GatewayClient: Sendable {
    var isMock: Bool { get }
    /// `GET /api/health`
    func health() async throws -> Bool
    /// `GET /api/gateway/me`
    func me() async throws -> Principal
    /// `GET /api/gateway/runs?status=waiting`, projected to waits on a person.
    func waits() async throws -> [Wait]
    /// `GET /api/gateway/runs?root_only=true&limit=20`
    func recentRuns(limit: Int) async throws -> [RunSummary]
    /// `GET /api/gateway/runs/{id}/input_data`: what the person asked in that turn.
    func prompt(ofRun id: String) async throws -> String?
    /// The same, with the files the person gave that turn.
    func input(ofRun id: String) async throws -> ConversationInput
    /// `GET /api/gateway/runs?session_id=…&root_only=true&include_metrics=true`: one session's turns, newest first (one page).
    func turns(ofSession id: String, limit: Int) async throws -> [RunSummary]
    /// The same, every page (a turn of another session, or a sub-run, an old gateway returned is dropped).
    func turns(ofSession id: String) async throws -> [RunSummary]
    /// `GET /api/gateway/runs/{run}/history_bundle?include_session=true`: the session of `run` (its
    /// newest turn) as the gateway replays it, each turn's question and answer, oldest first. One
    /// request (~200 KB for 44 turns) instead of two per turn (~850 KB over the watch's radio).
    func sessionHistory(latestRun runId: String, limit: Int) async throws -> [SessionTurn]
    /// `GET /api/gateway/runs/{id}`
    func run(id: String) async throws -> RunSummary
    /// `GET /api/gateway/runs?parent_run_id=`: a run's children, every page.
    func childRuns(ofRunID: String) async throws -> [RunSummary]
    /// `POST /api/gateway/sessions/{id}/archive` (or `/unarchive`): out of (or back in) the
    /// conversations listing; nothing is deleted.
    func setArchived(sessionId: String, _ archived: Bool) async throws
    /// `GET /api/gateway/runs?archived_only=true&root_only=true`: the archived conversations' turns, every page.
    func archivedRuns(limit: Int) async throws -> [RunSummary]
    /// `GET /api/gateway/sessions/search?q=…`: keyword search over the caller's conversations.
    func searchSessions(_ query: String, limit: Int) async throws -> SessionSearchPage
    /// `POST /api/gateway/runs/start` (the watch's turn); returns the run id. `workflow` nil: the gateway's default agent.
    func startRun(prompt: String, sessionId: String?, toolPolicy: RunToolPolicy?, tools: [String]?, workflow: WorkflowChoice?, primaryImage: MediaItem?) async throws -> String
    /// `POST /api/gateway/runs/start` with the account's Assistant workflow (the iPhone's turn).
    func startRun(prompt: String, sessionId: String?, toolPolicy: RunToolPolicy?) async throws -> String
    func startRun(prompt: String, sessionId: String?, attachments: [JSONValue]) async throws -> String
    func startRun(prompt: String, sessionId: String?, attachments: [JSONValue], tools: ConversationTools?) async throws -> String
    func startRun(prompt: String, sessionId: String?, attachments: [JSONValue], tools: ConversationTools?, primaryImage: JSONValue?) async throws -> String
    /// `GET /sessions/{id}/artifacts`: the media a conversation's turns made, by run.
    func sessionMedia(sessionId: String) async throws -> [String: [MediaItem]]
    /// `GET /runs/{run}/artifacts/{id}/content`: one media item's bytes (at most `MediaItem.byteLimit`).
    func mediaData(_ item: MediaItem) async throws -> Data
    /// `GET /sessions/{id}/artifacts`: the conversation's files (what its turns made or were given),
    /// with, given a run of the conversation, the files of its folder (`GET /runs/{run}/workspace/files`).
    func sessionFiles(sessionId: String, folderRunId: String?) async throws -> SessionFiles
    /// `GET /runs/{run}/artifacts/{id}/content`: one file's bytes (at most `MediaItem.byteLimit`).
    func fileData(_ file: SessionFile) async throws -> Data
    /// `POST /attachments/upload`: one file the person gives a turn.
    func upload(data: Data, filename: String, contentType: String, sessionId: String) async throws -> PhoneArtifact
    /// `GET /sessions/{id}/artifacts`, one page (or every one) as artifacts.
    func artifacts(sessionId: String) async throws -> [PhoneArtifact]
    func artifactPage(sessionID: String, offset: Int, includeVoice: Bool) async throws -> SessionArtifactPage
    /// `GET /runs/{run}/artifacts/{id}/content`, in memory or streamed to a file.
    func download(_ artifact: PhoneArtifact) async throws -> Data
    func download(_ artifact: PhoneArtifact, to destination: URL) async throws
    /// `GET /runs/{run}/workspace`, `…/workspace/files`, `…/workspace/content`.
    func workspace(runID: String) async throws -> RunWorkspace
    func workspaceFiles(runID: String, path: String, recursive: Bool, limit: Int?) async throws -> WorkspaceListing
    func downloadWorkspaceFile(runID: String, entry: WorkspaceEntry, to destination: URL) async throws
    /// `GET /api/gateway/discovery/tools`: the tools with their risk tiers.
    func tools() async throws -> [ToolInfo]
    /// `POST /api/gateway/commands` with `type: "resume"`.
    func answer(_ wait: Wait, with answer: WaitAnswer) async throws
    /// `GET /api/gateway/automations` (first page).
    func automations() async throws -> [AutomationSummary]
    /// `GET /api/gateway/automations?archived_only=true`: the archived automations.
    func archivedAutomations() async throws -> [AutomationSummary]
    /// `POST /api/gateway/automations/{id}/commands` `{type: "automation.run_now"}`.
    func runAutomationNow(id: String) async throws
    /// `POST /automations/{id}/commands` (`automation.pause`, `automation.resume`, …).
    func automationCommand(id: String, type: String) async throws
    /// `POST /automations/{id}/discuss {request_id, occurrence_index, prompt}`: a conversation about
    /// the automation, seeded with its runs up to that one; the automation's own context is untouched.
    func discussAutomation(id: String, occurrenceIndex: Int, prompt: String) async throws -> Discussion
    /// `GET /api/gateway/automations/defaults`: the gateway's defaults for a new automation.
    func automationDefaults() async throws -> AutomationDefaults
    /// `GET /automations/{id}` → `summary`: one automation's row, fresh (e.g. its run in progress).
    func automation(id: String) async throws -> AutomationSummary
    /// `GET /bundles?executable_for=<interface>`: the workflows this account may schedule (an empty
    /// interface: every runnable workflow).
    func workflows(forInterface interface: String) async throws -> [WorkflowChoice]
    /// The workflows a conversation can run: the agents' and the Assistant's (`WorkflowChoice.conversation`).
    func conversationWorkflows() async throws -> [WorkflowChoice]
    /// `GET /bundles/{b}/flows/{f}/input_schema?bundle_version=`: a workflow's inputs.
    func workflowInputs(_ w: WorkflowChoice) async throws -> WorkflowInputs
    /// `POST /automations`: creates it; returns its row.
    func createAutomation(_ a: NewAutomation) async throws -> AutomationSummary
    /// `GET /automations/{id}`: the committed definition (its task and target).
    func automationDefinition(id: String) async throws -> AutomationDefinition
    /// `PATCH /automations/{id}`: only what changed, with the revision it was read at.
    func reviseAutomation(id: String, changes: [String: JSONValue], expectedRevision: Int?) async throws
    /// `GET /api/gateway/entities`: the entities this account may visit.
    func entities() async throws -> [EntitySummary]
    /// `POST /entities/{slug}/validate` and `POST /entities`: a new entity.
    func validateEntity(_ draft: EntityDraft) async throws -> EntityValidation
    func createEntity(_ draft: EntityDraft) async throws -> CreatedEntity
    /// `POST /api/gateway/entities/{name}/chat/open` → chat id (one live session per home).
    func openEntityChat(name: String) async throws -> String
    /// `POST /api/gateway/entities/{name}/chat/{chat_id}/turn` `{text}` → the reply.
    func entityChatTurn(name: String, chatId: String, text: String) async throws -> String
    /// An entity visit (`/entities/{name}/visit/…`): its tools, open, a turn, its state, its tools'
    /// policy, an approval, close.
    func entityTools(name: String) async throws -> [ToolInfo]
    func openEntitySession(name: String, sessionID: String, tools: ConversationTools?) async throws -> EntitySessionState
    func sendEntityTurn(name: String, runID: String, text: String) async throws -> JSONValue
    func endEntitySession(name: String, runID: String) async throws
    func entitySession(name: String, runID: String) async throws -> EntitySessionState
    func setEntityTools(name: String, runID: String, tools: ConversationTools?) async throws
    func answerEntity(name: String, runID: String, waitKey: String, approved: Bool) async throws -> EntitySessionState
    func entityLedger(name: String, runID: String, after: Int) async throws -> LedgerPage
    /// `GET /api/gateway/runs/{id}/ledger?after=N` → records after the cursor.
    func ledger(runId: String, after: Int) async throws -> LedgerPage
    /// `GET /runs/{id}/ledger/stream` (SSE), or polled where a gateway has no stream.
    nonisolated func ledgerEvents(runID: String, after: Int) -> AsyncThrowingStream<LedgerStreamEvent, Error>
    /// The same step log, read for the run's activity only (`ActivityRecord`): a thinking step's
    /// conversation is skipped while decoding.
    func activity(runId: String, after: Int) async throws -> ActivityPage
    /// `GET /runs/{id}/message-stats`: a reply's time, tokens and tool calls (nil: not served).
    func messageStats(runID: String) async throws -> MessageStats?
    /// `POST /api/gateway/commands` `{type: "cancel"}`.
    func cancel(runId: String) async throws
    /// `GET /api/gateway/automations/{id}/occurrences?limit=N`.
    func occurrences(automationId: String, limit: Int) async throws -> [LastOccurrence]
    /// `POST /api/gateway/automations/{id}/seen` `{attention_cursor}`.
    func markSeen(automationId: String, cursor: String) async throws
    /// Speech for `text`, as complete WAV files in reading order: `POST /api/gateway/runs/{id}/voice/tts/stream`
    /// for a run's text, `POST /api/gateway/entities/{name}/voice/tts/stream` for an entity's (its own voice).
    /// The gateway's configured voice answers (or `voice`); the first chunk arrives after the first sentence is synthesized.
    nonisolated func speech(text: String, scope: SpeechScope) -> AsyncThrowingStream<Data, Error>
    nonisolated func speech(text: String, scope: SpeechScope, voice: VoiceChoice?) -> AsyncThrowingStream<Data, Error>
    /// What the person said: uploads the WAV as a session attachment (`POST /api/gateway/attachments/upload`)
    /// and transcribes it with the gateway's STT (`POST /api/gateway/runs/{session owner}/audio/transcribe`).
    func transcribe(wav: Data, sessionId: String) async throws -> String
    func transcribe(wav: Data, sessionId: String, model: TranscriptionChoice?) async throws -> String
    /// `GET /voice/voices` + `GET /audio/transcriptions/models`: the voices and transcription models offered.
    func voiceCatalog() async throws -> VoiceCatalog
    /// The voice library (AbstractGateway 0.16.0): `POST /voice/design`, `POST /voice/clones` (multipart),
    /// `PATCH` and `DELETE /voice/clones/{id}`. A refusal throws the gateway's sentence (403: one shared
    /// store, an administrator's act; 422: a shared voice is read-only; 501: the engine is missing).
    func designVoice(description: String, name: String?, language: String?) async throws -> CreatedVoice
    func cloneVoice(_ upload: VoiceCloneUpload) async throws -> CreatedVoice
    func renameVoice(id: String, name: String) async throws
    func deleteVoice(id: String) async throws
    /// `GET /accounts/me/preferences`, and `PUT` of the Assistant's workflow in it.
    func accountPreferences() async throws -> JSONValue
    func setAssistantWorkflow(_ value: String?) async throws -> JSONValue
    /// `GET /api/gateway/me/email`: this account's mailbox and whether its email tools are on.
    func emailStatus() async throws -> EmailStatus
    /// `GET /api/gateway/me/events?after=&limit=`: the person's own events after a sequence, oldest
    /// first (one request: the watch's background refresh's whole radio cost). A gateway without the
    /// stream answers 404 (`GatewayError.http(404, …)`).
    func events(after: Int, limit: Int) async throws -> UserEventsPage
    /// `GET /api/gateway/me/events/stream` with `Last-Event-ID`: the live tail; ends when the server closes it.
    nonisolated func userEventStream(lastEventID: Int) -> AsyncThrowingStream<UserEvent, Error>
    /// `POST /api/gateway/me/events/notifications {channel, outcome: "sent", record_key, device}`:
    /// this device showed the notice (sent once, only after it actually notified).
    func reportNotification(_ report: NotificationReport) async throws
    /// `GET /triggers/connections` (labels) and `GET /me/email/accounts` (addresses), only the ones asked
    /// for: the words an automation's trigger is said with.
    func triggerNames(connections: Bool, mailboxes: Bool) async throws -> TriggerNames
}

/// What a test double that does not answer a route gives: what a gateway without it would.
public extension GatewayClient {
    func turns(ofSession id: String, limit: Int) async throws -> [RunSummary] { throw GatewayError.http(status: 404, body: "") }
    func sessionHistory(latestRun runId: String, limit: Int) async throws -> [SessionTurn] { throw GatewayError.http(status: 404, body: "") }
    func setArchived(sessionId: String, _ archived: Bool) async throws { throw GatewayError.invalidResponse }
    func archivedRuns(limit: Int) async throws -> [RunSummary] { throw GatewayError.invalidResponse }
    func searchSessions(_ query: String, limit: Int) async throws -> SessionSearchPage { throw GatewayError.http(status: 404, body: "") }
    func startRun(prompt: String, sessionId: String?, toolPolicy: RunToolPolicy?, tools: [String]?, workflow: WorkflowChoice?, primaryImage: MediaItem?) async throws -> String {
        throw GatewayError.http(status: 404, body: "")
    }
    func sessionMedia(sessionId: String) async throws -> [String: [MediaItem]] { throw GatewayError.http(status: 404, body: "") }
    func mediaData(_ item: MediaItem) async throws -> Data { throw GatewayError.http(status: 404, body: "") }
    func sessionFiles(sessionId: String, folderRunId: String?) async throws -> SessionFiles { throw GatewayError.http(status: 404, body: "") }
    func fileData(_ file: SessionFile) async throws -> Data { throw GatewayError.http(status: 404, body: "") }
    func discussAutomation(id: String, occurrenceIndex: Int, prompt: String) async throws -> Discussion { throw GatewayError.http(status: 404, body: "") }
    func automationDefaults() async throws -> AutomationDefaults { throw GatewayError.http(status: 404, body: "") }
    func conversationWorkflows() async throws -> [WorkflowChoice] { throw GatewayError.http(status: 404, body: "") }
    func activity(runId: String, after: Int) async throws -> ActivityPage { throw GatewayError.http(status: 404, body: "") }
    func emailStatus() async throws -> EmailStatus { throw GatewayError.http(status: 404, body: "") }
}

/// Live client over URLSession: `Authorization: Bearer <token>`, or a gateway session from an
/// emailed sign-in code (`X-AbstractGateway-Session`, plus `X-AbstractGateway-CSRF` on writes).
public actor LiveGatewayClient: GatewayClient {
    public nonisolated let isMock = false
    private let baseURL: URL
    private let credential: GatewayCredential
    private let session: URLSession
    private let readTries: Int
    private var lockedOut = false
    private var entityVisitRoutes: [String: Bool] = [:]
    private func requireSignIn() throws { if lockedOut { throw GatewayError.unauthorized } }
    private func lockSignIn() { lockedOut = true }

    /// `readTries`: how many times a read is tried before its failure is reported (the iPhone: 1).
    public init(baseURL: URL, credential: GatewayCredential, session: URLSession = .shared, readTries: Int = LiveGatewayClient.readTries) {
        self.baseURL = baseURL; self.credential = credential; self.session = session; self.readTries = max(1, readTries)
    }

    public init(baseURL: URL, token: String, session: URLSession = .shared, readTries: Int = LiveGatewayClient.readTries) {
        self.init(baseURL: baseURL, credential: .token(token), session: session, readTries: readTries)
    }

    /// How many times the watch tries a read before its failure is reported.
    public static let readTries = 3

    /// A read (GET) that times out, loses its connection or meets a server error is tried again,
    /// after 1 s then 3 s: a screen keeps its spinner through the tries and says a read failed
    /// only once every try has (ADR-0039 in abstractframework docs/adr). A write (POST, PUT, …) is sent once.
    private func request(_ method: String, _ path: String, query: [URLQueryItem] = [], body: (any Encodable)? = nil,
                         timeout: TimeInterval = 20) async throws -> Data {
        var attempt = 1
        while true {
            do { return try await send(method, path, query: query, body: body, timeout: timeout) }
            catch {
                guard method == "GET", attempt < readTries, Self.isTransient(error), !Task.isCancelled else { throw error }
                try await Task.sleep(for: .seconds(attempt == 1 ? 1 : 3))
                attempt += 1
            }
        }
    }

    /// A failure that another try may not meet: no answer in time, a connection lost or refused,
    /// a server error (5xx, 408, 429). A refusal (401, 403, 404, …) or an unreadable answer is final.
    public static func isTransient(_ error: Error) -> Bool {
        switch error {
        case let e as URLError: return ![.cancelled, .badURL, .unsupportedURL, .userAuthenticationRequired, .userCancelledAuthentication].contains(e.code)
        case GatewayError.http(let status, _): return status >= 500 || status == 408 || status == 429
        case GatewayError.invalidResponse: return true
        default: return false
        }
    }

    private func send(_ method: String, _ path: String, query: [URLQueryItem], body: (any Encodable)?,
                      timeout: TimeInterval) async throws -> Data {
        if lockedOut { throw GatewayError.unauthorized }
        var comps = URLComponents(url: baseURL.appending(path: path), resolvingAgainstBaseURL: false)!
        if !query.isEmpty {
            comps.queryItems = query
            // A "+" left as is reads as a space on the server ("C++" would arrive as "C").
            comps.percentEncodedQuery = comps.percentEncodedQuery?.replacingOccurrences(of: "+", with: "%2B")
        }
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

    /// A voice library write (sent once): JSON `body`, or `raw` bytes with their `contentType`
    /// (multipart). Creating a voice loads an engine on first use, so the deadline is long.
    func voiceLibraryRequest(_ method: String, _ path: String, body: (any Encodable)? = nil, raw: Data? = nil,
                             contentType: String? = nil, timeout: TimeInterval = 300) async throws -> Data {
        if lockedOut { throw GatewayError.unauthorized }
        var req = URLRequest(url: baseURL.appending(path: path))
        req.httpMethod = method
        req.timeoutInterval = timeout
        credential.apply(to: &req, write: true)
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        if let raw {
            req.setValue(contentType, forHTTPHeaderField: "Content-Type"); req.httpBody = raw
        } else if let body {
            req.setValue("application/json", forHTTPHeaderField: "Content-Type"); req.httpBody = try JSONEncoder().encode(body)
        }
        let (data, resp) = try await session.data(for: req)
        guard let http = resp as? HTTPURLResponse else { throw GatewayError.invalidResponse }
        if http.statusCode == 401 { lockedOut = true; throw GatewayError.unauthorized }
        guard (200..<300).contains(http.statusCode) else { throw GatewayError.http(status: http.statusCode, body: String(decoding: data, as: UTF8.self)) }
        return data
    }

    private func get<T: Decodable>(_ path: String, query: [URLQueryItem] = [], as: T.Type, timeout: TimeInterval = 20) async throws -> T {
        try JSONDecoder().decode(T.self, from: try await request("GET", path, query: query, timeout: timeout))
    }

    public func health() async throws -> Bool {
        _ = try await request("GET", "api/health"); return true
    }

    public func me() async throws -> Principal { try await get("api/gateway/me", as: Principal.self) }

    // MARK: The person's events

    public func reportNotification(_ report: NotificationReport) async throws {
        _ = try await request("POST", "api/gateway/me/events/notifications", body: report)
    }

    public func events(after: Int, limit: Int) async throws -> UserEventsPage {
        try await get("api/gateway/me/events",
                      query: [.init(name: "after", value: String(after)), .init(name: "limit", value: String(limit))],
                      as: UserEventsPage.self, timeout: 30)
    }

    public nonisolated func userEventStream(lastEventID: Int) -> AsyncThrowingStream<UserEvent, Error> {
        var url = URLComponents(url: baseURL.appending(path: "api/gateway/me/events/stream"), resolvingAgainstBaseURL: false)!
        url.queryItems = [.init(name: "heartbeat_s", value: "15")]
        var request = URLRequest(url: url.url!)
        request.timeoutInterval = 60   // four missed keep-alives: a dead connection, reconnect
        request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        if lastEventID > 0 { request.setValue(String(lastEventID), forHTTPHeaderField: "Last-Event-ID") }
        credential.apply(to: &request, write: false)
        let streamRequest = request
        let session = self.session
        return AsyncThrowingStream(bufferingPolicy: .bufferingOldest(256)) { continuation in
            let task = Task {
                do {
                    try await self.requireSignIn()
                    let (bytes, response) = try await session.bytes(for: streamRequest, delegate: LedgerRedirectGuard())
                    defer { bytes.task.cancel() }
                    guard let http = response as? HTTPURLResponse else { throw GatewayError.invalidResponse }
                    if http.statusCode == 401 { await self.lockSignIn(); throw GatewayError.unauthorized }
                    guard (200..<300).contains(http.statusCode) else { throw GatewayError.http(status: http.statusCode, body: "") }
                    var parser = UserEventSSEParser()
                    for try await byte in bytes {
                        try Task.checkCancellation()
                        if let event = parser.feed(byte: byte) { continuation.yield(event) }
                    }
                    continuation.finish()   // the server closed it: the caller reconnects from its cursor
                } catch { continuation.finish(throwing: error) }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    public func triggerNames(connections: Bool, mailboxes: Bool) async throws -> TriggerNames {
        struct Connections: Decodable { struct Row: Decodable { var connection_id: String; var label: String? }; var connections: [Row] }
        struct Mailboxes: Decodable { struct Row: Decodable { var account_id: String; var address: String? }; var items: [Row] }
        var names = TriggerNames()
        if connections, let page = try? await get("api/gateway/triggers/connections", as: Connections.self) {
            for r in page.connections { if let l = r.label, !l.isEmpty { names.connections[r.connection_id] = l } }
        }
        if mailboxes, let page = try? await get("api/gateway/me/email/accounts", as: Mailboxes.self) {
            for r in page.items { if let a = r.address, !a.isEmpty { names.mailboxes[r.account_id] = a } }
        }
        return names
    }

    // MARK: Runs and conversations

    /// Person waits: list the waiting runs, keep the rows whose `waiting.reason` is `user`,
    /// then read each run's detail, which carries the full wait block (see `RunSummary.personWait`).
    public func waits() async throws -> [Wait] {
        let page = try await get("api/gateway/runs", query: [.init(name: "status", value: "waiting")], as: RunsPage.self, timeout: 45)
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

    public func prompt(ofRun id: String) async throws -> String? {
        try await get("api/gateway/runs/\(id)/input_data", as: RunInputData.self).inputData?.prompt
    }

    public func input(ofRun id: String) async throws -> ConversationInput {
        let value = try await get("api/gateway/runs/\(id)/input_data", as: JSONValue.self)["input_data"]
        let inputs = value?["attachments"] ?? value?["context"]?["attachments"] ?? .array([])
        let refs = RunSummary(runId: id, workflowId: nil, status: "completed", output: .object(["artifacts": inputs])).mediaArtifacts
        return ConversationInput(prompt: value?["prompt"]?.stringValue, attachments: refs)
    }

    public func sessionHistory(latestRun runId: String, limit: Int) async throws -> [SessionTurn] {
        let data = try await request("GET", "api/gateway/runs/\(runId)/history_bundle", query: [
            .init(name: "include_session", value: "true"), .init(name: "session_turn_limit", value: String(limit)),
            .init(name: "include_subruns", value: "false"), .init(name: "ledger_mode", value: "tail"),
            .init(name: "ledger_max_items", value: "1"), .init(name: "detail", value: "replay"),
        ], timeout: 90)
        let turns = try JSONDecoder().decode(HistoryBundle.self, from: data).session?.turns ?? []
        return turns.sorted { ($0.createdAt ?? "") < ($1.createdAt ?? "") }
    }

    public func turns(ofSession id: String, limit: Int) async throws -> [RunSummary] {
        try await get("api/gateway/runs", query: [.init(name: "session_id", value: id), .init(name: "root_only", value: "true"),
                                                   .init(name: "limit", value: String(limit)), .init(name: "include_metrics", value: "true")],
                      as: RunsPage.self).items
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
                      as: RunsPage.self, timeout: 45).items   // ~5 s on a public gateway, more over a watch's radio
    }

    public func run(id: String) async throws -> RunSummary { try await get("api/gateway/runs/\(id)", as: RunSummary.self) }

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

    public func setArchived(sessionId: String, _ archived: Bool) async throws {
        guard MediaItem.safeSession(sessionId) || PhoneArtifact.validID(sessionId) else { throw GatewayError.invalidResponse }
        _ = try await request("POST", "api/gateway/sessions/\(sessionId)/\(archived ? "archive" : "unarchive")")
    }

    public func archivedRuns(limit: Int) async throws -> [RunSummary] {
        let pageSize = max(1, min(limit, 100))
        var rows: [RunSummary] = [], seen: Set<String> = [], offset = 0
        while true {
            try Task.checkCancellation()
            let page = try await get("api/gateway/runs", query: [.init(name: "archived_only", value: "true"), .init(name: "root_only", value: "true"),
                .init(name: "limit", value: String(pageSize)), .init(name: "offset", value: String(offset)),
                .init(name: "include_metrics", value: "true"), .init(name: "session_kind", value: "chat,discussion")], as: RunsPage.self)
            let fresh = page.items.filter { seen.insert($0.runId).inserted }; rows += fresh
            guard page.hasMore ?? (page.items.count == pageSize) else { return rows }
            guard !fresh.isEmpty else { throw GatewayError.invalidResponse }
            offset += page.items.count
        }
    }

    public func searchSessions(_ query: String, limit: Int) async throws -> SessionSearchPage {
        try JSONDecoder().decode(SessionSearchPage.self, from: try await request(
            "GET", "api/gateway/sessions/search", query: [.init(name: "q", value: query), .init(name: "limit", value: String(limit))], timeout: 30))
    }

    public func tools() async throws -> [ToolInfo] {
        let page = try await get("api/gateway/discovery/tools", as: ToolsPage.self)
        guard page.error?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty != false else {
            throw GatewayError.http(status: 503, body: "{\"detail\":\"Your gateway’s tools could not be loaded. Try again before sending.\"}")
        }
        return page.items
    }

    // MARK: Starting a turn

    public func startRun(prompt: String, sessionId: String?, toolPolicy: RunToolPolicy?, tools: [String]?, workflow: WorkflowChoice?, primaryImage: MediaItem?) async throws -> String {
        try await startRun(StartRunRequest(prompt: prompt, sessionId: sessionId, toolPolicy: toolPolicy, tools: tools, system: AssistantPersona.watch,
                                           workflow: workflow, primaryImage: primaryImage))
    }
    public func startRun(prompt: String, sessionId: String?, toolPolicy: RunToolPolicy?) async throws -> String {
        try await startAssistantRun(prompt: prompt, sessionId: sessionId, attachments: [], selection: nil, toolPolicy: toolPolicy)
    }
    public func startRun(prompt: String, sessionId: String?, attachments: [JSONValue]) async throws -> String {
        try await startAssistantRun(prompt: prompt, sessionId: sessionId, attachments: attachments, selection: nil, toolPolicy: nil)
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
    /// The iPhone's turn: the account's Assistant workflow, the tools it may use (on every turn, as the
    /// tray), the person's files and the image an edit starts from.
    private func startAssistantRun(prompt: String, sessionId: String?, attachments: [JSONValue], selection: ConversationTools?, toolPolicy: RunToolPolicy?, primaryImage: JSONValue? = nil) async throws -> String {
        var body = try AssistantWorkflow.request(prompt: prompt, sessionId: sessionId, toolPolicy: toolPolicy, preferences: try await accountPreferences())
        let inventory = try await tools()
        let catalog = Dictionary(inventory.map { ($0.name, $0) }, uniquingKeysWith: { _, latest in latest })
        let available = Set(catalog.values.filter(\.offered).map(\.name))
        let allowed: [String]
        if let selection {
            let current = ConversationTools(modes: selection.modes.filter { available.contains($0.key) })
            allowed = current.allowed; body.inputData.runtime?.toolPolicy = current.policy
        } else {
            // Discovery approval defaults are not workflow Tools-pin defaults. Like the
            // tray, supply the actual enabled list on every turn, including inheritance.
            allowed = catalog.values.filter {
                $0.offered && !["off", "disabled"].contains($0.approvalDefault?.lowercased() ?? "")
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

    public func accountPreferences() async throws -> JSONValue { try await get("api/gateway/accounts/me/preferences", as: JSONValue.self) }
    public func setAssistantWorkflow(_ value: String?) async throws -> JSONValue {
        let data = try await request("PUT", "api/gateway/accounts/me/preferences", body: JSONValue.object(["default_workflow": .object([WorkflowChoice.assistantInterface: value.map(JSONValue.string) ?? .null])]))
        return try JSONDecoder().decode(JSONValue.self, from: data)
    }

    public func messageStats(runID: String) async throws -> MessageStats? {
        do { return try await get("api/gateway/runs/\(runID)/message-stats", as: MessageStats.self) }
        catch GatewayError.http(status: 404, body: _) { return nil }
    }

    // MARK: A conversation's media and files

    public func sessionMedia(sessionId: String) async throws -> [String: [MediaItem]] {
        MediaItem.bySession(try await get("api/gateway/sessions/\(sessionId)/artifacts", query: [.init(name: "limit", value: "500")], as: JSONValue.self))
    }

    public func mediaData(_ item: MediaItem) async throws -> Data {
        try await artifactData(runId: item.runId, artifactId: item.artifactId, sizeBytes: item.sizeBytes)
    }

    public func sessionFiles(sessionId: String, folderRunId: String?) async throws -> SessionFiles {
        async let kept = get("api/gateway/sessions/\(sessionId)/artifacts", query: [.init(name: "limit", value: "500")], as: JSONValue.self)
        async let folder = folderFiles(runId: folderRunId)
        let (more, truncated) = try await folder
        return SessionFiles.of(try await kept).adding(more, truncated: truncated)
    }

    /// The files of a conversation's folder: only one the gateway made for the conversation (or the
    /// run), never a folder of the person's own. None when there is no folder yet or the gateway
    /// refuses it (gone, blocked, outside the account's folders): the conversation's other files
    /// still show. A read that cannot get through is a failure, as any other.
    private func folderFiles(runId: String?) async throws -> ([SessionFile], Bool) {
        guard let runId else { return ([], false) }
        guard MediaItem.safe(runId) else { throw GatewayError.invalidResponse }
        do {
            let folder = try await get("api/gateway/runs/\(runId)/workspace", as: JSONValue.self)
            guard ["session", "run"].contains(folder["kind"]?.stringValue ?? ""), folder["exists"] != .bool(false) else { return ([], false) }
            let page = try await get("api/gateway/runs/\(runId)/workspace/files",
                                     query: [.init(name: "recursive", value: "true"), .init(name: "limit", value: "500")], as: JSONValue.self)
            return (SessionFiles.folder(page, runId: runId), page["truncated"] == .bool(true))
        } catch let error where !Self.isTransient(error) {
            if case GatewayError.http = error { return ([], false) }
            throw error
        }
    }

    public func fileData(_ file: SessionFile) async throws -> Data {
        guard let path = file.folderPath else {
            return try await artifactData(runId: file.runId, artifactId: file.artifactId, sizeBytes: file.sizeBytes)
        }
        guard MediaItem.safe(file.runId) else { throw GatewayError.invalidResponse }
        if let size = file.sizeBytes, size > MediaItem.byteLimit { throw GatewayError.invalidResponse }
        let data = try await request("GET", "api/gateway/runs/\(file.runId)/workspace/content", query: [.init(name: "path", value: path)], timeout: 120)
        guard data.count <= MediaItem.byteLimit else { throw GatewayError.invalidResponse }
        return data
    }

    private func artifactData(runId: String, artifactId: String, sizeBytes: Int?) async throws -> Data {
        guard MediaItem.safe(runId), MediaItem.safe(artifactId) else { throw GatewayError.invalidResponse }
        if let size = sizeBytes, size > MediaItem.byteLimit { throw GatewayError.invalidResponse }
        let data = try await request("GET", "api/gateway/runs/\(runId)/artifacts/\(artifactId)/content", timeout: 120)
        guard data.count <= MediaItem.byteLimit else { throw GatewayError.invalidResponse }
        return data
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
        try await artifactPage(sessionID: sessionId, offset: 0, includeVoice: true).items
    }
    public func artifactPage(sessionID: String, offset: Int, includeVoice: Bool) async throws -> SessionArtifactPage {
        let v = try await get("api/gateway/sessions/\(sessionID)/artifacts", query: [.init(name: "limit", value: "500"), .init(name: "offset", value: String(offset)), .init(name: "include_voice", value: includeVoice ? "true" : "false")], as: JSONValue.self)
        guard case .array(let items)? = v["items"] else { throw GatewayError.invalidResponse }
        let total: Int; if case .number(let n)? = v["total"], n >= 0, n < Double(Int.max) { total = Int(n) } else { total = items.count }
        return .init(items: items.compactMap(PhoneArtifact.parse), total: total, hasMore: v["has_more"] == .bool(true), nextOffset: offset + items.count,
            warnings: { if case .array(let rows)? = v["warnings"] { return rows.compactMap(\.stringValue) }; return [] }())
    }
    public func workspace(runID: String) async throws -> RunWorkspace {
        guard PhoneArtifact.validID(runID) else { throw GatewayError.invalidResponse }
        return try await get("api/gateway/runs/\(runID)/workspace", as: RunWorkspace.self)
    }
    public func workspaceFiles(runID: String, path: String, recursive: Bool, limit: Int?) async throws -> WorkspaceListing {
        guard PhoneArtifact.validID(runID), WorkspaceEntry.validPath(path) else { throw GatewayError.invalidResponse }
        var query = [URLQueryItem(name: "path", value: path), .init(name: "recursive", value: recursive ? "true" : "false")]
        if let limit { query.append(.init(name: "limit", value: String(limit))) }
        return try await get("api/gateway/runs/\(runID)/workspace/files", query: query, as: WorkspaceListing.self)
    }
    public func downloadWorkspaceFile(runID: String, entry: WorkspaceEntry, to destination: URL) async throws {
        guard PhoneArtifact.validID(runID), WorkspaceEntry.validPath(entry.path), !entry.isDirectory else { throw GatewayError.invalidResponse }
        guard (entry.size ?? 0) <= PhoneArtifact.previewByteLimit else { throw PhoneAttachmentError.previewTooLarge }
        var parts = URLComponents(url: baseURL.appending(path: "api/gateway/runs/\(runID)/workspace/content"), resolvingAgainstBaseURL: false)!
        parts.queryItems = [.init(name: "path", value: entry.path)]
        guard let url = parts.url else { throw GatewayError.invalidResponse }
        try await writeDownload(to: destination) { handle in
            try await self.readFile(url: url, limit: PhoneArtifact.previewByteLimit) { try handle.write(contentsOf: $0) }
        }
    }
    public func download(_ artifact: PhoneArtifact) async throws -> Data {
        var data = Data()
        try await readArtifact(artifact, limit: PhoneArtifact.byteLimit) { data.append($0) }
        return data
    }
    public func download(_ artifact: PhoneArtifact, to destination: URL) async throws {
        try await writeDownload(to: destination) { handle in
            try await self.readArtifact(artifact, limit: PhoneArtifact.previewByteLimit) { try handle.write(contentsOf: $0) }
        }
    }
    private func writeDownload(to destination: URL, operation: (FileHandle) async throws -> Void) async throws {
        guard destination.isFileURL, !FileManager.default.fileExists(atPath: destination.path),
              FileManager.default.createFile(atPath: destination.path, contents: nil) else { throw GatewayError.invalidResponse }
        var handle: FileHandle?
        do {
            let opened = try FileHandle(forWritingTo: destination); handle = opened
            try await operation(opened); try opened.close()
        } catch {
            try? handle?.close(); try? FileManager.default.removeItem(at: destination); throw error
        }
    }
    private func readArtifact(_ artifact: PhoneArtifact, limit: Int, consume: (Data) throws -> Void) async throws {
        try requireSignIn()
        guard PhoneArtifact.validID(artifact.runId), PhoneArtifact.validID(artifact.artifactId) else { throw GatewayError.invalidResponse }
        guard artifact.size <= limit else { throw limit == PhoneArtifact.byteLimit ? PhoneAttachmentError.tooLarge : PhoneAttachmentError.previewTooLarge }
        // Only Gateway-owned routes receive credentials. Stream large previews to disk in chunks.
        try await readFile(url: baseURL.appending(path: "api/gateway/runs/\(artifact.runId)/artifacts/\(artifact.artifactId)/content"), limit: limit, consume: consume)
    }
    private func readFile(url: URL, limit: Int, consume: (Data) throws -> Void) async throws {
        try requireSignIn()
        var req = URLRequest(url: url); req.timeoutInterval = 120
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

    // MARK: Waits and automations

    /// Answers a wait. The run is re-read first: if it no longer waits on the same key, the wait
    /// was handled elsewhere and nothing is sent (a stale approval must never resume another step).
    public func answer(_ wait: Wait, with answer: WaitAnswer) async throws {
        let current = try await run(id: wait.runId)
        guard current.status == "waiting", current.waiting?.waitKey == wait.waitKey else { throw GatewayError.alreadyHandled }
        _ = try await request("POST", "api/gateway/commands", body: ResumeCommand(runId: wait.runId, waitKey: wait.waitKey, answer: answer))
    }

    /// The slow call on a public gateway (~7 s of server time, more over a watch's radio): 60 s.
    public func automations() async throws -> [AutomationSummary] {
        try JSONDecoder().decode(AutomationsPage.self, from: try await request("GET", "api/gateway/automations", timeout: 60)).items
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

    public func automationDefaults() async throws -> AutomationDefaults {
        try await get("api/gateway/automations/defaults", as: AutomationDefaults.self)
    }

    public func archivedAutomations() async throws -> [AutomationSummary] {
        try JSONDecoder().decode(AutomationsPage.self, from: try await request(
            "GET", "api/gateway/automations", query: [.init(name: "archived_only", value: "true")], timeout: 60)).items
    }

    public func discussAutomation(id: String, occurrenceIndex: Int, prompt: String) async throws -> Discussion {
        struct Body: Encodable { let request_id: String; let occurrence_index: Int; let prompt: String }
        let data = try await request("POST", "api/gateway/automations/\(id)/discuss",
                                     body: Body(request_id: UUID().uuidString.lowercased(), occurrence_index: occurrenceIndex, prompt: prompt), timeout: 60)
        return try JSONDecoder().decode(Discussion.self, from: data)
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
        WorkflowChoice.choices(from: try await get("api/gateway/bundles", query: interface.isEmpty ? [] : [.init(name: "executable_for", value: interface)], as: JSONValue.self),
                               interface: interface)
    }

    public func conversationWorkflows() async throws -> [WorkflowChoice] {
        async let agents = workflows(forInterface: WorkflowChoice.agentInterface)
        async let assistant = workflows(forInterface: WorkflowChoice.assistantInterface)
        return WorkflowChoice.conversation(agents: try await agents, assistant: try await assistant)
    }

    public func workflowInputs(_ w: WorkflowChoice) async throws -> WorkflowInputs {
        let v = try await get("api/gateway/bundles/\(w.bundleId)/flows/\(w.flowId)/input_schema",
                              query: [.init(name: "bundle_version", value: w.bundleVersion)], as: JSONValue.self)
        guard let inputs = WorkflowInputs.parse(v) else { throw GatewayError.invalidResponse }
        return inputs
    }

    /// A gateway without per-tool automation policies refuses one (422 naming `tool_policy`).
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

    public func occurrences(automationId: String, limit: Int) async throws -> [LastOccurrence] {
        // Full answers: 6 of them take 7 s on a public gateway, more over a watch's radio.
        try await get("api/gateway/automations/\(automationId)/occurrences", query: [.init(name: "limit", value: String(limit))], as: OccurrencesPage.self, timeout: 60).items
    }

    public func markSeen(automationId: String, cursor: String) async throws {
        _ = try await request("POST", "api/gateway/automations/\(automationId)/seen", body: SeenRequest(attentionCursor: cursor))
    }

    // MARK: Entities

    public func entities() async throws -> [EntitySummary] {
        try await get("api/gateway/entities", as: EntitiesPage.self).entities
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

    public func openEntityChat(name: String) async throws -> String {
        let data = try await request("POST", "api/gateway/entities/\(name)/chat/open", body: ChatOpenRequest())
        return try JSONDecoder().decode(ChatOpenResponse.self, from: data).chatId
    }

    public func entityChatTurn(name: String, chatId: String, text: String) async throws -> String {
        let data = try await request("POST", "api/gateway/entities/\(name)/chat/\(chatId)/turn", body: ChatTurnRequest(text: text))
        return try JSONDecoder().decode(ChatTurnResponse.self, from: data).reply ?? ""
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
        let policy: JSONValue = .object(["modes": tools.map { .object($0.modes.mapValues { .string($0.visitValue) }) } ?? .null])
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
        let body: JSONValue = tools.map { .object(["modes": .object($0.modes.mapValues { .string($0.visitValue) })]) } ?? .object(["modes": .null])
        _ = try await request("PUT", "api/gateway/entities/\(name)/visit/\(runID)/tool-policy", body: body)
    }
    public func answerEntity(name: String, runID: String, waitKey: String, approved: Bool) async throws -> EntitySessionState {
        struct Body: Encodable { var wait_key: String; var approved: Bool }
        let data = try await request("POST", "api/gateway/entities/\(name)/visit/\(runID)/decision", body: Body(wait_key: waitKey, approved: approved), timeout: 120)
        return try JSONDecoder().decode(EntitySessionState.self, from: data)
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

    // MARK: A run's steps

    public func ledger(runId: String, after: Int) async throws -> LedgerPage {
        try await get("api/gateway/runs/\(runId)/ledger", query: [.init(name: "after", value: String(after))], as: LedgerPage.self)
    }

    public func activity(runId: String, after: Int) async throws -> ActivityPage {
        try JSONDecoder().decode(ActivityPage.self, from: try await request(
            "GET", "api/gateway/runs/\(runId)/ledger", query: [.init(name: "after", value: String(after)), .init(name: "limit", value: "25")],
            timeout: 30))
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

    // MARK: Email and voice

    public func emailStatus() async throws -> EmailStatus { try await get("api/gateway/me/email", as: EmailStatus.self) }

    public func voiceCatalog() async throws -> VoiceCatalog {
        // `compact`: the items without the engines' duplicated source catalogs (a shared voice pack
        // made the full listing 1.4 MB, 250 KB compact, the same voices: measured on a 0.16.0 gateway).
        async let v = get("api/gateway/voice/voices", query: [.init(name: "compact", value: "true")], as: JSONValue.self)
        async let t = get("api/gateway/audio/transcriptions/models", as: JSONValue.self)
        return VoiceCatalog.parse(voices: try await v, transcription: try await t)
    }

    public func transcribe(wav: Data, sessionId: String) async throws -> String { try await transcribe(wav: wav, sessionId: sessionId, model: nil) }
    /// The recording is kept under `voice/dictation/` (the reserved upload namespace): a conversation's
    /// files tell the person's spoken questions from the files they gave.
    public func transcribe(wav: Data, sessionId: String, model: TranscriptionChoice?) async throws -> String {
        if lockedOut { throw GatewayError.unauthorized }
        let boundary = "watch-" + UUID().uuidString
        var body = Data()
        func field(_ name: String, _ value: String) {
            body.append(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(name)\"\r\n\r\n\(value)\r\n".utf8))
        }
        field("session_id", sessionId); field("content_type", "audio/wav"); field("filename", "ask.wav"); field("source_path", "voice/dictation/" + UUID().uuidString.lowercased() + ".wav")
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
