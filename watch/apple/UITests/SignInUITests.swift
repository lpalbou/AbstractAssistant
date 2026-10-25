import XCTest

/// The sign-in page: the gateway line above the "Sign in with user or email" field, its chooser,
/// the sign-ins kept at Sign out (one-tap rows), and Settings → Connection's "Sign out". Sample
/// data; `--reset-signins` starts each test from a watch that never signed in.
final class SignInUITests: XCTestCase {
    private static let defaultHost = "gateway.abstractframework.ai"

    private func shot(_ name: String) {
        guard let dir = ProcessInfo.processInfo.environment["SHOTS_DIR"] else { return }
        try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent(name + ".png"))
    }

    private func launch(_ extra: [String] = []) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--screen", "signin", "--reset-signins"] + extra
        app.launch()
        return app
    }

    private func element(_ app: XCUIApplication, _ id: String) -> XCUIElement {
        app.descendants(matching: .any)[id].firstMatch
    }

    /// What the "Sign in with user or email" field shows: its text-field link (a button whose label
    /// is the text typed, or the placeholder), not the Continue arrow beside it.
    private func fieldText(_ identify: XCUIElement) -> String {
        identify.buttons.matching(NSPredicate(format: "label != %@", "Continue")).firstMatch.label
    }

    func testTheGatewayLineSitsAboveTheIdentifyField() throws {
        let app = launch()
        let gateway = element(app, "signin.gateway")
        let identify = element(app, "signin.identify")
        XCTAssertTrue(gateway.waitForExistence(timeout: 15), app.debugDescription)
        XCTAssertTrue(identify.exists, app.debugDescription)
        XCTAssertTrue(gateway.label.contains(Self.defaultHost), "gateway line reads \(gateway.label)")
        XCTAssertLessThanOrEqual(gateway.frame.maxY, identify.frame.minY,
                                 "the gateway line (\(gateway.frame)) must sit above the identify field (\(identify.frame))")
        XCTAssertFalse(element(app, "signin.kept").exists, "a kept sign-in row with nothing kept")
        // One screen on a 46 mm watch: both lines are on screen without scrolling.
        let screen = app.windows.firstMatch.frame
        XCTAssertLessThanOrEqual(identify.frame.maxY, screen.maxY, "the identify field is below the screen")
        shot("signin-1-no-kept")
    }

    func testTheGatewayLineOpensTheChooser() throws {
        let app = launch()
        let gateway = element(app, "signin.gateway")
        XCTAssertTrue(gateway.waitForExistence(timeout: 15), app.debugDescription)
        gateway.tap()
        let option = element(app, "gateway.option.\(Self.defaultHost)")
        XCTAssertTrue(option.waitForExistence(timeout: 5), app.debugDescription)
        XCTAssertTrue(option.label.contains("current"), "the default gateway is not marked current: \(option.label)")
        XCTAssertTrue(element(app, "gateway.another").exists, app.debugDescription)
        XCTAssertTrue(app.staticTexts["Another gateway…"].exists || element(app, "gateway.another").label.contains("Another gateway"),
                      app.debugDescription)
        shot("signin-2-chooser")
    }

    func testTheChooserListsKnownGatewaysAndChoosingOneChangesTheLine() throws {
        // Known oldest first: the last one is the most recent, so it is the page's gateway.
        let app = launch(["--test-known", "lab.example.org,\(Self.defaultHost)"])
        let gateway = element(app, "signin.gateway")
        XCTAssertTrue(gateway.waitForExistence(timeout: 15), app.debugDescription)
        XCTAssertTrue(gateway.label.contains(Self.defaultHost), gateway.label)
        gateway.tap()
        let current = element(app, "gateway.option.\(Self.defaultHost)")
        let lab = element(app, "gateway.option.lab.example.org")
        XCTAssertTrue(lab.waitForExistence(timeout: 5), app.debugDescription)
        XCTAssertLessThan(current.frame.minY, lab.frame.minY, "most recent first")
        shot("signin-3-chooser-known")
        lab.tap()
        XCTAssertTrue(gateway.waitForExistence(timeout: 5))
        let deadline = Date().addingTimeInterval(5)
        while Date() < deadline && !gateway.label.contains("lab.example.org") { usleep(200_000) }
        XCTAssertTrue(gateway.label.contains("lab.example.org"), "choosing a gateway did not change the line: \(gateway.label)")
    }

    func testAKeptSignInShowsAsAOneTapRow() throws {
        let app = launch(["--test-kept", "alice"])
        let gateway = element(app, "signin.gateway")
        let identify = element(app, "signin.identify")
        let kept = element(app, "signin.kept")
        XCTAssertTrue(gateway.waitForExistence(timeout: 15), app.debugDescription)
        XCTAssertTrue(kept.exists, "no row for the kept sign-in\n\(app.debugDescription)")
        XCTAssertEqual(kept.label, "Sign in as alice")
        XCTAssertLessThanOrEqual(gateway.frame.maxY, kept.frame.minY, "the kept row sits under the gateway line")
        XCTAssertLessThanOrEqual(kept.frame.maxY, identify.frame.minY, "the kept row sits above the identify field")
        shot("signin-4-kept")
        // Another gateway has nothing kept: the row goes.
        app.terminate()
        let other = launch(["--test-kept", "alice", "--test-known", "lab.example.org"])
        XCTAssertTrue(element(other, "signin.gateway").waitForExistence(timeout: 15))
        XCTAssertFalse(element(other, "signin.kept").exists, "a sign-in kept on another gateway shows here")
    }

    /// The field starts with the user signed in last, unless a kept sign-in already offers that user
    /// as a row: one way into an account, never two.
    func testTheFieldIsNotPrefilledWithAUserAKeptRowOffers() throws {
        let app = launch(["--test-last-user", "admin"])
        let identify = element(app, "signin.identify")
        XCTAssertTrue(identify.waitForExistence(timeout: 15), app.debugDescription)
        XCTAssertEqual(fieldText(identify), "admin", "the last user is not offered in the field")
        app.terminate()
        let kept = launch(["--test-last-user", "admin", "--test-kept", "admin"])
        let field = element(kept, "signin.identify")
        XCTAssertTrue(field.waitForExistence(timeout: 15), kept.debugDescription)
        XCTAssertEqual(element(kept, "signin.kept").label, "Sign in as admin")
        XCTAssertEqual(fieldText(field), "Sign in with user or email",
                       "the field repeats the user the kept row already offers")
    }

    /// Choosing another gateway empties the field: the user signed in last belongs to the gateway left.
    func testChoosingAnotherGatewayEmptiesTheField() throws {
        let app = launch(["--test-last-user", "admin", "--test-known", "lab.example.org,\(Self.defaultHost)"])
        let gateway = element(app, "signin.gateway"), identify = element(app, "signin.identify")
        XCTAssertTrue(gateway.waitForExistence(timeout: 15), app.debugDescription)
        XCTAssertEqual(fieldText(identify), "admin")
        gateway.tap()
        let lab = element(app, "gateway.option.lab.example.org")
        XCTAssertTrue(lab.waitForExistence(timeout: 5), app.debugDescription)
        lab.tap()
        let deadline = Date().addingTimeInterval(5)
        while Date() < deadline && !gateway.label.contains("lab.example.org") { usleep(200_000) }
        XCTAssertTrue(gateway.label.contains("lab.example.org"), gateway.label)
        XCTAssertEqual(fieldText(identify), "Sign in with user or email",
                       "the field kept the other gateway's user: \(fieldText(identify))")
    }

    func testConnectionSaysSignOutAndAsksFirst() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--screen", "connection"]
        app.launch()
        let button = element(app, "connection.signout")
        XCTAssertTrue(button.waitForExistence(timeout: 15), app.debugDescription)
        XCTAssertEqual(button.label, "Sign out")
        XCTAssertFalse(app.buttons["Sign in as someone else"].exists)
        var swipes = 0
        while !button.isHittable && swipes < 6 { app.swipeUp(); swipes += 1 }
        button.tap()
        let keep = element(app, "signout.keep")
        XCTAssertTrue(keep.waitForExistence(timeout: 5), app.debugDescription)
        XCTAssertEqual(keep.label, "Keep my sign-in")
        XCTAssertEqual(element(app, "signout.forget").label, "Sign out and forget")
        XCTAssertTrue(app.buttons["Cancel"].exists)
        shot("signin-5-signout-confirm")
        app.buttons["Cancel"].tap()
        XCTAssertTrue(button.waitForExistence(timeout: 5), "Cancel left the Connection page")
    }
}
