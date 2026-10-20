import XCTest

/// The voice reading an answer goes on while a page with a recording of its own (an earlier
/// message's) is opened and left: that row's idle player leaving the screen used to turn the audio
/// session off under the voice, which then stayed "speaking" in silence. Sample data.
final class VoiceGoesOnUITests: XCTestCase {
    func testAnotherPagesPlayerLeavingDoesNotStopTheVoice() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--long-voice"]
        app.launch()
        XCTAssertTrue(app.buttons["Settings"].waitForExistence(timeout: 15))
        app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Sessions'")).firstMatch.tap()
        XCTAssertTrue(app.buttons["New conversation"].waitForExistence(timeout: 10))
        let row = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", "QC")).firstMatch
        for _ in 0..<6 where !(row.exists && row.isHittable) { app.swipeUp(); usleep(300_000) }
        row.tap()
        let voice = app.buttons["voice.button"]
        XCTAssertTrue(voice.waitForExistence(timeout: 20), app.debugDescription)
        sleep(1)
        voice.tap()                                                           // read the answer aloud
        let position = app.staticTexts["debug.position"].firstMatch
        func seconds() -> Double { Double(position.label) ?? -1 }
        let started = Date()
        while seconds() < 0.8 && Date().timeIntervalSince(started) < 20 { usleep(200_000) }
        XCTAssertGreaterThan(seconds(), 0.8, "the voice did not start:\n\(app.debugDescription)")
        // An earlier message with a recording: open it, then come back.
        let message = app.buttons.matching(identifier: "message.row").firstMatch
        for _ in 0..<8 where !(message.exists && message.isHittable) { app.swipeUp(); usleep(300_000) }
        message.tap()
        XCTAssertTrue(app.buttons["Back"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS[c] 'recording'")).firstMatch.waitForExistence(timeout: 10)
                      || app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS[c] 'recording'")).firstMatch.waitForExistence(timeout: 5),
                      "no recording on the message page:\n\(app.debugDescription)")
        sleep(1)
        app.buttons["Back"].firstMatch.tap()
        XCTAssertTrue(voice.waitForExistence(timeout: 5))
        sleep(1)
        let before = seconds()
        sleep(3)
        let after = seconds()
        XCTAssertGreaterThan(after, before + 1.5, "the voice stopped when the other page's player left (\(before) → \(after) s)")
    }
}
