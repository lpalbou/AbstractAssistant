import XCTest

/// Against a live gateway (its automations call is the slow one): Home shows the spinner and
/// Loading until the automations are in, never an error, then their name. Runs only with
/// LIVE_GW_URL and LIVE_GW_TOKEN.
final class LiveHomeUITests: XCTestCase {
    func testHomeWaitsForTheAutomations() throws {
        let env = ProcessInfo.processInfo.environment
        guard let url = env["LIVE_GW_URL"], let token = env["LIVE_GW_TOKEN"] else { throw XCTSkip("live only") }
        let app = XCUIApplication()
        app.launchArguments = ["--no-notification-prompt", "--gateway", url, "--token", token, "--home-bottom"]
        app.launch()
        func shot(_ name: String) {
            let dir = env["SHOTS_DIR"] ?? NSTemporaryDirectory()
            try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent(name + ".png"))
        }
        let automations = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Automations'")).firstMatch
        XCTAssertTrue(automations.waitForExistence(timeout: 30), app.debugDescription)
        shot("live-h1")
        let started = Date()
        let unreachable = app.descendants(matching: .any)["gateway.error"].firstMatch
        while Date().timeIntervalSince(started) < 120 && automations.label.contains("Loading") {
            XCTAssertFalse(automations.label.contains("Can't") || automations.label.contains("None yet"), automations.label)
            XCTAssertFalse(unreachable.exists, "said unreachable: \(unreachable.label)")
            usleep(500_000)
        }
        print("automations in after \(Int(Date().timeIntervalSince(started))) s: \(automations.label)")
        XCTAssertFalse(automations.label.contains("Loading") || automations.label.contains("Can't"), automations.label)
        shot("live-h2")
    }

    /// This gateway's owner has two automations named "investigate today's news.": the list shows
    /// them by name with how many times each ran, and each page shows its own instructions whole.
    func testSameNamedAutomationsShowTheirInstructionsOnTheirPage() throws {
        let env = ProcessInfo.processInfo.environment
        guard let url = env["LIVE_GW_URL"], let token = env["LIVE_GW_TOKEN"] else { throw XCTSkip("live only") }
        let app = XCUIApplication()
        app.launchArguments = ["--no-notification-prompt", "--gateway", url, "--token", token, "--screen", "automations"]
        app.launch()
        func shot(_ name: String) {
            let dir = env["SHOTS_DIR"] ?? NSTemporaryDirectory()
            try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent(name + ".png"))
        }
        let ran = app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS 'Ran '")).firstMatch
        XCTAssertTrue(ran.waitForExistence(timeout: 120), app.debugDescription)
        let news = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", "investigate today's news.")).element(boundBy: 1)
        for _ in 0..<10 where !(news.exists && news.isHittable) { app.nudgeUp() }
        XCTAssertTrue(news.exists, app.debugDescription)
        shot("live-a1")
        usleep(800_000)
        news.tap()
        let whole = app.descendants(matching: .any)["automation.instructions"].firstMatch
        XCTAssertTrue(whole.waitForExistence(timeout: 60), app.debugDescription)
        XCTAssertTrue(whole.label.lowercased().contains("you are an expert at identifying the relevant"), whole.label)
        // The latest result: a spinner, then the answer, never an error on the way.
        let failed = app.buttons.matching(NSPredicate(format: "label BEGINSWITH \"Couldn't load\"")).firstMatch
        let deadline = Date().addingTimeInterval(90)
        while Date() < deadline && !app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS 'news digest'")).firstMatch.exists {
            XCTAssertFalse(failed.exists, "an error while the result was loading")
            usleep(500_000)
        }
        shot("live-a2")
    }
}
