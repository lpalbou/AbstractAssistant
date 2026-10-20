import XCTest

/// A conversation's files previewed one by one: a drawing (SVG, drawn on the watch), another, a
/// text; a swipe up shows the next file, a swipe down the one before. Sample data.
final class FilePreviewUITests: XCTestCase {
    private func shot(_ name: String) {
        guard let dir = ProcessInfo.processInfo.environment["SHOTS_DIR"] else { return }
        try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent(name + ".png"))
    }

    func testSwipingThroughAConversationsFiles() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt"]
        app.launch()
        XCTAssertTrue(app.buttons["Settings"].waitForExistence(timeout: 15))
        app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Sessions'")).firstMatch.tap()
        XCTAssertTrue(app.buttons["New conversation"].waitForExistence(timeout: 10))
        let row = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", "QC")).firstMatch
        for _ in 0..<6 where !(row.exists && row.isHittable) { app.swipeUp(); usleep(300_000) }
        row.tap()
        XCTAssertTrue(app.buttons["voice.button"].waitForExistence(timeout: 20))
        sleep(2)
        // Forward to the conversation's page (a swipe to the left).
        app.coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: 0.55))
            .press(forDuration: 0.02, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.08, dy: 0.55)), withVelocity: .fast, thenHoldForDuration: 0)
        let first = app.buttons.matching(identifier: "file.open").firstMatch
        XCTAssertTrue(first.waitForExistence(timeout: 10), "no file on the conversation's page")
        for _ in 0..<6 where !first.isHittable { app.swipeUp(); usleep(300_000) }
        first.tap()
        let name = app.staticTexts["preview.name"].firstMatch
        let position = app.staticTexts["preview.position"].firstMatch
        let drawing = app.descendants(matching: .any)["svg.drawing"].firstMatch
        XCTAssertTrue(drawing.waitForExistence(timeout: 10), "the chart is not drawn:\n\(app.debugDescription)")
        XCTAssertTrue(position.label.hasPrefix("1 of "), position.label)
        XCTAssertEqual(name.label, "cv-by-plate.svg")
        sleep(1); shot("p1-chart")
        // Up: the next file, the agent's drawing; up again: the notes; down: the drawing again.
        app.swipeUp(); sleep(2)
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label == 'hero.svg'")).firstMatch.waitForExistence(timeout: 5), app.debugDescription)
        XCTAssertTrue(app.descendants(matching: .any).matching(identifier: "svg.drawing").firstMatch.waitForExistence(timeout: 10))
        sleep(1); shot("p2-hero")
        app.swipeUp(); sleep(2)
        XCTAssertTrue(app.descendants(matching: .any)["preview.text"].firstMatch.waitForExistence(timeout: 10), "the notes are not shown")
        shot("p3-notes")
        app.swipeDown(); sleep(2)
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label == 'hero.svg'")).firstMatch.exists, "a swipe down did not go back to the drawing")
        // The share button follows the file on screen.
        XCTAssertTrue(app.buttons["Share hero.svg"].exists)
    }
}
