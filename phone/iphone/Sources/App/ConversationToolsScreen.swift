import SwiftUI
import AssistantKit
import AbstractGatewayClient

struct ConversationToolsScreen: View {
    @Environment(AssistantStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    @State private var inventory: [ToolInfo] = []
    @State private var modes: [String: ToolMode] = [:]
    @State private var loading = true
    @State private var error: String?
    @State private var search = ""
    @State private var origin: String?
    @State private var originContext: UUID?
    @State private var inherit = true
    private var matching: [ToolInfo] { inventory.filter { search.isEmpty || $0.name.localizedCaseInsensitiveContains(search) || ($0.description ?? "").localizedCaseInsensitiveContains(search) } }
    var body: some View {
        NavigationStack {
            List {
                if loading { ProgressView("Loading available tools…") }
                else if let error { Section { Text(error).foregroundStyle(PhoneTheme.secondary); Button("Try again") { Task { await load() } } } }
                else {
                    Section {
                        Toggle("Use gateway defaults", isOn: $inherit)
                            .accessibilityIdentifier("tools.defaults")
                    } header: {
                        Text(store.conversationTitle + " · This conversation").textCase(nil)
                    } footer: {
                        Text(inherit ? "Gateway defaults apply. Turn this off to choose each tool’s mode. Changes apply to the next message." : "Off blocks. Auto runs without asking. Approve asks you first. Changes apply to the next message.")
                    }
                    Group {
                        Section {
                            ForEach(matching, id: \.name) { tool in
                                VStack(alignment: .leading, spacing: 8) {
                                    Text(tool.name.replacingOccurrences(of: "_", with: " ").capitalized).font(.subheadline.weight(.medium))
                                    if let description = tool.description, !description.isEmpty { Text(description).font(.caption).foregroundStyle(PhoneTheme.secondary).lineLimit(2) }
                                    if inherit && defaultMode(tool) == nil {
                                        Text("Gateway default").font(.caption).foregroundStyle(PhoneTheme.secondary)
                                    } else {
                                    Picker(tool.name, selection: Binding(get: { inherit ? (defaultMode(tool) ?? .approve) : (modes[tool.name] ?? .off) }, set: { modes[tool.name] = $0 })) {
                                        ForEach(ToolMode.allCases, id: \.self) { Text($0.label).tag($0) }
                                    }.pickerStyle(.segmented).accessibilityLabel(tool.name.replacingOccurrences(of: "_", with: " ")).accessibilityIdentifier("tool." + tool.name).disabled(inherit)
                                    }
                                }.padding(.vertical, 6)
                            }
                        }
                        if inventory.isEmpty { Text("No tools are available for this conversation.").foregroundStyle(PhoneTheme.secondary) }
                        else if matching.isEmpty { Text("No tools match your search.").foregroundStyle(PhoneTheme.secondary) }
                    }
                }
            }
            .scrollContentBackground(.hidden).background(PhoneTheme.ground)
            .navigationTitle("Tools").navigationBarTitleDisplayMode(.inline)
            .searchable(text: $search, prompt: "Find a tool")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Close") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        guard origin == store.sessionID, originContext == store.contextID, store.canSend else { return }
                        store.setConversationTools(inherit ? nil : ConversationTools(modes: modes)); dismiss()
                    }.disabled(loading || error != nil || !store.canSend || origin != store.sessionID || originContext != store.contextID)
                }
            }.task { await load() }
        }
    }
    private func defaultMode(_ tool: ToolInfo) -> ToolMode? {
        switch tool.approvalDefault {
        case "auto": .auto
        case "ask", "approve": .approve
        case "off": .off
        default: nil
        }
    }
    private func load() async {
        guard let client = store.client else { return }
        let session = store.sessionID, context = store.contextID, entity = store.selectedEntity
        origin = session; originContext = context; loading = true; error = nil
        do {
            let rows: [ToolInfo]
            if let entity { rows = try await client.entityTools(name: entity) }
            else {
                guard try await client.supportsConversationTools() else { throw GatewayError.http(status: 409, body: "{\"detail\":\"Update this gateway to configure tools per conversation.\"}") }
                rows = try await client.tools()
            }
            guard context == store.contextID, session == store.sessionID, !Task.isCancelled else { return }
            inventory = Array(Dictionary(rows.map { ($0.name, $0) }, uniquingKeysWith: { _, new in new }).values).sorted { $0.name < $1.name }
            inherit = store.conversationTools == nil
            modes = Dictionary(rows.map { ($0.name, defaultMode($0) ?? .approve) }, uniquingKeysWith: { _, new in new })
            if let saved = store.conversationTools { for row in rows { modes[row.name] = saved.modes[row.name] ?? .off } }
        } catch {
            guard context == store.contextID, session == store.sessionID else { return }
            if case GatewayError.http(status: 404, body: _) = error { self.error = "Update this gateway to configure entity tools per conversation." }
            else { self.error = error.localizedDescription }
            if error as? GatewayError == .unauthorized { store.authenticationExpired() }
        }
        loading = false
    }
}
