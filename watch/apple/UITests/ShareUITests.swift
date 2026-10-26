import XCTest

/// The share icon beside Back opens the system share sheet with the page's link (watchOS has no
/// clipboard), and Back (drawn by the screen, the bar being hidden) leaves the page.
/// `SHOTS_DIR` receives a screenshot of each step.
final class ShareUITests: XCTestCase {
    private func shot(_ name: String) {
        guard let dir = ProcessInfo.processInfo.environment["SHOTS_DIR"] else { return }
        try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent(name + ".png"))
    }

    func testShareOpensTheShareSheet() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--test-open", "https://abstractframework.ai"]
        app.launch()
        let share = app.buttons["Share"].firstMatch
        XCTAssertTrue(share.waitForExistence(timeout: 40), "no Share button:\n\(app.debugDescription)")
        shot("1-link")
        // One top row: Share sits on Back's line (the page once drew two rows, a band apart).
        let back = app.buttons["Back"].firstMatch
        XCTAssertEqual(share.frame.minY, back.frame.minY, accuracy: 1, "Share is not on Back's row: \(share.frame) vs \(back.frame)")
        share.tap()
        sleep(3)
        shot("2-share-sheet")
        // The sheet covers the page: the app's own Share button is no longer hittable.
        XCTAssertFalse(share.isHittable, "the share sheet did not open:\n\(app.debugDescription)")
        let close = app.buttons["Close"].firstMatch
        if close.waitForExistence(timeout: 5) { close.tap() } else { app.buttons.element(boundBy: 0).tap() }
        XCTAssertTrue(share.waitForExistence(timeout: 5) && share.isHittable, "back on the page after the sheet")
        app.buttons["Back"].firstMatch.tap()
        sleep(2)
        XCTAssertFalse(app.buttons["Share"].exists, "Back did not leave the page:\n\(app.debugDescription)")
    }
}

/// About: the contact address is a link (it opens a new message in Mail).
final class AboutUITests: XCTestCase {
    func testContactIsAMailLink() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--screen", "about"]
        app.launch()
        let contact = app.descendants(matching: .any)
            .matching(NSPredicate(format: "label CONTAINS %@", "contact@abstractframework.ai")).firstMatch
        XCTAssertTrue(contact.waitForExistence(timeout: 10))
        for _ in 0..<4 where !contact.isHittable { app.swipeUp() }
        XCTAssertTrue(contact.elementType == .link || contact.elementType == .button,
                      "the contact address is not tappable:\n\(app.debugDescription)")
    }
}

/// Read aloud: the voice button beside Back pauses / plays on a tap and rewinds while held; Back
/// leaves the screen.
final class RewindUITests: XCTestCase {
    func testVoiceButtonPausesAndRewinds() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--screen", "read"]
        app.launch()
        let voice = app.buttons["voice.button"].firstMatch
        XCTAssertTrue(voice.waitForExistence(timeout: 20), "no voice button:\n\(app.debugDescription)")
        let position = app.staticTexts["debug.position"].firstMatch
        func seconds() -> Double { Double(position.label) ?? -1 }
        var waited = 0
        while seconds() < 1.5 && waited < 40 { usleep(250_000); waited += 1 }
        let before = seconds()
        XCTAssertEqual(voice.label, "Pause", "speaking: the button pauses")
        voice.press(forDuration: 1.6)                        // hold: rewind
        usleep(400_000)
        XCTAssertLessThan(seconds(), before - 0.5, "holding did not rewind (\(before) s -> \(seconds()) s)")
        voice.tap()                                          // pause
        usleep(400_000)
        XCTAssertEqual(voice.label, "Read aloud", "a tap paused it")
        app.buttons["Back"].firstMatch.tap()
        sleep(2)
        XCTAssertFalse(app.buttons["voice.button"].exists, "Back did not leave the screen")
    }
}

/// The orb page: while the orb speaks, Stop and the voice button sit beside Back and take a real tap
/// (and neither the keyboard nor "who answers" shows); Stop ends the voice and Share (the
/// conversation) is back, with the controls of the orb at rest; Back leaves.
final class AskShareUITests: XCTestCase {
    func testShareAndRewindOnTheOrb() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--screen", "ask", "--test-ask", "Compare overall survival by arm"]
        app.launch()
        let whoAnswers = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "Talking to")).firstMatch
        let share = app.buttons["Share"].firstMatch, stop = app.buttons["ask.stop"].firstMatch
        XCTAssertTrue(stop.waitForExistence(timeout: 40), "no Stop while it speaks the answer:\n\(app.debugDescription)")
        let rewind = app.buttons["voice.button"].firstMatch
        XCTAssertTrue(rewind.waitForExistence(timeout: 20), "no voice button while it speaks:\n\(app.debugDescription)")
        // While the orb speaks: no keyboard, no ✕, no "who answers" (they show only at rest).
        XCTAssertFalse(app.buttons["Cancel"].exists || app.buttons["Stop the voice"].exists, "a ✕ while speaking")
        XCTAssertFalse(whoAnswers.exists, "who answers shown while speaking:\n\(app.debugDescription)")
        // A tap on rewind takes the voice back (the position read from the debug readout).
        let position = app.staticTexts["debug.position"].firstMatch
        func seconds() -> Double { Double(position.label) ?? -1 }
        XCTAssertTrue(position.waitForExistence(timeout: 5))
        var waited = 0
        while seconds() < 1.5 && waited < 40 { usleep(250_000); waited += 1 }
        let before = seconds()
        XCTAssertGreaterThan(before, 1.0, "the voice never played:\n\(app.debugDescription)")
        rewind.press(forDuration: 1.6)                       // hold: rewind
        usleep(400_000)
        let after = seconds()
        XCTAssertLessThan(after, before - 0.5, "holding did not take the voice back (\(before) s -> \(after) s)")
        stop.tap()
        XCTAssertTrue(share.waitForExistence(timeout: 5), "Share not back after Stop")
        share.tap()
        sleep(3)
        XCTAssertFalse(share.isHittable, "the share sheet did not open:\n\(app.debugDescription)")
        let close = app.buttons["Close"].firstMatch
        if close.waitForExistence(timeout: 5) { close.tap() }
        XCTAssertTrue(share.waitForExistence(timeout: 5))
        // Once the voice is done, the orb is at rest: who answers is back.
        XCTAssertTrue(whoAnswers.waitForExistence(timeout: 40), "who answers not back at rest:\n\(app.debugDescription)")
        app.buttons["Back"].firstMatch.tap()
        sleep(2)
        XCTAssertFalse(app.buttons["Share"].exists, "Back did not leave the orb:\n\(app.debugDescription)")
    }
}

/// The orb page against the real gateway (the watch's saved sign-in): one short question, then
/// rewind while the gateway's voice plays must take it back. Runs only with LIVE_ASK=1.
final class LiveRewindUITests: XCTestCase {
    func testRewindDuringARealAnswer() throws {
        let env = ProcessInfo.processInfo.environment
        guard env["LIVE_ASK"] == "1", let url = env["LIVE_GW_URL"], let token = env["LIVE_GW_TOKEN"] else {
            throw XCTSkip("live only (LIVE_ASK=1, LIVE_GW_URL, LIVE_GW_TOKEN)")
        }
        let conversation = LiveConversation.newId()
        defer { LiveConversation.archive(conversation, url: url, token: token) }
        let app = XCUIApplication()
        app.launchArguments = ["--no-notification-prompt", "--gateway", url, "--token", token, "--screen", "ask",
                               "--test-session-id", conversation, "--test-ask",
                               "Count slowly from one to twenty in words, one number per sentence."]
        app.launch()
        let rewind = app.buttons["voice.button"].firstMatch
        XCTAssertTrue(rewind.waitForExistence(timeout: 120), "no voice button during the real answer:\n\(app.debugDescription)")
        let position = app.staticTexts["debug.position"].firstMatch
        func seconds() -> Double { Double(position.label) ?? -1 }
        var waited = 0
        while seconds() < 4 && waited < 120 { usleep(250_000); waited += 1 }
        let before = seconds()
        XCTAssertTrue(rewind.isHittable, "voice button not hittable:\n\(app.debugDescription)")
        rewind.press(forDuration: 1.6)
        usleep(500_000)
        let after = seconds()
        XCTAssertLessThan(after, before - 1, "rewind did not take the real voice back (\(before) s -> \(after) s):\n\(app.debugDescription)")
    }
}
