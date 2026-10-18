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
    /// Slow swipes until `e` can be tapped (a list loads its rows as they come near the screen).
    private func reveal(_ e: XCUIElement) {
        for _ in 0..<12 where !(e.exists && e.isHittable) { app.swipeUp(velocity: .slow); usleep(300_000) }
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
        // The QC conversation is further down (a list loads the rows near the screen).
        let qcRow = app.buttons.matching(NSPredicate(format: "label CONTAINS 'Did the nightly assay QC pass'")).firstMatch
        reveal(qcRow)
        if let dir = ProcessInfo.processInfo.environment["SHOTS_DIR"] {
            try? app.debugDescription.write(to: URL(fileURLWithPath: dir).appendingPathComponent("sessions-tree.txt"), atomically: true, encoding: .utf8)
        }
        shot("s2b-after-scroll")
        XCTAssertTrue(qcRow.exists, "no QC row")
        XCTAssertTrue(qcRow.label.contains("New answer"), "its new answer is not marked: \(qcRow.label)")
        shot("s2-sessions")
        // Archive it (it is finished, so its button is on).
        let rowFrame = qcRow.frame
        let button = archive.allElementsBoundByIndex.first { abs($0.frame.midY - rowFrame.midY) < 30 && $0.isEnabled }
        XCTAssertNotNil(button, "no archive button beside the QC conversation")
        button!.tap()
        let confirm = element("archive.confirm")
        XCTAssertTrue(confirm.waitForExistence(timeout: 5), "archiving does not ask first")
        shot("s3-confirm")
        confirm.tap()
        let gone = app.buttons.matching(NSPredicate(format: "label CONTAINS 'Did the nightly assay QC pass'")).firstMatch
        XCTAssertTrue(gone.waitForNonExistence(timeout: 10), "the archived conversation is still listed")
        shot("s4-archived")
        // Archived lists it; Restore brings it back.
        let archived = element("sessions.archived")
        reveal(archived)
        archived.tap()
        let restore = element("archived.restore")
        XCTAssertTrue(restore.waitForExistence(timeout: 10), app.debugDescription)
        shot("s5-archived-list")
        restore.tap()
        XCTAssertTrue(restore.waitForNonExistence(timeout: 10))
        app.buttons["Back"].firstMatch.tap()
        XCTAssertTrue(app.buttons.matching(NSPredicate(format: "label CONTAINS 'Did the nightly assay QC pass'")).firstMatch.waitForExistence(timeout: 10),
                      "the restored conversation is not back")
    }
}
