import Foundation

public enum ToolMode: String, Codable, CaseIterable, Sendable {
    case off, auto, approve
    public var label: String { switch self { case .off: "Off"; case .auto: "Auto"; case .approve: "Approve" } }
}

/// An explicit whitelist: omitted names and Off entries cannot run.
public struct ConversationTools: Codable, Equatable, Sendable {
    public var modes: [String: ToolMode]
    public init(modes: [String: ToolMode]) { self.modes = modes }
    public var allowed: [String] { modes.filter { $0.value != .off }.keys.sorted() }
    public var policy: RunToolPolicy {
        .init(requireApprovalTools: modes.filter { $0.value == .approve }.keys.sorted(),
              autoApproveTools: modes.filter { $0.value == .auto }.keys.sorted())
    }
}

public struct MessageStats: Codable, Equatable, Sendable {
    public var wallTimeSeconds: Double?
    public var inputTokens: Int?
    public var outputTokens: Int?
    public var toolCalls: Int?
    public init(wallTimeSeconds: Double? = nil, inputTokens: Int? = nil, outputTokens: Int? = nil, toolCalls: Int? = nil) {
        self.wallTimeSeconds = wallTimeSeconds; self.inputTokens = inputTokens; self.outputTokens = outputTokens; self.toolCalls = toolCalls
    }
    enum CodingKeys: String, CodingKey { case wallTimeSeconds = "wall_time_seconds", inputTokens = "input_tokens", outputTokens = "output_tokens", toolCalls = "tool_calls" }
}

public struct EntitySessionState: Decodable, Sendable {
    public var runID: String
    public var status: String
    public var turn: Int
    public var reply: String?
    public var pendingWait: RunWaiting?
    public var stats: MessageStats?
    public var readyForInput: Bool?
    public var turnComplete: Bool?
    public var error: String?
    enum CodingKeys: String, CodingKey { case runID = "run_id", status, turn = "turn_n", reply, pendingWait = "pending_wait", stats, turnComplete = "turn_complete", readyForInput = "ready_for_input", error }
    public var personWait: Wait? {
        RunSummary(runId: runID, workflowId: nil, status: status, waiting: pendingWait).personWait
    }
    public var finishedTurn: Bool { readyForInput == true || turnComplete == true || reply != nil || ["completed", "failed", "cancelled"].contains(status) }
}

public extension GatewayClient {
    func supportsConversationTools() async throws -> Bool { isMock }
    func automationDefaults() async throws -> Int? { nil }
    func messageStats(runID: String) async throws -> MessageStats? { nil }
    func entityTools(name: String) async throws -> [ToolInfo] { throw PhoneAttachmentError.unsupported }
    func openEntitySession(name: String, sessionID: String, tools: ConversationTools?) async throws -> EntitySessionState { throw PhoneAttachmentError.unsupported }
    func sendEntityTurn(name: String, runID: String, text: String) async throws -> JSONValue { throw PhoneAttachmentError.unsupported }
    func endEntitySession(name: String, runID: String) async throws { throw PhoneAttachmentError.unsupported }
    func entitySession(name: String, runID: String) async throws -> EntitySessionState { throw PhoneAttachmentError.unsupported }
    func setEntityTools(name: String, runID: String, tools: ConversationTools?) async throws { throw PhoneAttachmentError.unsupported }
    func answerEntity(name: String, runID: String, waitKey: String, approved: Bool) async throws -> EntitySessionState { throw PhoneAttachmentError.unsupported }
    func startRun(prompt: String, sessionId: String?, attachments: [JSONValue], tools: ConversationTools?) async throws -> String {
        guard tools == nil else { throw PhoneAttachmentError.unsupported }
        return try await startRun(prompt: prompt, sessionId: sessionId, attachments: attachments)
    }
}
