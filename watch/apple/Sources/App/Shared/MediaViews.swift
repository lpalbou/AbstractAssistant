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
    /// An SVG picture, drawn on the watch.
    @State private var drawing: SVGDocument?
    @State private var video: AVPlayer?
    @State private var failed = false
    @State private var zoom = 1.0
    @State private var offset = CGSize.zero
    @State private var dragStart = CGSize.zero

    var body: some View {
        GeometryReader { geo in
            Group {
                if let drawing {
                    let rest = Self.restFrame(drawing.viewBox.size, area: geo.size)
                    SVGView(document: drawing).frame(width: rest.width, height: rest.height)
                        .position(x: rest.midX, y: rest.midY)
                        .frame(width: geo.size.width, height: geo.size.height)
                } else if let image {
                    // The picture's own frame is where it rests; the zoomed picture is seen through the
                    // page's area (below the top row) and `clamp` keeps it there.
                    let rest = Self.restFrame(image.size, area: geo.size)
                    ZStack {
                        // The zoom and the drag take the whole area (a finger beside a wide picture still
                        // moves it); the picture itself is drawn above and is the page's element, so
                        // `media.full` is the picture's own frame, not the area around it.
                        Color.clear
                            .contentShape(Rectangle())
                            .gesture(DragGesture()
                                .onChanged { v in
                                    guard zoom > 1.01 else { return }
                                    offset = clamp(CGSize(width: dragStart.width + v.translation.width, height: dragStart.height + v.translation.height), rest, geo.size)
                                }
                                .onEnded { _ in dragStart = offset })
                            .onTapGesture(count: 2) { withAnimation { zoom = 1; offset = .zero; dragStart = .zero } }
                            .focusable()
                            .digitalCrownRotation($zoom, from: 1, through: 4, by: 0.05, sensitivity: .low,
                                                  isContinuous: false, isHapticFeedbackEnabled: true)
                            .onChange(of: zoom) { _, z in offset = clamp(offset, rest, geo.size); dragStart = offset; model.swipesPaused = z > 1.01 }
                            .onDisappear { model.swipesPaused = false }
                            .accessibilityHidden(true)
                        Image(uiImage: image).resizable()
                            .frame(width: rest.width, height: rest.height)
                            .scaleEffect(zoom)
                            .offset(offset)
                            .allowsHitTesting(false)
                            .accessibilityLabel("Image")
                            .accessibilityIdentifier("media.full")
                            .position(x: rest.midX, y: rest.midY)
                    }
                    .frame(width: geo.size.width, height: geo.size.height)
                    .clipped()
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
        // The top row once, with Share beside Back: `besideBack` is the screen (a `.screen("")` beside it
        // drew a second band, which pushed Share and the picture a band lower).
        .besideBack {
            if let image { ShareIcon(item: Image(uiImage: image), subject: "Image") }
        }
        .task { await load() }
        .onDisappear { video?.pause() }
    }

    /// Where a picture rests in the page's area (`area`: below the top row, down to the screen's
    /// bottom): fitted to the whole screen and centred on it, so a wide picture sits in the middle of
    /// the page; when that would put its top under the row's band (a tall picture), fitted to the area
    /// instead, as near the screen's centre as the band allows (a picture as tall as the area fills it).
    static func restFrame(_ picture: CGSize, area: CGSize) -> CGRect {
        guard picture.width > 0, picture.height > 0, area.width > 0, area.height > 0 else { return CGRect(origin: .zero, size: area) }
        let band = CornerButton.band, screen = CGSize(width: area.width, height: area.height + band)
        func fit(_ box: CGSize) -> CGSize {
            let s = min(box.width / picture.width, box.height / picture.height)
            return CGSize(width: picture.width * s, height: picture.height * s)
        }
        var size = fit(screen), top = (screen.height - size.height) / 2
        if top < band { size = fit(area); top = max(band, (screen.height - size.height) / 2) }
        return CGRect(x: (area.width - size.width) / 2, y: top - band, width: size.width, height: size.height)
    }

    /// A zoomed picture never leaves an empty edge in the area: on each side where it is larger than
    /// the area it covers it, where smaller it stays wholly inside it; unzoomed, it rests.
    private func clamp(_ o: CGSize, _ rest: CGRect, _ area: CGSize) -> CGSize {
        guard zoom > 1.01 else { return .zero }
        func axis(_ o: CGFloat, _ start: CGFloat, _ length: CGFloat, _ view: CGFloat) -> CGFloat {
            let half = length * zoom / 2, centre = start + length / 2
            let a = half - centre, b = view - half - centre      // an edge of the picture on an edge of the area
            return min(max(a, b), max(min(a, b), o))
        }
        return CGSize(width: axis(o.width, rest.minX, rest.width, area.width), height: axis(o.height, rest.minY, rest.height, area.height))
    }

    private func load() async {
        failed = false
        do {
            switch item.kind {
            case .image where item.contentType.contains("svg"):
                let data = try await MediaStore.shared.data(item, client: model.client)
                drawing = try await Task.detached { try SVGDocument.parse(data) }.value
            case .image: image = try await MediaStore.shared.image(item, client: model.client, maxPixel: 1200)
            case .video: video = AVPlayer(url: try await MediaStore.shared.file(item, client: model.client))
            case .audio: failed = true
            }
        } catch { failed = true }
    }
}
