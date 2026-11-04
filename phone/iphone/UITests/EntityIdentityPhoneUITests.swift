import XCTest

/// The entity list shows each entity in its identity colour (framework ADR 0052). The demo's Castor
/// is amber (#f59e0b) and Nerin teal (#2dd4bf); the Assistant keeps the app's mint.
final class EntityIdentityPhoneUITests: XCTestCase {
    @MainActor func testEntityRowsShowTheirIdentityColour() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test"]; app.launch()
        let chooser = app.buttons["Choose who answers"]
        XCTAssertTrue(chooser.waitForExistence(timeout: 10)); chooser.tap()
        let castor = app.buttons["Talk with Castor"], nerin = app.buttons["Talk with Nerin"]
        XCTAssertTrue(castor.waitForExistence(timeout: 10), app.debugDescription)
        XCTAssertTrue(nerin.waitForExistence(timeout: 5), app.debugDescription)
        Thread.sleep(forTimeInterval: 0.7)   // the sheet settled
        let shot = app.screenshot()
        let attachment = XCTAttachment(screenshot: shot); attachment.name = "Entity list — identity colours"; attachment.lifetime = .keepAlways; add(attachment)
        if let dir = ProcessInfo.processInfo.environment["SHOTS_DIR"] {
            try shot.pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent("iphone-entity-list.png"))
        }
        let image = try XCTUnwrap(shot.image.cgImage)
        let scale = CGFloat(image.width) / app.frame.width
        XCTAssertGreaterThan(pixels(in: icon(of: castor), of: image, scale: scale) { r, g, b in r > 200 && (110...190).contains(g) && b < 80 }, 8,
                             "Castor's icon is not amber")
        XCTAssertGreaterThan(pixels(in: icon(of: nerin), of: image, scale: scale) { r, g, b in r < 110 && g > 170 && b > 150 }, 8,
                             "Nerin's icon is not teal")
    }

    /// The icon's square at the row's leading edge.
    @MainActor private func icon(of row: XCUIElement) -> CGRect {
        CGRect(x: row.frame.minX, y: row.frame.minY, width: 56, height: row.frame.height)
    }

    /// How many pixels in `rect` (points) match the colour test.
    private func pixels(in rect: CGRect, of image: CGImage, scale: CGFloat, _ match: (Int, Int, Int) -> Bool) -> Int {
        let r = CGRect(x: rect.minX * scale, y: rect.minY * scale, width: rect.width * scale, height: rect.height * scale).integral
            .intersection(CGRect(x: 0, y: 0, width: image.width, height: image.height))
        guard let crop = image.cropping(to: r) else { return 0 }
        let w = crop.width, h = crop.height
        var data = [UInt8](repeating: 0, count: w * h * 4)
        guard let ctx = CGContext(data: &data, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w * 4, space: CGColorSpaceCreateDeviceRGB(),
                                  bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return 0 }
        ctx.draw(crop, in: CGRect(x: 0, y: 0, width: w, height: h))
        return stride(from: 0, to: data.count, by: 4).filter { match(Int(data[$0]), Int(data[$0 + 1]), Int(data[$0 + 2])) }.count
    }
}
