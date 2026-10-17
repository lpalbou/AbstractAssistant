import SwiftUI

/// A screen-owned recognizer dismisses editing without swallowing the outside control's tap.
struct OutsideInputDismissal: UIViewControllerRepresentable {
    var focused: Bool
    var dismiss: () -> Void
    func makeUIViewController(context: Context) -> OutsideInputController { OutsideInputController() }
    func updateUIViewController(_ controller: OutsideInputController, context: Context) {
        controller.focused = focused; controller.onDismiss = dismiss; controller.installIfNeeded()
    }
    static func dismantleUIViewController(_ controller: OutsideInputController, coordinator: ()) { controller.uninstall() }
}

final class OutsideInputController: UIViewController, UIGestureRecognizerDelegate {
    var focused = false
    var onDismiss: (() -> Void)?
    private weak var host: UIView?
    private lazy var tap: UITapGestureRecognizer = {
        let tap = UITapGestureRecognizer(target: self, action: #selector(outsideTap))
        tap.cancelsTouchesInView = false; tap.delaysTouchesBegan = false; tap.delaysTouchesEnded = false; tap.delegate = self
        return tap
    }()
    override func loadView() { view = UIView(); view.isUserInteractionEnabled = false }
    override func didMove(toParent parent: UIViewController?) { super.didMove(toParent: parent); installIfNeeded() }
    override func viewDidAppear(_ animated: Bool) { super.viewDidAppear(animated); installIfNeeded() }
    override func viewWillDisappear(_ animated: Bool) { uninstall(); super.viewWillDisappear(animated) }
    func installIfNeeded() {
        guard isViewLoaded, view.window != nil, let root = parent?.view else { return }
        if host !== root { uninstall(); root.addGestureRecognizer(tap); host = root }
    }
    func uninstall() { host?.removeGestureRecognizer(tap); host = nil }
    @objc private func outsideTap() {
        guard focused else { return }
        // Let Send/menu/orb actions finish before editing changes can reflow their hit area.
        DispatchQueue.main.async { [weak self] in self?.host?.endEditing(true); self?.onDismiss?() }
    }
    func gestureRecognizer(_ gestureRecognizer: UIGestureRecognizer, shouldReceive touch: UITouch) -> Bool {
        guard focused, view.window != nil else { return false }
        var touched = touch.view
        while let candidate = touched {
            let name = String(describing: type(of: candidate))
            if candidate is any UITextInput || name.contains("TextSelection") || name.contains("TextEditing") { return false }
            if candidate === host { break }; touched = candidate.superview
        }
        return true
    }
    func gestureRecognizer(_ gestureRecognizer: UIGestureRecognizer, shouldRecognizeSimultaneouslyWith otherGestureRecognizer: UIGestureRecognizer) -> Bool { true }
}
