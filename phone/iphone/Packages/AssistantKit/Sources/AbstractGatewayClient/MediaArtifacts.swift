import Foundation

public extension RunSummary {
    /// Artifact references returned by the workflow, never URLs embedded in model prose.
    var mediaArtifacts: [PhoneArtifact] {
        var found: [PhoneArtifact] = [], inferredOwners: [Bool] = []
        let containers = ["artifact", "artifact_ref", "image_artifact", "audio_artifact", "music_artifact", "video_artifact",
                          "image_artifacts", "video_artifacts", "artifacts", "outputs", "resources", "items",
                          "image", "video", "audio", "voice", "sound", "music", "media"]
        func visit(_ value: JSONValue, depth: Int, metadata: [String: JSONValue] = [:]) {
            guard depth < 12 else { return }
            if case .array(let items) = value { for item in items { visit(item, depth: depth + 1, metadata: metadata) }; return }
            guard case .object(let source) = value else { return }
            var inherited = metadata
            for key in ["content_type", "filename", "semantic_kind", "size_bytes", "run_id", "tags"] {
                if let value = source[key], value != .null { inherited[key] = value }
            }
            var row = source
            for (key, value) in inherited where row[key] == nil || row[key] == .null { row[key] = value }
            let ownID = source["artifact_id"]?.stringValue ?? source["$artifact"]?.stringValue
            // Some generated-item wrappers repeat artifact_id but its reference owns the bytes.
            if let nested = source["artifact_ref"], let owner = nested["run_id"],
               ownID == (nested["$artifact"]?.stringValue ?? nested["artifact_id"]?.stringValue) { row["run_id"] = owner }
            let inferred = row["run_id"] == nil
            if inferred { row["run_id"] = .string(runId) }
            if let artifact = PhoneArtifact.parse(.object(row)) {
                if let index = found.indices.first(where: {
                    found[$0].artifactId == artifact.artifactId && (found[$0].runId == artifact.runId || inferredOwners[$0] || inferred)
                }) {
                    let old = found[index]
                    if (!inferred && inferredOwners[index]) || (artifact.contentType != "application/octet-stream" && old.contentType == "application/octet-stream") {
                        var richer = artifact
                        if inferred && !inferredOwners[index] { richer.runId = old.runId }
                        found[index] = richer; inferredOwners[index] = inferredOwners[index] && inferred
                    }
                } else { found.append(artifact); inferredOwners.append(inferred) }
            }
            for key in containers { if let child = source[key] { visit(child, depth: depth + 1, metadata: inherited) } }
        }
        if let output { visit(output, depth: 0) }
        return found
    }
}

public extension PhoneArtifact {
    var isImage: Bool { contentType.lowercased().hasPrefix("image/") }
    var isAudio: Bool { contentType.lowercased().hasPrefix("audio/") }
    var isVideo: Bool { contentType.lowercased().hasPrefix("video/") }
    var symbol: String { isImage ? "photo" : isAudio ? "waveform" : isVideo ? "video" : "doc" }
    static func previewFilename(_ filename: String?, contentType: String, kind: String? = nil) -> String {
        let mime = contentType.lowercased().split(separator: ";").first.map(String.init) ?? contentType
        let suffix = ["image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/heic": "heic", "image/gif": "gif",
                      "audio/wav": "wav", "audio/x-wav": "wav", "audio/wave": "wav", "audio/mpeg": "mp3", "audio/mp3": "mp3",
                      "audio/mp4": "m4a", "audio/aac": "aac", "audio/flac": "flac", "audio/ogg": "ogg", "video/mp4": "mp4", "video/quicktime": "mov"][mime]
        let fallback = mime.hasPrefix("image/") ? "Image" : mime.hasPrefix("video/") ? "Video" : mime.hasPrefix("audio/") ? (kind == "music" ? "Music" : kind == "sound" ? "Sound" : "Voice") : "Attachment"
        let name = safeFilename(filename?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false ? filename! : fallback)
        return (name as NSString).pathExtension.isEmpty && suffix != nil ? name + "." + suffix! : name
    }
}

/// Persisted input uses the existing run input_data route, including the person's image sources.
public struct ConversationInput: Sendable {
    public var prompt: String?
    public var attachments: [PhoneArtifact]
    public init(prompt: String?, attachments: [PhoneArtifact] = []) { self.prompt = prompt; self.attachments = attachments }
}
public extension GatewayClient {
    func input(ofRun id: String) async throws -> ConversationInput { try await .init(prompt: prompt(ofRun: id)) }
}
