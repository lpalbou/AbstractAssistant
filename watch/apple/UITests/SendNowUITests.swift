import XCTest

/// While the orb listens, Send (where the tools icon sits at rest) ends the listening at once: in
/// the simulator's silence it says "I didn't hear anything" right away rather than after the 5 s
/// it waits for speech. Sample data.
final class SendNowUITests: XCTestCase {
    func testSendEndsTheListeningNow() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--fresh-conversation", "--screen", "ask", "--test-listen"]
        app.launch()
        let listening = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "Listening")).firstMatch
        XCTAssertTrue(listening.waitForExistence(timeout: 20), app.debugDescription)
        let send = app.buttons["ask.send"]
        XCTAssertTrue(send.waitForExistence(timeout: 3), "no Send while listening:\n\(app.debugDescription)")
        XCTAssertFalse(app.buttons["ask.tools"].exists, "the tools icon shows while it listens")
        send.tap()
        let note = app.staticTexts.matching(NSPredicate(format: "label CONTAINS[c] %@ OR label CONTAINS[c] %@", "hear anything", "catch that")).firstMatch
        XCTAssertTrue(note.waitForExistence(timeout: 5), "Send did not end the listening at once:\n\(app.debugDescription)")
        XCTAssertFalse(send.exists, "Send stays after the listening ended")
    }
}

/// Home's orb starts a new conversation every time; an earlier one continues from Sessions.
final class HomeOrbNewConversationUITests: XCTestCase {
    func testTheHomeOrbOpensAnEmptyConversation() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt"]
        app.launch()
        XCTAssertTrue(app.buttons["Settings"].waitForExistence(timeout: 15))
        // Continue a conversation with messages, then back Home.
        app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Sessions'")).firstMatch.tap()
        XCTAssertTrue(app.buttons["New conversation"].waitForExistence(timeout: 10))
        let row = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", "QC")).firstMatch
        app.bring(row)
        row.tap()
        XCTAssertTrue(app.buttons["voice.button"].waitForExistence(timeout: 20))
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "assay QC")).firstMatch.waitForExistence(timeout: 10))
        app.buttons["Back"].firstMatch.tap(); sleep(1)
        app.buttons["Back"].firstMatch.tap(); sleep(1)
        XCTAssertTrue(app.buttons["Settings"].waitForExistence(timeout: 5))
        // Home's orb: an empty conversation, not the one just left.
        app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Talk to'")).firstMatch.tap()
        XCTAssertTrue(app.staticTexts["ask.status"].waitForExistence(timeout: 10))
        sleep(2)
        XCTAssertFalse(app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "assay QC")).firstMatch.exists, "Home's orb reopened the earlier conversation")
        XCTAssertFalse(app.buttons["voice.button"].exists, "an answer to read: not a new conversation")
    }
}

/// A question whose sending fails keeps its recording: one line under the orb with Retry and
/// Discard, still offered after a relaunch; Retry sends the same recording (the answer comes and the
/// recording is gone), Discard deletes it. `--test-fail-send` opens the orb on a question just
/// recorded (sample audio) and makes every send fail while the app runs. Sample data.
final class KeptQuestionUITests: XCTestCase {
    private func shot(_ name: String) {
        guard let dir = ProcessInfo.processInfo.environment["SHOTS_DIR"] else { return }
        try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent(name + ".png"))
    }

    private func launch(failing: Bool) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--fresh-conversation", "--screen", "ask"]
            + (failing ? ["--test-fail-send"] : [])
        app.launch()
        return app
    }

    /// The failure state: the line and both actions, under the orb.
    private func assertKept(_ app: XCUIApplication, _ why: String) {
        XCTAssertTrue(app.buttons["ask.retry"].waitForExistence(timeout: 20), "\(why): no Retry\n\(app.debugDescription)")
        XCTAssertTrue(app.buttons["ask.discard"].exists, "\(why): no Discard")
        XCTAssertEqual(app.staticTexts["ask.status"].label, "Not sent.", why)
    }

    func testAFailedQuestionIsKeptAcrossARelaunchAndRetrySendsIt() throws {
        var app = launch(failing: true)
        assertKept(app, "a failed send")
        shot("kept-1-failed")
        // Retry while sending still fails: the recording stays.
        app.buttons["ask.retry"].tap()
        XCTAssertTrue(app.buttons["ask.retry"].waitForNonExistence(timeout: 3), "Retry did not send")
        assertKept(app, "a failed retry")
        app.terminate()

        // Relaunched, sending works again: still offered, and Retry sends it.
        app = launch(failing: false)
        assertKept(app, "after a relaunch")
        shot("kept-2-relaunched")
        app.buttons["ask.retry"].tap()
        XCTAssertTrue(app.buttons["voice.button"].waitForExistence(timeout: 40), "Retry after a relaunch brought no answer:\n\(app.debugDescription)")
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "overall survival")).firstMatch.exists,
                      "the answer is not to the kept question")
        XCTAssertFalse(app.buttons["ask.retry"].exists, "Retry stays after the question was sent")
        shot("kept-3-sent")
        app.terminate()

        // Sent: the recording is gone for good.
        app = launch(failing: false)
        XCTAssertTrue(app.staticTexts["ask.status"].waitForExistence(timeout: 20))
        sleep(2)
        XCTAssertFalse(app.buttons["ask.retry"].exists, "a sent question is still offered after a relaunch")
    }

    func testDiscardDeletesTheKeptRecording() throws {
        var app = launch(failing: true)
        assertKept(app, "a failed send")
        app.buttons["ask.discard"].tap()
        XCTAssertTrue(app.buttons["ask.retry"].waitForNonExistence(timeout: 3), "Discard left Retry")
        XCTAssertFalse(app.buttons["ask.discard"].exists)
        XCTAssertEqual(app.staticTexts["ask.status"].label, "Tap to talk", "Discard did not bring the orb back to rest")
        shot("kept-4-discarded")
        app.terminate()
        app = launch(failing: false)
        XCTAssertTrue(app.staticTexts["ask.status"].waitForExistence(timeout: 20))
        sleep(2)
        XCTAssertFalse(app.buttons["ask.retry"].exists, "a discarded recording came back after a relaunch")
    }
}
