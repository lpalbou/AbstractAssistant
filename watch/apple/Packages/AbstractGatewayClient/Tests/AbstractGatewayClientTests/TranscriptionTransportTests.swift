import Foundation
import Testing
@testable import AbstractGatewayClient

private final class TranscriptionWire: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var requests: [URLRequest] = []
    nonisolated(unsafe) static var replies: [(Int, String)] = []
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.requests.append(request)
        let reply = Self.replies.removeFirst()
        let data = Data(reply.1.utf8)
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: reply.0, httpVersion: nil,
            headerFields: ["Content-Type": "application/json"])!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: data)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@Suite(.serialized) struct TranscriptionTransportTests {
    private let uploaded = #"{"run_id":"session_memory_voice-chat","artifact":{"$artifact":"recording"}}"#

    private func client(_ replies: [(Int, String)]) -> LiveGatewayClient {
        TranscriptionWire.requests = []
        TranscriptionWire.replies = replies
        let cfg = URLSessionConfiguration.ephemeral
        cfg.protocolClasses = [TranscriptionWire.self]
        return LiveGatewayClient(baseURL: URL(string: "https://gateway.test")!, token: "fixture-key",
                                 session: URLSession(configuration: cfg), readTries: 1)
    }

    @Test func aRecordingUploadsThenTranscribesInItsActualOwner() async throws {
        let api = client([(200, uploaded), (200, #"{"text":"  hello\n"}"#)])
        #expect(try await api.transcribe(wav: Data([1, 2, 3]), sessionId: "voice-chat") == "hello")
        #expect(TranscriptionWire.requests.map { $0.url!.path } == [
            "/api/gateway/attachments/upload", "/api/gateway/runs/session_memory_voice-chat/audio/transcribe"])
        #expect(TranscriptionWire.requests.allSatisfy { $0.httpMethod == "POST" })
        #expect(TranscriptionWire.requests.allSatisfy { $0.value(forHTTPHeaderField: "Authorization") == "Bearer fixture-key" })
    }

    @Test func uploadFailurePreservesTheReasonWithoutStartingTranscription() async throws {
        let body = #"{"detail":"Upload unavailable"}"#
        let api = client([(503, body)])
        await #expect(throws: GatewayError.http(status: 503, body: body)) {
            _ = try await api.transcribe(wav: Data([1]), sessionId: "voice-chat")
        }
        #expect(TranscriptionWire.requests.count == 1)
    }

    @Test func transcriptionFailurePreservesTheReasonWithoutRepeatingWrites() async throws {
        let body = #"{"detail":"Transcription unavailable"}"#
        let api = client([(200, uploaded), (503, body)])
        await #expect(throws: GatewayError.http(status: 503, body: body)) {
            _ = try await api.transcribe(wav: Data([1]), sessionId: "voice-chat")
        }
        #expect(TranscriptionWire.requests.count == 2)
    }

    @Test func rejectedSignInStopsFurtherVoiceRequests() async throws {
        let api = client([(401, #"{"detail":"Sign in again"}"#)])
        for _ in 0..<2 {
            await #expect(throws: GatewayError.unauthorized) {
                _ = try await api.transcribe(wav: Data([1]), sessionId: "voice-chat")
            }
        }
        #expect(TranscriptionWire.requests.count == 1)
    }
}
