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
    a.readAloud = true
    a.voice = VoiceChoice(provider: "tts", model: "voice-model", voice: "speaker", label: "Speaker")
    a.transcription = TranscriptionChoice(provider: "stt", model: "small")
    let loaded = PhonePreferences(scope: "alice", defaults: defaults)
    #expect(loaded.readAloud && loaded.voice == a.voice && loaded.transcription == a.transcription)
    let b = PhonePreferences(scope: "bob", defaults: defaults)
    #expect(!b.readAloud && b.voice == nil && b.transcription == nil)
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
