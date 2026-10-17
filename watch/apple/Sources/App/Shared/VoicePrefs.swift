import AbstractGatewayClient
import Foundation

/// The voice choices made on this watch (Settings → Voice), kept on the watch and sent with each
/// request; nil is the gateway's default. They never change the gateway's defaults for others.
/// The speaking voice applies to the Assistant; an entity keeps its own voice.
enum VoicePrefs {
    private static let voiceKey = "voice.tts", transcriptionKey = "voice.stt"

    static var voice: VoiceChoice? {
        get { load(voiceKey) }
        set { save(newValue, voiceKey) }
    }
    static var transcription: TranscriptionChoice? {
        get { load(transcriptionKey) }
        set { save(newValue, transcriptionKey) }
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
