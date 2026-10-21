import XCTest

/// Deny · Approve · Approve all for a conversation and for an automation alike: Approve all is for
/// the run's owner (its conversation, or its automation, each with its own tools), wherever the
/// approval is opened; a send never offers it. Sample data.
final class ApproveAllUITests: XCTestCase {
    private func openWait(_ app: XCUIApplication, containing text: String) {
        let row = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", text)).firstMatch
        app.bring(row)
        XCTAssertTrue(row.exists, "no \(text) in Needs you:\n\(app.debugDescription)")
        row.tap()
    }

    func testAConversationsApprovalOffersApproveAll() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--reset-tools", "--screen", "waits"]
        app.launch()
        XCTAssertTrue(app.staticTexts.matching(identifier: "screen.title").firstMatch.waitForExistence(timeout: 15))
        openWait(app, containing: "rm -rf")
        let all = app.buttons["approval.all"].firstMatch
        XCTAssertTrue(all.waitForExistence(timeout: 10), "no Approve all for a conversation's approval:\n\(app.debugDescription)")
        XCTAssertEqual(all.label, "Allow these tools in this conversation")
    }

    func testAnAutomationsApprovalIsForThatAutomation() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--reset-tools", "--screen", "waits"]
        app.launch()
        XCTAssertTrue(app.staticTexts.matching(identifier: "screen.title").firstMatch.waitForExistence(timeout: 15))
        // A send (an email the automation drafted): no Approve all.
        openWait(app, containing: "qc-team")
        XCTAssertTrue(app.buttons["Deny"].firstMatch.waitForExistence(timeout: 10))
        sleep(2)
        XCTAssertFalse(app.buttons["approval.all"].exists, "Approve all offered for a send")
        app.buttons["Back"].firstMatch.tap(); sleep(1)
        // A page read by the automation's run: Approve all, for the automation.
        openWait(app, containing: "globenewswire")
        let all = app.buttons["approval.all"].firstMatch
        XCTAssertTrue(all.waitForExistence(timeout: 10), "no Approve all for an automation's approval:\n\(app.debugDescription)")
        XCTAssertEqual(all.label, "Allow these tools for this automation")
        all.tap()
        // Its details say what the watch now approves for its runs (and the conversation's tools are untouched).
        XCTAssertTrue(app.staticTexts["screen.title"].firstMatch.waitForExistence(timeout: 10))
        app.buttons["Back"].firstMatch.tap(); sleep(1)
        app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Automations'")).firstMatch.tap()
        let digest = app.buttons.matching(NSPredicate(format: "label CONTAINS 'Morning digest'")).firstMatch
        XCTAssertTrue(digest.waitForExistence(timeout: 15), app.debugDescription)
        digest.tap()
        let info = app.buttons["ask.info"].firstMatch
        XCTAssertTrue(info.waitForExistence(timeout: 15), app.debugDescription)
        sleep(1); info.tap()
        let revoke = app.buttons["automation.trust.revoke"].firstMatch
        app.bring(revoke)
        XCTAssertTrue(revoke.waitForExistence(timeout: 10), "the automation's details do not say what is allowed:\n\(app.debugDescription)")
        revoke.tap()
        XCTAssertTrue(revoke.waitForNonExistence(timeout: 5))
    }
}
