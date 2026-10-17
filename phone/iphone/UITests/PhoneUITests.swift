import XCTest

final class PhoneUITests: XCTestCase {
    @MainActor func testConversationAndNavigation() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--demo"]
        app.launch()
        XCTAssertTrue(app.staticTexts["What’s on\nyour mind?"].waitForExistence(timeout: 10))
        capture(app, "Assistant")
        app.buttons["Find a little focus"].firstMatch.tap()
        app.buttons["Send message"].tap()
        XCTAssertTrue(app.buttons["Share answer"].firstMatch.waitForExistence(timeout: 30))
        let finished = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: app.buttons["Stop"].firstMatch)
        XCTAssertEqual(XCTWaiter.wait(for: [finished], timeout: 30), .completed)
        XCTAssertTrue(app.buttons["Settings"].isHittable)
        XCTAssertTrue(app.buttons["Record a voice message"].isHittable)
        capture(app, "Conversation")
        app.tabBars.buttons["Inbox"].tap()
        XCTAssertTrue(app.staticTexts["A little attention.\nA lot of progress."].exists)
        capture(app, "Inbox")
        app.tabBars.buttons["Automations"].tap()
        XCTAssertTrue(app.staticTexts["A rhythm\nof your own."].exists)
        capture(app, "Automations")
    }
    @MainActor func testApprovalShowsActionAndReturnsToInbox() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--demo", "--screen", "inbox"]
        app.launch()
        let permission = app.buttons.containing(.staticText, identifier: "Permission to proceed").firstMatch
        XCTAssertTrue(permission.waitForExistence(timeout: 10)); permission.tap()
        XCTAssertTrue(app.buttons["Allow once"].waitForExistence(timeout: 10))
        capture(app, "Approval")
        app.buttons["Deny"].tap()
        XCTAssertTrue(app.staticTexts["A little attention.\nA lot of progress."].waitForExistence(timeout: 10))
    }
    @MainActor private func capture(_ app: XCUIApplication, _ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
    }
}
