import AbstractGatewayClient
import SwiftUI

/// What needs you, oldest first. One tap opens it; the screen closes itself once nothing is left.
struct WaitsView: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        List(model.waits) { w in
            NavigationLink(value: w.kind == .askUser ? Route.askUser(w) : Route.approval(w)) {
                HStack(spacing: 8) {
                    Image(systemName: w.kind == .askUser ? "questionmark.bubble" : model.isOutreach(w) ? "paperplane" : "checkmark.shield")
                        .font(.rounded(.body)).foregroundStyle(Theme.amber).frame(width: 22)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(w.headline).font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.text).lineLimit(2)
                        if w.kind != .askUser, let d = w.recipient ?? w.primaryArgument?.value {
                            Text(d).font(.rounded(.caption2)).foregroundStyle(Theme.muted).lineLimit(1)
                        }
                    }
                }
                .padding(.vertical, 2)
            }
        }
        .screen("Needs you")
        .refreshable { await model.refresh() }
        .onChange(of: model.waits.isEmpty) { _, empty in if empty, model.path.last == .waits { model.path.removeLast() } }
    }
}
