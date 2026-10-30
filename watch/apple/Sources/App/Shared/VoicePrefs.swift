import AbstractGatewayClient
import Foundation

/// The voice choices made on this watch (Settings → Voice), kept on the watch and sent with each
/// request; nil is the gateway's default. They never change the gateway's defaults for others.
/// The speaking voice applies to the Assistant; an entity keeps its own voice.
enum VoicePrefs {
    private static let voiceKey = "voice.tts", transcriptionKey = "voice.stt", speedKey = "voice.speed"
    static let speeds: [Double] = [1, 1.15, 1.3, 1.5]

    static var voice: VoiceChoice? {
        get { load(voiceKey) }
        set { save(newValue, voiceKey) }
    }

    /// The saved catalog label, available even when the gateway is offline. Older choices may
    /// have no label or repeat a voice-library identifier; those still represent a selected voice.
    static var voiceLabel: String {
        guard let voice else { return "Default" }
        let label = voice.label.trimmingCharacters(in: .whitespacesAndNewlines)
        let compact = label.replacingOccurrences(of: "-", with: "")
        let opaque = compact.count >= 16 && compact.allSatisfy(\.isHexDigit)
        return label.isEmpty || opaque ? "Selected voice" : label
    }
    static var transcription: TranscriptionChoice? {
        get { load(transcriptionKey) }
        set { save(newValue, transcriptionKey) }
    }

    /// How fast the watch plays the voice (1 is as made; the pitch stays the same).
    static var speed: Double {
        get { let v = UserDefaults.standard.double(forKey: speedKey); return v > 0 ? v : 1 }
        set { UserDefaults.standard.set(newValue, forKey: speedKey) }
    }

    /// The voice for one reading: the chosen one for the Assistant's text, the entity's own otherwise.
    static func voice(for scope: SpeechScope) -> VoiceChoice? {
        if case .run = scope { return voice }
        return nil
    }

    private static func load<T: Decodable>(_ key: String) -> T? {
        UserDefaults.standard.data(forKey: key).flatMap { try? JSONDecoder().decode(T.self, from: $0) }
    }
    private static func save<T: Encodable>(_ value: T?, _ key: String) {
        if let value, let data = try? JSONEncoder().encode(value) { UserDefaults.standard.set(data, forKey: key) }
        else { UserDefaults.standard.removeObject(forKey: key) }
    }
}
