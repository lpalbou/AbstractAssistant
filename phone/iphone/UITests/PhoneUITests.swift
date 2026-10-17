import XCTest

final class PhoneUITests: XCTestCase {
    @MainActor func testConversationAndNavigation() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--demo", "--ui-test"]
        app.launch()
        XCTAssertTrue(app.staticTexts["What’s on\nyour mind?"].waitForExistence(timeout: 10))
        capture(app, "Assistant")
        app.buttons["Find a little focus"].firstMatch.tap()
        app.buttons["Send message"].tap()
        XCTAssertTrue(app.buttons["Share answer"].firstMatch.waitForExistence(timeout: 30))
        let finished = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: app.buttons["Stop"].firstMatch)
        XCTAssertEqual(XCTWaiter.wait(for: [finished], timeout: 30), .completed)
        XCTAssertTrue(app.buttons["voice.orb"].exists)
        XCTAssertTrue(app.buttons["View conversation files (1)"].exists)
        XCTAssertTrue(app.buttons["Settings"].isHittable)
        XCTAssertTrue(app.buttons["voice.orb"].isHittable)
        capture(app, "Conversation")
        app.tabBars.buttons["Inbox"].tap()
        XCTAssertTrue(app.staticTexts["A little attention.\nA lot of progress."].exists)
        capture(app, "Inbox")
        app.tabBars.buttons["Automations"].tap()
        XCTAssertTrue(app.staticTexts["A rhythm\nof your own."].exists)
        capture(app, "Automations")
    }
    @MainActor func testApprovalShowsActionAndReturnsToInbox() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--demo", "--ui-test", "--screen", "inbox"]
        app.launch()
        let permission = app.buttons.containing(.staticText, identifier: "Permission to proceed").firstMatch
        XCTAssertTrue(permission.waitForExistence(timeout: 10)); permission.tap()
        XCTAssertTrue(app.buttons["Allow once"].waitForExistence(timeout: 10))
        capture(app, "Approval")
        app.buttons["Deny"].tap()
        XCTAssertTrue(app.staticTexts["A little attention.\nA lot of progress."].waitForExistence(timeout: 10))
    }
    @MainActor func testVoiceSettingsAndWorkflowAreAvailable() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test"]; app.launch()
        XCTAssertTrue(app.buttons["Settings"].waitForExistence(timeout: 10)); app.buttons["Settings"].tap()
        app.buttons["Voice & reading"].tap()
        XCTAssertTrue(app.switches["voice.readAloud"].waitForExistence(timeout: 10))
        // iOS exposes the whole labelled row as a switch; tap the actual trailing control.
        app.switches["voice.readAloud"].coordinate(withNormalizedOffset: CGVector(dx: 0.88, dy: 0.5)).tap()
        let enabled = XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == '1'"), object: app.switches["voice.readAloud"])
        XCTAssertEqual(XCTWaiter.wait(for: [enabled], timeout: 5), .completed)
        XCTAssertTrue(app.buttons["Preview voice"].exists)
        capture(app, "Voice settings")
        app.navigationBars.buttons.firstMatch.tap()
        app.buttons["Workflow"].tap()
        XCTAssertTrue(app.buttons["Save workflow"].waitForExistence(timeout: 10))
        capture(app, "Workflow settings")
    }
    @MainActor func testCreateAutomationOnThePhone() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test", "--screen", "automations"]; app.launch()
        XCTAssertTrue(app.buttons["New automation"].waitForExistence(timeout: 10)); app.buttons["New automation"].tap()
        let field = app.textFields["automation.task"].exists ? app.textFields["automation.task"] : app.textViews["automation.task"]
        XCTAssertTrue(field.waitForExistence(timeout: 10)); field.tap(); field.typeText("My phone daily briefing")
        app.buttons["Done"].firstMatch.tap()
        capture(app, "New automation")
        let create = app.buttons["automation.create"]
        for _ in 0..<4 { if create.isHittable { break }; app.swipeUp() }
        XCTAssertTrue(create.isHittable); create.tap()
        XCTAssertTrue(app.staticTexts["My phone daily briefing"].firstMatch.waitForExistence(timeout: 20))
        capture(app, "Created automation")
    }
    @MainActor func testConversationFilesAreVisible() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test"]; app.launch()
        XCTAssertTrue(app.buttons["Conversation files"].waitForExistence(timeout: 10)); app.buttons["Conversation files"].tap()
        XCTAssertTrue(app.staticTexts["A little focus.txt"].waitForExistence(timeout: 10))
        capture(app, "Conversation files")
    }
    @MainActor func testKeyboardExpandsInputHidesOrbAndOutsideTapRestoresButtons() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test"]; app.launch()
        let input = app.textFields["composer.input"]
        let keyboard = app.buttons["composer.keyboard"]
        let orb = app.buttons["voice.orb"]
        let attachment = app.buttons["Add attachment"]
        XCTAssertTrue(orb.waitForExistence(timeout: 10))
        XCTAssertTrue(keyboard.isHittable)
        XCTAssertFalse(input.exists)
        XCTAssertLessThan(abs(keyboard.frame.midY - attachment.frame.midY), 3)
        XCTAssertLessThan(abs(keyboard.frame.midY - orb.frame.midY), 3)
        XCTAssertGreaterThan(orb.frame.midX, app.frame.width * 0.75)
        capture(app, "Floating controls")
        keyboard.tap()
        XCTAssertTrue(input.waitForExistence(timeout: 5)); input.typeText("Keep this typed draft")
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 5))
        XCTAssertFalse(orb.exists)
        XCTAssertFalse(keyboard.exists)
        XCTAssertGreaterThan(input.frame.width, app.frame.width * 0.5)
        XCTAssertTrue(attachment.isHittable)
        XCTAssertTrue(app.buttons["Send message"].isHittable)
        XCTAssertFalse(app.buttons["Done"].exists)
        capture(app, "Keyboard composer")
        input.tap() // Caret and input taps keep editing active.
        XCTAssertTrue(app.keyboards.firstMatch.exists)
        app.staticTexts["What’s on\nyour mind?"].tap()
        let dismissed = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: app.keyboards.firstMatch)
        XCTAssertEqual(XCTWaiter.wait(for: [dismissed], timeout: 5), .completed)
        XCTAssertTrue(orb.isHittable)
        XCTAssertTrue(keyboard.isHittable)
        XCTAssertFalse(input.exists)
        XCTAssertEqual(keyboard.value as? String, "Draft saved")
        capture(app, "Minimized draft")
        keyboard.tap()
        XCTAssertTrue(input.waitForExistence(timeout: 5))
        XCTAssertEqual(input.value as? String, "Keep this typed draft")
        app.buttons["Send message"].tap()
        XCTAssertTrue(app.staticTexts["Keep this typed draft"].waitForExistence(timeout: 10))
        XCTAssertTrue(orb.waitForExistence(timeout: 5))
    }
    @MainActor func testOutsideTapPreservesTheAttachmentButtonAction() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test"]; app.launch()
        XCTAssertTrue(app.buttons["composer.keyboard"].waitForExistence(timeout: 10))
        app.buttons["composer.keyboard"].tap()
        app.textFields["composer.input"].typeText("A draft")
        app.buttons["Add attachment"].tap()
        XCTAssertTrue(app.buttons["Choose a file"].waitForExistence(timeout: 5))
        let dismissed = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: app.keyboards.firstMatch)
        XCTAssertEqual(XCTWaiter.wait(for: [dismissed], timeout: 5), .completed)
    }
    @MainActor func testKeyboardSwitchCancelsLocalVoice() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test", "--voice-fixture"]; app.launch()
        let orb = app.buttons["voice.orb"]
        XCTAssertTrue(orb.waitForExistence(timeout: 10)); orb.tap()
        XCTAssertTrue(app.staticTexts["Listening"].waitForExistence(timeout: 5))
        app.buttons["composer.keyboard"].tap()
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 5))
        XCTAssertFalse(orb.exists)
        XCTAssertFalse(app.staticTexts["Listening"].exists)
        XCTAssertFalse(app.buttons["Share answer"].waitForExistence(timeout: 5))
    }
    @MainActor func testSuggestionSwitchCancelsLocalVoice() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test", "--voice-fixture"]; app.launch()
        let orb = app.buttons["voice.orb"]
        XCTAssertTrue(orb.waitForExistence(timeout: 10)); orb.tap()
        XCTAssertTrue(app.staticTexts["Listening"].waitForExistence(timeout: 5))
        app.buttons["Find a little focus"].firstMatch.tap()
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 5))
        XCTAssertFalse(orb.exists)
        XCTAssertEqual(app.textFields["composer.input"].value as? String, "Help me make room for focused work this week.")
        XCTAssertFalse(app.buttons["Share answer"].waitForExistence(timeout: 5))
    }
    @MainActor func testTapSilenceCancelAndAutomaticVoiceSend() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test", "--voice-fixture"]; app.launch()
        let orb = app.buttons["voice.orb"]
        XCTAssertTrue(orb.waitForExistence(timeout: 10))
        let input = app.textFields["composer.input"]
        app.buttons["composer.keyboard"].tap(); input.typeText("Keep my keyboard draft")
        app.staticTexts["What’s on\nyour mind?"].tap()
        orb.tap()
        let countdown = app.buttons.matching(NSPredicate(format: "identifier == 'voice.orb' AND label BEGINSWITH 'Sending in '")).firstMatch
        XCTAssertTrue(countdown.waitForExistence(timeout: 6))
        XCTAssertTrue(app.staticTexts["Listening"].exists)
        XCTAssertFalse(app.buttons["Cancel voice message"].exists)
        XCTAssertFalse(app.buttons["Cancel"].exists)
        // Touch DOWN cancels even when it lifts after the previous silence deadline.
        orb.press(forDuration: 3.2)
        XCTAssertFalse(app.staticTexts["Listening"].exists)
        XCTAssertFalse(app.buttons["Share answer"].waitForExistence(timeout: 4))
        orb.tap()
        XCTAssertTrue(countdown.waitForExistence(timeout: 6))
        capture(app, "Voice listening")
        XCTAssertTrue(app.staticTexts["Help me make room for focused work this week"].firstMatch.waitForExistence(timeout: 12))
        XCTAssertTrue(app.buttons["Share answer"].firstMatch.waitForExistence(timeout: 30))
        XCTAssertTrue(orb.exists)
        // A partial answer appears before the gateway run completes; editing requires ready.
        let keyboard = app.buttons["composer.keyboard"]
        let ready = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true AND hittable == true"), object: keyboard)
        XCTAssertEqual(XCTWaiter.wait(for: [ready], timeout: 15), .completed)
        keyboard.tap()
        XCTAssertTrue(input.waitForExistence(timeout: 5))
        XCTAssertEqual(input.value as? String, "Keep my keyboard draft")
    }
    @MainActor private func capture(_ app: XCUIApplication, _ name: String) {
        Thread.sleep(forTimeInterval: 0.7) // Capture settled native navigation, not an intermediate animation frame.
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
    }
}
