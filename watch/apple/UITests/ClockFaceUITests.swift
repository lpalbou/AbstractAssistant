import XCTest

/// The clock: swiped to from Home (to the left), with no corner button over it; its orb talks; a
/// swipe to the right goes back Home. Sample data.
final class ClockFaceUITests: XCTestCase {
    func testHomeSwipesToTheClockAndBack() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt"]
        app.launch()
        let gear = app.buttons["Settings"]
        XCTAssertTrue(gear.waitForExistence(timeout: 15), app.debugDescription)
        sleep(1)
        app.swipeLeft()
        let orb = app.buttons["clock.orb"]
        XCTAssertTrue(orb.waitForExistence(timeout: 5), "a swipe left on Home did not open the clock:\n\(app.debugDescription)")
        XCTAssertTrue(app.descendants(matching: .any)["clock.date"].exists, "no date on the clock")
        XCTAssertTrue(app.buttons["clock.needYou"].exists, "the sample's waits are not on the clock")
        XCTAssertFalse(gear.exists || app.buttons["Back"].exists, "a corner button over the clock")
        // Back: a swipe to the right (from inside the screen, not its very edge).
        app.coordinate(withNormalizedOffset: CGVector(dx: 0.12, dy: 0.55))
            .press(forDuration: 0.02, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.95, dy: 0.55)), withVelocity: .fast, thenHoldForDuration: 0)
        XCTAssertTrue(gear.waitForExistence(timeout: 5), "a swipe right did not go back Home:\n\(app.debugDescription)")
        // Its orb talks, as Home's does.
        app.swipeLeft()
        XCTAssertTrue(orb.waitForExistence(timeout: 5))
        sleep(1)
        orb.tap()
        XCTAssertTrue(app.staticTexts["ask.status"].waitForExistence(timeout: 8), "the clock's orb did not open the orb page:\n\(app.debugDescription)")
    }
}
