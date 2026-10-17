import AbstractGatewayClient
import SwiftUI

/// The full content of an outreach tool call (an email the agent wants to send): recipient,
/// subject and body, verbatim from the tool arguments. Nothing here is sent; the decision stays
/// on the approval card.
struct DraftView: View {
    let wait: Wait

    private var args: [String: JSONValue] { wait.details?.first?.arguments ?? [:] }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 6) {
                if let to = args["to"]?.displayText { field("To", to) }
                if let subject = args["subject"]?.stringValue { field("Subject", subject) }
                if let body = args["body_text"]?.stringValue ?? args["body"]?.stringValue ?? args["text"]?.stringValue {
                    Card {
                        MarkdownText(body)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                } else if args["body_html"] != nil {
                    Text("HTML body: open on the Mac to read it").font(.rounded(.caption2)).foregroundStyle(Theme.muted)
                }
                Footnote(text: "verbatim tool arguments · run \(wait.runId.prefix(6))", mono: true)
            }
        }
        .screen("Draft")
    }

    private func field(_ k: String, _ v: String) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(k.uppercased()).font(.rounded(.caption2, weight: .semibold)).foregroundStyle(Theme.muted)
            Text(v).font(.rounded(.footnote)).foregroundStyle(Theme.text2)
        }
    }
}
