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
        for _ in 0..<6 where !(row.exists && row.isHittable) { app.swipeUp(); usleep(300_000) }
        row.tap()
        XCTAssertTrue(app.buttons["voice.button"].waitForExistence(timeout: 20), app.debugDescription)
        back()
        if !onSessions { shot("b-fail-orb-back") }
        XCTAssertTrue(onSessions, "back from the orb is not Sessions")
        forward()
        XCTAssertTrue(app.buttons["voice.button"].waitForExistence(timeout: 10), "forward from Sessions is not the orb again")
        // Nothing ahead, a message on the orb: forward opens the conversation; back; forward.
        forward()
        XCTAssertTrue(app.descendants(matching: .any)["conversation.stats"].waitForExistence(timeout: 5), "forward from the orb did not open the conversation")
        shot("b1-conversation")
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
        let title = app.descendants(matching: .any)["automation.title"].firstMatch
        XCTAssertTrue(title.waitForExistence(timeout: 10), app.debugDescription)
        back(); back()
        XCTAssertTrue(onHome, "two backs from an automation did not reach Home")
        forward(); shot("b-fwd1"); forward()
        if !title.waitForExistence(timeout: 5) { shot("b-fail-fwd2") }
        XCTAssertTrue(title.waitForExistence(timeout: 10), "two forwards did not come back to the automation:\n\(app.debugDescription)")
        shot("b2-automation")
    }
}
