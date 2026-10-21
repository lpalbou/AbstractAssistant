import XCTest

/// Swipes as in a browser: to the right goes back, to the left forward to a page went back from, and nowhere
/// when nothing is ahead; from the orb page with a message, right opens the conversation (its numbers
/// and files). Sample data.
final class BrowserNavigationUITests: XCTestCase {
    private var app: XCUIApplication!
    private func shot(_ name: String) {
        guard let dir = ProcessInfo.processInfo.environment["SHOTS_DIR"] else { return }
        try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent(name + ".png"))
    }
    /// Back: a swipe to the right (from inside the screen, not its very edge).
    private func back() {
        app.coordinate(withNormalizedOffset: CGVector(dx: 0.12, dy: 0.55))
            .press(forDuration: 0.02, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.95, dy: 0.55)), withVelocity: .fast, thenHoldForDuration: 0)
        sleep(2)
    }
    /// Forward: a swipe to the left.
    private func forward() {
        app.coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: 0.55))
            .press(forDuration: 0.02, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.08, dy: 0.55)), withVelocity: .fast, thenHoldForDuration: 0)
        sleep(2)
    }
    private var onHome: Bool { app.buttons["Settings"].exists && !app.buttons["Back"].exists }
    private var onSessions: Bool { app.buttons.matching(identifier: "session.archive").firstMatch.exists }
    private var onOrb: Bool { app.buttons["voice.button"].exists }
    private var onConversation: Bool { app.descendants(matching: .any)["conversation.stats"].exists }

    func testBackAndForwardLikeABrowser() throws {
        app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt"]
        app.launch()
        XCTAssertTrue(app.buttons["Settings"].waitForExistence(timeout: 15))
        // At startup neither swipe goes anywhere.
        forward()
        XCTAssertTrue(onHome, "forward from Home went somewhere")
        back()
        XCTAssertTrue(onHome, "back from Home went somewhere")
        // Sessions; nothing ahead; back to Home; forward to Sessions.
        app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Sessions'")).firstMatch.tap()
        XCTAssertTrue(app.buttons["New conversation"].waitForExistence(timeout: 10))
        forward()
        XCTAssertTrue(onSessions, "forward with nothing ahead left Sessions")
        back()
        XCTAssertTrue(onHome, "back from Sessions is not Home")
        back()
        XCTAssertTrue(onHome, "back from Home went somewhere")
        forward()
        XCTAssertTrue(onSessions, "forward from Home is not Sessions again")
        // A conversation on the orb; back to Sessions; forward to the orb.
        let row = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", "QC")).firstMatch
        app.bring(row)
        row.tap()
        XCTAssertTrue(app.buttons["voice.button"].waitForExistence(timeout: 20), app.debugDescription)
        back()
        if !onSessions { shot("b-fail-orb-back") }
        XCTAssertTrue(onSessions, "back from the orb is not Sessions")
        forward()
        XCTAssertTrue(app.buttons["voice.button"].waitForExistence(timeout: 10), "forward from Sessions is not the orb again")
        // A message opened from the orb page opens with a tap only: back from it, then forward opens
        // the conversation, not the message again.
        let message = app.buttons.matching(identifier: "message.row").firstMatch
        app.bring(message)
        message.tap()
        XCTAssertTrue(app.buttons["Back"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.buttons["voice.button"].exists, "the message did not open")
        app.buttons["Back"].firstMatch.tap(); sleep(2)
        XCTAssertTrue(onOrb, "Back from the message is not the orb")
        forward()
        XCTAssertTrue(app.descendants(matching: .any)["conversation.stats"].waitForExistence(timeout: 5),
                      "forward after a message reopened the message instead of the conversation")
        back()
        XCTAssertTrue(onOrb, "back from the conversation is not the orb")
        // Nothing ahead, a message on the orb: forward opens the conversation; back; forward.
        forward()
        XCTAssertTrue(app.descendants(matching: .any)["conversation.stats"].waitForExistence(timeout: 5), "forward from the orb did not open the conversation")
        shot("b1-conversation")
        // The file its assistant wrote into the conversation's folder is listed, with its share button.
        XCTAssertTrue(app.buttons["Share cv-by-plate.svg"].waitForExistence(timeout: 10), "the folder's file is not listed")
        back()
        XCTAssertTrue(onOrb, "back from the conversation is not the orb")
        forward()
        XCTAssertTrue(app.descendants(matching: .any)["conversation.stats"].waitForExistence(timeout: 5), "forward from the orb is not the conversation again")
        forward()
        XCTAssertTrue(onConversation, "forward with nothing ahead left the conversation")
        // Back three times: Home, the first page.
        back(); back(); back()
        XCTAssertTrue(onHome, "three backs did not reach Home:\n\(app.debugDescription)")
        // The same with an automation.
        app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Automations'")).firstMatch.tap()
        let digest = app.buttons.matching(NSPredicate(format: "label CONTAINS 'Morning digest'")).firstMatch
        XCTAssertTrue(digest.waitForExistence(timeout: 15), app.debugDescription)
        digest.tap()
        // Its orb page, as a conversation's; forward: its details (as a conversation's stats).
        let page = app.staticTexts["ask.automation"].firstMatch
        XCTAssertTrue(page.waitForExistence(timeout: 10), app.debugDescription)
        sleep(1)
        forward()
        let title = app.descendants(matching: .any)["automation.title"].firstMatch
        XCTAssertTrue(title.waitForExistence(timeout: 10), "forward from an automation's orb page is not its details:\n\(app.debugDescription)")
        back()
        XCTAssertTrue(page.waitForExistence(timeout: 5), "back from the details is not the automation's orb page")
        back(); back()
        XCTAssertTrue(onHome, "two backs from an automation did not reach Home")
        forward(); shot("b-fwd1"); forward()
        if !page.waitForExistence(timeout: 5) { shot("b-fail-fwd2") }
        XCTAssertTrue(page.waitForExistence(timeout: 10), "two forwards did not come back to the automation:\n\(app.debugDescription)")
        shot("b2-automation")
    }

    /// A conversation reopened from Sessions swipes forward to its stats page, every time, whatever
    /// was opened before.
    func testAReopenedConversationSwipesToItsStats() throws {
        app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt"]
        app.launch()
        XCTAssertTrue(app.buttons["Settings"].waitForExistence(timeout: 15))
        app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Sessions'")).firstMatch.tap()
        let row = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", "QC")).firstMatch
        for round in 1...2 {
            XCTAssertTrue(app.buttons["New conversation"].waitForExistence(timeout: 10) || onSessions)
            app.bring(row)
            row.tap()
            XCTAssertTrue(app.buttons["voice.button"].waitForExistence(timeout: 20), "round \(round): the orb did not open")
            sleep(2)
            forward()
            XCTAssertTrue(app.descendants(matching: .any)["conversation.stats"].waitForExistence(timeout: 5),
                          "round \(round): forward from the reopened orb is not its stats")
            back(); back()
            XCTAssertTrue(onSessions, "round \(round): two backs from the stats are not Sessions")
        }
    }
}
