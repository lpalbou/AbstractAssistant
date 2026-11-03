import XCTest

/// ADR 0048: Automations opens on the active ones in the gateway's order; the paused ones sit behind
/// "Paused · N", which opens them as the same cards (a tap opens one, where Resume is).
/// Demo data with two paused automations that never ran (`--paused-automations`).
final class PausedSectionPhoneUITests: XCTestCase {
    @MainActor private func capture(_ app: XCUIApplication, _ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
        if let dir = ProcessInfo.processInfo.environment["SHOTS_DIR"] {
            try? app.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent(name + ".png"))
        }
    }

    @MainActor func testPausedAutomationsLiveBehindTheirOwnSection() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--demo", "--ui-test", "--paused-automations", "--screen", "automations"]
        app.launch()
        XCTAssertTrue(app.buttons["automation.open.auto-morning"].waitForExistence(timeout: 15), app.debugDescription)
        XCTAssertFalse(app.buttons["automation.open.auto-consolidate"].exists, "a paused automation is listed with the active ones")
        capture(app, "phone-p1-list-top")
        let paused = app.descendants(matching: .any)["automations.paused"].firstMatch
        for _ in 0..<8 where !(paused.exists && paused.isHittable) { app.swipeUp() }
        XCTAssertTrue(paused.isHittable, app.debugDescription)
        XCTAssertTrue(paused.label.contains("Paused · 2"), paused.label)
        // ADR 0048: the active ones, then Paused · N, then Archived.
        let archived = app.descendants(matching: .any)["automations.archived"].firstMatch
        XCTAssertTrue(archived.exists && archived.frame.minY > paused.frame.minY, "Archived is not after Paused")
        capture(app, "phone-p2-list-bottom")
        paused.tap()
        XCTAssertTrue(app.buttons["automation.open.auto-consolidate"].waitForExistence(timeout: 10), app.debugDescription)
        XCTAssertTrue(app.buttons["automation.open.auto-reflect"].exists)
        XCTAssertFalse(app.buttons["automation.open.auto-morning"].exists, "an active one in Paused")
        capture(app, "phone-p3-paused")
    }
}
