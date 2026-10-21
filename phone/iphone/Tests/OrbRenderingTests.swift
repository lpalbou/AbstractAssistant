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
        func snapshot() -> UIImage {
            let image = UIGraphicsImageRenderer(bounds: window.bounds).image { _ in
                window.drawHierarchy(in: window.bounds, afterScreenUpdates: true)
            }
            return image
        }
        func record(_ image: UIImage, _ name: String) {
            let attachment = XCTAttachment(image: image)
            attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
        }
        func capture(_ name: String) -> UIImage {
            let image = snapshot()
            record(image, name)
            return image
        }
        @MainActor func changedFrame(from baseline: UIImage, name: String) async throws -> UIImage {
            let deadline = ContinuousClock.now.advanced(by: .seconds(3))
            var image = baseline
            repeat {
                try await Task.sleep(for: .milliseconds(20))
                image = snapshot()
                if try pixelDifference(baseline, image) > 0.05 {
                    record(image, name)
                    return image
                }
            } while ContinuousClock.now < deadline
            XCTFail("The orb did not present a changed animation frame within three seconds")
            record(image, name)
            return image
        }
        let sphere = capture("Morph 00 — sphere")
        state.working = true
        try await Task.sleep(for: .milliseconds(40))
        _ = capture("Morph 00b — sphere starts opening")
        let entering = try await changedFrame(from: sphere, name: "Morph 01 — entering stop")
        try await Task.sleep(for: .milliseconds(180))
        _ = capture("Morph 02 — rounded square")
        try await Task.sleep(for: .milliseconds(2200))
        let stop = capture("Morph 03 — stop")
        XCTAssertGreaterThan(try pixelDifference(sphere, stop), 0.05)
        XCTAssertGreaterThan(try pixelDifference(sphere, entering), 0.05)
        XCTAssertGreaterThan(try pixelDifference(entering, stop), 0.05)
        // Snapshot scheduling may skip intermediate native frames on a busy simulator.
        // Sample the production artwork directly to prove its middle and reverse trajectory.
        func artwork(_ progress: Double) throws -> UIImage {
            let renderer = ImageRenderer(content: HStack(spacing: 46) {
                OrbArtwork(size: 68, stopProgress: progress, active: true, animationTime: 2, paused: true)
                OrbArtwork(size: 136, stopProgress: progress, active: true, animationTime: 2, paused: true)
            }.frame(width: 390, height: 260).background(PhoneTheme.ground))
            renderer.scale = 2
            return try XCTUnwrap(renderer.uiImage)
        }
        let start = try artwork(0), end = try artwork(1)
        var previousFrame = start
        for (index, progress) in [0.7, 0.35, 0.65].enumerated() {
            let frame = try artwork(progress)
            XCTAssertGreaterThan(try pixelDifference(start, frame), 0.05)
            XCTAssertGreaterThan(try pixelDifference(end, frame), 0.05)
            XCTAssertGreaterThan(try pixelDifference(previousFrame, frame), 0.05)
            record(frame, "Sampled morph reversal \(index) — progress \(progress)")
            previousFrame = frame
        }
        state.working = false
        // Simulator scheduling can defer the first presentation beyond a fixed wall-clock sleep.
        let leaving = try await changedFrame(from: stop, name: "Morph 04 — returning to sphere")
        XCTAssertGreaterThan(try pixelDifference(stop, leaving), 0.05)
        XCTAssertGreaterThan(try pixelDifference(sphere, leaving), 0.05)
        // Interrupt the return on the same view identity, before its two-second test animation ends.
        state.working = true
        try await Task.sleep(for: .milliseconds(150))
        _ = capture("Morph 05 — interrupted return")
        try await Task.sleep(for: .milliseconds(2200))
        _ = capture("Morph 06 — stop restored")
        state.working = false
        try await Task.sleep(for: .milliseconds(2200))
        let restored = capture("Morph 07 — sphere restored")
        // GPU gradient rasterization can differ slightly; compare pixels, not PNG compression.
        XCTAssertLessThan(try pixelDifference(sphere, restored), 0.5)
        for (index, level) in [0.2, 0.85, 0.1].enumerated() {
            state.level = level
            try await Task.sleep(for: .milliseconds(100))
            _ = capture("Voice envelope \(index) — level \(level)")
        }
    }

    @MainActor func testSpeechAndGuardGeometryMorphsMovesAndRespectsReducedMotion() throws {
        func render(_ stop: Double, _ geo: Double, _ hand: Double, time: Double = 2, reduced: Bool = false) throws -> UIImage {
            let renderer = ImageRenderer(content: HStack(spacing: 46) {
                OrbArtwork(size: 68, stopProgress: stop, geodesicProgress: geo, approvalProgress: hand, active: true, animationTime: time, reduceMotion: reduced, paused: true)
                OrbArtwork(size: 136, stopProgress: stop, geodesicProgress: geo, approvalProgress: hand, active: true, animationTime: time, reduceMotion: reduced, paused: true)
            }.frame(width: 390, height: 260).background(PhoneTheme.ground))
            renderer.scale = 3
            return try XCTUnwrap(renderer.uiImage)
        }
        func record(_ image: UIImage, _ name: String) {
            let attachment = XCTAttachment(image: image); attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
        }
        let sphere = try render(0, 0, 0), stop = try render(1, 0, 0)
        let globe = try render(0, 1, 0), hand = try render(0, 0, 1)
        record(globe, "Speech — rotating geodesic at 68 and 136 points")
        record(hand, "Approval — orange cord hand at 68 and 136 points")
        XCTAssertGreaterThan(try pixelDifference(sphere, globe), 0.5)
        XCTAssertGreaterThan(try pixelDifference(stop, hand), 0.5)
        for (name, source, target, frame) in [
            ("Stop to guard", stop, hand, try render(0.5, 0, 0.5)),
            ("Sphere to speech", sphere, globe, try render(0, 0.5, 0)),
            ("Speech to guard", globe, hand, try render(0, 0.5, 0.5)),
            ("Guard interrupted return", stop, hand, try render(0.7, 0, 0.3))
        ] {
            XCTAssertGreaterThan(try pixelDifference(source, frame), 0.05, name)
            XCTAssertGreaterThan(try pixelDifference(target, frame), 0.05, name)
            record(frame, name)
        }
        XCTAssertGreaterThan(try pixelDifference(globe, render(0, 1, 0, time: 2.3)), 0.05)
        XCTAssertGreaterThan(try pixelDifference(hand, render(0, 0, 1, time: 2.3)), 0.05)
        for (geo, guardHand) in [(1.0, 0.0), (0.0, 1.0)] {
            let frozen = try render(0, geo, guardHand, time: 2, reduced: true)
            XCTAssertEqual(try pixelDifference(frozen, render(0, geo, guardHand, time: 8, reduced: true)), 0)
            record(frozen, "Reduced Motion — speech \(geo), guard \(guardHand)")
        }
    }

    private func pixelDifference(_ lhs: UIImage, _ rhs: UIImage) throws -> Double {
        func pixels(_ image: UIImage) throws -> [UInt8] {
            let image = try XCTUnwrap(image.cgImage)
            // A view-sized comparison retains visual differences without millions of
            // unoptimized byte operations blocking the UI thread between animation frames.
            let width = min(390, image.width), height = image.height * width / image.width
            var bytes = [UInt8](repeating: 0, count: width * height * 4)
            let space = try XCTUnwrap(CGColorSpace(name: CGColorSpace.sRGB))
            try bytes.withUnsafeMutableBytes { buffer in
                let context = try XCTUnwrap(CGContext(data: buffer.baseAddress, width: width, height: height,
                                                      bitsPerComponent: 8, bytesPerRow: width * 4,
                                                      space: space, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue))
                context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
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
            AssistantOrb(size: 68, active: true, level: state.level, working: state.working, animationTime: 2, morphDuration: 2)
            AssistantOrb(size: 136, active: true, level: state.level, working: state.working, animationTime: 2, morphDuration: 2)
        }.frame(maxWidth: .infinity, maxHeight: .infinity).background(PhoneTheme.ground)
    }
}
