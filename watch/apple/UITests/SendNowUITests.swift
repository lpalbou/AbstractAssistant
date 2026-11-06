import XCTest

/// One persistent root owns the orb and conversation; browsing changes only its lower section.
final class DirectHomeConversationUITests: XCTestCase {
    private func launch(_ extra: [String] = []) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--silent-mic", "--orb-design", "A", "--test-home-identity", "-ask.conversation", "NO"] + extra
        app.launch()
        XCTAssertTrue(app.buttons["home.orb"].waitForExistence(timeout: 15), app.debugDescription)
        return app
    }

    private func capture(_ name: String) {
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
    }

    func testOneTapListensInPlaceAndBrowsingKeepsTheSameRoot() {
        let app = launch()
        XCTAssertTrue(app.buttons["Type or dictate"].exists)
        XCTAssertTrue(app.buttons["ask.tools"].exists)
        XCTAssertTrue(app.buttons["Settings"].exists)
        XCTAssertFalse(app.buttons["Back"].exists)
        let identity = app.staticTexts["debug.home"].label
        let keyboard = app.buttons["Type or dictate"].frame
        capture("home-ready")
        app.buttons["home.orb"].tap()
        let listening = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH 'Listening'")).firstMatch
        XCTAssertTrue(listening.waitForExistence(timeout: 5), app.debugDescription)
        capture("home-first-tap-listening")
        XCTAssertFalse(app.buttons["Back"].exists)
        XCTAssertTrue(app.buttons["Settings"].exists)
        XCTAssertEqual(app.staticTexts["debug.home"].label, identity)
        XCTAssertFalse(app.buttons["home.sessions"].exists)
        app.buttons["ask.stop"].tap()
        XCTAssertTrue(app.buttons["Type or dictate"].waitForExistence(timeout: 5))
        XCTAssertEqual(app.buttons["Type or dictate"].frame.minY, keyboard.minY, accuracy: 1)
        let browse = app.buttons["home.browse"]
        app.bring(browse)
        XCTAssertEqual(browse.label, "Discuss something else")
        browse.tap()
        XCTAssertTrue(app.buttons["home.sessions"].waitForExistence(timeout: 5))
        let fresh = app.staticTexts["debug.home"].label.components(separatedBy: "|")
        XCTAssertEqual(fresh.first, identity.components(separatedBy: "|").first)
        XCTAssertNotEqual(fresh[1], identity.components(separatedBy: "|")[1])
        XCTAssertFalse(app.buttons["home.new"].exists)
        XCTAssertFalse(app.buttons["home.conversation"].exists)
        capture("home-browser-in-place")
    }

    func testHomeToolsSurviveSettingsAndTheFirstVoiceTurn() {
        let app = launch()
        func element(_ id: String) -> XCUIElement { app.descendants(matching: .any)[id].firstMatch }
        app.buttons["ask.tools"].tap()
        let files = element("tools.group.files")
        app.bring(files); files.tap()
        let off = element("tools.all.files.off")
        XCTAssertTrue(off.waitForExistence(timeout: 5)); off.tap()
        app.buttons["Back"].firstMatch.tap()
        app.buttons["Back"].firstMatch.tap()
        XCTAssertEqual(app.buttons["ask.tools"].label, "Tools, changed for this conversation")
        app.buttons["Settings"].tap()
        app.buttons["Back"].firstMatch.tap()
        XCTAssertTrue(app.buttons["home.orb"].waitForExistence(timeout: 5))
        XCTAssertEqual(app.buttons["ask.tools"].label, "Tools, changed for this conversation")
        app.buttons["home.orb"].tap()
        XCTAssertTrue(app.buttons["ask.stop"].waitForExistence(timeout: 5))
        app.buttons["ask.stop"].tap()
        XCTAssertTrue(app.buttons["ask.tools"].waitForExistence(timeout: 5))
        XCTAssertEqual(app.buttons["ask.tools"].label, "Tools, changed for this conversation")
        let browse = app.buttons["home.browse"]
        app.bring(browse)
        XCTAssertEqual(browse.label, "Discuss something else")
        browse.tap()
        XCTAssertTrue(app.buttons["ask.tools"].waitForExistence(timeout: 5))
        XCTAssertEqual(app.buttons["ask.tools"].label, "Tools", "New conversation must use the defaults")
    }

    func testTypingOnHomeSendsWithoutAnotherComposer() {
        let app = launch(["-ask.speak", "NO"])
        let identity = app.staticTexts["debug.home"].label
        app.buttons["Type or dictate"].tap()
        XCTAssertTrue(app.textViews.firstMatch.waitForExistence(timeout: 5), app.debugDescription)
        app.typeText("Hello from Home")
        app.buttons["Done"].firstMatch.tap()
        XCTAssertTrue(app.staticTexts["ask.status"].waitForExistence(timeout: 10), app.debugDescription)
        XCTAssertFalse(app.buttons["home.sessions"].exists)
        let prompt = app.staticTexts.matching(NSPredicate(format: "label CONTAINS 'Hello from Home'")).firstMatch
        XCTAssertTrue(prompt.waitForExistence(timeout: 15), app.debugDescription)
        XCTAssertEqual(app.staticTexts["debug.home"].label, identity)
        // Detail pages may restart SwiftUI tasks; they must not reset the root conversation.
        let tools = app.buttons["ask.tools"]
        XCTAssertTrue(tools.waitForExistence(timeout: 40), app.debugDescription)
        app.bring(tools)
        XCTAssertTrue(tools.isHittable, app.debugDescription)
        tools.tap()
        XCTAssertTrue(app.buttons["Back"].firstMatch.waitForExistence(timeout: 5), app.debugDescription)
        app.buttons["Back"].firstMatch.tap()
        XCTAssertEqual(app.staticTexts["debug.home"].label, identity)
        XCTAssertTrue(prompt.exists, "Tools cleared the current turn")
        app.buttons["Settings"].tap(); app.buttons["Back"].firstMatch.tap()
        XCTAssertEqual(app.staticTexts["debug.home"].label, identity)
        XCTAssertTrue(prompt.exists, "Settings cleared the current turn")
        capture("home-typed-conversation")
    }

    func testLoadedSessionKeepsTheStageAndShowsItsConversation() {
        // The general mock has a pending question on its completed QC run.
        // Use the existing completed-history fixture for this resume scenario.
        let app = launch(["--test-public-history"])
        let rootID = app.staticTexts["debug.home"].label.components(separatedBy: "|").first
        let keyboardY = app.buttons["Type or dictate"].frame.minY
        let sessions = app.buttons["home.sessions"]
        app.bring(sessions); sessions.tap()
        let row = app.buttons.matching(NSPredicate(format: "label CONTAINS 'QC'")).firstMatch
        app.bring(row)
        XCTAssertTrue(row.waitForExistence(timeout: 10), app.debugDescription); row.tap()
        XCTAssertTrue(app.buttons["voice.button"].waitForExistence(timeout: 20), app.debugDescription)
        XCTAssertEqual(app.buttons["Type or dictate"].frame.minY, keyboardY, accuracy: 1)
        XCTAssertFalse(app.buttons["home.sessions"].exists)
        XCTAssertFalse(app.buttons["Back"].exists)
        let identity = app.staticTexts["debug.home"].label
        XCTAssertEqual(identity.components(separatedBy: "|").first, rootID)
        XCTAssertTrue(identity.hasSuffix("|0"))
        capture("loaded-conversation-stage")
        app.nudgeUp(); app.nudgeUp()
        capture("loaded-conversation-history")
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS[c] 'assay QC'")).firstMatch.exists)
        let browse = app.buttons["home.browse"]
        app.bring(browse)
        XCTAssertEqual(browse.label, "Discuss something else")
        browse.tap()
        capture("session-browser")
        XCTAssertFalse(app.buttons["home.conversation"].exists)
        XCTAssertFalse(app.buttons["home.new"].exists)
        app.bring(sessions); sessions.tap()
        app.bring(row); row.tap()
        XCTAssertTrue(app.buttons["voice.button"].waitForExistence(timeout: 20))
        XCTAssertEqual(app.staticTexts["debug.home"].label, identity)
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS[c] 'assay QC'")).firstMatch.exists)
    }

    func testHomeBrowsesSessionsAndAutomationsBelowTheStage() {
        let app = launch()
        let sessions = app.buttons["home.sessions"]
        app.bring(sessions)
        XCTAssertTrue(sessions.isHittable)
        capture("home-browse")
        sessions.tap()
        XCTAssertTrue(app.buttons["New conversation"].waitForExistence(timeout: 10))
        app.buttons["Back"].firstMatch.tap()
        XCTAssertTrue(app.buttons["home.orb"].waitForExistence(timeout: 5))
        let automations = app.buttons["home.automations"]
        app.bring(automations)
        XCTAssertTrue(automations.isHittable)
        automations.tap()
        XCTAssertTrue(app.staticTexts.matching(identifier: "screen.title").matching(NSPredicate(format: "label == 'Automations'")).firstMatch.waitForExistence(timeout: 10))
    }
}

/// While the orb listens, Send (where the tools icon sits at rest) ends the listening at once: in
/// the simulator's silence it says "I didn't hear anything" right away rather than after the 5 s
/// it waits for speech. Sample data.
final class SendNowUITests: XCTestCase {
    func testSendEndsTheListeningNow() throws {
        let app = XCUIApplication()
        // `--silent-mic`: the room's noise through the Mac's microphone is never taken for speech.
        app.launchArguments = ["--mock", "--no-notification-prompt", "--fresh-conversation", "--screen", "ask", "--test-listen", "--silent-mic"]
        app.launch()
        let listening = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "Listening")).firstMatch
        XCTAssertTrue(listening.waitForExistence(timeout: 20), app.debugDescription)
        let send = app.buttons["ask.send"]
        XCTAssertTrue(send.waitForExistence(timeout: 3), "no Send while listening:\n\(app.debugDescription)")
        XCTAssertFalse(app.buttons["ask.tools"].exists, "the tools icon shows while it listens")
        send.tap()
        let note = app.staticTexts.matching(NSPredicate(format: "label CONTAINS[c] %@ OR label CONTAINS[c] %@", "hear anything", "catch that")).firstMatch
        XCTAssertTrue(note.waitForExistence(timeout: 5), "Send did not end the listening at once:\n\(app.debugDescription)")
        XCTAssertFalse(send.exists, "Send stays after the listening ended")
    }
}

/// Discuss something else returns to a fresh home draft in the same root view.
final class HomeOrbNewConversationUITests: XCTestCase {
    func testNewConversationClearsThePreviousSessionInPlace() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--silent-mic", "--no-notification-prompt", "--test-public-history", "--test-home-identity", "-ask.conversation", "NO"]
        app.launch()
        XCTAssertTrue(app.buttons["Settings"].waitForExistence(timeout: 15))
        // Continue a conversation with messages, then back Home.
        let sessions = app.buttons["home.sessions"]
        app.bring(sessions); sessions.tap()
        XCTAssertTrue(app.buttons["New conversation"].waitForExistence(timeout: 10))
        let row = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", "QC")).firstMatch
        app.bring(row)
        row.tap()
        XCTAssertTrue(app.buttons["voice.button"].waitForExistence(timeout: 20))
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "assay QC")).firstMatch.waitForExistence(timeout: 10))
        let previous = app.staticTexts["debug.home"].label.components(separatedBy: "|")
        let browse = app.buttons["home.browse"]
        app.bring(browse)
        XCTAssertEqual(browse.label, "Discuss something else")
        browse.tap()
        XCTAssertFalse(app.buttons["home.new"].exists)
        XCTAssertFalse(app.buttons["home.conversation"].exists)
        XCTAssertTrue(app.buttons["home.sessions"].exists)
        let current = app.staticTexts["debug.home"].label.components(separatedBy: "|")
        XCTAssertEqual(previous.first, current.first, "New must keep the same root view")
        XCTAssertNotEqual(previous[1], current[1], "New must use a new session")
        XCTAssertEqual(current.last, "0")
        XCTAssertTrue(app.staticTexts["ask.status"].waitForExistence(timeout: 10))
        sleep(2)
        XCTAssertFalse(app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "assay QC")).firstMatch.exists, "Home's orb reopened the earlier conversation")
        XCTAssertFalse(app.buttons["voice.button"].exists, "an answer to read: not a new conversation")
        let orb = app.buttons["home.orb"]
        app.bring(orb); orb.tap()
        XCTAssertTrue(app.buttons["ask.stop"].waitForExistence(timeout: 5))
        XCTAssertEqual(app.staticTexts["debug.home"].label.components(separatedBy: "|")[1], current[1])
    }
}

/// A question whose sending fails keeps its recording: one line under the orb with Retry and
/// Discard, still offered after a relaunch; Retry sends the same recording (the answer comes and the
/// recording is gone), Discard deletes it. `--test-fail-send` opens the orb on a question just
/// recorded (sample audio) and makes every send fail while the app runs. Sample data.
final class KeptQuestionUITests: XCTestCase {
    func testAFailedQuestionShowsItsConnectionFailureAndKeepsRetry() throws {
        let app = launch(failing: true)
        XCTAssertTrue(app.buttons["ask.retry"].waitForExistence(timeout: 20), app.debugDescription)
        XCTAssertTrue(app.buttons["ask.discard"].exists)
        XCTAssertEqual(app.staticTexts["ask.status"].label, "No connection.")
    }

    private func shot(_ name: String) {
        guard let dir = ProcessInfo.processInfo.environment["SHOTS_DIR"] else { return }
        try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent(name + ".png"))
    }

    private func launch(failing: Bool, session: String = "watch-test-kept-a", screen: String = "ask") -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--fresh-conversation", "--test-session-id", session, "--screen", screen]
            + (failing ? ["--test-fail-send"] : [])
        app.launch()
        return app
    }

    /// The failure state: the line and both actions, under the orb.
    private func assertKept(_ app: XCUIApplication, _ why: String, status: String = "Not sent.") {
        XCTAssertTrue(app.buttons["ask.retry"].waitForExistence(timeout: 20), "\(why): no Retry\n\(app.debugDescription)")
        XCTAssertTrue(app.buttons["ask.discard"].exists, "\(why): no Discard")
        XCTAssertEqual(app.staticTexts["ask.status"].label, status, why)
    }

    func testAFailedQuestionIsKeptAcrossARelaunchAndRetrySendsIt() throws {
        var app = launch(failing: true)
        assertKept(app, "a failed send", status: "No connection.")
        shot("kept-1-failed")
        // Retry while sending still fails: the recording stays.
        app.buttons["ask.retry"].tap()
        XCTAssertTrue(app.buttons["ask.retry"].waitForNonExistence(timeout: 3), "Retry did not send")
        assertKept(app, "a failed retry", status: "No connection.")
        app.terminate()

        // Relaunched, sending works again: still offered, and Retry sends it.
        app = launch(failing: false)
        assertKept(app, "after a relaunch")
        shot("kept-2-relaunched")
        app.buttons["ask.retry"].tap()
        XCTAssertTrue(app.buttons["voice.button"].waitForExistence(timeout: 40), "Retry after a relaunch brought no answer:\n\(app.debugDescription)")
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "overall survival")).firstMatch.exists,
                      "the answer is not to the kept question")
        XCTAssertFalse(app.buttons["ask.retry"].exists, "Retry stays after the question was sent")
        shot("kept-3-sent")
        app.terminate()

        // Sent: the recording is gone for good.
        app = launch(failing: false)
        XCTAssertTrue(app.staticTexts["ask.status"].waitForExistence(timeout: 20))
        sleep(2)
        XCTAssertFalse(app.buttons["ask.retry"].exists, "a sent question is still offered after a relaunch")
    }

    func testKeptRecordingStaysWithItsConversationAfterSwitchingAndRelaunching() throws {
        var app = launch(failing: true, session: "watch-test-kept-owner")
        assertKept(app, "the originating conversation", status: "No connection.")
        app.terminate()

        app = launch(failing: false, session: "watch-test-kept-other")
        XCTAssertTrue(app.staticTexts["ask.status"].waitForExistence(timeout: 20))
        sleep(2)
        XCTAssertFalse(app.buttons["ask.retry"].exists, "another conversation offers the original recording")
        XCTAssertFalse(app.buttons["ask.discard"].exists, "another conversation can discard the original recording")
        XCTAssertNotEqual(app.staticTexts["ask.status"].label, "Not sent.")
        app.terminate()

        app = launch(failing: false, session: "watch-test-kept-owner")
        assertKept(app, "returning to the originating conversation")
        app.buttons["ask.retry"].tap()
        XCTAssertTrue(app.buttons["voice.button"].waitForExistence(timeout: 40), app.debugDescription)
        XCTAssertFalse(app.buttons["ask.retry"].exists, "the successfully retried recording remains")
    }

    func testKeptRecordingIsNotOfferedToAnotherResponder() throws {
        var app = launch(failing: true, session: "watch-test-kept-responder")
        assertKept(app, "the Assistant's failed question", status: "No connection.")
        app.terminate()
        app = launch(failing: false, session: "watch-test-kept-responder", screen: "ask-entity")
        XCTAssertTrue(app.staticTexts["ask.status"].waitForExistence(timeout: 20))
        sleep(2)
        XCTAssertFalse(app.buttons["ask.retry"].exists, "the entity offers the Assistant's recording")
        XCTAssertFalse(app.buttons["ask.discard"].exists, "the entity can discard the Assistant's recording")
        app.terminate()
        app = launch(failing: false, session: "watch-test-kept-responder")
        assertKept(app, "returning to the Assistant")
        app.buttons["ask.discard"].tap()
        XCTAssertTrue(app.buttons["ask.retry"].waitForNonExistence(timeout: 3))
    }

    func testDiscardDeletesTheKeptRecording() throws {
        var app = launch(failing: true)
        assertKept(app, "a failed send", status: "No connection.")
        app.buttons["ask.discard"].tap()
        XCTAssertTrue(app.buttons["ask.retry"].waitForNonExistence(timeout: 3), "Discard left Retry")
        XCTAssertFalse(app.buttons["ask.discard"].exists)
        XCTAssertEqual(app.staticTexts["ask.status"].label, "Tap to talk", "Discard did not bring the orb back to rest")
        shot("kept-4-discarded")
        app.terminate()
        app = launch(failing: false)
        XCTAssertTrue(app.staticTexts["ask.status"].waitForExistence(timeout: 20))
        sleep(2)
        XCTAssertFalse(app.buttons["ask.retry"].exists, "a discarded recording came back after a relaunch")
    }
}

/// Leaving an automation must make the home orb a normal, fresh conversation.
final class FreshHomeFromAutomationUITests: XCTestCase {
    func testDiscussSomethingElseLeavesAutomationContext() {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--silent-mic", "--screen", "automation", "--test-home-identity", "-ask.conversation", "NO", "-ask.speak", "NO"]
        app.launch()
        XCTAssertTrue(app.buttons["ask.info"].waitForExistence(timeout: 15))
        let old = app.staticTexts["debug.home"].label.components(separatedBy: "|")
        let link = app.buttons["home.browse"]
        app.bring(link)
        XCTAssertEqual(link.label, "Discuss something else")
        capture("conversation-discuss-something-else")
        link.tap()
        XCTAssertTrue(app.buttons["ask.tools"].waitForExistence(timeout: 10))
        XCTAssertFalse(app.buttons["ask.info"].exists)
        XCTAssertFalse(app.staticTexts["ask.automation"].exists)
        XCTAssertFalse(app.buttons["home.new"].exists)
        XCTAssertFalse(app.buttons["home.conversation"].exists)
        XCTAssertFalse(app.buttons["home.browse"].exists)
        let fresh = app.staticTexts["debug.home"].label.components(separatedBy: "|")
        XCTAssertEqual(old.first, fresh.first)
        XCTAssertNotEqual(old[1], fresh[1])
        capture("fresh-home-orb")
        app.bring(app.buttons["home.sessions"])
        capture("fresh-home-lists")
        app.bring(app.buttons["home.orb"]); app.buttons["home.orb"].tap()
        XCTAssertTrue(app.buttons["ask.stop"].waitForExistence(timeout: 5))
        XCTAssertEqual(app.staticTexts["debug.home"].label.components(separatedBy: "|")[1], fresh[1])
    }
    private func capture(_ name: String) {
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
    }
}
