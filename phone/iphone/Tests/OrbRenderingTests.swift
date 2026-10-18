import XCTest
import SwiftUI
@testable import AbstractAssistantPhone

final class OrbRenderingTests: XCTestCase {
    @MainActor func testAccessibilityStopCannotBecomeMicrophoneOnRapidSecondActivation() {
        let control = OrbTouchControl()
        var stops = 0, microphoneStarts = 0
        control.cancelOnTouchDown = true
        control.onCancel = { stops += 1; control.cancelOnTouchDown = false }
        control.onTap = { microphoneStarts += 1 }
        XCTAssertTrue(control.accessibilityActivate())
        XCTAssertFalse(control.accessibilityActivate())
        XCTAssertEqual(stops, 1); XCTAssertEqual(microphoneStarts, 0)
        control.isEnabled = false
        XCTAssertFalse(control.accessibilityActivate())
    }

    @MainActor func testRenderedOrbListeningPlaybackAndStopStates() throws {
        for (name, energy, working) in [("Quiet orb", 0.05, false), ("Voice-reactive ribbons", 0.88, false), ("Agent stop square", 0.0, true)] {
            let renderer = ImageRenderer(content:
                AssistantOrb(size: 136, active: true, level: energy, working: working, animationTime: 2)
                    .frame(width: 240, height: 240).background(PhoneTheme.ground)
            )
            renderer.scale = 3
            let attachment = XCTAttachment(image: try XCTUnwrap(renderer.uiImage))
            attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
        }
        let rect = CGRect(x: 0, y: 0, width: 100, height: 100)
        let quiet = OrbContour(energy: 0, phase: 2, ribbon: true).path(in: rect)
        let loud = OrbContour(energy: 0.9, phase: 2, ribbon: true).path(in: rect)
        XCTAssertGreaterThan(loud.boundingRect.width, quiet.boundingRect.width + 4)
        XCTAssertGreaterThan(loud.boundingRect.height, quiet.boundingRect.height + 6)
        // The filled stop body must really morph, rather than keeping the circular silhouette.
        XCTAssertFalse(OrbContour().path(in: rect).contains(CGPoint(x: 10, y: 10)))
        XCTAssertTrue(OrbContour(squareness: 1).path(in: rect).contains(CGPoint(x: 10, y: 10)))
    }

    @MainActor func testMorphPresentationAndMidflightReversal() async throws {
        let state = OrbMorphState()
        let scene = try XCTUnwrap(UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first)
        let previous = scene.windows.first { $0.isKeyWindow }
        let window = UIWindow(windowScene: scene)
        window.frame = CGRect(x: 0, y: 0, width: 390, height: 260)
        window.rootViewController = UIHostingController(rootView: OrbMorphHarness(state: state))
        window.makeKeyAndVisible()
        defer { window.isHidden = true; previous?.makeKey() }
        try await Task.sleep(for: .milliseconds(150))
        func capture(_ name: String) -> UIImage {
            let image = UIGraphicsImageRenderer(bounds: window.bounds).image { _ in
                window.drawHierarchy(in: window.bounds, afterScreenUpdates: true)
            }
            let attachment = XCTAttachment(image: image)
            attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
            return image
        }
        let sphere = capture("Morph 00 — sphere")
        state.working = true
        try await Task.sleep(for: .milliseconds(40))
        _ = capture("Morph 00b — sphere starts opening")
        try await Task.sleep(for: .milliseconds(80))
        let entering = capture("Morph 01 — entering stop")
        try await Task.sleep(for: .milliseconds(180))
        _ = capture("Morph 02 — rounded square")
        try await Task.sleep(for: .milliseconds(500))
        let stop = capture("Morph 03 — stop")
        XCTAssertGreaterThan(try pixelDifference(sphere, entering), 0.05)
        XCTAssertGreaterThan(try pixelDifference(entering, stop), 0.05)
        state.working = false
        try await Task.sleep(for: .milliseconds(140))
        let leaving = capture("Morph 04 — returning to sphere")
        XCTAssertGreaterThan(try pixelDifference(stop, leaving), 0.05)
        // Interrupt the return: the same presentation must reverse without swapping identity.
        state.working = true
        try await Task.sleep(for: .milliseconds(150))
        _ = capture("Morph 05 — interrupted return")
        try await Task.sleep(for: .milliseconds(650))
        _ = capture("Morph 06 — stop restored")
        state.working = false
        try await Task.sleep(for: .milliseconds(800))
        let restored = capture("Morph 07 — sphere restored")
        // GPU gradient rasterization can differ slightly; compare pixels, not PNG compression.
        XCTAssertLessThan(try pixelDifference(sphere, restored), 0.5)
        for (index, level) in [0.2, 0.85, 0.1].enumerated() {
            state.level = level
            try await Task.sleep(for: .milliseconds(100))
            _ = capture("Voice envelope \(index) — level \(level)")
        }
    }

    private func pixelDifference(_ lhs: UIImage, _ rhs: UIImage) throws -> Double {
        func pixels(_ image: UIImage) throws -> [UInt8] {
            let image = try XCTUnwrap(image.cgImage)
            var bytes = [UInt8](repeating: 0, count: image.width * image.height * 4)
            let space = try XCTUnwrap(CGColorSpace(name: CGColorSpace.sRGB))
            try bytes.withUnsafeMutableBytes { buffer in
                let context = try XCTUnwrap(CGContext(data: buffer.baseAddress, width: image.width, height: image.height,
                                                      bitsPerComponent: 8, bytesPerRow: image.width * 4,
                                                      space: space, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue))
                context.draw(image, in: CGRect(x: 0, y: 0, width: image.width, height: image.height))
            }
            return bytes
        }
        let a = try pixels(lhs), b = try pixels(rhs)
        XCTAssertEqual(a.count, b.count)
        return zip(a, b).reduce(0.0) { $0 + Double(abs(Int($1.0) - Int($1.1))) } / Double(max(1, a.count))
    }

    @MainActor func testReducedMotionStopRemainsClearWithoutTimelineMotion() throws {
        let view = HStack(spacing: 30) {
            OrbArtwork(size: 68, stopProgress: 0, active: true, reduceMotion: true)
            OrbArtwork(size: 68, stopProgress: 1, active: true, reduceMotion: true)
        }.frame(width: 260, height: 150).background(PhoneTheme.ground)
        let renderer = ImageRenderer(content: view); renderer.scale = 3
        let attachment = XCTAttachment(image: try XCTUnwrap(renderer.uiImage))
        attachment.name = "Reduced Motion — stable sphere and stop"; attachment.lifetime = .keepAlways; add(attachment)
    }

}


@MainActor @Observable private final class OrbMorphState {
    var working = false
    var level: Double = 0
}

private struct OrbMorphHarness: View {
    var state: OrbMorphState
    var body: some View {
        HStack(spacing: 46) {
            AssistantOrb(size: 68, active: true, level: state.level, working: state.working, animationTime: 2)
            AssistantOrb(size: 136, active: true, level: state.level, working: state.working, animationTime: 2)
        }.frame(maxWidth: .infinity, maxHeight: .infinity).background(PhoneTheme.ground)
    }
}
