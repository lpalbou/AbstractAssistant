import SwiftUI

struct ApprovalDoneView: View {
    let workflow: String
    @EnvironmentObject private var model: AppModel

    var body: some View {
        ScrollView {
            VStack(spacing: 8) {
                Image(systemName: "checkmark").font(.system(size: 30, weight: .bold)).foregroundStyle(Theme.ground)
                    .frame(width: 58, height: 58).background(Theme.green, in: Circle())
                    .padding(6).background(Theme.green.opacity(0.15), in: Circle())
                Text("Allowed once").font(.rounded(.title3, weight: .bold)).foregroundStyle(Theme.text)
                Text("recorded in the run ledger").font(.rounded(.caption2)).foregroundStyle(Theme.muted)
                Card(stroke: Theme.line) {
                    HStack(spacing: 6) {
                        StatusDot(color: Theme.green)
                        VStack(alignment: .leading, spacing: 1) {
                            Text("\(workflow) continues").font(.rounded(.footnote, weight: .medium)).foregroundStyle(Theme.text)
                            Text("on your gateway").font(.rounded(.caption2)).foregroundStyle(Theme.muted)
                        }
                    }
                }
                if !model.waits.isEmpty {
                    Button("\(model.waits.count) still waiting for you") {
                        let w = model.waits[0]
                        model.path = [w.kind == .askUser ? .askUser(w) : .approval(w)]
                    }
                    .buttonStyle(.plain).font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.amber)
                }
            }
        }
        .screen("Approval")
    }
}
