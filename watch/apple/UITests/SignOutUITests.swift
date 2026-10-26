import XCTest

/// Sign out, for real (not sample data): a sign-out stands across launches, and "Keep my sign-in"
/// keeps the account on its own gateway, which the chooser keeps offering.
/// The gateway is a local address nothing answers: the watch stays signed in (no 401) and offline.
final class SignOutUITests: XCTestCase {
    private static let gateway = "http://127.0.0.1:9"
    private static let defaultHost = "gateway.abstractframework.ai"

    private func shot(_ name: String) {
        guard let dir = ProcessInfo.processInfo.environment["SHOTS_DIR"] else { return }
        try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent(name + ".png"))
    }

    private func element(_ app: XCUIApplication, _ id: String) -> XCUIElement {
        app.descendants(matching: .any)[id].firstMatch
    }

    private func launch(_ args: [String]) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["--no-notification-prompt", "--orb-design", "A"] + args
        app.launch()
        return app
    }

    /// A watch that never signed in, then signed in as alice: Home.
    private func signedIn() -> XCUIApplication {
        let fresh = launch(["--mock", "--screen", "signin", "--reset-signins"])
        XCTAssertTrue(element(fresh, "signin.identify").waitForExistence(timeout: 15), fresh.debugDescription)
        fresh.terminate()
        let app = launch(["--gateway", Self.gateway, "--token", "alice-token", "--user", "alice"])
        XCTAssertTrue(app.buttons["Settings"].firstMatch.waitForExistence(timeout: 20), app.debugDescription)
        return app
    }

    /// Settings → Sign out → keep or forget: the sign-in page.
    private func signOut(_ app: XCUIApplication, keep: Bool) {
        app.buttons["Settings"].firstMatch.tap()
        let button = element(app, "settings.signout")
        XCTAssertTrue(button.waitForExistence(timeout: 10), app.debugDescription)
        var turns = 0
        while !button.isHittable && turns < 8 { XCUIDevice.shared.rotateDigitalCrown(delta: 1.0); turns += 1 }
        button.tap()
        let choice = element(app, keep ? "signout.keep" : "signout.forget")
        XCTAssertTrue(choice.waitForExistence(timeout: 5), app.debugDescription)
        choice.tap()
        XCTAssertTrue(element(app, "signin.identify").waitForExistence(timeout: 10), app.debugDescription)
    }

    /// Signed out, then relaunched (twice): the sign-in page, and it stays.
    func testASignOutStandsAcrossALaunch() throws {
        let app = signedIn()
        signOut(app, keep: false)
        app.terminate()
        for i in 0..<2 {
            let again = launch([])
            XCTAssertTrue(element(again, "signin.identify").waitForExistence(timeout: 15), again.debugDescription)
            sleep(3)
            shot("signout-1-relaunched-\(i)")
            XCTAssertTrue(element(again, "signin.identify").exists, "signed in again after a sign-out")
            XCTAssertFalse(again.buttons["Settings"].exists, "Home after a sign-out")
            // "Sign out and forget": nothing to tap back in with.
            XCTAssertFalse(element(again, "signin.kept").exists, "a forgotten sign-in is offered")
            again.terminate()
        }
    }

    /// "Keep my sign-in": the page opens on the gateway just left with the account as a one-tap row;
    /// the chooser offers that gateway (with its account) and AbstractFramework's; the account shows
    /// on its own gateway only; it survives a relaunch, and one tap signs in.
    func testKeepMySignInKeepsTheAccountOnItsGateway() throws {
        let app = signedIn()
        signOut(app, keep: true)
        let gateway = element(app, "signin.gateway"), kept = element(app, "signin.kept")
        XCTAssertTrue(gateway.label.contains("127.0.0.1:9"), "the page is not on the gateway just left: \(gateway.label)")
        XCTAssertTrue(kept.waitForExistence(timeout: 5), "the kept account is not offered\n\(app.debugDescription)")
        XCTAssertEqual(kept.label, "Sign in as alice")
        shot("signout-2-kept")
        gateway.tap()
        let left = element(app, "gateway.option.\(Self.gateway)")
        let home = element(app, "gateway.option.\(Self.defaultHost)")
        XCTAssertTrue(left.waitForExistence(timeout: 5), app.debugDescription)
        XCTAssertTrue(left.label.contains("1 kept account"), left.label)
        XCTAssertTrue(home.exists, "AbstractFramework's gateway is not offered\n\(app.debugDescription)")
        shot("signout-3-chooser")
        home.tap()
        let deadline = Date().addingTimeInterval(5)
        while Date() < deadline && !gateway.label.contains(Self.defaultHost) { usleep(200_000) }
        XCTAssertTrue(gateway.label.contains(Self.defaultHost), gateway.label)
        XCTAssertFalse(kept.exists, "an account kept on another gateway shows here")
        app.terminate()
        // Relaunched: the account is still kept, on its gateway.
        let again = launch([])
        let keptAgain = element(again, "signin.kept")
        XCTAssertTrue(keptAgain.waitForExistence(timeout: 15), "the kept account did not survive a relaunch\n\(again.debugDescription)")
        XCTAssertEqual(keptAgain.label, "Sign in as alice")
        keptAgain.tap()
        XCTAssertTrue(again.buttons["Settings"].firstMatch.waitForExistence(timeout: 15), again.debugDescription)
    }
}
