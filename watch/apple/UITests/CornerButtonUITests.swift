import XCTest

/// The one corner button: the gear on Home, Back on every other page, at the very same place on
/// each (it morphs, it never moves); Settings opens from the left and its pages stack on it.
final class CornerButtonUITests: XCTestCase {
    private func shot(_ app: XCUIApplication, _ name: String) {
        guard let dir = ProcessInfo.processInfo.environment["SHOTS_DIR"] else { return }
        try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent(name + ".png"))
    }
    /// The titles on screen (a page under Settings keeps its own).
    private func titles(_ app: XCUIApplication) -> [String] {
        app.staticTexts.matching(identifier: "screen.title").allElementsBoundByIndex.map { $0.label }
    }
    private func same(_ a: CGRect, _ b: CGRect, _ what: String) {
        XCTAssertEqual(a.origin.x, b.origin.x, accuracy: 1, "\(what) moved: \(a) vs \(b)")
        XCTAssertEqual(a.origin.y, b.origin.y, accuracy: 1, "\(what) moved: \(a) vs \(b)")
        XCTAssertEqual(a.size.width, b.size.width, accuracy: 1, "\(what) resized: \(a) vs \(b)")
    }

    func testTheCornerButtonNeverMoves() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--orb-design", "A"]
        app.launch()
        let settings = app.buttons["Settings"].firstMatch
        XCTAssertTrue(settings.waitForExistence(timeout: 15), app.debugDescription)
        let home = settings.frame
        shot(app, "c0-home")
        // A page of the main stack: Back, at the gear's place.
        app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Sessions'")).firstMatch.tap()
        let back = app.buttons["Back"].firstMatch
        XCTAssertTrue(back.waitForExistence(timeout: 10), app.debugDescription)
        XCTAssertTrue(titles(app).contains("Sessions"), titles(app).description)
        same(back.frame, home, "Back on Sessions")
        shot(app, "c1-sessions")
        back.tap()
        XCTAssertTrue(settings.waitForExistence(timeout: 5), app.debugDescription)
        same(settings.frame, home, "the gear after Back")
        // Settings: frames through its arrival, then Back at the gear's place.
        settings.tap()
        for i in 0..<6 { shot(app, "c2-settings-\(i)"); usleep(70_000) }
        XCTAssertTrue(back.waitForExistence(timeout: 5), app.debugDescription)
        XCTAssertTrue(titles(app).contains("Settings"), titles(app).description)
        same(back.frame, home, "Back on Settings")
        shot(app, "c3-settings")
        // A page of Settings' own stack.
        let orbStyle = app.buttons.matching(NSPredicate(format: "label CONTAINS 'Orb style'")).firstMatch
        XCTAssertTrue(orbStyle.waitForExistence(timeout: 5), app.debugDescription)
        orbStyle.tap()
        let halo = app.buttons["orb.Halo"].firstMatch
        XCTAssertTrue(halo.waitForExistence(timeout: 10), app.debugDescription)
        XCTAssertTrue(titles(app).contains("Orb style"), titles(app).description)
        same(back.frame, home, "Back on Orb style")
        shot(app, "c4-orbstyle")
        // Back through Settings to Home: the gear again.
        back.tap()
        XCTAssertTrue(app.buttons.matching(NSPredicate(format: "label CONTAINS 'Orb style'")).firstMatch.waitForExistence(timeout: 5), app.debugDescription)
        back.tap()
        for i in 0..<6 { shot(app, "c5-closing-\(i)"); usleep(70_000) }
        XCTAssertTrue(settings.waitForExistence(timeout: 5), app.debugDescription)
        XCTAssertFalse(back.exists, "Back on Home")
        same(settings.frame, home, "the gear at the end")
        shot(app, "c6-home")
    }

    /// A launch straight into a Settings page opens it in Settings' stack: Back leads to Settings.
    func testALaunchIntoASettingsPage() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--screen", "about"]
        app.launch()
        let back = app.buttons["Back"].firstMatch
        XCTAssertTrue(back.waitForExistence(timeout: 15), app.debugDescription)
        XCTAssertTrue(titles(app).contains("About"), titles(app).description)
        back.tap()
        XCTAssertTrue(app.buttons.matching(NSPredicate(format: "label CONTAINS 'Orb style'")).firstMatch.waitForExistence(timeout: 5), app.debugDescription)
        shot(app, "l1-settings")
        back.tap()
        XCTAssertTrue(app.buttons["Settings"].firstMatch.waitForExistence(timeout: 5), app.debugDescription)
        shot(app, "l2-home")
    }
}
