import XCTest

/// Against a live gateway: a question that needs the web shows its real steps under the orb while it
/// works, then the answer with how it worked. Runs only with LIVE_GW_URL and LIVE_GW_TOKEN.
final class LiveActivityUITests: XCTestCase {
    func testRealStepsUnderTheOrb() throws {
        let env = ProcessInfo.processInfo.environment
        guard let url = env["LIVE_GW_URL"], let token = env["LIVE_GW_TOKEN"] else { throw XCTSkip("live only") }
        let app = XCUIApplication()
        app.launchArguments = ["--no-notification-prompt", "--gateway", url, "--token", token, "--reset-tools", "--screen", "ask",
                               "--test-ask", "Search the web for the height of the tallest building in Europe, then answer in one sentence."]
        app.launch()
        func shot(_ name: String) {
            let dir = env["SHOTS_DIR"] ?? NSTemporaryDirectory()
            try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent(name + ".png"))
        }
        let panel = app.descendants(matching: .any)["activity.panel"].firstMatch
        XCTAssertTrue(panel.waitForExistence(timeout: 60), app.debugDescription)
        let tool = app.descendants(matching: .any).matching(NSPredicate(format: "identifier BEGINSWITH 'activity.step.'")).firstMatch
        XCTAssertTrue(tool.waitForExistence(timeout: 120), "no step under the orb:\n\(app.debugDescription)")
        for k in 0..<3 { XCUIDevice.shared.rotateDigitalCrown(delta: 0.25); usleep(200_000); if k == 2 { shot("live-a1-steps") } }
        sleep(4); shot("live-a2-steps")
        let work = app.descendants(matching: .any)["work.link"].firstMatch
        XCTAssertTrue(work.waitForExistence(timeout: 240), "no answer:\n\(app.debugDescription)")
        for _ in 0..<12 where !work.isHittable { XCUIDevice.shared.rotateDigitalCrown(delta: 0.15); usleep(150_000) }
        shot("live-a3-answer")
        print("work: \(work.label)")
        work.tap()
        sleep(2); shot("live-a4-work")
    }
}
