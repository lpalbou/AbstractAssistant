import XCTest

/// Home never says a list is empty, or that it failed, while its information is still coming:
/// the number's place shows a spinner and the line below "Loading…" until the list is in. Here the
/// automations answer slowly and their first call fails (as over a watch's radio): the retry brings
/// them, and no error ever shows on Home.
final class HomeLoadingUITests: XCTestCase {
    func testAutomationsShowASpinnerUntilTheyAreRead() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--slow-automations", "--flaky-automations", "--home-bottom"]
        app.launch()
        func shot(_ name: String) {
            guard let dir = ProcessInfo.processInfo.environment["SHOTS_DIR"] else { return }
            try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent(name + ".png"))
        }
        let automations = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Automations'")).firstMatch
        XCTAssertTrue(automations.waitForExistence(timeout: 15), app.debugDescription)
        sleep(1)
        XCTAssertTrue(automations.label.contains("Loading"), automations.label)
        shot("h1-loading")
        // Through the failed first call and the retry: Loading, never an error, never "None yet".
        let deadline = Date().addingTimeInterval(25)
        while Date() < deadline && automations.label.contains("Loading") {
            XCTAssertFalse(automations.label.contains("Can't") || automations.label.contains("None yet"), automations.label)
            usleep(250_000)
        }
        XCTAssertTrue(automations.label.contains("Morning digest"), automations.label)
        shot("h2-loaded")
    }
}
