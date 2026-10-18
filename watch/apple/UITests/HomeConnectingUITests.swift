import XCTest

/// Opening the app while the watch's radio is still coming up: Home says Connecting (animated)
/// while the first polls fail and are retried, never that the gateway is unreachable; that is said
/// only after 3 failed tries over 20 s. Sample data.
final class HomeConnectingUITests: XCTestCase {
    private func shot(_ name: String) {
        guard let dir = ProcessInfo.processInfo.environment["SHOTS_DIR"] else { return }
        try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent(name + ".png"))
    }

    func testASlowStartSaysConnectingNeverUnreachable() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--slow-start"]
        app.launch()
        let connecting = app.descendants(matching: .any)["gateway.connecting"].firstMatch
        let error = app.descendants(matching: .any)["gateway.error"].firstMatch
        XCTAssertTrue(connecting.waitForExistence(timeout: 10), app.debugDescription)
        shot("c1-connecting")
        // The 3 failed polls are retried every 3 s; the 4th answers.
        let sessions = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Sessions' AND NOT label CONTAINS 'Loading'")).firstMatch
        let deadline = Date().addingTimeInterval(30)
        while Date() < deadline && !sessions.exists {
            XCTAssertFalse(error.exists, "said unreachable while it was only starting: \(error.label)")
            usleep(250_000)
        }
        XCTAssertTrue(sessions.exists, app.debugDescription)
        XCTAssertFalse(connecting.exists, "still says Connecting once connected")
        XCTAssertFalse(error.exists)
        shot("c2-connected")
    }

    func testAnUnreachableGatewayIsSaidAfterTwentySeconds() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--offline"]
        let launched = Date()
        app.launch()
        let connecting = app.descendants(matching: .any)["gateway.connecting"].firstMatch
        let error = app.descendants(matching: .any)["gateway.error"].firstMatch
        XCTAssertTrue(connecting.waitForExistence(timeout: 10), app.debugDescription)
        while Date().timeIntervalSince(launched) < 17 {
            XCTAssertFalse(error.exists, "said unreachable after \(Int(Date().timeIntervalSince(launched))) s")
            usleep(250_000)
        }
        XCTAssertTrue(error.waitForExistence(timeout: 25), "never says the gateway is unreachable")
        XCTAssertFalse(connecting.exists)
        shot("c3-unreachable")
    }
}
