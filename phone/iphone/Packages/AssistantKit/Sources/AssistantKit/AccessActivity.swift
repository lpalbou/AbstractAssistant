import Foundation
import AbstractGatewayClient

public enum AccessKind: String, CaseIterable, Identifiable, Sendable {
    case filesRead, filesChanged, searches, pages
    public var id: String { rawValue }
}
public struct AccessLink: Equatable, Sendable {
    public var title: String
    public var url: String
    public var snippet: String
    public var canOpen: Bool
}
public struct AccessEvent: Identifiable, Equatable, Sendable {
    public var id: String
    public var mode: String
    public var target: String
    public var preview: String
    public var timestamp: Date?
    public var links: [AccessLink]
}
public struct AccessEntry: Identifiable, Equatable, Sendable {
    public var id: String
    public var kind: AccessKind
    public var target: String
    public var runID: String
    public var operations: Int
    public var events: [AccessEvent]
}

/// Positive evidence only. Discovery results and opaque shell commands are not file/page reads.
public struct AccessActivity: Sendable {
    public private(set) var entries: [AccessEntry] = []
    private var counted: [AccessKind: Set<String>] = [:]
    private var seenEvents: Set<String> = []
    private var arguments: [String: JSONValue] = [:]
    public init() {}
    public func count(_ kind: AccessKind) -> Int { counted[kind]?.count ?? 0 }
    public func items(_ kind: AccessKind) -> [AccessEntry] { entries.filter { $0.kind == kind } }
    public mutating func ingest(name: String, key: String, runID: String, status: String?, call: JSONValue, result: JSONValue?, timestamp: Date?) {
        let supported: Set<String> = ["read_file", "skim_files", "write_file", "edit_file", "web_search", "skim_websearch", "skim_url", "fetch_url"]
        guard supported.contains(name) else { return }
        if let object = SentEmail.object(call["arguments"])?.objectValue {
            let allowed: Set<String> = ["file_path", "paths", "start_line", "end_line", "start_char", "mode", "preview_only", "query", "url", "method", "include_full_content"]
            arguments[key] = .object((arguments[key]?.objectValue ?? [:]).merging(object.filter { allowed.contains($0.key) }) { _, new in new })
        }
        guard status == "completed" || status == "failed" else { return }
        let args = arguments.removeValue(forKey: key)
        guard status == "completed", result?["success"] != .bool(false), result?["error"]?.stringValue?.isEmpty != false,
              let raw = result?["output"] else { return }
        let object = SentEmail.object(raw)
        guard object?["success"] != .bool(false), object?["error"] == nil || object?["error"] == .null || object?["error"] == .string("") else { return }
        let text = raw.stringValue ?? object?["rendered"]?.stringValue ?? ""
        func field(_ name: String) -> String { args?[name]?.stringValue ?? "" }
        func filePath(_ block: String) -> String? {
            capture(#"^File: (.+) \([0-9]+ lines\)(?: — skim[^\n]*)?(?:\n|$)"#, block) ?? capture(#"^File: (.+?) — FINAL PART"#, block) ?? capture(#"^File: ([^\n]+)\n#TRUNCATION:"#, block)
        }
        switch name {
        case "read_file", "skim_files":
            let blocks = name == "skim_files" ? text.components(separatedBy: "\n\n---\n\n") : [text]
            for (index, block) in blocks.enumerated() {
                guard let path = filePath(block) else { continue }
                if name == "skim_files", let firstBody = block.components(separatedBy: "\n\n").dropFirst().first?.trimmingCharacters(in: .whitespacesAndNewlines), firstBody.hasPrefix("Error:") { continue }
                let target = path
                let mode = name == "skim_files" ? "Skim" : (args?["start_line"] != nil || args?["end_line"] != nil || args?["start_char"] != nil ? "Range read" : "Read")
                put(kind: .filesRead, target: target, source: runID + ":" + target, runID: runID, event: event(key + ":\(index)", mode, name == "read_file" ? field("file_path") : target, block, timestamp))
            }
        case "write_file":
            guard text.hasPrefix("✅ Successfully written to ") || text.hasPrefix("✅ Successfully appended to "), !field("file_path").isEmpty else { return }
            let path = capture(#"^✅ Successfully (?:written to|appended to) '(.+)' \("#, text) ?? field("file_path")
            put(kind: .filesChanged, target: path, source: runID + ":" + path, runID: runID,
                event: event(key, text.hasPrefix("✅ Successfully appended") ? "Appended" : "Written", field("file_path"), text, timestamp))
        case "edit_file":
            guard args?["preview_only"] != .bool(true), args?["preview_only"] != .string("true"),
                  text.hasPrefix("Edited "), !field("file_path").isEmpty else { return }
            let path = capture(#"^Edited (.+) \(\+[0-9]+ -[0-9]+\)"#, text) ?? field("file_path")
            put(kind: .filesChanged, target: path, source: runID + ":" + path, runID: runID,
                event: event(key, "Edited", field("file_path"), text, timestamp))
        case "web_search", "skim_websearch":
            guard object?["success"] == .bool(true) else { return }
            let query = object?["query"]?.stringValue ?? field("query")
            guard !query.isEmpty else { return }
            var links: [AccessLink] = []
            if case .array(let rows) = object?["results"] {
                links = rows.prefix(30).compactMap { row in
                    guard let url = row["url"]?.stringValue ?? row["href"]?.stringValue ?? row["link"]?.stringValue else { return nil }
                    let title = row["title"]?.stringValue ?? url, snippet = row["snippet"]?.stringValue ?? row["body"]?.stringValue ?? ""
                    return AccessLink(title: title.count > 500 ? String(title.prefix(500)) + "…" : title,
                        url: url.count > 8192 ? String(url.prefix(8192)) + " [URL truncated; link disabled]" : url,
                        snippet: snippet.count > 2000 ? String(snippet.prefix(2000)) + "…" : snippet, canOpen: url.count <= 8192)
                }
            }
            let count = object?["results"].flatMap { if case .array(let rows) = $0 { rows.count } else { nil } } ?? 0
            var e = event(key, name == "skim_websearch" ? "Skim search" : "Search", query, "\(count) \(count == 1 ? "result" : "results") returned. Search links are leads, not opened pages." + (count > 30 ? " Showing the first 30 links." : ""), timestamp); e.links = links
            put(kind: .searches, target: query, source: key, runID: runID, event: e)
        case "skim_url":
            guard text.hasPrefix("🌐 URL Skim\nURL:"), let headerEnd = text.range(of: "\nContent-Type:") else { return }
            let header = String(text[..<headerEnd.lowerBound])
            guard let code = capture(#"(?m)^Status: ([0-9]{3})"#, header).flatMap(Int.init), (200..<300).contains(code) else { return }
            let url = capture(#"(?m)^Final URL: (.+)$"#, header) ?? capture(#"(?m)^URL: (.+)$"#, header) ?? field("url")
            guard !url.isEmpty else { return }
            put(kind: .pages, target: url, source: url, runID: runID, event: event(key, "Skim · HTTP \(code)", field("url"), text, timestamp))
        case "fetch_url":
            guard object?["success"] == .bool(true) else { return }
            let url = object?["final_url"]?.stringValue ?? object?["url"]?.stringValue ?? field("url")
            guard !url.isEmpty else { return }
            let method = field("method").isEmpty ? "GET" : field("method").uppercased()
            let preview = object?["rendered"]?.stringValue ?? object?["content"]?.stringValue ?? object?["content"]?["text"]?.stringValue ?? "The request completed; no recorded text preview is available."
            put(kind: .pages, target: url, source: url, runID: runID, event: event(key, method + (args?["include_full_content"] == .bool(false) ? " · Fetch preview" : " · Fetch"), field("url"), preview, timestamp))
        default: break
        }
    }
    private func capture(_ pattern: String, _ text: String) -> String? {
        guard let expression = try? NSRegularExpression(pattern: pattern), let match = expression.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)), let range = Range(match.range(at: 1), in: text) else { return nil }
        return String(text[range])
    }
    private func event(_ id: String, _ mode: String, _ target: String, _ preview: String, _ timestamp: Date?) -> AccessEvent {
        .init(id: id, mode: mode, target: target, preview: preview.count > 8000 ? String(preview.prefix(8000)) + "\n[Truncated for display]" : preview, timestamp: timestamp, links: [])
    }
    private mutating func put(kind: AccessKind, target: String, source: String, runID: String, event: AccessEvent) {
        guard seenEvents.insert(kind.rawValue + ":" + event.id).inserted else { return }
        let id = kind.rawValue + ":" + source
        counted[kind, default: []].insert(id)
        if let index = entries.firstIndex(where: { $0.id == id }) {
            entries[index].operations += 1; entries[index].events.append(event)
            if entries[index].events.count > 5 { entries[index].events.removeFirst() }
        } else { entries.append(.init(id: id, kind: kind, target: target, runID: runID, operations: 1, events: [event])) }
        let kindIndices = entries.indices.filter { entries[$0].kind == kind }
        if kindIndices.count > 100 { entries.remove(at: kindIndices[0]) }
    }
}
