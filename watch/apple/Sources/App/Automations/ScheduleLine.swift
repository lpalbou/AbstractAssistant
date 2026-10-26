import AbstractGatewayClient
import SwiftUI

/// "⟳ 44   🕐 12h   ➜ 6h": how many times an automation has run, how often it runs and when it
/// runs next, in one short line. A paused one says Paused. Rewritten every minute so "next" stays true.
struct ScheduleLine: View {
    let automation: AutomationSummary
    /// The run count on a line of its own (beside the page's Edit and Run now there is no room for one line).
    var stacked = false

    var body: some View {
        TimelineView(.periodic(from: .now, by: 60)) { ctx in
            if stacked {
                VStack(alignment: .leading, spacing: 3) { runs; schedule(ctx.date) }
            } else {
                HStack(spacing: 10) { runs; schedule(ctx.date) }
            }
        }
    }

    @ViewBuilder private var runs: some View {
        if let n = automation.occurrenceCount {
            SessionStat(symbol: "arrow.triangle.2.circlepath", value: "\(n)").accessibilityLabel("Ran \(n) \(n == 1 ? "time" : "times")")
        }
    }

    private func schedule(_ now: Date) -> some View {
        HStack(spacing: 10) {
            if automation.status == "active" {
                if let i = Self.interval(automation) { SessionStat(symbol: "clock", value: i) }
                if let n = Self.nextIn(automation.nextFireAt, now: now) { SessionStat(symbol: "arrow.forward.circle", value: n) }
            } else {
                SessionStat(symbol: automation.status == "paused" ? "pause.circle" : "stop.circle",
                            value: automation.status == "paused" ? "Paused" : "Ended")
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

    /// How often an automation can run, shortest first (a new automation, Edit).
    static let presets = ["30s", "1m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "24h", "48h", "7d"]

    /// "30s" → 30, "5m" → 300, "2h" → 7200, "1d" → 86400 (the gateway's `^[1-9][0-9]*[smhd]$`).
    static func seconds(_ every: String) -> Int? {
        guard let unit = every.last, let n = Int(every.dropLast()), n > 0 else { return nil }
        switch unit {
        case "s": return n
        case "m": return n * 60
        case "h": return n * 3600
        case "d": return n * 86_400
        default: return nil
        }
    }

    /// In its largest whole unit: "60s" → "1m", "90m" → "90m", "120m" → "2h", "24h" → "1d", "48h" → "2d".
    static func compact(_ every: String) -> String {
        guard let s = seconds(every) else { return every }
        if s % 86_400 == 0 { return "\(s / 86_400)d" }
        if s % 3600 == 0 { return "\(s / 3600)h" }
        if s % 60 == 0 { return "\(s / 60)m" }
        return "\(s)s"
    }

    /// The same interval written two ways ("60s" and "1m").
    static func same(_ a: String, _ b: String) -> Bool {
        guard let x = seconds(a), let y = seconds(b) else { return a == b }
        return x == y
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
