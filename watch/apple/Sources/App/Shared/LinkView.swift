import AbstractGatewayClient
import SwiftUI
import WatchKit

/// A tapped link. watchOS has no browser view an app can embed, and the system's web view refused
/// every page in testing (2026-10-17, watchOS 27.0.1: "URL failed to load"). So the watch reads the
/// page itself: it fetches it, shows the title and the readable text, can read it aloud, and hands
/// the URL to the iPhone (Handoff: Safari offers it in the app switcher). A page shows its lead image
/// (the one it gives for link previews) above its text; a link to an image shows the image.
struct LinkView: View {
    let url: URL
    @EnvironmentObject private var model: AppModel
    @State private var page: WebPageText?
    @State private var error: String?
    /// The image: the link's own (a link to a picture), or the page's lead image.
    @State private var picture: UIImage?

    var body: some View {
        FitScroll {
            VStack(alignment: .leading, spacing: 6) {
                HStack(alignment: .top) {
                    Text(page?.title ?? url.host() ?? url.absoluteString)
                        .font(.rounded(.headline)).foregroundStyle(Theme.text).lineLimit(4)
                    Spacer(minLength: 4)
                    if let page, let run = model.runs.first, !page.text.isEmpty {
                        ReadAloudLink(item: ReadItem(title: url.host() ?? "Page", text: page.markdown, scope: .run(run.runId)))
                    }
                }
                if let picture {
                    Image(uiImage: picture).resizable().scaledToFit()
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                        .accessibilityLabel(page?.title ?? "Image")
                        .accessibilityIdentifier("link.image")
                }
                if let page, !(picture != nil && page.paragraphs.isEmpty && page.title == nil) {
                    MarkdownText(page.markdown.isEmpty ? "Nothing to read on this page." : page.markdown)
                } else if let error {
                    Text(error).font(.rounded(.footnote)).foregroundStyle(Theme.muted)
                } else {
                    ProgressView().frame(maxWidth: .infinity).padding(.top, 8)
                }
            }
            .padding(.horizontal, 4)
        }
        .screen("")
        .besideBack { ShareIcon(item: url, subject: page?.title) }   // send the link on (the watch has no clipboard)
        .userActivity("NSUserActivityTypeBrowsingWeb") { activity in
            activity.webpageURL = url
            activity.isEligibleForHandoff = true
            activity.title = page?.title
        }
        .task { await load() }
    }

    private func load() async {
        var req = URLRequest(url: url)
        req.timeoutInterval = 25
        req.setValue("Mozilla/5.0 (Apple Watch) AbstractAssistant", forHTTPHeaderField: "User-Agent")
        do {
            let (data, resp) = try await URLSession.shared.data(for: req)
            let status = (resp as? HTTPURLResponse)?.statusCode ?? 200
            guard (200..<400).contains(status) else { error = "This page didn't open."; return }
            let type = (resp as? HTTPURLResponse)?.value(forHTTPHeaderField: "Content-Type") ?? ""
            if type.hasPrefix("image/") {
                // A link to a picture: the picture itself, made small for the watch.
                guard let image = Self.small(data) else { error = "This image didn't open."; return }
                picture = image
                page = WebPageText(title: nil, paragraphs: [])
                return
            }
            let body = String(decoding: data.prefix(1_500_000), as: UTF8.self)
            page = type.contains("html") || body.lowercased().contains("<html") ? WebPageText(html: body, base: resp.url ?? url)
                : WebPageText(title: nil, paragraphs: [String(body.prefix(6000))])
            // Its lead image, after the text is on screen (a failure shows the text alone).
            if let lead = page?.image, let (bytes, _) = try? await URLSession.shared.data(from: lead) { picture = Self.small(bytes) }
        } catch {
            self.error = "Couldn't open this page."
        }
    }

    /// A picture at most 400 px on its long side (a full-size photo would not fit in a watch's memory).
    private static func small(_ data: Data) -> UIImage? {
        MediaStore.downsample(data, maxPixel: 400).map { UIImage(cgImage: $0) }
    }
}
