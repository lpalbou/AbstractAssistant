@preconcurrency import AVFoundation
import AVKit
import AbstractGatewayClient
import ImageIO
import SwiftUI
import WatchKit

/// The media of answers on this watch: each item is downloaded once (an image shows in several
/// places) and kept in the watch's caches; pictures are made small here (a generated image is 1–3 MB,
/// a few hundred pixels are shown).
@MainActor
final class MediaStore {
    static let shared = MediaStore()
    private var inflight: [String: Task<Data, Error>] = [:]
    /// Decoded pictures, by item and size, within a memory budget (a full-screen one is ~6 MB).
    private let images: NSCache<NSString, UIImage> = {
        let c = NSCache<NSString, UIImage>(); c.totalCostLimit = 24 * 1024 * 1024; return c
    }()
    private let dir = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0].appending(path: "media")
    /// The most the cache keeps; the oldest files go first.
    private static let cacheBytes = 150 * 1024 * 1024

    func data(_ item: MediaItem, client: any GatewayClient) async throws -> Data {
        let file = dir.appending(path: item.artifactId)
        if let d = try? Data(contentsOf: file) { return d }
        if let t = inflight[item.artifactId] { return try await t.value }
        let t = Task { try await client.mediaData(item) }
        inflight[item.artifactId] = t
        defer { inflight[item.artifactId] = nil }
        let d = try await t.value
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        try? d.write(to: file, options: .atomic)
        prune()
        return d
    }

    /// The picture at most `maxPixel` on its long side.
    func image(_ item: MediaItem, client: any GatewayClient, maxPixel: Int) async throws -> UIImage {
        let key = "\(item.artifactId)@\(maxPixel)" as NSString
        if let i = images.object(forKey: key) { return i }
        let d = try await data(item, client: client)
        let small = await Task.detached(priority: .userInitiated) { Picture(Self.downsample(d, maxPixel: maxPixel)) }.value
        guard let cg = small.image else { throw GatewayError.invalidResponse }
        let image = UIImage(cgImage: cg)
        images.setObject(image, forKey: key, cost: cg.bytesPerRow * cg.height)
        return image
    }

    /// A file to play from (video), named with its kind's extension.
    func file(_ item: MediaItem, client: any GatewayClient) async throws -> URL {
        let d = try await data(item, client: client)
        let ext = item.contentType.split(separator: "/").last.map { $0 == "quicktime" ? "mov" : String($0) } ?? "mp4"
        let url = FileManager.default.temporaryDirectory.appending(path: "\(item.artifactId).\(ext)")
        if !FileManager.default.fileExists(atPath: url.path()) { try d.write(to: url, options: .atomic) }
        return url
    }

    /// A recording's length, read from its cached file (not a second copy in memory).
    func duration(_ item: MediaItem, client: any GatewayClient) async throws -> Double {
        _ = try await data(item, client: client)
        let t = item.contentType.lowercased()
        let hint = t.contains("wav") ? AVFileType.wav : t.contains("mpeg") || t.contains("mp3") ? AVFileType.mp3 : t.contains("aac") || t.contains("mp4") ? AVFileType.m4a : nil
        return try AVAudioPlayer(contentsOf: dir.appending(path: item.artifactId), fileTypeHint: hint?.rawValue).duration
    }

    /// Signed out or another account: nothing of the previous one stays on the watch.
    func clear() {
        inflight.values.forEach { $0.cancel() }; inflight = [:]
        images.removeAllObjects()
        try? FileManager.default.removeItem(at: dir)
    }

    private struct Picture: @unchecked Sendable { let image: CGImage?; init(_ i: CGImage?) { image = i } }

    nonisolated static func downsample(_ data: Data, maxPixel: Int) -> CGImage? {
        guard let source = CGImageSourceCreateWithData(data as CFData, [kCGImageSourceShouldCache: false] as CFDictionary) else { return nil }
        return CGImageSourceCreateThumbnailAtIndex(source, 0, [
            kCGImageSourceCreateThumbnailFromImageAlways: true, kCGImageSourceCreateThumbnailWithTransform: true,
            kCGImageSourceShouldCacheImmediately: true, kCGImageSourceThumbnailMaxPixelSize: maxPixel,
        ] as CFDictionary)
    }

    private func prune() {
        let keys: [URLResourceKey] = [.contentModificationDateKey, .fileSizeKey]
        guard let files = try? FileManager.default.contentsOfDirectory(at: dir, includingPropertiesForKeys: keys) else { return }
        var rows = files.compactMap { f -> (URL, Date, Int)? in
            guard let v = try? f.resourceValues(forKeys: Set(keys)) else { return nil }
            return (f, v.contentModificationDate ?? .distantPast, v.fileSize ?? 0)
        }
        var total = rows.reduce(0) { $0 + $1.2 }
        rows.sort { $0.1 < $1.1 }
        while total > Self.cacheBytes, let oldest = rows.first {
            try? FileManager.default.removeItem(at: oldest.0); total -= oldest.2; rows.removeFirst()
        }
    }
}

/// The media under an answer: each image as a picture (it opens full screen), each recording as a
/// row that plays it, each video as a row that opens it.
struct MediaStrip: View {
    let items: [MediaItem]
    /// Plays a recording through the orb (the conversation's voice); nil: it plays on its own.
    var play: ((MediaItem) -> Void)? = nil
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(items) { item in
                switch item.kind {
                case .image:
                    NavigationLink(value: Route.media(item)) { MediaThumbnail(item: item) }
                        .buttonStyle(.tap)
                        .accessibilityLabel("Image. Opens full screen")
                        .accessibilityIdentifier("media.image")
                case .audio:
                    AudioClipRow(item: item, play: play)
                case .video:
                    NavigationLink(value: Route.media(item)) {
                        MediaRowLabel(symbol: "play.rectangle.fill", title: "Video", detail: item.sizeText)
                    }
                    .buttonStyle(.tap)
                    .accessibilityIdentifier("media.video")
                }
            }
        }
    }
}

extension MediaItem {
    /// "2.1 MB" when the gateway said how big it is.
    var sizeText: String? {
        sizeBytes.map { ByteCountFormatter.string(fromByteCount: Int64($0), countStyle: .file) }
    }
    /// The symbol for a message card that carries media (on the small cards of earlier messages).
    static func symbol(of items: [MediaItem]) -> String? {
        if items.contains(where: { $0.kind == .image }) { return "photo" }
        if items.contains(where: { $0.kind == .video }) { return "play.rectangle" }
        if items.contains(where: { $0.kind == .audio }) { return "waveform" }
        return nil
    }
}

/// An image under its answer, as wide as the card, shrunk on the watch.
struct MediaThumbnail: View {
    let item: MediaItem
    /// A small square (a search result's picture); nil: as wide as the card.
    var side: CGFloat? = nil
    @EnvironmentObject private var model: AppModel
    @State private var image: UIImage?
    @State private var failed = false

    var body: some View {
        Group {
            if let image, let side {
                Image(uiImage: image).resizable().scaledToFill().frame(width: side, height: side)
                    .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
            } else if let image {
                Image(uiImage: image).resizable().scaledToFit()
                    .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            } else {
                RoundedRectangle(cornerRadius: side == nil ? 12 : 8, style: .continuous).fill(Theme.card)
                    .frame(width: side, height: side ?? 96)
                    .overlay {
                        if failed {
                            VStack(spacing: 4) {
                                Image(systemName: "photo").foregroundStyle(Theme.muted)
                                Text("Couldn't load the image").font(.rounded(.caption2)).foregroundStyle(Theme.muted)
                            }
                        } else {
                            ProgressView()
                        }
                    }
            }
        }
        .frame(maxWidth: side == nil ? .infinity : side)
        .task(id: item.id) {
            failed = false
            do { image = try await MediaStore.shared.image(item, client: model.client, maxPixel: 400) } catch { failed = true }
        }
    }
}

/// A recording or a video under its answer: a pill with its symbol, its title and a detail (its
/// length, or its size until it is known).
struct MediaRowLabel: View {
    let symbol: String
    let title: String
    var detail: String?
    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: symbol).font(.system(size: 22, weight: .semibold)).foregroundStyle(Theme.cyan)
            VStack(alignment: .leading, spacing: 0) {
                Text(title).font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.text)
                if let detail { Text(detail).font(.rounded(.caption2)).foregroundStyle(Theme.muted).lineLimit(2) }
            }
            Spacer(minLength: 2)
        }
        .padding(.leading, 6).padding(.trailing, 10).padding(.vertical, 6)
        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
        .background(Theme.line.opacity(0.7), in: Capsule())
    }
}

/// A recording: tap plays it (through the orb on the orb page, else here), tap again pauses.
struct AudioClipRow: View {
    let item: MediaItem
    var play: ((MediaItem) -> Void)?
    @EnvironmentObject private var model: AppModel
    @StateObject private var speaker = Speaker()
    /// Its length, once read (a recording is small: it is fetched when shown).
    @State private var seconds: Double?

    var body: some View {
        Button {
            if let play { play(item); return }
            switch speaker.state {
            case .speaking, .preparing: speaker.pause()
            case .paused: speaker.resume()
            default: speaker.play(clips: [item], client: model.client)
            }
            WKInterfaceDevice.current().play(.click)
        } label: {
            MediaRowLabel(symbol: symbol, title: "Recording", detail: detail)
        }
        .buttonStyle(.tap)
        .accessibilityLabel(play == nil && speaker.isActive ? "Pause the recording" : "Play the recording")
        .accessibilityIdentifier("media.audio")
        .onDisappear { speaker.stop() }
        .task(id: item.id) { seconds = try? await MediaStore.shared.duration(item, client: model.client) }
    }

    private var symbol: String {
        guard play == nil else { return "play.circle.fill" }
        return speaker.isActive ? "pause.circle.fill" : "play.circle.fill"
    }
    private var detail: String? {
        if play == nil {
            switch speaker.state {
            case .preparing: return "Loading…"
            case .failed(let why): return why
            default: break
            }
        }
        if let seconds { return Duration.seconds(seconds.rounded(.up)).formatted(.time(pattern: .minuteSecond)) }
        return item.sizeText
    }
}

/// One image full screen (turn the Digital Crown to zoom, drag to look around, double tap to fit),
/// or one video.
struct MediaPage: View {
    let item: MediaItem
    @EnvironmentObject private var model: AppModel
    @State private var image: UIImage?
    @State private var video: AVPlayer?
    @State private var failed = false
    @State private var zoom = 1.0
    @State private var offset = CGSize.zero
    @State private var dragStart = CGSize.zero

    var body: some View {
        GeometryReader { geo in
            Group {
                if let image {
                    Image(uiImage: image).resizable().scaledToFit()
                        .scaleEffect(zoom)
                        .offset(offset)
                        .frame(width: geo.size.width, height: geo.size.height)
                        .clipped()
                        .contentShape(Rectangle())
                        .gesture(DragGesture()
                            .onChanged { v in
                                guard zoom > 1.01 else { return }
                                offset = clamp(CGSize(width: dragStart.width + v.translation.width, height: dragStart.height + v.translation.height), geo.size)
                            }
                            .onEnded { _ in dragStart = offset })
                        .onTapGesture(count: 2) { withAnimation { zoom = 1; offset = .zero; dragStart = .zero } }
                        .focusable()
                        .digitalCrownRotation($zoom, from: 1, through: 4, by: 0.05, sensitivity: .low,
                                              isContinuous: false, isHapticFeedbackEnabled: true)
                        .onChange(of: zoom) { _, _ in offset = clamp(offset, geo.size); dragStart = offset }
                        .accessibilityLabel("Image")
                        .accessibilityIdentifier("media.full")
                } else if let video {
                    VideoPlayer(player: video).onAppear { video.play() }
                } else if failed {
                    VStack(spacing: 8) {
                        Text(item.kind == .video ? "Couldn't load the video" : "Couldn't load the image")
                            .font(.rounded(.footnote)).foregroundStyle(Theme.muted)
                        Button("Retry") { Task { await load() } }.buttonStyle(FilledButtonStyle(fill: Theme.neutralButton))
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
        }
        .ignoresSafeArea(edges: .bottom)
        .besideBack {
            if let image { ShareIcon(item: Image(uiImage: image), subject: "Image") }
        }
        .screen("")
        .task { await load() }
        .onDisappear { video?.pause() }
    }

    /// A zoomed picture never leaves an empty edge on screen.
    private func clamp(_ o: CGSize, _ size: CGSize) -> CGSize {
        let maxX = size.width * (zoom - 1) / 2, maxY = size.height * (zoom - 1) / 2
        return CGSize(width: min(maxX, max(-maxX, o.width)), height: min(maxY, max(-maxY, o.height)))
    }

    private func load() async {
        failed = false
        do {
            switch item.kind {
            case .image: image = try await MediaStore.shared.image(item, client: model.client, maxPixel: 1200)
            case .video: video = AVPlayer(url: try await MediaStore.shared.file(item, client: model.client))
            case .audio: failed = true
            }
        } catch { failed = true }
    }
}
