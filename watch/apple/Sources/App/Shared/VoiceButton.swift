import SwiftUI
import WatchKit

/// The one voice control beside Back, sharing the orb's state (the same `Speaker`): a tap plays the
/// selected message, or pauses / resumes the one playing; holding it rewinds, about 4 s per second
/// held at first and faster the longer it is held (the voice waits while held, then goes on from
/// there). The screen hides it while there is nothing to read, or while the orb listens or works.
struct VoiceButton: View {
    @ObservedObject var speaker: Speaker
    /// The voice playing or paused is the selected message's (else a tap starts the selection).
    var isCurrent = true
    /// Reads the selected message from its start.
    let play: () -> Void

    @State private var pressed = false
    @State private var scrubbing = false
    @State private var wasPlaying = false
    @State private var scrub: Task<Void, Never>?

    private var playing: Bool { isCurrent && speaker.isActive }

    var body: some View {
        GlassIcon(symbol: scrubbing ? "backward.fill" : playing ? "pause.fill" : "play.fill")
            .scaleEffect(pressed ? 0.86 : 1).opacity(pressed ? 0.7 : 1)
            .animation(.easeOut(duration: 0.12), value: pressed)
            .contentShape(Circle())
            .gesture(DragGesture(minimumDistance: 0)
                .onChanged { _ in if !pressed { began() } }
                .onEnded { _ in ended() })
            .accessibilityElement()
            .accessibilityLabel(playing ? "Pause" : "Play")
            .accessibilityAddTraits(.isButton)
            .accessibilityIdentifier("voice.button")
            .accessibilityAction { tap() }
            .accessibilityAction(named: "Back 10 seconds") { speaker.rewindAndPlay(10) }
            .onDisappear { scrub?.cancel(); scrub = nil }
    }

    private func tap() {
        if !isCurrent { play() }
        else if speaker.isActive { speaker.pause() }
        else if speaker.isPaused { speaker.resume() }
        else { play() }
        WKInterfaceDevice.current().play(.click)
    }

    private func began() {
        pressed = true
        scrub = Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(450))
            // A hold, not a tap: rewind while held (only a message already heard can go back).
            guard !Task.isCancelled, isCurrent, speaker.isActive || speaker.isPaused || speaker.state == .finished else { return }
            scrubbing = true
            wasPlaying = speaker.isActive
            if speaker.isActive { speaker.pause() }
            var step = 1.0, ticks = 0
            while !Task.isCancelled {
                speaker.rewind(step)
                ticks += 1
                if ticks % 4 == 0 { WKInterfaceDevice.current().play(.click) }
                step = min(3, step * 1.12)                    // 4 s per second held, up to 12
                try? await Task.sleep(for: .milliseconds(250))
            }
        }
    }

    private func ended() {
        scrub?.cancel(); scrub = nil
        pressed = false
        if scrubbing {
            scrubbing = false
            if wasPlaying || speaker.isPaused { speaker.resume() }   // go on from the earlier point
        } else {
            tap()
        }
    }
}
