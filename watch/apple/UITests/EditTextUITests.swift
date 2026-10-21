import XCTest

/// Editing an automation's task starts from the current text (a text-field link opened empty).
/// `SHOTS_DIR` (TEST_RUNNER_SHOTS_DIR from xcodebuild) receives screenshots of each step.
final class EditTextUITests: XCTestCase {
    private func shot(_ name: String) {
        guard let dir = ProcessInfo.processInfo.environment["SHOTS_DIR"] else { return }
        try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent(name + ".png"))
    }

    /// Taps a field: the system editor (a text view with the keyboard) must hold the current text.
    private func open(_ app: XCUIApplication, field: XCUIElement, expect: String, shotName: String) throws {
        field.tap()
        let editor = app.textViews.matching(NSPredicate(format: "value == %@", expect)).firstMatch
        XCTAssertTrue(editor.waitForExistence(timeout: 5), "the editor did not open with the current text:\n\(app.debugDescription)")
        shot(shotName)
    }

    func testTheTaskOpensWithItsCurrentText() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--screen", "automation-edit"]
        app.launch()
        let task = app.descendants(matching: .any)["edit.task"].firstMatch
        XCTAssertTrue(task.waitForExistence(timeout: 10))
        XCTAssertTrue(app.descendants(matching: .any)["edit.title"].exists, "the title has its own field")
        shot("1-edit")
        try open(app, field: task, expect: "Summarise the overnight assay QC runs, new papers on my target, and dependency updates to pin.",
                 shotName: "2-task-editor")
    }

    /// The title is edited on its own: Save sends it, and the automation's page and list show it.
    func testTheTitleIsEditedOnItsOwn() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--screen", "automation-edit"]
        app.launch()
        let title = app.descendants(matching: .any)["edit.title"].firstMatch
        XCTAssertTrue(title.waitForExistence(timeout: 10), app.debugDescription)
        XCTAssertFalse(app.buttons["Save"].isEnabled, "nothing changed yet")
        try open(app, field: title, expect: "Morning digest", shotName: "3-title-editor")
        app.typeText(" on weekdays")
        app.buttons["Done"].firstMatch.tap()
        sleep(1)
        shot("4-title-changed")
        let save = app.buttons["Save"].firstMatch
        XCTAssertTrue(save.isEnabled, "the new title is not a change")
        save.tap()
        let shown = app.descendants(matching: .any)["automation.title"].firstMatch
        XCTAssertTrue(shown.waitForExistence(timeout: 10), app.debugDescription)
        let deadline = Date().addingTimeInterval(10)
        while Date() < deadline && shown.label != "Morning digest on weekdays" { usleep(250_000) }
        XCTAssertEqual(shown.label, "Morning digest on weekdays")
        shot("5-title-saved")
    }

    /// Back with a change asks: Discard leaves it as it was, Save saves it.
    func testLeavingWithChangesAsks() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--screen", "automation-edit"]
        app.launch()
        let title = app.descendants(matching: .any)["edit.title"].firstMatch
        XCTAssertTrue(title.waitForExistence(timeout: 10), app.debugDescription)
        try open(app, field: title, expect: "Morning digest", shotName: "6-title-editor")
        app.typeText(" draft")
        app.buttons["Done"].firstMatch.tap(); sleep(1)
        app.buttons["Back"].firstMatch.tap()
        XCTAssertTrue(app.staticTexts["Save your changes?"].waitForExistence(timeout: 5), "leaving with a change does not ask:\n\(app.debugDescription)")
        shot("7-leave-asks")
        app.buttons["Discard"].firstMatch.tap()
        let shown = app.descendants(matching: .any)["automation.title"].firstMatch
        XCTAssertTrue(shown.waitForExistence(timeout: 10), app.debugDescription)
        XCTAssertEqual(shown.label, "Morning digest", "Discard changed it")
        // Again, and Save this time.
        app.buttons["Edit"].firstMatch.tap()
        XCTAssertTrue(title.waitForExistence(timeout: 10))
        try open(app, field: title, expect: "Morning digest", shotName: "8-title-editor")
        app.typeText(" kept")
        app.buttons["Done"].firstMatch.tap(); sleep(1)
        app.buttons["Back"].firstMatch.tap()
        // The dialog's Save (the page's own Save is under it).
        XCTAssertTrue(app.staticTexts["Save your changes?"].waitForExistence(timeout: 5))
        guard let save = app.buttons.matching(NSPredicate(format: "label == 'Save'")).allElementsBoundByIndex.first(where: { $0.isHittable }) else {
            return XCTFail("no Save in the dialog:\n\(app.debugDescription)")
        }
        save.tap()
        XCTAssertTrue(shown.waitForExistence(timeout: 10))
        let end = Date().addingTimeInterval(5)
        while Date() < end && shown.label != "Morning digest kept" { usleep(200_000) }
        XCTAssertEqual(shown.label, "Morning digest kept")
        // Its orb page and the list show it too, at once.
        app.buttons["Back"].firstMatch.tap()
        XCTAssertTrue(app.staticTexts["Morning digest kept"].waitForExistence(timeout: 5), app.debugDescription)
        app.buttons["Back"].firstMatch.tap()
        XCTAssertTrue(app.buttons.matching(NSPredicate(format: "label CONTAINS 'Morning digest kept'")).firstMatch.waitForExistence(timeout: 5),
                      app.debugDescription)
        shot("9-list-shows-it")
    }

    /// The page reads the automation once: Edit then opens with it at once (a definition takes 3 s
    /// here, as on a public gateway).
    func testEditOpensAtOnceWithWhatThePageRead() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--slow-definitions", "--open-automation", "3"]
        app.launch()
        // Its orb page, then its details (they read the definition).
        let info = app.buttons["ask.info"].firstMatch
        XCTAssertTrue(info.waitForExistence(timeout: 15), app.debugDescription)
        info.tap()
        XCTAssertTrue(app.descendants(matching: .any)["automation.title"].firstMatch.waitForExistence(timeout: 15), app.debugDescription)
        sleep(4)                                                  // the definition is read
        app.buttons["Edit"].firstMatch.tap()
        let opened = Date()
        let field = app.descendants(matching: .any)["edit.task"].firstMatch
        XCTAssertTrue(field.waitForExistence(timeout: 10), app.debugDescription)
        XCTAssertLessThan(Date().timeIntervalSince(opened), 1.5, "Edit read the automation again")
        XCTAssertEqual(field.value as? String, "investigate today's news.")
        XCTAssertFalse(app.descendants(matching: .any)["edit.instructions"].exists, "instructions are not an automation's")
        shot("10-edit-at-once")
    }
}
