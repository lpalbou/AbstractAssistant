import XCTest

/// Edit → how often: from every 30 seconds to every week (a plain schedule), the current one
/// checked; choosing one shows it and Save can send it (sample data).
final class ScheduleChoicesUITests: XCTestCase {
    /// Turns the crown until the element is on screen (a list draws only the rows it shows).
    static func scrollTo(_ element: XCUIElement, in app: XCUIApplication, down: Bool = true) -> Bool {
        let screen = app.windows.firstMatch.frame
        for _ in 0..<12 {
            if element.exists, screen.contains(CGPoint(x: element.frame.midX, y: element.frame.midY)) { return true }
            XCUIDevice.shared.rotateDigitalCrown(delta: down ? 0.4 : -0.4)
        }
        return element.exists && screen.contains(CGPoint(x: element.frame.midX, y: element.frame.midY))
    }

    private func shot(_ name: String) {
        guard let dir = ProcessInfo.processInfo.environment["SHOTS_DIR"] else { return }
        try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent(name + ".png"))
    }

    func testTheChoicesRunFromThirtySecondsToAWeek() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--screen", "automation-edit"]
        app.launch()
        let row = app.buttons["Every day"].firstMatch
        XCTAssertTrue(row.waitForExistence(timeout: 10), app.debugDescription)
        XCTAssertFalse(app.buttons["Save"].isEnabled, "nothing changed yet")
        row.tap()
        XCTAssertTrue(app.buttons["Every 30 sec"].firstMatch.waitForExistence(timeout: 5), app.debugDescription)
        XCTAssertLessThan(app.buttons["Every 30 sec"].firstMatch.frame.minY, app.buttons["Every minute"].firstMatch.frame.minY, "shortest first")
        shot("schedule-1-choices")
        // The list draws the rows it shows: each choice in turn comes on screen with the crown.
        for label in ["Every 5 min", "Every 15 min", "Every 30 min", "Every hour", "Every 12 hours", "Every day", "Every 2 days", "Every 7 days"] {
            XCTAssertTrue(Self.scrollTo(app.buttons[label].firstMatch, in: app), "no \(label)\n\(app.debugDescription)")
        }
        XCTAssertTrue(Self.scrollTo(app.buttons["Every minute"].firstMatch, in: app, down: false), app.debugDescription)
        app.buttons["Every minute"].firstMatch.tap()
        let chosen = app.buttons["Every minute"].firstMatch
        XCTAssertTrue(chosen.waitForExistence(timeout: 5), app.debugDescription)
        XCTAssertTrue(app.buttons["Save"].firstMatch.isEnabled, "a new interval is a change to save")
        shot("schedule-2-chosen")
    }
}
