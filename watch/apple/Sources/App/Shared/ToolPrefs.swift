import AbstractGatewayClient
import Foundation

/// The tools chosen on this watch (Settings → Tools, and the tools icon on the orb page): defaults
/// for new conversations, and each conversation's own changes on top of them. Kept on this watch;
/// the gateway's settings are not changed. A tool with no choice follows the gateway.
enum ToolPrefs {
    private static let defaultsKey = "tools.defaults", sessionsKey = "tools.sessions", orderKey = "tools.sessions.order"
    /// Conversations whose changes are kept (the oldest are forgotten).
    static let keptSessions = 100

    static var defaults: [String: ToolMode] {
        get { load(defaultsKey) ?? [:] }
        set { save(newValue, defaultsKey) }
    }

    static func session(_ id: String) -> [String: ToolMode] { (load(sessionsKey) as [String: [String: ToolMode]]?)?[id] ?? [:] }

    static func setSession(_ id: String, _ modes: [String: ToolMode]) {
        var all: [String: [String: ToolMode]] = load(sessionsKey) ?? [:]
        var order = UserDefaults.standard.stringArray(forKey: orderKey) ?? []
        order.removeAll { $0 == id }
        if modes.isEmpty { all[id] = nil } else { all[id] = modes; order.append(id) }
        while order.count > keptSessions { all[order.removeFirst()] = nil }
        save(all, sessionsKey)
        UserDefaults.standard.set(order, forKey: orderKey)
    }

    #if DEBUG
    /// Tests start from the gateway's tools (`--reset-tools`).
    static func reset() { [defaultsKey, sessionsKey, orderKey].forEach(UserDefaults.standard.removeObject(forKey:)) }
    #endif

    /// A conversation in use: its changes are kept the longest.
    static func touch(_ id: String) {
        var order = UserDefaults.standard.stringArray(forKey: orderKey) ?? []
        guard let i = order.firstIndex(of: id) else { return }
        order.remove(at: i); order.append(id)
        UserDefaults.standard.set(order, forKey: orderKey)
    }

    private static func load<T: Decodable>(_ key: String) -> T? {
        UserDefaults.standard.data(forKey: key).flatMap { try? JSONDecoder().decode(T.self, from: $0) }
    }
    private static func save<T: Encodable>(_ value: T, _ key: String) {
        if let data = try? JSONEncoder().encode(value) { UserDefaults.standard.set(data, forKey: key) }
    }
}
