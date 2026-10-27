import Foundation

// The gateway's voice library (AbstractGateway 0.16.0, `docs/api.md` "Voice library"): whose voice
// each catalog voice is, the language it speaks, and the calls that create, rename and delete
// the person's own voices. Shared by the iPhone (which creates voices) and the watch (which lists
// them); the same rules as the desktop app and the web apps' voice picker.

/// Whose voice a catalog voice is. The order is the order a picker shows them in.
public enum VoiceGroup: String, Sendable, Codable, CaseIterable, Comparable {
    /// The person's own: cloned or designed into their voice store.
    case yours = "Your voices"
    /// The engine's own voices and presets.
    case engine = "Engine voices"
    /// The library everyone can use: the built-in voices and the voices the administrator shares.
    case shared = "Shared voices"

    public var title: String { rawValue }
    public static func < (a: VoiceGroup, b: VoiceGroup) -> Bool {
        allCases.firstIndex(of: a)! < allCases.firstIndex(of: b)!
    }
}

/// One voice of the catalog with what the picker shows about it. `choice` is what is stored and
/// sent with speech; the rest is read from the gateway's record.
public struct VoiceEntry: Hashable, Sendable, Identifiable {
    public var choice: VoiceChoice
    public var group: VoiceGroup
    /// The voice's native language (ISO 639-1, lowercased), when the gateway says.
    public var language: String?
    /// Other languages it speaks (`languages`); empty with no native language = unrestricted.
    public var languages: [String]
    /// A sentence about the voice (`tags.description`).
    public var summary: String?
    public var id: String { choice.id }
    /// The id the voice library knows it by (`voice_id`): what rename and delete address.
    public var voiceID: String { choice.voice }
    /// The person may rename and delete it (shared voices are read-only).
    public var isOwn: Bool { group == .yours }

    public init(choice: VoiceChoice, group: VoiceGroup = .engine, language: String? = nil, languages: [String] = [], summary: String? = nil) {
        self.choice = choice; self.group = group; self.language = language; self.languages = languages; self.summary = summary
    }

    /// The voice speaks `code`: it is its native language or one it lists. A voice with neither
    /// (no native language and no listed languages: AbstractVoice's `languages: []` on remote and
    /// OpenAI voices) is unrestricted and speaks every language. Empty `code` = no filter.
    public func speaks(_ code: String) -> Bool {
        let wanted = code.lowercased()
        if wanted.isEmpty { return true }
        if language == wanted { return true }
        if language == nil && languages.isEmpty { return true }
        return languages.contains(wanted)
    }
}

/// The rules of the voice library, as pure functions over the gateway's records.
public enum VoiceLibrary {
    /// A record is a cloned voice by its own `kind` first: the gateway's catalog merge sets
    /// `voice_kind: "voice"` on a clone its engine also lists among its voices (AbstractVoice lists
    /// every clone in both), while the record's `kind` stays `"clone"`.
    public static func isClone(_ record: JSONValue) -> Bool {
        (record["kind"]?.stringValue ?? record["voice_kind"]?.stringValue) == "clone"
    }

    /// Whose voice: `tags.builtin`, or a clone whose `params.meta.scope` is `library`, is shared;
    /// any other clone is the person's own; everything else is the engine's.
    public static func group(_ record: JSONValue) -> VoiceGroup {
        if case .bool(true)? = record["tags"]?["builtin"] { return .shared }
        guard isClone(record) else { return .engine }
        let scope = record["params"]?["meta"]?["scope"]?.stringValue ?? record["meta"]?["scope"]?.stringValue
        return scope == "library" ? .shared : .yours
    }

    /// The native language: `language`, else `tags.language_code`, else the clone's own record's.
    public static func language(_ record: JSONValue) -> String? {
        let raw = record["language"]?.stringValue ?? record["tags"]?["language_code"]?.stringValue
            ?? record["params"]?["language"]?.stringValue ?? record["params"]?["meta"]?["language"]?.stringValue
        let code = (raw ?? "").trimmingCharacters(in: .whitespaces).lowercased()
        return code.isEmpty ? nil : code
    }

    /// The languages a record lists (`languages`), lowercased.
    public static func languages(_ record: JSONValue) -> [String] {
        (record["languages"]?.arrayValue ?? []).compactMap { $0.stringValue?.lowercased() }.filter { !$0.isEmpty }
    }

    /// The native languages of a catalog, for the "Voices that speak…" filter (sorted codes).
    public static func languages(of entries: [VoiceEntry]) -> [String] {
        Array(Set(entries.compactMap(\.language))).sorted()
    }

    /// The languages a voice can be created in (the gateway's design and cloning languages).
    public static let creationLanguages = ["en", "fr", "de", "es", "it", "pt", "ru", "zh", "ja", "ko"]

    private static let names: [String: String] = [
        "en": "English", "fr": "French", "de": "German", "es": "Spanish", "it": "Italian", "pt": "Portuguese",
        "ru": "Russian", "zh": "Chinese", "ja": "Japanese", "ko": "Korean", "nl": "Dutch", "pl": "Polish",
        "tr": "Turkish", "ar": "Arabic", "hi": "Hindi",
    ]
    /// "fr" → "French"; an unknown code stays as it is.
    public static func languageName(_ code: String) -> String { names[code.lowercased()] ?? code }

    /// The voices that speak `language` (empty: all), in groups (yours, engine, shared), empty groups
    /// left out; within a group the catalog's order. `keep` stays listed whatever the filter (the
    /// chosen voice never disappears from under its checkmark).
    public static func grouped(_ entries: [VoiceEntry], speaking language: String = "", keep: VoiceChoice? = nil) -> [(group: VoiceGroup, entries: [VoiceEntry])] {
        let visible = entries.filter { $0.speaks(language) || $0.choice == keep }
        return VoiceGroup.allCases.compactMap { group in
            let rows = visible.filter { $0.group == group }
            return rows.isEmpty ? nil : (group, rows)
        }
    }

    /// The catalog entry of a record from `GET /voice/voices` (`items[]`), or nil when it names no
    /// voice to speak with. An engine voice needs `params {provider, model, voice}` (as before); a
    /// cloned voice is spoken by its `voice_id` on its engine (`provider`), with the model the
    /// record names, else the engine's first listed model (`tts_models_by_provider`), else none
    /// (the engine's default).
    static func entry(_ record: JSONValue, modelsByProvider: JSONValue?) -> VoiceEntry? {
        let params = record["params"]
        let provider: String, model: String, voice: String
        if isClone(record) {
            guard let p = params?["provider"]?.stringValue ?? record["provider"]?.stringValue ?? record["engine"]?.stringValue, !p.isEmpty,
                  let v = params?["voice"]?.stringValue ?? record["voice_id"]?.stringValue ?? record["id"]?.stringValue, !v.isEmpty
            else { return nil }
            provider = p; voice = v
            model = params?["model"]?.stringValue ?? record["model"]?.stringValue ?? modelsByProvider?[p]?.arrayValue?.first?.stringValue ?? ""
        } else {
            guard let p = params?["provider"]?.stringValue, let m = params?["model"]?.stringValue, let v = params?["voice"]?.stringValue else { return nil }
            provider = p; model = m; voice = v
        }
        let label = record["label"]?.stringValue ?? record["name"]?.stringValue ?? voice
        let summary = record["tags"]?["description"]?.stringValue?.trimmingCharacters(in: .whitespacesAndNewlines)
        return VoiceEntry(choice: VoiceChoice(provider: provider, model: model, voice: voice, label: label, gender: record["tags"]?["gender"]?.stringValue),
                          group: group(record), language: language(record), languages: languages(record),
                          summary: (summary ?? "").isEmpty ? nil : summary)
    }

    /// A voice id the library route can carry as one path segment.
    public static func validVoiceID(_ id: String) -> Bool { PhoneArtifact.validID(id) }
}

/// A voice the gateway just created (`POST /voice/design`, `POST /voice/clones`): its stored record.
public struct CreatedVoice: Decodable, Sendable, Equatable {
    public var voiceID: String
    public var name: String?
    /// The engine it speaks on (`engine`).
    public var engine: String?
    public var language: String?
    public init(voiceID: String, name: String? = nil, engine: String? = nil, language: String? = nil) {
        self.voiceID = voiceID; self.name = name; self.engine = engine; self.language = language
    }
    enum CodingKeys: String, CodingKey { case voiceID = "voice_id", name, engine, language, meta }
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        voiceID = try c.decode(String.self, forKey: .voiceID)
        name = try c.decodeIfPresent(String.self, forKey: .name)
        let meta = try c.decodeIfPresent(JSONValue.self, forKey: .meta)
        engine = try c.decodeIfPresent(String.self, forKey: .engine) ?? meta?["engine"]?.stringValue
        language = try c.decodeIfPresent(String.self, forKey: .language) ?? meta?["language"]?.stringValue
    }
}

/// A recording to clone a voice from (`POST /voice/clones`, multipart).
public struct VoiceCloneUpload: Sendable, Equatable {
    public var audio: Data
    public var filename: String
    public var contentType: String
    public var name: String?
    /// The recording's language; nil: the gateway identifies it.
    public var language: String?
    /// What the recording says; nil: the gateway transcribes it where the engine can.
    public var referenceText: String?
    /// The cloning engine; nil: the gateway's default.
    public var provider: String?
    public init(audio: Data, filename: String, contentType: String, name: String? = nil, language: String? = nil, referenceText: String? = nil, provider: String? = nil) {
        self.audio = audio; self.filename = filename; self.contentType = contentType
        self.name = name; self.language = language; self.referenceText = referenceText; self.provider = provider
    }

    /// The form fields sent besides the file, in order (absent values are not sent).
    public var fields: [(String, String)] {
        [("name", name), ("language", language), ("reference_text", referenceText), ("provider", provider)]
            .compactMap { key, value in
                guard let v = value?.trimmingCharacters(in: .whitespacesAndNewlines), !v.isEmpty else { return nil }
                return (key, v)
            }
    }
    public static func == (a: Self, b: Self) -> Bool {
        a.audio == b.audio && a.filename == b.filename && a.contentType == b.contentType && a.fields.map { "\($0.0)=\($0.1)" } == b.fields.map { "\($0.0)=\($0.1)" }
    }
}

struct VoiceDesignBody: Encodable {
    var description: String
    var name: String?
    var language: String?
}

struct VoiceRenameBody: Encodable { var name: String }

// MARK: Live calls

extension LiveGatewayClient {
    /// `POST /voice/design {description, name?, language?}`. Designing loads an engine on first use:
    /// minutes, not seconds.
    public func designVoice(description: String, name: String?, language: String?) async throws -> CreatedVoice {
        let body = VoiceDesignBody(description: description, name: name.flatMap { $0.isEmpty ? nil : $0 }, language: language.flatMap { $0.isEmpty ? nil : $0 })
        let data = try await voiceLibraryRequest("POST", "api/gateway/voice/design", body: body)
        return try JSONDecoder().decode(CreatedVoice.self, from: data)
    }

    /// `POST /voice/clones` (multipart: `file`, then `name`, `language`, `reference_text`, `provider` when given).
    public func cloneVoice(_ upload: VoiceCloneUpload) async throws -> CreatedVoice {
        let boundary = "voice-" + UUID().uuidString
        var body = Data()
        for (key, value) in upload.fields {
            body.append(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(key)\"\r\n\r\n\(value)\r\n".utf8))
        }
        let filename = PhoneArtifact.safeFilename(upload.filename)
        body.append(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"\(filename)\"\r\nContent-Type: \(upload.contentType)\r\n\r\n".utf8))
        body.append(upload.audio)
        body.append(Data("\r\n--\(boundary)--\r\n".utf8))
        let data = try await voiceLibraryRequest("POST", "api/gateway/voice/clones", raw: body, contentType: "multipart/form-data; boundary=\(boundary)")
        return try JSONDecoder().decode(CreatedVoice.self, from: data)
    }

    /// `PATCH /voice/clones/{id} {name}`: the person's own voices only (a shared voice: 422).
    public func renameVoice(id: String, name: String) async throws {
        guard VoiceLibrary.validVoiceID(id) else { throw GatewayError.invalidResponse }
        _ = try await voiceLibraryRequest("PATCH", "api/gateway/voice/clones/\(id)", body: VoiceRenameBody(name: name))
    }

    /// `DELETE /voice/clones/{id}`: the voice and its reference recording (a shared voice: 422).
    public func deleteVoice(id: String) async throws {
        guard VoiceLibrary.validVoiceID(id) else { throw GatewayError.invalidResponse }
        _ = try await voiceLibraryRequest("DELETE", "api/gateway/voice/clones/\(id)")
    }
}
