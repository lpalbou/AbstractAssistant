import XCTest

/// A reading is requested in pieces: a piece whose stream breaks is requested again while what
/// arrived plays, and a piece lost for good ends the reading with "The voice stopped early. Tap the
/// speaker to continue." — the tap goes on from that piece, never from the start. Sample data on
/// the Read page: `--piece-chars 80` cuts the sample answer's two sentences into two pieces of 2 s
/// each; `--stalled-voice` makes the second piece's first two requests time out,
/// `--stalled-voice-fatal` its first four, `--stalled-voice-midpiece` the second piece's first
/// request send half its sound, stay quiet until that half has partly played, and break.
final class StalledVoiceUITests: XCTestCase {
    private var app: XCUIApplication!
    private var voice: XCUIElement { app.buttons["voice.button"].firstMatch }
    private var position: XCUIElement { app.staticTexts["debug.position"].firstMatch }
    private var stopped: XCUIElement { app.staticTexts["The voice stopped early. Tap the speaker to continue."].firstMatch }
    private func seconds() -> Double { Double(position.label) ?? -1 }

    /// The Read page, its sample answer being read aloud from the start.
    private func reading(_ mode: String) {
        app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--screen", "read", "--piece-chars", "80", mode]
        app.launch()
        XCTAssertTrue(voice.waitForExistence(timeout: 20), app.debugDescription)
        let started = Date()
        while seconds() < 0.5 && Date().timeIntervalSince(started) < 20 { usleep(200_000) }
        XCTAssertGreaterThanOrEqual(seconds(), 0.5, "the voice did not start:\n\(app.debugDescription)")
    }

    /// Waits for the reading to end (the button reads "Read aloud" again) without the position ever
    /// falling under `floor` (a reading that started over would drop to 0). Returns the furthest position seen.
    private func waitForEnd(floor: Double, timeout: TimeInterval) -> Double {
        let started = Date()
        var top = seconds()
        while Date().timeIntervalSince(started) < timeout {
            let now = seconds()
            XCTAssertGreaterThanOrEqual(now, floor - 0.3, "the reading started over instead of going on")
            top = max(top, now)
            // The reading may end between the two reads: its final position is the one to keep.
            if voice.label == "Read aloud", now >= floor { top = max(top, seconds()); break }
            usleep(250_000)
        }
        return top
    }

    func testALostPieceIsRequestedAgainWhileTheVoiceGoesOn() throws {
        reading("--stalled-voice")
        let top = waitForEnd(floor: 0.5, timeout: 30)
        // Two pieces of 2 s: the second arrived on its third request (two timed out, 2 s apart).
        XCTAssertGreaterThanOrEqual(top, 3.8, "the second piece never played:\n\(app.debugDescription)")
        XCTAssertFalse(stopped.exists, "a piece requested again was reported as lost")
        XCTAssertEqual(voice.label, "Read aloud")
    }

    /// Council 2026-11-02 A3: the half of the second piece that arrived plays out, and the retry
    /// skips it: the reading is its two pieces' 4 s, heard once (a replay of the half made it 5 s).
    func testAPieceBrokenMidwayIsHeardOnce() throws {
        reading("--stalled-voice-midpiece")
        let top = waitForEnd(floor: 0.5, timeout: 40)
        XCTAssertGreaterThanOrEqual(top, 3.8, "the second piece's sound was lost:\n\(app.debugDescription)")
        XCTAssertLessThan(top, 4.4, "the second piece's first half was heard twice (\(top) s)")
        XCTAssertFalse(stopped.exists, "a piece requested again was reported as lost")
        XCTAssertEqual(voice.label, "Read aloud")
    }

    func testAPieceLostForGoodEndsEarlyAndTheSpeakerGoesOnFromIt() throws {
        reading("--stalled-voice-fatal")
        XCTAssertTrue(stopped.waitForExistence(timeout: 30), "the lost piece did not end the reading with its line:\n\(app.debugDescription)")
        let before = seconds()
        XCTAssertGreaterThanOrEqual(before, 1.8, "the first piece did not play out before the reading ended")
        XCTAssertLessThan(before, 3.0, "the second piece played although every request for it timed out")
        voice.tap()                                              // on from the second piece
        XCTAssertTrue(stopped.waitForNonExistence(timeout: 5), "the line stayed after the tap")
        let top = waitForEnd(floor: before, timeout: 30)
        XCTAssertGreaterThanOrEqual(top, before + 1.8, "the second piece did not play after the tap:\n\(app.debugDescription)")
        XCTAssertFalse(stopped.exists, "the reading did not end well after the tap")
        XCTAssertEqual(voice.label, "Read aloud")
    }
}
