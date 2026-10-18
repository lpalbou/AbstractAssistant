import XCTest

final class PhoneUITests: XCTestCase {
    @MainActor func testConversationAndNavigation() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--demo", "--ui-test"]
        app.launch()
        XCTAssertTrue(app.staticTexts["What’s on your mind?"].waitForExistence(timeout: 10))
        capture(app, "Assistant")
        app.buttons["Find a little focus"].firstMatch.tap()
        app.buttons["Send message"].tap()
        XCTAssertTrue(app.buttons["Share answer"].firstMatch.waitForExistence(timeout: 30))
        let finished = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: app.buttons["Stop"].firstMatch)
        XCTAssertEqual(XCTWaiter.wait(for: [finished], timeout: 30), .completed)
        XCTAssertTrue(app.buttons["voice.orb"].exists)
        XCTAssertTrue(app.buttons["View conversation files (1)"].exists)
        XCTAssertTrue(app.buttons["More options"].isHittable)
        XCTAssertTrue(app.buttons["voice.orb"].isHittable)
        capture(app, "Conversation")
        app.tabBars.buttons["Inbox"].tap()
        XCTAssertTrue(app.staticTexts["RECENT ACTIVITY"].exists)
        capture(app, "Inbox")
        app.tabBars.buttons["Automations"].tap()
        XCTAssertTrue(app.staticTexts["Morning digest"].exists)
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
        XCTAssertTrue(app.staticTexts["RECENT ACTIVITY"].waitForExistence(timeout: 10))
    }
    @MainActor func testVoiceSettingsAndWorkflowAreAvailable() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test"]; app.launch()
        openSettings(app)
        app.buttons["Voice & reading"].tap()
        XCTAssertTrue(app.switches["voice.readAloud"].waitForExistence(timeout: 10))
        // iOS exposes the whole labelled row as a switch; tap the actual trailing control.
        app.switches["voice.readAloud"].coordinate(withNormalizedOffset: CGVector(dx: 0.88, dy: 0.5)).tap()
        let enabled = XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == '1'"), object: app.switches["voice.readAloud"])
        XCTAssertEqual(XCTWaiter.wait(for: [enabled], timeout: 5), .completed)
        XCTAssertTrue(app.buttons["voice.choices"].waitForExistence(timeout: 10))
        XCTAssertFalse(app.buttons["Preview voice"].exists)
        capture(app, "Voice settings")
        app.buttons["voice.choices"].tap()
        let choice = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Supertonic · M1'")).firstMatch
        XCTAssertTrue(choice.waitForExistence(timeout: 5)); choice.tap()
        XCTAssertTrue(app.buttons["Stop sample"].waitForExistence(timeout: 5))
        capture(app, "Voice choices")
        app.navigationBars.buttons.firstMatch.tap()
        app.buttons["1.5×"].tap()
        XCTAssertTrue(app.buttons["Stop sample"].waitForExistence(timeout: 5))
        capture(app, "Speaking speed")
        app.buttons["Stop sample"].tap()
        app.buttons["voice.transcription"].tap()
        XCTAssertTrue(app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'large-v3-turbo'")).firstMatch.waitForExistence(timeout: 5))
        capture(app, "Speech recognition")
        app.navigationBars.buttons.firstMatch.tap()
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
        XCTAssertTrue(app.buttons["More options"].waitForExistence(timeout: 10)); app.buttons["More options"].tap(); app.buttons["Conversation files"].tap()
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
        app.staticTexts["What’s on your mind?"].tap()
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
        app.staticTexts["What’s on your mind?"].tap()
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
    @MainActor func testEmptyAutomationHasOnePaddedCreateAction() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test", "--empty-automations", "--screen", "automations"]; app.launch()
        XCTAssertTrue(app.staticTexts["No automations yet"].waitForExistence(timeout: 10))
        let create = app.buttons["automations.create"]
        XCTAssertEqual(app.buttons.matching(NSPredicate(format: "label == 'New automation'")).count, 1)
        XCTAssertGreaterThanOrEqual(create.frame.height, 50)
        XCTAssertGreaterThan(create.frame.minX, 20)
        XCTAssertLessThan(create.frame.maxX, app.frame.width - 20)
        capture(app, "Empty automations")
        create.tap(); XCTAssertTrue(app.textFields["automation.task"].waitForExistence(timeout: 5))
    }
    @MainActor func testEntitiesCanBeListedSelectedAndCreated() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test"]; app.launch()
        let chooser = app.buttons["Choose who answers"]
        XCTAssertTrue(chooser.waitForExistence(timeout: 10)); chooser.tap()
        XCTAssertTrue(app.buttons["Talk with Castor"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.buttons["Talk with Assistant"].exists)
        capture(app, "Entities")
        app.buttons["Talk with Castor"].tap()
        XCTAssertEqual(chooser.value as? String, "Castor")
        capture(app, "Entity conversation")
        chooser.tap(); app.buttons["entities.new"].tap()
        let name = app.textFields["entity.name"]
        XCTAssertTrue(name.waitForExistence(timeout: 5)); name.tap(); name.typeText("Atlas One")
        let create = app.buttons["entity.create"]
        let ready = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true AND hittable == true"), object: create)
        XCTAssertEqual(XCTWaiter.wait(for: [ready], timeout: 10), .completed)
        capture(app, "New entity")
        create.tap()
        let opened = XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == 'Atlas One'"), object: chooser)
        XCTAssertEqual(XCTWaiter.wait(for: [opened], timeout: 15), .completed)
        chooser.tap(); XCTAssertTrue(app.buttons["Talk with Atlas One"].waitForExistence(timeout: 5))
        capture(app, "Created entity")
    }
    @MainActor func testToolsSaveOnlyForTheCurrentConversation() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test"]; app.launch()
        openTools(app)
        let defaults = app.switches["tools.defaults"]
        XCTAssertTrue(defaults.waitForExistence(timeout: 10)); XCTAssertEqual(defaults.value as? String, "1")
        capture(app, "Inherited conversation tools")
        defaults.coordinate(withNormalizedOffset: CGVector(dx: 0.88, dy: 0.5)).tap()
        let read = app.segmentedControls["tool.read_file"]
        XCTAssertTrue(read.waitForExistence(timeout: 5))
        read.buttons["Off"].tap()
        app.segmentedControls["tool.fetch_url"].buttons["Auto"].tap()
        app.segmentedControls["tool.execute_command"].buttons["Approve"].tap()
        capture(app, "Conversation tools")
        app.buttons["Save"].tap()
        openTools(app)
        XCTAssertEqual(defaults.value as? String, "0")
        XCTAssertTrue(read.buttons["Off"].isSelected)
        XCTAssertTrue(app.segmentedControls["tool.fetch_url"].buttons["Auto"].isSelected)
        XCTAssertTrue(app.segmentedControls["tool.execute_command"].buttons["Approve"].isSelected)
        defaults.coordinate(withNormalizedOffset: CGVector(dx: 0.88, dy: 0.5)).tap()
        XCTAssertTrue(read.buttons["Auto"].isSelected)
        defaults.coordinate(withNormalizedOffset: CGVector(dx: 0.88, dy: 0.5)).tap()
        XCTAssertTrue(read.buttons["Off"].isSelected)
        app.buttons["Close"].tap()
        app.buttons["More options"].tap(); app.buttons["New conversation"].tap()
        openTools(app)
        XCTAssertTrue(defaults.waitForExistence(timeout: 5)); XCTAssertEqual(defaults.value as? String, "1")
        defaults.coordinate(withNormalizedOffset: CGVector(dx: 0.88, dy: 0.5)).tap()
        XCTAssertTrue(read.buttons["Auto"].isSelected)
    }
    @MainActor func testAnswerStatisticsAreOptionalAndCanBeHiddenAgain() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test"]; app.launch()
        openSettings(app)
        let toggle = app.switches["settings.messageStats"]
        XCTAssertTrue(toggle.waitForExistence(timeout: 5))
        if toggle.value as? String == "1" { toggle.coordinate(withNormalizedOffset: CGVector(dx: 0.88, dy: 0.5)).tap() }
        app.buttons["Done"].tap()
        app.buttons["Find a little focus"].firstMatch.tap(); app.buttons["Send message"].tap()
        XCTAssertTrue(app.buttons["Share answer"].firstMatch.waitForExistence(timeout: 30))
        let keyboard = app.buttons["composer.keyboard"]
        let ready = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true AND hittable == true"), object: keyboard)
        XCTAssertEqual(XCTWaiter.wait(for: [ready], timeout: 30), .completed)
        let stats = app.descendants(matching: .any).matching(identifier: "message.stats").firstMatch
        XCTAssertFalse(stats.exists)
        openSettings(app)
        toggle.coordinate(withNormalizedOffset: CGVector(dx: 0.88, dy: 0.5)).tap()
        XCTAssertEqual(toggle.value as? String, "1")
        app.buttons["Done"].tap()
        XCTAssertTrue(stats.waitForExistence(timeout: 10))
        XCTAssertTrue(stats.label.contains("Input:")); XCTAssertTrue(stats.label.contains("Output:"))
        XCTAssertTrue(stats.label.contains("tool calls"))
        capture(app, "Answer statistics")
        openSettings(app); toggle.coordinate(withNormalizedOffset: CGVector(dx: 0.88, dy: 0.5)).tap(); app.buttons["Done"].tap()
        let hidden = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: stats)
        XCTAssertEqual(XCTWaiter.wait(for: [hidden], timeout: 5), .completed)
    }
    @MainActor func testGrowingAutomationBudgetValidatesAndInheritsByDefault() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test", "--screen", "automations"]; app.launch()
        XCTAssertTrue(app.buttons["New automation"].waitForExistence(timeout: 10)); app.buttons["New automation"].tap()
        let task = app.textFields["automation.task"]
        XCTAssertTrue(task.waitForExistence(timeout: 10)); task.tap(); task.typeText("My inherited history briefing")
        app.buttons["Done"].firstMatch.tap()
        let growing = app.switches["automation.growing"]
        let budget = app.textFields["automation.historyBudget"]
        XCTAssertFalse(budget.exists)
        growing.coordinate(withNormalizedOffset: CGVector(dx: 0.88, dy: 0.5)).tap()
        XCTAssertTrue(budget.waitForExistence(timeout: 5))
        XCTAssertTrue((budget.value as? String ?? "").contains("50,000"))
        budget.tap(); budget.typeText("0"); app.buttons["Done"].firstMatch.tap()
        let create = app.buttons["automation.create"]
        XCTAssertFalse(create.isEnabled)
        budget.tap(); budget.typeText(XCUIKeyboardKey.delete.rawValue + "24000"); app.buttons["Done"].firstMatch.tap()
        XCTAssertTrue(create.isEnabled)
        capture(app, "Custom history budget")
        growing.coordinate(withNormalizedOffset: CGVector(dx: 0.88, dy: 0.5)).tap()
        XCTAssertFalse(budget.exists)
        growing.coordinate(withNormalizedOffset: CGVector(dx: 0.88, dy: 0.5)).tap()
        XCTAssertEqual(budget.value as? String, "24000")
        budget.tap(); budget.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: 5)); app.buttons["Done"].firstMatch.tap()
        XCTAssertTrue((budget.value as? String ?? "").contains("50,000"))
        XCTAssertTrue(create.isEnabled)
        capture(app, "Inherited history budget")
        for _ in 0..<4 { if create.isHittable { break }; app.swipeUp() }
        XCTAssertTrue(create.isHittable); create.tap()
        XCTAssertTrue(app.staticTexts["My inherited history briefing"].firstMatch.waitForExistence(timeout: 20))
    }
    @MainActor func testOnlyTheSpeakingAnswerShowsStop() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test"]; app.launch()
        for index in 1...2 {
            let keyboard = app.buttons["composer.keyboard"]
            XCTAssertTrue(keyboard.waitForExistence(timeout: 10))
            let ready = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true AND hittable == true"), object: keyboard)
            XCTAssertEqual(XCTWaiter.wait(for: [ready], timeout: 30), .completed)
            keyboard.tap(); app.textFields["composer.input"].typeText("Answer \(index)"); app.buttons["Send message"].tap()
            let done = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true"), object: keyboard)
            XCTAssertEqual(XCTWaiter.wait(for: [done], timeout: 30), .completed)
        }
        let readers = app.buttons.matching(identifier: "Read answer aloud")
        XCTAssertEqual(readers.count, 2)
        readers.element(boundBy: 1).tap()
        XCTAssertTrue(app.buttons["Stop reading"].firstMatch.waitForExistence(timeout: 5))
        XCTAssertEqual(app.buttons.matching(identifier: "Stop reading").count, 1)
        XCTAssertEqual(app.buttons.matching(identifier: "Read answer aloud").count, 1)
        capture(app, "Isolated answer playback")
        app.buttons["Stop reading"].tap()
        XCTAssertEqual(app.buttons.matching(identifier: "Read answer aloud").count, 2)
    }
    @MainActor func testSettingsAlsoOpensToolsForTheCurrentConversation() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test"]; app.launch()
        openSettings(app)
        app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Conversation tools'")).firstMatch.tap()
        XCTAssertTrue(app.switches["tools.defaults"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["Assistant · This conversation"].exists)
        app.buttons["Close"].tap()
        XCTAssertTrue(app.switches["settings.messageStats"].waitForExistence(timeout: 5))
    }
    @MainActor private func openTools(_ app: XCUIApplication) {
        XCTAssertTrue(app.buttons["More options"].waitForExistence(timeout: 10)); app.buttons["More options"].tap()
        app.buttons["Tools"].tap()
    }
    @MainActor private func openSettings(_ app: XCUIApplication) {
        XCTAssertTrue(app.buttons["More options"].waitForExistence(timeout: 10)); app.buttons["More options"].tap()
        app.buttons["Settings"].tap()
    }
    @MainActor private func capture(_ app: XCUIApplication, _ name: String) {
        Thread.sleep(forTimeInterval: 0.7) // Capture settled native navigation, not an intermediate animation frame.
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
    }
}
