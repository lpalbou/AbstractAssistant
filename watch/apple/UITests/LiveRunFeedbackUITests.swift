import XCTest

/// Run on an automation's details against a real gateway (LIVE_GW_URL, LIVE_GW_TOKEN; its first
/// automation, or the one at LIVE_AUTOMATION_INDEX, runs once): the tap shows at once that it is
/// starting, the details stay until the gateway has the run, then the orb page follows it to its
/// answer. Each step is printed with its time (`RUNSEQ`).
final class LiveRunFeedbackUITests: XCTestCase {
    private var t0 = Date()
    private func step(_ s: String) { print(String(format: "RUNSEQ %6.2f %.0f %@", Date().timeIntervalSince(t0), Date().timeIntervalSince1970 * 1000, s)) }

    func testRunIsFollowedFromTheTap() throws {
        let env = ProcessInfo.processInfo.environment
        guard let url = env["LIVE_GW_URL"], let token = env["LIVE_GW_TOKEN"] else { throw XCTSkip("live only") }
        let app = XCUIApplication()
        app.launchArguments = ["--gateway", url, "--token", token, "--no-notification-prompt", "--orb-design", "A",
                               "--open-automation", env["LIVE_AUTOMATION_INDEX"] ?? "0"]
        app.launch()
        XCTAssertTrue(app.staticTexts["ask.automation"].firstMatch.waitForExistence(timeout: 60), app.debugDescription)
        let info = app.buttons["ask.info"].firstMatch
        XCTAssertTrue(info.waitForExistence(timeout: 30), app.debugDescription)
        sleep(2)
        t0 = Date(); step("orb page of the automation")
        info.tap()
        let run = app.buttons["automation.run"].firstMatch
        XCTAssertTrue(run.waitForExistence(timeout: 30), app.debugDescription)
        XCTAssertTrue(app.descendants(matching: .any)["automation.title"].firstMatch.waitForExistence(timeout: 10))
        sleep(3)                                                     // its definition and fresh row are read
        step("details, Run shown")
        run.tap()
        step("Run tapped")
        // What the screen shows, every quarter second, until the orb page follows the run.
        var last = "", followed = false, sawStarting = false, atRestSince: Date?, atRestFor: TimeInterval = 0
        let end = Date().addingTimeInterval(40)
        while Date() < end {
            let onDetails = app.descendants(matching: .any)["automation.title"].exists
            let starting = app.descendants(matching: .any)["automation.starting"].exists
            let working = app.descendants(matching: .any)["activity.panel"].exists || app.buttons["ask.stop"].exists
            let now = onDetails ? (starting ? "details: starting line shown" : "details: no feedback")
                                : (working ? "orb page: following the run" : "orb page: at rest, nothing shown")
            if starting { sawStarting = true }
            if !onDetails && !working { atRestSince = atRestSince ?? Date() }
            if working, let since = atRestSince { atRestFor = Date().timeIntervalSince(since) }
            if now != last { step(now); last = now }
            if working && !onDetails { followed = true; break }
            usleep(250_000)
        }
        XCTAssertTrue(sawStarting, "the tap on Run showed nothing on the details")
        XCTAssertTrue(followed, "the run was never followed on the orb page")
        XCTAssertLessThan(atRestFor, 1.5, "the orb page sat at rest before following the run")
        let done = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: app.buttons["ask.stop"].firstMatch)
        let answered = XCTWaiter.wait(for: [done], timeout: 180) == .completed && app.buttons["Share"].waitForExistence(timeout: 10)
        step(answered ? "orb page: the run's answer" : "no answer in 180 s")
        XCTAssertTrue(answered)
    }
}
