import Foundation
import UniformTypeIdentifiers

/// One file of a conversation: what one of its turns made (an image, a recording, a video) or was
/// given (an attachment), kept with the conversation (`GET /sessions/{id}/artifacts`), or a file its
/// assistant wrote with a tool into the conversation's folder on the gateway
/// (`GET /runs/{id}/workspace/files`). The person's own spoken questions are not files: they are
/// uploads the gateway transcribed (a transcript names each as its source), and are counted apart.
public struct SessionFile: Identifiable, Hashable, Sendable {
    public enum Origin: String, Sendable { case made, attached }
    public var artifactId: String
    /// The run that owns it (the download route is scoped to it).
    public var runId: String
    public var contentType: String
    public var name: String?
    public var sizeBytes: Int?
    public var createdAt: Date?
    public var origin: Origin
    /// Where it is in the conversation's folder (relative to it), for a file written there; `runId`
    /// is then a run of the conversation, whose folder it is. Nil for what is kept with the conversation.
    public var folderPath: String?
    public var id: String { folderPath.map { "folder:" + $0 } ?? artifactId }

    public init(artifactId: String, runId: String, contentType: String, name: String? = nil, sizeBytes: Int? = nil,
                createdAt: Date? = nil, origin: Origin, folderPath: String? = nil) {
        self.artifactId = artifactId; self.runId = runId; self.contentType = contentType; self.name = name
        self.sizeBytes = sizeBytes; self.createdAt = createdAt; self.origin = origin; self.folderPath = folderPath
    }

    /// The media it is, when it is one the watch opens (an image, a recording, a video kept with the
    /// conversation; a file of its folder is shared, not opened).
    public var media: MediaItem? {
        guard folderPath == nil else { return nil }
        return MediaItem.kind(of: contentType).map { MediaItem(artifactId: artifactId, runId: runId, contentType: contentType, kind: $0, sizeBytes: sizeBytes) }
    }

    /// Small enough to be downloaded to the watch and shared from it.
    public var fitsTheWatch: Bool { (sizeBytes ?? 0) <= MediaItem.byteLimit }

    /// A file name to save it under: its own, else its kind and a short id with the right extension.
    public var fileName: String {
        if let name, !name.isEmpty { return (name as NSString).lastPathComponent }
        let ext = contentType.split(separator: ";").first.flatMap { $0.split(separator: "/").last }.map(String.init) ?? "bin"
        let kind = MediaItem.kind(of: contentType).map(\.rawValue) ?? "file"
        return "\(kind)-\(artifactId.prefix(8)).\(ext == "plain" ? "txt" : ext == "quicktime" ? "mov" : ext)"
    }
}

/// A conversation's files, newest first, and how many questions were spoken.
public struct SessionFiles: Sendable, Hashable {
    public var files: [SessionFile]
    public var spokenQuestions: Int
    /// The conversation's folder holds more than was listed.
    public var folderTruncated = false
    public init(files: [SessionFile], spokenQuestions: Int, folderTruncated: Bool = false) {
        self.files = files; self.spokenQuestions = spokenQuestions; self.folderTruncated = folderTruncated
    }

    public static func of(_ page: JSONValue) -> SessionFiles {
        guard case .array(let rows)? = page["items"] else { return SessionFiles(files: [], spokenQuestions: 0) }
        // The uploads the gateway transcribed: the person speaking (their transcripts name them).
        let spoken = Set(rows.compactMap { row -> String? in
            guard row["tags"]?["task"]?.stringValue == "stt" else { return nil }
            return row["tags"]?["source_audio_artifact"]?.stringValue
        })
        var files: [SessionFile] = []
        for row in rows {
            guard let id = row["artifact_id"]?.stringValue, let run = row["run_id"]?.stringValue,
                  MediaItem.safe(id), MediaItem.safe(run), !spoken.contains(id) else { continue }
            let origin: SessionFile.Origin
            switch row["tags"]?["kind"]?.stringValue {
            case "generated_media": origin = .made
            case "attachment": origin = .attached
            default: continue                                        // transcripts and other derived text
            }
            let size: Int? = if case .number(let n)? = row["size_bytes"] { Int(n) } else { nil }
            files.append(SessionFile(artifactId: id, runId: run, contentType: row["content_type"]?.stringValue ?? "application/octet-stream",
                                     name: row["filename"]?.stringValue, sizeBytes: size,
                                     createdAt: row["created_at"]?.stringValue.flatMap(ISO8601.date), origin: origin))
        }
        files.sort { ($0.createdAt ?? .distantPast) > ($1.createdAt ?? .distantPast) }
        return SessionFiles(files: files, spokenQuestions: spoken.count)
    }

    /// The files of the conversation's folder (`GET /runs/{run}/workspace/files?recursive=true`),
    /// sub-folders' included, named by their path in it; hidden files and folders (a leading dot)
    /// and caches (`__pycache__`, `node_modules`) are tools' own, not the conversation's files.
    public static func folder(_ page: JSONValue, runId: String) -> [SessionFile] {
        guard case .array(let entries)? = page["entries"] else { return [] }
        return entries.compactMap { e -> SessionFile? in
            guard e["type"]?.stringValue == "file", let path = e["path"]?.stringValue, !path.isEmpty,
                  !path.split(separator: "/").contains(where: { $0.hasPrefix(".") || $0 == "__pycache__" || $0 == "node_modules" })
            else { return nil }
            let ext = (path as NSString).pathExtension
            let type = UTType(filenameExtension: ext)?.preferredMIMEType ?? "application/octet-stream"
            let size: Int? = if case .number(let n)? = e["size_bytes"] { Int(n) } else { nil }
            return SessionFile(artifactId: "", runId: runId, contentType: type, name: path, sizeBytes: size,
                               createdAt: e["mtime"]?.stringValue.flatMap(ISO8601.date), origin: .made, folderPath: path)
        }
    }

    /// With the files of the conversation's folder too, newest first.
    public func adding(_ more: [SessionFile], truncated: Bool = false) -> SessionFiles {
        var all = files + more
        all.sort { ($0.createdAt ?? .distantPast) > ($1.createdAt ?? .distantPast) }
        return SessionFiles(files: all, spokenQuestions: spokenQuestions, folderTruncated: folderTruncated || truncated)
    }
}
