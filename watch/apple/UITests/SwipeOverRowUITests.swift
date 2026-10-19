import XCTest

/// A swipe across a full-width row moves the history only: the row under the finger is not opened
/// (a button fires where the finger lifts). Sample data.
final class SwipeOverRowUITests: XCTestCase {
    func testSwipeOverARowDoesNotOpenIt() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt"]
        app.launch()
        let row = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Sessions'")).firstMatch
        XCTAssertTrue(row.waitForExistence(timeout: 15))
        row.coordinate(withNormalizedOffset: CGVector(dx: 0.1, dy: 0.5))
            .press(forDuration: 0.02, thenDragTo: row.coordinate(withNormalizedOffset: CGVector(dx: 0.95, dy: 0.5)), withVelocity: .fast, thenHoldForDuration: 0)
        sleep(2)
        XCTAssertFalse(app.buttons["New conversation"].exists, "a swipe to the right over the Sessions row opened it")
        let auto = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Automations'")).firstMatch
        auto.coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: 0.5))
            .press(forDuration: 0.02, thenDragTo: auto.coordinate(withNormalizedOffset: CGVector(dx: 0.05, dy: 0.5)), withVelocity: .fast, thenHoldForDuration: 0)
        sleep(2)
        XCTAssertTrue(app.buttons["Settings"].exists && !app.buttons["Back"].exists, "a swipe to the left over the Automations row opened it")
    }
}
