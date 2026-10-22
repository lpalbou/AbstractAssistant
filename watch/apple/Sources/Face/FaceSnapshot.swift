import Foundation
import WidgetKit

/// What the watch face shows of the assistant (the Assistant complication, the app's blue orb): how
/// many approvals and questions wait for you, the first of them, the next automation to run and the automations' results not seen yet. The app writes it
/// (and the background check, when the app is closed); the complication reads it. It lives in the
/// app group both share.
struct FaceSnapshot: Codable, Equatable, Sendable {
    var needYou = 0
    var firstNeed: String?
    var nextName: String?
    var nextAt: Date?
    var newResults = 0

    static let group = "group.ai.abstractframework.assistant"
    static let kind = "Avatar"
    private static let key = "face.snapshot"

    /// What the face shows in the gallery, before the app has said anything.
    static let sample = FaceSnapshot(needYou: 2, firstNeed: "Send an email?", nextName: "Morning digest",
                                     nextAt: Date().addingTimeInterval(2 * 3600), newResults: 1)

    static func read() -> FaceSnapshot {
        guard let data = UserDefaults(suiteName: group)?.data(forKey: key),
              let s = try? JSONDecoder().decode(FaceSnapshot.self, from: data) else { return FaceSnapshot() }
        return s
    }

    /// Changes it and redraws the face, only when something it shows changed (a redraw costs the
    /// face's daily budget).
    static func update(_ change: (inout FaceSnapshot) -> Void) {
        var s = read()
        let before = s
        change(&s)
        guard s != before, let data = try? JSONEncoder().encode(s) else { return }
        UserDefaults(suiteName: group)?.set(data, forKey: key)
        WidgetCenter.shared.reloadTimelines(ofKind: kind)
    }

    /// How long until then, in one unit: "now", "45m", "6h", "3d".
    static func inShort(_ at: Date, from now: Date) -> String {
        let s = Int(at.timeIntervalSince(now))
        if s <= 30 { return "now" }
        if s < 3600 { return "\(max(1, s / 60))m" }
        if s < 2 * 86_400 { return "\(s / 3600)h" }
        return "\(s / 86_400)d"
    }

    /// The next automation to run, the next one after `now`.
    func next(after now: Date) -> (name: String, at: Date)? {
        guard let nextName, let nextAt, nextAt > now else { return nil }
        return (nextName, nextAt)
    }
}
