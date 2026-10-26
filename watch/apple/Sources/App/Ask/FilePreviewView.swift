import AbstractGatewayClient
import SwiftUI

/// A conversation's files, one per page: swipe up or down (or turn the crown) for the file after or
/// before. Each shows what the watch can: a picture, a drawing (SVG, drawn on the watch), the start
/// of a text, a recording or a video to open; otherwise what it is. Its share button is beside Back.
struct FilePreviewView: View {
    let files: [SessionFile]
    @State private var index: Int
    @EnvironmentObject private var model: AppModel

    init(files: [SessionFile], index: Int) {
        self.files = files
        _index = State(initialValue: min(max(0, index), max(0, files.count - 1)))
    }

    var body: some View {
        TabView(selection: $index) {
            ForEach(Array(files.enumerated()), id: \.element.id) { i, file in
                FilePage(file: file, position: files.count > 1 ? "\(i + 1) of \(files.count)" : nil)
                    .tag(i)
            }
        }
        .tabViewStyle(.verticalPage)
        .besideBack {
            if files.indices.contains(index), files[index].fitsTheWatch {
                let file = files[index]
                ShareLink(item: SharedFile(file: file, client: model.client), preview: SharePreview(file.fileName)) {
                    GlassIcon(symbol: "square.and.arrow.up", size: CornerButton.size)
                }
                .buttonStyle(GlassPress())
                .accessibilityLabel("Share \(file.fileName)")
                .accessibilityIdentifier("preview.share")
            }
        }
    }
}

/// One file's page: its name, where it is in the list, and its preview.
private struct FilePage: View {
    let file: SessionFile
    let position: String?
    @EnvironmentObject private var model: AppModel
    @State private var preview: Preview?
    @State private var failed = false

    enum Preview {
        case image(UIImage), drawing(SVGDocument), text(String), open(MediaItem), nothing
    }

    var body: some View {
        VStack(spacing: 4) {
            Text(file.fileName).font(.rounded(.caption2, weight: .semibold)).foregroundStyle(Theme.text2)
                .lineLimit(1).truncationMode(.middle)
                .accessibilityIdentifier("preview.name")
            if let position {
                Text(position).font(.rounded(.caption2)).foregroundStyle(Theme.muted).monospacedDigit()
                    .accessibilityIdentifier("preview.position")
            }
            content.frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .padding(.top, 34)                                   // below Back and the share button
        .task(id: file.id) { await load() }
    }

    @ViewBuilder private var content: some View {
        switch preview {
        case .image(let image):
            Button { if let m = file.media { model.path.append(.media(m)) } } label: {
                Image(uiImage: image).resizable().scaledToFit().clipShape(RoundedRectangle(cornerRadius: 8))
            }
            .buttonStyle(.tap)
            .accessibilityLabel("Image")
            .accessibilityIdentifier("preview.image")
        case .drawing(let doc):
            SVGView(document: doc).clipShape(RoundedRectangle(cornerRadius: 8))
        case .text(let text):
            Text(text).font(.rounded(.caption2)).foregroundStyle(Theme.text)
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                .mask(LinearGradient(colors: [.black, .black, .clear], startPoint: .top, endPoint: .bottom))
                .accessibilityIdentifier("preview.text")
        case .open(let media):
            Button { model.path.append(.media(media)) } label: {
                VStack(spacing: 6) {
                    GlassIcon(symbol: media.kind == .video ? "play.fill" : "waveform", size: 44)
                    Text(media.kind == .video ? "Play the video" : "Play the recording").font(.rounded(.footnote)).foregroundStyle(Theme.text)
                }
            }
            .buttonStyle(.tap)
            .accessibilityIdentifier("preview.open")
        case .nothing:
            what
        case nil:
            if failed {
                VStack(spacing: 6) {
                    Text("Couldn't load this file").font(.rounded(.footnote)).foregroundStyle(Theme.muted)
                    Button("Retry") { Task { await load() } }.buttonStyle(FilledButtonStyle(fill: Theme.neutralButton))
                }
            } else {
                ProgressView()
            }
        }
    }

    /// What it is, when the watch cannot show it.
    private var what: some View {
        VStack(spacing: 6) {
            Image(systemName: file.contentType.contains("pdf") ? "doc.richtext" : "doc").font(.system(size: 30)).foregroundStyle(Theme.cyan)
            Text(file.fitsTheWatch ? "No preview on the watch" : "Too large for the watch")
                .font(.rounded(.footnote)).foregroundStyle(Theme.muted)
            if let size = file.sizeBytes {
                Text(ByteCountFormatter.string(fromByteCount: Int64(size), countStyle: .file)).font(.rounded(.caption2)).foregroundStyle(Theme.muted)
            }
        }
    }

    private var isDrawing: Bool { file.contentType.contains("svg") || file.fileName.lowercased().hasSuffix(".svg") }
    private var isText: Bool {
        let t = file.contentType
        let ext = (file.fileName as NSString).pathExtension.lowercased()
        return t.hasPrefix("text/") || t.contains("json") || t.contains("xml") || t.contains("yaml")
            || ["txt", "md", "csv", "json", "log", "yaml", "yml", "py", "swift", "js", "ts", "html", "css", "sh"].contains(ext)
    }

    private func load() async {
        failed = false
        if let m = file.media, m.kind != .image { preview = .open(m); return }
        guard file.fitsTheWatch, isDrawing || isText || file.contentType.hasPrefix("image/") else { preview = .nothing; return }
        do {
            let data = try await FilePreviewCache.shared.data(file, client: model.client)
            if isDrawing {
                preview = .drawing(try await Task.detached { try SVGDocument.parse(data) }.value)
            } else if file.contentType.hasPrefix("image/") {
                guard let cg = await Task.detached(operation: { MediaStore.downsample(data, maxPixel: 600) }).value else { preview = .nothing; return }
                preview = .image(UIImage(cgImage: cg))
            } else {
                let text = String(decoding: data.prefix(4000), as: UTF8.self)
                preview = .text(String(text.prefix(1200)))
            }
        } catch is CancellationError {
        } catch {
            failed = preview == nil
        }
    }
}

/// The files looked at, kept while the app runs (paging back and forth does not read them again).
@MainActor final class FilePreviewCache {
    static let shared = FilePreviewCache()
    private var kept: [String: Data] = [:]
    private var order: [String] = []
    private let maxBytes = 30 * 1024 * 1024

    func data(_ file: SessionFile, client: any GatewayClient) async throws -> Data {
        if let d = kept[file.id] { return d }
        let d = try await client.fileData(file)
        kept[file.id] = d; order.append(file.id)
        while kept.values.reduce(0, { $0 + $1.count }) > maxBytes, let oldest = order.first {
            order.removeFirst(); kept[oldest] = nil
        }
        return d
    }
}
