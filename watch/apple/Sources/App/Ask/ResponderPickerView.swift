import AbstractGatewayClient
import SwiftUI

/// Who answers an Ask: the gateway's default agent workflow, or one of the user's entities
/// (`GET /api/gateway/entities` lists the entities the signed-in account may visit; an entity
/// conversation uses `POST /entities/{name}/chat/open` and `.../turn`).
struct ResponderPickerView: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        ScrollView {
            VStack(spacing: 6) {
                row(.assistant, title: "Assistant", detail: "the gateway's default agent workflow", color: Theme.cyan)
                if model.entities.isEmpty {
                    Text(model.client.isMock ? "" : "No entities on this account yet. Create one on the gateway, or ask its creator to share it.")
                        .font(.rounded(.caption2)).foregroundStyle(Theme.muted).multilineTextAlignment(.center)
                } else {
                    Text("ENTITIES").font(.rounded(.caption2, weight: .semibold)).foregroundStyle(Theme.muted)
                        .frame(maxWidth: .infinity, alignment: .leading).padding(.top, 4)
                    ForEach(model.entities) { e in
                        row(.entity(e.name), title: e.name.capitalized, detail: e.detail ?? "entity", color: Theme.indigo)
                    }
                }
                Footnote(text: "the choice is kept for this watch")
            }
        }
        .screen("Who answers")
        .task { await model.loadEntities() }
    }

    private func row(_ r: Responder, title: String, detail: String, color: Color) -> some View {
        let selected = model.responder == r
        return Button {
            model.setResponder(r)
            model.path.removeLast()
        } label: {
            Card(stroke: selected ? color : Theme.line) {
                HStack(spacing: 8) {
                    Orb(mode: .idle, size: 26, fps: 12)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(title).font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.text)
                        Text(detail).font(.rounded(.caption2)).foregroundStyle(Theme.muted).lineLimit(2)
                    }
                    Spacer(minLength: 2)
                    if selected { Image(systemName: "checkmark").font(.caption.weight(.bold)).foregroundStyle(color) }
                }
            }
        }
        .buttonStyle(.plain)
    }
}
