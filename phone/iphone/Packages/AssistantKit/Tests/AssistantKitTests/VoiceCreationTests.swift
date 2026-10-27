import Foundation
import Testing
import AssistantKit
import AbstractGatewayClient

// "Create a voice" on the iPhone: the request each form sends, and what becomes of the new voice.

@Suite struct VoiceCreationFormTests {
    @Test func aDescriptionSendsItsWordsNameAndLanguage() {
        var form = VoiceDesignForm()
        #expect(form.problem == "Describe the voice first." && form.request == nil)
        form.description = "  A calm, warm adult voice  "
        #expect(form.request == VoiceDesignRequest(description: "A calm, warm adult voice", name: nil, language: "en"))
        form.name = " Narrator "; form.language = "fr"
        #expect(form.request == VoiceDesignRequest(description: "A calm, warm adult voice", name: "Narrator", language: "fr"))
    }

    @Test func aRecordingDetectsItsLanguageUnlessChosen() throws {
        var form = VoiceRecordingForm(audio: Data([1, 2, 3]), filename: "voice.m4a", recordedSeconds: 8)
        #expect(form.language == VoiceRecordingForm.detect)
        let detected = try #require(form.upload)
        #expect(detected.language == nil)
        #expect(detected.fields.map(\.0).contains("language") == false)
        form.language = "fr"
        #expect(form.upload?.language == "fr")
    }

    @Test func aRecordingSendsItsFileTranscriptNameAndCloningEngine() throws {
        let form = VoiceRecordingForm(audio: Data([1, 2, 3]), filename: "voice.m4a", recordedSeconds: 8, transcript: " Hello there. ",
                                      name: " Me ", language: "en", engine: "qwen3-tts")
        let upload = try #require(form.upload)
        #expect(upload == VoiceCloneUpload(audio: Data([1, 2, 3]), filename: "voice.m4a", contentType: "audio/mp4", name: "Me",
                                           language: "en", referenceText: "Hello there.", provider: "qwen3-tts"))
        // An engine that cannot clone is not sent: the gateway's cloning engine does it.
        #expect(VoiceRecordingForm(audio: Data([1]), filename: "a.wav", recordedSeconds: 6, engine: "supertonic").upload?.provider == nil)
        #expect(VoiceRecordingForm(audio: Data([1]), filename: "a.wav", recordedSeconds: 6, engine: "omnivoice").upload?.provider == "omnivoice")
    }

    @Test func aRecordingIsFiveToTwentySecondsInAnAcceptedFormat() {
        #expect(VoiceRecordingForm().problem == "Record or choose a recording first.")
        #expect(VoiceRecordingForm(audio: Data([1]), filename: "a.wav", recordedSeconds: 3).problem == "Record at least 5 seconds of speech.")
        #expect(VoiceRecordingForm(audio: Data([1]), filename: "a.wav", recordedSeconds: 25).problem == "Keep the recording under 20 seconds.")
        #expect(VoiceRecordingForm(audio: Data([1]), filename: "a.aiff").problem == "Choose a WAV, FLAC, OGG, MP3, M4A or WEBM recording.")
        #expect(VoiceRecordingForm(audio: Data(count: VoiceRecordingForm.maximumBytes + 1), filename: "a.wav").problem != nil)
        // A chosen file's length is the gateway's to judge.
        #expect(VoiceRecordingForm(audio: Data([1]), filename: "Interview.MP3").problem == nil)
        for ext in ["wav", "flac", "ogg", "mp3", "m4a", "webm"] { #expect(VoiceRecordingForm.contentType(for: "x.\(ext)") != nil) }
    }
}

@Suite struct VoiceCreationOutcomeTests {
    private let catalog = VoiceCatalog(entries: [
        VoiceEntry(choice: VoiceChoice(provider: "supertonic", model: "supertonic-3", voice: "F2", label: "F2"), group: .engine, language: "en"),
        VoiceEntry(choice: VoiceChoice(provider: "qwen3-tts", model: "Qwen3-TTS-12Hz-1.7B-Base", voice: "v-1", label: "Narrator"), group: .yours, language: "en"),
    ], transcription: [], defaultVoice: nil, defaultTranscription: nil, defaultVoiceProvider: "supertonic")
    private let created = CreatedVoice(voiceID: "v-1", name: "Narrator", engine: "qwen3-tts")

    @Test func aVoiceOnTheAssistantsEngineIsSelected() {
        let current = VoiceChoice(provider: "qwen3-tts", model: "Qwen3-TTS-12Hz-1.7B-Base", voice: "aiden", label: "Aiden")
        let outcome = VoiceCreationOutcome.of(created, in: catalog, current: current)
        #expect(outcome == .selected(catalog.entries[1].choice, message: "“Narrator” is ready and is now your assistant’s voice."))
    }

    @Test func aVoiceOnAnotherEngineIsNotSelectedAndSaysSo() {
        // The assistant follows the gateway's default (supertonic): the qwen3-tts voice is not selected.
        let outcome = VoiceCreationOutcome.of(created, in: catalog, current: nil)
        guard case .elsewhere(let message) = outcome else { Issue.record("selected on another engine: \(outcome)"); return }
        #expect(message.contains("qwen3-tts") && message.contains("supertonic") && message.contains("Your voices"))
    }

    @Test func aVoiceTheCatalogDoesNotListIsSaid() {
        let outcome = VoiceCreationOutcome.of(CreatedVoice(voiceID: "v-9", name: "Later"), in: catalog, current: nil)
        guard case .unlisted(let message) = outcome else { Issue.record("\(outcome)"); return }
        #expect(message.contains("Later"))
    }
}
