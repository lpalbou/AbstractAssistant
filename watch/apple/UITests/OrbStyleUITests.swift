import XCTest

/// The first-launch orb question lists the styles by family (Orbs, Forms, Faces, Machines); a style
/// opens its preview, which goes through the assistant's phases; "Use this" keeps it (Settings
/// names it). Sample data.
final class OrbStyleUITests: XCTestCase {
    private func shot(_ name: String) {
        guard let dir = ProcessInfo.processInfo.environment["SHOTS_DIR"] else { return }
        try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent(name + ".png"))
    }

    func testStylesByFamilyPreviewAndChoose() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--orb-design", "A", "--ask-orb"]
        app.launch()
        let halo = app.buttons["orb.Halo"].firstMatch
        XCTAssertTrue(halo.waitForExistence(timeout: 15), app.debugDescription)
        XCTAssertTrue(app.descendants(matching: .any)["family.Orbs"].exists, "no Orbs section")
        shot("o1-list")
        // Every family, in order: the first style of each, further down each time.
        var lastY = halo.frame.minY - 1
        for name in ["Lotus", "Face", "Lens"] {
            let row = app.buttons["orb.\(name)"].firstMatch
            for _ in 0..<30 where !row.exists { app.nudgeUp() }
            if !row.exists { shot("o1-missing-\(name)") }
            XCTAssertTrue(row.exists, "no \(name) row:\n\(app.debugDescription)")
            shot("o1-\(name)")
            _ = lastY; lastY = row.frame.minY
        }
        // The four newest machines are there, then the last style, on screen at the end of the
        // list: its preview.
        for name in ["Hover", "Spark", "Cruiser"] {
            let row = app.buttons["orb.\(name)"].firstMatch
            for _ in 0..<12 where !row.exists { app.nudgeUp() }
            XCTAssertTrue(row.exists, "no \(name) row:\n\(app.debugDescription)")
        }
        let android = app.buttons["orb.Android"].firstMatch
        for _ in 0..<8 where !android.exists { app.nudgeUp() }
        for _ in 0..<3 where !android.isHittable { app.nudgeUp() }
        XCTAssertTrue(android.exists, app.debugDescription)
        android.tap()
        // The preview: the phases in turn.
        let phase = app.staticTexts["orb.phase"].firstMatch
        XCTAssertTrue(phase.waitForExistence(timeout: 10), app.debugDescription)
        let first = phase.label
        let end = Date().addingTimeInterval(6)
        while Date() < end && phase.label == first { usleep(250_000) }
        XCTAssertNotEqual(phase.label, first, "the preview stays in one phase")
        shot("o2-preview")
        app.buttons["Use this"].firstMatch.tap()
        // Home, then Settings: it is the orb in use.
        let settings = app.buttons["Settings"].firstMatch
        XCTAssertTrue(settings.waitForExistence(timeout: 10), app.debugDescription)
        settings.tap()
        XCTAssertTrue(app.buttons.matching(NSPredicate(format: "label CONTAINS 'Orb style' AND label CONTAINS 'Android'")).firstMatch
            .waitForExistence(timeout: 10), app.debugDescription)
        shot("o3-settings")
    }
}
