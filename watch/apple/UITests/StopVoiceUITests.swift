import XCTest

/// While the orb speaks, Share becomes Stop: Stop (or a 1.5 s hold on the orb) ends the voice,
/// Share comes back, and the next tap on the orb listens. At rest, the same hold reads the last
/// answer aloud again (a toggle). A short hold does nothing. Sample data.
final class StopVoiceUITests: XCTestCase {
    private var app: XCUIApplication!
    private func shot(_ name: String) {
        guard let dir = ProcessInfo.processInfo.environment["SHOTS_DIR"] else { return }
        try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent(name + ".png"))
    }
    private var stop: XCUIElement { app.buttons["ask.stop"].firstMatch }
    private var share: XCUIElement { app.buttons["Share"].firstMatch }
    private var orb: XCUICoordinate { app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.45)) }

    /// A conversation on the orb, its last answer being read aloud.
    private func speaking() {
        app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--screen", "sessions"]
        app.launch()
        let row = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", "QC")).firstMatch
        XCTAssertTrue(app.buttons["New conversation"].waitForExistence(timeout: 15))
        app.bring(row)
        row.tap()
        let voice = app.buttons["voice.button"].firstMatch
        XCTAssertTrue(voice.waitForExistence(timeout: 20), app.debugDescription)
        XCTAssertTrue(share.waitForExistence(timeout: 5), "no Share before it speaks")
        voice.tap()
        XCTAssertTrue(stop.waitForExistence(timeout: 8), "Share did not become Stop while it speaks:\n\(app.debugDescription)")
        XCTAssertFalse(share.exists, "Share and Stop at once")
    }

    /// After a stop: Share is back, and a tap on the orb listens.
    private func tapListens() {
        XCTAssertTrue(stop.waitForNonExistence(timeout: 5), "Stop stays after the voice stopped")
        XCTAssertTrue(share.waitForExistence(timeout: 5), "Share did not come back")
        orb.tap()
        let listening = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "Listening")).firstMatch
        XCTAssertTrue(listening.waitForExistence(timeout: 5), "a tap after the stop does not listen:\n\(app.debugDescription)")
    }

    func testStopButtonEndsTheVoice() throws {
        speaking()
        shot("v1-speaking")
        stop.tap()
        tapListens()
        shot("v2-listening")
    }

    func testHoldingTheOrbTogglesReadingAndListening() throws {
        speaking()
        // A short hold: nothing stops.
        orb.press(forDuration: 0.6)
        XCTAssertTrue(stop.exists, "a short hold stopped the voice")
        XCTAssertNotEqual(app.buttons["voice.button"].firstMatch.label, "Read aloud", "a hold let go early paused the voice (it is not a tap)")
        // A full hold: the ring closes, the voice stops.
        orb.press(forDuration: 1.9)
        shot("v3-held")
        XCTAssertTrue(stop.waitForNonExistence(timeout: 5), "a full hold did not stop the voice")
        XCTAssertTrue(share.waitForExistence(timeout: 5))
        // At rest, a short hold reads nothing; a full one reads the last answer aloud again.
        orb.press(forDuration: 0.6)
        XCTAssertFalse(stop.waitForExistence(timeout: 2), "a short hold started reading")
        orb.press(forDuration: 1.9)
        XCTAssertTrue(stop.waitForExistence(timeout: 8), "a full hold at rest did not read the answer aloud")
        shot("v4-reading-again")
        // And back: Stop, then a tap listens.
        stop.tap()
        tapListens()
    }
}
