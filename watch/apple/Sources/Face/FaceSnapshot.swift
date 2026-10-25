import Foundation
import WidgetKit

/// What the watch face shows of the assistant (the Assistant complication): your avatar (the orb
/// style you chose, drawn by the app), how many approvals and questions wait for you, the first of
/// them, the next automation to run and the automations' results not seen yet. The app writes it
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

    // MARK: Your avatar, as the app drew it

    /// What the avatar shows: at rest; news (results or messages not seen: the orb speaking, with
    /// a dot); needs you (approvals or questions waiting: the orb listening, with their number).
    var state: FaceState { needYou > 0 ? .needYou : (newResults > 0 ? .news : .rest) }

    private static let avatarIdKey = "face.avatar.id"

    /// The app group's folder, where the avatar's pictures live (the complication's own bundle
    /// cannot change after installation; the group is shared).
    private static var folder: URL? { FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: group) }

    private static func file(_ state: FaceState, mask: Bool) -> URL? {
        folder?.appending(path: "Library").appending(path: "face-avatar-\(state.rawValue)\(mask ? "-mask" : "").png")
    }

    /// Your avatar as a picture (PNG): the orb style chosen, in that state, drawn by the app and
    /// trimmed to the drawing. In colour, or (`mask`) its light as transparency, for a face that
    /// draws its complications in one tint. nil before the app has drawn it (the complication
    /// then shows the app's own orb).
    static func avatar(_ state: FaceState = .rest, mask: Bool = false) -> Data? { file(state, mask: mask).flatMap { try? Data(contentsOf: $0) } }

    /// What the avatar was drawn from (its orb style), to draw it again only when that changes.
    static var avatarId: String? { UserDefaults(suiteName: group)?.string(forKey: avatarIdKey) }

    /// Keeps new pictures of the avatar, one pair per state, and redraws the face.
    static func setAvatar(_ pictures: [FaceState: (color: Data, mask: Data)], id: String) {
        guard let first = file(.rest, mask: false) else { return }
        do {
            try FileManager.default.createDirectory(at: first.deletingLastPathComponent(), withIntermediateDirectories: true)
            for (state, p) in pictures {
                guard let colorFile = file(state, mask: false), let maskFile = file(state, mask: true) else { return }
                try p.color.write(to: colorFile, options: .atomic)
                try p.mask.write(to: maskFile, options: .atomic)
            }
        } catch { return }
        UserDefaults(suiteName: group)?.set(id, forKey: avatarIdKey)
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

/// The avatar's states on the face, each its own picture.
enum FaceState: String, CaseIterable, Sendable {
    case rest, news, needYou = "need"
}
