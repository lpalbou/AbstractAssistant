import XCTest

/// Synthetic gates on one leaf run. Only the first receives a local decision; the next one is
/// resolved by another client. The fixture also delivers stale snapshots in both directions.
final class ApprovalSyncUITests: XCTestCase {
    private func needsYou(_ app: XCUIApplication) -> XCUIElement {
        app.buttons.matching(NSPredicate(format: "label CONTAINS %@", "Needs you")).firstMatch
    }

    func testNextGateAppearsAfterOneAnswerAndMonitorReactivation() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--sequential-approvals"]
        app.launch()
        let pending = needsYou(app)
        XCTAssertTrue(pending.waitForExistence(timeout: 15), app.debugDescription)
        pending.tap()
        XCTAssertTrue(app.staticTexts["echo gate-1"].waitForExistence(timeout: 5))
        app.buttons["Allow once"].tap()
        let answered = Date()
        XCTAssertTrue(pending.waitForExistence(timeout: 5), "the next gate must not wait for the 15-second list poll")
        pending.tap()
        XCTAssertTrue(app.staticTexts["echo gate-2"].waitForExistence(timeout: 3), "a stale list restored gate 1")
        XCTAssertLessThan(Date().timeIntervalSince(answered), 7)
        sleep(2)
        XCTAssertTrue(app.staticTexts["echo gate-2"].exists, "Allow once must not approve the next gate")
        XCTAssertTrue(app.buttons["Allow once"].waitForNonExistence(timeout: 15), "an external decision must close the gate")
        XCTAssertFalse(pending.exists)
    }

    func testNewerListGateWinsOverAnOlderRunSnapshot() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--sequential-approvals", "--approval-index-race"]
        app.launch()
        let pending = needsYou(app)
        XCTAssertTrue(pending.waitForExistence(timeout: 15), app.debugDescription)
        pending.tap()
        XCTAssertTrue(app.staticTexts["echo gate-2"].waitForExistence(timeout: 5),
                      "a delayed gate-1 response must not replace or retire gate 2")
        sleep(2)
        XCTAssertTrue(app.staticTexts["echo gate-2"].exists)
        XCTAssertTrue(app.buttons["Allow once"].waitForNonExistence(timeout: 15))
        XCTAssertFalse(pending.exists)
    }
}
