import AbstractGatewayClient
import SwiftUI

/// Home: the orb first (one tap to talk), then only what needs you, then your conversations and
/// automations. Settings is the gear at the top; the gateway's state shows only when it matters.
struct HomeView: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.openURL) private var openURL

    var body: some View {
        ScrollViewReader { proxy in
        ScrollView {
            VStack(spacing: 8) {
                NavigationLink(value: Route.ask(.idle)) {
                    VStack(spacing: 2) {
                        // Smaller when something needs you, so that card stays on the first screen.
                        Orb(mode: .idle, size: model.waits.isEmpty ? 96 : 68, fps: 24, look: model.responderLook)
                        Text("Talk to \(model.responder.title)").font(.rounded(.footnote, weight: .medium)).foregroundStyle(Theme.text2)
                    }
                    .frame(maxWidth: .infinity)
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Talk to \(model.responder.title)")
                if let line = gatewayLine {
                    Text(line.text).font(.rounded(.caption2)).foregroundStyle(line.color)
                        .multilineTextAlignment(.center).lineLimit(2)
                }
                // Only when something needs you: an empty "0 nothing waiting" card is noise.
                if !model.waits.isEmpty { waitingCard }
                NavigationLink(value: Route.sessions) {
                    row("Sessions", symbol: "bubble.left.and.bubble.right",
                        detail: model.sessions.isEmpty ? "None yet" : (model.sessions.first.flatMap { model.title(of: $0) } ?? ""),
                        badge: nil, badgeColor: Theme.cyan, count: model.runningCount, countLabel: "working")
                }
                .buttonStyle(.plain)
                NavigationLink(value: Route.automations) {
                    row("Automations", symbol: "clock.arrow.circlepath", detail: automationDetail,
                        badge: nil, badgeColor: Theme.amber, count: unseenCount, countLabel: "new")
                }
                .buttonStyle(.plain)
                .id("bottom")
            }
        }
        #if DEBUG
        .task {   // screenshots of the lower rows: --home-bottom
            guard ProcessInfo.processInfo.arguments.contains("--home-bottom") else { return }
            try? await Task.sleep(for: .seconds(1)); proxy.scrollTo("bottom", anchor: .bottom)
        }
        #endif
        }
        .screen("Assistant")
        .toolbar {
            ToolbarItem(placement: .topBarLeading) {
                NavigationLink(value: Route.settings) { BarIcon(symbol: "gearshape") }
                    .tint(Theme.neutralButton)
                    .accessibilityLabel("Settings")
            }
        }
        .refreshable { await model.refresh() }
        .task {
            #if DEBUG
            if let url = model.testOpen { model.testOpen = nil; try? await Task.sleep(for: .seconds(2)); openURL(url) }
            if ProcessInfo.processInfo.arguments.contains("--render-icon") { OrbIcon.render() }
            if ProcessInfo.processInfo.arguments.contains("--render-orb-work") { OrbIcon.renderWork() }
            #endif
        }
    }

    /// Nothing while all is well: only connecting, offline, signed-out or a minute-old refresh.
    private var gatewayLine: (text: String, color: Color)? {
        if model.client.isMock { return nil }
        if let err = model.lastError { return (err, Theme.red) }
        if model.connecting { return ("Connecting…", Theme.amber) }
        return nil
    }

    private var waitingCard: some View {
        let first = model.waits[0]
        let route: Route = model.waits.count > 1 ? .waits : (first.kind == .askUser ? .askUser(first) : .approval(first))
        return NavigationLink(value: route) {
            Card(fill: Theme.amber.opacity(0.12), stroke: Color(hex: 0xc2620c)) {
                HStack(spacing: 8) {
                    Text("\(model.waits.count)").font(.rounded(.title2, weight: .bold)).foregroundStyle(Theme.amber)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(model.waits.count == 1 ? "Needs you" : "Need you").font(.rounded(.headline)).foregroundStyle(Theme.text)
                        Text(first.headline).font(.rounded(.caption2)).foregroundStyle(Theme.text2).lineLimit(1)
                    }
                    Spacer(minLength: 2)
                    Image(systemName: "chevron.right").foregroundStyle(Theme.amber)
                }
            }
        }
        .buttonStyle(.plain)
    }

    private func row(_ title: String, symbol: String, detail: String, badge: String?, badgeColor: Color, count: Int = 0, countLabel: String = "") -> some View {
        Card {
            HStack(spacing: 8) {
                Image(systemName: symbol).font(.rounded(.body)).foregroundStyle(Theme.cyan).frame(width: 22)
                VStack(alignment: .leading, spacing: 1) {
                    Text(title).font(.rounded(.headline)).foregroundStyle(Theme.text).lineLimit(1)
                    Text(detail).font(.rounded(.caption2)).foregroundStyle(Theme.muted).lineLimit(1)
                }
                Spacer(minLength: 2)
                if let badge { Pill(text: badge, color: badgeColor) }
                // A count (new results, conversations working): just the number, in a round badge.
                if count > 0 {
                    Text("\(count)").font(.rounded(.caption2, weight: .bold)).monospacedDigit()
                        .foregroundStyle(Theme.ground)
                        .frame(minWidth: 20, minHeight: 20).padding(.horizontal, count > 9 ? 3 : 0)
                        .background(badgeColor, in: Capsule())
                        .accessibilityLabel("\(count) \(countLabel)")
                }
            }
        }
    }

    private var unseenCount: Int { model.automations.reduce(0) { $0 + ($1.attention?.unseenCount ?? 0) } }

    private var automationDetail: String {
        guard let a = model.automations.first else { return model.lastRefresh == nil ? "" : "None yet" }
        return a.name ?? "Automation"
    }
}
