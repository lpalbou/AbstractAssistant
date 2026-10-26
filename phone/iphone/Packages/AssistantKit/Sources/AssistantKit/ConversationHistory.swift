import Foundation
import AbstractGatewayClient

/// The iPhone's conversation list: Today, Yesterday, Earlier, and how long ago.
public struct ConversationHistorySection: Identifiable, Sendable {
    public let id: String
    public let sessions: [SessionSummary]
    public static func grouped(_ sessions: [SessionSummary], now: Date = Date(), calendar: Calendar = .current) -> [Self] {
        let today = calendar.startOfDay(for: now)
        let yesterday = calendar.date(byAdding: .day, value: -1, to: today) ?? today
        let sorted = sessions.sorted { ($0.updatedAt ?? .distantPast) > ($1.updatedAt ?? .distantPast) }
        return [("Today", sorted.filter { ($0.updatedAt ?? .distantPast) >= today }),
                ("Yesterday", sorted.filter { let d = $0.updatedAt ?? .distantPast; return d >= yesterday && d < today }),
                ("Earlier", sorted.filter { ($0.updatedAt ?? .distantPast) < yesterday })]
            .filter { !$0.1.isEmpty }.map { Self(id: $0.0, sessions: $0.1) }
    }
    public static func age(_ date: Date, now: Date = Date()) -> String {
        let seconds = max(0, now.timeIntervalSince(date))
        if seconds < 60 { return "just now" }
        if seconds < 3600 { return "\(Int(seconds / 60)) min ago" }
        if seconds < 86400 { return "\(Int(seconds / 3600)) h ago" }
        return "\(Int(seconds / 86400)) d ago"
    }
}
