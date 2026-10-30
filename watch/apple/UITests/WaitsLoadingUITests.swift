import XCTest

/// A notification opens Needs you before a list read. An empty array alone cannot distinguish
/// a slow radio, a failed read, a handled gate, or one the watch's existing trust just approved.
final class WaitsLoadingUITests: XCTestCase {
    private func launch(_ scenario: String) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--reset-tools", "--screen", "waits", "--waits-state", scenario]
        app.launch()
        return app
    }

    func testInitiallyEmptyListShowsConfirmedEmptyAfterRead() {
        let app = launch("empty")
        XCTAssertTrue(app.staticTexts["waits.empty"].waitForExistence(timeout: 10), app.debugDescription)
        XCTAssertEqual(app.staticTexts["screen.title"].firstMatch.label, "Needs you")
        XCTAssertTrue(app.buttons["Back"].exists)
    }

    func testDelayedGateShowsCheckingWithoutDismissingThePage() {
        let app = launch("delayed")
        XCTAssertTrue(app.staticTexts["Checking what needs you…"].waitForExistence(timeout: 5), app.debugDescription)
        XCTAssertFalse(app.staticTexts["waits.empty"].exists)
        let gate = app.buttons.matching(NSPredicate(format: "label CONTAINS 'echo gate-1'")).firstMatch
        XCTAssertTrue(gate.waitForExistence(timeout: 10), app.debugDescription)
        XCTAssertEqual(app.staticTexts["screen.title"].firstMatch.label, "Needs you")
    }

    func testFailedReadCanBeRetriedToConfirmedEmpty() {
        let app = launch("retry")
        let retry = app.buttons["waits.retry"]
        XCTAssertTrue(retry.waitForExistence(timeout: 10), app.debugDescription)
        XCTAssertFalse(app.staticTexts["waits.empty"].exists)
        retry.tap()
        XCTAssertTrue(app.staticTexts["waits.empty"].waitForExistence(timeout: 10), app.debugDescription)
    }

    func testRunsFailureDoesNotMakeSuccessfulWaitsReadFail() {
        let app = launch("runs-fail")
        XCTAssertTrue(app.staticTexts["waits.empty"].waitForExistence(timeout: 10), app.debugDescription)
        XCTAssertFalse(app.buttons["waits.retry"].exists)
    }

    func testOlderFailureCannotReplaceNewerSuccessfulRead() {
        // The foreground poll and opening the page overlap: the first read fails late,
        // while the newer read succeeds. Its empty confirmation must remain authoritative.
        let app = launch("stale-error")
        XCTAssertTrue(app.staticTexts["waits.empty"].waitForExistence(timeout: 10), app.debugDescription)
        sleep(5)
        XCTAssertTrue(app.staticTexts["waits.empty"].exists, app.debugDescription)
        XCTAssertFalse(app.buttons["waits.retry"].exists)
    }

    func testOlderGateCannotReplaceNewerEmptyRead() {
        // In the incident the newer empty result equals the initial []. It does not bump the
        // approval revision, so the waits-read revision must also guard list publication.
        let app = launch("stale-gate")
        XCTAssertTrue(app.staticTexts["waits.empty"].waitForExistence(timeout: 10), app.debugDescription)
        sleep(5)
        XCTAssertTrue(app.staticTexts["waits.empty"].exists, app.debugDescription)
        XCTAssertFalse(app.buttons.matching(NSPredicate(format: "label CONTAINS 'echo gate-1'")).firstMatch.exists)
    }

    func testBackgroundReadKeepsConfirmedEmptyVisible() {
        let app = launch("poll-slow")
        XCTAssertTrue(app.staticTexts["waits.empty"].waitForExistence(timeout: 10), app.debugDescription)
        // The normal 15-second foreground poll is still reading when we look again.
        sleep(14)
        XCTAssertTrue(app.staticTexts["waits.empty"].exists, app.debugDescription)
        XCTAssertFalse(app.staticTexts["Checking what needs you…"].exists)
    }
}
