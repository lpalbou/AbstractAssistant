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
    @MainActor func testOutsideTapMinimizesInputAndOrbStaysVisible() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test"]; app.launch()
        let input = app.textFields["composer.input"]
        let orb = app.buttons["voice.orb"]
        XCTAssertTrue(orb.waitForExistence(timeout: 10))
        let compactWidth = input.frame.width
        XCTAssertLessThan(compactWidth, app.frame.width * 0.3)
        XCTAssertLessThan(abs(input.frame.midY - app.buttons["Add attachment"].frame.midY), 3)
        XCTAssertLessThan(abs(input.frame.midY - orb.frame.midY), 3)
        capture(app, "Compact composer")
        input.tap(); input.typeText("Keep this typed draft")
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 5))
        XCTAssertTrue(orb.isHittable)
        XCTAssertGreaterThan(input.frame.width, compactWidth + 50)
        XCTAssertTrue(app.buttons["Add attachment"].isHittable)
        XCTAssertTrue(app.buttons["Send message"].isHittable)
        XCTAssertFalse(app.buttons["Done"].exists)
        input.tap() // Caret and input taps keep editing active.
        XCTAssertTrue(app.keyboards.firstMatch.exists)
        capture(app, "Keyboard composer")
        app.staticTexts["What’s on\nyour mind?"].tap()
        let dismissed = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: app.keyboards.firstMatch)
        XCTAssertEqual(XCTWaiter.wait(for: [dismissed], timeout: 5), .completed)
        XCTAssertTrue(orb.isHittable)
        XCTAssertLessThan(input.frame.width, compactWidth + 5)
        XCTAssertEqual(input.value as? String, "Keep this typed draft")
        capture(app, "Minimized draft")
    }
    @MainActor func testOutsideTapPreservesTheAttachmentButtonAction() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test"]; app.launch()
        XCTAssertTrue(app.buttons["voice.orb"].waitForExistence(timeout: 10))
        app.textFields["composer.input"].tap(); app.textFields["composer.input"].typeText("A draft")
        app.buttons["Add attachment"].tap()
        XCTAssertTrue(app.buttons["Choose a file"].waitForExistence(timeout: 5))
        let dismissed = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: app.keyboards.firstMatch)
        XCTAssertEqual(XCTWaiter.wait(for: [dismissed], timeout: 5), .completed)
    }
    @MainActor func testTapSilenceCancelAndAutomaticVoiceSend() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test", "--voice-fixture"]; app.launch()
        let orb = app.buttons["voice.orb"]
        XCTAssertTrue(orb.waitForExistence(timeout: 10))
        let input = app.textFields["composer.input"]
        input.tap(); input.typeText("Keep my keyboard draft")
        app.staticTexts["What’s on\nyour mind?"].tap()
        orb.tap()
        let countdown = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH 'Sending in '")).firstMatch
        XCTAssertTrue(countdown.waitForExistence(timeout: 6))
        // Touch DOWN cancels even when it lifts after the previous silence deadline.
        orb.press(forDuration: 3.2)
        XCTAssertFalse(app.buttons["Cancel voice message"].exists)
        XCTAssertFalse(app.buttons["Share answer"].waitForExistence(timeout: 4))
        orb.tap()
        XCTAssertTrue(countdown.waitForExistence(timeout: 6))
        capture(app, "Voice countdown")
        XCTAssertTrue(app.staticTexts["Help me make room for focused work this week"].firstMatch.waitForExistence(timeout: 12))
        XCTAssertEqual(input.value as? String, "Keep my keyboard draft")
        XCTAssertTrue(app.buttons["Share answer"].firstMatch.waitForExistence(timeout: 30))
        XCTAssertTrue(orb.exists)
    }
    @MainActor private func capture(_ app: XCUIApplication, _ name: String) {
        Thread.sleep(forTimeInterval: 0.7) // Capture settled native navigation, not an intermediate animation frame.
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
    }
}
