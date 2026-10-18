import Foundation
import AbstractGatewayClient

public struct RunActivityItem: Identifiable, Equatable, Sendable {
    public enum Kind: String, Sendable { case model, tool, result, wait, failure }
    public enum Status: String, Sendable { case running, completed, waiting, failed, cancelled }
    public var id: String
    public var runID: String
    public var kind: Kind
    public var title: String
    public var detail: String
    public var status: Status
    public var timestamp: Date?
}

/// A bounded projection of durable ledger events. Cursors belong to individual runs.
/// Model prompts, reasoning fields and tool arguments are deliberately never rendered.
public struct RunActivity: Sendable {
    public private(set) var items: [RunActivityItem] = []
    public private(set) var modelCalls = 0
    public private(set) var toolCalls = 0
    public private(set) var cycleCount = 0
    public private(set) var lastEventAt: Date?
    public private(set) var wasTrimmed = false
    private var cursors: [String: Int] = [:]
    private var countedModels: Set<String> = []
    private var countedTools: Set<String> = []
    public init() {}

    public mutating func ingest(_ record: LedgerRecord, runID: String, cursor: Int) {
        guard cursor > (cursors[runID] ?? -1) else { return }
        cursors[runID] = cursor
        guard record.effectType != "resume", record.result?["resumed"] != .bool(true) else { return }
        let step = record.stepId ?? "cursor-\(cursor)"
        let base = runID + ":" + step
        let timestamp = (record.endedAt ?? record.startedAt).flatMap(ISO8601.date)
        let status: RunActivityItem.Status = switch record.status {
        case "completed": .completed
        case "failed", "cancelled": .failed
        case "waiting": .waiting
        default: .running
        }
        if let timestamp { lastEventAt = max(lastEventAt ?? timestamp, timestamp) }
        if status != .waiting {
            for index in items.indices where items[index].runID == runID && items[index].kind == .wait && items[index].status == .waiting {
                items[index].status = .completed
            }
        }
        if record.effectType == "llm_call" {
            if countedModels.insert(base).inserted {
                modelCalls += 1
                if record.nodeId?.lowercased() == "reason" { cycleCount += 1 }
            }
            put(.init(id: base + ":model", runID: runID, kind: .model,
                      title: record.nodeId?.lowercased() == "reason" ? "Agent cycle" : "Model call",
                      detail: "", status: status, timestamp: timestamp))
        }
        if record.effectType == "tool_calls" {
            let calls = array(record.effect?["payload"]?["tool_calls"])
            let results = array(record.result?["results"])
            for (index, call) in calls.enumerated() {
                guard let name = call["name"]?.stringValue, !name.isEmpty else { continue }
                let uid = identity(call)
                let key = runID + ":tool:" + (uid ?? (step + ":\(index)"))
                if countedTools.insert(key).inserted { toolCalls += 1 }
                var result = uid.flatMap { id in results.first { identity($0) == id } }
                if result == nil, let callID = call["call_id"]?.stringValue {
                    let matches = results.filter { $0["call_id"]?.stringValue == callID }
                    if matches.count == 1 { result = matches[0] }
                }
                if result == nil, results.count == calls.count { result = results[index] }
                let error = result?["error"]?.stringValue
                let failed = result?["success"] == .bool(false) || (error?.isEmpty == false)
                let detail = error ?? publicOutput(result?["output"])
                put(.init(id: key, runID: runID, kind: .tool, title: name.replacingOccurrences(of: "_", with: " "),
                          detail: bounded(detail), status: failed ? .failed : status, timestamp: timestamp))
            }
        }
        if let wait = record.result?["wait"], wait["reason"]?.stringValue != "subworkflow" {
            let key = wait["wait_key"]?.stringValue ?? ""
            let reason = wait["reason"]?.stringValue ?? ""
            let title = key.hasPrefix("tool_approval:") ? "Approval needed" : reason == "job" ? "Waiting for job" : reason == "event" ? "Waiting for event" : "Waiting"
            // Wait details can include internal tool arguments. Only the public prompt is shown.
            put(.init(id: base + ":wait", runID: runID, kind: .wait, title: title,
                      detail: bounded(wait["prompt"]?.stringValue ?? ""), status: .waiting, timestamp: timestamp))
        }
        if status == .failed {
            put(.init(id: base + ":failure", runID: runID, kind: .failure, title: "Step failed",
                      detail: bounded(record.error ?? record.result?["error"]?.stringValue ?? "The step did not complete."),
                      status: .failed, timestamp: timestamp))
        }
    }

    public mutating func finish(status: String) {
        for index in items.indices where items[index].status == .running || items[index].status == .waiting {
            items[index].status = status == "cancelled" ? .cancelled : status == "failed" ? .failed : .completed
        }
    }
    private mutating func put(_ item: RunActivityItem) {
        if let index = items.firstIndex(where: { $0.id == item.id }) {
            var updated = item
            if updated.detail.isEmpty { updated.detail = items[index].detail }
            if updated.timestamp == nil { updated.timestamp = items[index].timestamp }
            items[index] = updated
        } else { items.append(item) }
        while items.count > 250 {
            // Keep actionable waits and failures ahead of old successful history.
            let index = items.firstIndex { $0.status == .completed } ?? 0
            items.remove(at: index); wasTrimmed = true
        }
    }
    private func array(_ value: JSONValue?) -> [JSONValue] { if case .array(let values) = value { values } else { [] } }
    private func identity(_ value: JSONValue) -> String? {
        for key in ["runtime_call_id", "call_uid"] {
            if let id = value[key]?.stringValue, !id.isEmpty { return id }
        }
        return nil
    }
    private func publicOutput(_ value: JSONValue?) -> String {
        guard let value, value != .null else { return "" }
        if let text = value.stringValue { return text }
        // Structured outputs expose an explicitly rendered public summary when supplied.
        for key in ["rendered", "text", "content", "answer"] {
            if let text = value[key]?.stringValue { return text }
        }
        return scrub(value).displayText
    }
    private func scrub(_ value: JSONValue) -> JSONValue {
        switch value {
        case .object(let object):
            return .object(object.filter {
                !$0.key.hasPrefix("_") && !["reasoning", "messages", "system", "prompt", "api_key", "token", "authorization", "password"].contains($0.key.lowercased())
            }.mapValues(scrub))
        case .array(let values): return .array(values.map(scrub))
        default: return value
        }
    }
    private func bounded(_ text: String) -> String {
        let marker = "\n[Truncated for display]"
        guard text.count > 4000 else { return text }
        return String(text.prefix(4000 - marker.count)) + marker
    }
}
