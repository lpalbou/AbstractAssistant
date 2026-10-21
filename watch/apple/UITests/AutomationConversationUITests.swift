import XCTest

/// An automation is a conversation its trigger writes in: the same orb page (its runs as messages,
/// the voice, Share), (i) for its details where a conversation has its tools; Run now is followed on
/// the orb; talking about it opens a conversation about it; Sessions lists it. Sample data.
final class AutomationConversationUITests: XCTestCase {
    private func shot(_ name: String) {
        guard let dir = ProcessInfo.processInfo.environment["SHOTS_DIR"] else { return }
        try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent(name + ".png"))
    }

    func testAnAutomationIsAConversation() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--orb-design", "A", "--screen", "automations"]
        app.launch()
        let digest = app.buttons.matching(NSPredicate(format: "label CONTAINS 'Morning digest'")).firstMatch
        XCTAssertTrue(digest.waitForExistence(timeout: 15), app.debugDescription)
        digest.tap()
        // The orb page: its name where a conversation shows who answers, (i) where it has its tools.
        let name = app.staticTexts["ask.automation"].firstMatch
        XCTAssertTrue(name.waitForExistence(timeout: 10), app.debugDescription)
        XCTAssertEqual(name.label, "Morning digest")
        XCTAssertTrue(app.buttons["ask.info"].waitForExistence(timeout: 5), "no (i):\n\(app.debugDescription)")
        XCTAssertFalse(app.buttons["ask.tools"].exists, "an automation's tools are in its details")
        XCTAssertTrue(app.buttons["Share"].waitForExistence(timeout: 10), "no Share: its runs are not its messages")
        shot("c1-orb")
        // Its runs below, as a conversation's messages: the latest in full, the earlier ones as cards.
        let latest = app.staticTexts.matching(NSPredicate(format: "label CONTAINS 'Three things today'")).firstMatch
        app.bring(latest)
        XCTAssertTrue(latest.exists, "the latest run is not the last message:\n\(app.debugDescription)")
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS 'Summarise what changed overnight'")).firstMatch.exists,
                      "the message its trigger sent is not shown")
        let earlier = app.buttons.matching(identifier: "message.row").firstMatch
        app.bring(earlier)
        XCTAssertTrue(earlier.exists, "no earlier runs as messages")
        shot("c2-messages")
        // (i): its details; Run now goes back to the orb, which follows the run, then its answer.
        for _ in 0..<3 { app.swipeDown() }                   // back to the top: the orb and its icons
        sleep(1)
        XCTAssertTrue(app.buttons["ask.info"].waitForExistence(timeout: 5), "no (i) back at the top:\n\(app.debugDescription)")
        app.buttons["ask.info"].tap()
        XCTAssertTrue(app.descendants(matching: .any)["automation.title"].firstMatch.waitForExistence(timeout: 10), app.debugDescription)
        shot("c3-info")
        let runNow = app.buttons["automation.run"].firstMatch
        XCTAssertTrue(runNow.waitForExistence(timeout: 5)); sleep(1)       // the page has slid in
        runNow.tap()
        // Back on the orb page, which follows the run at once (its controls hide while it works).
        XCTAssertTrue(app.buttons["ask.stop"].waitForExistence(timeout: 15), "Run now is not followed on the orb page:\n\(app.debugDescription)")
        XCTAssertFalse(app.descendants(matching: .any)["automation.title"].exists, "still on the details")
        shot("c4-working")
        let answer = app.staticTexts.matching(NSPredicate(format: "label CONTAINS 'Digest 42'")).firstMatch
        XCTAssertTrue(answer.waitForExistence(timeout: 40), "the run's answer did not come:\n\(app.debugDescription)")
        shot("c5-answer")
    }

    /// Talking on an automation's page opens a conversation about it (its own context untouched):
    /// the page goes on as a conversation (its tools, no (i)).
    func testTalkingAboutAnAutomation() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--orb-design", "A", "--screen", "automation",
                               "--test-ask", "Which plates failed?"]
        app.launch()
        let answer = app.staticTexts.matching(NSPredicate(format: "label CONTAINS 'About that run'")).firstMatch
        XCTAssertTrue(answer.waitForExistence(timeout: 30), app.debugDescription)
        // Once its voice has read the answer, the controls of a conversation show: its tools.
        XCTAssertTrue(app.buttons["ask.tools"].waitForExistence(timeout: 40), "the page did not become a conversation:\n\(app.debugDescription)")
        XCTAssertFalse(app.buttons["ask.info"].exists)
        shot("c6-discussion")
    }

    /// Sessions lists the automations with the conversations; a tap opens its orb page.
    func testSessionsListsAutomations() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--screen", "sessions"]
        app.launch()
        XCTAssertTrue(app.buttons["New conversation"].waitForExistence(timeout: 15), app.debugDescription)
        let row = app.descendants(matching: .any).matching(identifier: "sessions.automation")
            .matching(NSPredicate(format: "label CONTAINS 'Morning digest'")).firstMatch
        app.bring(row)
        XCTAssertTrue(row.exists, "Morning digest is not in Sessions:\n\(app.debugDescription)")
        shot("c7-sessions")
        row.tap()
        XCTAssertTrue(app.staticTexts["ask.automation"].waitForExistence(timeout: 10), app.debugDescription)
    }
}

/// A new conversation takes the tools set in Settings → Tools, whichever way it starts.
final class NewConversationToolsUITests: XCTestCase {
    func testANewConversationTakesTheDefaults() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--reset-tools", "--screen", "settings"]
        app.launch()
        func element(_ id: String) -> XCUIElement { app.descendants(matching: .any)[id].firstMatch }
        // Defaults: Web off.
        let tools = element("settings.tools")
        app.bring(tools)
        XCTAssertTrue(tools.waitForExistence(timeout: 10), app.debugDescription)
        tools.tap()
        XCTAssertTrue(app.staticTexts["Defaults"].waitForExistence(timeout: 10), app.debugDescription)
        element("tools.group.web").tap(); sleep(1)
        element("tools.all.web.off").tap()
        app.buttons["Back"].firstMatch.tap()
        XCTAssertEqual(element("tools.summary").label, "3 auto · 3 ask · 3 off")
        app.buttons["Back"].firstMatch.tap(); sleep(1)
        app.buttons["Back"].firstMatch.tap(); sleep(1)
        // The Home orb: a new conversation, on the defaults.
        func newConversationTools(_ start: () -> Void, _ what: String) {
            start()
            let icon = app.buttons["ask.tools"]
            XCTAssertTrue(icon.waitForExistence(timeout: 15), "\(what): no tools icon:\n\(app.debugDescription)")
            XCTAssertEqual(icon.label, "Tools", "\(what): marked as changed")
            icon.tap()
            XCTAssertTrue(element("tools.summary").waitForExistence(timeout: 10))
            XCTAssertEqual(element("tools.summary").label, "3 auto · 3 ask · 3 off", "\(what): not the defaults")
        }
        newConversationTools({ app.buttons["Talk to Assistant"].firstMatch.tap() }, "Home orb")
        // Changed for this conversation only.
        element("tools.group.files").tap(); sleep(1)
        element("tools.all.files.off").tap()
        app.buttons["Back"].firstMatch.tap(); sleep(1)
        app.buttons["Back"].firstMatch.tap(); sleep(1)
        XCTAssertEqual(app.buttons["ask.tools"].label, "Tools, changed for this conversation")
        app.buttons["Back"].firstMatch.tap(); sleep(1)
        // Sessions → New: the defaults again.
        app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Sessions'")).firstMatch.tap()
        newConversationTools({ app.buttons["New conversation"].firstMatch.tap() }, "Sessions → New")
    }
}

/// An automation's page shows its latest run at once while its runs are read.
/// Its details, back after a Run, say it is running (Stop).
final class AutomationLoadingUITests: XCTestCase {
    /// Its latest run shows at once (as the list has it), while its runs are read: no spinner.
    func testTheLatestRunShowsAtOnce() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--orb-design", "A", "--screen", "automation"]
        app.launch()
        XCTAssertTrue(app.buttons["Share"].waitForExistence(timeout: 2.5), "the latest run is not shown at once:\n\(app.debugDescription)")
        XCTAssertFalse(app.descendants(matching: .any)["ask.loading"].exists, "a spinner over a run already known")
        let earlier = app.buttons.matching(identifier: "message.row").firstMatch
        app.bring(earlier)
        XCTAssertTrue(earlier.waitForExistence(timeout: 15), "the earlier runs never came")
    }

    func testDetailsSayItIsRunningAfterRun() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--orb-design", "A", "--screen", "automation-info"]
        app.launch()
        let run = app.buttons["automation.run"].firstMatch
        XCTAssertTrue(run.waitForExistence(timeout: 10), app.debugDescription)
        sleep(1)
        run.tap()
        XCTAssertTrue(app.buttons["ask.stop"].waitForExistence(timeout: 15), "not back on the orb, following the run")
        // Forward (a swipe to the left): its details, saying it runs.
        app.coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: 0.55))
            .press(forDuration: 0.02, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.08, dy: 0.55)), withVelocity: .fast, thenHoldForDuration: 0)
        let stop = app.buttons["Stop this run"].firstMatch
        XCTAssertTrue(stop.waitForExistence(timeout: 10), "the details do not say it is running:\n\(app.debugDescription)")
    }
}
