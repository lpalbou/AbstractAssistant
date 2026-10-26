import XCTest

/// The Digital Crown scrolls the page on screen, whatever was on screen before it: Settings slides
/// over Home as a stack of the app's own, and closing it used to leave the crown with nothing to
/// scroll until a finger touched Home.
final class CrownScrollUITests: XCTestCase {
    private func shot(_ name: String) {
        guard let dir = ProcessInfo.processInfo.environment["SHOTS_DIR"] else { return }
        try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent(name + ".png"))
    }

    /// Turns the crown down and back up: true when the row moved with it (the page scrolled).
    private func crownScrolls(_ row: XCUIElement, _ name: String) -> Bool {
        let before = row.frame.minY
        XCUIDevice.shared.rotateDigitalCrown(delta: 1.0)
        sleep(1)
        let after = row.frame.minY
        shot(name)
        XCUIDevice.shared.rotateDigitalCrown(delta: -1.0)
        sleep(1)
        return after < before - 10
    }

    private func launch() -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--orb-design", "A"]
        app.launch()
        XCTAssertTrue(app.buttons["Settings"].firstMatch.waitForExistence(timeout: 15), app.debugDescription)
        return app
    }

    private func automationsRow(_ app: XCUIApplication) -> XCUIElement {
        app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Automations'")).firstMatch
    }

    func testTheCrownScrollsHomeAfterSettingsCloses() throws {
        let app = launch()
        let row = automationsRow(app)
        XCTAssertTrue(row.waitForExistence(timeout: 10), app.debugDescription)
        XCTAssertTrue(crownScrolls(row, "k0-home"), "the crown does not scroll Home at launch")
        // Settings, and back with the corner button.
        app.buttons["Settings"].firstMatch.tap()
        let back = app.buttons["Back"].firstMatch
        XCTAssertTrue(back.waitForExistence(timeout: 5), app.debugDescription)
        sleep(1)
        back.tap()
        XCTAssertTrue(app.buttons["Settings"].firstMatch.waitForExistence(timeout: 5), app.debugDescription)
        sleep(1)
        XCTAssertTrue(crownScrolls(row, "k1-home-after-settings"), "the crown does not scroll Home after Settings closed")
    }

    /// A page of the navigation stack closes: the crown scrolls the page it uncovers.
    func testTheCrownScrollsSessionsAfterAConversationCloses() throws {
        let app = launch()
        app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Sessions'")).firstMatch.tap()
        let back = app.buttons["Back"].firstMatch
        XCTAssertTrue(back.waitForExistence(timeout: 10), app.debugDescription)
        let first = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", "Now split it by age group")).firstMatch
        XCTAssertTrue(first.waitForExistence(timeout: 10), app.debugDescription)
        XCTAssertTrue(crownScrolls(first, "k4-sessions"), "the crown does not scroll Sessions")
        first.tap()
        sleep(2)
        back.tap()
        sleep(1)
        XCTAssertTrue(crownScrolls(first, "k5-sessions-after-conversation"), "the crown does not scroll Sessions after a conversation closed")
    }
}
