import SwiftUI
import AssistantKit
import AbstractGatewayClient

/// A quiet summary until opened; all detail comes from durable runtime events.
struct RunActivityPanel: View {
    @Environment(AssistantStore.self) private var store
    var review: (Wait) -> Void
    @State private var expanded = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Button {
                withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.22)) { expanded.toggle() }
            } label: {
                HStack(alignment: .center, spacing: 11) {
                    Image(systemName: symbol).font(.subheadline.weight(.medium)).foregroundStyle(tint)
                        .frame(width: 22)
                    VStack(alignment: .leading, spacing: 4) {
                        Text(title).font(.subheadline.weight(.medium)).foregroundStyle(PhoneTheme.ink)
                            .accessibilityIdentifier("activity.status")
                        Text(counts).font(.caption).foregroundStyle(PhoneTheme.secondary)
                    }
                    Spacer(minLength: 6)
                    Image(systemName: "chevron.down").font(.caption.weight(.semibold))
                        .rotationEffect(.degrees(expanded ? 180 : 0)).foregroundStyle(PhoneTheme.secondary)
                }.frame(minHeight: 44).contentShape(Rectangle())
            }.buttonStyle(.plain).accessibilityIdentifier("activity.toggle")
                .accessibilityLabel("Activity: " + title).accessibilityValue(expanded ? "Expanded" : "Collapsed")
                .accessibilityHint("Shows model cycles, tools and results")

            if let wait = store.conversationWait {
                Button { review(wait) } label: {
                    HStack(spacing: 8) {
                        Text(wait.kind == .toolApproval ? "Review tools" : "Reply").font(.subheadline.weight(.medium))
                        Spacer(); Image(systemName: "arrow.up.right").font(.caption.weight(.semibold))
                    }.frame(minHeight: 44).contentShape(Rectangle()).padding(.top, 4).foregroundStyle(PhoneTheme.amber)
                }.buttonStyle(.plain).accessibilityIdentifier("activity.review")
            }
            if let failure = store.activityFailure {
                Text(failure).font(.footnote).foregroundStyle(.red.opacity(0.9)).textSelection(.enabled).padding(.top, 10)
                    .accessibilityIdentifier("activity.failure")
            }
            if let issue = store.activityIssue {
                VStack(alignment: .leading, spacing: 6) {
                    Text(issue).font(.caption).foregroundStyle(PhoneTheme.amber).textSelection(.enabled)
                    Button("Reconnect activity") { Task { await store.refreshActivity() } }.font(.caption.weight(.medium))
                }.padding(.top, 10).accessibilityIdentifier("activity.connection")
            }
            if expanded {
                VStack(alignment: .leading, spacing: 0) {
                    Rectangle().fill(PhoneTheme.stroke).frame(height: 1).padding(.vertical, 13)
                    if store.activity.items.isEmpty {
                        Text("No runtime events received yet.").font(.footnote).foregroundStyle(PhoneTheme.secondary).padding(.bottom, 10)
                    }
                    ForEach(store.activity.items) { item in ActivityEventRow(item: item) }
                    if store.activity.wasTrimmed {
                        Text("Showing the latest 250 events. Counts include earlier events.").font(.caption).foregroundStyle(PhoneTheme.secondary).padding(.top, 10)
                    }
                    TimelineView(.periodic(from: .now, by: 1)) { _ in
                        VStack(alignment: .leading, spacing: 4) {
                            if let at = store.activity.lastEventAt {
                                Text("Last event \(at, style: .relative) ago")
                            } else { Text("Waiting for the first runtime event") }
                            if let checked = store.activityCheckedAt { Text("Status checked \(checked, style: .relative) ago") }
                        }.font(.caption2).foregroundStyle(PhoneTheme.secondary).padding(.top, 12)
                    }
                }.accessibilityIdentifier("activity.events")
            }
        }
        .padding(.horizontal, 14).padding(.vertical, 11)
        .background(PhoneTheme.surface.opacity(0.65), in: RoundedRectangle(cornerRadius: 17))
        .overlay(RoundedRectangle(cornerRadius: 17).stroke(PhoneTheme.stroke))
        .onChange(of: store.activityRootID) { _, _ in expanded = false }
    }
    private var title: String {
        if store.isStopping { return "Stopping…" }
        switch store.activityState {
        case .idle, .connecting: return "Sending…"
        case .waiting: return store.conversationWait?.kind == .toolApproval ? "Approval needed" : "Waiting for your reply"
        case .failed: return "Couldn’t finish"
        case .cancelled: return "Stopped"
        case .completed: return "Activity complete"
        case .running:
            if store.activityIssue != nil { return "Checking activity…" }
            if let summary = store.activitySummary { return summary }
            if let item = store.activity.items.last(where: { $0.status == .running }) {
                return item.kind == .tool ? "Using " + item.title : item.kind == .model ? "Thinking…" : "Working…"
            }
            return "Working…"
        }
    }
    private var counts: String {
        var parts: [String] = []
        let activity = store.activity
        if activity.cycleCount > 0 { parts.append("\(activity.cycleCount) \(activity.cycleCount == 1 ? "cycle" : "cycles")") }
        else if activity.modelCalls > 0 { parts.append("\(activity.modelCalls) \(activity.modelCalls == 1 ? "model call" : "model calls")") }
        if activity.toolCalls > 0 { parts.append("\(activity.toolCalls) \(activity.toolCalls == 1 ? "tool call" : "tool calls")") }
        if parts.isEmpty { return store.activityState == .connecting ? "Connecting to your gateway" : "View activity" }
        return parts.joined(separator: " · ")
    }
    private var tint: Color {
        switch store.activityState { case .failed: .red; case .waiting: PhoneTheme.amber; case .completed: PhoneTheme.mint; default: PhoneTheme.secondary }
    }
    private var symbol: String {
        switch store.activityState {
        case .waiting: "hand.raised"
        case .failed: "exclamationmark.circle"
        case .completed: "checkmark.circle"
        case .cancelled: "stop.circle"
        default: store.activityIssue == nil ? "waveform.path" : "wifi.exclamationmark"
        }
    }
}

private struct ActivityEventRow: View {
    let item: RunActivityItem
    @State private var opened = false
    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            if item.detail.isEmpty { label }
            else {
                DisclosureGroup(isExpanded: $opened) {
                    Text(item.detail).font(.footnote).foregroundStyle(PhoneTheme.secondary)
                        .textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.leading, 27).padding(.top, 6)
                        .accessibilityIdentifier("activity.result")
                } label: { label }.tint(PhoneTheme.secondary)
            }
        }.padding(.vertical, 9)
    }
    private var label: some View {
        HStack(alignment: .firstTextBaseline, spacing: 9) {
            Image(systemName: symbol).font(.caption).foregroundStyle(color).frame(width: 18)
            Text(item.title).font(.footnote.weight(.medium)).foregroundStyle(PhoneTheme.ink)
            Spacer(minLength: 8)
            Text(status).font(.caption2).foregroundStyle(color)
        }.accessibilityElement(children: .combine)
    }
    private var status: String {
        switch item.status { case .running: "Running"; case .completed: "Done"; case .waiting: "Waiting"; case .failed: "Failed"; case .cancelled: "Stopped" }
    }
    private var symbol: String {
        if item.status == .failed { return "exclamationmark.circle" }
        switch item.kind { case .model: return "sparkle"; case .tool: return "wrench.and.screwdriver"; case .wait: return "hand.raised"; case .failure: return "exclamationmark.circle"; case .result: return "text.alignleft" }
    }
    private var color: Color { item.status == .failed ? .red.opacity(0.85) : item.status == .waiting ? PhoneTheme.amber : item.status == .completed ? PhoneTheme.mint : PhoneTheme.secondary }
}
