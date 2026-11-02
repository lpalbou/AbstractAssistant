import Foundation
import Testing
@testable import AbstractGatewayClient

/// ADR 0047: a spoken question's recording and an answer read aloud are transport, never
/// attachments or media of the conversation — whatever a history bundle turn lists.
@Suite struct SessionTurnVoiceTransportTests {
    private let turn = """
    {"run_id":"r1","status":"completed","prompt":"Tell me","answer":"Here",
     "attachments":[
       {"artifact_id":"a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1","content_type":"audio/wav","filename":"ask.wav",
        "tags":{"kind":"attachment","modality":"audio","path":"client:voice/dictation/x.wav"}},
       {"artifact_id":"a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2","content_type":"audio/wav","filename":"ask.wav",
        "tags":{"kind":"attachment","purpose":"voice_dictation","artifact_space":"voice"}},
       {"artifact_id":"a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3","content_type":"application/pdf","filename":"report.pdf","tags":{"kind":"attachment"}}],
     "artifacts":[
       {"artifact_id":"b1b1b1b1b1b1b1b1b1b1b1b1b1b1b1b1","content_type":"audio/wav","filename":"tts-1.wav",
        "tags":{"kind":"generated_media","purpose":"voice_playback","artifact_space":"voice","path":"voice/tts-1.wav"}},
       {"artifact_id":"b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2","content_type":"image/png","filename":"sunset.png","tags":{"kind":"generated_media"}},
       {"artifact_id":"b3b3b3b3b3b3b3b3b3b3b3b3b3b3b3b3","content_type":"text/plain","filename":"node_trace.txt","tags":{"kind":"trace"}}]}
    """

    @Test func voiceTransportNeverBecomesAnAttachmentOrMedia() throws {
        let decoded = try JSONDecoder().decode(SessionTurn.self, from: Data(turn.utf8))
        #expect(decoded.attachments.map(\.filename) == ["report.pdf"])
        #expect(decoded.artifacts.map(\.artifactId) == ["b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2"])
        #expect(decoded.artifacts.first?.runId == "r1")   // a row without an owner belongs to its turn
    }

    @Test func theRuleIsDecidedByTagsNotByFileName() {
        #expect(SessionTurn.isVoiceTransport(["tags": .object(["purpose": .string("voice_playback")])]))
        #expect(SessionTurn.isVoiceTransport(["tags": .object(["purpose": .string("voice_dictation")])]))
        #expect(SessionTurn.isVoiceTransport(["tags": .object(["artifact_space": .string("voice")])]))
        #expect(SessionTurn.isVoiceTransport(["tags": .object(["path": .string("client:voice/dictation/a.wav")])]))
        #expect(!SessionTurn.isVoiceTransport(["content_type": .string("audio/wav"), "filename": .string("tts-song.wav"), "tags": .object(["kind": .string("generated_media")])]))
    }
}
