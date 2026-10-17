import Foundation
import CryptoKit

public enum PhoneAttachmentError: Error, LocalizedError {
    case tooLarge, unsupported
    public var errorDescription: String? { switch self {
    case .tooLarge: "Choose a file smaller than 25 MB."
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
    public var id: String { runId + ":" + artifactId }
    public var ref: JSONValue { .object(["$artifact": .string(artifactId), "run_id": .string(runId), "filename": .string(filename), "content_type": .string(contentType)]) }
    public init(artifactId: String, runId: String, filename: String, contentType: String, size: Int = 0) {
        self.artifactId = artifactId; self.runId = runId; self.filename = Self.safeFilename(filename); self.contentType = contentType; self.size = size
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
        let size: Int; if case .number(let n)? = v["size_bytes"] { size = n <= 0 ? 0 : (!n.isFinite || n > Double(Self.byteLimit) ? Self.byteLimit + 1 : Int(n)) } else { size = 0 }
        return PhoneArtifact(artifactId: id, runId: owner, filename: v["filename"]?.stringValue ?? v["tags"]?["filename"]?.stringValue ?? "Attachment", contentType: v["content_type"]?.stringValue ?? "application/octet-stream", size: size)
    }
    static func upload(_ v: JSONValue, filename: String, contentType: String, size: Int) -> PhoneArtifact? {
        let ref = v["artifact"] ?? v["attachment"]
        guard let id = ref?["$artifact"]?.stringValue, let owner = v["run_id"]?.stringValue ?? ref?["run_id"]?.stringValue, validID(id), validID(owner) else { return nil }
        return PhoneArtifact(artifactId: id, runId: owner, filename: filename, contentType: contentType, size: size)
    }
}

// Older test clients may supply the original voice methods. Live implements all overrides.
public extension GatewayClient {
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
