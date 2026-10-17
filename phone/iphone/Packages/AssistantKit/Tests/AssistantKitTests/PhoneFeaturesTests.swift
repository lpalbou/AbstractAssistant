import Foundation
import Testing
import AssistantKit
import AbstractGatewayClient

@Test func malformedArtifactSizesCannotTrapAndPathsStayLocal() throws {
    for (value, expected) in [(1e100, PhoneArtifact.byteLimit + 1), (-1e100, 0), (123.0, 123)] {
        let row: JSONValue = .object(["artifact_id": .string("file1"), "run_id": .string("run1"), "size_bytes": .number(value), "filename": .string("../../report.pdf")])
        let file = try #require(PhoneArtifact.parse(row))
        #expect(file.size == expected && file.filename == "report.pdf")
    }
    #expect(PhoneArtifact.parse(.object(["artifact_id": .string("../file"), "run_id": .string("run1")])) == nil)
    #expect(PhoneArtifact.safeFilename("../..") == "Attachment")
    #expect(PhoneSession.owner("phone-1") == "session_memory_phone-1")
    #expect(PhoneSession.owner("chat:1").hasPrefix("session_memory_sha_"))
    #expect(PhoneSession.owner("chat.1").hasPrefix("session_memory_sha_"))
}

@Test @MainActor func readingAndVoiceChoicesStayScopedToTheAccount() {
    let defaults = UserDefaults(suiteName: "phone-features-\(UUID())")!
    let a = PhonePreferences(scope: "alice", defaults: defaults)
    a.readAloud = true; a.speed = 1.3
    a.voice = VoiceChoice(provider: "tts", model: "voice-model", voice: "speaker", label: "Speaker")
    a.transcription = TranscriptionChoice(provider: "stt", model: "small")
    let loaded = PhonePreferences(scope: "alice", defaults: defaults)
    #expect(loaded.readAloud && loaded.voice == a.voice && loaded.transcription == a.transcription && loaded.speed == 1.3)
    let b = PhonePreferences(scope: "bob", defaults: defaults)
    #expect(!b.readAloud && b.voice == nil && b.transcription == nil && b.speed == 1)
}

@Test @MainActor func restoredHistoryDoesNotEmitANewSpokenReply() async {
    let store = AssistantStore()
    store.connect(nil, client: MockGatewayClient())
    await store.refresh()
    if let session = store.sessions.first { await store.openSession(session) }
    #expect(store.completedReply == nil)
    let before = store.contextID
    store.disconnect()
    #expect(store.contextID != before && store.completedReply == nil)
}

@Test func automationCreationRetryUsesTheSameRequest() async throws {
    let client = MockGatewayClient()
    let request = NewAutomation(task: "Check the news", target: .gatewayDefault(interface: "abstractassistant.agent.v1"), when: .daily(at: "08:00"), buildsOnEarlierRuns: false, askBeforeTools: true)
    let first = try await client.createAutomation(request), retry = try await client.createAutomation(request)
    #expect(first.id == retry.id)
    let list = try await client.automations()
    #expect(list.filter { $0.id == first.id }.count == 1)
    #expect(request.body["policy"]?["tool_approval"] == .string("ask"))
}

@Test @MainActor func invalidSpeakingSpeedIsRestoredSafely() {
    let defaults = UserDefaults(suiteName: "speed-\(UUID())")!
    for value in [Double.nan, .infinity, -1, 0, 12] {
        defaults.set(value, forKey: "phone.preferences.test.speed")
        let prefs = PhonePreferences(scope: "test", defaults: defaults)
        #expect(prefs.speed == 1)
        prefs.speed = value
        #expect(prefs.speed == 1)
    }
}

@Test func entityDraftRejectsPathInjectionAndCreationPreservesWarnings() throws {
    #expect(EntityDraft(name: " Atlas One ").slug == "atlas-one")
    for bad in ["../secret", "name/path", "?bad", "_leading", String(repeating: "a", count: 65)] { #expect(!EntityDraft(name: bad).valid) }
    let created = try CreatedEntity(.object(["created": .bool(true), "manifest": .object(["slug": .string("atlas-one"), "name": .string("Atlas One")]), "warnings": .array([.string("Partial setup")]), "skills_warning": .string("Skills unavailable"), "capability_map_warning": .string("Map unavailable")]))
    #expect(created.entity.name == "atlas-one" && created.entity.displayName == "Atlas One")
    #expect(created.warnings == ["Partial setup", "Skills unavailable", "Map unavailable"])
}

@Test func entityCreationRetryKeepsTheSameEntity() async throws {
    let client = MockGatewayClient(), draft = EntityDraft(name: "Atlas One")
    let validation = try await client.validateEntity(draft)
    #expect(validation.ok && !validation.exists)
    let first = try await client.createEntity(draft), retry = try await client.createEntity(draft)
    #expect(first.created && !retry.created && first.entity.name == retry.entity.name)
    #expect(try await client.entities().filter { $0.name == draft.slug }.count == 1)
}

@Test func liveEntityManifestUsesSlugForRoutingAndKeepsDisplayName() throws {
    let rows = try JSONDecoder().decode(EntitiesPage.self, from: Data(#"{"entities":[{"name":"Atlas One","slug":"atlas-one","state":{"state":"asleep"}},{"slug":"broken-home","error":"Unreadable identity"}]}"#.utf8)).entities
    #expect(rows[0].name == "atlas-one" && rows[0].displayName == "Atlas One")
    let restored = try JSONDecoder().decode([EntitySummary].self, from: JSONEncoder().encode(rows))
    #expect(restored[0].name == "atlas-one" && restored[0].displayName == "Atlas One")
    #expect(rows[1].name == "broken-home" && rows[1].extra["error"]?.stringValue == "Unreadable identity")
}
