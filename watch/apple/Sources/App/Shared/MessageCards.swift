import AbstractGatewayClient
import SwiftUI

// One look for a message wherever it shows: an automation's results and a conversation's messages
// share these three views (the same caption, font and size).

/// A message in full: a caption line inside the card (when it ran, or the question asked), then
/// the text in markdown at the reading size, then the images, recordings and videos it made. Red
/// border when it failed.
struct MessageCard<Caption: View>: View {
    let text: String
    var failed = false
    var media: [MediaItem] = []
    /// Plays a recording through the orb (on the orb page); nil: it plays on its own.
    var play: ((MediaItem) -> Void)? = nil
    @ViewBuilder let caption: () -> Caption
    var body: some View {
        Card(stroke: failed ? Theme.red.opacity(0.6) : nil) {
            VStack(alignment: .leading, spacing: 4) {
                caption()
                if !text.isEmpty || media.isEmpty { MarkdownText(text.isEmpty ? "No answer" : text) }
                if !media.isEmpty { MediaStrip(items: media, play: play).padding(.top, 2) }
            }
        }
    }
}

/// An earlier message as a compact card: its caption, the first two lines, a chevron (it opens).
struct MessageRowCard<Caption: View>: View {
    let text: String
    var media: [MediaItem] = []
    @ViewBuilder let caption: () -> Caption
    var body: some View {
        Card {
            HStack(spacing: 6) {
                VStack(alignment: .leading, spacing: 2) {
                    caption()
                    Text(text.isEmpty ? "No answer" : SpeechText.plain(text))
                        .font(.rounded(.footnote)).foregroundStyle(Theme.text2).lineLimit(2)
                }
                Spacer(minLength: 2)
                // It made an image, a recording or a video: open it to see.
                if let symbol = MediaItem.symbol(of: media) {
                    Image(systemName: symbol).font(.caption2).foregroundStyle(Theme.cyan).accessibilityLabel("With media")
                }
                Image(systemName: "chevron.right").font(.caption2).foregroundStyle(Theme.muted)
            }
        }
    }
}

/// One message on its own page (opened from its card): the caption with Read aloud, then the text.
struct MessagePage<Caption: View>: View {
    let text: String
    let read: ReadItem?
    var media: [MediaItem] = []
    var footer: AnyView? = nil
    @ViewBuilder let caption: () -> Caption
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                HStack(alignment: .top) {
                    caption()
                    Spacer(minLength: 4)
                    if let read { ReadAloudLink(item: read) }
                }
                if !text.isEmpty || media.isEmpty { MarkdownText(text.isEmpty ? "No answer" : text) }
                if !media.isEmpty { MediaStrip(items: media) }
                if let footer { footer }
            }
            .padding(.horizontal, 4)
        }
        .screen("")
    }
}

/// A message's caption, the same for a conversation and an automation: when its trigger sent it (an
/// automation's run, "Failed" in red when it failed), then the message sent.
struct ExchangeCaption: View {
    let exchange: Exchange
    var lines = 2
    var body: some View {
        VStack(alignment: .leading, spacing: 1) {
            if exchange.when != nil || exchange.failed {
                HStack(spacing: 6) {
                    if let when = exchange.when {
                        Text(when).font(.rounded(.caption2)).foregroundStyle(Theme.muted).lineLimit(1).minimumScaleFactor(0.7)
                    }
                    if exchange.failed {
                        Text("Failed").font(.rounded(.caption2, weight: .semibold)).foregroundStyle(Theme.red).fixedSize()
                    }
                }
            }
            QuestionCaption(text: exchange.prompt, lines: lines)
        }
    }
}

/// A conversation message's caption: the question asked, as an automation's date line.
struct QuestionCaption: View {
    let text: String
    var lines = 2
    var body: some View {
        if !text.isEmpty {
            Text(text).font(.rounded(.caption2)).foregroundStyle(Theme.muted).lineLimit(lines)
        }
    }
}
