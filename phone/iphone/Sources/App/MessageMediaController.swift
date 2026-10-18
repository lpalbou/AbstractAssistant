import SwiftUI
import AVFoundation
import ImageIO
import AssistantKit
import AbstractGatewayClient

/// Conversation-owned previews. Downloads stay in the app's disposable preview namespace.
@MainActor @Observable final class MessageMediaController: NSObject, AVAudioPlayerDelegate {
    private(set) var images: [String: UIImage] = [:]
    private(set) var files: [String: URL] = [:]
    private(set) var loading: Set<String> = []
    private(set) var errors: [String: String] = [:]
    private(set) var playingID: String?
    private(set) var paused = false
    private(set) var level: Double = 0
    private var envelope = AudioEnvelope()
    private var sampler: Task<Void, Never>?
    private var events: AudioSessionEvents?
    var preview: URL?
    var onUnauthorized: (() -> Void)?
    private var binding: String?
    private var generation = UUID()
    private var player: AVAudioPlayer?
    private var audioRequest = UUID()
    private var folders: [URL] = []
    private var cacheOrder: [String] = []
    private var downloads: [String: Task<Void, Error>] = [:]
    private let storage: PhoneTemporaryStorage
    init(storage: PhoneTemporaryStorage = .init()) {
        self.storage = storage; super.init()
        events = AudioSessionEvents { [weak self] in self?.stop() }
    }
    isolated deinit { sampler?.cancel(); for task in downloads.values { task.cancel() }; for folder in folders { try? FileManager.default.removeItem(at: folder) } }
    func bind(_ key: String) { if key != binding { reset(); binding = key } }
    func stop() { audioRequest = UUID(); player?.stop(); player = nil; playingID = nil; paused = false; sampler?.cancel(); sampler = nil; envelope.reset(); level = 0 }
    func reset() {
        generation = UUID(); for task in downloads.values { task.cancel() }; downloads = [:]; stop(); preview = nil; images = [:]; files = [:]; loading = []; errors = [:]
        for folder in folders { try? storage.discard(folder) }; folders = []; cacheOrder = []
    }
    private var cachedBytes: Int { files.values.reduce(0) { $0 + ((try? $1.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0) } }
    var revision: UUID { generation }
    var duration: Double { player?.duration ?? 0 }
    var elapsed: Double { player?.currentTime ?? 0 }
    func seek(_ seconds: Double) { player?.currentTime = seconds }
    private func fetch(_ file: PhoneArtifact, client: any GatewayClient) async -> URL? {
        if let url = files[file.id] { cacheOrder.removeAll { $0 == file.id }; cacheOrder.append(file.id); return url }
        guard !loading.contains(file.id) else { return nil }
        let epoch = generation; loading.insert(file.id); errors[file.id] = nil
        defer { if epoch == generation { loading.remove(file.id) } }
        var owned: URL?
        do {
            let folder = try storage.makeDirectory(for: .previews); owned = folder
            let url = folder.appending(path: file.filename)
            let download = Task { try await client.download(file, to: url) }
            downloads[file.id] = download
            defer { if epoch == generation { downloads[file.id] = nil } }
            try await withTaskCancellationHandler { try await download.value } onCancel: { download.cancel() }
            try Task.checkCancellation()
            guard epoch == generation else { try? storage.discard(folder); return nil }
            folders.append(folder); files[file.id] = url; cacheOrder.append(file.id)
            while files.count > 6 || cachedBytes > 128 * 1024 * 1024, let oldest = cacheOrder.first(where: { $0 != file.id && $0 != playingID && files[$0] != preview }) {
                if let expired = files.removeValue(forKey: oldest) {
                    let owned = expired.deletingLastPathComponent(); try? storage.discard(owned); folders.removeAll { $0 == owned }
                }
                cacheOrder.removeAll { $0 == oldest }; images[oldest] = nil
            }
            return url
        } catch {
            if let owned { try? storage.discard(owned) }
            guard epoch == generation, !(error is CancellationError) else { return nil }
            errors[file.id] = error.localizedDescription
            if error as? GatewayError == .unauthorized { onUnauthorized?() }
            return nil
        }
    }
    func thumbnail(_ file: PhoneArtifact, client: any GatewayClient) async {
        guard file.isImage, images[file.id] == nil, let url = await fetch(file, client: client) else { return }
        let options: [CFString: Any] = [kCGImageSourceShouldCache: false]
        guard let source = CGImageSourceCreateWithURL(url as CFURL, options as CFDictionary),
              let cgImage = CGImageSourceCreateThumbnailAtIndex(source, 0, [kCGImageSourceCreateThumbnailFromImageAlways: true,
                  kCGImageSourceCreateThumbnailWithTransform: true, kCGImageSourceThumbnailMaxPixelSize: 1200] as CFDictionary) else { return }
        images[file.id] = UIImage(cgImage: cgImage)
    }
    func open(_ file: PhoneArtifact, client: any GatewayClient) async {
        if let url = await fetch(file, client: client) { preview = url }
    }
    func play(_ file: PhoneArtifact, client: any GatewayClient) async {
        if playingID == file.id, let player {
            if player.isPlaying { player.pause(); paused = true } else { player.play(); paused = false }
            return
        }
        stop(); let request = audioRequest
        guard let url = await fetch(file, client: client), request == audioRequest else { return }
        do {
            try AVAudioSession.sharedInstance().setCategory(.playback, mode: .spokenAudio)
            try AVAudioSession.sharedInstance().setActive(true)
            let audio = try AVAudioPlayer(contentsOf: url)
            audio.delegate = self; audio.isMeteringEnabled = true; audio.prepareToPlay()
            guard audio.play() else { throw PhoneAttachmentError.unsupported }
            player = audio; playingID = file.id; paused = false
            sampler = Task { [weak self] in
                while !Task.isCancelled {
                    self?.sample()
                    do { try await Task.sleep(for: .milliseconds(33)) } catch { return }
                }
            }
        } catch { errors[file.id] = "Couldn’t play this audio. " + error.localizedDescription }
    }
    private func sample() {
        guard let player, player.isPlaying else { level = envelope.sample(averageDB: -160, peakDB: -160); return }
        player.updateMeters(); level = envelope.sample(averageDB: player.averagePower(forChannel: 0), peakDB: player.peakPower(forChannel: 0))
    }
    nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        Task { @MainActor [weak self] in if self?.player === player { self?.stop() } }
    }
}

struct MessageArtifactView: View {
    let file: PhoneArtifact
    let media: MessageMediaController
    let client: any GatewayClient
    var useImage: () -> Void
    var beforePlayback: () -> Void
    private var playing: Bool { media.playingID == file.id }
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if file.isImage {
                Button { Task { await media.open(file, client: client) } } label: {
                    Group {
                        if let image = media.images[file.id] { Image(uiImage: image).resizable().scaledToFit() }
                        else { Rectangle().fill(PhoneTheme.surface).aspectRatio(1.5, contentMode: .fit).overlay { if media.loading.contains(file.id) { ProgressView() } else { Image(systemName: "photo").foregroundStyle(PhoneTheme.mint) } } }
                    }.frame(maxHeight: 340).clipShape(RoundedRectangle(cornerRadius: 18))
                }.buttonStyle(.plain).disabled(media.loading.contains(file.id)).accessibilityLabel("Preview " + file.filename).accessibilityIdentifier("media.image." + file.artifactId).accessibilityValue(media.images[file.id] == nil ? "Loading" : "Ready")
                .task(id: file.id + media.revision.uuidString) { await media.thumbnail(file, client: client) }
            }
            HStack(spacing: 12) {
                if file.isAudio {
                    Button { beforePlayback(); Task { await media.play(file, client: client) } } label: {
                        Image(systemName: playing && !media.paused ? "pause.fill" : "play.fill").font(.subheadline)
                            .frame(width: 44, height: 44).background(PhoneTheme.mint.opacity(0.12), in: Circle())
                    }.accessibilityLabel(playing && !media.paused ? "Pause audio" : "Play " + file.filename).accessibilityIdentifier("media.play." + file.artifactId)
                } else { Image(systemName: file.symbol).foregroundStyle(PhoneTheme.mint) }
                Button { Task { await media.open(file, client: client) } } label: { Text(file.filename).font(.subheadline).lineLimit(2).frame(maxWidth: .infinity, alignment: .leading) }
                if media.loading.contains(file.id) { ProgressView().controlSize(.small) }
                if let url = media.files[file.id] { ShareLink(item: url) { Image(systemName: "square.and.arrow.up").frame(width: 44, height: 44) }.accessibilityLabel("Share " + file.filename) }
                if file.isImage { Button(action: useImage) { Image(systemName: "photo.badge.plus").frame(width: 44, height: 44) }.accessibilityLabel("Use image as reference").accessibilityIdentifier("media.reference." + file.artifactId) }
            }.foregroundStyle(PhoneTheme.mint).buttonStyle(.plain).frame(minHeight: 44)
            if playing {
                TimelineView(.periodic(from: .now, by: 0.25)) { _ in
                    HStack {
                        Text(clock(media.elapsed)).font(.caption.monospacedDigit())
                        Slider(value: Binding(get: { media.elapsed }, set: { media.seek($0) }), in: 0...max(1, media.duration)).tint(PhoneTheme.mint).accessibilityLabel("Audio position")
                        Text(clock(media.duration)).font(.caption.monospacedDigit())
                        Button { media.stop() } label: { Image(systemName: "stop.fill").frame(width: 44, height: 44) }.accessibilityLabel("Stop audio")
                    }.foregroundStyle(PhoneTheme.secondary)
                }
            }
            if let error = media.errors[file.id] { Text(error).font(.caption).foregroundStyle(PhoneTheme.amber).textSelection(.enabled) }
        }.padding(file.isImage ? 0 : 14)
            .background(file.isImage ? Color.clear : PhoneTheme.surface, in: RoundedRectangle(cornerRadius: 18))
            .frame(maxWidth: .infinity, alignment: .leading)
    }
    private func clock(_ value: Double) -> String { let seconds = max(0, Int(value)); return String(format: "%d:%02d", seconds / 60, seconds % 60) }
}
