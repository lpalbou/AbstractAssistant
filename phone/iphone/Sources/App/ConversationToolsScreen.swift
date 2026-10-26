import SwiftUI
import AssistantKit
import PhoneGatewayClient

struct ConversationToolsScreen: View {
    @Environment(AssistantStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    enum Scope { case settings, conversation, automation }
    var scope: Scope = .conversation
    var automationSelection: ConversationTools?
    var saveAutomation: ((ConversationTools?) async throws -> Void)?
    @State private var inventory: [ToolInfo] = []
    @State private var modes: [String: ToolMode] = [:]
    @State private var inherit = true
    @State private var saving = false
    @State private var legacyAskingAgain: Set<String> = []
    private var inheritedModes: [String: ToolMode] {
        let selection = scope == .settings ? nil : store.appTools
        return ConversationTools.snapshot(selection, inventory: inventory).modes
    }
    private var scopeTitle: String {
        switch scope {
        case .settings: "Defaults for sessions and automations"
        case .conversation: store.conversationTitle + " · This session"
        case .automation: "This automation"
        }
    }
    private var scopeHelp: String {
        switch scope {
        case .settings: "Default tools for all sessions and new automations on this iPhone."
        case .conversation: "Session choices override Settings and apply to your next message."
        case .automation: "Settings defaults are saved with the automation unless you override them here."
        }
    }
    private var validOrigin: Bool {
        originContext == store.contextID && (scope != .conversation || origin == store.sessionID)
    }
    private var canSave: Bool {
        validOrigin && store.client != nil && (scope == .automation || store.canEditToolPreferences) && !saving
    }
    @State private var expanded: Set<String> = []
    @State private var loading = true
    @State private var error: String?
    @State private var search = ""
    @State private var origin: String?
    @State private var originContext: UUID?
    private var groups: [ToolCatalogGroup] { ToolCatalogGroup.groups(inventory, matching: search) }
    private var searching: Bool { !search.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
    var body: some View {
        NavigationStack {
            List {
                if loading { ProgressView("Loading available tools…").listRowBackground(PhoneTheme.surface) }
                else if let error, inventory.isEmpty {
                    Section { Text(error).foregroundStyle(PhoneTheme.secondary); Button("Try again") { Task { await load() } } }
                        .listRowBackground(PhoneTheme.surface)
                } else {
                    if let error { Section { Text(error).foregroundStyle(PhoneTheme.amber) }.listRowBackground(PhoneTheme.surface) }
                    if scope == .conversation {
                        if !store.sessionApprovalGrants.isEmpty {
                            Section {
                                Label("Allowed for this session", systemImage: "checkmark.shield.fill").foregroundStyle(PhoneTheme.amber)
                                Text(store.sessionApprovalGrants.map(toolName).sorted().joined(separator: ", "))
                                    .font(.caption).foregroundStyle(PhoneTheme.secondary)
                                Button("Ask again", systemImage: "hand.raised") { store.revokeSessionApprovals() }
                                    .foregroundStyle(PhoneTheme.amber).accessibilityIdentifier("tools.approvals.revoke")
                                    .disabled(!validOrigin)
                            } footer: { Text("Removes temporary approvals from the next unanswered call. Auto tools stay Auto. Calls already approved may finish.") }
                                .listRowBackground(PhoneTheme.surface)
                        }
                        if !store.legacySessionApprovalNames.isEmpty {
                            Section {
                                Label("Review earlier approvals", systemImage: "checkmark.shield.fill").foregroundStyle(PhoneTheme.amber)
                                Text("An earlier app version saved these approvals as Auto. Select the tools you want to ask again; the rest keep their current settings.")
                                    .font(.caption).foregroundStyle(PhoneTheme.secondary)
                                ForEach(store.legacySessionApprovalNames, id: \.self) { name in
                                    Toggle(toolName(name), isOn: Binding(get: { legacyAskingAgain.contains(name) }, set: { enabled in
                                        if enabled { legacyAskingAgain.insert(name) } else { legacyAskingAgain.remove(name) }
                                    })).tint(PhoneTheme.amber).accessibilityIdentifier("tools.approvals.legacy." + name)
                                }
                                Button(legacyAskingAgain.isEmpty ? "Keep current settings" : "Make selected tools ask again") {
                                    store.reviewLegacySessionApprovals(askingAgain: legacyAskingAgain)
                                    legacyAskingAgain = []
                                    if let selection = store.conversationTools { modes = selection.modes; inherit = false }
                                }.disabled(!canSave).accessibilityIdentifier("tools.approvals.legacy.save")
                            } footer: { Text("Applies from your next message. Original Auto and Approve choices were not retained by that version.") }
                                .listRowBackground(PhoneTheme.surface)
                        }
                    }
                    Section {
                        Toggle(scope == .settings ? "Use gateway defaults" : "Use Settings defaults", isOn: $inherit)
                            .tint(PhoneTheme.mint).accessibilityIdentifier("tools.defaults")
                    } header: { Text(scopeTitle).textCase(nil) }
                    footer: { if !searching { Text(scopeHelp + " Off blocks · Auto runs · Approve asks.") } }
                        .listRowBackground(PhoneTheme.surface)
                    ForEach(groups) { group in
                        Section {
                            categoryHeader(group)
                            categoryPicker(group)
                            if searching {
                                Text("All \(inventory.filter { $0.categoryID == group.id }.count) \(group.title) tools")
                                    .font(.caption2).foregroundStyle(PhoneTheme.secondary)
                            }
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
                    Button(saving ? "Saving…" : "Save") { Task { await save() } }
                        .accessibilityIdentifier("tools.save").disabled(loading || (error != nil && inventory.isEmpty) || !canSave)
                }
            }.task { await load() }.interactiveDismissDisabled(saving)
        }
    }
    private func toolName(_ name: String) -> String {
        inventory.first { $0.name == name }?.displayName ?? name.replacingOccurrences(of: "_", with: " ").capitalized
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
                Image(systemName: symbol(group.id)).font(.subheadline).foregroundStyle(group.isAvailable ? PhoneTheme.mint : PhoneTheme.secondary).frame(width: 22)
                VStack(alignment: .leading, spacing: 3) {
                    Text(group.title).font(.subheadline.weight(.semibold)).foregroundStyle(group.isAvailable ? PhoneTheme.mint : PhoneTheme.secondary)
                    Text(group.isAvailable ? "\(group.availableCount) available" : "Not set up on gateway")
                        .font(.caption2).foregroundStyle(PhoneTheme.secondary)
                }
                Text(group.tools.count.formatted()).font(.caption.monospacedDigit()).foregroundStyle(PhoneTheme.secondary)
                    .padding(.horizontal, 8).padding(.vertical, 3).background(PhoneTheme.ground.opacity(0.7), in: Capsule())
                if group.isAvailable && ConversationTools(modes: inherit ? inheritedModes : modes).categoryMode(group.id, inventory: inventory) == nil {
                    Text("Mixed").font(.caption2).foregroundStyle(PhoneTheme.secondary)
                }
                Spacer(minLength: 8)
                Image(systemName: "chevron.right").font(.caption.weight(.semibold)).foregroundStyle(PhoneTheme.secondary)
                    .rotationEffect(.degrees(open ? 90 : 0))
            }.frame(minHeight: 44).contentShape(Rectangle())
        }.buttonStyle(.plain).accessibilityIdentifier("tools.category." + group.id)
            .accessibilityLabel(group.title + ", " + group.tools.count.formatted() + (group.tools.count == 1 ? " tool" : " tools"))
            .accessibilityValue((open ? "Expanded" : "Collapsed") + (group.isAvailable ? ", Available" : ", Not set up"))
            .accessibilityHint(searching ? "Matching tools are shown while searching." : "Show or hide tools in this category.")
    }
    private func categoryPicker(_ group: ToolCatalogGroup) -> some View {
        let effective = ConversationTools(modes: inherit ? inheritedModes : modes)
        return Picker(group.title + " tools", selection: Binding<ToolMode?>(get: {
            effective.categoryMode(group.id, inventory: inventory)
        }, set: { mode in
            guard let mode else { return }
            modes = effective.settingCategory(group.id, to: mode, inventory: inventory).modes
            inherit = false
        })) {
            ForEach(ToolMode.allCases, id: \.self) { Text($0.label).tag(Optional($0)) }
        }.pickerStyle(.segmented).disabled(!group.isAvailable || saving)
            .accessibilityIdentifier("tools.categoryMode." + group.id)
            .accessibilityValue(effective.categoryMode(group.id, inventory: inventory)?.label ?? "Mixed")
            .accessibilityHint("Sets all available tools in this category, including tools hidden by search.")
            .padding(.bottom, 6)
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
            Picker(tool.displayName, selection: Binding(get: { !tool.isAvailable ? .off : inherit ? (inheritedModes[tool.name] ?? .approve) : (modes[tool.name] ?? .off) }, set: { mode in
                if inherit {
                    modes = inheritedModes
                    inherit = false
                }
                modes[tool.name] = mode
            })) {
                ForEach(ToolMode.allCases, id: \.self) { Text($0.label).tag($0) }
            }.pickerStyle(.segmented).accessibilityLabel(tool.displayName).accessibilityIdentifier("tool." + tool.name)
                .disabled(!tool.isAvailable)
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
        if category.hasPrefix("mcp:") { return "puzzlepiece" }
        return switch category.lowercased() {
        case "comms", "email", "comms.email": "envelope"
        case "comms.telegram": "paperplane"
        case "comms.whatsapp": "message"
        case "files", "filesystem": "folder"
        case "web", "browser": "globe"
        case "camera": "camera"
        case "system", "shell": "terminal"
        case "memory": "brain"
        case "agora": "bubble.left.and.bubble.right"
        default: "square.grid.2x2"
        }
    }
    private func save() async {
        guard canSave else { return }
        saving = true; error = nil
        defer { saving = false }
        let selected = inherit ? nil : ConversationTools(modes: Dictionary(inventory.map {
            ($0.name, $0.isAvailable ? (modes[$0.name] ?? .off) : .off)
        }, uniquingKeysWith: { _, new in new }))
        do {
            switch scope {
            case .settings: store.setAppTools(selected)
            case .conversation: store.setConversationTools(selected)
            case .automation:
                guard let saveAutomation else { return }
                try await saveAutomation(selected)
            }
            guard validOrigin else { return }
            dismiss()
        } catch {
            guard validOrigin else { return }
            self.error = error.localizedDescription
            if error as? GatewayError == .unauthorized { store.authenticationExpired() }
        }
    }
    private func load() async {
        guard let client = store.client else { return }
        let session = store.sessionID, context = store.contextID, entity = scope == .conversation ? store.selectedEntity : nil
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
            guard context == store.contextID, (scope != .conversation || session == store.sessionID), !Task.isCancelled else { return }
            inventory = Array(Dictionary(rows.map { ($0.name, $0) }, uniquingKeysWith: { _, new in new }).values).sorted { $0.name < $1.name }
            let selected: ConversationTools?
            switch scope { case .settings: selected = store.appTools; case .conversation: selected = store.conversationTools; case .automation: selected = automationSelection }
            inherit = selected == nil; modes = selected?.modes ?? inheritedModes
        } catch {
            guard context == store.contextID, session == store.sessionID else { return }
            if entity != nil, case GatewayError.http(status: 404, body: _) = error { self.error = "This gateway does not support tools per entity conversation. Assistant conversation tools remain available." }
            else { self.error = error.localizedDescription }
            if error as? GatewayError == .unauthorized { store.authenticationExpired() }
        }
        loading = false
    }
}
