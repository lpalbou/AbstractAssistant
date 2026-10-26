import XCTest

/// The voice button, attacked the way a finger uses it (sample data, whose voice arrives as the
/// public gateway's does: two words, then the rest about 3.4 s later). `SHOTS_DIR` gets screenshots.
final class VoiceButtonUITests: XCTestCase {
    private var app: XCUIApplication!

    private func shot(_ name: String) {
        guard let dir = ProcessInfo.processInfo.environment["SHOTS_DIR"] else { return }
        try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent(name + ".png"))
    }
    private var voice: XCUIElement { app.buttons["voice.button"].firstMatch }
    private func seconds() -> Double { Double(app.staticTexts["debug.position"].firstMatch.label) ?? -1 }
    /// The orb went to listening: its status says so, or the voice button is gone with "who answers".
    private func listening() -> Bool {
        app.staticTexts["Listening…"].exists || app.buttons["Send what you said"].exists || app.alerts.count > 0
    }
    /// Waits for the label to settle (the voice being made shows "Making the voice").
    private func settledLabel(timeout: TimeInterval = 10) -> String {
        let end = Date().addingTimeInterval(timeout)
        while voice.label == "Making the voice" && Date() < end { usleep(200_000) }
        return voice.label
    }

    /// Once the voice has started it never stops before the end: no break after the first words.
    /// With LIVE_ASK=1 the watch's own sign-in and the gateway's real voice read a reply that starts
    /// with two words ("Ah oui,").
    func testNoBreakAfterTheFirstWords() throws {
        app = XCUIApplication()
        let live = ProcessInfo.processInfo.environment["LIVE_ASK"] == "1"
        app.launchArguments = live
            ? ["--no-notification-prompt", "--test-read",
               "Ah oui, je vois très bien ce que tu veux dire, et voici ce que je propose pour la suite de notre discussion sur ce sujet passionnant."]
            : ["--mock", "--no-notification-prompt", "--screen", "read"]
        app.launch()
        XCTAssertTrue(voice.waitForExistence(timeout: 20))
        var started: Date?, lastMove = Date(), last = -1.0, longest = 0.0
        let end = Date().addingTimeInterval(live ? 60 : 30)
        while Date() < end {
            let s = seconds()
            if s > 0.15 && started == nil { started = Date(); lastMove = Date(); last = s }
            if started != nil {
                if s > last + 0.05 { longest = max(longest, Date().timeIntervalSince(lastMove)); lastMove = Date(); last = s }
                if s >= 8.5 { break }
            }
            usleep(150_000)
        }
        longest = max(longest, Date().timeIntervalSince(lastMove))
        XCTAssertNotNil(started, "the voice never played")
        XCTAssertGreaterThanOrEqual(last, 8.5, "the voice stopped at \(last) s")
        XCTAssertLessThan(longest, 1.0, "the voice broke for \(longest) s once started")
    }

    /// The orb page, scrolled, voice finished: taps that just miss the button (beside, above,
    /// below, a corner) work the button or do nothing, and never start listening; a short press is
    /// a tap; a hold on a finished voice replays it.
    func testNearMissesNeverStartListening() throws {
        app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--screen", "ask", "--test-ask", "Compare overall survival by arm"]
        app.launch()
        let whoAnswers = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "Talking to")).firstMatch
        XCTAssertTrue(voice.waitForExistence(timeout: 40), "no voice button:\n\(app.debugDescription)")
        XCTAssertTrue(whoAnswers.waitForExistence(timeout: 60), "the voice never finished:\n\(app.debugDescription)")
        app.swipeUp(); sleep(1)
        shot("vb1-scrolled")
        XCTAssertTrue(voice.isHittable, "voice button hidden once scrolled:\n\(app.debugDescription)")

        // Points around the drawn circle (35 pt, at the frame's left, centred in its height): 5 pt
        // below, beside, above; the square's corner outside the circle; the centre.
        let frame = voice.frame
        let top = (frame.height - 35) / 2
        func at(_ x: CGFloat, _ y: CGFloat) -> XCUICoordinate {
            voice.coordinate(withNormalizedOffset: .zero).withOffset(CGVector(dx: x, dy: top + y))
        }
        for (i, offset) in [CGVector(dx: 17.5, dy: 40), CGVector(dx: 40, dy: 17.5), CGVector(dx: 17.5, dy: -5),
                            CGVector(dx: 33, dy: 33), CGVector(dx: 17.5, dy: 17.5)].enumerated() {
            let before = settledLabel()
            at(offset.dx, offset.dy).tap()
            usleep(600_000)
            let after = settledLabel()
            shot("vb2-tap\(i)")
            XCTAssertFalse(listening(), "tap \(offset) started listening:\n\(app.debugDescription)")
            XCTAssertNotEqual(before, after, "tap \(offset) did nothing (\(before))")
        }
        // Below the row (in its band): nothing.
        let label = settledLabel()
        at(17.5, 35 + 12).tap()                               // 12 pt below the circle: the row's band
        usleep(600_000)
        XCTAssertFalse(listening(), "a tap under the row started listening:\n\(app.debugDescription)")
        XCTAssertEqual(settledLabel(), label, "a tap under the row worked the voice")

        // A firm tap (half a second) is a tap, not a hold.
        if voice.label == "Read aloud" { voice.tap(); XCTAssertEqual(settledLabel(), "Pause") }
        sleep(1)
        voice.press(forDuration: 0.5)
        usleep(400_000)
        XCTAssertEqual(voice.label, "Read aloud", "a half-second press did not pause")
        voice.press(forDuration: 0.5)
        XCTAssertEqual(settledLabel(), "Pause", "a half-second press did not resume")
        XCTAssertEqual(voice.value as? String ?? "", "", "the button stayed pressed")
    }

    /// Every quick tap counts: eight taps in a row, each pauses or resumes (a tap shorter than a
    /// frame used to be lost).
    func testEveryQuickTapCounts() throws {
        app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--screen", "read"]
        app.launch()
        XCTAssertTrue(voice.waitForExistence(timeout: 20))
        XCTAssertEqual(settledLabel(timeout: 15), "Pause", "the voice did not start")
        for i in 0..<8 {
            let before = voice.label
            voice.tap()
            usleep(700_000)
            XCTAssertNotEqual(voice.label, before, "tap \(i + 1) was lost (\(before))")
        }
    }

    /// A hold on a finished voice plays it again from the start (it used to replay its last second).
    func testHoldOnAFinishedVoicePlaysItFromTheStart() throws {
        app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--screen", "read"]
        app.launch()
        XCTAssertTrue(voice.waitForExistence(timeout: 20))
        let end = Date().addingTimeInterval(40)
        while voice.label != "Read aloud" && Date() < end { usleep(250_000) }   // finished
        XCTAssertEqual(voice.label, "Read aloud", "the voice never finished")
        voice.press(forDuration: 1.6)
        XCTAssertEqual(settledLabel(), "Pause", "a hold on a finished voice did not play it")
        usleep(500_000)
        XCTAssertLessThan(seconds(), 3, "it did not start from the beginning (\(seconds()) s)")
        XCTAssertEqual(voice.value as? String ?? "", "", "the button stayed pressed")
    }

    /// The detector works: a tap on the orb itself does start listening (else the test above
    /// proves nothing).
    func testATapOnTheOrbListens() throws {
        app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--screen", "ask", "--test-ask", "Compare overall survival by arm"]
        app.launch()
        let whoAnswers = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "Talking to")).firstMatch
        XCTAssertTrue(whoAnswers.waitForExistence(timeout: 60))
        app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.55)).tap()
        let end = Date().addingTimeInterval(8)
        while !listening() && Date() < end { usleep(200_000) }
        shot("vb3-orb")
        XCTAssertTrue(listening(), "a tap on the orb did not listen:\n\(app.debugDescription)")
    }
}
