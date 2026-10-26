import Foundation
import Testing
@testable import AbstractGatewayClient

private final class MediaWireStub: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var status = 200
    nonisolated(unsafe) static var bytes = Data()
    nonisolated(unsafe) static var requests: [URLRequest] = []
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.requests.append(request)
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: Self.status, httpVersion: nil, headerFields: ["Content-Type":"image/png", "Content-Length":String(Self.bytes.count)])!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Self.bytes)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}
@Suite(.serialized) struct MediaTransportTests {
    private func client(status: Int = 200, bytes: Data = Data([1,2,3])) -> LiveGatewayClient {
        MediaWireStub.status = status; MediaWireStub.bytes = bytes; MediaWireStub.requests = []
        let config = URLSessionConfiguration.ephemeral; config.protocolClasses = [MediaWireStub.self]
        return LiveGatewayClient(baseURL: URL(string: "https://gateway.test")!, token: "media-token", session: URLSession(configuration: config), readTries: 1)
    }
    private func destination() throws -> URL {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("media-wire-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        return folder.appendingPathComponent("image.png")
    }
    private var artifact: PhoneArtifact { .init(artifactId: "image", runId: "turn", filename: "Image.png", contentType: "image/png") }
    @Test func streamedPreviewWritesExactBytesToOwnedDisk() async throws {
        let payload = Data((0..<200_000).map { UInt8($0 % 251) }), url = try destination()
        defer { try? FileManager.default.removeItem(at: url.deletingLastPathComponent()) }
        let client = client(bytes: payload)
        try await client.download(artifact, to: url)
        #expect(try Data(contentsOf: url) == payload)
        #expect(MediaWireStub.requests.first?.url?.path == "/api/gateway/runs/turn/artifacts/image/content")
        #expect(MediaWireStub.requests.first?.value(forHTTPHeaderField: "Authorization") == "Bearer media-token")
    }
    @Test func unauthorizedDeletesPartialFileAndLocksFurtherRequests() async throws {
        let client = client(status: 401), url = try destination()
        defer { try? FileManager.default.removeItem(at: url.deletingLastPathComponent()) }
        for _ in 0..<2 {
            do { try await client.download(artifact, to: url); Issue.record("Expected unauthorized") }
            catch { #expect(error as? GatewayError == .unauthorized) }
            #expect(!FileManager.default.fileExists(atPath: url.path))
        }
        #expect(MediaWireStub.requests.count == 1)
    }
    @Test func invalidArtifactAndOversizeNeverFetchAndRemoveEmptyFile() async throws {
        let client = client(), url = try destination()
        defer { try? FileManager.default.removeItem(at: url.deletingLastPathComponent()) }
        for file in [PhoneArtifact(artifactId: "../escape", runId: "turn", filename: "x", contentType: "image/png"),
                     PhoneArtifact(artifactId: "huge", runId: "turn", filename: "x", contentType: "image/png", size: PhoneArtifact.previewByteLimit + 1)] {
            do { try await client.download(file, to: url); Issue.record("Expected refusal") } catch {}
            #expect(!FileManager.default.fileExists(atPath: url.path))
        }
        #expect(MediaWireStub.requests.isEmpty)
    }
    @Test func existingFileIsNotOverwritten() async throws {
        let client = client(), url = try destination(), original = Data("keep".utf8)
        defer { try? FileManager.default.removeItem(at: url.deletingLastPathComponent()) }
        try original.write(to: url)
        do { try await client.download(artifact, to: url); Issue.record("Expected refusal") } catch {}
        #expect(try Data(contentsOf: url) == original)
        #expect(MediaWireStub.requests.isEmpty)
    }
    @Test func cancelledDownloadLeavesNoFile() async throws {
        let client = client(bytes: Data(repeating: 1, count: 200_000)), url = try destination(), artifact = artifact
        defer { try? FileManager.default.removeItem(at: url.deletingLastPathComponent()) }
        let task = Task { try await client.download(artifact, to: url) }
        task.cancel()
        do { try await task.value; Issue.record("Expected cancellation") } catch {}
        #expect(!FileManager.default.fileExists(atPath: url.path))
    }
    @Test func existingInputRouteRestoresUploadOwnerAndTypedFilename() async throws {
        let json = #"{"input_data":{"prompt":"Describe this","attachments":[{"$artifact":"upload","run_id":"session_memory_history","content_type":"image/png","filename":null}]}}"#
        let client = client(bytes: Data(json.utf8))
        let input = try await client.input(ofRun: "turn")
        #expect(input.prompt == "Describe this")
        #expect(input.attachments.map(\.id) == ["session_memory_history:upload"])
        #expect(input.attachments.first?.filename == "Image-upload.png")
        #expect(MediaWireStub.requests.first?.url?.path == "/api/gateway/runs/turn/input_data")
    }

}
