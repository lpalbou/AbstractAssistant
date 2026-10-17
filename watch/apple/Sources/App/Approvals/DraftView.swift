import AbstractGatewayClient
import SwiftUI

/// The email the assistant wants to send, in full. Nothing here is sent; the decision stays on
/// the approval.
struct DraftView: View {
    let wait: Wait

    private var args: [String: JSONValue] { wait.details?.first?.arguments ?? [:] }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 6) {
                if let subject = args["subject"]?.stringValue {
                    Text(subject).font(.rounded(.headline)).foregroundStyle(Theme.text)
                }
                if let to = args["to"]?.displayText {
                    Text("To \(to)").font(.rounded(.caption2)).foregroundStyle(Theme.muted).lineLimit(2)
                }
                if let body = args["body_text"]?.stringValue ?? args["body"]?.stringValue ?? args["text"]?.stringValue {
                    MarkdownText(body).padding(.top, 2)
                } else if args["body_html"] != nil {
                    Text("Read this email on your Mac").font(.rounded(.footnote)).foregroundStyle(Theme.muted)
                }
            }
            .padding(.horizontal, 4)
        }
        .screen("")
    }
}
