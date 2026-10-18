import XCTest

/// Sessions has a search field; a search lists the conversations whose questions or answers hold
/// the words, the words marked; a result continues its conversation. Sample data ("assay QC").
final class SessionSearchUITests: XCTestCase {
    func testSearchFindsAndOpensAConversation() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--screen", "session-search"]
        app.launch()
        func shot(_ name: String) {
            guard let dir = ProcessInfo.processInfo.environment["SHOTS_DIR"] else { return }
            try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent(name + ".png"))
        }
        let hit = app.buttons.matching(identifier: "search.hit").firstMatch
        XCTAssertTrue(hit.waitForExistence(timeout: 15), app.debugDescription)
        XCTAssertTrue(hit.label.contains("Did the nightly assay QC pass"), hit.label)
        XCTAssertEqual(app.buttons.matching(identifier: "search.hit").count, 1, "one conversation holds both words")
        shot("q1-results")
        hit.tap()
        // The orb opens on that conversation's last exchange.
        let answer = app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS 'assay QC passed'")).firstMatch
        XCTAssertTrue(answer.waitForExistence(timeout: 15), app.debugDescription)
        shot("q2-opened")
        // Back on Sessions, the search field is there.
        app.terminate()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--screen", "sessions"]
        app.launch()
        XCTAssertTrue(app.buttons["sessions.search"].waitForExistence(timeout: 10))
        shot("q3-sessions-search")
    }

    /// Found in what a turn made: the result shows the picture beside the words.
    func testAnImageIsFoundByWhatItWasMadeFrom() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--screen", "session-search-media"]
        app.launch()
        let hit = app.buttons.matching(identifier: "search.hit").firstMatch
        XCTAssertTrue(hit.waitForExistence(timeout: 15), app.debugDescription)
        XCTAssertTrue(hit.label.contains("Kaplan"), hit.label)
        sleep(2)                                   // the picture replaces its placeholder
        if let dir = ProcessInfo.processInfo.environment["SHOTS_DIR"] {
            try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent("q4-image-hit.png"))
        }
    }
}
