import XCTest
import UIKit
import AVFoundation
import PhoneGatewayClient
import AssistantKit
@testable import AbstractAssistantPhone

final class MessageMediaTests: XCTestCase {
    @MainActor func testCancelledRowAndReplacementShareDownloadAndRestoreInlineImage() async throws {
        let base = FileManager.default.temporaryDirectory.appending(path: UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: base) }
        let media = MessageMediaController(storage: .init(temporaryDirectory: base))
        media.bind("account:restored-session")
        let file = PhoneArtifact(artifactId: "image", runId: "original", filename: "Generated.png", contentType: "image/png")
        let client = imageClient()
        let firstRow = Task { await media.thumbnail(file, client: client) }
        try await waitForRequests(1)
        firstRow.cancel() // LazyVStack removes/rebuilds the original row during history restoration.
        await Task.yield()
        let replacement = Task { await media.thumbnail(file, client: client) }
        let preview = Task { await media.open(file, client: client) }
        try await Task.sleep(for: .milliseconds(60))
        ImageDownloadWire.state.complete(data: MediaDesignFixture.image)
        await firstRow.value; await replacement.value; await preview.value
        XCTAssertNotNil(media.images[file.id])
        XCTAssertNotNil(media.preview)
        XCTAssertNil(media.errors[file.id])
        XCTAssertFalse(media.loading.contains(file.id))
        XCTAssertEqual(ImageDownloadWire.state.requestCount, 1)
        XCTAssertEqual(ImageDownloadWire.state.cancelCount, 0)
        media.reset()
    }
    @MainActor func testSwitchingSessionCancelsOldTransferWithoutStrandingSameArtifact() async throws {
        let base = FileManager.default.temporaryDirectory.appending(path: UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: base) }
        let media = MessageMediaController(storage: .init(temporaryDirectory: base))
        let client = imageClient()
        let file = PhoneArtifact(artifactId: "same-image", runId: "original", filename: "Generated.png", contentType: "image/png")
        media.bind("account-one:session")
        let old = Task { await media.open(file, client: client) }
        try await waitForRequests(1)
        media.bind("account-two:session")
        XCTAssertNil(media.preview); XCTAssertTrue(media.images.isEmpty)
        let current = Task { await media.thumbnail(file, client: client) }
        try await waitForRequests(2)
        await old.value
        XCTAssertTrue(media.loading.contains(file.id)) // Old completion cannot clear the new operation.
        XCTAssertNil(media.preview); XCTAssertNil(media.errors[file.id])
        ImageDownloadWire.state.complete(data: MediaDesignFixture.image)
        await current.value
        XCTAssertNotNil(media.images[file.id]); XCTAssertFalse(media.loading.contains(file.id))
        XCTAssertNil(media.preview); XCTAssertEqual(media.files.count, 1)
        XCTAssertGreaterThanOrEqual(ImageDownloadWire.state.cancelCount, 1)
        media.reset()
        XCTAssertTrue(media.files.isEmpty)
    }
    @MainActor func testOpenRestoresThumbnailRetriesFailureAndRefetchesPurgedCache() async throws {
        let base = FileManager.default.temporaryDirectory.appending(path: UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: base) }
        let media = MessageMediaController(storage: .init(temporaryDirectory: base))
        media.bind("account:session")
        let client = imageClient()
        let file = PhoneArtifact(artifactId: "retry-image", runId: "original", filename: "Generated.png", contentType: "image/png")
        let failed = Task { await media.thumbnail(file, client: client) }
        try await waitForRequests(1)
        ImageDownloadWire.state.complete(data: Data("temporary outage".utf8), status: 503)
        await failed.value
        XCTAssertNotNil(media.errors[file.id]); XCTAssertFalse(media.loading.contains(file.id))
        let retried = Task { await media.open(file, client: client) }
        try await waitForRequests(2)
        ImageDownloadWire.state.complete(data: MediaDesignFixture.image)
        await retried.value
        XCTAssertNotNil(media.images[file.id]); XCTAssertNil(media.errors[file.id])
        let original = try XCTUnwrap(media.preview)
        try FileManager.default.removeItem(at: original); media.preview = nil
        let refreshed = Task { await media.open(file, client: client) }
        try await waitForRequests(3)
        ImageDownloadWire.state.complete(data: MediaDesignFixture.image)
        await refreshed.value
        let replacement = try XCTUnwrap(media.preview)
        XCTAssertNotEqual(original, replacement)
        XCTAssertTrue(FileManager.default.fileExists(atPath: replacement.path))
        XCTAssertNotNil(media.images[file.id]); XCTAssertNil(media.errors[file.id])
        XCTAssertEqual(media.files.count, 1)
        media.reset()
    }
    private func imageClient() -> LiveGatewayClient {
        ImageDownloadWire.state.reset()
        let config = URLSessionConfiguration.ephemeral; config.protocolClasses = [ImageDownloadWire.self]
        return .init(baseURL: URL(string: "https://gateway.test")!, token: "fixture", session: .init(configuration: config))
    }
    @MainActor private func waitForRequests(_ count: Int) async throws {
        for _ in 0..<200 {
            if ImageDownloadWire.state.requestCount >= count { return }
            try await Task.sleep(for: .milliseconds(10))
        }
        XCTFail("Expected image download to begin")
    }
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


private final class ImageDownloadWire: URLProtocol, @unchecked Sendable {
    static let state = ImageDownloadState()
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() { Self.state.start(self) }
    override func stopLoading() { Self.state.stop(self) }
}

private final class ImageDownloadState: @unchecked Sendable {
    private let lock = NSLock()
    private var pending: [ObjectIdentifier: ImageDownloadWire] = [:]
    private var requests = 0, cancellations = 0
    var requestCount: Int { lock.withLock { requests } }
    var cancelCount: Int { lock.withLock { cancellations } }
    func reset() { lock.withLock { pending = [:]; requests = 0; cancellations = 0 } }
    func start(_ wire: ImageDownloadWire) { lock.withLock { requests += 1; pending[ObjectIdentifier(wire)] = wire } }
    func stop(_ wire: ImageDownloadWire) {
        lock.withLock { if pending.removeValue(forKey: ObjectIdentifier(wire)) != nil { cancellations += 1 } }
    }
    func complete(data: Data, status: Int = 200) {
        let wires = lock.withLock { let values = Array(pending.values); pending = [:]; return values }
        for wire in wires {
            wire.client?.urlProtocol(wire, didReceive: HTTPURLResponse(url: wire.request.url!, statusCode: status,
                httpVersion: nil, headerFields: ["Content-Type": "image/png", "Content-Length": String(data.count)])!, cacheStoragePolicy: .notAllowed)
            wire.client?.urlProtocol(wire, didLoad: data)
            wire.client?.urlProtocolDidFinishLoading(wire)
        }
    }
}
