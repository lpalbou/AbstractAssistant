import AbstractGatewayClient
import Foundation

/// The watch face's view of the gateway: what the app (or its background check) has just read.
extension FaceSnapshot {
    /// The approvals and questions waiting for you.
    static func waits(_ waits: [Wait]) {
        update { $0.needYou = waits.count; $0.firstNeed = waits.first?.headline }
    }

    /// The next active automation to run, and the results not seen yet.
    static func automations(_ list: [AutomationSummary], now: Date = Date()) {
        let next = list.filter { $0.status == "active" }
            .compactMap { a in a.nextFireAt.flatMap(ISO8601.date).map { (name: a.name ?? "Automation", at: $0) } }
            .filter { $0.at > now }
            .min { $0.at < $1.at }
        update {
            $0.nextName = next?.name; $0.nextAt = next?.at
            $0.newResults = list.reduce(0) { $0 + ($1.attention?.unseenCount ?? 0) }
        }
    }
}
