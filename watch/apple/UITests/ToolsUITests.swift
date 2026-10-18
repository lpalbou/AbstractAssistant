import XCTest

/// The tools of a conversation and the defaults for new ones (sample data: files, web and system
/// set up; email and agora not). `SHOTS_DIR` receives a screenshot of each step.
final class ToolsUITests: XCTestCase {
    private var app: XCUIApplication!
    private func shot(_ name: String) {
        guard let dir = ProcessInfo.processInfo.environment["SHOTS_DIR"] else { return }
        try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent(name + ".png"))
    }
    private func element(_ id: String) -> XCUIElement { app.descendants(matching: .any)[id].firstMatch }
    private func reveal(_ e: XCUIElement) {
        for _ in 0..<10 where !(e.exists && e.isHittable) { app.swipeUp(); usleep(300_000) }
    }
    private func isSelected(_ id: String) -> Bool { element(id).isSelected }

    /// The orb's tools icon opens this conversation's tools; a change there marks the icon.
    func testAConversationsToolsFromTheOrb() throws {
        app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--reset-tools", "--fresh-conversation", "--screen", "ask"]
        app.launch()
        let tools = app.buttons["ask.tools"]
        XCTAssertTrue(tools.waitForExistence(timeout: 20), "no tools icon on the orb:\n\(app.debugDescription)")
        XCTAssertEqual(tools.label, "Tools")
        shot("t1-orb")
        tools.tap()
        XCTAssertTrue(app.staticTexts["This conversation"].waitForExistence(timeout: 10), app.debugDescription)
        XCTAssertEqual(element("tools.summary").label, "5 auto · 4 ask", "the gateway's defaults")
        shot("t2-groups")
        // A group the gateway has not set up is listed, and says so.
        let email = element("tools.group.comms.email")
        reveal(email)
        XCTAssertTrue(email.label.contains("Not set up"), email.label)
        shot("t3-groups-end")
        for _ in 0..<6 { app.swipeDown() }
        element("tools.group.files").tap()
        let write = "tool.write_file"
        reveal(element("\(write).auto"))
        XCTAssertTrue(isSelected("\(write).ask"), "write_file asks by default")
        shot("t4-files")
        element("\(write).auto").tap()
        XCTAssertTrue(isSelected("\(write).auto") && !isSelected("\(write).ask"))
        XCTAssertEqual(element("\(write).default").label, "Default: Ask", "a change shows the default it overrides")
        XCTAssertEqual(element("\(write).auto").label, "Write file: Auto", "VoiceOver names the tool")
        shot("t5-files-changed")
        app.buttons["Back"].firstMatch.tap()
        XCTAssertTrue(element("tools.summary").waitForExistence(timeout: 5))
        XCTAssertEqual(element("tools.summary").label, "6 auto · 3 ask")
        XCTAssertTrue(app.buttons["Use my defaults"].exists, "a changed conversation offers its defaults back")
        app.buttons["Back"].firstMatch.tap()
        XCTAssertTrue(tools.waitForExistence(timeout: 5))
        XCTAssertEqual(tools.label, "Tools, changed for this conversation")
        shot("t6-orb-changed")
        // Defaults again.
        tools.tap()
        XCTAssertTrue(app.buttons["Use my defaults"].waitForExistence(timeout: 5))
        app.buttons["Use my defaults"].tap()
        XCTAssertEqual(element("tools.summary").label, "5 auto · 4 ask")
        XCTAssertFalse(app.buttons["Use my defaults"].exists)
    }

    /// Settings → Tools sets the defaults of new conversations; a group's All applies to its tools,
    /// and All auto leaves the tools that reach outside or destroy on Ask.
    func testDefaultsAndAGroupsAll() throws {
        app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--reset-tools", "--screen", "settings"]
        app.launch()
        let row = element("settings.tools")
        reveal(row)
        XCTAssertTrue(row.waitForExistence(timeout: 10), app.debugDescription)
        row.tap()
        XCTAssertTrue(app.staticTexts["Defaults"].waitForExistence(timeout: 10), app.debugDescription)
        element("tools.group.web").tap()
        // All auto counts the tools it reaches: fetch URL (the assistant picks where it goes) asks.
        XCTAssertTrue(isSelected("tools.all.web.auto") && isSelected("tool.fetch_url.ask"), app.debugDescription)
        element("tool.skim_url.ask").tap()
        XCTAssertTrue(app.staticTexts["Mixed"].waitForExistence(timeout: 3) && !isSelected("tools.all.web.auto"), "one reached tool on Ask: mixed")
        element("tools.all.web.off").tap()
        XCTAssertTrue(isSelected("tools.all.web.off") && isSelected("tool.web_search.off"))
        shot("t7-web-off")
        app.buttons["Back"].firstMatch.tap()
        XCTAssertEqual(element("tools.summary").label, "3 auto · 3 ask · 3 off")
        element("tools.group.system").tap()
        XCTAssertFalse(element("tools.all.system.auto").isEnabled, "All auto reaches no tool of System")
        XCTAssertTrue(isSelected("tool.execute_command.ask"), "a destructive tool is set to Auto only by itself")
        shot("t8-system")
        app.buttons["Back"].firstMatch.tap()
        element("tools.group.web").tap()
        element("tools.all.web.auto").tap()
        XCTAssertTrue(isSelected("tool.web_search.auto") && isSelected("tool.fetch_url.ask"), "All auto leaves fetch URL on Ask")
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "Tools that reach outside")).firstMatch.exists)
        shot("t9-web-all-auto")
    }
}
