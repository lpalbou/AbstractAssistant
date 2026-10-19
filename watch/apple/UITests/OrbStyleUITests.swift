import XCTest

/// The first-launch orb question offers every style (the planets, the avatars, then Ocean); the one
/// chosen is kept (Settings names it). Sample data.
final class OrbStyleUITests: XCTestCase {
    private func shot(_ name: String) {
        guard let dir = ProcessInfo.processInfo.environment["SHOTS_DIR"] else { return }
        try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent(name + ".png"))
    }

    func testFaceAndOceanCanBeChosen() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--orb-design", "A", "--ask-orb"]
        app.launch()
        XCTAssertTrue(app.staticTexts["Halo"].waitForExistence(timeout: 15), app.debugDescription)
        // One page per style: swipe up to the last two.
        for name in ["Vortex", "Nebula", "Rings", "Liquid", "Galaxy", "Lotus", "Crystal", "Eclipse", "Synapse", "Drop", "Face", "Imprint", "Hologram", "Eye", "Lens", "Dome", "Valet", "Retro", "Deco", "Rover"] {
            app.swipeUp()
            XCTAssertTrue(app.staticTexts[name].waitForExistence(timeout: 5), "no \(name) page:\n\(app.debugDescription)")
        }
        sleep(1); shot("o1-rover")
        app.swipeUp()
        XCTAssertTrue(app.staticTexts["Ocean"].waitForExistence(timeout: 5), app.debugDescription)
        sleep(1); shot("o2-ocean")
        app.buttons["Use this"].firstMatch.tap()
        // Home, then Settings: it is the orb in use.
        let settings = app.buttons["Settings"].firstMatch
        XCTAssertTrue(settings.waitForExistence(timeout: 10), app.debugDescription)
        settings.tap()
        XCTAssertTrue(app.buttons.matching(NSPredicate(format: "label CONTAINS 'Orb style' AND label CONTAINS 'Ocean'")).firstMatch
            .waitForExistence(timeout: 10), app.debugDescription)
        shot("o3-settings")
    }
}
