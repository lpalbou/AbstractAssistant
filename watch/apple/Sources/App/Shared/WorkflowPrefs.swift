import AbstractGatewayClient
import Foundation

/// A workflow chosen on this watch, by bundle (its newest version on the gateway runs). The empty
/// bundle is the gateway's default agent.
struct WorkflowPick: Codable, Hashable {
    var bundleId: String
    var interface: String
    static let gatewayDefault = WorkflowPick(bundleId: "", interface: WorkflowChoice.agentInterface)
    var isGatewayDefault: Bool { bundleId.isEmpty }
    init(bundleId: String, interface: String) { self.bundleId = bundleId; self.interface = interface }
    init(_ w: WorkflowChoice) { self.init(bundleId: w.bundleId, interface: w.interface) }
}

/// The workflow chosen for new conversations (Settings → Tools) and for each conversation (the
/// tools icon on the orb page). Kept on this watch, like the tools.
enum WorkflowPrefs {
    private static let defaultKey = "workflow.default", sessionsKey = "workflow.sessions", orderKey = "workflow.sessions.order"

    static var defaultPick: WorkflowPick {
        get { load(defaultKey) ?? .gatewayDefault }
        set { save(newValue, defaultKey) }
    }

    /// This conversation's choice; nil when none was made here.
    static func session(_ id: String) -> WorkflowPick? { (load(sessionsKey) as [String: WorkflowPick]?)?[id] }

    static func setSession(_ id: String, _ pick: WorkflowPick?) {
        var all: [String: WorkflowPick] = load(sessionsKey) ?? [:]
        var order = UserDefaults.standard.stringArray(forKey: orderKey) ?? []
        order.removeAll { $0 == id }
        all[id] = pick
        if pick != nil { order.append(id) }
        while order.count > ToolPrefs.keptSessions { all[order.removeFirst()] = nil }
        save(all, sessionsKey)
        UserDefaults.standard.set(order, forKey: orderKey)
    }

    #if DEBUG
    static func reset() { [defaultKey, sessionsKey, orderKey].forEach(UserDefaults.standard.removeObject(forKey:)) }
    #endif

    private static func load<T: Decodable>(_ key: String) -> T? {
        UserDefaults.standard.data(forKey: key).flatMap { try? JSONDecoder().decode(T.self, from: $0) }
    }
    private static func save<T: Encodable>(_ value: T, _ key: String) {
        if let data = try? JSONEncoder().encode(value) { UserDefaults.standard.set(data, forKey: key) }
    }
}
