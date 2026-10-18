import Foundation
import CryptoKit

public enum PhoneAttachmentError: Error, LocalizedError {
    case tooLarge, previewTooLarge, unsupported
    public var errorDescription: String? { switch self {
    case .tooLarge: "Choose a file smaller than 25 MB."
    case .previewTooLarge: "This file is larger than the 256 MB in-app preview limit."
    case .unsupported: "This connection does not support that action."
    } }
}

public struct PhoneArtifact: Identifiable, Hashable, Sendable {
    public static let byteLimit = 25 * 1024 * 1024
    public var artifactId: String
    public var runId: String
    public var filename: String
    public var contentType: String
    public var size: Int
    /// Logical gateway path, independent of the safe local preview basename.
    public var sourcePath: String? = nil
    public var purpose: String? = nil
    public var producer: JSONValue? = nil
    public var sourceRefs: [JSONValue] = []
    public var semanticKind: String? = nil
    public var sourceOrigin: String? = nil
    public var isConversationVoice: Bool = false
    public var inferredConversationVoice: Bool = false
    public static let previewByteLimit = 256 * 1024 * 1024
    public var id: String { runId + ":" + artifactId }
    public var ref: JSONValue { .object(["$artifact": .string(artifactId), "run_id": .string(runId), "filename": .string(filename), "content_type": .string(contentType)]) }
    public init(artifactId: String, runId: String, filename: String, contentType: String, size: Int = 0) {
        self.artifactId = artifactId; self.runId = runId; self.filename = Self.previewFilename(filename, contentType: contentType); self.contentType = contentType; self.size = size
    }
    public static func safeFilename(_ value: String) -> String {
        let last = value.replacingOccurrences(of: "\\", with: "/").split(separator: "/").last.map(String.init) ?? "Attachment"
        let clean = last.unicodeScalars.filter { CharacterSet.alphanumerics.union(CharacterSet(charactersIn: " ._-()")).contains($0) }.map(String.init).joined()
        return clean.isEmpty || clean == "." || clean == ".." ? "Attachment" : String(clean.prefix(160))
    }
    public static func validID(_ s: String) -> Bool { !s.isEmpty && s != "." && s != ".." && s.unicodeScalars.allSatisfy { CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "_-.")).contains($0) } }
    public static func parse(_ v: JSONValue) -> PhoneArtifact? {
        guard let id = v["artifact_id"]?.stringValue ?? v["$artifact"]?.stringValue,
              let owner = v["run_id"]?.stringValue ?? v["ref"]?["run_id"]?.stringValue,
              validID(id), validID(owner) else { return nil }
        let size: Int; if case .number(let n)? = v["size_bytes"] { size = n <= 0 ? 0 : (!n.isFinite || n >= Double(Int.max) ? Int.max : Int(n)) } else { size = 0 }
        let mime = v["content_type"]?.stringValue ?? "application/octet-stream"
        let path = v["source_path"]?.stringValue ?? v["tags"]?["source_path"]?.stringValue ?? v["tags"]?["path"]?.stringValue
        let named = [v["filename"]?.stringValue, v["tags"]?["filename"]?.stringValue, path?.replacingOccurrences(of: "\\", with: "/").split(separator: "/").last.map(String.init)]
            .compactMap { $0 }.first { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
        let kind = v["semantic_kind"]?.stringValue
        let label = mime.hasPrefix("image/") ? "Image" : mime.hasPrefix("audio/") ? "Audio" : mime.hasPrefix("video/") ? "Video" : mime.hasPrefix("text/") ? "Document" : "File"
        let fallback = label + "-" + String(id.prefix(8)) + (mime.hasPrefix("text/markdown") ? ".md" : mime.hasPrefix("text/plain") ? ".txt" : "")
        var artifact = PhoneArtifact(artifactId: id, runId: owner, filename: Self.previewFilename(named ?? fallback, contentType: mime, kind: kind), contentType: mime, size: size)
        artifact.sourcePath = path
        artifact.purpose = v["tags"]?["purpose"]?.stringValue ?? v["purpose"]?.stringValue
        artifact.producer = v["producer"] ?? v["descriptor"]?["producer"]
        if case .array(let refs)? = v["source_refs"] ?? v["descriptor"]?["source_refs"] { artifact.sourceRefs = refs }
        artifact.semanticKind = kind
        artifact.sourceOrigin = v["tags"]?["source"]?.stringValue ?? v["source"]?.stringValue
        let legacyStream = v["metadata"]?["capability_metadata"]?["stream"]?["chunk_format"]?.stringValue
            ?? v["raw_metadata"]?["capability_metadata"]?["stream"]?["chunk_format"]?.stringValue
        let legacyPlayback = v["tags"]?["kind"]?.stringValue == "generated_media"
            && v["tags"]?["modality"]?.stringValue == "voice" && v["tags"]?["task"]?.stringValue == "tts" && legacyStream == "wav-segment"
        artifact.isConversationVoice = artifact.purpose == "voice_playback" || legacyPlayback || artifact.isDictationSource
        return artifact
    }
    static func upload(_ v: JSONValue, filename: String, contentType: String, size: Int) -> PhoneArtifact? {
        let ref = v["artifact"] ?? v["attachment"]
        guard let id = ref?["$artifact"]?.stringValue, let owner = v["run_id"]?.stringValue ?? ref?["run_id"]?.stringValue, validID(id), validID(owner) else { return nil }
        return PhoneArtifact(artifactId: id, runId: owner, filename: filename, contentType: contentType, size: size)
    }
}

// Older test clients may supply the original voice methods. Live implements all overrides.
public extension GatewayClient {
    func startRun(prompt: String, sessionId: String?, attachments: [JSONValue], tools: ConversationTools?, primaryImage: JSONValue?) async throws -> String {
        var refs = attachments
        if let primaryImage, !refs.contains(primaryImage) { refs.append(primaryImage) }
        return try await startRun(prompt: prompt, sessionId: sessionId, attachments: refs, tools: tools)
    }
    func download(_ artifact: PhoneArtifact, to destination: URL) async throws {
        let data = try await download(artifact)
        try data.write(to: destination, options: .withoutOverwriting)
    }

    func voiceCatalog() async throws -> VoiceCatalog { throw PhoneAttachmentError.unsupported }
    func accountPreferences() async throws -> JSONValue { throw PhoneAttachmentError.unsupported }
    func setAssistantWorkflow(_ value: String?) async throws -> JSONValue { throw PhoneAttachmentError.unsupported }
    func startRun(prompt: String, sessionId: String?, attachments: [JSONValue]) async throws -> String {
        guard attachments.isEmpty else { throw PhoneAttachmentError.unsupported }
        return try await startRun(prompt: prompt, sessionId: sessionId, toolPolicy: nil)
    }
    func upload(data: Data, filename: String, contentType: String, sessionId: String) async throws -> PhoneArtifact { throw PhoneAttachmentError.unsupported }
    func artifacts(sessionId: String) async throws -> [PhoneArtifact] { [] }
    func download(_ artifact: PhoneArtifact) async throws -> Data { throw PhoneAttachmentError.unsupported }
    nonisolated func speech(text: String, scope: SpeechScope, voice: VoiceChoice?) -> AsyncThrowingStream<Data, Error> { speech(text: text, scope: scope) }
    func transcribe(wav: Data, sessionId: String, model: TranscriptionChoice?) async throws -> String { try await transcribe(wav: wav, sessionId: sessionId) }
}

public enum PhoneSession {
    public static func owner(_ session: String) -> String {
        let candidate = "session_memory_" + session.trimmingCharacters(in: .whitespacesAndNewlines)
        if !session.isEmpty && candidate.unicodeScalars.allSatisfy({ CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "_-")).contains($0) && $0.isASCII }) { return candidate }
        let digest = SHA256.hash(data: Data(session.trimmingCharacters(in: .whitespacesAndNewlines).utf8)).map { String(format: "%02x", $0) }.joined()
        return "session_memory_sha_" + digest.prefix(32)
    }
}
