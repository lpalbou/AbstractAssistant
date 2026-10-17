import SwiftUI

/// Real touch-down/up/cancel events: a grace-cancel wins before the finger lifts.
struct OrbTouchSurface: UIViewRepresentable {
    var enabled: Bool
    var label: String
    var onPress: () -> Void
    var onRelease: () -> Void
    var onCancel: () -> Void
    var onAccessibleActivate: () -> Void
    func makeUIView(context: Context) -> OrbTouchControl { OrbTouchControl() }
    func updateUIView(_ view: OrbTouchControl, context: Context) {
        if !enabled && view.isTracking { view.cancelCapture() }
        view.isEnabled = enabled; view.accessibilityLabel = label; view.accessibilityIdentifier = "voice.orb"
        view.accessibilityHint = "Hold while speaking. Release to send after three seconds. Touch again during the countdown to cancel. With VoiceOver, double-tap to start or finish."
        view.onPress = onPress; view.onRelease = onRelease; view.onCancel = onCancel; view.onAccessibleActivate = onAccessibleActivate
    }
}

final class OrbTouchControl: UIControl {
    var onPress: (() -> Void)?
    var onRelease: (() -> Void)?
    var onCancel: (() -> Void)?
    var onAccessibleActivate: (() -> Void)?
    private var ownsTouch = false
    override init(frame: CGRect) {
        super.init(frame: frame); backgroundColor = .clear; isAccessibilityElement = true; accessibilityTraits = .button
        accessibilityCustomActions = [UIAccessibilityCustomAction(name: "Cancel voice message", actionHandler: { [weak self] _ in self?.onCancel?(); return true })]
    }
    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }
    override func beginTracking(_ touch: UITouch, with event: UIEvent?) -> Bool {
        guard isEnabled else { return false }; ownsTouch = true; onPress?(); return true
    }
    override func continueTracking(_ touch: UITouch, with event: UIEvent?) -> Bool {
        guard bounds.insetBy(dx: -18, dy: -18).contains(touch.location(in: self)) else { cancelCapture(); return false }
        return ownsTouch
    }
    override func endTracking(_ touch: UITouch?, with event: UIEvent?) {
        guard ownsTouch else { return }; ownsTouch = false
        if let touch, bounds.insetBy(dx: -18, dy: -18).contains(touch.location(in: self)) { onRelease?() } else { onCancel?() }
    }
    override func cancelTracking(with event: UIEvent?) { cancelCapture() }
    func cancelCapture() { guard ownsTouch else { return }; ownsTouch = false; onCancel?() }
    override func accessibilityActivate() -> Bool { guard isEnabled else { return false }; onAccessibleActivate?(); return true }
}
