import AbstractGatewayClient
import SwiftUI

/// An earlier message of a conversation, as a card under the orb (as an automation's earlier runs).
struct MessageRow: View {
    let exchange: Exchange
    var body: some View {
        MessageRowCard(text: exchange.answer) { QuestionCaption(text: exchange.prompt, lines: 1) }
    }
}

/// One earlier message, opened from its card (as an automation's earlier run): the question with
/// Read aloud, then the answer in full.
struct MessageView: View {
    let title: String
    let exchange: Exchange

    var body: some View {
        MessagePage(text: exchange.answer,
                    read: exchange.scope.flatMap { scope in exchange.answer.isEmpty ? nil : ReadItem(title: title, text: exchange.answer, scope: scope) }) {
            QuestionCaption(text: exchange.prompt, lines: 4)
        }
    }
}
