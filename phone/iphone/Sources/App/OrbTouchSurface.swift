import SwiftUI

/// Normal taps activate; touch-down cancels an existing local voice turn before its deadline.
struct OrbTouchSurface: UIViewRepresentable {
    var enabled: Bool
    var label: String
    var cancelOnTouchDown: Bool
    var onTap: () -> Void
    var onCancel: () -> Void
    func makeUIView(context: Context) -> OrbTouchControl { OrbTouchControl() }
    func updateUIView(_ view: OrbTouchControl, context: Context) {
        view.isEnabled = enabled; view.accessibilityLabel = label; view.accessibilityIdentifier = "voice.orb"
        view.accessibilityHint = "Tap to listen. After speaking, three seconds of silence sends your message. Tap again before sending to cancel."
        view.cancelOnTouchDown = cancelOnTouchDown; view.onTap = onTap; view.onCancel = onCancel
    }
}

final class OrbTouchControl: UIControl {
    var onTap: (() -> Void)?
    var onCancel: (() -> Void)?
    var cancelOnTouchDown = false
    private var ownsTouch = false
    private var consumed = false
    override init(frame: CGRect) {
        super.init(frame: frame); backgroundColor = .clear; isAccessibilityElement = true; accessibilityTraits = .button
        accessibilityCustomActions = [UIAccessibilityCustomAction(name: "Cancel voice message", actionHandler: { [weak self] _ in self?.onCancel?(); return true })]
    }
    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }
    override func beginTracking(_ touch: UITouch, with event: UIEvent?) -> Bool {
        guard isEnabled else { return false }; ownsTouch = true; consumed = cancelOnTouchDown
        if consumed { onCancel?() }; return true
    }
    override func continueTracking(_ touch: UITouch, with event: UIEvent?) -> Bool {
        guard bounds.insetBy(dx: -18, dy: -18).contains(touch.location(in: self)) else { ownsTouch = false; return false }
        return ownsTouch
    }
    override func endTracking(_ touch: UITouch?, with event: UIEvent?) {
        guard ownsTouch else { return }; ownsTouch = false
        if !consumed, isEnabled, let touch, bounds.insetBy(dx: -18, dy: -18).contains(touch.location(in: self)) { onTap?() }
    }
    override func cancelTracking(with event: UIEvent?) { ownsTouch = false }
    override func accessibilityActivate() -> Bool {
        guard isEnabled else { return false }
        if cancelOnTouchDown { onCancel?() } else { onTap?() }; return true
    }
}
