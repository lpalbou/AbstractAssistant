import XCTest
import AbstractGatewayClient
@testable import AbstractAssistantPhone

final class AttachmentAndVoiceTests: XCTestCase {
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
