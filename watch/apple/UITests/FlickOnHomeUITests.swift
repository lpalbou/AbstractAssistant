import XCTest

/// Home is the first page: a flick either way over the orb or a row opens nothing (a flick is not
/// a tap). Sample data.
final class FlickOnHomeUITests: XCTestCase {
    func testFlicksOnHomeOpenNothing() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt"]
        app.launch()
        XCTAssertTrue(app.buttons["Settings"].waitForExistence(timeout: 15))
        let orb = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Talk to'")).firstMatch
        let sessions = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Sessions'")).firstMatch
        XCTAssertTrue(orb.waitForExistence(timeout: 10))
        var onHome: Bool { app.buttons["Settings"].exists && !app.buttons["Back"].exists }
        for (name, flick) in [("left on the orb", { orb.swipeLeft() }), ("right on the orb", { orb.swipeRight() }),
                              ("left on Sessions", { sessions.swipeLeft() }), ("right on Sessions", { sessions.swipeRight() })] {
            flick(); sleep(2)
            XCTAssertTrue(onHome, "a flick \(name) left Home")
            if !onHome { app.buttons["Back"].firstMatch.tap(); sleep(2) }
        }
    }
}
