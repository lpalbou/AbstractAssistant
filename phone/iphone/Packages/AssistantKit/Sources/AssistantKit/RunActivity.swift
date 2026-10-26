import Foundation
import AbstractGatewayClient

public struct RunActivityItem: Identifiable, Equatable, Sendable {
    public enum Kind: String, Sendable { case model, tool, result, wait, failure, workflow }
    public enum Status: String, Sendable { case running, completed, waiting, failed, cancelled }
    public var id: String
    public var runID: String
    public var kind: Kind
    public var title: String
    public var detail: String
    public var status: Status
    public var timestamp: Date?
    public var startedAt: Date? = nil
    public var endedAt: Date? = nil
    public var nodeID: String? = nil
    public var provider: String? = nil
    public var model: String? = nil
    public var inputTokens: Int? = nil
    public var outputTokens: Int? = nil
    public var finishReason: String? = nil
    public var outputLabel: String = "Result"
    public var inputText: String? = nil
    public var toolName: String? = nil
    public var cycleID: String? = nil
    public var isToolApproval = false
    public var cycleOrdinal: Int? = nil
    public var isAgentCycle: Bool { kind == .model && nodeID?.lowercased() == "reason" }
    public var duration: TimeInterval? {
        guard let startedAt, let endedAt, endedAt >= startedAt else { return nil }
        return endedAt.timeIntervalSince(startedAt)
    }
}

/// A bounded projection of durable ledger events. Cursors belong to individual runs.
/// Model prompts and reasoning are never rendered. Tool inputs are structured,
/// recursively credential-redacted and bounded separately from their public outputs.
public struct RunActivity: Sendable {
    public private(set) var items: [RunActivityItem] = []
    public private(set) var modelCalls = 0
    public private(set) var toolCalls = 0
    public private(set) var cycleCount = 0
    public private(set) var lastEventAt: Date?
    public private(set) var wasTrimmed = false
    public private(set) var access = AccessActivity()
    public private(set) var sentEmails: [SentEmail] = []
    public private(set) var sentEmailCount = 0
    public private(set) var readEmails: [ReadEmail] = []
    public private(set) var readEmailCount = 0
    private var countedReadEmails: Set<String> = []
    private var readEmailArguments: [String: JSONValue] = [:]
    private var countedEmails: Set<String> = []
    private var emailArguments: [String: JSONValue] = [:]
    private var cursors: [String: Int] = [:]
    private var cycleOrdinalsByRun: [String: Int] = [:]
    private var latestCycleByRun: [String: String] = [:]
    private var countedModels: Set<String> = []
    private var countedTools: Set<String> = []
    public init() {}

    public mutating func ingest(_ record: LedgerRecord, runID: String, cursor: Int) {
        guard cursor > (cursors[runID] ?? -1) else { return }
        cursors[runID] = cursor
        if record.effectType == "resume" || record.result?["resumed"] == .bool(true) {
            let resumedAt = (record.startedAt ?? record.endedAt).flatMap(ISO8601.date)
            for index in items.indices where items[index].runID == runID && items[index].nodeID == record.nodeId && items[index].kind == .wait && items[index].status == .waiting {
                items[index].status = .completed
                items[index].title = items[index].title == "Approval needed" ? "Approval resolved" : "Wait ended"
                items[index].endedAt = resumedAt
            }
            // The runtime resumes a subworkflow with a new step ID. Close its existing
            // boundary row rather than exposing internal resume bookkeeping as a step.
            if let index = items.lastIndex(where: { $0.runID == runID && $0.nodeID == record.nodeId && $0.kind == .workflow && $0.status == .running }) {
                items[index].status = .completed
                items[index].endedAt = record.endedAt.flatMap(ISO8601.date)
            }
            return
        }
        let step = record.stepId ?? "cursor-\(cursor)"
        let base = runID + ":" + step
        let timestamp = (record.endedAt ?? record.startedAt).flatMap(ISO8601.date)
        let status: RunActivityItem.Status = switch record.status {
        case "completed": .completed
        case "failed": .failed
        case "cancelled": .cancelled
        case "waiting": .waiting
        default: .running
        }
        if let timestamp { lastEventAt = max(lastEventAt ?? timestamp, timestamp) }
        if status != .waiting {
            for index in items.indices where items[index].runID == runID && items[index].kind == .wait && items[index].status == .waiting {
                items[index].status = .completed
                items[index].title = items[index].title == "Approval needed" ? "Approval resolved" : "Wait ended"
                items[index].endedAt = (record.startedAt ?? record.endedAt).flatMap(ISO8601.date)
            }
        }
        if record.effectType == "llm_call" {
            let firstModel = countedModels.insert(base).inserted
            if firstModel {
                modelCalls += 1
                if record.nodeId?.lowercased() == "reason" { cycleCount += 1; cycleOrdinalsByRun[runID, default: 0] += 1; latestCycleByRun[runID] = base + ":model" }
            }
            put(.init(id: base + ":model", runID: runID, kind: .model,
                      title: modelTitle(record), detail: modelOutput(record), status: status, timestamp: timestamp,
                      cycleOrdinal: record.nodeId?.lowercased() == "reason" ? (firstModel ? cycleOrdinalsByRun[runID] : items.first { $0.id == base + ":model" }?.cycleOrdinal) : nil), record: record)
        }
        if record.effectType == "start_subworkflow" {
            put(.init(id: base + ":workflow", runID: runID, kind: .workflow,
                      title: record.nodeId == "assistant_agent" ? "Assistant workflow" : "Run subworkflow",
                      detail: "", status: status == .waiting ? .running : status, timestamp: timestamp), record: record)
        }
        if record.effectType == "tool_calls" {
            let calls = array(record.effect?["payload"]?["tool_calls"])
            let results = array(record.result?["results"])
            for (index, call) in calls.enumerated() {
                guard let name = call["name"]?.stringValue, !name.isEmpty else { continue }
                let uid = identity(call)
                let key = runID + ":tool:" + (uid ?? (step + ":\(index)"))
                let firstTool = countedTools.insert(key).inserted
                if firstTool { toolCalls += 1 }
                var result = uid.flatMap { id in results.first { identity($0) == id } }
                if result == nil, let callID = call["call_id"]?.stringValue {
                    let matches = results.filter { $0["call_id"]?.stringValue == callID && (uid == nil || identity($0) == nil) }
                    if matches.count == 1 { result = matches[0] }
                }
                if result == nil, results.count == calls.count, results.allSatisfy({ identity($0) == nil && $0["call_id"] == nil }) { result = results[index] }
                access.ingest(name: name, key: key, runID: runID, status: record.status, call: call, result: result, timestamp: timestamp)
                if name == "send_email" || name == "reply_email" {
                    if let args = SentEmail.object(call["arguments"]), let object = args.objectValue, !object.isEmpty {
                        let fields: Set<String> = ["to", "cc", "bcc", "subject", "body_text", "body_html", "attachments"]
                        var saved = object.filter { fields.contains($0.key) }
                        for field in ["body_text", "body_html"] {
                            if let text = saved[field]?.stringValue { saved[field] = .string(SentEmail.bounded(text)) }
                        }
                        emailArguments[key] = .object((emailArguments[key]?.objectValue ?? [:]).merging(saved) { _, new in new })
                    }
                    if record.status == "completed", let mail = SentEmail.confirmed(key: key, name: name, arguments: emailArguments[key], result: result, timestamp: timestamp) {
                        if countedEmails.insert(mail.id).inserted { sentEmailCount += 1; sentEmails.append(mail) }
                        else if let index = sentEmails.firstIndex(where: { $0.id == mail.id }), sentEmails[index].body.isEmpty && !mail.body.isEmpty { sentEmails[index] = mail }
                        if sentEmails.count > 100 { sentEmails.removeFirst(sentEmails.count - 100) }
                        emailArguments[key] = nil
                    } else if record.status == "completed" || record.status == "failed" { emailArguments[key] = nil }
                }
                if name == "read_email" {
                    if let args = SentEmail.object(call["arguments"]), let object = args.objectValue {
                        let saved = object.filter { ["account", "mailbox", "uid"].contains($0.key) }
                        readEmailArguments[key] = .object((readEmailArguments[key]?.objectValue ?? [:]).merging(saved) { _, new in new })
                    }
                    if record.status == "completed", let mail = ReadEmail.confirmed(arguments: readEmailArguments[key], result: result, timestamp: timestamp) {
                        if countedReadEmails.insert(mail.id).inserted { readEmailCount += 1; readEmails.append(mail) }
                        else if let index = readEmails.firstIndex(where: { $0.id == mail.id }), readEmails[index].body.isEmpty && !mail.body.isEmpty { readEmails[index] = mail }
                        if readEmails.count > 100 { readEmails.removeFirst(readEmails.count - 100) }
                        readEmailArguments[key] = nil
                    } else if record.status == "completed" || record.status == "failed" { readEmailArguments[key] = nil }
                }
                let error = result?["error"]?.stringValue
                let failed = result?["success"] == .bool(false) || (error?.isEmpty == false)
                let detail = error ?? publicOutput(result?["output"])
                put(.init(id: key, runID: runID, kind: .tool, title: name.replacingOccurrences(of: "_", with: " "),
                          detail: bounded(detail), status: failed ? .failed : status, timestamp: timestamp,
                          inputText: ToolCallInput.display(call["arguments"]), toolName: name,
                          cycleID: firstTool ? latestCycleByRun[runID] : items.first { $0.id == key }?.cycleID), record: record)
            }
        }
        if let wait = record.result?["wait"], wait["reason"]?.stringValue != "subworkflow" {
            let key = wait["wait_key"]?.stringValue ?? ""
            let reason = wait["reason"]?.stringValue ?? ""
            let title = key.hasPrefix("tool_approval:") ? "Approval needed" : reason == "job" ? "Waiting for job" : reason == "event" ? "Waiting for event" : "Waiting"
            // Wait details can include internal tool arguments. Only the public prompt is shown.
            put(.init(id: base + ":wait", runID: runID, kind: .wait, title: title,
                      detail: bounded(wait["prompt"]?.stringValue ?? ""), status: .waiting, timestamp: timestamp,
                      isToolApproval: key.hasPrefix("tool_approval:")), record: record)
        }
        if status == .failed {
            put(.init(id: base + ":failure", runID: runID, kind: .failure, title: "Step failed",
                      detail: bounded(record.error ?? record.result?["error"]?.stringValue ?? "The step did not complete."),
                      status: .failed, timestamp: timestamp), record: record)
        }
    }

    public mutating func finish(status: String) {
        for index in items.indices where items[index].status == .running || items[index].status == .waiting {
            items[index].status = status == "cancelled" ? .cancelled : status == "failed" ? .failed : .completed
            if items[index].kind == .wait && status == "completed" {
                items[index].title = items[index].title == "Approval needed" ? "Approval resolved" : "Wait ended"
            }
        }
    }
    private mutating func put(_ value: RunActivityItem, record: LedgerRecord) {
        var item = value
        item.startedAt = (item.kind == .wait ? (record.endedAt ?? record.startedAt) : record.startedAt).flatMap(ISO8601.date)
        if item.status != .waiting && item.status != .running { item.endedAt = record.endedAt.flatMap(ISO8601.date) }
        item.nodeID = record.nodeId
        if item.kind == .wait { item.cycleID = latestCycleByRun[item.runID] }
        if item.isAgentCycle { item.cycleID = item.id }
        if item.kind == .model {
            let result = record.result
            item.provider = result?["route"]?["provider"]?.stringValue ?? record.effect?["payload"]?["provider"]?.stringValue
            item.model = result?["route"]?["served_model"]?.stringValue ?? result?["model"]?.stringValue ?? record.effect?["payload"]?["model"]?.stringValue
            item.inputTokens = tokens(result?["usage"]?["input_tokens"] ?? result?["usage"]?["prompt_tokens"])
            item.outputTokens = tokens(result?["usage"]?["output_tokens"] ?? result?["usage"]?["completion_tokens"])
            item.finishReason = result?["finish_reason"]?.stringValue
            item.outputLabel = record.nodeId == "route_call" ? "Routing decision" : result?["data"] != nil && result?["data"] != .null ? "Structured output" : "Public output"
        }
        if let index = items.firstIndex(where: { $0.id == item.id }) {
            var updated = item
            if updated.detail.isEmpty { updated.detail = items[index].detail }
            let old = items[index]
            if updated.timestamp == nil { updated.timestamp = old.timestamp }
            updated.startedAt = [old.startedAt, updated.startedAt].compactMap { $0 }.min()
            updated.endedAt = updated.endedAt ?? old.endedAt
            updated.nodeID = updated.nodeID ?? old.nodeID
            updated.inputText = updated.inputText ?? old.inputText
            updated.toolName = updated.toolName ?? old.toolName
            updated.cycleOrdinal = old.cycleOrdinal ?? updated.cycleOrdinal
            if updated.kind == .tool || updated.kind == .wait { updated.cycleID = old.cycleID }
            updated.isToolApproval = old.isToolApproval || updated.isToolApproval
            updated.provider = updated.provider ?? old.provider; updated.model = updated.model ?? old.model
            updated.inputTokens = updated.inputTokens ?? old.inputTokens; updated.outputTokens = updated.outputTokens ?? old.outputTokens
            items[index] = updated
        } else { items.append(item) }
        items.sort {
            let a = $0.startedAt ?? $0.timestamp, b = $1.startedAt ?? $1.timestamp
            if a != b { return (a ?? .distantFuture) < (b ?? .distantFuture) }
            if a == nil { return false } // Preserve ledger order when the gateway omitted times.
            return $0.id < $1.id
        }
        while items.count > 250 {
            // Keep actionable waits and failures ahead of old successful history.
            let index = items.firstIndex { $0.status == .completed } ?? 0
            items.remove(at: index); wasTrimmed = true
        }
    }
    private func tokens(_ value: JSONValue?) -> Int? {
        guard case .number(let n) = value, n.isFinite, n >= 0, n < Double(Int.max) else { return nil }
        return Int(n)
    }
    private func modelTitle(_ record: LedgerRecord) -> String {
        switch record.nodeId?.lowercased() {
        case "reason": return "Agent cycle"
        case "route_call": return "Choose response type"
        case "generate_voice": return "Generate voice"
        case "generate_image": return "Generate image"
        case "edit_image": return "Edit image"
        case "generate_music": return "Generate music"
        case "generate_sound": return "Generate sound"
        case "generate_video": return "Generate video"
        default: return "Model call"
        }
    }
    private func modelOutput(_ record: LedgerRecord) -> String {
        let result = record.result
        var text = ""
        if let data = result?["data"], data != .null {
            if record.nodeId == "route_call", let mode = data["mode"]?.stringValue {
                var lines = ["Response type: " + mode.replacingOccurrences(of: "_", with: " ")]
                for (key, label) in [("assistant_message", "Message"), ("media_prompt", "Generation prompt")] {
                    if let value = data[key]?.stringValue, !value.isEmpty { lines.append(label + ": " + value) }
                }
                if case .number(let seconds)? = data["seconds"] { lines.append("Requested length: \(seconds) s") }
                return bounded(lines.joined(separator: "\n\n"))
            }
            text = scrub(data).displayText
        } else { text = result?["content"]?.stringValue ?? result?["response"]?.stringValue ?? "" }
        let names = array(result?["tool_calls"]).compactMap { $0["name"]?.stringValue }
        if !names.isEmpty { text += (text.isEmpty ? "" : "\n\n") + "Requested tools: " + names.joined(separator: ", ") }
        let output = record.effect?["payload"]?["output"] ?? record.effect?["payload"]?["params"]?["output_spec"]
        if let modality = output?["modality"]?.stringValue {
            var request = "Requested output: " + modality
            if let task = output?["task"]?.stringValue { request += " · " + task.replacingOccurrences(of: "_", with: " ") }
            text = request + (text.isEmpty ? "" : "\n\n" + text)
            if record.status == "completed" {
                // The normalizer publishes generated attachments under result.outputs.
                // Completion alone is not proof of a stored attachment.
                let files = RunSummary(runId: "projection", workflowId: nil, status: "completed", output: result).mediaArtifacts
                text += files.isEmpty ? "\nStep completed. No stored media attachment was recorded in this event." : "\nStored media: " + files.map(\.filename).joined(separator: ", ")
            }
        }
        return bounded(text)
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
                !$0.key.hasPrefix("_") && !ToolCallInput.isCredential($0.key) && !["reasoning", "messages", "system", "prompt", "api_key", "token", "authorization", "password"].contains($0.key.lowercased())
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
