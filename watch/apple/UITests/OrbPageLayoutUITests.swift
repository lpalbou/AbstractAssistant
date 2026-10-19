import XCTest

/// The orb page looks the same however it was reached and however it was scrolled: the orb, its
/// keyboard and tools icons and "who answers" stay where a fresh page puts them, after scrolling
/// down to the messages and back, after opening a message and coming back, after pulling past the
/// top. Sample data.
final class OrbPageLayoutUITests: XCTestCase {
    private var app: XCUIApplication!
    private func shot(_ name: String) {
        guard let dir = ProcessInfo.processInfo.environment["SHOTS_DIR"] else { return }
        try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent(name + ".png"))
    }
    /// Where the stage's controls are now (the keyboard and tools icons, "who answers").
    private func layout() -> [CGFloat] {
        let keyboard = app.buttons["Type or dictate"].firstMatch, tools = app.buttons["ask.tools"].firstMatch
        let who = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "Talking to")).firstMatch
        return [keyboard, tools, who].map { $0.exists ? $0.frame.midY.rounded() : -1 }
    }
    /// Turns of the Digital Crown: down to the messages (positive) or back up (negative).
    private func crown(_ delta: CGFloat, _ times: Int = 1) {
        for _ in 0..<times { XCUIDevice.shared.rotateDigitalCrown(delta: delta); usleep(250_000) }
        usleep(800_000)
    }
    private func drag(_ from: CGFloat, _ to: CGFloat) {
        app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: from))
            .press(forDuration: 0.05, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: to)))
        usleep(900_000)
    }

    func testTheOrbStaysWhereAFreshPagePutsIt() throws {
        app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--screen", "sessions"]
        app.launch()
        let row = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", "QC")).firstMatch
        XCTAssertTrue(app.buttons["New conversation"].waitForExistence(timeout: 15))
        for _ in 0..<6 where !(row.exists && row.isHittable) { app.swipeUp(); usleep(300_000) }
        row.tap()
        XCTAssertTrue(app.buttons["voice.button"].waitForExistence(timeout: 20), app.debugDescription)
        sleep(2)
        let fresh = layout()
        shot("l1-fresh")
        XCTAssertFalse(fresh.contains(-1), "a control is missing on the fresh page: \(fresh)\n\(app.debugDescription)")
        // Down to the messages and back up.
        crown(0.5, 6)
        shot("l2-down")
        crown(-0.5, 12)
        shot("l2-back-up")
        XCTAssertEqual(layout(), fresh, "scrolled back up, the stage moved")
        // A message opened from below the orb, then Back.
        let card = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "Did the assay QC pass,")).firstMatch
        for _ in 0..<12 where !(card.exists && card.isHittable && card.frame.minY > 70) { crown(0.3) }
        XCTAssertTrue(card.exists && card.isHittable, "no earlier message to open:\n\(app.debugDescription)")
        if card.exists && card.isHittable {
            card.tap(); sleep(2)
            app.buttons["Back"].firstMatch.tap(); sleep(2)
            crown(-0.5, 14)
            shot("l3-after-a-message")
            XCTAssertEqual(layout(), fresh, "after opening a message and coming back, the stage moved")
        }
        // Pulled past the top and let go.
        drag(0.3, 0.95)
        shot("l4-pulled")
        XCTAssertEqual(layout(), fresh, "pulled past the top, the stage moved")
    }
}
