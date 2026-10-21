import XCTest

/// Against a live gateway: an automation's title and task edited on the watch are saved (the
/// gateway's definition moves to the next revision) and shown on its page and in Edit at once.
/// Runs only with LIVE_GW_URL, LIVE_GW_TOKEN and LIVE_AUTOMATION_INDEX (the scratch automation's
/// place in the list, newest first).
final class LiveEditUITests: XCTestCase {
    func testTitleAndTaskAreSaved() throws {
        let env = ProcessInfo.processInfo.environment
        guard let url = env["LIVE_GW_URL"], let token = env["LIVE_GW_TOKEN"], let index = env["LIVE_AUTOMATION_INDEX"] else { throw XCTSkip("live only") }
        let app = XCUIApplication()
        app.launchArguments = ["--no-notification-prompt", "--gateway", url, "--token", token, "--open-automation", index]
        app.launch()
        func shot(_ name: String) {
            let dir = env["SHOTS_DIR"] ?? NSTemporaryDirectory()
            try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent(name + ".png"))
        }
        let title = app.descendants(matching: .any)["automation.title"].firstMatch
        XCTAssertTrue(title.waitForExistence(timeout: 120), app.debugDescription)
        let before = title.label
        // The page reads the definition; Edit then opens with it at once.
        XCTAssertTrue(app.descendants(matching: .any)["automation.title"].waitForExistence(timeout: 60), app.debugDescription)
        sleep(3)
        let edit = app.buttons["Edit"].firstMatch
        let opened = Date()
        edit.tap()
        let titleField = app.descendants(matching: .any)["edit.title"].firstMatch
        XCTAssertTrue(titleField.waitForExistence(timeout: 60), app.debugDescription)
        let took = Date().timeIntervalSince(opened)
        print("edit fields after \(String(format: "%.1f", took)) s")
        // (Timing cannot tell a kept definition from a fresh read on a small automation: the mock's
        // EditTextUITests, with a 3 s read, check that Edit does not read it again.)
        shot("live-e1")
        for (id, extra) in [("edit.title", " renamed"), ("edit.task", " now")] {
            let field = app.descendants(matching: .any)[id].firstMatch
            for _ in 0..<6 where !(field.exists && field.isHittable) { app.nudgeUp() }
            field.tap(); sleep(1)
            app.typeText(extra)
            app.buttons["Done"].firstMatch.tap(); sleep(1)
        }
        shot("live-e2")
        let save = app.buttons["Save"].firstMatch
        for _ in 0..<6 where !(save.exists && save.isHittable) { app.nudgeUp() }
        XCTAssertTrue(save.isEnabled, "Save is off after a change")
        let saved = Date()
        save.tap()
        // The page shows the new title at once (the gateway applies the edit a few seconds later).
        let deadline = Date().addingTimeInterval(30)
        while Date() < deadline && !(title.exists && title.label == before + " renamed") { usleep(200_000) }
        XCTAssertEqual(title.label, before + " renamed", app.debugDescription)
        print("new title shown after \(String(format: "%.1f", Date().timeIntervalSince(saved))) s")
        shot("live-e3")
        // Edit again: both hold what was saved.
        edit.tap()
        XCTAssertTrue(titleField.waitForExistence(timeout: 30))
        XCTAssertEqual(titleField.value as? String, before + " renamed")
        XCTAssertTrue((app.descendants(matching: .any)["edit.task"].firstMatch.value as? String ?? "").hasSuffix(" now"))
        shot("live-e4")
    }
}
