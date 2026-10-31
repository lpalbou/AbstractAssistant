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
        app.launchArguments = ["--mock", "--no-notification-prompt", "-ask.conversation", "YES", "-ask.speak", "NO"]
        app.launch()
        app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Sessions'")).firstMatch.tap()
        let qc = app.buttons.matching(NSPredicate(format: "label CONTAINS 'QC'")).firstMatch
        app.bring(qc); qc.tap()
        let receipt = app.staticTexts["ask.guidance.3e9a10c4:guidance:1"]
        XCTAssertTrue(receipt.waitForExistence(timeout: 20), app.debugDescription)
        XCTAssertEqual(receipt.label, "You: Keep the flagged plates in the report.")
        app.buttons["Back"].firstMatch.tap()
        XCTAssertTrue(qc.waitForExistence(timeout: 10), app.debugDescription)
        app.bring(qc); qc.tap()
        XCTAssertTrue(receipt.waitForExistence(timeout: 20), app.debugDescription)
        XCTAssertEqual(app.staticTexts.matching(identifier: "ask.guidance.3e9a10c4:guidance:1").count, 1)
        XCTAssertEqual(receipt.label, "You: Keep the flagged plates in the report.")
    }

}
