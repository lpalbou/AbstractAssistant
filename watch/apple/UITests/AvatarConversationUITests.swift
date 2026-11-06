import XCTest

final class AvatarConversationUITests: XCTestCase {
    func testOptionalViewKeepsTalkAvailableAndPinsAnUpdateDuringWork() {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--screen", "ask", "--test-ask", "Research museum options.",
                               "-ask.conversation", "YES", "-ask.speak", "NO"]
        app.launch()
        let talk = app.buttons["conversation.talk"]
        XCTAssertTrue(talk.waitForExistence(timeout: 20), app.debugDescription)
        let subtitle = app.buttons["conversation.subtitle"]
        XCTAssertTrue(subtitle.waitForExistence(timeout: 15), app.debugDescription)
        subtitle.tap()
        let reply = app.buttons["Reply to this"]
        XCTAssertTrue(reply.waitForExistence(timeout: 5), app.debugDescription)
        reply.tap()
        XCTAssertTrue(app.buttons["Latest"].waitForExistence(timeout: 5), app.debugDescription)
        XCTAssertTrue(talk.exists)
        XCTAssertTrue(app.buttons["Type or dictate"].exists)
        app.buttons["Latest"].tap()
        XCTAssertFalse(app.buttons["Latest"].exists)
    }

    func testExistingViewRemainsTheDefaultPresentation() {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--screen", "thinking", "-ask.conversation", "NO"]
        app.launch()
        XCTAssertTrue(app.staticTexts["ask.status"].waitForExistence(timeout: 15), app.debugDescription)
        XCTAssertFalse(app.buttons["conversation.talk"].exists)
        XCTAssertFalse(app.buttons["conversation.subtitle"].exists)
    }

    func testAcceptedHumanGuidanceReturnsAfterLeavingAndReopeningTheConversation() {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--test-public-history", "-ask.conversation", "YES", "-ask.speak", "YES", "-conversation.cue.completion.audio", "YES", "-conversation.cue.question.audio", "YES"]
        app.launch()
        let sessions = app.buttons["home.sessions"]
        app.bring(sessions); sessions.tap()
        let qc = app.buttons.matching(NSPredicate(format: "label CONTAINS 'QC'")).firstMatch
        app.bring(qc); qc.tap()
        let receipt = app.staticTexts["ask.guidance.3e9a10c4:guidance:1"]
        XCTAssertTrue(receipt.waitForExistence(timeout: 20), app.debugDescription)
        XCTAssertEqual(receipt.label, "You: Keep the flagged plates in the report.")
        let browse = app.buttons["home.browse"]
        app.bring(browse); browse.tap()
        app.bring(sessions); sessions.tap()
        app.bring(qc)
        XCTAssertTrue(qc.waitForExistence(timeout: 10), app.debugDescription)
        app.bring(qc); qc.tap()
        XCTAssertTrue(receipt.waitForExistence(timeout: 20), app.debugDescription)
        XCTAssertEqual(app.staticTexts.matching(identifier: "ask.guidance.3e9a10c4:guidance:1").count, 1)
        XCTAssertEqual(receipt.label, "You: Keep the flagged plates in the report.")
        XCTAssertTrue(app.staticTexts["ask.history.3e9a10c4:reply1:answer"].exists, app.debugDescription)
        XCTAssertTrue(app.staticTexts["ask.history.3e9a10c4:question:q2:expired"].exists, app.debugDescription)
        let late = app.staticTexts["ask.history.3e9a10c4:late:retained_reply"]
        app.bring(late)
        XCTAssertTrue(late.exists, app.debugDescription)
        XCTAssertTrue(late.label.contains("You: Keep last week’s report."))
        XCTAssertTrue(late.label.contains("did not answer the question"))
        XCTAssertFalse(app.buttons["Read the question"].exists, "restoration reopened a historical question")
        XCTAssertFalse(app.staticTexts["conversation.hostOutcome"].exists, "restoration selected a stale timeout caption")
        XCTAssertFalse(app.buttons["ask.stop"].exists, "restoring history started speech despite having no new event")
        XCTAssertTrue(app.buttons["Share"].exists, "restoration unexpectedly started live work or narration")
        let screenshot = XCTAttachment(screenshot: XCUIScreen.main.screenshot()); screenshot.lifetime = .keepAlways; add(screenshot)
    }

}
