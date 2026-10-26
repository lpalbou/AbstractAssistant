import XCTest
import Foundation
import AssistantKit
import PhoneGatewayClient
@testable import AbstractAssistantPhone

private final class SessionFileWire: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var contents = "# First version"
    nonisolated(unsafe) static var contentReads = 0
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let path = request.url!.path
        let parent = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?.queryItems?.first { $0.name == "parent_run_id" }?.value
        var status = 200, body = #"{"items":[],"has_more":false}"#
        if path.hasSuffix("/artifacts") {
            body = #"{"items":[{"artifact_id":"playback","run_id":"child","filename":"Read aloud.wav","content_type":"audio/wav","tags":{"purpose":"voice_playback"}},{"artifact_id":"export","run_id":"child","filename":"My export.wav","content_type":"audio/wav"}],"total":2,"has_more":false}"#
        } else if path == "/api/gateway/runs/root/workspace" { status = 409; body = #"{"detail":"No root workspace"}"# }
        else if path == "/api/gateway/runs", parent == "root" { body = #"{"items":[{"run_id":"child","parent_run_id":"root","status":"completed"}],"has_more":false}"# }
        else if path == "/api/gateway/runs/child/workspace" { body = #"{"run_id":"child","workspace_root":"/private/session","exists":true,"kind":"session"}"# }
        else if path.hasSuffix("/workspace/files") {
            body = #"{"path":"","entries":[{"name":"discussion-summary.md","path":"discussion-summary.md","type":"file","size_bytes":20}],"truncated":false,"hidden":{}}"#
        } else if path.hasSuffix("/workspace/content") { body = Self.contents; Self.contentReads += 1 }
        let data = Data(body.utf8)
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: ["Content-Length": String(data.count)])!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: data); client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}
final class SessionFilesTests: XCTestCase {
    private func client() -> LiveGatewayClient {
        SessionFileWire.contentReads = 0; SessionFileWire.contents = "# First version"
        let cfg = URLSessionConfiguration.ephemeral; cfg.protocolClasses = [SessionFileWire.self]
        return .init(baseURL: URL(string: "https://gateway.test")!, token: "fixture-key", session: .init(configuration: cfg))
    }
    @MainActor func testRootWithoutWorkspaceStillFindsChildDocumentsAndKeepsAudioExports() async throws {
        let files = SessionFilesController(); files.bind("account:session")
        await files.refresh(client: client(), sessionID: "session", runIDs: ["root"])
        XCTAssertEqual(files.workspaces.count, 1)
        XCTAssertEqual(files.workspaces.first?.workspace.runID, "child")
        XCTAssertEqual(files.workspaces.first?.inventory.entries.first?.name, "discussion-summary.md")
        XCTAssertEqual(files.visibleArtifacts.map(\.artifactId), ["export"])
        XCTAssertEqual(files.count, 2)
        files.includeVoice = true
        XCTAssertEqual(files.visibleArtifacts.count, 2); XCTAssertEqual(files.count, 3)
        // Filenames alone never remove a requested voice export from a workspace.
        XCTAssertFalse(SessionFilesController.isConversationVoicePath("voice/tts-requested-export.wav"))
    }
    @MainActor func testMutableDocumentRefetchesAndPreviewCopiesAreRemoved() async throws {
        let api = client(), files = SessionFilesController(), root = RunWorkspace(runID: "child", root: "/private/session")
        let entry = WorkspaceEntry(name: "discussion-summary.md", path: "discussion-summary.md")
        files.bind("account:session"); files.open(entry, workspace: root, client: api)
        for _ in 0..<200 where files.downloading { try await Task.sleep(for: .milliseconds(10)) }
        let first = try XCTUnwrap(files.preview)
        XCTAssertEqual(try String(contentsOf: first, encoding: .utf8), "# First version")
        files.preview = nil; XCTAssertFalse(FileManager.default.fileExists(atPath: first.path))
        SessionFileWire.contents = "# Updated version"
        files.open(entry, workspace: root, client: api)
        for _ in 0..<200 where files.downloading { try await Task.sleep(for: .milliseconds(10)) }
        let second = try XCTUnwrap(files.preview)
        XCTAssertEqual(try String(contentsOf: second, encoding: .utf8), "# Updated version")
        XCTAssertEqual(SessionFileWire.contentReads, 2)
        files.bind("another-account:session")
        XCTAssertNil(files.preview); XCTAssertTrue(files.artifacts.isEmpty); XCTAssertTrue(files.workspaces.isEmpty)
        XCTAssertFalse(FileManager.default.fileExists(atPath: second.path))
    }
}
