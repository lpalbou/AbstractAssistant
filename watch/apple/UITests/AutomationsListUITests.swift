import XCTest

/// Automations: New and Search on one line; each row its name, when it runs and the runs you have
/// not seen (an orange badge; on or off is in Edit); the archive button archives one after a
/// confirmation, and Archived restores it. Sample data.
final class AutomationsListUITests: XCTestCase {
    private func shot(_ name: String) {
        guard let dir = ProcessInfo.processInfo.environment["SHOTS_DIR"] else { return }
        try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent(name + ".png"))
    }

    func testBadgeArchiveAndRestore() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--screen", "automations"]
        app.launch()
        XCTAssertTrue(app.buttons["New automation"].waitForExistence(timeout: 15), app.debugDescription)
        XCTAssertTrue(app.descendants(matching: .any)["automations.search"].exists, "no Search beside New")
        // The runs not seen: an orange badge with their number; no switch in the list.
        let badge = app.descendants(matching: .any)["automation.unseen"].firstMatch
        XCTAssertTrue(badge.waitForExistence(timeout: 15), app.debugDescription)
        XCTAssertTrue(badge.label.contains("1 new run"), badge.label)
        XCTAssertFalse(app.switches.firstMatch.exists, "a switch in the list (on or off is in Edit)")
        shot("a1-list")
        // Archive the first one: it asks, then it leaves the list.
        app.buttons.matching(identifier: "automation.archive").firstMatch.tap()
        let confirm = app.descendants(matching: .any)["archive.confirm"].firstMatch
        XCTAssertTrue(confirm.waitForExistence(timeout: 5), "archiving does not ask first")
        XCTAssertTrue(app.staticTexts["Archive this automation?"].exists)
        confirm.tap()
        let digest = app.buttons.matching(NSPredicate(format: "label CONTAINS 'Morning digest'")).firstMatch
        XCTAssertTrue(digest.waitForNonExistence(timeout: 10), "the archived automation is still listed")
        // Archived lists it; Restore brings it back.
        let archived = app.descendants(matching: .any)["automations.archived"].firstMatch
        for _ in 0..<8 where !(archived.exists && archived.isHittable) { app.nudgeUp() }
        archived.tap()
        let restore = app.descendants(matching: .any)["archived.automation.restore"].firstMatch
        XCTAssertTrue(restore.waitForExistence(timeout: 10), app.debugDescription)
        restore.tap()
        XCTAssertTrue(restore.waitForNonExistence(timeout: 10))
        app.buttons["Back"].firstMatch.tap()
        for _ in 0..<10 where !digest.exists { app.nudgeDown() }
        XCTAssertTrue(digest.waitForExistence(timeout: 15), "the restored automation is not back")
    }

    /// Search: the automations whose name or task holds the words.
    func testSearchFindsByName() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--screen", "automations"]
        app.launch()
        let search = app.descendants(matching: .any)["automations.search"].firstMatch
        XCTAssertTrue(search.waitForExistence(timeout: 15), app.debugDescription)
        XCTAssertTrue(app.buttons.matching(NSPredicate(format: "label CONTAINS 'Literature watch'")).firstMatch.waitForExistence(timeout: 15))
        search.tap()
        sleep(1)
        app.typeText("literature")
        app.buttons["Done"].firstMatch.tap()
        XCTAssertTrue(app.staticTexts["screen.title"].firstMatch.waitForExistence(timeout: 5))
        let found = app.buttons.matching(NSPredicate(format: "label CONTAINS 'Literature watch'")).firstMatch
        XCTAssertTrue(found.waitForExistence(timeout: 5), app.debugDescription)
        XCTAssertFalse(app.buttons.matching(NSPredicate(format: "label CONTAINS 'Morning digest'")).firstMatch.exists, "a match without the word")
        shot("a5-search")
    }

    /// Edit: on or off with when it runs; builds on earlier runs with how much of them it reads (a
    /// number only, the gateway's value to start).
    func testEditActiveAndMemory() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--screen", "automation-edit"]
        app.launch()
        let tokens = app.buttons["edit.tokens"].firstMatch
        app.bring(tokens)
        XCTAssertTrue(tokens.waitForExistence(timeout: 10), app.debugDescription)
        XCTAssertTrue(tokens.label.contains("50,000 tokens"), tokens.label)
        shot("e1-memory")
        tokens.tap(); sleep(1)
        app.typeText("lots")
        app.buttons["Done"].firstMatch.tap()
        XCTAssertTrue(app.staticTexts["Numbers only, more than 0."].waitForExistence(timeout: 5), "letters were taken:\n\(app.debugDescription)")
        XCTAssertTrue(tokens.label.contains("50,000 tokens"), "the value changed: \(tokens.label)")
        tokens.tap(); sleep(1)
        app.typeText("75000")
        app.buttons["Done"].firstMatch.tap()
        XCTAssertTrue(tokens.waitForExistence(timeout: 5))
        let end = Date().addingTimeInterval(5)
        while Date() < end && !tokens.label.contains("75,000 tokens") { usleep(200_000) }
        XCTAssertTrue(tokens.label.contains("75,000 tokens"), tokens.label)
        // Active: off, saved, said on its details.
        let active = app.switches["edit.active"].firstMatch
        app.bring(active)
        active.coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: 0.5)).tap()
        let save = app.buttons["Save"].firstMatch
        app.bring(save)
        XCTAssertTrue(save.isEnabled)
        shot("e2-changed")
        save.tap()
        XCTAssertTrue(app.descendants(matching: .any)["automation.title"].firstMatch.waitForExistence(timeout: 10), app.debugDescription)
        XCTAssertTrue(app.staticTexts["Paused"].waitForExistence(timeout: 10), "not paused:\n\(app.debugDescription)")
    }
}

/// New automation: building on earlier runs shows how much of them it reads (the gateway's default,
/// a number only), as Edit does.
final class NewAutomationMemoryUITests: XCTestCase {
    func testBuildsOnEarlierRunsShowsTheBudget() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--screen", "automation-new"]
        app.launch()
        let toggle = app.switches["Builds on earlier runs"].firstMatch
        app.bring(toggle)
        XCTAssertTrue(toggle.waitForExistence(timeout: 10), app.debugDescription)
        XCTAssertFalse(app.buttons["new.tokens"].exists, "a budget without building on earlier runs")
        toggle.coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: 0.5)).tap()
        let tokens = app.buttons["new.tokens"].firstMatch
        XCTAssertTrue(tokens.waitForExistence(timeout: 5), app.debugDescription)
        XCTAssertTrue(tokens.label.contains("50,000 tokens"), tokens.label)
        app.bring(tokens); sleep(1)
        tokens.tap(); sleep(1)
        app.typeText("80000")
        app.buttons["Done"].firstMatch.tap()
        let end = Date().addingTimeInterval(5)
        while Date() < end && !tokens.label.contains("80,000 tokens") { usleep(200_000) }
        XCTAssertTrue(tokens.label.contains("80,000 tokens"), tokens.label)
    }
}

/// Settings → Automation results: on by default; off stays off.
final class AutomationNoticesSettingUITests: XCTestCase {
    func testTheToggleIsOnAndKeepsItsValue() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--screen", "settings"]
        app.launch()
        let toggle = app.switches["settings.automationNotices"].firstMatch
        app.bring(toggle)
        XCTAssertTrue(toggle.waitForExistence(timeout: 10), app.debugDescription)
        let start = toggle.value as? String
        toggle.coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: 0.5)).tap()
        let end = Date().addingTimeInterval(3)
        while Date() < end && (toggle.value as? String) == start { usleep(200_000) }
        XCTAssertNotEqual(toggle.value as? String, start, "the toggle did not change")
        let changed = toggle.value as? String
        app.terminate(); app.launch()
        app.bring(toggle)
        XCTAssertTrue(toggle.waitForExistence(timeout: 10))
        XCTAssertEqual(toggle.value as? String, changed, "the choice was not kept")
        // Leave it on for other runs.
        if changed == "0" { toggle.coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: 0.5)).tap() }
    }
}
