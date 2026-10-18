import XCTest

/// Against a live gateway whose Assistant workflow makes images: choose it for new conversations,
/// ask for a picture, see it under the answer and full screen; then a conversation that already
/// made one (LIVE_MEDIA_SESSION) shows it in its history. Runs only with LIVE_GW_URL and LIVE_GW_TOKEN.
final class LiveMediaUITests: XCTestCase {
    private var app: XCUIApplication!
    private func element(_ id: String) -> XCUIElement { app.descendants(matching: .any)[id].firstMatch }
    private func shot(_ name: String) {
        let dir = ProcessInfo.processInfo.environment["SHOTS_DIR"] ?? NSTemporaryDirectory()
        try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent(name + ".png"))
    }
    private func reveal(_ e: XCUIElement) {
        for _ in 0..<10 where !(e.exists && e.isHittable) { app.swipeUp(); usleep(300_000) }
    }

    func testAPictureFromTheLiveAssistantWorkflow() throws {
        let env = ProcessInfo.processInfo.environment
        guard let url = env["LIVE_GW_URL"], let token = env["LIVE_GW_TOKEN"] else { throw XCTSkip("live only") }
        let live = ["--no-notification-prompt", "--gateway", url, "--token", token]
        app = XCUIApplication()
        app.launchArguments = live + ["--reset-tools", "--screen", "settings"]
        app.launch()
        let settingsTools = element("settings.tools")
        reveal(settingsTools)
        XCTAssertTrue(settingsTools.waitForExistence(timeout: 30), app.debugDescription)
        settingsTools.tap()
        let row = element("tools.workflow")
        XCTAssertTrue(row.waitForExistence(timeout: 60), app.debugDescription)
        row.tap()
        let orchestrator = element("workflow.abstractassistant-orchestrator")
        XCTAssertTrue(orchestrator.waitForExistence(timeout: 60), app.debugDescription)
        orchestrator.tap()
        XCTAssertTrue(row.waitForExistence(timeout: 10) && row.label.contains("Orchestrator"), row.label)

        app = XCUIApplication()
        app.launchArguments = live + ["--screen", "ask", "--test-ask", "Generate an image of a small red apple on a white plate."]
        app.launch()
        let image = element("media.image")
        XCTAssertTrue(image.waitForExistence(timeout: 240), "no image under the answer:\n\(app.debugDescription)")
        reveal(image)
        sleep(8)                                       // a 2 MB picture over the network, then shrunk
        shot("live-m1-answer-image")
        image.tap()
        XCTAssertTrue(element("media.full").waitForExistence(timeout: 60), app.debugDescription)
        sleep(2)
        shot("live-m2-image-full")

        if let session = env["LIVE_MEDIA_SESSION"] {
            app = XCUIApplication()
            app.launchArguments = live + ["--test-session", session]
            app.launch()
            let withMedia = app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS %@", "With media")).firstMatch
            let fullImage = element("media.image")
            let deadline = Date().addingTimeInterval(120)
            while Date() < deadline && !withMedia.exists && !fullImage.exists { app.swipeUp(); sleep(2) }
            shot("live-m3-history")
            XCTAssertTrue(withMedia.exists || fullImage.exists, "the conversation's image is not in its history:\n\(app.debugDescription)")
        }

        app = XCUIApplication()
        app.launchArguments = live + ["--reset-tools", "--screen", "settings"]
        app.launch()
        app.terminate()
    }
}
