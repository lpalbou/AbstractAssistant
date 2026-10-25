import Foundation

/// The automations' names as the app last read them, kept in the app group so the notification
/// service extension can say "Morning digest has a result" (the event carries the id only).
public enum AutomationNameBook {
    static let key = "push.automation.names"

    public static func defaults() -> UserDefaults {
        UserDefaults(suiteName: SharedSignInStore.appGroup) ?? .standard
    }

    public static func remember(_ names: [String: String], in d: UserDefaults = defaults()) {
        var book = d.dictionary(forKey: key) as? [String: String] ?? [:]
        var changed = false
        for (id, name) in names where !name.isEmpty && book[id] != name { book[id] = name; changed = true }
        if changed { d.set(book, forKey: key) }
    }

    public static func name(_ id: String, in d: UserDefaults = defaults()) -> String? {
        (d.dictionary(forKey: key) as? [String: String])?[id]
    }
}
