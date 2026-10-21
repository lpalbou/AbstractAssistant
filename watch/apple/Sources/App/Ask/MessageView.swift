import AbstractGatewayClient
import SwiftUI

/// An earlier message of a conversation (or an automation's earlier run), as a card under the orb.
struct MessageRow: View {
    let exchange: Exchange
    var body: some View {
        MessageRowCard(text: exchange.answer, media: exchange.media) { ExchangeCaption(exchange: exchange, lines: 1) }
    }
}

/// One earlier message, opened from its card: the message sent with Read aloud, then the answer in full.
struct MessageView: View {
    let title: String
    let exchange: Exchange

    var body: some View {
        MessagePage(text: exchange.answer,
                    read: exchange.scope.flatMap { scope in exchange.answer.isEmpty ? nil : ReadItem(title: title, text: exchange.answer, scope: scope) },
                    media: exchange.media, footer: AnyView(WorkLink(runId: exchange.id))) {
            ExchangeCaption(exchange: exchange, lines: 4)
        }
    }
}
