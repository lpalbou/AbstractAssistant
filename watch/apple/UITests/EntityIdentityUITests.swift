import XCTest

/// An entity is drawn and named by its digital identity (framework ADR 0052). The sample gateway's
/// Castor wrote its first update under its earlier look (rev 1) and the newest under its look now
/// (rev 2): the newest is labelled with the name and orb of who speaks.
final class EntityIdentityUITests: XCTestCase {
    @MainActor func testTheSpeakerIsNamedWhenTheIdentityChanges() {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--screen", "ask-entity", "--test-ask", "Check the QC log.",
                               "-ask.conversation", "YES", "-ask.speak", "NO"]
        app.launch()
        let subtitle = app.buttons["conversation.subtitle"]
        XCTAssertTrue(subtitle.waitForExistence(timeout: 20), app.debugDescription)
        XCTAssertTrue(subtitle.label.contains("comparing the options"), subtitle.label)
        let speaker = app.descendants(matching: .any)["conversation.speaker"]
        XCTAssertTrue(speaker.waitForExistence(timeout: 10), app.debugDescription)
        XCTAssertEqual(speaker.label, "Castor")
        shoot(app, "entity-speaker-label")
    }

    /// The Assistant's own conversation names no speaker (its updates carry no identity).
    @MainActor func testTheAssistantsConversationNamesNoSpeaker() {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--screen", "ask", "--test-ask", "Research museum options.",
                               "-ask.conversation", "YES", "-ask.speak", "NO"]
        app.launch()
        XCTAssertTrue(app.buttons["conversation.subtitle"].waitForExistence(timeout: 20), app.debugDescription)
        XCTAssertFalse(app.descendants(matching: .any)["conversation.speaker"].exists)
    }

    /// Mira's visit is a dialogue: Castor wrote the first update, Mira the newest; Mira is named.
    @MainActor func testTwoSpeakersInARowNameTheNewOne() {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--screen", "ask", "--test-ask", "Check the QC log.",
                               "-ask.responder", "entity:mira", "-ask.conversation", "YES", "-ask.speak", "NO"]
        app.launch()
        let subtitle = app.buttons["conversation.subtitle"]
        XCTAssertTrue(subtitle.waitForExistence(timeout: 20), app.debugDescription)
        XCTAssertTrue(subtitle.label.contains("re-read P07"), subtitle.label)
        let speaker = app.descendants(matching: .any)["conversation.speaker"]
        XCTAssertTrue(speaker.waitForExistence(timeout: 10), app.debugDescription)
        XCTAssertEqual(speaker.label, "Mira")
        shoot(app, "entity-two-speakers")
    }

    /// An entity whose identity is not known (closed for maintenance) has no orb: an empty grey ring,
    /// no design and no colour (the Assistant's look in its place turns this red), and the gateway's
    /// sentence under it.
    @MainActor func testAnEntityWithoutAKnownIdentityHasNoOrb() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--screen", "ask-entity", "--test-held-entity", "castor"]
        app.launch()
        let status = app.staticTexts["ask.status"]
        XCTAssertTrue(status.waitForExistence(timeout: 15), app.debugDescription)
        let sentence = NSPredicate(format: "label BEGINSWITH %@", "Castor is closed for maintenance")
        XCTAssertTrue(app.staticTexts.matching(sentence).firstMatch.waitForExistence(timeout: 15), app.debugDescription)
        let slot = app.descendants(matching: .any)["orb.empty"]
        XCTAssertTrue(slot.waitForExistence(timeout: 5), "an orb is drawn for an entity without a known identity:\n\(app.debugDescription)")
        sleep(1)
        let shot = XCUIScreen.main.screenshot()
        shoot(app, "entity-no-identity")
        let image = try XCTUnwrap(shot.image.cgImage)
        let scale = CGFloat(image.width) / app.frame.width
        let f = slot.frame, side = min(f.width, f.height) * 0.6
        let inner = CGRect(x: f.midX - side / 2, y: f.midY - side / 2, width: side, height: side)
        XCTAssertLessThan(colouredPixels(in: inner, of: image, scale: scale), 20, "the empty place carries a colour (a look was drawn)")
    }

    /// Pixels whose channels differ by more than 60 (a hue, not a grey) in `rect` (points).
    private func colouredPixels(in rect: CGRect, of image: CGImage, scale: CGFloat) -> Int {
        let r = CGRect(x: rect.minX * scale, y: rect.minY * scale, width: rect.width * scale, height: rect.height * scale).integral
            .intersection(CGRect(x: 0, y: 0, width: image.width, height: image.height))
        guard let crop = image.cropping(to: r) else { return 0 }
        let w = crop.width, h = crop.height
        var data = [UInt8](repeating: 0, count: w * h * 4)
        guard let ctx = CGContext(data: &data, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w * 4, space: CGColorSpaceCreateDeviceRGB(),
                                  bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return 0 }
        ctx.draw(crop, in: CGRect(x: 0, y: 0, width: w, height: h))
        return stride(from: 0, to: data.count, by: 4).filter { i in
            let c = [Int(data[i]), Int(data[i + 1]), Int(data[i + 2])]
            return c.max()! - c.min()! > 60
        }.count
    }

    @MainActor private func shoot(_ app: XCUIApplication, _ name: String) {
        let shot = XCTAttachment(screenshot: XCUIScreen.main.screenshot()); shot.name = name; shot.lifetime = .keepAlways; add(shot)
        if let dir = ProcessInfo.processInfo.environment["SHOTS_DIR"] {
            try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent(name + ".png"))
        }
    }
}
