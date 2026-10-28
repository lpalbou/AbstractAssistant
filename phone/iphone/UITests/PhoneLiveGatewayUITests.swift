import XCTest

/// Against a real gateway (`TEST_RUNNER_GW_URL` + `TEST_RUNNER_GW_TOKEN`, optionally `TEST_RUNNER_GW_USER`):
/// the account's conversations load and one opens with its messages; the voice list loads and a chosen
/// voice plays its sample. Skipped without a gateway (CI has none).
final class PhoneLiveGatewayUITests: XCTestCase {
    @MainActor private func launch() throws -> XCUIApplication {
        let env = ProcessInfo.processInfo.environment
        guard let url = env["GW_URL"], let token = env["GW_TOKEN"] else { throw XCTSkip("no gateway given") }
        addUIInterruptionMonitor(withDescription: "notifications") { alert in
            for label in ["Allow", "Don’t Allow", "Don't Allow"] where alert.buttons[label].exists { alert.buttons[label].tap(); return true }
            return false
        }
        let app = XCUIApplication()
        app.launchArguments = ["--gateway", url, "--token", token] + (env["GW_USER"].map { ["--user", $0] } ?? [])
        app.launch()
        let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        let allow = springboard.buttons["Allow"]
        if allow.waitForExistence(timeout: 8) { allow.tap() }
        return app
    }

    @MainActor func testConversationsLoadAndOneOpensWithItsMessages() throws {
        let app = try launch()
        XCTAssertTrue(app.buttons["chat.conversations"].waitForExistence(timeout: 30), app.debugDescription)
        app.buttons["chat.conversations"].tap()
        let row = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'conversation.open.'")).firstMatch
        XCTAssertTrue(row.waitForExistence(timeout: 30), "no conversation listed:\n\(app.debugDescription)")
        row.tap()
        let transcript = app.descendants(matching: .any)["chat.transcript"]
        XCTAssertTrue(transcript.waitForExistence(timeout: 30), "the conversation did not open:\n\(app.debugDescription)")
        XCTAssertTrue(transcript.staticTexts.firstMatch.waitForExistence(timeout: 30), "the conversation shows no message:\n\(app.debugDescription)")
        // A failed load (a lost connection, a TLS error, a refused route) shows a dismissible error banner.
        XCTAssertFalse(app.buttons["Dismiss message"].exists, "an error banner is shown:\n\(app.debugDescription)")
    }

    @MainActor func testVoicesLoadAndAChosenVoicePlaysItsSample() throws {
        let app = try launch()
        XCTAssertTrue(app.buttons["Settings"].waitForExistence(timeout: 30), app.debugDescription); app.buttons["Settings"].tap()
        app.buttons["Voice & reading"].tap()
        XCTAssertTrue(app.buttons["voice.choices"].waitForExistence(timeout: 30), app.debugDescription)
        app.buttons["voice.choices"].tap()
        // The list is lazy: a voice below the first screen exists only once scrolled to.
        XCTAssertTrue(app.staticTexts["Gateway default"].waitForExistence(timeout: 30), "the voice list did not load:\n\(app.debugDescription)")
        let choice = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Supertonic M1' OR label BEGINSWITH 'Supertonic · M1'")).firstMatch
        for _ in 0..<25 where !(choice.exists && choice.isHittable) { app.swipeUp() }
        XCTAssertTrue(choice.exists, "no Supertonic M1 voice listed:\n\(app.debugDescription)")
        choice.tap()
        XCTAssertTrue(app.buttons["Stop sample"].waitForExistence(timeout: 30), "the chosen voice did not play:\n\(app.debugDescription)")
        app.buttons["Stop sample"].tap()
    }
}
