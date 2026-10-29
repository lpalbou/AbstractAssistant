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
        for _ in 0..<14 where !(f2.exists && f2.isHittable) { nudge() }
        XCTAssertTrue(f2.exists, app.debugDescription)
        f2.tap()
        XCTAssertTrue(f2.isSelected, "the chosen voice is marked")
        let small = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "small")).firstMatch
        for _ in 0..<20 where !(small.exists && small.isHittable) { nudge() }
        small.tap()
        XCTAssertTrue(small.isSelected, "the chosen model is marked")
        // Kept: Settings shows the voice, and the page reopens with both choices.
        app.buttons["Back"].firstMatch.tap()
        XCTAssertTrue(app.staticTexts["F2"].waitForExistence(timeout: 5), "Settings does not show the chosen voice:\n\(app.debugDescription)")
    }

    /// The voice library on the watch (sample data): voices in groups (yours, the engine's, the
    /// shared ones) with their language, the "Voices that speak" filter, and where voices are made.
    func testVoicesComeInGroupsWithTheirLanguage() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--screen", "voice"]
        app.launch()
        XCTAssertTrue(app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "Gateway default")).firstMatch.waitForExistence(timeout: 15),
                      app.debugDescription)
        func nudge() {
            app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.75))
                .press(forDuration: 0.05, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.45)),
                       withVelocity: .slow, thenHoldForDuration: 0.2)
        }
        XCTAssertTrue(app.descendants(matching: .any)["voices.language"].exists, "no language filter:\n\(app.debugDescription)")
        func header(_ title: String) -> XCUIElement { app.staticTexts.matching(NSPredicate(format: "label ==[c] %@", title)).firstMatch }
        func reach(_ element: XCUIElement, _ tries: Int) -> Bool { for _ in 0..<tries where !element.exists { nudge() }; return element.exists }
        // In order down the page: your voices, the engine's, the shared ones.
        XCTAssertTrue(reach(header("Your voices"), 4), "no Your voices header:\n\(app.debugDescription)")
        let mine = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "My narrator")).firstMatch
        XCTAssertTrue(reach(mine, 4) && mine.label.contains("English"), "your voice with its language:\n\(app.debugDescription)")
        XCTAssertTrue(reach(header("Engine voices"), 6), "no Engine voices header:\n\(app.debugDescription)")
        XCTAssertTrue(reach(header("Shared voices"), 12), "no Shared voices header:\n\(app.debugDescription)")
        let camille = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "Camille")).firstMatch
        XCTAssertTrue(reach(camille, 4) && camille.label.contains("French"), app.debugDescription)
        let elsewhere = app.staticTexts["voices.createElsewhere"]
        for _ in 0..<6 where !elsewhere.exists { nudge() }
        XCTAssertTrue(elsewhere.exists, "the watch says where voices are made:\n\(app.debugDescription)")
        XCTAssertEqual(elsewhere.label, "Create voices on the iPhone or the desktop.")
        if let dir = ProcessInfo.processInfo.environment["SHOTS_DIR"] {
            try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent("v2-groups.png"))
        }
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

    /// Operator 2026-10-29: choosing a voice did not always play its sample, and a failure was silent.
    /// Every tap on a voice plays its sample (a newer tap replaces the older one), and a sample that
    /// cannot play says why in that voice's row (sample data; `--failing-sample` fails the voice M2).
    func testEveryTapPlaysItsSampleAndAFailureSaysWhy() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--screen", "voice", "--failing-sample"]
        app.launch()
        XCTAssertTrue(app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "Gateway default")).firstMatch.waitForExistence(timeout: 15),
                      app.debugDescription)
        func nudge() {
            app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.75))
                .press(forDuration: 0.05, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.45)),
                       withVelocity: .slow, thenHoldForDuration: 0.2)
        }
        func row(_ name: String) -> XCUIElement { app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", name)).firstMatch }
        func reach(_ e: XCUIElement) { for _ in 0..<16 where !(e.exists && e.isHittable) { nudge() } }
        func says(_ e: XCUIElement, _ text: String, _ timeout: TimeInterval) -> Bool {
            let end = Date().addingTimeInterval(timeout)
            while Date() < end { if e.label.contains(text) { return true }; usleep(200_000) }
            return false
        }
        let m1 = row("Supertonic M1"), f1 = row("Supertonic F1"), m2 = row("Supertonic M2")
        reach(m1)
        m1.tap()
        XCTAssertTrue(says(m1, "Playing the sample", 10), "M1's sample did not play:\n\(m1.label)")
        // A second voice while the first still speaks: it plays, and the first one no longer does.
        reach(f1)
        f1.tap()
        XCTAssertTrue(says(f1, "Playing the sample", 10), "F1's sample did not play:\n\(f1.label)")
        XCTAssertFalse(m1.label.contains("Playing the sample"), "the earlier sample still says it plays")
        // The same voice again: a tap is a request, never ignored.
        f1.tap()
        XCTAssertTrue(says(f1, "Playing the sample", 10), "F1 tapped again did not play:\n\(f1.label)")
        // A voice the gateway cannot speak: its row says why, in one line.
        reach(m2)
        m2.tap()
        XCTAssertTrue(says(m2, "The sample did not play:", 8), "a failed sample is silent:\n\(m2.label)")
        XCTAssertTrue(m2.label.contains("not loaded"), m2.label)
    }
}
