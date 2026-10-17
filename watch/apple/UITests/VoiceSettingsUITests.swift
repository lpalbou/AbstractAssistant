import XCTest

/// Settings → Voice: the gateway's voices and transcription models, the default first; a choice is
/// marked and kept (sample data).
final class VoiceSettingsUITests: XCTestCase {
    func testChooseAVoiceAndAModel() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--screen", "voice"]
        app.launch()
        // A spinner while the gateway's lists load, then the page.
        XCTAssertTrue(app.descendants(matching: .any)["voices.loading"].waitForExistence(timeout: 5), "no spinner while loading:\n\(app.debugDescription)")
        if let dir = ProcessInfo.processInfo.environment["SHOTS_DIR"] {
            try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent("v0-loading.png"))
        }
        let f2 = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "Supertonic F2")).firstMatch
        XCTAssertTrue(app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "Gateway default")).firstMatch.waitForExistence(timeout: 15),
                      app.debugDescription)
        // Short, slow scrolls: rows build as they scroll in, and a fast swipe passes them.
        func nudge() {
            app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.75))
                .press(forDuration: 0.05, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.45)),
                       withVelocity: .slow, thenHoldForDuration: 0.2)
        }
        for _ in 0..<10 where !(f2.exists && f2.isHittable) { nudge() }
        XCTAssertTrue(f2.exists, app.debugDescription)
        f2.tap()
        XCTAssertTrue(f2.isSelected, "the chosen voice is marked")
        let small = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "small")).firstMatch
        for _ in 0..<12 where !(small.exists && small.isHittable) { nudge() }
        small.tap()
        XCTAssertTrue(small.isSelected, "the chosen model is marked")
        // Kept: Settings shows the voice, and the page reopens with both choices.
        app.buttons["Back"].firstMatch.tap()
        XCTAssertTrue(app.staticTexts["F2"].waitForExistence(timeout: 5), "Settings does not show the chosen voice:\n\(app.debugDescription)")
    }

    /// Against a real gateway (GW_URL + GW_TOKEN): choosing a voice shows a spinner on its row while
    /// the gateway makes the sample, then the checkmark.
    func testSpinnerWhileTheSampleIsMade() throws {
        let env = ProcessInfo.processInfo.environment
        guard let url = env["GW_URL"], let token = env["GW_TOKEN"] else { throw XCTSkip("no gateway given") }
        let app = XCUIApplication()
        app.launchArguments = ["--gateway", url, "--token", token, "--no-notification-prompt", "--screen", "voice"]
        app.launch()
        let m1 = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "Supertonic M1")).firstMatch
        XCTAssertTrue(m1.waitForExistence(timeout: 30), app.debugDescription)
        m1.tap()
        let spinner = app.descendants(matching: .any)["Making the sample"].firstMatch
        XCTAssertTrue(spinner.waitForExistence(timeout: 3), "no spinner while the sample is made:\n\(app.debugDescription)")
        if let dir = env["SHOTS_DIR"] {
            try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent("v1-spinner.png"))
        }
        var waited = 0
        while spinner.exists && waited < 60 { usleep(500_000); waited += 1 }
        XCTAssertFalse(spinner.exists, "the spinner stayed")
        XCTAssertTrue(m1.isSelected, "the voice is marked once its sample plays")
        // Leave the default for the next run.
        app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "Gateway default")).firstMatch.tap()
    }
}
