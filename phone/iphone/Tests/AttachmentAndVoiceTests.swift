import XCTest
import PhoneGatewayClient
import AssistantKit
@testable import AbstractAssistantPhone

final class AttachmentAndVoiceTests: XCTestCase {
    @MainActor func testPreviewDismissalAndReplacementDoNotAccumulateCopies() async throws {
        let base = FileManager.default.temporaryDirectory.appending(path: "preview-test-\(UUID())")
        defer { try? FileManager.default.removeItem(at: base) }
        let storage = PhoneTemporaryStorage(temporaryDirectory: base)
        let files = AttachmentsController(storage: storage), client = MockGatewayClient()
        let artifact = try await client.artifacts(sessionId: "test").first!
        var previous: URL?
        for _ in 0..<12 {
            files.open(artifact, client: client)
            for _ in 0..<100 where files.busy { try await Task.sleep(for: .milliseconds(10)) }
            let current = try XCTUnwrap(files.preview)
            if let previous { XCTAssertFalse(FileManager.default.fileExists(atPath: previous.path)) }
            let previews = try FileManager.default.contentsOfDirectory(at: storage.root.appending(path: "previews"), includingPropertiesForKeys: nil)
            XCTAssertEqual(previews.count, 1)
            previous = current
        }
        files.preview = nil // The binding QuickLook resets when dismissed.
        XCTAssertFalse(FileManager.default.fileExists(atPath: try XCTUnwrap(previous).path))
        XCTAssertTrue(try FileManager.default.contentsOfDirectory(at: storage.root.appending(path: "previews"), includingPropertiesForKeys: nil).isEmpty)
    }

    @MainActor func testImportRemovesItsCopyButPreservesTheOriginal() async throws {
        let source = FileManager.default.temporaryDirectory.appending(path: "original-\(UUID()).txt")
        try Data("original".utf8).write(to: source)
        defer { try? FileManager.default.removeItem(at: source) }
        let copy = try ImportedMedia.copy(source), folder = copy.deletingLastPathComponent()
        let files = AttachmentsController()
        files.importFile(copy, client: MockGatewayClient(), sessionId: "test", owned: true)
        for _ in 0..<200 where files.busy { try await Task.sleep(for: .milliseconds(10)) }
        XCTAssertEqual(files.pending.count, 1)
        XCTAssertFalse(FileManager.default.fileExists(atPath: folder.path))
        XCTAssertEqual(try Data(contentsOf: source), Data("original".utf8))
    }

    @MainActor func testPreviewUsesALocalFileAndResetRemovesIt() async throws {
        let files = AttachmentsController()
        let client = MockGatewayClient()
        let artifact = try await client.artifacts(sessionId: "test").first!
        files.open(artifact, client: client)
        for _ in 0..<100 where files.busy { try await Task.sleep(for: .milliseconds(10)) }
        let url = try XCTUnwrap(files.preview)
        XCTAssertTrue(url.isFileURL)
        XCTAssertEqual(try String(contentsOf: url, encoding: .utf8), MockGatewayClient.cannedAnswer)
        files.reset()
        XCTAssertFalse(FileManager.default.fileExists(atPath: url.path))
    }
    @MainActor func testUploadKeepsItsOwnerAndSurvivesReturningToTheSameConversation() async throws {
        let files = AttachmentsController(); files.bind("original")
        let url = FileManager.default.temporaryDirectory.appending(path: "phone-test-\(UUID()).txt")
        try Data("hello".utf8).write(to: url)
        defer { try? FileManager.default.removeItem(at: url) }
        files.importFile(url, client: MockGatewayClient(), sessionId: "original")
        for _ in 0..<200 where files.busy { try await Task.sleep(for: .milliseconds(10)) }
        files.bind("original")
        XCTAssertEqual(files.pending.count, 1)
        XCTAssertEqual(files.pending.first?.runId, "session_memory_original")
        files.remove(try XCTUnwrap(files.pending.first))
        XCTAssertTrue(files.pending.isEmpty)
    }
}
