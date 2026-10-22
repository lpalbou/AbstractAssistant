import XCTest

/// A flick on Home is not a tap: over the orb or a row, to the right it opens nothing (Home is the
/// first page), to the left it opens the clock (Home's page ahead), never the orb or the row under
/// the finger. Sample data.
final class FlickOnHomeUITests: XCTestCase {
    func testFlicksOnHomeOpenNothingButTheClock() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt"]
        app.launch()
        XCTAssertTrue(app.buttons["Settings"].waitForExistence(timeout: 15))
        let orb = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Talk to'")).firstMatch
        let sessions = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Sessions'")).firstMatch
        XCTAssertTrue(orb.waitForExistence(timeout: 10))
        var onHome: Bool { app.buttons["Settings"].exists && !app.buttons["Back"].exists }
        var onClock: Bool { app.buttons["clock.orb"].exists }
        func back() {
            app.coordinate(withNormalizedOffset: CGVector(dx: 0.12, dy: 0.55))
                .press(forDuration: 0.02, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.95, dy: 0.55)), withVelocity: .fast, thenHoldForDuration: 0)
            sleep(2)
        }
        for (name, flick, left) in [("left on the orb", { orb.swipeLeft() }, true), ("right on the orb", { orb.swipeRight() }, false),
                                    ("left on Sessions", { sessions.swipeLeft() }, true), ("right on Sessions", { sessions.swipeRight() }, false)] {
            flick(); sleep(2)
            if left {
                XCTAssertTrue(onClock, "a flick \(name) did not open the clock:\n\(app.debugDescription)")
                back()
            }
            XCTAssertTrue(onHome, "a flick \(name) left Home")
            if !onHome { app.buttons["Back"].firstMatch.tap(); sleep(2) }
        }
    }
}
