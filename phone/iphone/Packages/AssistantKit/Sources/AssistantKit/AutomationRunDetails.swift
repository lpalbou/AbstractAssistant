import Foundation
import AbstractGatewayClient

/// Presentation of a recorded occurrence. A provider's 401 is not a phone sign-in failure.
public struct AutomationRunExplanation: Sendable {
    public let title: String
    public let message: String
    public let nextStep: String?
    public let technicalDetail: String?
    public init(occurrence: LastOccurrence, runError: String? = nil, stepError: String? = nil) {
        let detail = [occurrence.failure?.message, runError, stepError].compactMap(Self.nonempty).first
        technicalDetail = detail
        let status = occurrence.status ?? "unknown"
        title = switch status {
        case "failed": "Run failed"
        case "waiting": "Needs you"
        case "backoff": "Retry scheduled"
        case "admitted", "running": "Working"
        case "completed": "Completed"
        case "cancelled": "Stopped"
        default: "Run details"
        }
        if status == "failed" {
            let lower = detail?.lowercased() ?? ""
            if lower.contains("401") && (lower.contains("airelays") || lower.contains("server api error") || lower.contains("provider")) {
                message = "The model provider rejected the gateway’s sign-in. Your iPhone is connected."
                nextStep = "Ask the gateway administrator to check the provider connection used by this automation, then try Run now. This error describes the recorded run."
            } else if lower.contains("404") && (lower.contains("server api error") || lower.contains("model provider")) {
                message = "The model provider could not find the requested endpoint or model."
                nextStep = "Ask the gateway administrator to check the provider endpoint and model used by this automation."
            } else if lower.contains("429") || lower.contains("rate limit") {
                message = "The model provider limited this request."
                nextStep = "Check the provider’s quota or wait before trying again."
            } else if lower.contains("timeout") || lower.contains("timed out") || lower.contains("connection refused") {
                message = "A service needed by this run did not respond."
                nextStep = "Check the gateway and provider connection before trying again."
            } else {
                message = detail ?? "The gateway marked this run as failed without an explanation."
                nextStep = detail == nil ? "Refresh the details to check its activity, or ask the gateway administrator to investigate using the run ID below." : "Review the recorded error and activity before running again."
            }
        } else {
            message = switch status {
            case "waiting": "This run is waiting for a response or tool approval."
            case "backoff": "The gateway will retry this run."
            case "running", "admitted": "The gateway is processing this task."
            case "cancelled": "This run was stopped before it finished."
            case "completed": Self.nonempty(occurrence.answer) == nil && Self.nonempty(occurrence.excerpt) == nil ? "The run completed without a text answer. Its activity may contain files or tool results." : "This run completed."
            default: "Open the recorded activity for more information."
            }
            nextStep = status == "waiting" ? "Open Inbox to review what the assistant needs." : nil
        }
    }
    public static func nonempty(_ text: String?) -> String? {
        guard let text = text?.trimmingCharacters(in: .whitespacesAndNewlines), !text.isEmpty else { return nil }
        return text
    }
}

extension LastOccurrence {
    public var displayAnswer: String? { AutomationRunExplanation.nonempty(answer) ?? AutomationRunExplanation.nonempty(excerpt) }
    public var attemptCount: Int? { attempts ?? failure?.attempts }
    public var isActive: Bool { ["admitted", "running", "waiting", "backoff"].contains(status ?? "") }
    public var occurrenceKey: String { index.map { "occurrence-\($0)" } ?? stableID }
    public var stableID: String { runId ?? "occurrence-\(index.map(String.init) ?? firedAt ?? "unknown")" }
}

public extension GatewayClient {
    /// The gateway's budget for an automation that builds on its earlier runs; nil from a gateway
    /// without `GET /automations/defaults` (404), never an invented value.
    func defaultGrowingMaxTokens() async throws -> Int? {
        do { return try await automationDefaults().growingMaxTokens } catch GatewayError.http(status: 404, body: _) { return nil }
    }
}
