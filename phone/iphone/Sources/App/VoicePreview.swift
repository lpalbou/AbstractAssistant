import Foundation
import AbstractGatewayClient

extension VoiceController {
    static func forApp() -> VoiceController {
        #if DEBUG
        let args = ProcessInfo.processInfo.arguments
        if args.contains("--demo") && args.contains("--ui-test") && args.contains("--voice-fixture") {
            let clock = PreviewVoiceClock()
            return VoiceController(now: { clock.time }, permission: { true }, recordingFactory: { try PreviewRecording(url: $0, clock: clock) }, configureAudio: false)
        }
        #endif
        return VoiceController()
    }
}

#if DEBUG
/// Advance only for microphone samples the controller actually observes. CI stalls must not
/// become missing audio frames or consume the synthetic speech before the first sample.
@MainActor private final class PreviewVoiceClock {
    private(set) var time: TimeInterval = 0
    func sample() { time += 1.0 / 30 }
}

/// Deterministic native UI fixture; never used with a real gateway or in Release builds.
@MainActor private final class PreviewRecording: VoiceRecording {
    private let clock: PreviewVoiceClock
    private var startTime: TimeInterval = 0
    init(url: URL, clock: PreviewVoiceClock) throws {
        self.clock = clock
        try SyntheticSpeech.wav(seconds: 1, seed: 2).write(to: url)
    }
    func start() throws { startTime = clock.time }
    func stop() {}
    func power() -> (average: Float, peak: Float) {
        clock.sample()
        let elapsed = clock.time - startTime
        let db: Float = elapsed < 1.1 ? Float(-28 + sin(elapsed * 9) * 9) : -90
        return (db, db + 6)
    }
}
#endif
