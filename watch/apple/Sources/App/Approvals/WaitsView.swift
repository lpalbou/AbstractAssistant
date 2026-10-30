import AbstractGatewayClient
import SwiftUI

/// What needs you, oldest first. A notification may open this before the first read, or after a
/// gate was handled: keep its checking, failure and confirmed-empty states visible.
struct WaitsView: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        List {
            if model.waits.isEmpty {
                switch model.waitsReadState {
                case .checking:
                    HStack(spacing: 8) {
                        ProgressView().frame(width: 20, height: 20)
                        Text("Checking what needs you…")
                            .font(.rounded(.footnote)).foregroundStyle(Theme.muted)
                    }
                    .accessibilityIdentifier("waits.checking")
                case .failed(let message):
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Couldn't check what needs you.").foregroundStyle(Theme.text)
                        Text(message).font(.rounded(.footnote)).foregroundStyle(Theme.muted)
                        Button("Retry") { Task { await model.refresh(checkingWaits: true) } }
                            .accessibilityIdentifier("waits.retry")
                    }
                case .ready:
                    Text("Nothing needs you now.")
                        .foregroundStyle(Theme.muted)
                        .accessibilityIdentifier("waits.empty")
                }
            }
            ForEach(model.waits) { w in
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
        }
        .screen("Needs you")
        .refreshable { await model.refresh(checkingWaits: true) }
        .task { await model.refresh(checkingWaits: true) }
    }
}
