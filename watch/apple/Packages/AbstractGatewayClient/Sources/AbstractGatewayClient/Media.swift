import Foundation

/// An image, a recording or a video a run made (the Assistant's workflow generates them), shown
/// with the answer. Its bytes come from the gateway's own artifact route, never from a URL the
/// model wrote.
public struct MediaItem: Hashable, Sendable, Identifiable, Codable {
    public enum Kind: String, Sendable, Codable { case image, audio, video }

    public var artifactId: String
    /// The run that owns it (the download route is scoped to it).
    public var runId: String
    public var contentType: String
    public var kind: Kind
    public var sizeBytes: Int?
    public var id: String { artifactId }

    /// The most the watch downloads for one item.
    public static let byteLimit = 25 * 1024 * 1024

    public init(artifactId: String, runId: String, contentType: String, kind: Kind, sizeBytes: Int? = nil) {
        self.artifactId = artifactId; self.runId = runId; self.contentType = contentType; self.kind = kind
        self.sizeBytes = sizeBytes
    }

    static func kind(of contentType: String) -> Kind? {
        let t = contentType.lowercased()
        if t.hasPrefix("image/") { return .image }
        if t.hasPrefix("audio/") { return .audio }
        if t.hasPrefix("video/") { return .video }
        return nil
    }

    /// Ids go into a URL path: letters, digits, `-` and `_` only.
    static func safe(_ id: String) -> Bool {
        !id.isEmpty && id.count <= 128 && id.allSatisfy { $0.isASCII && ($0.isLetter || $0.isNumber || $0 == "-" || $0 == "_") }
    }

    /// One `$artifact` reference (`{"$artifact": id, "content_type": …}`), owned by `run` unless it
    /// names its own run.
    static func ref(_ v: JSONValue?, run: String, contentType fallback: String? = nil) -> MediaItem? {
        guard let v, let id = v["$artifact"]?.stringValue ?? v["artifact_id"]?.stringValue,
              let type = v["content_type"]?.stringValue ?? fallback, let kind = kind(of: type) else { return nil }
        let owner = v["run_id"]?.stringValue ?? run
        guard safe(id), safe(owner) else { return nil }
        let size: Int? = if case .number(let n)? = v["size_bytes"] { Int(n) } else { nil }
        return MediaItem(artifactId: id, runId: owner, contentType: type, kind: kind, sizeBytes: size)
    }

    /// What a finished run's output carries: `outputs.{image,voice,…}[].artifact_ref`, and the
    /// media ends' `artifact`, `image_artifact`, `audio_artifact`, `video_artifact`, `music_artifact`.
    public static func of(output: JSONValue?, runId: String) -> [MediaItem] {
        guard let output else { return [] }
        var found: [MediaItem] = []
        if case .object(let outputs)? = output["outputs"] {
            for key in outputs.keys.sorted() {
                guard case .array(let items)? = outputs[key] else { continue }
                for item in items {
                    if let m = ref(item["artifact_ref"], run: runId, contentType: item["content_type"]?.stringValue) ?? ref(item, run: runId) {
                        found.append(m)
                    }
                }
            }
        }
        for key in ["artifact", "image_artifact", "audio_artifact", "video_artifact", "music_artifact"] {
            if let m = ref(output[key], run: runId, contentType: output["content_type"]?.stringValue) { found.append(m) }
        }
        var seen = Set<String>()
        return found.filter { seen.insert($0.artifactId).inserted }
    }

    /// `GET /sessions/{id}/artifacts`: the generated media of a conversation, by the turn (run) that
    /// made it. A piece made inside an agent's own run is also listed under its parent run.
    public static func bySession(_ page: JSONValue) -> [String: [MediaItem]] {
        guard case .array(let rows)? = page["items"] else { return [:] }
        var out: [String: [MediaItem]] = [:]
        for row in rows {
            guard row["tags"]?["kind"]?.stringValue == "generated_media",
                  let run = row["run_id"]?.stringValue, let m = ref(row, run: run) else { continue }
            for key in Set([run, row["parent_run_id"]?.stringValue].compactMap { $0 }) where !(out[key] ?? []).contains(m) {
                out[key, default: []].append(m)
            }
        }
        return out
    }
}
