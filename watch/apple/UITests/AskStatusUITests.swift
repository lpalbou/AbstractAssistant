import XCTest

/// The orb's line says nothing about an earlier listening while the orb speaks: on a conversation
/// continued from Sessions, a tap on the orb listens, hears nothing ("I didn't hear anything"), then the voice
/// button reads the answer: the note is gone while it speaks. Sample data (the simulator's
/// microphone hears nothing).
final class AskStatusUITests: XCTestCase {
    func testANoteOnListeningEndsWhenTheOrbSpeaks() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--screen", "sessions"]
        app.launch()
        // A conversation, continued on the orb: its last answer, with the voice button.
        let row = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", "QC")).firstMatch
        XCTAssertTrue(app.buttons["New conversation"].waitForExistence(timeout: 15))
        app.bring(row)
        row.tap()
        let voice = app.buttons["voice.button"].firstMatch
        XCTAssertTrue(voice.waitForExistence(timeout: 20), "the conversation's last answer is not shown:\n\(app.debugDescription)")
        sleep(1)
        // The orb: listen (again if the first tap did not reach it).
        let listening = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "Listening")).firstMatch
        for _ in 0..<3 where !listening.exists {
            app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.45)).tap()
            _ = listening.waitForExistence(timeout: 4)
        }
        XCTAssertTrue(listening.exists, "the orb did not listen:\n\(app.debugDescription)")
        // Silence, or a sound that is no words: either note.
        let note = app.staticTexts.matching(NSPredicate(format: "label CONTAINS[c] %@ OR label CONTAINS[c] %@", "hear anything", "catch that")).firstMatch
        XCTAssertTrue(note.waitForExistence(timeout: 30), "the silent listening did not end with its note:\n\(app.debugDescription)")
        voice.tap()                                                                       // read the answer aloud
        XCTAssertTrue(note.waitForNonExistence(timeout: 8), "the note stays while the orb speaks")
    }
}
