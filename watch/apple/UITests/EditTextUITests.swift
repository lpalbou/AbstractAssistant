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
        XCTAssertFalse(app.descendants(matching: .any)["edit.title"].exists, "one field only: the task")
        let task = app.descendants(matching: .any)["edit.task"].firstMatch
        XCTAssertTrue(task.waitForExistence(timeout: 10))
        shot("1-edit")
        try open(app, field: task, expect: "Summarise the overnight assay QC runs, new papers on my target, and dependency updates to pin.",
                 shotName: "2-task-editor")
    }
}
