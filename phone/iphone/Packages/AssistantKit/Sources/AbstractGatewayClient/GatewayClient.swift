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
    /// `GET /api/gateway/me`
    func me() async throws -> Principal
    /// `GET /api/gateway/runs?status=waiting`, projected to waits on a person.
    func waits() async throws -> [Wait]
    /// `GET /api/gateway/runs?root_only=true&limit=20`
    func recentRuns(limit: Int) async throws -> [RunSummary]
    /// `GET /api/gateway/runs/{id}/input_data`: what the person asked in that turn.
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
    func entities() async throws -> [EntitySummary]
    /// `POST /api/gateway/entities/{name}/chat/open` → chat id (one live session per home).
    func openEntityChat(name: String) async throws -> String
    /// `POST /api/gateway/entities/{name}/chat/{chat_id}/turn` `{text}` → the reply.
    func entityChatTurn(name: String, chatId: String, text: String) async throws -> String
    /// `GET /api/gateway/runs/{id}/ledger?after=N` → records after the cursor.
    func ledger(runId: String, after: Int) async throws -> LedgerPage
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
}

/// Live client over URLSession: `Authorization: Bearer <token>`, or a gateway session from an
/// emailed sign-in code (`X-AbstractGateway-Session`, plus `X-AbstractGateway-CSRF` on writes).
public actor LiveGatewayClient: GatewayClient {
    public nonisolated let isMock = false
    private let baseURL: URL
    private let credential: GatewayCredential
    private let session: URLSession
    private var lockedOut = false
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

    public func prompt(ofRun id: String) async throws -> String? {
        try await get("api/gateway/runs/\(id)/input_data", as: RunInputData.self).inputData?.prompt
    }

    public func turns(ofSession id: String) async throws -> [RunSummary] {
        try await get("api/gateway/runs", query: [.init(name: "session_id", value: id), .init(name: "root_only", value: "true"),
                                                   .init(name: "limit", value: "30"), .init(name: "include_metrics", value: "true")],
                      as: RunsPage.self).items
    }

    /// The conversations' turns (chats and discussions; automations have their own screen), with metrics.
    public func recentRuns(limit: Int) async throws -> [RunSummary] {
        try await get("api/gateway/runs", query: [.init(name: "root_only", value: "true"), .init(name: "limit", value: String(limit)),
                                                   .init(name: "include_metrics", value: "true"), .init(name: "session_kind", value: "chat,discussion")],
                      as: RunsPage.self).items
    }

    public func run(id: String) async throws -> RunSummary { try await get("api/gateway/runs/\(id)", as: RunSummary.self) }

    public func tools() async throws -> [ToolInfo] {
        try await get("api/gateway/discovery/tools", as: ToolsPage.self).items
    }

    public func startRun(prompt: String, sessionId: String?, toolPolicy: RunToolPolicy?) async throws -> String {
        let preferences = try await get("api/gateway/accounts/me/preferences", as: JSONValue.self)
        let body = try AssistantWorkflow.request(prompt: prompt, sessionId: sessionId, toolPolicy: toolPolicy, preferences: preferences)
        let data = try await request("POST", "api/gateway/runs/start", body: body)
        return try JSONDecoder().decode(StartRunResponse.self, from: data).runId
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
        let data = try await request("POST", "api/gateway/automations", body: a.body, timeout: 60)
        return try JSONDecoder().decode(CreatedAutomation.self, from: data).summary
    }

    public func automationDefinition(id: String) async throws -> AutomationDefinition {
        try await get("api/gateway/automations/\(id)", as: AutomationDefinitionResponse.self).definition
    }

    public func reviseAutomation(id: String, changes: [String: JSONValue], expectedRevision: Int?) async throws {
        _ = try await request("PATCH", "api/gateway/automations/\(id)", body: Revise(expected_revision: expectedRevision, changes: changes))
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

    public func cancel(runId: String) async throws {
        _ = try await request("POST", "api/gateway/commands", body: CancelCommand(runId: runId))
    }

    public func occurrences(automationId: String, limit: Int) async throws -> [LastOccurrence] {
        try await get("api/gateway/automations/\(automationId)/occurrences", query: [.init(name: "limit", value: String(limit))], as: OccurrencesPage.self).items
    }

    public func markSeen(automationId: String, cursor: String) async throws {
        _ = try await request("POST", "api/gateway/automations/\(automationId)/seen", body: SeenRequest(attentionCursor: cursor))
    }

    public func transcribe(wav: Data, sessionId: String) async throws -> String {
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
                                    body: TranscribeRequest(audioArtifact: ["$artifact": id]), timeout: 120)
        return try JSONDecoder().decode(TranscribeResponse.self, from: out).text.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    public nonisolated func speech(text: String, scope: SpeechScope) -> AsyncThrowingStream<Data, Error> {
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
        req.httpBody = try? JSONEncoder().encode(SpeechRequest(text: text))
        let session = self.session
        let request = req
        return AsyncThrowingStream { continuation in
            let task = Task { @Sendable in
                do {
                    try await self.requireSignIn()
                    let (bytes, resp) = try await session.bytes(for: request)
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
