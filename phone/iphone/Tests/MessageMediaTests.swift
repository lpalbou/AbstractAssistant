import XCTest
import UIKit
import AVFoundation
import AbstractGatewayClient
import AssistantKit
@testable import AbstractAssistantPhone

final class MessageMediaTests: XCTestCase {
    @MainActor func testThumbnailsAreBoundedAndSwitchingAccountsDeletesOwnedFiles() async throws {
        let base = FileManager.default.temporaryDirectory.appending(path: UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: base) }
        let storage = PhoneTemporaryStorage(temporaryDirectory: base), media = MessageMediaController(storage: storage)
        let client = MockGatewayClient(); media.bind("account-one:session")
        let png = MediaDesignFixture.image
        for index in 0..<9 {
            let file = try await client.upload(data: png, filename: "Image \(index).png", contentType: "image/png", sessionId: "session")
            await media.thumbnail(file, client: client)
            XCTAssertNotNil(media.images[file.id]); XCTAssertLessThanOrEqual(media.files.count, 6)
        }
        let urls = Array(media.files.values)
        XCTAssertEqual(try FileManager.default.contentsOfDirectory(at: storage.root.appending(path: "previews"), includingPropertiesForKeys: nil).count, 6)
        media.bind("account-two:session")
        XCTAssertTrue(media.images.isEmpty); XCTAssertTrue(media.files.isEmpty)
        for url in urls { XCTAssertFalse(FileManager.default.fileExists(atPath: url.path)) }
    }
    @MainActor func testVoiceFilesPlayIndependentlyPauseAndResetWithoutLeakingCopies() async throws {
        let base = FileManager.default.temporaryDirectory.appending(path: UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: base) }
        let media = MessageMediaController(storage: PhoneTemporaryStorage(temporaryDirectory: base))
        let client = MockGatewayClient()
        let wav = SyntheticSpeech.wav(seconds: 4, seed: 2)
        let first = try await client.upload(data: wav, filename: "First.wav", contentType: "audio/wav", sessionId: "session")
        let second = try await client.upload(data: wav, filename: "Second.wav", contentType: "audio/wav", sessionId: "session")
        await media.play(first, client: client)
        XCTAssertEqual(media.playingID, first.id); XCTAssertGreaterThan(media.duration, 3)
        try await Task.sleep(for: .milliseconds(200)); XCTAssertGreaterThan(media.level, 0.01)
        await media.play(first, client: client); XCTAssertTrue(media.paused)
        await media.play(second, client: client)
        XCTAssertEqual(media.playingID, second.id); XCTAssertFalse(media.paused)
        media.seek(1); XCTAssertEqual(media.elapsed, 1, accuracy: 0.1)
        let urls = Array(media.files.values); media.reset()
        XCTAssertNil(media.playingID); XCTAssertNil(media.preview)
        for url in urls { XCTAssertFalse(FileManager.default.fileExists(atPath: url.path)) }
    }
    @MainActor func testReferenceSelectionKeepsGatewayIdentityWithoutUploadingACopy() throws {
        let files = AttachmentsController()
        let image = PhoneArtifact(artifactId: "generated-image", runId: "original-run", filename: "Image.png", contentType: "image/png")
        files.use(image); files.use(image)
        XCTAssertEqual(files.pending, [image]); XCTAssertEqual(files.pending[0].ref["run_id"], .string("original-run"))
    }
}
