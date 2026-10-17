import AbstractGatewayClient
import SwiftUI
import WatchKit

/// A text and where its voice comes from: a run (the gateway's voice) or an entity (its own voice).
struct ReadItem: Hashable {
    var title: String
    var text: String
    var scope: SpeechScope
}

/// Read aloud: the orb speaks with the voice and fills the screen; the text is below on scroll.
/// Tap the orb to pause or resume (or read again once done); beside Back, go back 10 seconds.
struct ReadView: View {
    let item: ReadItem
    @EnvironmentObject private var model: AppModel
    @StateObject private var speaker = Speaker()
    @State private var started = false

    var body: some View {
        GeometryReader { geo in
            ScrollView {
                VStack(spacing: 6) {
                    // Like Ask: the orb fills the screen and is the control (tap: pause, resume, read
                    // again); the text is below, on scroll.
                    ZStack(alignment: .bottom) {
                        Orb(mode: orbMode, size: min(geo.size.width, geo.size.height + geo.safeAreaInsets.bottom), level: { speaker.level() }, look: lookOfVoice)
                            .frame(width: geo.size.width, height: geo.size.height + geo.safeAreaInsets.bottom)   // the text below starts off screen
                            .contentShape(Rectangle())
                            .onTapGesture(perform: orbTapped)
                            .accessibilityAddTraits(.isButton)
                            .accessibilityLabel(speaker.isActive ? "Pause" : speaker.isPaused ? "Resume" : "Read aloud")
                        Text(status).font(.rounded(.footnote)).foregroundStyle(statusColor)
                            .lineLimit(1).shadow(color: .black, radius: 3)
                            .padding(.bottom, geo.safeAreaInsets.bottom * 0.25)   // low, clear of the orb and the round corners
                    }
                    MarkdownText(item.text, font: .rounded(.body)).padding(.horizontal, 10)
                }
            }
        }
        .screen("")            // like Ask: the orb is the screen
        .overlay(alignment: .topLeading) {
            rewindButton.padding(.leading, 56).padding(.top, 18).ignoresSafeArea()
        }
        // Starts once: watchOS repeats onAppear (dimming, polling) and reading must go on with the
        // wrist down. Leaving the screen (Back) is what stops it.
        .onAppear { if !started { started = true; start() } }
        #if DEBUG
        .task {   // --test-rewind: rewind once mid-reading, once after it finished; positions printed
            guard ProcessInfo.processInfo.arguments.contains("--test-rewind") else { return }
            while speaker.playedSeconds == 0 { try? await Task.sleep(for: .milliseconds(100)) }
            try? await Task.sleep(for: .milliseconds(600))
            let before = speaker.position()
            speaker.rewind(ProcessInfo.processInfo.arguments.contains("--rewind-1") ? 1 : 10)
            print(String(format: "test-rewind playing: %.2f s -> %.2f s, state %@", before, speaker.position(), "\(speaker.state)"))
            while speaker.state != .finished { try? await Task.sleep(for: .milliseconds(100)) }
            let end = speaker.position()
            speaker.rewind(10)
            try? await Task.sleep(for: .milliseconds(400))
            print(String(format: "test-rewind finished: %.2f s -> %.2f s, state %@", end, speaker.position(), "\(speaker.state)"))
        }
        #endif
        .task {
            guard model.testPause else { return }
            model.testPause = false
            while speaker.state != .speaking { try? await Task.sleep(for: .milliseconds(100)) }
            try? await Task.sleep(for: .seconds(2)); speaker.pause()
            try? await Task.sleep(for: .seconds(3)); speaker.resume()
        }
        .onChange(of: model.path) { _, path in if !path.contains(.read(item)) { speaker.stop() } }
    }

    private func orbTapped() {
        if speaker.isPaused { speaker.resume() } else if speaker.isActive { speaker.pause() } else { start() }
    }

    /// Back 10 s, in the top bar beside Back (drawn over the page: a toolbar item there would
    /// replace the Back button).
    /// Once something has been spoken (the player clamps a rewind past the start to the start).
    private var rewindable: Bool {
        switch speaker.state {
        case .idle, .failed: false
        case .preparing: speaker.playedSeconds > 0
        default: true
        }
    }

    private var rewindButton: some View {
        Button { speaker.rewind(10); WKInterfaceDevice.current().play(.click) } label: {
            GlassIcon(symbol: "gobackward.10")
        }
        .buttonStyle(.plain)
        .disabled(!rewindable)
        .opacity(rewindable ? 1 : 0.4)
        .accessibilityLabel("Back 10 seconds")
    }

    /// The orb of the voice that reads: the entity's own for an entity's text, else the Assistant's.
    private var lookOfVoice: OrbLook {
        if case .entity(let name) = item.scope { return model.look(for: .entity(name)) }
        return .assistant
    }

    private func start() { speaker.read(item.text, scope: item.scope, client: model.client) }

    private var orbMode: Orb.Mode {
        switch speaker.state {
        case .preparing: .thinking
        case .speaking: .speaking
        default: .idle
        }
    }

    private var status: String {
        switch speaker.state {
        case .paused: "Paused"
        case .failed: "Voice unavailable"
        default: ""
        }
    }

    private var statusColor: Color {
        if case .failed = speaker.state { return Theme.red }
        return speaker.state == .speaking ? Theme.cyan : Theme.muted
    }

}

/// "Read aloud": a small glass speaker beside a text's title.
struct ReadAloudLink: View {
    let item: ReadItem
    var body: some View {
        NavigationLink(value: Route.read(item)) { GlassIcon(symbol: "speaker.wave.2.fill") }
            .buttonStyle(.plain)
            .accessibilityLabel("Read aloud")
    }
}
