import XCTest
import UIKit
import UniformTypeIdentifiers
import LinkPresentation
import AssistantKit
import AbstractGatewayClient
@testable import AbstractAssistantPhone

private final class DeferredShareWire: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var pending: DeferredShareWire?
    nonisolated(unsafe) static var started: XCTestExpectation?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() { Self.pending = self; Self.started?.fulfill() }
    override func stopLoading() {}
    func reject() {
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: 401, httpVersion: nil, headerFields: [:])!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocolDidFinishLoading(self)
    }
}

final class ConversationSharingTests: XCTestCase {
    @MainActor func testRichFormattingInlinePositionsAndOriginalFileProviders() async throws {
        let image = UIGraphicsImageRenderer(size: CGSize(width: 1400, height: 900)).image { context in UIColor.systemTeal.setFill(); context.fill(CGRect(x: 0, y: 0, width: 1400, height: 900)) }
        let bytes = try XCTUnwrap(image.pngData()), client = MockGatewayClient(mediaImage: bytes)
        let file = PhoneArtifact(artifactId: "demo-image", runId: "r", filename: "Photo.png", contentType: "image/png")
        let source: [ConversationMessage] = [.init(role: .user, text: "Before **bold** and *italic*.\n\n# A heading\n\n- Item one\n- Item two\n\n<script>bad</script>", artifacts: [file]), .init(role: .assistant, text: "After the image.\n\n```\n**literal code**\n```", runID: "r")]
        let export = try await ConversationExportBuilder().prepare(messages: source, responder: "Assistant", client: client, activities: ["r": .init(activity: .init())])
        defer { try? PhoneTemporaryStorage().discard(export.folder) }
        let value = try RichConversation(export: export), plain = String(decoding: value.plain, as: UTF8.self), html = String(decoding: value.html, as: UTF8.self)
        XCTAssertTrue(plain.contains("Before bold and italic.")); XCTAssertFalse(plain.contains("Before **bold**")); XCTAssertTrue(plain.contains("**literal code**"))
        XCTAssertTrue(html.contains("<strong>bold</strong>") && html.contains("<em>italic</em>"))
        XCTAssertTrue(html.contains("&lt;script&gt;") && !html.contains("<script>"))
        XCTAssertTrue(html.contains("data:image/jpeg;base64,"))
        XCTAssertLessThan(try XCTUnwrap(html.range(of: "data:image" )).lowerBound, try XCTUnwrap(html.range(of: "After the image.")).lowerBound)
        var attachments = 0, strong = false
        value.body.enumerateAttributes(in: NSRange(location: 0, length: value.body.length)) { attrs, _, _ in
            if attrs[.attachment] != nil { attachments += 1 }
            if let font = attrs[.font] as? UIFont, font.fontDescriptor.symbolicTraits.contains(.traitBold) { strong = true }
        }
        XCTAssertEqual(attachments, 1); XCTAssertTrue(strong)
        let restored = try NSAttributedString(data: value.rtfd, options: [.documentType: NSAttributedString.DocumentType.rtfd], documentAttributes: nil)
        XCTAssertTrue(restored.string.contains("After the image."))
        var restoredImages = 0
        restored.enumerateAttribute(.attachment, in: NSRange(location: 0, length: restored.length)) { value, _, _ in if value != nil { restoredImages += 1 } }
        XCTAssertEqual(restoredImages, 1)
        let configuration = value.configuration(export: export)
        XCTAssertEqual(configuration.itemProvidersForActivityItemsConfiguration.count, 2)
        let provider = try XCTUnwrap(configuration.itemProvidersForActivityItemsConfiguration.first)
        XCTAssertTrue(provider.hasItemConformingToTypeIdentifier(UTType.flatRTFD.identifier))
        XCTAssertTrue(provider.hasItemConformingToTypeIdentifier(UTType.html.identifier))
        XCTAssertTrue(provider.hasItemConformingToTypeIdentifier(UTType.utf8PlainText.identifier))
        XCTAssertTrue(configuration.metadataProvider?(.messageBody) is NSAttributedString)
        XCTAssertEqual((configuration.perItemMetadataProvider?(0, .linkPresentationMetadata) as? LPLinkMetadata)?.title, "Conversation")
        XCTAssertEqual(try Data(contentsOf: export.files[0].url), bytes)
        let offeredHTML: Data = try await withCheckedThrowingContinuation { continuation in
            provider.loadDataRepresentation(forTypeIdentifier: UTType.html.identifier) { data, error in
                if let data { continuation.resume(returning: data) } else { continuation.resume(throwing: error ?? GatewayError.invalidResponse) }
            }
        }
        XCTAssertEqual(offeredHTML, value.html)
        let originalProvider = configuration.itemProvidersForActivityItemsConfiguration[1]
        let offeredOriginal: Data = try await withCheckedThrowingContinuation { continuation in
            originalProvider.loadFileRepresentation(forTypeIdentifier: UTType.png.identifier) { url, error in
                do { if let url { continuation.resume(returning: try Data(contentsOf: url)) } else { continuation.resume(throwing: error ?? GatewayError.invalidResponse) } }
                catch { continuation.resume(throwing: error) }
            }
        }
        XCTAssertEqual(offeredOriginal, bytes)
        let preview = UITextView(frame: CGRect(x: 0, y: 0, width: 390, height: 1000))
        preview.backgroundColor = .white; preview.textContainerInset = UIEdgeInsets(top: 22, left: 18, bottom: 22, right: 18); preview.attributedText = value.body
        let screenshot = UIGraphicsImageRenderer(size: preview.bounds.size).image { preview.layer.render(in: $0.cgContext) }
        let attachment = XCTAttachment(image: screenshot); attachment.name = "Rich transcript — native formatted text and inline image"; attachment.lifetime = .keepAlways; add(attachment)
    }
    @MainActor func testShareLeaseKeepsCopiesUntilCompletionAndCleansIdempotently() async throws {
        let export = try await ConversationExportBuilder().prepare(messages: [.init(role: .user, text: "**Hello**")], responder: "Assistant", client: MockGatewayClient())
        let lease = PreparedConversationShare(export: export, rich: try RichConversation(export: export))
        _ = lease.rich.configuration(export: export)
        XCTAssertTrue(FileManager.default.fileExists(atPath: export.folder.path))
        lease.close(); lease.close()
        XCTAssertFalse(FileManager.default.fileExists(atPath: export.folder.path))
    }
    @MainActor func testLateOldAccountUnauthorizedCannotInvalidateNewContext() async throws {
        let config = URLSessionConfiguration.ephemeral; config.protocolClasses = [DeferredShareWire.self]
        let oldClient = LiveGatewayClient(baseURL: URL(string: "https://gateway.test")!, token: "fixture", session: .init(configuration: config))
        let store = AssistantStore(); store.connect(nil, client: MockGatewayClient()); defer { store.disconnect(); DeferredShareWire.pending = nil; DeferredShareWire.started = nil }
        let storage = PhoneTemporaryStorage(temporaryDirectory: FileManager.default.temporaryDirectory.appending(path: "share-race-" + UUID().uuidString))
        defer { try? FileManager.default.removeItem(at: storage.temporaryDirectory) }
        let file = PhoneArtifact(artifactId: "original", runId: "old", filename: "original.pdf", contentType: "application/pdf")
        let snapshot = ConversationShareSnapshot(messages: [.init(role: .user, text: "Old account", artifacts: [file])], responder: "Assistant", client: oldClient, activities: [:], contextID: store.contextID, sessionID: store.sessionID)
        let preparation = ConversationShareController(storage: storage)
        let started = expectation(description: "Old download began"); DeferredShareWire.started = started
        let task = Task { await preparation.prepare(snapshot: snapshot, store: store) }
        await fulfillment(of: [started], timeout: 5)
        store.connect(nil, client: MockGatewayClient())
        let current = store.contextID
        try XCTUnwrap(DeferredShareWire.pending).reject(); await task.value
        XCTAssertEqual(store.contextID, current); XCTAssertNotNil(store.client)
        XCTAssertNil(preparation.prepared); XCTAssertNil(preparation.issue)
        XCTAssertTrue(try FileManager.default.contentsOfDirectory(atPath: storage.root.appending(path: "exports").path).isEmpty)
    }
}
