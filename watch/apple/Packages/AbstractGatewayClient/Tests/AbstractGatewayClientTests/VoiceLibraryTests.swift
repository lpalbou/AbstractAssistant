import Foundation
import Testing
@testable import AbstractGatewayClient

// The gateway's voice library (AbstractGateway 0.16.0): the catalog's groups and languages, and the
// calls that create, rename and delete a person's voices.

/// The record AbstractGateway's catalog really emits for a cloned voice: AbstractVoice lists each
/// clone in both `voices` and `cloned_voices`, and the gateway's merge (`_gateway_catalog_voice_items`,
/// routes/gateway.py at abstractgateway 15987aef) sets `voice_kind: "voice"` with
/// `voice_kinds: ["voice", "clone"]`; the record's own `kind` stays "clone". Captured by running
/// those gateway functions on the plugin's clone record; verbatim.
private let gatewayClone = ##"{"display_name":"My voice","engine":"qwen3-tts","engine_id":"qwen3-tts","id":"a1b2c3","kind":"clone","label":"My voice","name":"My voice","params":{"engine":"qwen3-tts","language":"en","meta":{"engine":"qwen3-tts","language":"en","scope":"personal"},"name":"My voice","reference_text":"Hello there.","voice_id":"a1b2c3"},"profile_id":"a1b2c3","provider":"qwen3-tts","tags":{"engine":"qwen3-tts","engine_id":"qwen3-tts","language_code":"en","provider":"qwen3-tts","source":"abstractvoice_clone_store"},"voice_id":"a1b2c3","voice_kind":"voice","voice_kinds":["voice","clone"]}"##

private func json(_ text: String) -> JSONValue { try! JSONDecoder().decode(JSONValue.self, from: Data(text.utf8)) }

private let catalogJSON = """
{"items":[
  \(gatewayClone),
  {"id":"F2","label":"Supertonic F2","voice_kind":"profile","params":{"provider":"supertonic","model":"supertonic-3","voice":"F2"},"tags":{"gender":"female","language_code":"en"}},
  {"id":"fr-female-camille","label":"Camille","kind":"clone","provider":"qwen3-tts","voice_id":"fr-female-camille","tags":{"builtin":true,"language_code":"fr","description":"A bright adult female voice."},"params":{"meta":{"scope":"library"}}},
  {"id":"team","label":"Team voice","kind":"clone","provider":"qwen3-tts","voice_id":"team","language":"de","params":{"meta":{"scope":"library"}}},
  {"id":"alloy","label":"Alloy","voice_kind":"voice","languages":[],"params":{"provider":"openai","model":"gpt-4o-mini-tts","voice":"alloy"}}
],
"tts_models_by_provider":{"qwen3-tts":["Qwen3-TTS-12Hz-1.7B-Base"],"supertonic":["supertonic-3"]},
"gateway_defaults":{"tts":{"provider":"supertonic","model":"supertonic-3","voice":"F2"},"stt":{"provider":"faster-whisper","model":"base"}}}
"""

@Suite struct VoiceLibraryCatalogTests {
    @Test func theGatewaysCloneRecordIsThePersonsOwnAndSpeaksOnItsEngine() {
        let record = json(gatewayClone)
        #expect(VoiceLibrary.group(record) == .yours)
        let catalog = VoiceCatalog.parse(voices: json(catalogJSON), transcription: .null)
        let mine = catalog.entries.first { $0.voiceID == "a1b2c3" }
        #expect(mine?.group == .yours)
        #expect(mine?.choice == VoiceChoice(provider: "qwen3-tts", model: "Qwen3-TTS-12Hz-1.7B-Base", voice: "a1b2c3", label: "My voice"))
        #expect(mine?.language == "en")
        #expect(mine?.isOwn == true)
        #expect(catalog.voices.contains(mine!.choice))
    }

    @Test func groupsAreYoursEngineAndShared() {
        let catalog = VoiceCatalog.parse(voices: json(catalogJSON), transcription: .null)
        let groups = Dictionary(uniqueKeysWithValues: catalog.entries.map { ($0.voiceID, $0.group) })
        #expect(groups == ["a1b2c3": .yours, "F2": .engine, "fr-female-camille": .shared, "team": .shared, "alloy": .engine])
        #expect(VoiceGroup.allCases.map(\.title) == ["Your voices", "Engine voices", "Shared voices"])
        // A record whose voice_kind says "clone" without a kind is a clone too.
        #expect(VoiceLibrary.group(json(#"{"voice_kind":"clone","params":{"meta":{"scope":"personal"}}}"#)) == .yours)
        #expect(VoiceLibrary.group(json(#"{"voice_kind":"profile"}"#)) == .engine)
        // A built-in voice is listed from the personal layer (AbstractVoice's layered store stamps
        // `meta.scope: personal` on it); `tags.builtin` alone makes it shared, never the person's own.
        #expect(VoiceLibrary.group(json(#"{"kind":"clone","tags":{"builtin":true,"language_code":"fr"},"params":{"meta":{"builtin":true,"scope":"personal"}}}"#)) == .shared)
        #expect(catalog.defaultVoiceProvider == "supertonic")
        #expect(catalog.entry(for: VoiceChoice(provider: "supertonic", model: "supertonic-3", voice: "F2", label: "an old label"))?.voiceID == "F2")
    }

    @Test func languagesDescriptionsAndTheFilter() {
        let catalog = VoiceCatalog.parse(voices: json(catalogJSON), transcription: .null)
        #expect(VoiceLibrary.languages(of: catalog.entries) == ["de", "en", "fr"])
        #expect(VoiceLibrary.languageName("fr") == "French" && VoiceLibrary.languageName("xx") == "xx")
        let camille = catalog.entries.first { $0.voiceID == "fr-female-camille" }!
        #expect(camille.language == "fr" && camille.summary == "A bright adult female voice.")
        #expect(camille.speaks("fr") && !camille.speaks("en") && camille.speaks(""))
        // No native language and no listed languages: unrestricted (remote/OpenAI voices).
        let alloy = catalog.entries.first { $0.voiceID == "alloy" }!
        #expect(alloy.speaks("ja"))
        #expect(VoiceEntry(choice: alloy.choice, languages: ["en", "fr"]).speaks("fr"))
        #expect(!VoiceEntry(choice: alloy.choice, languages: ["en", "fr"]).speaks("de"))

        let french = VoiceLibrary.grouped(catalog.entries, speaking: "fr")
        #expect(french.map(\.group) == [.engine, .shared])
        #expect(french.flatMap { $0.entries.map(\.voiceID) } == ["alloy", "fr-female-camille"])
        // The chosen voice stays listed under any filter.
        let kept = VoiceLibrary.grouped(catalog.entries, speaking: "fr", keep: catalog.entries[0].choice)
        #expect(kept.map(\.group) == [.yours, .engine, .shared])
        #expect(VoiceLibrary.grouped(catalog.entries).map(\.group) == [.yours, .engine, .shared])
    }
}

// MARK: Transport

private final class VoiceWireStub: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var status = 200
    nonisolated(unsafe) static var reply = Data()
    nonisolated(unsafe) static var requests: [(URLRequest, Data)] = []
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        var data = request.httpBody ?? Data()
        if data.isEmpty, let stream = request.httpBodyStream {
            stream.open(); defer { stream.close() }
            var buffer = [UInt8](repeating: 0, count: 4096)
            while stream.hasBytesAvailable { let n = stream.read(&buffer, maxLength: buffer.count); if n <= 0 { break }; data.append(contentsOf: buffer.prefix(n)) }
        }
        Self.requests.append((request, data))
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: Self.status, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Self.reply)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@Suite(.serialized) struct VoiceLibraryTransportTests {
    private func client(status: Int = 200, reply: String = #"{"voice_id":"v-1","name":"Narrator","engine":"qwen3-tts"}"#) -> LiveGatewayClient {
        VoiceWireStub.status = status; VoiceWireStub.reply = Data(reply.utf8); VoiceWireStub.requests = []
        let config = URLSessionConfiguration.ephemeral; config.protocolClasses = [VoiceWireStub.self]
        return LiveGatewayClient(baseURL: URL(string: "https://gateway.test")!, token: "voice-token", session: URLSession(configuration: config), readTries: 1)
    }

    @Test func designPostsTheDescriptionNameAndLanguage() async throws {
        let created = try await client().designVoice(description: "A calm, warm voice", name: "Narrator", language: "fr")
        #expect(created == CreatedVoice(voiceID: "v-1", name: "Narrator", engine: "qwen3-tts"))
        let (request, body) = try #require(VoiceWireStub.requests.first)
        #expect(request.httpMethod == "POST")
        #expect(request.url?.absoluteString == "https://gateway.test/api/gateway/voice/design")
        #expect(request.value(forHTTPHeaderField: "Authorization") == "Bearer voice-token")
        #expect(request.value(forHTTPHeaderField: "Content-Type") == "application/json")
        #expect(json(String(decoding: body, as: UTF8.self)) == json(#"{"description":"A calm, warm voice","name":"Narrator","language":"fr"}"#))
        // Long: a design loads its engine on first use.
        #expect(request.timeoutInterval >= 120)
    }

    @Test func designWithoutNameOrLanguageSendsNeither() async throws {
        _ = try await client().designVoice(description: "A voice", name: nil, language: "")
        let (_, body) = try #require(VoiceWireStub.requests.first)
        #expect(json(String(decoding: body, as: UTF8.self)) == json(#"{"description":"A voice"}"#))
    }

    @Test func clonePostsMultipartWithTheRecordingAndItsFields() async throws {
        let audio = Data("RIFF-wave-bytes".utf8)
        let upload = VoiceCloneUpload(audio: audio, filename: "me.m4a", contentType: "audio/mp4", name: "Me", language: "en", referenceText: "Hello there.", provider: "qwen3-tts")
        let created = try await client().cloneVoice(upload)
        #expect(created.voiceID == "v-1")
        let (request, body) = try #require(VoiceWireStub.requests.first)
        #expect(request.httpMethod == "POST")
        #expect(request.url?.absoluteString == "https://gateway.test/api/gateway/voice/clones")
        let type = try #require(request.value(forHTTPHeaderField: "Content-Type"))
        #expect(type.hasPrefix("multipart/form-data; boundary="))
        let text = String(decoding: body, as: UTF8.self)
        for part in ["name=\"name\"\r\n\r\nMe\r\n", "name=\"language\"\r\n\r\nen\r\n", "name=\"reference_text\"\r\n\r\nHello there.\r\n",
                     "name=\"provider\"\r\n\r\nqwen3-tts\r\n", "name=\"file\"; filename=\"me.m4a\"\r\nContent-Type: audio/mp4\r\n\r\nRIFF-wave-bytes\r\n"] {
            #expect(text.contains(part), "missing \(part.debugDescription)")
        }
        #expect(text.hasSuffix("--\r\n"))
    }

    @Test func aDetectedLanguageAndNoEngineAreNotSent() async throws {
        _ = try await client().cloneVoice(VoiceCloneUpload(audio: Data([1, 2]), filename: "me.wav", contentType: "audio/wav"))
        let text = String(decoding: try #require(VoiceWireStub.requests.first).1, as: UTF8.self)
        #expect(!text.contains("name=\"language\"") && !text.contains("name=\"provider\"") && !text.contains("name=\"name\""))
        #expect(text.contains("name=\"file\"; filename=\"me.wav\""))
    }

    @Test func renameAndDeleteAddressTheVoice() async throws {
        let c = client(reply: "{}")
        try await c.renameVoice(id: "v-1", name: "Story voice")
        try await c.deleteVoice(id: "v-1")
        let (rename, body) = VoiceWireStub.requests[0], (delete, _) = VoiceWireStub.requests[1]
        #expect(rename.httpMethod == "PATCH" && rename.url?.absoluteString == "https://gateway.test/api/gateway/voice/clones/v-1")
        #expect(json(String(decoding: body, as: UTF8.self)) == json(#"{"name":"Story voice"}"#))
        #expect(delete.httpMethod == "DELETE" && delete.url?.absoluteString == "https://gateway.test/api/gateway/voice/clones/v-1")
        // An id that is not one path segment never leaves the phone.
        await #expect(throws: GatewayError.invalidResponse) { try await c.deleteVoice(id: "../escape") }
        #expect(VoiceWireStub.requests.count == 2)
    }

    @Test(arguments: [
        (403, "On this gateway every account shares one voice store, so creating, changing or deleting a voice is an administrator's act."),
        (422, "Built-in voices are read-only."),
        (501, "Voice design needs abstractvoice[qwen3-tts] where the voice capability runs."),
    ])
    func aRefusalIsTheGatewaysSentence(status: Int, sentence: String) async throws {
        let body = try String(decoding: JSONEncoder().encode(["detail": sentence]), as: UTF8.self)
        let c = client(status: status, reply: body)
        do { _ = try await c.designVoice(description: "x", name: nil, language: nil); Issue.record("expected a refusal") }
        catch { #expect(error.localizedDescription == sentence); #expect(error as? GatewayError == .http(status: status, body: body)) }
        do { try await c.deleteVoice(id: "fr-female-camille"); Issue.record("expected a refusal") }
        catch { #expect(error.localizedDescription == sentence) }
    }
}

// MARK: The sample gateway

@Suite struct MockVoiceLibraryTests {
    @Test func theSampleLibraryCreatesRenamesAndDeletesOwnVoicesOnly() async throws {
        let mock = MockGatewayClient(world: .phone)
        var catalog = try await mock.voiceCatalog()
        #expect(Set(catalog.entries.map(\.group)) == [.yours, .engine, .shared])
        let designed = try await mock.designVoice(description: "A calm voice", name: "Calm", language: "en")
        catalog = try await mock.voiceCatalog()
        #expect(catalog.entries.first { $0.voiceID == designed.voiceID }?.group == .yours)
        try await mock.renameVoice(id: designed.voiceID, name: "Calmer")
        #expect(try await mock.voiceCatalog().entries.first { $0.voiceID == designed.voiceID }?.choice.label == "Calmer")
        try await mock.deleteVoice(id: designed.voiceID)
        #expect(try await mock.voiceCatalog().entries.first { $0.voiceID == designed.voiceID } == nil)
        do { try await mock.deleteVoice(id: "fr-female-camille"); Issue.record("a shared voice was deleted") }
        catch { #expect(error.localizedDescription == "Built-in and shared voices are read-only.") }
    }
}
