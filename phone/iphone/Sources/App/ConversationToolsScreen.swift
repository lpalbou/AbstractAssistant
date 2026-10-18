import SwiftUI
import AssistantKit
import AbstractGatewayClient

struct ConversationToolsScreen: View {
    @Environment(AssistantStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var inventory: [ToolInfo] = []
    @State private var modes: [String: ToolMode] = [:]
    @State private var expanded: Set<String> = []
    @State private var loading = true
    @State private var error: String?
    @State private var search = ""
    @State private var origin: String?
    @State private var originContext: UUID?
    @State private var inherit = true
    private var groups: [ToolCatalogGroup] { ToolCatalogGroup.groups(inventory, matching: search) }
    private var searching: Bool { !search.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
    var body: some View {
        NavigationStack {
            List {
                if loading { ProgressView("Loading available tools…").listRowBackground(PhoneTheme.surface) }
                else if let error {
                    Section { Text(error).foregroundStyle(PhoneTheme.secondary); Button("Try again") { Task { await load() } } }
                        .listRowBackground(PhoneTheme.surface)
                } else {
                    Section {
                        Toggle("Use gateway defaults", isOn: $inherit).tint(PhoneTheme.mint)
                            .accessibilityIdentifier("tools.defaults")
                    } header: {
                        Text(store.conversationTitle + " · This conversation").textCase(nil)
                    } footer: {
                        Text(inherit ? "Gateway defaults apply. Turn this off to choose each tool’s mode." : "Off blocks. Auto runs without asking. Approve asks you first. Changes apply to the next message.")
                    }.listRowBackground(PhoneTheme.surface)
                    ForEach(groups) { group in
                        Section {
                            categoryHeader(group)
                            if searching || expanded.contains(group.id) {
                                ForEach(group.tools, id: \.name) { tool in toolRow(tool) }
                            }
                        }.listRowBackground(PhoneTheme.surface)
                    }
                    if inventory.isEmpty { Text("No tools are available for this conversation.").foregroundStyle(PhoneTheme.secondary).listRowBackground(PhoneTheme.surface) }
                    else if groups.isEmpty { Text("No tools match your search.").foregroundStyle(PhoneTheme.secondary).listRowBackground(PhoneTheme.surface) }
                }
            }
            .listStyle(.insetGrouped).listSectionSpacing(14)
            .scrollContentBackground(.hidden).background(PhoneTheme.ground)
            .navigationTitle("Tools").navigationBarTitleDisplayMode(.inline)
            .searchable(text: $search, placement: .navigationBarDrawer(displayMode: .always), prompt: "Find a category or tool")
            .searchPresentationToolbarBehavior(.avoidHidingContent)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Close") { dismiss() }.accessibilityLabel("Close tools").accessibilityIdentifier("tools.close") }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        guard origin == store.sessionID, originContext == store.contextID, store.canSend else { return }
                        let selection = Dictionary(inventory.map { ($0.name, $0.isAvailable ? (modes[$0.name] ?? .off) : .off) }, uniquingKeysWith: { _, new in new })
                        store.setConversationTools(inherit ? nil : ConversationTools(modes: selection)); dismiss()
                    }.accessibilityIdentifier("tools.save").disabled(loading || error != nil || !store.canSend || origin != store.sessionID || originContext != store.contextID)
                }
            }.task { await load() }
        }
    }
    private func categoryHeader(_ group: ToolCatalogGroup) -> some View {
        let open = searching || expanded.contains(group.id)
        return Button {
            guard !searching else { return }
            withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.22)) {
                if !expanded.insert(group.id).inserted { expanded.remove(group.id) }
            }
        } label: {
            HStack(spacing: 12) {
                Image(systemName: symbol(group.id)).font(.subheadline).foregroundStyle(PhoneTheme.lavender).frame(width: 22)
                Text(group.title).font(.subheadline.weight(.semibold)).foregroundStyle(PhoneTheme.ink)
                Text(group.tools.count.formatted()).font(.caption.monospacedDigit()).foregroundStyle(PhoneTheme.secondary)
                    .padding(.horizontal, 8).padding(.vertical, 3).background(PhoneTheme.ground.opacity(0.7), in: Capsule())
                Spacer(minLength: 8)
                Image(systemName: "chevron.right").font(.caption.weight(.semibold)).foregroundStyle(PhoneTheme.secondary)
                    .rotationEffect(.degrees(open ? 90 : 0))
            }.frame(minHeight: 44).contentShape(Rectangle())
        }.buttonStyle(.plain).disabled(searching).accessibilityIdentifier("tools.category." + group.id)
            .accessibilityLabel(group.title + ", " + group.tools.count.formatted() + (group.tools.count == 1 ? " tool" : " tools"))
            .accessibilityValue(open ? "Expanded" : "Collapsed")
            .accessibilityHint(searching ? "Matching tools are shown while searching." : "Show or hide tools in this category.")
    }
    private func toolRow(_ tool: ToolInfo) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .top, spacing: 8) { toolTitle(tool); Spacer(minLength: 4); riskBadge(tool) }
                VStack(alignment: .leading, spacing: 6) { toolTitle(tool); riskBadge(tool) }
            }
            if !tool.isAvailable {
                Text(tool.whyDisabled ?? "This tool is disabled on the gateway.").font(.caption).foregroundStyle(PhoneTheme.secondary)
            } else if let description = tool.description, !description.isEmpty {
                Text(description).font(.caption).foregroundStyle(PhoneTheme.secondary).lineLimit(3)
            }
            if inherit && defaultMode(tool) == nil && tool.isAvailable {
                Text("Gateway default").font(.caption).foregroundStyle(PhoneTheme.secondary)
            } else {
                Picker(tool.displayName, selection: Binding(get: { !tool.isAvailable ? .off : inherit ? (defaultMode(tool) ?? .off) : (modes[tool.name] ?? .off) }, set: { modes[tool.name] = $0 })) {
                    ForEach(ToolMode.allCases, id: \.self) { Text($0.label).tag($0) }
                }.pickerStyle(.segmented).accessibilityLabel(tool.displayName).accessibilityIdentifier("tool." + tool.name)
                    .disabled(inherit || !tool.isAvailable)
            }
        }.padding(.vertical, 10)
    }
    private func toolTitle(_ tool: ToolInfo) -> some View {
        Text(tool.displayName).font(.subheadline.weight(.medium)).foregroundStyle(PhoneTheme.ink).fixedSize(horizontal: false, vertical: true)
    }
    private func riskBadge(_ tool: ToolInfo) -> some View {
        let value: (String, Color) = {
            guard tool.isAvailable else { return ("Disabled on gateway", PhoneTheme.secondary) }
            switch tool.riskTier?.lowercased() {
            case "observe": return ("Reads only", PhoneTheme.mint)
            case "act": return ("Makes changes", PhoneTheme.amber)
            case "outreach": return ("Reaches outside", PhoneTheme.amber)
            case "destroy": return ("Destructive", .red.opacity(0.9))
            default: return ("Not classified", PhoneTheme.secondary)
            }
        }()
        return Text(value.0).font(.caption2.weight(.medium)).foregroundStyle(value.1)
            .padding(.horizontal, 8).padding(.vertical, 5).background(value.1.opacity(0.09), in: Capsule()).fixedSize()
    }
    private func symbol(_ category: String) -> String {
        switch category.lowercased() {
        case "comms", "email": "envelope"
        case "files", "filesystem": "folder"
        case "web", "browser": "globe"
        case "camera": "camera"
        case "system", "shell": "terminal"
        case "memory": "brain"
        case "agora": "bubble.left.and.bubble.right"
        default: "square.grid.2x2"
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
            if let entity {
                let offered = try await client.entityTools(name: entity)
                // Older entity inventories omit display metadata. Enrich only from gateway
                // declarations, preserving the entity's own availability and approval defaults.
                if offered.contains(where: { $0.toolset?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty != false }) {
                    do { rows = ToolCatalogGroup.enriching(offered, from: try await client.tools()) }
                    catch GatewayError.unauthorized { throw GatewayError.unauthorized }
                    catch is CancellationError { throw CancellationError() }
                    catch { rows = offered } // Unreported categories remain Other.
                } else { rows = offered }
            } else {
                rows = try await client.tools()
            }
            guard context == store.contextID, session == store.sessionID, !Task.isCancelled else { return }
            inventory = Array(Dictionary(rows.map { ($0.name, $0) }, uniquingKeysWith: { _, new in new }).values).sorted { $0.name < $1.name }
            inherit = store.conversationTools == nil
            modes = Dictionary(rows.map { ($0.name, defaultMode($0) ?? .off) }, uniquingKeysWith: { _, new in new })
            if let saved = store.conversationTools { for row in rows { modes[row.name] = saved.modes[row.name] ?? .off } }
        } catch {
            guard context == store.contextID, session == store.sessionID else { return }
            if entity != nil, case GatewayError.http(status: 404, body: _) = error { self.error = "This gateway does not support tools per entity conversation. Assistant conversation tools remain available." }
            else { self.error = error.localizedDescription }
            if error as? GatewayError == .unauthorized { store.authenticationExpired() }
        }
        loading = false
    }
}
