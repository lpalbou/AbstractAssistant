import Foundation
import AbstractGatewayClient

extension VoiceController {
    static func forApp() -> VoiceController {
        #if DEBUG
        let args = ProcessInfo.processInfo.arguments
        if args.contains("--demo") && args.contains("--ui-test") && args.contains("--voice-fixture") {
            return VoiceController(permission: { true }, recordingFactory: { try PreviewRecording(url: $0) }, configureAudio: false)
        }
        #endif
        return VoiceController()
    }
}

#if DEBUG
/// Deterministic native UI fixture; never used with a real gateway or in Release builds.
@MainActor private final class PreviewRecording: VoiceRecording {
    private var startTime: TimeInterval = 0
    init(url: URL) throws { try SyntheticSpeech.wav(seconds: 1, seed: 2).write(to: url) }
    func start() throws { startTime = ProcessInfo.processInfo.systemUptime }
    func stop() {}
    func power() -> (average: Float, peak: Float) {
        let db = Float(-38 + sin((ProcessInfo.processInfo.systemUptime - startTime) * 9) * 20)
        return (db, db + 6)
    }
}
#endif
