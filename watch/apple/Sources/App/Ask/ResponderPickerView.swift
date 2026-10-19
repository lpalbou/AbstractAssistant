import AbstractGatewayClient
import SwiftUI

/// Who answers an Ask: the Assistant (a one-shot agent), or one of the user's entities (long-term
/// discussions, with memory)
/// (`GET /api/gateway/entities` lists the entities the signed-in account may visit; an entity
/// conversation uses `POST /entities/{name}/chat/open` and `.../turn`).
struct ResponderPickerView: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        ScrollView {
            VStack(spacing: 6) {
                // Two different things, kept apart: the Assistant is a one-shot agent (a task, an
                // answer); an entity is someone you keep talking with over time, who remembers.
                row(.assistant, title: "Assistant", detail: "One-shot agent", color: Theme.cyan)
                VStack(alignment: .leading, spacing: 0) {
                    Text("ENTITIES").font(.rounded(.caption2, weight: .semibold)).foregroundStyle(Theme.muted)
                    Text("Long-term discussions").font(.rounded(.caption2)).foregroundStyle(Theme.muted)
                }
                .frame(maxWidth: .infinity, alignment: .leading).padding(.top, 6)
                if model.entities.isEmpty {
                    Text(model.client.isMock ? "" : "No entities yet. Create one in the console, or ask its creator to share it.")
                        .font(.rounded(.caption2)).foregroundStyle(Theme.muted).frame(maxWidth: .infinity, alignment: .leading)
                } else {
                    ForEach(model.entities) { e in
                        row(.entity(e.name), title: e.name.replacingOccurrences(of: "-", with: " ").capitalized,
                            detail: e.detail ?? "Entity", color: Theme.indigo)
                    }
                }
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
                    Orb(mode: .idle, size: 30, fps: 12, look: model.look(for: r))
                    VStack(alignment: .leading, spacing: 1) {
                        Text(title).font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.text).lineLimit(1)
                        Text(detail).font(.rounded(.caption2)).foregroundStyle(Theme.muted).lineLimit(2)
                    }
                    Spacer(minLength: 2)
                    if selected { Image(systemName: "checkmark").font(.caption.weight(.bold)).foregroundStyle(color) }
                }
            }
        }
        .buttonStyle(.tap)
    }
}
