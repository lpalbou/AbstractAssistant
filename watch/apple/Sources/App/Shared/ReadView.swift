import AbstractGatewayClient
import SwiftUI

/// A text and where its voice comes from: a run (the gateway's voice) or an entity (its own voice).
struct ReadItem: Hashable {
    var title: String
    var text: String
    var scope: SpeechScope
}

/// Read aloud: the orb speaks with the voice (its size and glow follow the audio level),
/// the text stays readable below, Stop or Read again.
struct ReadView: View {
    let item: ReadItem
    @EnvironmentObject private var model: AppModel
    @StateObject private var speaker = Speaker()
    @State private var started = false

    var body: some View {
        ScrollView {
            VStack(spacing: 8) {
                // Tap the orb: pause, and tap again to resume exactly where it stopped.
                Button { if speaker.isPaused { speaker.resume() } else if speaker.isActive { speaker.pause() } else { start() } } label: {
                    Orb(mode: orbMode, size: 78, level: { speaker.level() })
                }
                .buttonStyle(.plain)
                TimelineView(.periodic(from: .now, by: 0.5)) { _ in
                    Text(status).font(.rounded(.caption2)).foregroundStyle(statusColor)
                        .multilineTextAlignment(.center).lineLimit(4)
                }
                if speaker.isActive || speaker.isPaused {
                    Button("Stop") { speaker.stop() }
                        .buttonStyle(FilledButtonStyle(fill: Theme.neutralButton, foreground: Theme.text2))
                } else {
                    Button { start() } label: { Label(speaker.state == .idle ? "Read aloud" : "Read again", systemImage: "speaker.wave.2.fill") }
                        .buttonStyle(FilledButtonStyle(fill: Theme.indigoButton))
                }
                Card { MarkdownText(item.text) }
            }
        }
        .screen(item.title)
        // Starts once: watchOS repeats onAppear (dimming, polling) and reading must go on with the
        // wrist down. Leaving the screen (Back) is what stops it.
        .onAppear { if !started { started = true; start() } }
        .task {
            guard model.testPause else { return }
            model.testPause = false
            while speaker.state != .speaking { try? await Task.sleep(for: .milliseconds(100)) }
            try? await Task.sleep(for: .seconds(2)); speaker.pause()
            try? await Task.sleep(for: .seconds(3)); speaker.resume()
        }
        .onChange(of: model.path) { _, path in if !path.contains(.read(item)) { speaker.stop() } }
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
        case .idle: "stopped"
        case .paused: "paused · " + Self.clock(speaker.position()) + " · tap the orb to resume"
        case .preparing: speaker.playedSeconds > 0 ? "waiting for the next sentence…" : "preparing the voice…"
        case .speaking: "reading · " + Self.clock(speaker.position()) + (speaker.receivedSeconds > 0 ? " / " + Self.clock(speaker.receivedSeconds) : "")
        case .finished: "read · " + Self.clock(speaker.playedSeconds)
        case .failed(let why): why
        }
    }

    private var statusColor: Color {
        if case .failed = speaker.state { return Theme.red }
        return speaker.state == .speaking ? Theme.cyan : Theme.muted
    }

    private static func clock(_ s: Double) -> String { String(format: "%d:%02d", Int(s) / 60, Int(s) % 60) }
}

/// "Read aloud" as a row under a text.
struct ReadAloudLink: View {
    let item: ReadItem
    var body: some View {
        NavigationLink(value: Route.read(item)) {
            Label("Read aloud", systemImage: "speaker.wave.2.fill")
                .font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.cyan)
                .frame(maxWidth: .infinity, minHeight: 34)
                .background(Theme.cyan.opacity(0.1), in: RoundedRectangle(cornerRadius: 17))
        }
        .buttonStyle(.plain)
    }
}
