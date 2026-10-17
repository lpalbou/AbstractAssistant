import XCTest
import AVFoundation
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
    var powerDB: Float = -40
    var stopped = false
    init(url: URL) throws { try SyntheticSpeech.wav(seconds: 0.5, seed: 1).write(to: url) }
    func start() throws {}
    func stop() { stopped = true }
    func power() -> (average: Float, peak: Float) { (powerDB, powerDB + 6) }
}

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
    @MainActor func testGraceMakesZeroGatewayCallsAndTouchDownCancelsAcrossDeadline() async throws {
        var clock: TimeInterval = 0; var recorder: TestRecording?
        let voice = VoiceController(now: { clock }, permission: { true }, recordingFactory: { url in let r = try TestRecording(url: url); recorder = r; return r }, configureAudio: false)
        defer { voice.stop() }
        let client = client()
        voice.press(); try await waitUntilRecording(voice)
        voice.sample(); let quiet = voice.meter.level
        recorder?.powerDB = -15; voice.sample()
        XCTAssertGreaterThan(voice.meter.level, quiet * 2)
        clock = 1; voice.release(); XCTAssertTrue(recorder!.stopped)
        XCTAssertEqual(voice.inputPhase, .countdown)
        let premature = await voice.finish(client: client, sessionID: "test")
        XCTAssertNil(premature); XCTAssertEqual(VoiceWire.log.count, 0)
        clock = 3.99; voice.sample(); voice.press() // DOWN before deadline, UP much later.
        clock = 8; voice.sample(); voice.release()
        XCTAssertEqual(voice.inputPhase, .idle); XCTAssertEqual(VoiceWire.log.count, 0)
        XCTAssertEqual(voice.meter.level, 0)
    }
    @MainActor func testUncancelledGraceUploadsAndTranscribesExactlyOnce() async throws {
        var clock: TimeInterval = 0
        let voice = VoiceController(now: { clock }, permission: { true }, recordingFactory: { try TestRecording(url: $0) }, configureAudio: false)
        defer { voice.stop() }
        let client = client()
        voice.press(); try await waitUntilRecording(voice); clock = 1; voice.release()
        clock = 3.99; voice.sample(); XCTAssertEqual(VoiceWire.log.count, 0)
        clock = 4; voice.sample(); voice.sample(); XCTAssertEqual(voice.inputPhase, .ready)
        let text = await voice.finish(client: client, sessionID: "test")
        XCTAssertEqual(text, "A voice turn"); XCTAssertEqual(VoiceWire.log.count, 2)
        let duplicate = await voice.finish(client: client, sessionID: "test")
        XCTAssertNil(duplicate); XCTAssertEqual(VoiceWire.log.count, 2)
    }
    @MainActor func testPermissionGrantAfterReleaseCannotStartTheMicrophone() async throws {
        var reply: CheckedContinuation<Bool, Never>?; var captures = 0
        let voice = VoiceController(permission: { await withCheckedContinuation { reply = $0 } }, recordingFactory: { url in captures += 1; return try TestRecording(url: url) }, configureAudio: false)
        defer { voice.stop() }
        voice.press()
        for _ in 0..<100 { if reply != nil { break }; await Task.yield() }
        XCTAssertNotNil(reply); voice.release(); reply?.resume(returning: true)
        for _ in 0..<10 { await Task.yield() }
        XCTAssertEqual(voice.inputPhase, .idle); XCTAssertEqual(captures, 0)
    }
    @MainActor func testRecordingLimitAndAudioInterruptionNeverSendAHeldMessage() async throws {
        var clock: TimeInterval = 0
        let voice = VoiceController(now: { clock }, permission: { true }, recordingFactory: { try TestRecording(url: $0) }, configureAudio: false)
        defer { voice.stop() }
        let client = client()
        voice.press(); try await waitUntilRecording(voice); clock = 65; voice.sample()
        XCTAssertEqual(voice.inputPhase, .atLimit); clock = 70; voice.sample()
        XCTAssertEqual(voice.inputPhase, .atLimit)
        let held = await voice.finish(client: client, sessionID: "test"); XCTAssertNil(held)
        XCTAssertEqual(VoiceWire.log.count, 0)
        voice.release(); XCTAssertEqual(voice.inputPhase, .countdown)
        NotificationCenter.default.post(name: AVAudioSession.interruptionNotification, object: nil, userInfo: [AVAudioSessionInterruptionTypeKey: AVAudioSession.InterruptionType.began.rawValue])
        for _ in 0..<10 { await Task.yield() }
        clock = 80; voice.sample()
        XCTAssertEqual(voice.inputPhase, .idle); XCTAssertEqual(VoiceWire.log.count, 0)
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
