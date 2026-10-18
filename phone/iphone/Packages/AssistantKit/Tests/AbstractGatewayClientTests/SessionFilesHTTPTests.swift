import Foundation
import Testing
@testable import AbstractGatewayClient

private final class FileWire: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var requests: [URLRequest] = []
    nonisolated(unsafe) static var status = 200
    nonisolated(unsafe) static var payload = Data()
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.requests.append(request)
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: Self.status, httpVersion: nil, headerFields: ["Content-Length": String(Self.payload.count)])!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Self.payload); client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}
@Suite(.serialized) struct SessionFilesHTTPTests {
    private func client(_ json: String, status: Int = 200) -> LiveGatewayClient {
        FileWire.requests = []; FileWire.status = status; FileWire.payload = Data(json.utf8)
        let cfg = URLSessionConfiguration.ephemeral; cfg.protocolClasses = [FileWire.self]
        return LiveGatewayClient(baseURL: URL(string: "https://gateway.test")!, token: "fixture-key", session: .init(configuration: cfg))
    }
    @Test func pageUsesOffsetAndVoiceFlagAndKeepsMetadata() async throws {
        let api = client(#"{"items":[{"artifact_id":"recording","run_id":"owner","content_type":"audio/wav","source_path":"client:voice/dictation/test.wav"}],"total":501,"has_more":true,"warnings":["fixture warning"]}"#)
        let page = try await api.artifactPage(sessionID: "chat", offset: 500, includeVoice: true)
        #expect(page.nextOffset == 501 && page.total == 501 && page.hasMore)
        #expect(page.items.first?.isConversationVoice == true)
        let url = try #require(FileWire.requests.first?.url)
        let params = Dictionary(uniqueKeysWithValues: URLComponents(url: url, resolvingAgainstBaseURL: false)!.queryItems!.map { ($0.name, $0.value ?? "") })
        #expect(url.path == "/api/gateway/sessions/chat/artifacts")
        #expect(params["offset"] == "500" && params["include_voice"] == "true" && params["cursor"] == nil)
        #expect(page.warnings == ["fixture warning"])
    }
    @Test func workspaceListingPreservesDirectoriesPathsAndTruncation() async throws {
        let api = client(#"{"path":"Research","entries":[{"name":"a+b & c.md","path":"Research/a+b & c.md","type":"file","size_bytes":19},{"name":"Nested","path":"Research/Nested","type":"dir","size_bytes":null}],"truncated":true,"hidden":{"blocked":1}}"#)
        let listing = try await api.workspaceFiles(runID: "turn", path: "Research", recursive: false, limit: nil)
        #expect(listing.entries[0].path == "Research/a+b & c.md")
        #expect(listing.entries[1].isDirectory && listing.truncated && listing.hidden?["blocked"] == 1)
        let url = try #require(FileWire.requests.first?.url)
        #expect(url.path == "/api/gateway/runs/turn/workspace/files")
        #expect(URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems?.contains { $0.name == "limit" } == false)
    }
    @Test func authenticatedWorkspaceBytesAreExactAndPathUsesQueryEncoding() async throws {
        let api = client("# A real Markdown file\n"), directory = FileManager.default.temporaryDirectory.appending(path: UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let url = directory.appending(path: "notes.md")
        try await api.downloadWorkspaceFile(runID: "turn", entry: .init(name: "notes.md", path: "Research/a+b & c.md"), to: url)
        #expect(try String(contentsOf: url, encoding: .utf8) == "# A real Markdown file\n")
        let req = try #require(FileWire.requests.first)
        #expect(req.url?.path == "/api/gateway/runs/turn/workspace/content")
        #expect(URLComponents(url: req.url!, resolvingAgainstBaseURL: false)?.queryItems?.first?.value == "Research/a+b & c.md")
        #expect(req.value(forHTTPHeaderField: "Authorization") == "Bearer fixture-key")
    }
    @Test func unsafePathsAndDirectoriesNeverReachTheGateway() async throws {
        let api = client("{}"); let url = FileManager.default.temporaryDirectory.appending(path: UUID().uuidString)
        for path in ["../secret", "/etc/passwd", "a/../../secret", "C:/secret", "a\\..\\secret"] {
            await #expect(throws: GatewayError.self) { try await api.downloadWorkspaceFile(runID: "turn", entry: .init(name: "x", path: path), to: url) }
        }
        await #expect(throws: GatewayError.self) { try await api.downloadWorkspaceFile(runID: "turn", entry: .init(name: "folder", path: "folder", type: "dir"), to: url) }
        #expect(FileWire.requests.isEmpty && !FileManager.default.fileExists(atPath: url.path))
    }
    @Test func unauthorizedWorkspaceReadRemovesPartialAndLocksOtherReads() async throws {
        let api = client("refused", status: 401), folder = FileManager.default.temporaryDirectory.appending(path: UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        let url = folder.appending(path: "notes.md")
        await #expect(throws: GatewayError.unauthorized) { try await api.downloadWorkspaceFile(runID: "turn", entry: .init(name: "notes.md", path: "notes.md"), to: url) }
        await #expect(throws: GatewayError.unauthorized) { _ = try await api.workspace(runID: "turn") }
        #expect(FileWire.requests.count == 1 && !FileManager.default.fileExists(atPath: url.path))
    }
}
