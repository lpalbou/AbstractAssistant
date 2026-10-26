import Foundation
import Testing
import PhoneGatewayClient

@Suite struct ArtifactProvenanceTests {
    private func artifact(_ fields: String) throws -> PhoneArtifact {
        let raw = "{\"artifact_id\":\"abcdefgh123\",\"run_id\":\"owner\"," + fields + "}"
        return try #require(PhoneArtifact.parse(JSONDecoder().decode(JSONValue.self, from: Data(raw.utf8))))
    }
    @Test func preservesLogicalHierarchyAndUsesActualBasename() throws {
        let item = try artifact(#""source_path":"client:reports/weekly.md","content_type":"text/markdown""#)
        #expect(item.filename == "weekly.md")
        #expect(item.sourcePath == "client:reports/weekly.md")
        #expect(!item.isConversationVoice)
    }
    @Test func missingNameHasTypeAndStableIdentity() throws {
        let item = try artifact(#""content_type":"text/markdown""#)
        #expect(item.filename == "Document-abcdefgh.md")
    }
    @Test func deliberateAudioAndLegacyAskFilenameRemainVisible() throws {
        for fields in [#""filename":"ask.wav","content_type":"audio/wav","tags":{"kind":"attachment"}"#,
                       #""content_type":"audio/wav","tags":{"kind":"generated_media","modality":"voice","task":"tts"}"#,
                       #""content_type":"audio/wav","semantic_kind":"music""#] {
            #expect(try !artifact(fields).isConversationVoice)
        }
    }
    @Test func explicitPlaybackAndLegacyStreamAreClassified() throws {
        #expect(try artifact(#""tags":{"purpose":"voice_playback"}"#).isConversationVoice)
        #expect(try artifact(#""tags":{"kind":"generated_media","modality":"voice","task":"tts"},"raw_metadata":{"capability_metadata":{"stream":{"chunk_format":"wav-segment"}}}"#).isConversationVoice)
    }
    @Test func reservedDictationRequiresExactComponentsAndAudio() throws {
        #expect(try artifact(#""content_type":"audio/wav","source_path":"client:voice/dictation/recording.wav""#).isConversationVoice)
        for path in ["client/voice/dictation-other/a.wav", "client:voice/dictation/../a.wav", "notes/voice/dictation/a.wav"] {
            #expect(try !artifact("\"content_type\":\"audio/wav\",\"source_path\":\"\(path)\"").isConversationVoice)
        }
        #expect(try !artifact(#""content_type":"text/plain","source_path":"client:voice/dictation/notes.txt""#).isConversationVoice)
    }
    @Test func transcriptHiddenOnlyAfterProvenDictationSourceAcrossPages() throws {
        let transcript = try artifact(#""semantic_kind":"transcript","producer":{"capability_route":"audio.transcribe"},"source_refs":[{"role":"source_audio","artifact_id":"recording"}]"#)
        var audio = try artifact(#""content_type":"audio/wav","source_path":"client:voice/dictation/a.wav""#)
        audio.artifactId = "recording"
        #expect(!PhoneArtifact.classifyingConversationVoice([transcript])[0].isConversationVoice)
        #expect(PhoneArtifact.classifyingConversationVoice([transcript, audio])[0].isConversationVoice)
        audio.sourcePath = "client/ask.wav"
        #expect(!PhoneArtifact.classifyingConversationVoice([transcript, audio])[0].isConversationVoice)
    }
}

@Suite struct LegacyConversationAudioTests {
    private func fixtures() throws -> [PhoneArtifact] {
        let json = #"[{"artifact_id":"readout","run_id":"reply","content_type":"audio/wav","semantic_kind":"voice","tags":{"source":"llm_call"},"producer":{"capability_route":"tts"}},{"artifact_id":"requested","run_id":"reply","content_type":"audio/wav","semantic_kind":"voice","tags":{"source":"llm_call"},"producer":{"capability_route":"tts"}},{"artifact_id":"input","run_id":"session_memory_chat","content_type":"audio/wav","semantic_kind":"attachment","tags":{"source":"upload"},"source_path":"client:ask.wav"},{"artifact_id":"transcript","run_id":"session_memory_chat","content_type":"text/plain","semantic_kind":"transcript","producer":{"capability_route":"audio.transcribe"},"source_refs":[{"artifact_id":"input","run_id":"session_memory_chat","role":"source_audio"}]}]"#
        return try JSONDecoder().decode([JSONValue].self, from: Data(json.utf8)).compactMap(PhoneArtifact.parse)
    }
    @Test func completeHistoryProtectsRequestedExportsAndIdentifiesLinkedLegacyConversationAudio() throws {
        let rows = PhoneArtifact.classifyingConversationVoice(try fixtures(), explicitFileIDs: ["requested"])
        #expect(rows.filter(\.isConversationVoice).map(\.artifactId) == ["readout", "input", "transcript"])
        #expect(rows.first { $0.artifactId == "requested" }?.isConversationVoice == false)
        #expect(rows.filter(\.isConversationVoice).allSatisfy { $0.inferredConversationVoice })
    }
    @Test func missingHistoryNeverInfersLegacyIntent() throws {
        let rows = PhoneArtifact.classifyingConversationVoice(try fixtures(), explicitFileIDs: nil)
        #expect(rows.allSatisfy { !$0.isConversationVoice && !$0.inferredConversationVoice })
    }
    @Test func explicitlyAttachedAudioAndItsTranscriptArePreserved() throws {
        let rows = PhoneArtifact.classifyingConversationVoice(try fixtures(), explicitFileIDs: ["requested", "input"])
        #expect(rows.filter(\.isConversationVoice).map(\.artifactId) == ["readout"])
    }
    @Test func askFilenameWithoutLinkedTranscriptionDoesNotEstablishIntent() throws {
        let input = try fixtures().filter { $0.artifactId == "input" }
        #expect(PhoneArtifact.classifyingConversationVoice(input, explicitFileIDs: []).first?.isConversationVoice == false)
    }
}
