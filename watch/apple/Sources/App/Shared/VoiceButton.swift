import SwiftUI
import WatchKit

/// The one voice control beside Back, sharing the orb's state (the same `Speaker`): a tap plays the
/// selected message, or pauses / resumes the one playing; holding it rewinds, about 8 s per second
/// held at first (a bump every half second) and faster the longer it is held (the voice waits while
/// held, then goes on from there). While the voice is being made it shows a spinner and a tap waits with it. The screen
/// hides it while there is nothing to read, or while the orb listens or works.
struct VoiceButton: View {
    @ObservedObject var speaker: Speaker
    /// The voice playing or paused is the selected message's (else a tap starts the selection).
    var isCurrent = true
    /// Reads the selected message from its start.
    let play: () -> Void

    /// The finger is down (the dip). Reset by SwiftUI when the touch ends AND when the system takes
    /// it (a banner, the top-edge swipe, wrist down), so the button can never stay pressed. A quick
    /// tap may set and reset it within one frame, unseen: the press itself starts from the gesture.
    @GestureState private var touching = false
    /// The press in progress (a token: the gesture's end and its reset may arrive in either order).
    @State private var press: Int?
    @State private var presses = 0
    /// A press whose rewind was ended by the system taking the touch: its late release is no tap.
    @State private var cancelledScrub: Int?
    @State private var scrubbing = false
    @State private var wasPlaying = false
    @State private var scrub: Task<Void, Never>?
    /// How far a finger may move and still tap (a fingertip rolls a little).
    private static let tapSlop: CGFloat = 12
    /// A firm tap on a watch can last half a second: only a longer press is a hold.
    private static let holdDelay = Duration.milliseconds(650)

    private var playing: Bool { isCurrent && speaker.isActive }
    private var preparing: Bool { isCurrent && speaker.state == .preparing }
    /// Only a voice playing or paused can go back (a finished one replays with a tap).
    private var canScrub: Bool { isCurrent && (speaker.state == .speaking || speaker.isPaused) }

    var body: some View {
        GlassIcon(symbol: scrubbing ? "backward.fill" : playing ? "pause.fill" : "speaker.wave.2.fill")   // a speaker, not a play: it reads aloud
            .overlay {
                if preparing && !scrubbing {
                    Circle().fill(Color(red: 28 / 255, green: 28 / 255, blue: 38 / 255))
                    ProgressView().controlSize(.small)
                }
            }
            .scaleEffect(touching ? 0.86 : 1).opacity(touching ? 0.7 : 1)
            .animation(.easeOut(duration: 0.12), value: touching)
            // The touch area reaches past the drawn circle (a fingertip is wider than 35 pt), above,
            // below and to the right (the icon beside it is 6 pt to the left).
            .rowReach(trailing: 9)
            .gesture(DragGesture(minimumDistance: 0)
                .updating($touching) { _, down, _ in down = true }
                .onChanged { _ in if press == nil { pressed() } }
                // A finger that slid away (a scroll that began on the button) is no tap.
                .onEnded { v in released(tapped: hypot(v.translation.width, v.translation.height) < Self.tapSlop) })
            .onChange(of: touching) { _, down in if !down { touchGone() } }
            .accessibilityElement()
            .accessibilityLabel(preparing ? "Making the voice" : playing ? "Pause" : "Read aloud")
            .accessibilityValue(debugValue)
            .accessibilityAddTraits(.isButton)
            .accessibilityIdentifier("voice.button")
            .accessibilityAction { tap() }
            .accessibilityAction(named: "Back 10 seconds") { speaker.rewindAndPlay(10) }
            .onDisappear { cancelPress() }
    }

    /// For the UI tests: whether a press or a rewind is still under way.
    private var debugValue: String {
        #if DEBUG
        scrubbing ? "rewinding" : press != nil ? "down" : ""
        #else
        ""
        #endif
    }

    private func tap() {
        if !isCurrent { play() }
        else if speaker.state == .preparing { }           // the voice is on its way: a second tap waits too
        else if speaker.isActive { speaker.pause() }
        else if speaker.isPaused { speaker.resume() }
        else { play() }
        WKInterfaceDevice.current().play(.click)
    }

    private func pressed() {
        presses += 1
        let mine = presses
        press = mine
        scrub?.cancel()
        scrub = Task { @MainActor in
            try? await Task.sleep(for: Self.holdDelay)
            guard !Task.isCancelled, press == mine, canScrub else { return }
            scrubbing = true
            wasPlaying = speaker.isActive
            if speaker.isActive { speaker.pause() }
            var step = 2.0, ticks = 0
            while !Task.isCancelled, press == mine {
                speaker.rewind(step)
                ticks += 1
                if ticks % 2 == 0 { WKInterfaceDevice.current().play(.click) }   // a bump every half second
                step = min(6, step * 1.12)                    // 8 s per second held, up to 24
                try? await Task.sleep(for: .milliseconds(250))
            }
        }
    }

    /// The finger lifted: a tap (where it landed), or the end of a hold (the voice goes on from the
    /// earlier point).
    private func released(tapped: Bool) {
        let mine = presses
        press = nil
        if endScrub(resumeIfPaused: true) || cancelledScrub == mine || !tapped { return }
        tap()
    }

    /// The touch is gone; without a release (the system took it) nothing is tapped.
    private func touchGone() {
        guard let mine = press else { return }
        Task { @MainActor in if press == mine { cancelPress() } }
    }

    private func cancelPress() {
        if scrubbing { cancelledScrub = press }
        press = nil
        endScrub(resumeIfPaused: false)
    }

    @discardableResult private func endScrub(resumeIfPaused: Bool) -> Bool {
        scrub?.cancel(); scrub = nil
        guard scrubbing else { return false }
        scrubbing = false
        if wasPlaying || (resumeIfPaused && speaker.isPaused) { speaker.resume() }
        return true
    }
}
