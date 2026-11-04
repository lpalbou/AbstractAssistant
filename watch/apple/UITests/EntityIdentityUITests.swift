import XCTest

/// An entity is drawn and named by its digital identity (framework ADR 0052). The sample gateway's
/// Castor wrote its first update under its earlier look (rev 1) and the newest under its look now
/// (rev 2): the newest is labelled with the name and orb of who speaks.
final class EntityIdentityUITests: XCTestCase {
    func testTheSpeakerIsNamedWhenTheIdentityChanges() {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--screen", "ask-entity", "--test-ask", "Check the QC log.",
                               "-ask.conversation", "YES", "-ask.speak", "NO"]
        app.launch()
        let subtitle = app.buttons["conversation.subtitle"]
        XCTAssertTrue(subtitle.waitForExistence(timeout: 20), app.debugDescription)
        XCTAssertTrue(subtitle.label.contains("comparing the options"), subtitle.label)
        let speaker = app.descendants(matching: .any)["conversation.speaker"]
        XCTAssertTrue(speaker.waitForExistence(timeout: 10), app.debugDescription)
        XCTAssertEqual(speaker.label, "Castor")
        shoot(app, "entity-speaker-label")
    }

    /// The Assistant's own conversation names no speaker (its updates carry no identity).
    func testTheAssistantsConversationNamesNoSpeaker() {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--screen", "ask", "--test-ask", "Research museum options.",
                               "-ask.conversation", "YES", "-ask.speak", "NO"]
        app.launch()
        XCTAssertTrue(app.buttons["conversation.subtitle"].waitForExistence(timeout: 20), app.debugDescription)
        XCTAssertFalse(app.descendants(matching: .any)["conversation.speaker"].exists)
    }

    private func shoot(_ app: XCUIApplication, _ name: String) {
        let shot = XCTAttachment(screenshot: XCUIScreen.main.screenshot()); shot.name = name; shot.lifetime = .keepAlways; add(shot)
        if let dir = ProcessInfo.processInfo.environment["SHOTS_DIR"] {
            try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent(name + ".png"))
        }
    }
}
