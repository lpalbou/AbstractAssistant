import Foundation
import Testing
import AbstractGatewayClient
@testable import AssistantKit

struct ConversationExportTests {
    private func storage() -> PhoneTemporaryStorage { .init(temporaryDirectory: FileManager.default.temporaryDirectory.appending(path: "export-test-" + UUID().uuidString)) }
    private func written(_ path: String) throws -> AnswerActivity {
        let json: JSONValue = .object(["step_id": .string("write"), "status": .string("completed"), "effect": .object(["type": .string("tool_calls"), "payload": .object(["tool_calls": .array([.object(["name": .string("write_file"), "runtime_call_id": .string("write"), "arguments": .object(["file_path": .string(path)])])])])]), "result": .object(["results": .array([.object(["runtime_call_id": .string("write"), "success": .bool(true), "output": .string("✅ Successfully written to '\(path)' (12 bytes, 1 lines)")])])])])
        var activity = RunActivity(); activity.ingest(try JSONDecoder().decode(LedgerRecord.self, from: JSONEncoder().encode(json)), runID: "child", cursor: 1)
        return .init(activity: activity)
    }
    @Test func repeatedImagesShareOneOriginalAndGeneratedFileStaysWithItsAnswer() async throws {
        let storage = storage(); defer { try? FileManager.default.removeItem(at: storage.temporaryDirectory) }
        let client = MockGatewayClient(mediaImage: Data("original-image".utf8))
        let image = PhoneArtifact(artifactId: "demo-image", runId: "root", filename: "Photo.png", contentType: "image/png")
        let messages: [ConversationMessage] = [.init(role: .user, text: "Use this", artifacts: [image]), .init(role: .assistant, text: "Saved **summary**", runID: "root", artifacts: [image])]
        let value = try await ConversationExportBuilder(storage: storage).prepare(messages: messages, responder: "Assistant", client: client, activities: ["root": try written("/demo/session/discussion-summary.md")])
        #expect(value.files.count == 2 && value.turns.count == 2)
        #expect(value.turns[0].fileIDs.count == 1 && value.turns[1].fileIDs.count == 2)
        #expect(value.turns[0].fileIDs[0] == value.turns[1].fileIDs[0])
        let document = try #require(value.files.first { $0.name == "discussion-summary.md" })
        #expect(try String(contentsOf: document.url, encoding: .utf8).contains("Discussion summary"))
        #expect(!value.files.contains { $0.name == "notes.md" }) // Unrelated workspace file never exported.
        try storage.discard(value.folder); #expect(!FileManager.default.fileExists(atPath: value.folder.path))
    }
    @Test func collisionsKeepBothOriginalsAndNamesCannotEscapeTheExport() async throws {
        let storage = storage(); defer { try? FileManager.default.removeItem(at: storage.temporaryDirectory) }
        let client = MockGatewayClient(mediaImage: Data("image".utf8), mediaVoice: Data("voice".utf8))
        let files: [PhoneArtifact] = [.init(artifactId: "demo-image", runId: "r", filename: "same.bin", contentType: "application/octet-stream"), .init(artifactId: "demo-voice", runId: "r", filename: "same.bin", contentType: "application/octet-stream")]
        let value = try await ConversationExportBuilder(storage: storage).prepare(messages: [.init(role: .user, text: "Files", artifacts: files)], responder: "Assistant", client: client)
        #expect(Set(value.files.map(\.name)).count == 2 && value.files.count == 2)
        #expect(Set(try value.files.map { try Data(contentsOf: $0.url) }).count == 2)
        #expect(value.files.allSatisfy { $0.url.deletingLastPathComponent().path == value.folder.appending(path: "Files").path })
    }
    @Test func missingOrOutsideWorkspaceFileCannotProduceAPartialExport() async throws {
        let storage = storage(); defer { try? FileManager.default.removeItem(at: storage.temporaryDirectory) }
        for target in ["/demo/session/missing.md", "/private/other/secret.md"] {
            do {
                _ = try await ConversationExportBuilder(storage: storage).prepare(messages: [.init(role: .assistant, text: "Saved", runID: "root")], responder: "Assistant", client: MockGatewayClient(), activities: ["root": try written(target)])
                Issue.record("Expected missing/outside workspace rejection")
            } catch is ConversationExportError { }
        }
        let root = storage.root.appending(path: "exports")
        #expect(try FileManager.default.contentsOfDirectory(atPath: root.path).isEmpty)
    }
    @Test func cancellationRemovesOwnedCopies() async throws {
        let storage = storage(); defer { try? FileManager.default.removeItem(at: storage.temporaryDirectory) }
        let task = Task { try await ConversationExportBuilder(storage: storage).prepare(messages: [.init(role: .user, text: "test")], responder: "Assistant", client: MockGatewayClient()) }
        task.cancel()
        do { _ = try await task.value; Issue.record("Expected cancellation") } catch is CancellationError { }
        let root = storage.root.appending(path: "exports")
        #expect(try FileManager.default.contentsOfDirectory(atPath: root.path).isEmpty)
    }
    @Test func identicalContentFromDistinctRefsOccursOnlyOnceWithinATurn() async throws {
        let storage = storage(); defer { try? FileManager.default.removeItem(at: storage.temporaryDirectory) }
        let bytes = Data("same original".utf8), client = MockGatewayClient(mediaImage: bytes, mediaVoice: bytes)
        let files = [PhoneArtifact(artifactId: "demo-image", runId: "r", filename: "same.dat", contentType: "application/octet-stream"), PhoneArtifact(artifactId: "demo-voice", runId: "r", filename: "same.dat", contentType: "application/octet-stream")]
        let export = try await ConversationExportBuilder(storage: storage).prepare(messages: [.init(role: .user, text: "Shared", artifacts: files)], responder: "Assistant", client: client)
        #expect(export.files.count == 1 && export.turns.first?.fileIDs.count == 1)
    }
}
