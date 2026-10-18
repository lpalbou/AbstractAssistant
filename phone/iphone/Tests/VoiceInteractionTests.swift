import XCTest
import AVFoundation
import SwiftUI
import AssistantKit
import AbstractGatewayClient
@testable import AbstractAssistantPhone

private final class VoiceRequestLog: @unchecked Sendable {
    private let lock = NSLock()
    private var paths: [String] = []
    func append(_ path: String) { lock.lock(); defer { lock.unlock() }; paths.append(path) }
    var count: Int { lock.lock(); defer { lock.unlock() }; return paths.count }
    func clear() { lock.lock(); defer { lock.unlock() }; paths = [] }
}
private final class VoiceWire: URLProtocol, @unchecked Sendable {
    static let log = VoiceRequestLog()
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let path = request.url!.path; Self.log.append(path)
        let json = path.hasSuffix("attachments/upload") ? #"{"run_id":"session_memory_test","artifact":{"$artifact":"voice1"}}"# : #"{"text":"A voice turn"}"#
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(json.utf8)); client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}
@MainActor private final class TestRecording: VoiceRecording {
    var powerDB: Float = -28
    var stopped = false
    let url: URL
    init(url: URL) throws { self.url = url; try SyntheticSpeech.wav(seconds: 0.5, seed: 1).write(to: url) }
    func start() throws {}
    func stop() { stopped = true }
    func power() -> (average: Float, peak: Float) { (powerDB, powerDB + 6) }
}

@MainActor private final class VoiceClock { var time: TimeInterval = 0 }
final class VoiceInteractionTests: XCTestCase {
    private func client() -> LiveGatewayClient {
        VoiceWire.log.clear()
        let config = URLSessionConfiguration.ephemeral; config.protocolClasses = [VoiceWire.self]
        return LiveGatewayClient(baseURL: URL(string: "https://gateway.example")!, token: "fixture", session: URLSession(configuration: config))
    }
    @MainActor private func waitUntilRecording(_ voice: VoiceController) async throws {
        for _ in 0..<100 { if voice.recording { return }; try await Task.sleep(for: .milliseconds(5)) }
        XCTFail("Recorder did not start")
    }
    @MainActor private func advance(_ voice: VoiceController, clock: VoiceClock, to target: Double) {
        while clock.time + 0.03 < target { clock.time += 0.03; voice.sample() }
        clock.time = target; voice.sample()
    }
    @MainActor func testSilenceMakesZeroGatewayCallsAndTouchDownCancelsAcrossDeadline() async throws {
        let clock = VoiceClock(); var recorder: TestRecording?
        let voice = VoiceController(now: { clock.time }, permission: { true }, recordingFactory: { url in let r = try TestRecording(url: url); recorder = r; return r }, configureAudio: false)
        defer { voice.stop() }; let client = client()
        voice.activate(); try await waitUntilRecording(voice)
        recorder?.powerDB = -42; advance(voice, clock: clock, to: 0.3); let quiet = voice.meter.level
        recorder?.powerDB = -15; advance(voice, clock: clock, to: 0.6)
        // Microphone visualization uses its recent range, so quiet speech is already
        // deliberately visible; it must not depend on playback-sized amplitudes.
        XCTAssertGreaterThan(quiet, 0.6)
        XCTAssertGreaterThan(voice.meter.level, 0.8)
        recorder?.powerDB = -90; advance(voice, clock: clock, to: 1.3)
        XCTAssertEqual(voice.inputPhase, .countdown); XCTAssertFalse(recorder!.stopped)
        let premature = await voice.finish(client: client, sessionID: "test")
        XCTAssertNil(premature); XCTAssertEqual(VoiceWire.log.count, 0)
        advance(voice, clock: clock, to: 3.59); voice.stop() // Touch down just before 3s silence ends.
        advance(voice, clock: clock, to: 8)
        XCTAssertEqual(voice.inputPhase, .idle); XCTAssertTrue(recorder!.stopped)
        XCTAssertEqual(VoiceWire.log.count, 0); XCTAssertEqual(voice.meter.level, 0)
        XCTAssertFalse(FileManager.default.fileExists(atPath: recorder!.url.deletingLastPathComponent().path))
    }
    @MainActor private func attachRecorderOrb(_ voice: VoiceController, name: String) throws {
        let renderer = ImageRenderer(content:
            AssistantOrb(size: 136, active: true, level: voice.meter.level, listening: true, animationTime: 2)
                .frame(width: 240, height: 240).background(PhoneTheme.ground)
        )
        renderer.scale = 3
        let attachment = XCTAttachment(image: try XCTUnwrap(renderer.uiImage))
        attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
    }
    @MainActor func testQuietMicrophoneSpeechUsesTheVisibleRangeAndKeepsTheRawSilenceDeadline() async throws {
        let clock = VoiceClock(); var recorder: TestRecording?
        let voice = VoiceController(now: { clock.time }, permission: { true }, recordingFactory: { url in
            let r = try TestRecording(url: url); r.powerDB = -70; recorder = r; return r
        }, configureAudio: false)
        defer { voice.stop() }; _ = client()
        voice.activate(); try await waitUntilRecording(voice)
        advance(voice, clock: clock, to: 0.3)
        let roomLevel = voice.meter.level
        XCTAssertLessThan(roomLevel, 0.02)
        try attachRecorderOrb(voice, name: "Recorder fixture — room -70 dBFS")
        recorder?.powerDB = -48; advance(voice, clock: clock, to: 0.6)
        let speechLevel = voice.meter.level
        XCTAssertGreaterThan(speechLevel, 0.7)
        try attachRecorderOrb(voice, name: "Recorder fixture — quiet speech -48 dBFS")
        XCTAssertEqual(voice.inputPhase, .recording)
        recorder?.powerDB = -70; advance(voice, clock: clock, to: 1.1)
        let pauseLevel = voice.meter.level
        XCTAssertLessThan(pauseLevel, 0.05)
        XCTAssertEqual(voice.inputPhase, .countdown)
        advance(voice, clock: clock, to: 3.599)
        XCTAssertEqual(voice.inputPhase, .countdown)
        XCTAssertEqual(VoiceWire.log.count, 0)
        advance(voice, clock: clock, to: 3.6)
        XCTAssertEqual(voice.inputPhase, .ready)
        XCTAssertEqual(VoiceWire.log.count, 0) // Visualization never uploads or sends by itself.
        let samples = XCTAttachment(string: "Injected recorder, not a physical microphone measurement\ntime_seconds,input_dBFS,normalized_level\n0.3,-70,\(roomLevel)\n0.6,-48,\(speechLevel)\n1.1,-70,\(pauseLevel)")
        samples.name = "Quiet microphone recorder wiring"; samples.lifetime = .keepAlways; add(samples)
    }
    @MainActor func testThreeQuietSecondsUploadAndTranscribeExactlyOnce() async throws {
        let clock = VoiceClock(); var recorder: TestRecording?
        let voice = VoiceController(now: { clock.time }, permission: { true }, recordingFactory: { url in let r = try TestRecording(url: url); recorder = r; return r }, configureAudio: false)
        defer { voice.stop() }; let client = client()
        voice.activate(); try await waitUntilRecording(voice); advance(voice, clock: clock, to: 0.3)
        recorder?.powerDB = -90; advance(voice, clock: clock, to: 3.299)
        XCTAssertEqual(VoiceWire.log.count, 0); XCTAssertEqual(voice.inputPhase, .countdown)
        advance(voice, clock: clock, to: 3.3); XCTAssertEqual(voice.inputPhase, .ready); XCTAssertTrue(recorder!.stopped)
        let text = await voice.finish(client: client, sessionID: "test")
        XCTAssertEqual(text, "A voice turn"); XCTAssertEqual(VoiceWire.log.count, 2)
        XCTAssertFalse(FileManager.default.fileExists(atPath: recorder!.url.deletingLastPathComponent().path))
        let duplicate = await voice.finish(client: client, sessionID: "test")
        XCTAssertNil(duplicate); XCTAssertEqual(VoiceWire.log.count, 2)
    }
    @MainActor func testSpeechResumingBeforeSilenceExpiresKeepsEverythingLocal() async throws {
        let clock = VoiceClock(); var recorder: TestRecording?
        let voice = VoiceController(now: { clock.time }, permission: { true }, recordingFactory: { url in let r = try TestRecording(url: url); recorder = r; return r }, configureAudio: false)
        defer { voice.stop() }; let client = client()
        voice.activate(); try await waitUntilRecording(voice); advance(voice, clock: clock, to: 0.3)
        recorder?.powerDB = -90; advance(voice, clock: clock, to: 3.28)
        recorder?.powerDB = -25; advance(voice, clock: clock, to: 3.29)
        XCTAssertEqual(voice.inputPhase, .recording)
        recorder?.powerDB = -90; advance(voice, clock: clock, to: 6.28)
        let premature = await voice.finish(client: client, sessionID: "test")
        XCTAssertNil(premature); XCTAssertEqual(VoiceWire.log.count, 0)
        advance(voice, clock: clock, to: 6.29)
        let text = await voice.finish(client: client, sessionID: "test")
        XCTAssertEqual(text, "A voice turn"); XCTAssertEqual(VoiceWire.log.count, 2)
    }
    @MainActor func testNoSpeechAndSustainedNoiseTimeoutWithoutSending() async throws {
        for db: Float in [-90, -20] {
            let clock = VoiceClock()
            let voice = VoiceController(now: { clock.time }, permission: { true }, recordingFactory: { url in let r = try TestRecording(url: url); r.powerDB = db; return r }, configureAudio: false)
            let client = client(); voice.activate(); try await waitUntilRecording(voice)
            advance(voice, clock: clock, to: db == -90 ? 8 : 61)
            XCTAssertEqual(voice.inputPhase, .idle); XCTAssertNotNil(voice.error)
            let text = await voice.finish(client: client, sessionID: "test")
            XCTAssertNil(text); XCTAssertEqual(VoiceWire.log.count, 0); voice.stop()
        }
    }
    @MainActor func testPermissionGrantAfterCancelCannotStartTheMicrophone() async throws {
        var reply: CheckedContinuation<Bool, Never>?; var captures = 0
        let voice = VoiceController(permission: { await withCheckedContinuation { reply = $0 } }, recordingFactory: { url in captures += 1; return try TestRecording(url: url) }, configureAudio: false)
        defer { voice.stop() }; voice.activate()
        for _ in 0..<100 { if reply != nil { break }; await Task.yield() }
        XCTAssertNotNil(reply); voice.stop(); reply?.resume(returning: true)
        for _ in 0..<10 { await Task.yield() }
        XCTAssertEqual(voice.inputPhase, .idle); XCTAssertEqual(captures, 0)
    }
    @MainActor func testAudioInterruptionCancelsLocalSilenceCountdown() async throws {
        let clock = VoiceClock(); var recorder: TestRecording?
        let voice = VoiceController(now: { clock.time }, permission: { true }, recordingFactory: { url in let r = try TestRecording(url: url); recorder = r; return r }, configureAudio: false)
        defer { voice.stop() }; let client = client()
        voice.activate(); try await waitUntilRecording(voice); advance(voice, clock: clock, to: 0.3)
        recorder?.powerDB = -90; advance(voice, clock: clock, to: 1.3)
        XCTAssertEqual(voice.inputPhase, .countdown)
        NotificationCenter.default.post(name: AVAudioSession.interruptionNotification, object: nil, userInfo: [AVAudioSessionInterruptionTypeKey: AVAudioSession.InterruptionType.began.rawValue])
        for _ in 0..<10 { await Task.yield() }
        advance(voice, clock: clock, to: 8)
        let cancelled = await voice.finish(client: client, sessionID: "test")
        XCTAssertNil(cancelled)
        XCTAssertEqual(voice.inputPhase, .idle); XCTAssertEqual(VoiceWire.log.count, 0)
    }
    @MainActor func testPermissionWhileInactiveCannotStartTheMicrophone() async throws {
        var captures = 0
        let voice = VoiceController(permission: { true }, recordingFactory: { url in captures += 1; return try TestRecording(url: url) }, configureAudio: false, isActive: { false })
        defer { voice.stop() }; voice.activate()
        for _ in 0..<150 { if voice.inputPhase == .idle { break }; try await Task.sleep(for: .milliseconds(10)) }
        XCTAssertEqual(voice.inputPhase, .idle); XCTAssertEqual(captures, 0)
    }
    @MainActor func testRecordingLimitWinsOverAFinalSilenceSample() async throws {
        let clock = VoiceClock(); var recorder: TestRecording?
        let voice = VoiceController(now: { clock.time }, permission: { true }, recordingFactory: { url in let r = try TestRecording(url: url); recorder = r; return r }, configureAudio: false)
        defer { voice.stop() }; let client = client()
        voice.activate(); try await waitUntilRecording(voice); advance(voice, clock: clock, to: 57)
        recorder?.powerDB = -90; advance(voice, clock: clock, to: 59.99)
        XCTAssertEqual(voice.inputPhase, .countdown)
        advance(voice, clock: clock, to: 60)
        XCTAssertEqual(voice.inputPhase, .idle)
        let text = await voice.finish(client: client, sessionID: "test")
        XCTAssertNil(text); XCTAssertEqual(VoiceWire.log.count, 0)
    }
    @MainActor func testSpeakingSpeedAppliesToActualPlaybackAndNewPreviewReplacesOld() async throws {
        let voice = VoiceController(); defer { voice.stop() }
        voice.read("First sample", client: MockGatewayClient(), scope: .run("test"), speed: 1.15)
        for _ in 0..<100 { if !voice.preparing { break }; try await Task.sleep(for: .milliseconds(20)) }
        XCTAssertEqual(voice.playbackRate, 1.15, accuracy: 0.001)
        voice.read("Second sample", client: MockGatewayClient(), scope: .entity("castor"), speed: 1.5)
        for _ in 0..<100 { if !voice.preparing { break }; try await Task.sleep(for: .milliseconds(20)) }
        XCTAssertEqual(voice.playbackRate, 1.5, accuracy: 0.001)
        XCTAssertTrue(voice.speaking); XCTAssertNil(voice.error)
        voice.stop(); XCTAssertFalse(voice.preparing); XCTAssertFalse(voice.speaking)
    }
    @MainActor func testActualWAVPlaybackDrivesTheMeterAndStopsCleanly() async throws {
        let voice = VoiceController()
        defer { voice.stop() }
        voice.read("A test phrase", client: MockGatewayClient(), scope: .run("test"))
        var levels: [Double] = []
        for _ in 0..<110 {
            try await Task.sleep(for: .milliseconds(30)); levels.append(voice.meter.level)
        }
        XCTAssertNil(voice.error)
        XCTAssertGreaterThan(levels.max() ?? 0, 0.3)
        XCTAssertGreaterThan((levels.max() ?? 0) - (levels.min() ?? 0), 0.25)
        // Exclude initial synthesis silence: energy must fluctuate during actual playback.
        let interior = Array(levels.dropFirst(35).prefix(55))
        XCTAssertGreaterThan((interior.max() ?? 0) - (interior.min() ?? 0), 0.15)
        let trace = XCTAttachment(string: "elapsed_seconds,level\n" + levels.enumerated().map { String(format: "%.3f,%.4f", Double($0.offset + 1) * 0.03, $0.element) }.joined(separator: "\n"))
        trace.name = "WAV playback energy samples"; trace.lifetime = .keepAlways; add(trace)
        voice.togglePause(); try await Task.sleep(for: .milliseconds(400))
        XCTAssertLessThan(voice.meter.level, 0.06)
        voice.stop(); try await Task.sleep(for: .milliseconds(100))
        XCTAssertEqual(voice.meter.level, 0); XCTAssertFalse(voice.speaking)
    }
}
