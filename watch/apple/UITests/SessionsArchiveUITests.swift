import XCTest

/// Home says what is new (Sessions and Automations), Sessions outlines the conversations with an
/// answer not seen yet, and the red button archives one on the gateway after a confirmation;
/// Archived restores it. Sample data.
final class SessionsArchiveUITests: XCTestCase {
    private var app: XCUIApplication!
    private func shot(_ name: String) {
        guard let dir = ProcessInfo.processInfo.environment["SHOTS_DIR"] else { return }
        try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent(name + ".png"))
    }
    private func element(_ id: String) -> XCUIElement { app.descendants(matching: .any)[id].firstMatch }
    private func text(containing s: String) -> XCUIElement {
        app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS %@", s)).firstMatch
    }
    /// Short drags until `e` can be tapped (a list loads its rows as they come near the screen).
    private func reveal(_ e: XCUIElement) {
        for _ in 0..<12 where !(e.exists && e.isHittable) { app.nudgeUp() }
    }

    func testNewSessionsAndArchive() throws {
        app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--reset-seen"]
        app.launch()
        // Home: the sample has two finished conversations (the ADTTE and QC ones; the build one waits
        // on you, the docs one failed but is new too) — the count is what is new.
        let newBadge = text(containing: "new")
        XCTAssertTrue(newBadge.waitForExistence(timeout: 20), app.debugDescription)
        reveal(element("Sessions"))
        shot("s1-home")
        app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Sessions'")).firstMatch.tap()
        let archive = app.buttons.matching(identifier: "session.archive")
        XCTAssertTrue(archive.firstMatch.waitForExistence(timeout: 10), app.debugDescription)
        // Finished conversations with an answer not opened yet are marked.
        let marked = app.buttons.matching(NSPredicate(format: "label CONTAINS 'New answer'")).firstMatch
        for _ in 0..<8 where !marked.exists { app.nudgeUp() }
        XCTAssertTrue(marked.exists, "no new answer is marked")
        shot("s2-sessions")
        // Archive a conversation whose button is on screen (below the title bar) and on (it is finished).
        var target: XCUIElement?
        for _ in 0..<10 {
            target = archive.allElementsBoundByIndex.first { $0.isEnabled && $0.frame.minY > 70 && $0.frame.maxY < 230 }
            if target != nil { break }
            app.nudgeUp()
        }
        guard let button = target else { return XCTFail("no archive button on screen:\n\(app.debugDescription)") }
        usleep(800_000)                                   // the list stops coasting: a tap is a tap, not "stop"
        button.tap()
        let confirm = element("archive.confirm")
        XCTAssertTrue(confirm.waitForExistence(timeout: 5), "archiving does not ask first")
        // The confirmation names the conversation.
        let named = element("archive.title")
        guard named.waitForExistence(timeout: 3), !named.label.isEmpty else { return XCTFail("the confirmation does not name the conversation") }
        let title = named.label
        shot("s3-confirm")
        confirm.tap()
        let row = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", title)).firstMatch
        XCTAssertTrue(row.waitForNonExistence(timeout: 10), "the archived conversation is still listed: \(title)")
        shot("s4-archived")
        // Archived lists it; Restore brings it back.
        let archived = element("sessions.archived")
        reveal(archived)
        archived.tap()
        let restore = element("archived.restore")
        XCTAssertTrue(restore.waitForExistence(timeout: 10), app.debugDescription)
        XCTAssertTrue(text(containing: title).exists, "Archived does not list \(title)")
        shot("s5-archived-list")
        restore.tap()
        XCTAssertTrue(restore.waitForNonExistence(timeout: 10))
        app.buttons["Back"].firstMatch.tap()
        let back = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", title)).firstMatch
        for _ in 0..<10 where !back.exists { app.nudgeUp() }
        XCTAssertTrue(back.exists, "the restored conversation is not back: \(title)")
    }
}
