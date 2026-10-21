import AbstractGatewayClient
import SwiftUI
import WatchKit

/// Which workflow answers: for this conversation (the tools icon on the orb page) or for new
/// conversations (Settings → Tools). The gateway's default agent first, then the Assistant's
/// workflows (they also make images and other media), then the other agents.
struct WorkflowPickView: View {
    @EnvironmentObject private var model: AppModel
    let scope: AppModel.ToolScope
    @State private var loading = true

    var body: some View {
        List {
            if model.workflows.isEmpty {
                if loading { ProgressView().frame(maxWidth: .infinity) }
                else {
                    Text("Couldn't load the workflows").font(.rounded(.footnote)).foregroundStyle(Theme.muted)
                    Button("Retry") { Task { await load() } }
                }
            } else if !model.workflows.contains(where: \.isDefault) {
                // The gateway's default agent is not among the listed ones (an older or catalog
                // version): it can still be chosen.
                row("Gateway default", detail: "Default", pick: .gatewayDefault, id: "workflow.default")
            }
            ForEach(model.workflows) { w in
                row(w.name, detail: Self.detail(w), pick: w.isDefault ? .gatewayDefault : WorkflowPick(w), id: "workflow.\(w.bundleId)")
            }
        }
        .screen("Workflow")
        .task { await load() }
    }

    private func row(_ name: String, detail: String?, pick: WorkflowPick, id: String) -> some View {
        let chosen = model.workflowPick(scope) == pick
        return Button {
            model.setWorkflow(pick, scope: scope)
            WKInterfaceDevice.current().play(.click)
            if model.activeTop == .workflow(scope) { model.pop() }
        } label: {
            HStack {
                VStack(alignment: .leading, spacing: 1) {
                    Text(name).font(.rounded(.footnote))
                    if let detail { Text(detail).font(.rounded(.caption2)).foregroundStyle(Theme.muted) }
                }
                Spacer()
                if chosen { Image(systemName: "checkmark").foregroundStyle(Theme.cyan) }
            }
        }
        .accessibilityAddTraits(chosen ? .isSelected : [])
        .accessibilityIdentifier(id)
    }

    static func detail(_ w: WorkflowChoice) -> String? {
        if w.isDefault { return "Default" }
        if w.interface == WorkflowChoice.assistantInterface { return "Also makes images and other media" }
        return nil
    }

    private func load() async {
        loading = true
        defer { loading = false }
        await model.ensureWorkflows(maxAge: 0)
    }
}

/// The workflow row at the top of a Tools page (a conversation's, or the defaults).
struct WorkflowRow: View {
    @EnvironmentObject private var model: AppModel
    let scope: AppModel.ToolScope
    @State private var failed = false
    var body: some View {
        Button { model.push(.workflow(scope)) } label: {
            Card {
                HStack(spacing: 8) {
                    Image(systemName: "square.stack.3d.up").font(.system(size: 13, weight: .semibold)).foregroundStyle(Theme.cyan).frame(width: 18)
                    VStack(alignment: .leading, spacing: 1) {
                        Text("Workflow").font(.rounded(.caption2)).foregroundStyle(Theme.muted)
                        if let name = model.workflowName(scope) ?? (failed ? "Couldn't load. Tap to retry" : nil) {
                            Text(name).font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.text)
                                .lineLimit(2).fixedSize(horizontal: false, vertical: true)
                        } else {
                            LoadingText().font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.text2)
                        }
                        if model.workflowPick(scope).isGatewayDefault {
                            Text("Default").font(.rounded(.caption2)).foregroundStyle(Theme.muted)
                        }
                    }
                    Spacer(minLength: 4)
                    Image(systemName: "chevron.right").font(.caption2).foregroundStyle(Theme.muted)
                }
            }
        }
        .buttonStyle(.tap)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("tools.workflow")
        .task { await model.ensureWorkflows(maxAge: 600); failed = model.workflows.isEmpty }
    }
}
