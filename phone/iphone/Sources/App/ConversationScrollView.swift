import SwiftUI

/// Follow measured transcript layout, without stealing the viewport while reading history.
struct ConversationScrollView<Content: View>: View {
    var conversationID: String
    var userTurnID: String?
    var latestID: String?
    var latestText: String?
    @ViewBuilder var content: () -> Content
    @State private var following = true
    @State private var userScrolling = false
    @State private var userDragging = false
    @State private var scrollRequest = 0
    @State private var extent = TranscriptExtent()

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                content()
            }
            .accessibilityIdentifier("chat.transcript")
            .scrollDismissesKeyboard(.interactively)
            .defaultScrollAnchor(.bottom, for: .initialOffset)
            .onScrollPhaseChange { _, phase, context in
                if phase == .idle, userDragging {
                    let geometry = context.geometry
                    following = geometry.contentSize.height - geometry.visibleRect.maxY < 72
                }
                userScrolling = phase == .tracking || phase == .interacting || phase == .decelerating
                userDragging = phase == .interacting || phase == .decelerating
                if phase == .idle { requestIfFollowing() }
            }
            .onScrollGeometryChange(for: TranscriptExtent.self) { geometry in
                TranscriptExtent(height: geometry.contentSize.height.rounded(),
                    viewport: geometry.containerSize.height.rounded(),
                    bottomInset: geometry.contentInsets.bottom.rounded(),
                    distance: max(0, geometry.contentSize.height - geometry.visibleRect.maxY))
            } action: { old, new in
                extent = new
                // Programmatic scrolling and layout changes must never opt out of following.
                if userDragging || new.distance < 72 { following = new.distance < 72 }
                if following, old.height != new.height || old.viewport != new.viewport || old.bottomInset != new.bottomInset {
                    scrollRequest += 1
                }
            }
            .onChange(of: conversationID) { _, _ in resumeFollowing() }
            .onChange(of: userTurnID) { _, _ in resumeFollowing() }
            .onChange(of: latestID) { _, _ in requestIfFollowing() }
            .onChange(of: latestText) { _, _ in requestIfFollowing() }
            .onChange(of: following) { _, follow in if follow { scrollRequest += 1 } }
            .task(id: scrollRequest) {
                // Coalesce a streaming burst and let the row layout complete. Further measured
                // lazy-size changes request another correction, including image/inset changes.
                // A cooperative yield can resume before SwiftUI's next layout pass.
                // Coalesce through a display frame before asking the proxy for the bottom.
                try? await Task.sleep(for: .milliseconds(32))
                guard !Task.isCancelled, following, !userScrolling else { return }
                var transaction = Transaction(); transaction.disablesAnimations = true
                withTransaction(transaction) { proxy.scrollTo("bottom", anchor: .bottom) }
            }
            .overlay(alignment: .bottomTrailing) {
                if !following, extent.distance >= 72, extent.height > extent.viewport {
                    Button { resumeFollowing() } label: {
                        Label("Latest messages", systemImage: "arrow.down")
                            .font(.caption.weight(.semibold)).padding(.horizontal, 14).padding(.vertical, 10)
                            .foregroundStyle(PhoneTheme.ground).background(PhoneTheme.mint, in: Capsule())
                    }.buttonStyle(.plain).padding(12).accessibilityIdentifier("chat.latest")
                }
            }
        }
    }
    private func resumeFollowing() { userScrolling = false; userDragging = false; following = true; scrollRequest += 1 }
    private func requestIfFollowing() { if following { scrollRequest += 1 } }
}

private struct TranscriptExtent: Equatable {
    var height: CGFloat = 0
    var viewport: CGFloat = 0
    var bottomInset: CGFloat = 0
    var distance: CGFloat = 0
}
