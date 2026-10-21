import SwiftUI

/// Normal taps activate; touch-down cancels an existing local voice turn before its deadline.
struct OrbTouchSurface: UIViewRepresentable {
    var enabled: Bool
    var label: String
    var working = false
    var hint: String? = nil
    var cancelActionLabel = "Cancel voice message"
    var cancelOnTouchDown: Bool
    var onTap: () -> Void
    var onCancel: () -> Void
    func makeUIView(context: Context) -> OrbTouchControl { OrbTouchControl() }
    func updateUIView(_ view: OrbTouchControl, context: Context) {
        view.isEnabled = enabled; view.accessibilityLabel = label; view.accessibilityIdentifier = "voice.orb"
        view.accessibilityHint = hint ?? (working ? "Stops the current agent response." : "Speak, then review the transcription before sending. Tap again to cancel.")
        view.accessibilityTraits = enabled ? [.button] : [.button, .notEnabled]
        view.accessibilityCustomActions = !working && cancelOnTouchDown ? [UIAccessibilityCustomAction(name: cancelActionLabel, actionHandler: { [weak view] _ in view?.onCancel?(); return true })] : nil
        view.cancelOnTouchDown = cancelOnTouchDown; view.onTap = onTap; view.onCancel = onCancel
    }
}

final class OrbTouchControl: UIControl {
    var onTap: (() -> Void)?
    var onCancel: (() -> Void)?
    var cancelOnTouchDown = false
    private var ownsTouch = false
    private var consumed = false
    private var trackingAction: (() -> Void)?
    private var lastCancellation: TimeInterval = -.infinity
    override init(frame: CGRect) {
        super.init(frame: frame); backgroundColor = .clear; isAccessibilityElement = true; accessibilityTraits = .button
    }
    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }
    override func beginTracking(_ touch: UITouch, with event: UIEvent?) -> Bool {
        guard isEnabled, touch.timestamp - lastCancellation > 0.45 else { return false }; ownsTouch = true; consumed = cancelOnTouchDown
        // Preserve the action under this finger if the orb changes state before release.
        trackingAction = consumed ? nil : onTap
        if consumed { lastCancellation = touch.timestamp; onCancel?() }; return true
    }
    override func continueTracking(_ touch: UITouch, with event: UIEvent?) -> Bool {
        guard bounds.insetBy(dx: -18, dy: -18).contains(touch.location(in: self)) else { ownsTouch = false; return false }
        return ownsTouch
    }
    override func endTracking(_ touch: UITouch?, with event: UIEvent?) {
        let action = trackingAction; trackingAction = nil
        guard ownsTouch else { return }; ownsTouch = false
        if !consumed, isEnabled, let touch, bounds.insetBy(dx: -18, dy: -18).contains(touch.location(in: self)) { action?() }
    }
    override func cancelTracking(with event: UIEvent?) { ownsTouch = false; trackingAction = nil }
    override func accessibilityActivate() -> Bool {
        let now = ProcessInfo.processInfo.systemUptime
        guard isEnabled, now - lastCancellation > 0.45 else { return false }
        if cancelOnTouchDown { lastCancellation = now; onCancel?() } else { onTap?() }; return true
    }
}
