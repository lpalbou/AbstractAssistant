import XCTest

/// While the orb listens, Send (where the tools icon sits at rest) ends the listening at once: in
/// the simulator's silence it says "I didn't hear anything" right away rather than after the 5 s
/// it waits for speech. Sample data.
final class SendNowUITests: XCTestCase {
    func testSendEndsTheListeningNow() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--fresh-conversation", "--screen", "ask", "--test-listen"]
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

/// Home's orb starts a new conversation every time; an earlier one continues from Sessions.
final class HomeOrbNewConversationUITests: XCTestCase {
    func testTheHomeOrbOpensAnEmptyConversation() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt"]
        app.launch()
        XCTAssertTrue(app.buttons["Settings"].waitForExistence(timeout: 15))
        // Continue a conversation with messages, then back Home.
        app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Sessions'")).firstMatch.tap()
        XCTAssertTrue(app.buttons["New conversation"].waitForExistence(timeout: 10))
        let row = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", "QC")).firstMatch
        app.bring(row)
        row.tap()
        XCTAssertTrue(app.buttons["voice.button"].waitForExistence(timeout: 20))
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "assay QC")).firstMatch.waitForExistence(timeout: 10))
        app.buttons["Back"].firstMatch.tap(); sleep(1)
        app.buttons["Back"].firstMatch.tap(); sleep(1)
        XCTAssertTrue(app.buttons["Settings"].waitForExistence(timeout: 5))
        // Home's orb: an empty conversation, not the one just left.
        app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Talk to'")).firstMatch.tap()
        XCTAssertTrue(app.staticTexts["ask.status"].waitForExistence(timeout: 10))
        sleep(2)
        XCTAssertFalse(app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "assay QC")).firstMatch.exists, "Home's orb reopened the earlier conversation")
        XCTAssertFalse(app.buttons["voice.button"].exists, "an answer to read: not a new conversation")
    }
}
