import AbstractGatewayClient
import SwiftUI
import WatchKit

/// A tapped link. watchOS has no browser view an app can embed, and the system's web view refused
/// every page in testing (2026-10-17, watchOS 27.0.1: "URL failed to load"). So the watch reads the
/// page itself: it fetches it, shows the title and the readable text, can read it aloud, and hands
/// the URL to the iPhone (Handoff: Safari offers it in the app switcher). The system web view stays
/// one tap away.
struct LinkView: View {
    let url: URL
    @EnvironmentObject private var model: AppModel
    @State private var page: WebPageText?
    @State private var error: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 6) {
                Text(page?.title ?? url.host() ?? url.absoluteString)
                    .font(.rounded(.headline)).foregroundStyle(Theme.text).lineLimit(4)
                Text(url.absoluteString).font(.mono(.caption2)).foregroundStyle(Theme.muted).lineLimit(2)
                if let page {
                    if let run = model.runs.first, !page.text.isEmpty {
                        ReadAloudLink(item: ReadItem(title: url.host() ?? "Page", text: page.markdown, scope: .run(run.runId)))
                    }
                    Card { MarkdownText(page.markdown.isEmpty ? "This page has no readable text." : page.markdown) }
                } else if let error {
                    Text(error).font(.rounded(.caption2)).foregroundStyle(Theme.red)
                } else {
                    HStack(spacing: 6) { ProgressView().frame(width: 18); Text("reading the page…").font(.rounded(.caption2)).foregroundStyle(Theme.muted) }
                }
                Label("Continue on iPhone: open the app switcher there", systemImage: "iphone")
                    .font(.rounded(.caption2)).foregroundStyle(Theme.muted)
                Button("Open in the watch browser") { WKApplication.shared().openSystemURL(url) }
                    .buttonStyle(FilledButtonStyle(fill: Theme.neutralButton, foreground: Theme.text2))
            }
        }
        .screen("Link")
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
            guard (200..<400).contains(status) else { error = "The page answered \(status)."; return }
            let type = (resp as? HTTPURLResponse)?.value(forHTTPHeaderField: "Content-Type") ?? ""
            let body = String(decoding: data.prefix(1_500_000), as: UTF8.self)
            page = type.contains("html") || body.lowercased().contains("<html") ? WebPageText(html: body)
                : WebPageText(title: nil, paragraphs: [String(body.prefix(6000))])
        } catch {
            self.error = "Could not read the page: \(error.localizedDescription)"
        }
    }
}
