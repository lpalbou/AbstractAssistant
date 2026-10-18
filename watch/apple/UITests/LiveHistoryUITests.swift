import XCTest

/// A real conversation's history on the orb page, read-only, against a live gateway: open the
/// conversation LIVE_SESSION as a tap on its row does, then Show older until there is nothing
/// older, collecting every card's question; LIVE_SESSION_OLDEST must be among them (the
/// conversation's first question). Runs only with LIVE_GW_URL and LIVE_GW_TOKEN.
final class LiveHistoryUITests: XCTestCase {
    func testEveryMessageOfARealConversation() throws {
        let env = ProcessInfo.processInfo.environment
        guard let url = env["LIVE_GW_URL"], let token = env["LIVE_GW_TOKEN"],
              let session = env["LIVE_SESSION"], let oldest = env["LIVE_SESSION_OLDEST"] else { throw XCTSkip("live only") }
        let app = XCUIApplication()
        app.launchArguments = ["--no-notification-prompt", "--gateway", url, "--token", token, "--test-session", session]
        app.launch()
        XCTAssertTrue(app.buttons["Share"].waitForExistence(timeout: 120), "the conversation did not open:\n\(app.debugDescription)")
        let rowLabel = session
        let oldestText = app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS %@", oldest)).firstMatch
        let showOlder = app.buttons["Show older"].firstMatch
        var taps = 0, swipes = 0
        for _ in 0..<150 {
            if oldestText.exists { break }
            if showOlder.exists && showOlder.isHittable { showOlder.tap(); taps += 1; sleep(3); continue }
            if app.buttons["Loading…"].exists { sleep(2); continue }
            app.swipeUp(); swipes += 1
            if swipes > 40 && !showOlder.exists { break }
        }
        let seen = app.buttons.allElementsBoundByIndex.map { String($0.label.prefix(70)) }
        let found = oldestText.exists
        let dir = env["SHOTS_DIR"] ?? NSTemporaryDirectory()
        try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent("live-history-end.png"))
        try? (["session: " + rowLabel, "show older taps: \(taps), swipes: \(swipes), oldest shown: \(found)"] + seen).joined(separator: "\n")
            .write(to: URL(fileURLWithPath: dir).appendingPathComponent("live-history.txt"), atomically: true, encoding: .utf8)
        XCTAssertTrue(found, "the oldest question never showed (\(taps) Show older taps, \(swipes) swipes)")
    }
}

/// What a real conversation shows while it opens, frame by frame (screenshots every 0.5 s to
/// SHOTS_DIR, plus the text of the last message each time): a message must appear once, whole.
final class LiveOpeningUITests: XCTestCase {
    func testWhatShowsWhileAConversationOpens() throws {
        let env = ProcessInfo.processInfo.environment
        guard let url = env["LIVE_GW_URL"], let token = env["LIVE_GW_TOKEN"], let session = env["LIVE_SESSION"],
              let dir = env["SHOTS_DIR"] else { throw XCTSkip("live only") }
        let app = XCUIApplication()
        app.launchArguments = ["--no-notification-prompt", "--gateway", url, "--token", token, "--test-session", session]
        app.launch()
        var log: [String] = []
        let t0 = Date()
        var swiped = false
        while Date().timeIntervalSince(t0) < 20 {
            let t = Date().timeIntervalSince(t0)
            if !swiped && app.buttons["Share"].exists { app.swipeUp(); swiped = true }
            let texts = app.staticTexts.allElementsBoundByIndex.prefix(12).map { "\($0.label.count):\($0.label.prefix(50))" }
            log.append(String(format: "%.1f s ", t) + texts.joined(separator: " | "))
            try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent(String(format: "open-%04.1f.png", t)))
            usleep(500_000)
        }
        try? log.joined(separator: "\n").write(to: URL(fileURLWithPath: dir).appendingPathComponent("opening.txt"), atomically: true, encoding: .utf8)
    }
}
