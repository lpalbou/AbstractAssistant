import Foundation
import WatchKit

/// Keeps the app running while the wrist is down for as long as the assistant is listening,
/// working on an Ask or speaking. Without it watchOS suspends the app a few seconds after the screen
/// dims, and the voice stops mid-sentence (measured 2026-10-17 on a Series 11: the scene went
/// inactive at 4:37:14, a 14.6 s chunk started at 4:37:15 and never finished). An extended runtime
/// session (`WKBackgroundModes: self-care`, up to 10 minutes) keeps it alive; it can only start
/// while the app is active, so it is taken when a turn starts (a tap) and released when it ends.
@MainActor
final class RuntimeKeeper: NSObject {
    static let shared = RuntimeKeeper()

    private var holders: Set<String> = []
    private var session: WKExtendedRuntimeSession?

    /// `who` holds the app awake ("listen", "ask", "speak"); idempotent per holder.
    func hold(_ who: String) {
        holders.insert(who)
        guard session == nil || session?.state == .invalid else { return }
        guard WKApplication.shared().applicationState == .active else {
            trace("not started for \(who): the app is not active")
            return
        }
        let s = WKExtendedRuntimeSession()
        s.delegate = self
        s.start()
        session = s
        trace("session started for \(who)")
    }

    func release(_ who: String) {
        holders.remove(who)
        guard holders.isEmpty, let s = session else { return }
        if s.state != .invalid { s.invalidate() }   // including a session still starting
        session = nil
        trace("session ended (\(who) was the last holder)")
    }

    private func trace(_ s: String) {
        #if DEBUG
        print("keeper \(Date().formatted(date: .omitted, time: .standard)) \(s)")
        #endif
    }
}

extension RuntimeKeeper: WKExtendedRuntimeSessionDelegate {
    nonisolated func extendedRuntimeSessionDidStart(_ extendedRuntimeSession: WKExtendedRuntimeSession) {
        let id = ObjectIdentifier(extendedRuntimeSession)
        Task { @MainActor in
            self.trace("session running")
            // Everyone let go while it was starting: end it now rather than in 10 minutes.
            if self.holders.isEmpty, let s = self.session, ObjectIdentifier(s) == id { s.invalidate(); self.session = nil }
        }
    }

    nonisolated func extendedRuntimeSessionWillExpire(_ extendedRuntimeSession: WKExtendedRuntimeSession) {
        Task { @MainActor in self.trace("session about to expire") }
    }

    nonisolated func extendedRuntimeSession(_ extendedRuntimeSession: WKExtendedRuntimeSession,
                                            didInvalidateWith reason: WKExtendedRuntimeSessionInvalidationReason, error: Error?) {
        let id = ObjectIdentifier(extendedRuntimeSession)
        let why = "reason \(reason.rawValue) \(error.map { String(describing: $0) } ?? "")"
        Task { @MainActor in
            self.trace("session invalidated: \(why)")
            if let s = self.session, ObjectIdentifier(s) == id { self.session = nil }
        }
    }
}
