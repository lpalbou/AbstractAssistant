import Foundation
import AbstractGatewayClient

// "Create a voice" on the iPhone (the gateway's voice library, AbstractGateway 0.16.0): the two
// forms, the request each sends, and what happens to the voice once it exists. Pure, so the
// requests are tested without a screen.

public enum VoiceCreationMode: String, CaseIterable, Sendable, Identifiable {
    case description = "From a description"
    case recording = "From a recording"
    public var id: String { rawValue }
}

/// What `POST /voice/design` is sent.
public struct VoiceDesignRequest: Equatable, Sendable {
    public var description: String
    public var name: String?
    public var language: String?
    public init(description: String, name: String?, language: String?) {
        self.description = description; self.name = name; self.language = language
    }
}

/// A voice from a written description. Design needs a language (English unless chosen).
public struct VoiceDesignForm: Equatable, Sendable {
    public var description = ""
    public var name = ""
    public var language = "en"
    public init(description: String = "", name: String = "", language: String = "en") {
        self.description = description; self.name = name; self.language = language
    }
    /// Why the form cannot be sent yet (nil: it can).
    public var problem: String? {
        description.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "Describe the voice first." : nil
    }
    public var request: VoiceDesignRequest? {
        guard problem == nil else { return nil }
        let n = name.trimmingCharacters(in: .whitespacesAndNewlines)
        return VoiceDesignRequest(description: description.trimmingCharacters(in: .whitespacesAndNewlines),
                                  name: n.isEmpty ? nil : n, language: language.isEmpty ? "en" : language)
    }
}

/// A voice from a recording: recorded here (5 to 20 seconds) or chosen from Files. Its language
/// is detected by the gateway unless chosen; the selected engine clones it when it can.
public struct VoiceRecordingForm: Equatable, Sendable {
    /// The language choice that sends none: the gateway identifies it from the recording.
    public static let detect = ""
    public static let minimumSeconds: TimeInterval = 5
    public static let maximumSeconds: TimeInterval = 20
    /// The gateway's cap on a reference recording.
    public static let maximumBytes = 25 * 1024 * 1024
    /// Engines that clone a voice from a recording (AbstractVoice); another engine is not sent.
    public static let cloningEngines = ["qwen3-tts", "omnivoice", "f5_tts", "chroma", "audiodit"]
    /// What the gateway accepts, by file extension.
    public static let contentTypes: [String: String] = [
        "wav": "audio/wav", "flac": "audio/flac", "ogg": "audio/ogg", "mp3": "audio/mpeg", "m4a": "audio/mp4", "webm": "audio/webm",
    ]

    public var audio: Data?
    public var filename = ""
    /// Seconds recorded here (nil for a chosen file: its length is the gateway's to judge).
    public var recordedSeconds: TimeInterval?
    public var transcript = ""
    public var name = ""
    public var language = VoiceRecordingForm.detect
    /// The engine the assistant speaks with (the route's provider), if any.
    public var engine: String?

    public init(audio: Data? = nil, filename: String = "", recordedSeconds: TimeInterval? = nil, transcript: String = "",
                name: String = "", language: String = VoiceRecordingForm.detect, engine: String? = nil) {
        self.audio = audio; self.filename = filename; self.recordedSeconds = recordedSeconds
        self.transcript = transcript; self.name = name; self.language = language; self.engine = engine
    }

    public static func contentType(for filename: String) -> String? {
        contentTypes[(filename as NSString).pathExtension.lowercased()]
    }

    /// Why the form cannot be sent yet (nil: it can).
    public var problem: String? {
        guard let audio, !audio.isEmpty else { return "Record or choose a recording first." }
        guard Self.contentType(for: filename) != nil else { return "Choose a WAV, FLAC, OGG, MP3, M4A or WEBM recording." }
        if audio.count > Self.maximumBytes { return "The recording is larger than 25 MB. Choose a shorter one." }
        if let s = recordedSeconds, s < Self.minimumSeconds { return "Record at least 5 seconds of speech." }
        if let s = recordedSeconds, s > Self.maximumSeconds + 0.5 { return "Keep the recording under 20 seconds." }
        return nil
    }

    public var upload: VoiceCloneUpload? {
        guard problem == nil, let audio, let type = Self.contentType(for: filename) else { return nil }
        func text(_ s: String) -> String? { let t = s.trimmingCharacters(in: .whitespacesAndNewlines); return t.isEmpty ? nil : t }
        let selected = engine?.lowercased()
        return VoiceCloneUpload(audio: audio, filename: filename, contentType: type, name: text(name),
                                language: language == Self.detect ? nil : language, referenceText: text(transcript),
                                provider: selected.flatMap { Self.cloningEngines.contains($0) ? $0 : nil })
    }
}

/// What becomes of a voice once the gateway made it.
public enum VoiceCreationOutcome: Equatable, Sendable {
    /// It speaks on the engine the assistant uses: it is the assistant's voice now.
    case selected(VoiceChoice, message: String)
    /// It speaks on another engine: kept in Your voices, not selected, and said so.
    case elsewhere(message: String)
    /// The gateway has it but the catalog does not list it (yet).
    case unlisted(message: String)

    public var message: String {
        switch self { case .selected(_, let m), .elsewhere(let m), .unlisted(let m): m }
    }

    /// `catalog`: read again after the creation; `current`: the assistant's voice (nil: the
    /// gateway's default, whose engine is `catalog.defaultVoiceProvider`).
    public static func of(_ created: CreatedVoice, in catalog: VoiceCatalog, current: VoiceChoice?) -> VoiceCreationOutcome {
        let name = created.name ?? created.voiceID
        guard let entry = catalog.entries.first(where: { $0.voiceID == created.voiceID && (created.engine == nil || $0.choice.provider == created.engine) })
                ?? catalog.entries.first(where: { $0.voiceID == created.voiceID }) else {
            return .unlisted(message: "“\(name)” was created, but the gateway does not list it among its voices yet. Open this list again in a moment.")
        }
        let engine = entry.choice.provider
        guard let speaking = current?.provider ?? catalog.defaultVoiceProvider, speaking != engine else {
            return .selected(entry.choice, message: "“\(name)” is ready and is now your assistant’s voice.")
        }
        return .elsewhere(message: "“\(name)” was created on \(engine), but your assistant speaks with \(speaking), so it is not selected. Choose it under Your voices to switch.")
    }
}
