import XCTest

final class NotesUITests: XCTestCase {
    private var chatIdentity = ""
    override func setUp() { continueAfterFailure = false }
    private func launch(_ extra: [String] = []) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--silent-mic", "--test-home-identity"] + extra
        app.launch()
        XCTAssertTrue(app.buttons["home.orb"].waitForExistence(timeout: 15))
        chatIdentity = app.staticTexts["debug.home"].label
        let notes = app.buttons["home.notes"]
        app.bring(notes)
        XCTAssertTrue(notes.waitForExistence(timeout: 10))
        capture("home-three-choices")
        notes.tap()
        XCTAssertTrue(app.textFields["notes.text"].waitForExistence(timeout: 10))
        return app
    }
    private func write(_ text: String, in app: XCUIApplication) {
        app.textFields["notes.text"].tap()
        app.typeText(text)
        if app.buttons["Done"].firstMatch.exists { app.buttons["Done"].firstMatch.tap() }
    }
    private func capture(_ name: String) {
        let image = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        image.name = name; image.lifetime = .keepAlways; add(image)
    }
    func testNoteCapturePreservesChatAndDraftAcrossNavigation() {
        let app = launch()
        let chat = chatIdentity
        write("Remember the lighthouse", in: app)
        app.buttons["Back"].firstMatch.tap()
        let notes = app.buttons["home.notes"]
        app.bring(notes); notes.tap()
        XCTAssertEqual(app.textFields["notes.text"].value as? String, "Remember the lighthouse")
        capture("note-ready-to-save")
        app.buttons["notes.save"].tap()
        XCTAssertTrue(app.descendants(matching: .any)["notes.saved"].waitForExistence(timeout: 10))
        capture("note-saved")
        app.buttons["notes.new"].tap()
        XCTAssertFalse(app.buttons["notes.save"].isEnabled)
        app.buttons["Back"].firstMatch.tap()
        XCTAssertEqual(app.staticTexts["debug.home"].label, chat, "A note must not replace the current chat session")
    }
    func testLostCaptureResponseCanRetryTheSameNote() {
        let app = launch(["--note-save-fail-once"])
        write("One note, even after retry", in: app)
        app.buttons["notes.save"].tap()
        XCTAssertTrue(app.staticTexts["notes.error"].waitForExistence(timeout: 10))
        XCTAssertFalse(app.descendants(matching: .any)["notes.saved"].exists)
        app.buttons["notes.save"].tap()
        XCTAssertTrue(app.descendants(matching: .any)["notes.saved"].waitForExistence(timeout: 10))
    }
    func testFailedDraftCanBeDiscardedWithoutPretendingItWasUnsent() {
        let app = launch(["--note-save-fail-once"])
        write("A draft I want to leave", in: app)
        app.buttons["notes.save"].tap()
        XCTAssertTrue(app.buttons["notes.discard"].waitForExistence(timeout: 10))
        app.bring(app.buttons["notes.discard"]); app.buttons["notes.discard"].tap()
        XCTAssertTrue(app.staticTexts["Any note already sent may still be saved in your notebook."].waitForExistence(timeout: 5))
        app.buttons["Discard"].firstMatch.tap()
        XCTAssertTrue(app.textFields["notes.text"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.buttons["notes.save"].isEnabled)
        XCTAssertFalse(app.staticTexts["notes.error"].exists)
    }
    func testDictationCanStopWithoutSavingAnEmptyNote() {
        let app = launch()
        app.buttons["notes.dictate"].tap()
        XCTAssertTrue(app.buttons["notes.voice.done"].waitForExistence(timeout: 5))
        capture("note-listening")
        app.buttons["notes.voice.done"].tap()
        XCTAssertTrue(app.buttons["notes.dictate"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.buttons["notes.save"].isEnabled)
        XCTAssertFalse(app.descendants(matching: .any)["notes.saved"].exists)
    }
}
