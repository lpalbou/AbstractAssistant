import XCTest

/// New automation: the task, the workflow and the schedule are chosen, Create opens the new
/// automation's page (sample data). With `GW_URL` + `GW_TOKEN` (TEST_RUNNER_ prefixed), the
/// workflow list is read from a real gateway (nothing is created).
final class NewAutomationUITests: XCTestCase {
    private func shot(_ name: String) {
        guard let dir = ProcessInfo.processInfo.environment["SHOTS_DIR"] else { return }
        try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent(name + ".png"))
    }

    func testCreateWithSampleData() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--reset-tools", "--screen", "automation-new"]
        app.launch()
        let task = app.descendants(matching: .any)["new.task"].firstMatch
        XCTAssertTrue(task.waitForExistence(timeout: 10))
        XCTAssertFalse(app.buttons["Create"].isEnabled, "Create needs a task")
        shot("n1-empty")
        task.tap()
        sleep(1)
        app.typeText("Summarise the overnight QC runs")
        app.buttons["Done"].firstMatch.tap()
        sleep(1)
        // The default workflow by its name, never "Gateway default".
        let workflow = app.buttons["Workflow: Basic agent · default"].firstMatch
        XCTAssertTrue(workflow.waitForExistence(timeout: 10), app.debugDescription)
        // Its tools: from the defaults, changed here for this automation only.
        let tools = app.buttons["new.tools"].firstMatch
        XCTAssertEqual(tools.label, "Tools: 5 auto · 4 ask")
        tools.tap()
        XCTAssertTrue(app.staticTexts["This automation"].waitForExistence(timeout: 10), app.debugDescription)
        shot("n1b-tools")
        app.descendants(matching: .any)["tools.group.web"].firstMatch.tap()
        let off = app.descendants(matching: .any)["tools.all.web.off"].firstMatch
        XCTAssertTrue(off.waitForExistence(timeout: 5))
        off.tap()
        app.buttons["Back"].firstMatch.tap()
        app.buttons["Back"].firstMatch.tap()
        XCTAssertTrue(tools.waitForExistence(timeout: 5))
        XCTAssertEqual(tools.label, "Tools: 3 auto · 3 ask · 3 off · changed", "the automation keeps its tools")
        workflow.tap()
        let deep = app.buttons["Deep research"].firstMatch
        XCTAssertTrue(deep.waitForExistence(timeout: 5))
        shot("n2-workflows")
        deep.tap()
        sleep(1)
        app.buttons["When: Every day"].firstMatch.tap()
        let eight = app.buttons["Every 8 hours"].firstMatch
        // From 30 s to a week: 8 hours is further down the list.
        XCTAssertTrue(app.buttons["Every 30 sec"].firstMatch.waitForExistence(timeout: 5), app.debugDescription)
        XCTAssertTrue(ScheduleChoicesUITests.scrollTo(eight, in: app), app.debugDescription)
        eight.tap()
        sleep(1)
        shot("n3-filled")
        XCTAssertTrue(app.buttons["Workflow: Deep research"].exists && app.buttons["When: Every 8 hours"].exists)
        let create = app.buttons["Create"].firstMatch
        for _ in 0..<3 where !create.isHittable { app.swipeUp() }
        create.tap()
        // The new automation's page: its title is the task.
        XCTAssertTrue(app.staticTexts["Summarise the overnight QC runs"].waitForExistence(timeout: 10), app.debugDescription)
        shot("n4-created")
    }

    func testWorkflowsFromTheGateway() throws {
        let env = ProcessInfo.processInfo.environment
        guard let url = env["GW_URL"], let token = env["GW_TOKEN"] else { throw XCTSkip("no gateway given") }
        let app = XCUIApplication()
        app.launchArguments = ["--gateway", url, "--token", token, "--no-notification-prompt", "--screen", "automation-new"]
        app.launch()
        let row = app.buttons["new.workflow"].firstMatch
        XCTAssertTrue(row.waitForExistence(timeout: 20))
        sleep(6)                                   // the list loads while the form shows
        XCTAssertTrue(row.label.hasSuffix("· default"), row.label)
        row.tap()
        XCTAssertTrue(app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "Basic agent")).firstMatch.waitForExistence(timeout: 20), app.debugDescription)
        shot("n5-live-workflows")
    }
}
