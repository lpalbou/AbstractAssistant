import Foundation
import Testing
@testable import AbstractGatewayClient

/// Pins how a history-bundle session turn (`session.turns[]`) is projected today, so the
/// server-side projection work (ADR 0047 and the proposed per-turn `voice` block) can change the
/// wire shape without silently changing what the watch and the phone show.
///
/// Today's contract: `attachments` are the question's files as sent (every kind, voice transport
/// dropped); `artifacts` keep only `tags.kind == generated_media` (voice transport dropped); a row
/// without `run_id` belongs to the turn, a row with one keeps it (a sub-run's media stays
/// attributed to that sub-run); unknown fields are ignored.
@Suite struct SessionTurnProjectionTests {
    private func decode(_ json: String) throws -> SessionTurn {
        try JSONDecoder().decode(SessionTurn.self, from: Data(json.utf8))
    }

    @Test func unknownFieldsAreIgnoredIncludingAVoiceBlock() throws {
        // The server may add `kind`, `workflow_id`, `prompt_metadata`, `stats`, `answer_meta`,
        // `prompt_verbatim` and (proposed) `voice` without breaking the decode.
        let turn = try decode("""
        {"run_id":"r1","kind":"conversation","workflow_id":"@default","status":"completed",
         "created_at":"2026-11-02T10:00:00Z","updated_at":"2026-11-02T10:00:09Z",
         "prompt":"Hello","prompt_verbatim":"Hello","prompt_metadata":{"input_channel":"voice"},
         "answer":"Hi","answer_meta":{"model":"m"},"stats":{"tool_calls":2},
         "voice":{"dictation":{"$artifact":"d1d1d1d1d1d1d1d1d1d1d1d1d1d1d1d1","run_id":"session_memory_s1"},
                  "playback":[{"$artifact":"p1p1p1p1p1p1p1p1p1p1p1p1p1p1p1p1","run_id":"r1"}]},
         "attachments":[],"artifacts":[]}
        """)
        #expect(turn.runId == "r1")
        #expect(turn.prompt == "Hello" && turn.answer == "Hi" && turn.status == "completed")
        #expect(turn.createdAt == "2026-11-02T10:00:00Z")
        #expect(turn.attachments.isEmpty && turn.artifacts.isEmpty)
    }

    @Test func attachmentsKeepEveryKindWhileArtifactsKeepOnlyGeneratedMedia() throws {
        let turn = try decode("""
        {"run_id":"r1","prompt":"Look","answer":"Done",
         "attachments":[
           {"artifact_id":"a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1","content_type":"application/pdf","filename":"report.pdf","tags":{"kind":"attachment"}},
           {"artifact_id":"a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2","content_type":"image/jpeg","filename":"photo.jpg"},
           {"$artifact":"a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3","run_id":"session_memory_s1","content_type":"text/plain","filename":"notes.txt","tags":{"kind":"trace"}}],
         "artifacts":[
           {"artifact_id":"b1b1b1b1b1b1b1b1b1b1b1b1b1b1b1b1","content_type":"image/png","filename":"sunset.png","tags":{"kind":"generated_media"}},
           {"artifact_id":"b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2","content_type":"image/png","filename":"untagged.png"},
           {"artifact_id":"b3b3b3b3b3b3b3b3b3b3b3b3b3b3b3b3","content_type":"text/plain","filename":"node_trace.txt","tags":{"kind":"trace"}},
           {"artifact_id":"b4b4b4b4b4b4b4b4b4b4b4b4b4b4b4b4","content_type":"audio/wav","filename":"song.wav","tags":{"kind":"generated_media","modality":"music"}}]}
        """)
        // Attachments: the kind tag does not filter; a `$artifact` reference form is accepted.
        #expect(turn.attachments.map(\.filename) == ["report.pdf", "photo.jpg", "notes.txt"])
        #expect(turn.attachments[2].runId == "session_memory_s1")
        // Artifacts: the session listing's rule — generated media only, whatever the content type.
        #expect(turn.artifacts.map(\.filename) == ["sunset.png", "song.wav"])
    }

    @Test func ownerlessRowsBelongToTheTurnAndOwnedRowsKeepTheirRun() throws {
        // A piece made inside an agent's sub-run arrives with that sub-run's `run_id` (the runtime
        // walks descendants); the turn it belongs to is the turn whose list carries it.
        let turn = try decode("""
        {"run_id":"root","answer":"Made two",
         "artifacts":[
           {"artifact_id":"c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1","run_id":"child_run_1","content_type":"image/png","filename":"a.png","tags":{"kind":"generated_media"}},
           {"artifact_id":"c2c2c2c2c2c2c2c2c2c2c2c2c2c2c2c2","run_id":null,"content_type":"image/png","filename":"b.png","tags":{"kind":"generated_media"}},
           {"artifact_id":"c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1","run_id":"child_run_1","content_type":"image/png","filename":"a-again.png","tags":{"kind":"generated_media"}}]}
        """)
        #expect(turn.artifacts.map(\.runId) == ["child_run_1", "root"])
        #expect(turn.artifacts.map(\.filename) == ["a.png", "b.png"])   // a repeated artifact id is one row
        #expect(turn.artifacts.first?.ref["run_id"] == .string("child_run_1"))  // content reads go to the owner
    }

    @Test func missingOrMalformedListsDecodeToEmptyAndAMissingRunIdFails() throws {
        let sparse = try decode(#"{"run_id":"r1","attachments":"nope","artifacts":{"not":"a list"}}"#)
        #expect(sparse.attachments.isEmpty && sparse.artifacts.isEmpty && sparse.prompt == nil && sparse.answer == nil)
        // A row without an id, a non-object row, or an id that is not path-safe (`PhoneArtifact.validID`:
        // alphanumerics and `_-.` only, never `.`/`..`) is dropped; the length of an id is not checked.
        let rowsWithoutIds = try decode(#"{"run_id":"r1","attachments":[{"filename":"x.pdf"},"text",null],"artifacts":[{"artifact_id":"../escape","tags":{"kind":"generated_media"}},{"artifact_id":"a/b","run_id":"r1","tags":{"kind":"generated_media"}}]}"#)
        #expect(rowsWithoutIds.attachments.isEmpty && rowsWithoutIds.artifacts.isEmpty)
        let shortId = try decode(#"{"run_id":"r1","artifacts":[{"artifact_id":"short","content_type":"image/png","tags":{"kind":"generated_media"}}]}"#)
        #expect(shortId.artifacts.map(\.artifactId) == ["short"])
        #expect(throws: (any Error).self) { try decode(#"{"prompt":"no run id"}"#) }
    }

    @Test func bundleSessionTurnsDecodeAndAMissingSessionIsNil() throws {
        let bundle = try JSONDecoder().decode(HistoryBundle.self, from: Data("""
        {"run":{"run_id":"r2"},"ledgers":{},"session":{"session_id":"s1","turns":[
           {"run_id":"r2","created_at":"2026-11-02T10:05:00Z","prompt":"second"},
           {"run_id":"r1","created_at":"2026-11-02T10:00:00Z","prompt":"first","voice":{}}]}}
        """.utf8))
        #expect(bundle.session?.turns?.map(\.runId) == ["r2", "r1"])   // the client sorts by created_at afterwards
        let noSession = try JSONDecoder().decode(HistoryBundle.self, from: Data(#"{"run":{"run_id":"r2"},"ledgers":{}}"#.utf8))
        #expect(noSession.session == nil)
    }

    /// PROPOSED CONTRACT (not implemented): each session turn carries a typed `voice` block —
    /// `{"dictation": {"$artifact", "run_id"} | null, "playback": [{"$artifact", "run_id"}]}` —
    /// so a view can show a mic glyph on a spoken question or replay a reading without the
    /// recordings ever being attachments or media. The shared `SessionTurn` would expose it as
    /// `voice: SessionTurn.Voice?` (dictation ref, playback refs). Enabled once the gateway
    /// serves the block and the model decodes it; until then it documents the seam.
    @Test(.disabled("proposed `voice` block on session turns (ADR 0047 follow-up): SessionTurn.voice not implemented"))
    func voiceBlockDecodesDictationAndPlaybackReferences() throws {
        let turn = try decode("""
        {"run_id":"r1","prompt":"Spoken","answer":"Read aloud",
         "voice":{"dictation":{"$artifact":"d1d1d1d1d1d1d1d1d1d1d1d1d1d1d1d1","run_id":"session_memory_s1"},
                  "playback":[{"$artifact":"p1p1p1p1p1p1p1p1p1p1p1p1p1p1p1p1","run_id":"r1"}]},
         "attachments":[],"artifacts":[]}
        """)
        let labels = Mirror(reflecting: turn).children.compactMap(\.label)
        #expect(labels.contains("voice"), "SessionTurn exposes the turn's voice block")
        #expect(turn.attachments.isEmpty && turn.artifacts.isEmpty, "voice transport is never an attachment or media")
    }
}
