import Foundation
import Observation
import AbstractGatewayClient

@MainActor @Observable public final class PhonePreferences {
    public var readAloud: Bool { didSet { defaults.set(readAloud, forKey: prefix + "readAloud") } }
    public var voice: VoiceChoice? { didSet { save(voice, "voice") } }
    public var transcription: TranscriptionChoice? { didSet { save(transcription, "transcription") } }
    @ObservationIgnored private let defaults: UserDefaults
    @ObservationIgnored private let prefix: String
    public init(scope: String = "demo", defaults: UserDefaults = .standard) {
        self.defaults = defaults; prefix = "phone.preferences." + scope + "."
        readAloud = defaults.bool(forKey: prefix + "readAloud")
        voice = defaults.data(forKey: prefix + "voice").flatMap { try? JSONDecoder().decode(VoiceChoice.self, from: $0) }
        transcription = defaults.data(forKey: prefix + "transcription").flatMap { try? JSONDecoder().decode(TranscriptionChoice.self, from: $0) }
    }
    private func save<T: Encodable>(_ value: T?, _ key: String) {
        if let value, let data = try? JSONEncoder().encode(value) { defaults.set(data, forKey: prefix + key) }
        else { defaults.removeObject(forKey: prefix + key) }
    }
}
