import Foundation
import Testing
@testable import AbstractGatewayClient

private final class SpeechWire: URLProtocol, @unchecked Sendable {
    struct State {
        var status = 200
        var body = ""
        var end = true
        var requests: [URLRequest] = []
        var stopped = 0
    }
    private static let lock = NSLock()
    nonisolated(unsafe) private static var state = State()
    static func configure(_ body: String, status: Int, end: Bool) {
        lock.withLock { state = State(status: status, body: body, end: end) }
    }
    static var requests: [URLRequest] { lock.withLock { state.requests } }
    static var stopped: Int { lock.withLock { state.stopped } }
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let response = Self.lock.withLock {
            Self.state.requests.append(request)
            return (Self.state.status, Self.state.body, Self.state.end)
        }
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: response.0, httpVersion: nil,
            headerFields: ["Content-Type": "application/x-ndjson"])!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(response.1.utf8))
        if response.2 { client?.urlProtocolDidFinishLoading(self) }
    }
    override func stopLoading() { Self.lock.withLock { Self.state.stopped += 1 } }
}

@Suite(.serialized) struct SpeechTransportTests {
    private let wav = SyntheticSpeech.wav(seconds: 0.02, seed: 1)
    private var audio: String { "{\"type\":\"audio\",\"audio_b64\":\"\(wav.base64EncodedString())\"}\n" }
    private let done = "{\"type\":\"done\",\"ok\":true}\n"

    private func client(_ body: String, status: Int = 200, end: Bool = true) -> LiveGatewayClient {
        SpeechWire.configure(body, status: status, end: end)
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [SpeechWire.self]
        return LiveGatewayClient(baseURL: URL(string: "https://gateway.test")!, token: "fixture-key",
                                 session: URLSession(configuration: configuration), readTries: 1)
    }
    private func collect(_ stream: AsyncThrowingStream<Data, Error>) async throws -> [Data] {
        var chunks: [Data] = []
        for try await chunk in stream { chunks.append(chunk) }
        return chunks
    }

    @Test func audioNeedsSuccessfulCompletionAndMetadataDoesNotInterruptIt() async throws {
        let api = client("\n{\"type\":\"runtime_start\"}\n{\"type\":\"queued\",\"message\":\"Waiting\"}\n" + audio
                         + "{\"type\":\"future_metadata\",\"value\":1}\n" + audio + done)
        let voice = VoiceChoice(provider: "qwen3-tts", model: "example-model", voice: "example-voice", label: "Example")
        #expect(try await collect(api.speech(text: "Hello", scope: .run("r1"), voice: voice)) == [wav, wav])
        let requests = SpeechWire.requests
        #expect(requests.count == 1)
        #expect(requests.first?.url?.path == "/api/gateway/runs/r1/voice/tts/stream")
        #expect(requests.first?.httpMethod == "POST")
        #expect(requests.first?.value(forHTTPHeaderField: "Authorization") == "Bearer fixture-key")
    }

    @Test func aCleanSocketEOFStillMeansTruncatedSpeech() async throws {
        let api = client(audio)
        var received: [Data] = []
        do {
            for try await chunk in api.speech(text: "Hello", scope: .run("r1")) { received.append(chunk) }
            Issue.record("A connection ending without done must not report complete speech")
        } catch {
            #expect(error as? GatewayError == .http(status: 502, body: #"{"detail":"The voice stream ended before speech was complete. Try again."}"#))
        }
        #expect(received == [wav])
        #expect(SpeechWire.requests.count == 1, "Partial speech must not automatically start another synthesis")
    }

    @Test(arguments: ["not json\n", "{\"type\":\"audio\",\"audio_b64\":\"not base64!\"}\n",
                      "{\"type\":\"audio\"}\n", "{\"type\":\"audio\",\"audio_b64\":\"\"}\n"])
    func malformedDataCannotSilentlyDropSpokenWords(_ malformed: String) async {
        let api = client(audio + malformed + done)
        await #expect(throws: GatewayError.invalidResponse) {
            _ = try await collect(api.speech(text: "Hello", scope: .run("r1")))
        }
    }

    @Test(arguments: ["error", "cancelled"])
    func terminalFailuresDoNotPassForCompletedSpeech(_ type: String) async {
        let api = client(audio + "{\"type\":\"\(type)\",\"ok\":false,\"error\":\"Voice interrupted\"}\n")
        await #expect(throws: GatewayError.http(status: 502, body: "Voice interrupted")) {
            _ = try await collect(api.speech(text: "Hello", scope: .entity("assistant")))
        }
    }

    @Test func aDoneEventCanReportFailure() async {
        let api = client(audio + "{\"type\":\"done\",\"ok\":false,\"error\":\"Voice interrupted\"}\n")
        await #expect(throws: GatewayError.http(status: 502, body: "Voice interrupted")) {
            _ = try await collect(api.speech(text: "Hello", scope: .run("r1")))
        }
    }

    @Test func anOlderSuccessfulDoneWithoutOKStillCompletes() async throws {
        let api = client(audio + "{\"type\":\"done\"}\n")
        #expect(try await collect(api.speech(text: "Hello", scope: .run("r1"))) == [wav])
    }

    @Test func HTTPFailuresAreNotMistakenForTruncatedAudioOrRetried() async {
        let body = #"{"detail":"Voice temporarily unavailable"}"#
        let api = client(body, status: 503)
        await #expect(throws: GatewayError.http(status: 503, body: body)) {
            _ = try await collect(api.speech(text: "Hello", scope: .run("r1")))
        }
        #expect(SpeechWire.requests.count == 1)
    }

    @Test func rejectedSignInStopsFurtherVoiceRequests() async {
        let api = client(#"{"detail":"Sign in again"}"#, status: 401)
        for _ in 0..<2 {
            await #expect(throws: GatewayError.unauthorized) {
                _ = try await collect(api.speech(text: "Hello", scope: .run("r1")))
            }
        }
        #expect(SpeechWire.requests.count == 1)
    }

    @Test func cancellingTheConsumerClosesTheVoiceRequest() async throws {
        let api = client(audio, end: false)
        let stream = api.speech(text: "Hello", scope: .run("r1"))
        let received = AsyncStream.makeStream(of: Void.self)
        let consumer = Task {
            do {
                for try await _ in stream { received.continuation.yield(()) }
            } catch { }
        }
        var first = received.stream.makeAsyncIterator()
        _ = await first.next()
        consumer.cancel()
        await consumer.value
        for _ in 0..<100 where SpeechWire.stopped == 0 { try await Task.sleep(for: .milliseconds(10)) }
        #expect(SpeechWire.stopped == 1)
        #expect(SpeechWire.requests.count == 1)
        received.continuation.finish()
    }
}
