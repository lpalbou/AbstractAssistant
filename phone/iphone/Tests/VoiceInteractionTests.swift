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
        return LiveGatewayClient(baseURL: URL(string: "https://gateway.example")!, token: "fixture", session: URLSession(configuration: config), readTries: 1)
    }
    @MainActor private func waitUntilRecording(_ voice: VoiceController) async throws {
        for _ in 0..<100 { if voice.recording { return }; try await Task.sleep(for: .milliseconds(5)) }
        XCTFail("Recorder did not start")
    }
    @MainActor private func advance(_ voice: VoiceController, clock: VoiceClock, to target: Double) {
        while clock.time + 0.03 < target { clock.time += 0.03; voice.sample() }
        clock.time = target; voice.sample()
    }
    @MainActor func testSpeechBufferingRemainsWorkingAndCancelPreventsLateChunks() async throws {
        let voice = VoiceController(configureAudio: false)
        defer { voice.stop() }
        let client = MockGatewayClient(world: .phone, speechPreparationDelay: 0.7)
        voice.read("Two streamed chunks", client: client, scope: .run("test"), messageID: "buffered")
        XCTAssertTrue(voice.preparing)
        func waitFor(_ predicate: () -> Bool) async throws {
            let deadline = ContinuousClock.now.advanced(by: .seconds(6))
            while !predicate(), ContinuousClock.now < deadline { try await Task.sleep(for: .milliseconds(10)) }
            XCTAssertTrue(predicate())
        }
        try await waitFor { voice.speaking && !voice.preparing }
        try await waitFor { voice.speaking && voice.preparing }
        XCTAssertEqual(voice.readingID, "buffered")
        voice.stop()
        try await Task.sleep(for: .milliseconds(1000))
        XCTAssertFalse(voice.preparing); XCTAssertFalse(voice.speaking); XCTAssertNil(voice.readingID)
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
    /// The reading is requested in pieces (two sentences, two pieces here); the mock's second piece
    /// times out twice, then plays: the reading ends whole, with no error, in four requests.
    @MainActor func testALostPieceIsRequestedAgainAndTheReadingGoesOn() async throws {
        resetStalledVoice(); defer { resetStalledVoice() }
        MockGatewayClient.stalledVoiceFailures = 2...3
        let voice = VoiceController(configureAudio: false, pieceTarget: 30); defer { voice.stop() }   // two sentences, two pieces
        voice.read("The first sentence is here. The second sentence is there.", client: MockGatewayClient(world: .phone), scope: .run("test"), messageID: "m1")
        XCTAssertTrue(voice.speaking)
        for _ in 0..<160 { if !voice.speaking { break }; try await Task.sleep(for: .milliseconds(100)) }
        XCTAssertFalse(voice.speaking, "the reading did not end")
        XCTAssertNil(voice.error)
        XCTAssertEqual(MockGatewayClient.stalledVoiceCalls, 4)
    }

    /// The second piece's request and its three retries time out: the reading ends after the first
    /// piece with "The voice stopped early. Tap play to continue." Reading the same message again
    /// requests the second piece only (one more request), and ends well.
    @MainActor func testAPieceLostForGoodStopsEarlyAndReadingAgainGoesOnFromIt() async throws {
        resetStalledVoice(); defer { resetStalledVoice() }
        MockGatewayClient.stalledVoiceFailures = 2...5
        let voice = VoiceController(configureAudio: false, pieceTarget: 30); defer { voice.stop() }   // two sentences, two pieces
        let text = "The first sentence is here. The second sentence is there."
        voice.read(text, client: MockGatewayClient(world: .phone), scope: .run("test"), messageID: "m1")
        for _ in 0..<200 { if !voice.speaking { break }; try await Task.sleep(for: .milliseconds(100)) }
        XCTAssertFalse(voice.speaking, "the reading did not end")
        XCTAssertEqual(voice.error, "The voice stopped early. Tap play to continue.")
        XCTAssertEqual(MockGatewayClient.stalledVoiceCalls, 5)
        voice.read(text, client: MockGatewayClient(world: .phone), scope: .run("test"), messageID: "m1")
        XCTAssertNil(voice.error); XCTAssertTrue(voice.speaking); XCTAssertEqual(voice.readingID, "m1")
        for _ in 0..<80 { if !voice.speaking { break }; try await Task.sleep(for: .milliseconds(100)) }
        XCTAssertFalse(voice.speaking, "the resumed reading did not end")
        XCTAssertNil(voice.error)
        XCTAssertEqual(MockGatewayClient.stalledVoiceCalls, 6, "reading again must request the lost piece only")
    }

    /// Three pieces, 2 s of sound each, scheduled back to back on the one engine: playback ends
    /// after about the summed duration (no gap, no overlap, no re-play), with no error.
    @MainActor func testThreeChunksPlayBackToBackForTheirSummedDuration() async throws {
        resetStalledVoice(); defer { resetStalledVoice() }
        MockGatewayClient.stalledVoiceFailures = 100...100   // never fails: one 2 s chunk per piece
        let voice = VoiceController(configureAudio: false, pieceTarget: 30); defer { voice.stop() }
        voice.read("The first sentence is here. The second sentence is there. The third one ends it.", client: MockGatewayClient(world: .phone), scope: .run("test"))
        var started: ContinuousClock.Instant?
        for _ in 0..<440 {
            if started == nil, !voice.preparing { started = .now }
            if started != nil, !voice.speaking { break }
            try await Task.sleep(for: .milliseconds(25))
        }
        let elapsed = started.map { $0.duration(to: .now) } ?? .zero
        XCTAssertFalse(voice.speaking, "the reading did not end"); XCTAssertNil(voice.error)
        XCTAssertEqual(MockGatewayClient.stalledVoiceCalls, 3)
        XCTAssertEqual(voice.playedSeconds, 6.0, accuracy: 0.05)
        XCTAssertGreaterThan(elapsed, .seconds(5.6)); XCTAssertLessThan(elapsed, .seconds(7.2), "the three chunks did not play back to back (\(elapsed))")
    }

    /// The mock's stall settings back to their defaults (a test sets the ones it needs).
    private func resetStalledVoice() {
        MockGatewayClient.stalledVoiceFailures = nil; MockGatewayClient.stalledVoiceCalls = 0; MockGatewayClient.stalledVoiceChunks = 1
        MockGatewayClient.stalledVoiceYieldsBeforeFailing = 0; MockGatewayClient.stalledVoiceStall = .zero
    }

    /// The second piece's stream sends its whole sound, then breaks: that sound plays (the retry's
    /// 2 s wait is covered by it) and the retry's copy of it is skipped, never heard twice — 4 s
    /// played, not 6, with no silence between the pieces.
    @MainActor func testSoundThatArrivedBeforeABreakPlaysOnceAndCoversTheRetry() async throws {
        resetStalledVoice(); defer { resetStalledVoice() }
        MockGatewayClient.stalledVoiceFailures = 2...2; MockGatewayClient.stalledVoiceYieldsBeforeFailing = 1
        let voice = VoiceController(configureAudio: false, pieceTarget: 30); defer { voice.stop() }
        voice.read("The first sentence is here. The second sentence is there.", client: MockGatewayClient(world: .phone), scope: .run("test"))
        var wentQuiet = false
        for _ in 0..<400 {
            if !voice.speaking { break }
            if voice.playedSeconds > 0.5, voice.preparing { wentQuiet = true }
            try await Task.sleep(for: .milliseconds(25))
        }
        XCTAssertFalse(voice.speaking, "the reading did not end"); XCTAssertNil(voice.error)
        XCTAssertEqual(MockGatewayClient.stalledVoiceCalls, 3)
        XCTAssertEqual(voice.playedSeconds, 4.0, accuracy: 0.05, "the retry's copy was played (6 s) or the sound that arrived was dropped (2 s)")
        XCTAssertFalse(wentQuiet, "the sound that arrived before the break should have played through the retry's wait")
    }

    /// Council 2026-11-02 A3 + A4. The second piece's stream sends two of its four half-second
    /// chunks, stays quiet until they have partly played (the node then starves for about 2 s: its
    /// timeline runs on over silence), and breaks. Every chunk that arrived plays out whole, the
    /// retry skips exactly that second and plays the other: the person hears the text's 4 s once.
    /// After the stall the playhead is placed again, so the sound waiting is the retry's second,
    /// not "nothing" (the node's own clock ran 2 s ahead).
    @MainActor func testAPieceBrokenMidwayIsHeardOnceAndThePlayheadSurvivesTheStall() async throws {
        resetStalledVoice(); defer { resetStalledVoice() }
        MockGatewayClient.stalledVoiceFailures = 2...2; MockGatewayClient.stalledVoiceChunks = 4
        MockGatewayClient.stalledVoiceYieldsBeforeFailing = 2; MockGatewayClient.stalledVoiceStall = .milliseconds(2500)
        let voice = VoiceController(configureAudio: false, pieceTarget: 30); defer { voice.stop() }
        voice.read("The first sentence is here. The second sentence is there.", client: MockGatewayClient(world: .phone), scope: .run("test"))
        var starved = false, aheadAfterStall: Double?
        for _ in 0..<600 {
            if !voice.speaking { break }
            if voice.playedSeconds >= 2.9, voice.preparing { starved = true }
            if starved, aheadAfterStall == nil, !voice.preparing { aheadAfterStall = voice.aheadSeconds() }
            try await Task.sleep(for: .milliseconds(20))
        }
        XCTAssertFalse(voice.speaking, "the reading did not end"); XCTAssertNil(voice.error)
        XCTAssertEqual(MockGatewayClient.stalledVoiceCalls, 3)
        XCTAssertTrue(starved, "the stall should have left nothing to play for a while")
        XCTAssertEqual(voice.playedSeconds, 4.0, accuracy: 0.05, "a sound was heard twice (more) or one was cut (less)")
        // About 1 s waits right after the retry's sound is scheduled (the poll may read it a little
        // late on a busy machine); a playhead that ran on during the stall reads 0.
        XCTAssertGreaterThan(aheadAfterStall ?? 0, 0.3, "after the stall the playhead ran ahead of the sound: \(String(describing: aheadAfterStall))")
        XCTAssertLessThanOrEqual(aheadAfterStall ?? 9, 1.01)
    }

    /// A call (an interruption) pauses the reading and keeps it; its end, with the system's
    /// go-ahead, resumes it where it stopped: the reading ends whole.
    @MainActor func testAnInterruptionPausesTheReadingAndItsEndResumesIt() async throws {
        resetStalledVoice(); defer { resetStalledVoice() }
        MockGatewayClient.stalledVoiceFailures = 100...100                              // never fails: 2 s a piece
        let voice = VoiceController(configureAudio: false, pieceTarget: 30); defer { voice.stop() }
        voice.read("The first sentence is here. The second sentence is there.", client: MockGatewayClient(world: .phone), scope: .run("test"))
        for _ in 0..<200 { if voice.playedSeconds >= 2 { break }; try await Task.sleep(for: .milliseconds(20)) }
        func post(_ type: AVAudioSession.InterruptionType, resume: Bool = false) {
            var info: [AnyHashable: Any] = [AVAudioSessionInterruptionTypeKey: type.rawValue]
            if resume { info[AVAudioSessionInterruptionOptionKey] = AVAudioSession.InterruptionOptions.shouldResume.rawValue }
            NotificationCenter.default.post(name: AVAudioSession.interruptionNotification, object: nil, userInfo: info)
        }
        post(.began)
        for _ in 0..<50 { if voice.paused { break }; try await Task.sleep(for: .milliseconds(10)) }
        XCTAssertTrue(voice.paused, "the interruption did not pause the reading"); XCTAssertTrue(voice.speaking)
        let held = voice.playedSeconds
        try await Task.sleep(for: .milliseconds(1500))
        XCTAssertEqual(voice.playedSeconds, held, "the reading went on during the call")
        XCTAssertNil(voice.error)
        post(.ended, resume: true)
        for _ in 0..<50 { if !voice.paused { break }; try await Task.sleep(for: .milliseconds(10)) }
        XCTAssertFalse(voice.paused, "the end of the interruption did not resume the reading")
        for _ in 0..<300 { if !voice.speaking { break }; try await Task.sleep(for: .milliseconds(20)) }
        XCTAssertFalse(voice.speaking, "the resumed reading did not end"); XCTAssertNil(voice.error)
        XCTAssertEqual(voice.playedSeconds, 4.0, accuracy: 0.05)
    }

    /// The person paused: the end of an interruption never resumes a reading it did not pause.
    @MainActor func testAnInterruptionsEndLeavesAReadingThePersonPaused() async throws {
        resetStalledVoice(); defer { resetStalledVoice() }
        MockGatewayClient.stalledVoiceFailures = 100...100
        let voice = VoiceController(configureAudio: false, pieceTarget: 30); defer { voice.stop() }
        voice.read("The first sentence is here. The second sentence is there.", client: MockGatewayClient(world: .phone), scope: .run("test"))
        for _ in 0..<200 { if voice.playedSeconds >= 2 { break }; try await Task.sleep(for: .milliseconds(20)) }
        voice.togglePause(); XCTAssertTrue(voice.paused)
        NotificationCenter.default.post(name: AVAudioSession.interruptionNotification, object: nil, userInfo: [AVAudioSessionInterruptionTypeKey: AVAudioSession.InterruptionType.began.rawValue])
        NotificationCenter.default.post(name: AVAudioSession.interruptionNotification, object: nil, userInfo: [
            AVAudioSessionInterruptionTypeKey: AVAudioSession.InterruptionType.ended.rawValue,
            AVAudioSessionInterruptionOptionKey: AVAudioSession.InterruptionOptions.shouldResume.rawValue])
        try await Task.sleep(for: .milliseconds(300))
        XCTAssertTrue(voice.paused, "an interruption's end resumed a reading the person had paused"); XCTAssertTrue(voice.speaking)
    }

    @MainActor func testSpeakingSpeedAppliesToActualPlaybackAndNewPreviewReplacesOld() async throws {
        let voice = VoiceController(); defer { voice.stop() }
        voice.read("First sample", client: MockGatewayClient(world: .phone), scope: .run("test"), speed: 1.15)
        for _ in 0..<100 { if !voice.preparing { break }; try await Task.sleep(for: .milliseconds(20)) }
        XCTAssertEqual(voice.playbackRate, 1.15, accuracy: 0.001)
        voice.read("Second sample", client: MockGatewayClient(world: .phone), scope: .entity("castor"), speed: 1.5)
        for _ in 0..<100 { if !voice.preparing { break }; try await Task.sleep(for: .milliseconds(20)) }
        XCTAssertEqual(voice.playbackRate, 1.5, accuracy: 0.001)
        XCTAssertTrue(voice.speaking); XCTAssertNil(voice.error)
        voice.stop(); XCTAssertFalse(voice.preparing); XCTAssertFalse(voice.speaking)
    }
    @MainActor func testActualWAVPlaybackDrivesTheMeterAndStopsCleanly() async throws {
        let voice = VoiceController()
        defer { voice.stop() }
        voice.read("A test phrase", client: MockGatewayClient(world: .phone), scope: .run("test"))
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
