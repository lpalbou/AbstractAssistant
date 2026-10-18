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
}
