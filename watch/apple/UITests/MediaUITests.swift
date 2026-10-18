import XCTest

/// The Assistant's workflow makes images and recordings: choose it (for a conversation from the
/// orb's tools, for new conversations in Settings → Tools), ask for a picture and see it under the
/// answer and full screen, ask for a recording and hear it after the spoken answer. Sample data:
/// the mock's Orchestrator draws for "draw"/"image", records for "voice"/"record".
final class MediaUITests: XCTestCase {
    private var app: XCUIApplication!
    private func shot(_ name: String) {
        guard let dir = ProcessInfo.processInfo.environment["SHOTS_DIR"] else { return }
        try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent(name + ".png"))
    }
    private func element(_ id: String) -> XCUIElement { app.descendants(matching: .any)[id].firstMatch }
    private func reveal(_ e: XCUIElement) {
        for _ in 0..<10 where !(e.exists && e.isHittable) { app.swipeUp(); usleep(300_000) }
    }
    private func launch(_ args: [String]) {
        app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt"] + args
        app.launch()
    }

    override func tearDown() {
        // The next tests start from the gateway's default workflow again.
        launch(["--reset-tools", "--screen", "settings"])
        app.terminate()
    }

    /// The orb's tools page chooses this conversation's workflow; it says which one answers.
    func testAConversationChoosesItsWorkflow() throws {
        launch(["--reset-tools", "--fresh-conversation", "--screen", "ask"])
        let tools = app.buttons["ask.tools"]
        XCTAssertTrue(tools.waitForExistence(timeout: 20), app.debugDescription)
        tools.tap()
        let row = element("tools.workflow")
        XCTAssertTrue(row.waitForExistence(timeout: 10), app.debugDescription)
        XCTAssertTrue(row.label.contains("Basic agent") && row.label.contains("Default"), row.label)
        shot("m1-tools-workflow")
        row.tap()
        let orchestrator = element("workflow.abstractassistant-orchestrator")
        XCTAssertTrue(orchestrator.waitForExistence(timeout: 10), app.debugDescription)
        XCTAssertTrue(app.staticTexts["Also makes images and other media"].exists)
        shot("m2-workflows")
        orchestrator.tap()
        XCTAssertTrue(row.waitForExistence(timeout: 5), "picking returns to the tools page")
        XCTAssertTrue(row.label.contains("AbstractAssistant Orchestrator"), row.label)
        shot("m3-tools-orchestrator")
    }

    func testAPictureAndARecordingFromTheAssistantsWorkflow() throws {
        // New conversations use the Assistant's workflow (Settings → Tools).
        launch(["--reset-tools", "--screen", "settings"])
        let settingsTools = element("settings.tools")
        reveal(settingsTools)
        XCTAssertTrue(settingsTools.waitForExistence(timeout: 10), app.debugDescription)
        settingsTools.tap()
        let row = element("tools.workflow")
        XCTAssertTrue(row.waitForExistence(timeout: 10), app.debugDescription)
        row.tap()
        let orchestrator = element("workflow.abstractassistant-orchestrator")
        XCTAssertTrue(orchestrator.waitForExistence(timeout: 10), app.debugDescription)
        orchestrator.tap()
        XCTAssertTrue(row.waitForExistence(timeout: 5) && row.label.contains("AbstractAssistant Orchestrator"), row.label)

        // A picture: under the answer, then full screen.
        launch(["--screen", "ask", "--test-ask", "Draw an apple on a table"])
        let image = element("media.image")
        XCTAssertTrue(image.waitForExistence(timeout: 30), "no image under the answer:\n\(app.debugDescription)")
        XCTAssertTrue(app.staticTexts["Here is your picture."].exists, app.debugDescription)
        reveal(image)
        sleep(2)                                       // the picture replaces its placeholder
        shot("m4-answer-image")
        image.tap()
        XCTAssertTrue(element("media.full").waitForExistence(timeout: 15), app.debugDescription)
        sleep(1)
        shot("m5-image-full")
        app.buttons["Back"].firstMatch.tap()
        XCTAssertTrue(image.waitForExistence(timeout: 5))

        // A recording: it plays after the spoken answer (the mock's speech lasts 9.3 s, its recording 3 s).
        launch(["--screen", "ask", "--test-ask", "Make a voice recording saying good morning"])
        let audio = element("media.audio")
        XCTAssertTrue(audio.waitForExistence(timeout: 30), "no recording under the answer:\n\(app.debugDescription)")
        reveal(audio)
        shot("m6-answer-recording")
        let position = element("debug.position")
        let deadline = Date().addingTimeInterval(30)
        var reached = 0.0
        while Date() < deadline {
            reached = Double(position.label) ?? 0
            if reached > 9.8 { break }
            usleep(250_000)
        }
        XCTAssertGreaterThan(reached, 9.8, "the recording never played after the spoken answer")
    }
}
