import Foundation
import Testing
import AbstractGatewayClient

private final class MediaInputWire: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var started: JSONValue?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let path = request.url!.path
        let json: String
        if path.hasSuffix("preferences") {
            json = #"{"apps":[{"interface":"abstractassistant.agent.v1","value":"abstractassistant-orchestrator:c53b1579","effective":{"available":true,"bundle_id":"abstractassistant-orchestrator","bundle_version":"0.0.12","flow_id":"c53b1579","registry_scope":"user"}}]}"#
        } else if path.hasSuffix("tools") { json = #"{"items":[]}"# }
        else {
            if let body = request.httpBody { Self.started = try? JSONDecoder().decode(JSONValue.self, from: body) }
            else if let stream = request.httpBodyStream {
                stream.open(); defer { stream.close() }; var body = Data(), buffer = [UInt8](repeating: 0, count: 4096)
                while stream.hasBytesAvailable { let count = stream.read(&buffer, maxLength: buffer.count); if count <= 0 { break }; body.append(contentsOf: buffer.prefix(count)) }
                Self.started = try? JSONDecoder().decode(JSONValue.self, from: body)
            }
            json = #"{"run_id":"generated"}"#
        }
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: ["Content-Type":"application/json"])!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(json.utf8)); client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}
@Suite(.serialized) struct MediaRunInputTests {
    @Test func existingStartRouteKeepsSelectedWorkflowAndPrimaryImagePins() async throws {
        let config = URLSessionConfiguration.ephemeral; config.protocolClasses = [MediaInputWire.self]
        let client = LiveGatewayClient(baseURL: URL(string: "https://gateway.test")!, token: "fixture", session: URLSession(configuration: config), readTries: 1)
        let old = PhoneArtifact(artifactId: "old", runId: "earlier-run", filename: "Old.png", contentType: "image/png").ref
        let upload = PhoneArtifact(artifactId: "fresh", runId: "session_memory_chat", filename: "New.png", contentType: "image/png").ref
        for attachments in [[], [upload]] {
            _ = try await client.startRun(prompt: "Make it gold", sessionId: "chat", attachments: attachments, tools: nil, primaryImage: old)
            let body = try #require(MediaInputWire.started), input = try #require(body["input_data"])
            #expect(body["bundle_id"] == .string("abstractassistant-orchestrator"))
            #expect(body["bundle_version"] == .string("0.0.12")); #expect(body["flow_id"] == .string("c53b1579"))
            #expect(input["has_primary_image_context"] == .bool(true))
            #expect(input["primary_image_artifact"] == (attachments.first ?? old))
            #expect(input["context"]?["primary_image_artifact"] == input["primary_image_artifact"])
        }
        _ = try await client.startRun(prompt: "Hello", sessionId: "new-chat", attachments: [], tools: nil, primaryImage: nil)
        #expect(MediaInputWire.started?["input_data"]?["has_primary_image_context"] == .bool(false))
        #expect(MediaInputWire.started?["input_data"]?["primary_image_artifact"] == nil)
    }
}
