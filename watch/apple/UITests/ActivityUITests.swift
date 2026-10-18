import XCTest

/// The orb page while it works (sample data: a scripted run that thinks, searches the web, reads
/// two pages, then asks twice to run a command): the steps live under the orb, Accept all with
/// its shield, the shield taking it back, then the answer with how it worked.
final class ActivityUITests: XCTestCase {
    private var app: XCUIApplication!
    private func shot(_ name: String) {
        guard let dir = ProcessInfo.processInfo.environment["SHOTS_DIR"] else { return }
        try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent(name + ".png"))
    }
    private func element(_ id: String) -> XCUIElement { app.descendants(matching: .any)[id].firstMatch }
    private func text(containing s: String) -> XCUIElement {
        app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS %@", s)).firstMatch
    }
    /// Scrolls with small turns of the Digital Crown until `e` can be tapped (a swipe moves a page).
    private func reveal(_ e: XCUIElement) {
        for _ in 0..<24 where !(e.exists && e.isHittable) { XCUIDevice.shared.rotateDigitalCrown(delta: 0.12); usleep(150_000) }
    }

    func testTheWorkUnderTheOrbAndAcceptAll() throws {
        app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--reset-tools", "--screen", "ask", "--test-ask", "Look up what fills my disk"]
        app.launch()
        let search = element("activity.step.web_search")
        XCTAssertTrue(search.waitForExistence(timeout: 20), "no live steps under the orb:\n\(app.debugDescription)")
        XCTAssertTrue(search.label.contains("Searching the web"), search.label)
        app.swipeUp(); usleep(400_000)
        shot("w1-steps")
        // It asks to run a command: Accept all.
        let all = app.buttons["Allow these tools in this conversation"]
        XCTAssertTrue(all.waitForExistence(timeout: 20), app.debugDescription)
        shot("w2-approval")
        all.tap()
        let shield = element("activity.trust")
        XCTAssertTrue(shield.waitForExistence(timeout: 10), "no shield after Accept all:\n\(app.debugDescription)")
        shot("w3-allowed")
        // The second command is approved by the watch: no second question, then the answer.
        let answer = text(containing: "42 GB free")
        let deadline = Date().addingTimeInterval(30)
        while Date() < deadline && !answer.exists {
            XCTAssertFalse(all.exists, "asked again although its tools were allowed")
            usleep(300_000)
        }
        XCTAssertTrue(answer.exists, app.debugDescription)
        let work = element("work.link")
        reveal(work)
        XCTAssertTrue(work.waitForExistence(timeout: 10), app.debugDescription)
        XCTAssertTrue(work.label.contains("steps"), work.label)
        shot("w4-answer")
        work.tap()
        XCTAssertTrue(element("activity.step.skim_url").waitForExistence(timeout: 5), app.debugDescription)
        shot("w5-work")
    }

    func testTheShieldMakesToolsAskAgain() throws {
        app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--reset-tools", "--screen", "ask", "--test-ask", "Check my disk"]
        app.launch()
        let all = app.buttons["Allow these tools in this conversation"]
        XCTAssertTrue(all.waitForExistence(timeout: 30), app.debugDescription)
        all.tap()
        let shield = element("activity.trust")
        XCTAssertTrue(shield.waitForExistence(timeout: 10), app.debugDescription)
        XCTAssertTrue(shield.isHittable, "the shield must be on the orb, without scrolling")
        shot("w5b-shield")
        shield.tap()
        XCTAssertTrue(shield.waitForNonExistence(timeout: 5), "the shield stays after taking it back")
        // The next command asks again.
        let once = app.buttons["Allow once"]
        XCTAssertTrue(once.waitForExistence(timeout: 20), "the second command did not ask:\n\(app.debugDescription)")
        shot("w6-asks-again")
        once.tap()
        XCTAssertTrue(text(containing: "42 GB free").waitForExistence(timeout: 30), app.debugDescription)
    }
}
