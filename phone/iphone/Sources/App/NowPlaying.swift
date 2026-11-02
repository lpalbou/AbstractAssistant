import MediaPlayer

/// A reading on the lock screen, in Control Center and on the headphones' button: its title and
/// play/pause. Set while a reading started with a title is under way (the conversation's), cleared
/// when it ends; nothing else is shown (the reading's length is not known while it streams).
@MainActor final class NowPlaying {
    private var targets: [(MPRemoteCommand, Any)] = []
    private var info: [String: Any] = [:]

    func begin(title: String, toggle: @escaping @MainActor @Sendable () -> Void, play: @escaping @MainActor @Sendable () -> Void,
               pause: @escaping @MainActor @Sendable () -> Void) {
        end()
        let center = MPRemoteCommandCenter.shared()
        for (command, action) in [(center.togglePlayPauseCommand, toggle), (center.playCommand, play), (center.pauseCommand, pause)] {
            command.isEnabled = true
            // The command center does not promise the thread it calls on: hop to the main actor.
            targets.append((command, command.addTarget { _ in Task { @MainActor in action() }; return .success }))
        }
        info = [MPMediaItemPropertyTitle: title, MPMediaItemPropertyArtist: "AbstractAssistant",
                MPNowPlayingInfoPropertyMediaType: MPNowPlayingInfoMediaType.audio.rawValue,
                MPNowPlayingInfoPropertyElapsedPlaybackTime: 0.0, MPNowPlayingInfoPropertyPlaybackRate: 0.0]
        MPNowPlayingInfoCenter.default().nowPlayingInfo = info
    }

    /// The system moves the lock screen's time on from `elapsed` at `rate` while it plays.
    func update(playing: Bool, elapsed: Double, rate: Float) {
        guard !targets.isEmpty else { return }
        info[MPNowPlayingInfoPropertyElapsedPlaybackTime] = elapsed
        info[MPNowPlayingInfoPropertyPlaybackRate] = playing ? Double(rate) : 0.0
        MPNowPlayingInfoCenter.default().nowPlayingInfo = info
    }

    func end() {
        guard !targets.isEmpty else { return }
        for (command, target) in targets { command.removeTarget(target) }
        targets.removeAll(); info.removeAll()
        MPNowPlayingInfoCenter.default().nowPlayingInfo = nil
    }
}
