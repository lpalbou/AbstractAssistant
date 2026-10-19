import Foundation

/// One file of a conversation (`GET /sessions/{id}/artifacts`): what one of its turns made (an
/// image, a recording, a video) or was given (an attachment). The person's own spoken questions are
/// not files: they are uploads the gateway transcribed (a transcript names each as its source), and
/// are counted apart.
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
    public var id: String { artifactId }

    public init(artifactId: String, runId: String, contentType: String, name: String? = nil, sizeBytes: Int? = nil,
                createdAt: Date? = nil, origin: Origin) {
        self.artifactId = artifactId; self.runId = runId; self.contentType = contentType; self.name = name
        self.sizeBytes = sizeBytes; self.createdAt = createdAt; self.origin = origin
    }

    /// The media it is, when it is one (an image, a recording, a video: it opens on the watch).
    public var media: MediaItem? {
        MediaItem.kind(of: contentType).map { MediaItem(artifactId: artifactId, runId: runId, contentType: contentType, kind: $0, sizeBytes: sizeBytes) }
    }

    /// A file name to save it under: its own, else its kind and a short id with the right extension.
    public var fileName: String {
        if let name, !name.isEmpty { return name }
        let ext = contentType.split(separator: ";").first.flatMap { $0.split(separator: "/").last }.map(String.init) ?? "bin"
        let kind = MediaItem.kind(of: contentType).map(\.rawValue) ?? "file"
        return "\(kind)-\(artifactId.prefix(8)).\(ext == "plain" ? "txt" : ext == "quicktime" ? "mov" : ext)"
    }
}

/// A conversation's files, newest first, and how many questions were spoken.
public struct SessionFiles: Sendable, Hashable {
    public var files: [SessionFile]
    public var spokenQuestions: Int
    public init(files: [SessionFile], spokenQuestions: Int) { self.files = files; self.spokenQuestions = spokenQuestions }

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
}
