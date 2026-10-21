import Foundation
import Observation
import AbstractGatewayClient

@MainActor @Observable public final class PhonePreferences {
    public var autoSendVoice: Bool { didSet { defaults.set(autoSendVoice, forKey: prefix + "autoSendVoice") } }
    public var readAloud: Bool { didSet { defaults.set(readAloud, forKey: prefix + "readAloud") } }
    public var showMessageStats: Bool { didSet { defaults.set(showMessageStats, forKey: prefix + "showMessageStats") } }
    public var voice: VoiceChoice? { didSet { save(voice, "voice") } }
    public var speed: Double { didSet { if !Self.speeds.contains(speed) { speed = 1 }; defaults.set(speed, forKey: prefix + "speed") } }
    public nonisolated static let speeds: [Double] = [1, 1.15, 1.3, 1.5]
    public nonisolated static func validSpeed(_ value: Double) -> Double { speeds.contains(value) ? value : 1 }
    public var transcription: TranscriptionChoice? { didSet { save(transcription, "transcription") } }
    @ObservationIgnored private let defaults: UserDefaults
    @ObservationIgnored private let prefix: String
    public init(scope: String = "demo", defaults: UserDefaults = .standard) {
        self.defaults = defaults; prefix = "phone.preferences." + scope + "."
        speed = Self.validSpeed(defaults.double(forKey: prefix + "speed"))
        readAloud = defaults.bool(forKey: prefix + "readAloud")
        autoSendVoice = defaults.bool(forKey: prefix + "autoSendVoice")
        showMessageStats = defaults.bool(forKey: prefix + "showMessageStats")
        voice = defaults.data(forKey: prefix + "voice").flatMap { try? JSONDecoder().decode(VoiceChoice.self, from: $0) }
        transcription = defaults.data(forKey: prefix + "transcription").flatMap { try? JSONDecoder().decode(TranscriptionChoice.self, from: $0) }
    }
    private func save<T: Encodable>(_ value: T?, _ key: String) {
        if let value, let data = try? JSONEncoder().encode(value) { defaults.set(data, forKey: prefix + key) }
        else { defaults.removeObject(forKey: prefix + key) }
    }
}
