import AbstractGatewayClient
import SwiftUI

/// Home is the ready-to-talk conversation stage. Browsing lives below it;
/// beginning a turn opens the identical stage with session content in its place.
struct HomeView: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.openURL) private var openURL
    @AppStorage("ask.conversation") private var conversationView = false

    var body: some View {
        GeometryReader { geo in
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(spacing: 6) {
                        AssistantStage(width: geo.size.width, top: geo.frame(in: .global).minY) { side in
                            Orb(mode: .idle, size: side * (conversationView ? 0.72 : 0.9), look: model.responderLook)
                                .contentShape(Circle())
                                .onTapGesture { model.startHomeConversation(.listen) }
                                .accessibilityAddTraits(.isButton)
                                .accessibilityLabel("Talk to \(model.responder.title)")
                                .accessibilityIdentifier("home.orb")
                        } bottom: {
                            VStack(spacing: 4) {
                                AssistantResponderSwitch()
                                Text("Tap to talk").font(.rounded(.footnote)).foregroundStyle(Theme.muted)
                                    .accessibilityIdentifier("home.status")
                            }.padding(.bottom, 8)
                        } keyboard: {
                            TextFieldLink(prompt: Text("Ask \(model.responder.title)")) {
                                GlassIcon(symbol: "keyboard").padding(AskView.reach).contentShape(Rectangle())
                            } onSubmit: { text in
                                let draft = text.trimmingCharacters(in: .whitespacesAndNewlines)
                                if !draft.isEmpty { model.startHomeConversation(.text(draft)) }
                            }
                            .accessibilityLabel("Type or dictate")
                        } accessory: {
                            if model.responder == .assistant { AssistantToolsLink() }
                        }
                        .id("orb")
                        VStack(spacing: 8) {
                            if model.connecting {
                                LoadingText(text: "Connecting").font(.rounded(.caption2)).foregroundStyle(Theme.amber)
                                    .accessibilityIdentifier("gateway.connecting")
                            } else if let err = gatewayError {
                                Text(err).font(.rounded(.caption2)).foregroundStyle(Theme.red)
                                    .multilineTextAlignment(.center).lineLimit(2)
                                    .accessibilityIdentifier("gateway.error")
                            }
                            if !model.waits.isEmpty { waitingCard }
                            NavigationLink(value: Route.sessions) {
                                row("Sessions", symbol: "bubble.left.and.bubble.right", detail: sessionsDetail,
                                    badge: nil, badgeColor: Theme.cyan, count: model.newSessionCount, countLabel: "new", total: model.sessions.count,
                                    loading: !model.sessionsLoaded)
                            }.buttonStyle(.tap).accessibilityIdentifier("home.sessions")
                            NavigationLink(value: Route.automations) {
                                row("Automations", symbol: "clock.arrow.circlepath", detail: automationDetail,
                                    badge: nil, badgeColor: Theme.amber, count: unseenCount, countLabel: "new", total: model.automations.count,
                                    loading: !model.automationsLoaded)
                            }.buttonStyle(.tap).accessibilityIdentifier("home.automations")
                                .id("bottom")
                        }.padding(.horizontal, 10)
                    }
                }
                .refreshable { await model.refresh() }
                .onChange(of: model.path) { _, path in
                    if path.isEmpty {
                        model.prepareHomeConversation()
                        proxy.scrollTo("orb", anchor: .top)
                    }
                }
                #if DEBUG
                .task {
                    if ProcessInfo.processInfo.arguments.contains("--home-bottom") {
                        try? await Task.sleep(for: .seconds(1)); proxy.scrollTo("bottom", anchor: .bottom)
                    }
                }
                #endif
            }
        }
        .besideBack { EmptyView() }
        .onAppear { model.prepareHomeConversation() }
        .task(id: model.responder) {
            if case .entity(let name) = model.responder { await model.loadIdentity(of: name) }
        }
        .task {
            #if DEBUG
            if let url = model.testOpen { model.testOpen = nil; try? await Task.sleep(for: .seconds(2)); openURL(url) }
            if ProcessInfo.processInfo.arguments.contains("--render-icon") { OrbIcon.render() }
            if ProcessInfo.processInfo.arguments.contains("--render-orb-work") { OrbIcon.renderWork() }
            if ProcessInfo.processInfo.arguments.contains("--render-orb-scenes") { OrbIcon.renderScenes() }
            if ProcessInfo.processInfo.arguments.contains("--render-icons") { OrbIcon.renderIcons() }
            #endif
        }
    }

    /// Red only once the gateway is really unreachable (3 failed tries over 20 s), or when an
    /// action failed; a poll that fails and is being retried says nothing (or Connecting, above).
    private var gatewayError: String? {
        if model.unreachable { return model.lastError ?? "Can't reach your assistant." }
        if model.failures > 0 || model.client.isMock { return nil }
        return model.lastError
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
        .buttonStyle(.tap)
    }

    /// Conversations working now come first ("2 working"), else the latest one's title; nil while
    /// it is not known yet (the row says Loading…).
    private var sessionsDetail: String? {
        guard model.sessionsLoaded else { return nil }
        if model.sessions.isEmpty { return "None yet" }
        if model.runningCount > 0 { return "\(model.runningCount) working" }
        guard let latest = model.sessions.first else { return nil }
        if model.unreadablePrompts.contains(latest.latest.runId) { return "" }
        return model.title(of: latest)
    }

    private func row(_ title: String, symbol: String, detail: String?, badge: String?, badgeColor: Color, count: Int = 0, countLabel: String = "",
                     total: Int? = nil, loading: Bool = false) -> some View {
        Card {
            HStack(spacing: 8) {
                Image(systemName: symbol).font(.rounded(.body)).foregroundStyle(Theme.cyan).frame(width: 22)
                VStack(alignment: .leading, spacing: 1) {
                    Text(title).font(.rounded(.headline)).foregroundStyle(Theme.text).lineLimit(1)
                    // Not known yet: Loading, with its dots.
                    Group { if let detail { Text(detail).lineLimit(1) } else { LoadingText() } }
                        .font(.rounded(.caption2)).foregroundStyle(Theme.muted)
                }
                Spacer(minLength: 2)
                if let badge { Pill(text: badge, color: badgeColor) }
                // Not read yet: a spinner where the number goes (never a 0 or "None yet" before it is known).
                // What is new: the number in a filled badge; nothing new: how many there are, muted.
                if loading {
                    ProgressView().frame(width: 20, height: 20).accessibilityLabel("Loading")
                } else if count > 0 {
                    Text("\(count)").font(.rounded(.caption2, weight: .bold)).monospacedDigit()
                        .foregroundStyle(Theme.ground)
                        .frame(minWidth: 20, minHeight: 20).padding(.horizontal, count > 9 ? 3 : 0)
                        .background(badgeColor, in: Capsule())
                        .accessibilityLabel("\(count) \(countLabel)")
                } else if let total, total > 0 {
                    Text("\(total)").font(.rounded(.caption2, weight: .semibold)).monospacedDigit()
                        .foregroundStyle(Theme.muted)
                        .frame(minWidth: 20, minHeight: 20).padding(.horizontal, total > 9 ? 3 : 0)
                        .overlay(Capsule().strokeBorder(Theme.line, lineWidth: 1))
                        .accessibilityLabel("\(total), nothing new")
                }
            }
        }
    }

    private var unseenCount: Int { model.automations.reduce(0) { $0 + ($1.attention?.unseenCount ?? 0) } }

    /// The name of the automation with the latest activity (the gateway's first row), "None yet", or nil
    /// until the list is in (the row says Loading…).
    private var automationDetail: String? {
        guard model.automationsLoaded else { return nil }
        guard let a = model.automations.first else { return "None yet" }
        return a.name ?? "Automation"
    }
}
