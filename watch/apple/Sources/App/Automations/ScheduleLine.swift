import AbstractGatewayClient
import SwiftUI

/// "🕐 12h   ➜ 6h": how often an automation runs and when it runs next, in one short line.
/// A paused one says Paused. Rewritten every minute so "next" stays true.
struct ScheduleLine: View {
    let automation: AutomationSummary

    var body: some View {
        TimelineView(.periodic(from: .now, by: 60)) { ctx in
            HStack(spacing: 12) {
                if automation.status == "active" {
                    if let i = Self.interval(automation) { SessionStat(symbol: "clock", value: i) }
                    if let n = Self.nextIn(automation.nextFireAt, now: ctx.date) { SessionStat(symbol: "arrow.forward.circle", value: n) }
                } else {
                    SessionStat(symbol: automation.status == "paused" ? "pause.circle" : "stop.circle",
                                value: automation.status == "paused" ? "Paused" : "Ended")
                }
            }
        }
    }

    /// "12h", "30m", "1d"; a calendar rule as "Daily", "Weekly", "Monthly", "Once"; an email trigger as "Email".
    static func interval(_ a: AutomationSummary) -> String? {
        if let every = a.every { return compact(every) }
        switch a.triggerConfig?["kind"]?.stringValue {
        case "daily": return "Daily"
        case "weekly": return "Weekly"
        case "monthly": return "Monthly"
        case "once": return "Once"
        default: return (a.triggerSource ?? "").hasPrefix("email") ? "Email" : nil
        }
    }

    /// "90m" → "90m", "120m" → "2h", "24h" → "1d", "48h" → "2d".
    static func compact(_ every: String) -> String {
        guard let unit = every.last, let n = Int(every.dropLast()), n > 0 else { return every }
        switch unit {
        case "m" where n % 1440 == 0: return "\(n / 1440)d"
        case "m" where n % 60 == 0: return "\(n / 60)h"
        case "h" where n % 24 == 0: return "\(n / 24)d"
        default: return every
        }
    }

    /// Time until the next run in one unit: "now", "45m", "6h", "3d".
    static func nextIn(_ iso: String?, now: Date = Date()) -> String? {
        guard let iso, let d = ISO8601.date(iso) else { return nil }
        let s = Int(d.timeIntervalSince(now))
        if s <= 30 { return "now" }
        if s < 3600 { return "\(max(1, s / 60))m" }
        if s < 2 * 86_400 { return "\(s / 3600)h" }
        return "\(s / 86_400)d"
    }
}
