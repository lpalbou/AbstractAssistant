import Foundation
import Testing
@testable import AbstractGatewayClient

/// The identity routes as gateway 0.20 serves them (framework ADR 0052 section 11).
private final class IdentityWire: URLProtocol, @unchecked Sendable {
    struct Reply { var status = 200; var body = ""; var headers: [String: String] = [:] }
    private static let lock = NSLock()
    nonisolated(unsafe) private static var reply = Reply()
    nonisolated(unsafe) private static var seen: [URLRequest] = []
    static func configure(_ r: Reply) { lock.withLock { reply = r; seen = [] } }
    static var requests: [URLRequest] { lock.withLock { seen } }
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let r = Self.lock.withLock { Self.seen.append(request); return Self.reply }
        var headers = r.headers; headers["Content-Type"] = headers["Content-Type"] ?? "application/json"
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: r.status, httpVersion: nil, headerFields: headers)!,
                            cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(r.body.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@Suite(.serialized) struct DigitalIdentityTests {
    private func client(_ reply: IdentityWire.Reply) -> LiveGatewayClient {
        IdentityWire.configure(reply)
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [IdentityWire.self]
        return LiveGatewayClient(baseURL: URL(string: "https://gateway.test")!, token: "fixture-key",
                                 session: URLSession(configuration: configuration), readTries: 1)
    }

    private static let view = ##"""
    {"entity_id":"entity:castor@h1","identity":{"rev":2,"avatar":{"style":"watch-vortex","color":"#f59e0b","source":"chosen","watch_code":"B"},
     "voice":{"provider":"qwen3-tts","model":"m","voice":"fr-male-rene","source":"chosen"},"set_at":"2026-11-04T10:00:00+00:00","set_by":"person:laurent"},
     "identity_ref":{"of":"entity:castor@h1","rev":2},"fingerprint":{"actor_id":"ar_1"},"age":{"born":"2026-10-01T00:00:00Z","days":34}}
    """##

    @Test func identityIsReadFromItsRouteWithTheRevisionAsked() async throws {
        let api = client(.init(body: Self.view))
        let now = try await api.entityIdentity(name: "castor", rev: nil)
        #expect(now.identityRef == IdentityRef(of: "entity:castor@h1", rev: 2))
        #expect(now.identity.avatar.drawing == .design("B") && now.identity.avatar.color == "#f59e0b")
        #expect(IdentityWire.requests.first?.url?.path == "/api/gateway/entities/castor/identity")
        #expect(IdentityWire.requests.first?.url?.query == nil)
        _ = try await client(.init(body: Self.view)).entityIdentity(name: "castor", rev: 2)
        #expect(IdentityWire.requests.first?.url?.query == "rev=2")
    }

    /// No look is ever made up: a refusal reaches the view as the gateway's own sentence, and a
    /// record whose reference names another revision is not the record asked for.
    @Test func aRefusalIsTheGatewaysSentenceAndAMismatchedRecordIsRefused() async throws {
        let held = client(.init(status: 409, body: #"{"detail":"Castor is closed for maintenance; its identity is served again when the window closes."}"#))
        do { _ = try await held.entityIdentity(name: "castor", rev: nil); Issue.record("a held home answered a record") }
        catch { #expect(error.localizedDescription == "Castor is closed for maintenance; its identity is served again when the window closes.") }
        let wrong = Self.view.replacingOccurrences(of: #""identity_ref":{"of":"entity:castor@h1","rev":2}"#, with: #""identity_ref":{"of":"entity:castor@h1","rev":1}"#)
        await #expect(throws: (any Error).self) { _ = try await client(.init(body: wrong)).entityIdentity(name: "castor", rev: nil) }
    }

    @Test func theListRowCarriesTheRecordAndItsReference() throws {
        let json = ##"""
        {"entities":[{"slug":"castor","name":"Castor","entity_id":"entity:castor@h1","identity":{"rev":3,"avatar":{"style":"watch-shape-kitty","color":"#f59e0b","source":"chosen","watch_code":"shape:kitty"},"voice":null},"appearance":{"color":"#f59e0b","shape":"kitty"}},
                     {"slug":"held","entity_id":"entity:held@h2","identity":null},
                     {"slug":"broken","entity_id":"entity:broken@h3","identity":{"rev":0,"avatar":{"style":"x","color":"#000000"}}}]}
        """##
        let rows = try JSONDecoder().decode(EntitiesPage.self, from: Data(json.utf8)).entities
        #expect(rows[0].identity?.avatar.drawing == .shape("kitty"))
        #expect(rows[0].identityRef == IdentityRef(of: "entity:castor@h1", rev: 3))
        #expect(rows[1].identity == nil && rows[1].identityRef == nil)          // held: no record, no look
        #expect(rows[2].identity == nil)                                          // rev 0 is not a record
    }

    @Test func aWatchCodeIsADesignOrASilhouette() {
        #expect(WatchDrawing(watchCode: "AU") == .design("AU"))
        #expect(WatchDrawing(watchCode: "shape:wave") == .shape("wave"))
        #expect(WatchDrawing(watchCode: "shape:") == nil)
        #expect(WatchDrawing(watchCode: "") == nil && WatchDrawing(watchCode: nil) == nil)
    }

    @Test func aReferenceRoundTripsItsStringFormAndRefusesWhatIsNotOne() throws {
        #expect(IdentityRef(header: "entity:castor@h1#3") == IdentityRef(of: "entity:castor@h1", rev: 3))
        #expect(IdentityRef(header: "entity:castor@h1#3")?.description == "entity:castor@h1#3")
        #expect(IdentityRef(header: "castor") == nil)
        #expect(IdentityRef(header: "entity:castor#0") == nil)
        #expect(IdentityRef(header: "#2") == nil)
        #expect(throws: (any Error).self) { try JSONDecoder().decode(IdentityRef.self, from: Data(#"{"of":"entity:castor","rev":0}"#.utf8)) }
    }

    /// Public updates carry the identity that wrote them, on the visit state and on the replay view.
    @Test func publicUpdatesCarryTheirWriter() throws {
        let state = try JSONDecoder().decode(EntitySessionState.self, from: Data(#"{"run_id":"v","status":"waiting","turn_n":1,"public_updates":[{"id":"v:public_update:1","text":"Hello","run_id":"v","identity_ref":{"of":"entity:castor@h1","rev":2}},{"id":"v:public_update:2","text":"Hi","run_id":"v"}]}"#.utf8))
        #expect(state.publicUpdates?.first?.identityRef == IdentityRef(of: "entity:castor@h1", rev: 2))
        #expect(state.publicUpdates?.last?.identityRef == nil)
        let view = try JSONDecoder().decode(PublicConversationView.self, from: Data(#"{"messages":[{"id":"r:u:1","kind":"public_update","role":"assistant","source":"emit_event","text":"Hello","run_id":"r","identity_ref":{"of":"entity:vega@h2","rev":1}}]}"#.utf8))
        #expect(view.updates.first?.identityRef == IdentityRef(of: "entity:vega@h2", rev: 1))
    }

    /// The entity lane names whose voice speaks; the Assistant's lane names none.
    @Test func theSpeechStreamNamesItsSpeakerBeforeTheAudio() async throws {
        let wav = SyntheticSpeech.wav(seconds: 0.02, seed: 1)
        let body = "{\"type\":\"audio\",\"audio_b64\":\"\(wav.base64EncodedString())\"}\n{\"type\":\"done\",\"ok\":true}\n"
        var parts: [SpeechPart] = []
        for try await p in client(.init(body: body, headers: ["X-Identity-Ref": "entity:castor@h1#2", "Content-Type": "application/x-ndjson"]))
            .speechParts(text: "Hello", scope: .entity("castor"), voice: nil) { parts.append(p) }
        #expect(parts == [.identity(IdentityRef(of: "entity:castor@h1", rev: 2)!), .audio(wav)])
        parts = []
        for try await p in client(.init(body: body, headers: ["Content-Type": "application/x-ndjson"]))
            .speechParts(text: "Hello", scope: .run("r1"), voice: nil) { parts.append(p) }
        #expect(parts == [.audio(wav)])
    }

    /// An entity's text is spoken with the entity's identity voice: the reading names no voice of
    /// its own, whatever the person chose for the Assistant (a named voice would replace it).
    @Test func anEntitysReadingNeverNamesAVoice() async throws {
        let chosen = VoiceChoice(provider: "kokoro", model: "k", voice: "af_heart", label: "Heart")
        #expect(SpeechScope.entity("castor").requestedVoice(chosen) == nil)
        #expect(SpeechScope.run("r1").requestedVoice(chosen) == chosen)
        let body = "{\"type\":\"done\",\"ok\":true}\n"
        for try await _ in client(.init(body: body)).speechParts(text: "Hello", scope: .entity("castor"),
                                                                 voice: SpeechScope.entity("castor").requestedVoice(chosen)) {}
        let sent = try #require(IdentityWire.requests.first.flatMap { request in
            request.httpBody ?? request.httpBodyStream.map { stream in
                stream.open(); defer { stream.close() }
                var data = Data(); var buffer = [UInt8](repeating: 0, count: 4096)
                while stream.hasBytesAvailable { let n = stream.read(&buffer, maxLength: buffer.count); if n <= 0 { break }; data.append(buffer, count: n) }
                return data
            }
        })
        let json = try #require(try JSONSerialization.jsonObject(with: sent) as? [String: Any])
        #expect(json["provider"] == nil && json["model"] == nil && json["voice"] == nil)
        #expect(IdentityWire.requests.first?.url?.path == "/api/gateway/entities/castor/voice/tts/stream")
    }

    /// A refused reading shows the gateway's sentence (the recorded "no voice yet"), never a guess;
    /// a failure another try may fix is not a refusal.
    @Test func aRefusalIsItsSentence() {
        let none = GatewayError.http(status: 409, body: #"{"detail":"Castor has no voice yet: choose one in its Identity settings or set the Gateway default voice"}"#)
        #expect(GatewayError.refusal(none) == "Castor has no voice yet: choose one in its Identity settings or set the Gateway default voice")
        #expect(GatewayError.refusal(GatewayError.http(status: 502, body: #"{"detail":"engine failed"}"#)) == nil)
        #expect(GatewayError.refusal(GatewayError.http(status: 429, body: #"{"detail":"slow down"}"#)) == nil)
        #expect(GatewayError.refusal(GatewayError.http(status: 404, body: "plain")) == nil)
        #expect(GatewayError.refusal(URLError(.timedOut)) == nil)
    }

    /// A dialogue names who speaks when the speaker changes; the same identity going on is not
    /// named again, and the first speaker is the conversation's own.
    @Test func theSpeakerIsNamedWhenItChanges() {
        let castor = IdentityRef(of: "entity:castor@h1", rev: 2)!, vega = IdentityRef(of: "entity:vega@h2", rev: 1)!
        let castorBefore = IdentityRef(of: "entity:castor@h1", rev: 1)!
        #expect(SpeakerChange.label([castor]) == nil)
        #expect(SpeakerChange.label([castor, castor]) == nil)
        #expect(SpeakerChange.label([castor, vega]) == vega)
        #expect(SpeakerChange.label([castor, nil, vega]) == vega)
        #expect(SpeakerChange.label([vega, nil]) == nil)
        #expect(SpeakerChange.label([castorBefore, castor]) == castor)        // a new look is named too
        #expect(SpeakerChange.label([]) == nil)
    }

    /// The sample gateway serves its entities by reference too (screenshots and UI tests).
    @Test func theMockServesRecordsAndStampedUpdates() async throws {
        let mock = MockGatewayClient(world: .watch)
        let castor = try #require(await mock.entities().first { $0.name == "castor" })
        #expect(castor.identity?.avatar.drawing == .design("B"))
        let earlier = try await mock.entityIdentity(name: "castor", rev: 1)
        #expect(earlier.identity.avatar.drawing == .shape("kitty"))
        let updates = try await mock.entitySession(name: "castor", runID: "mock-visit-castor").publicUpdates ?? []
        #expect(SpeakerChange.label(updates.map(\.identityRef)) == castor.identityRef)
    }
}
