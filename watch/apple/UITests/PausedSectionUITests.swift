import XCTest

/// ADR 0048: the automations list opens on the active ones in the gateway's order; the paused ones
/// sit behind "Paused · N", which opens them as the same rows (a tap opens one, where Resume is).
/// Sample data with two paused automations that never ran (`--paused-automations`).
final class PausedSectionUITests: XCTestCase {
    private func shot(_ name: String) {
        guard let dir = ProcessInfo.processInfo.environment["SHOTS_DIR"] else { return }
        try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent(name + ".png"))
    }

    func testPausedAutomationsLiveBehindTheirOwnSection() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--paused-automations", "--screen", "automations"]
        app.launch()
        let first = app.buttons.matching(NSPredicate(format: "label CONTAINS 'Morning digest'")).firstMatch
        XCTAssertTrue(first.waitForExistence(timeout: 15), app.debugDescription)
        // The paused ones are not among the rows.
        XCTAssertFalse(app.buttons.matching(NSPredicate(format: "label CONTAINS 'Consolidate my notes'")).firstMatch.exists,
                       "a paused automation is listed with the active ones")
        shot("p1-list-top")
        let paused = app.descendants(matching: .any)["automations.paused"].firstMatch
        for _ in 0..<12 where !(paused.exists && paused.isHittable) { app.nudgeUp() }
        XCTAssertTrue(paused.exists, app.debugDescription)
        XCTAssertTrue(paused.label.contains("Paused · 2"), paused.label)
        let archived = app.descendants(matching: .any)["automations.archived"].firstMatch
        for _ in 0..<4 where !(archived.exists && archived.isHittable) { app.nudgeUp() }
        shot("p2-list-bottom")
        paused.tap()
        let consolidate = app.buttons.matching(NSPredicate(format: "label CONTAINS 'Consolidate my notes'")).firstMatch
        XCTAssertTrue(consolidate.waitForExistence(timeout: 10), app.debugDescription)
        XCTAssertTrue(app.buttons.matching(NSPredicate(format: "label CONTAINS 'Reflect on my notes'")).firstMatch.exists)
        XCTAssertFalse(app.buttons.matching(NSPredicate(format: "label CONTAINS 'Morning digest'")).firstMatch.exists, "an active one in Paused")
        shot("p3-paused")
    }
}
