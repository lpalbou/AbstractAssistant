import XCTest

/// Automations: a switch turns one off and on (the gateway's pause and resume), the archive button
/// archives one after a confirmation, and Archived restores it. Sample data.
final class AutomationsListUITests: XCTestCase {
    func testSwitchArchiveAndRestore() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--screen", "automations"]
        app.launch()
        func shot(_ name: String) {
            guard let dir = ProcessInfo.processInfo.environment["SHOTS_DIR"] else { return }
            try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent(name + ".png"))
        }
        let toggle = app.switches.matching(identifier: "automation.active").firstMatch
        XCTAssertTrue(toggle.waitForExistence(timeout: 15), app.debugDescription)
        XCTAssertEqual(toggle.value as? String, "1", "the morning digest is on")
        shot("a1-list")
        toggle.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        func waitValue(_ v: String) -> Bool {
            let end = Date().addingTimeInterval(5)
            while Date() < end { if (toggle.value as? String) == v { return true }; usleep(200_000) }
            return false
        }
        XCTAssertTrue(waitValue("0"), "the switch did not turn off")
        XCTAssertTrue(app.staticTexts["Paused"].waitForExistence(timeout: 5), "the schedule line says it is paused")
        shot("a2-off")
        toggle.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        XCTAssertTrue(waitValue("1"), "the switch did not turn back on")
        // Archive the first one: it asks, then it leaves the list.
        app.buttons.matching(identifier: "automation.archive").firstMatch.tap()
        let confirm = app.descendants(matching: .any)["archive.confirm"].firstMatch
        XCTAssertTrue(confirm.waitForExistence(timeout: 5), "archiving does not ask first")
        XCTAssertTrue(app.staticTexts["Archive this automation?"].exists)
        shot("a3-confirm")
        confirm.tap()
        let digest = app.buttons.matching(NSPredicate(format: "label CONTAINS 'Morning digest'")).firstMatch
        XCTAssertTrue(digest.waitForNonExistence(timeout: 10), "the archived automation is still listed")
        // Archived lists it; Restore brings it back.
        let archived = app.descendants(matching: .any)["automations.archived"].firstMatch
        for _ in 0..<8 where !(archived.exists && archived.isHittable) { app.nudgeUp() }
        archived.tap()
        let restore = app.descendants(matching: .any)["archived.automation.restore"].firstMatch
        XCTAssertTrue(restore.waitForExistence(timeout: 10), app.debugDescription)
        shot("a4-archived")
        restore.tap()
        XCTAssertTrue(restore.waitForNonExistence(timeout: 10))
        app.buttons["Back"].firstMatch.tap()
        // The list is still scrolled to its end: back up to the first row.
        for _ in 0..<10 where !digest.exists { app.nudgeDown() }
        XCTAssertTrue(digest.waitForExistence(timeout: 15), "the restored automation is not back")
    }

    /// The list shows each automation by its name only (two may share one), with how many times it
    /// ran; its page shows its instructions whole.
    func testTheListShowsNamesAndThePageTheInstructions() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--screen", "automations"]
        app.launch()
        func shot(_ name: String) {
            guard let dir = ProcessInfo.processInfo.environment["SHOTS_DIR"] else { return }
            try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent(name + ".png"))
        }
        XCTAssertTrue(app.switches.matching(identifier: "automation.active").firstMatch.waitForExistence(timeout: 15), app.debugDescription)
        XCTAssertTrue(app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS 'Ran 41 times'")).firstMatch.exists,
                      "the morning digest does not say how many times it ran")
        let news = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", "investigate today's news.")).element(boundBy: 1)
        for _ in 0..<10 where !(news.exists && news.isHittable) { app.nudgeUp() }
        XCTAssertTrue(news.exists, app.debugDescription)
        XCTAssertFalse(app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS 'expert'")).firstMatch.exists,
                       "the list shows more than the names")
        XCTAssertTrue(app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS 'Ran 42 times'")).firstMatch.exists)
        shot("a6-names")
        usleep(800_000)
        news.tap()
        let whole = app.descendants(matching: .any)["automation.instructions"].firstMatch
        XCTAssertTrue(whole.waitForExistence(timeout: 10), app.debugDescription)
        XCTAssertTrue(whole.label.contains("international political and economic stories, and you provide informative and actionable digests."), whole.label)
        XCTAssertFalse(app.descendants(matching: .any)["automation.task"].exists, "the page repeats the task")
        shot("a7-instructions")
    }
}
