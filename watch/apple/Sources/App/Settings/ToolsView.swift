import AbstractGatewayClient
import SwiftUI
import WatchKit

/// The tools a conversation may use, by group: Settings → Tools sets the defaults, the tools icon on
/// the orb page changes them for this conversation only. Each tool is Off (not offered), Auto (runs
/// without asking) or Ask (asks first); a tool the gateway has not set up is listed and stays off.
struct ToolsView: View {
    @EnvironmentObject private var model: AppModel
    let scope: AppModel.ToolScope
    @State private var failed = false

    var body: some View {
        Group {
            if !model.tools.isEmpty { content }
            else if failed {
                VStack(spacing: 8) {
                    Text("Couldn't load the tools").font(.rounded(.footnote)).foregroundStyle(Theme.muted)
                    Button("Retry") { Task { await load() } }.buttonStyle(FilledButtonStyle(fill: Theme.neutralButton))
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                VStack(spacing: 8) {
                    ProgressView()
                    Text("Loading tools…").font(.rounded(.footnote)).foregroundStyle(Theme.muted)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .accessibilityElement(children: .combine)
                .accessibilityIdentifier("tools.loading")
            }
        }
        .screen("Tools")
        // Read again on every visit: a toolset the gateway's admin turns on or off shows up.
        .task { await load() }
    }

    private func load() async {
        failed = false
        await model.ensureTools(maxAge: 0)
        failed = model.tools.isEmpty
    }

    private var groups: [ToolGroup] { ToolGroup.all(Array(model.tools.values)) }

    private var content: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 6) {
                Text(heading).font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.text)
                // Which workflow answers (an automation chooses its own on its page).
                if scope != .draft { WorkflowRow(scope: scope) }
                if scope == .session, !model.sessionTrust.isEmpty { trustCard }
                Text(caption).font(.rounded(.caption2)).foregroundStyle(Theme.muted)
                Text(summary).font(.rounded(.caption2, weight: .semibold)).foregroundStyle(Theme.text2)
                    .accessibilityIdentifier("tools.summary")
                if scope != .defaults, !model.toolChanges(scope).isEmpty {
                    Button("Use my defaults") { model.resetTools(scope); WKInterfaceDevice.current().play(.click) }
                        .buttonStyle(FilledButtonStyle(fill: Theme.neutralButton))
                } else if scope == .defaults, !model.toolDefaults.isEmpty {
                    Button("Use the gateway's") { model.resetToolDefaults(); WKInterfaceDevice.current().play(.click) }
                        .buttonStyle(FilledButtonStyle(fill: Theme.neutralButton))
                }
                ForEach(groups) { g in
                    NavigationLink(value: Route.toolGroup(scope, g.id)) { groupRow(g) }
                        .buttonStyle(.tap)
                }
            }
            .padding(.horizontal, 4)
        }
    }

    /// After an Accept all: the tools the watch approves for you in this conversation.
    private var trustCard: some View {
        Card(stroke: Theme.amber.opacity(0.5)) {
            VStack(alignment: .leading, spacing: 4) {
                Label("Allowed for now", systemImage: "checkmark.shield.fill")
                    .font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.amber)
                Text(model.sessionTrust.map(ToolGroup.title(of:)).sorted().joined(separator: ", "))
                    .font(.rounded(.caption2)).foregroundStyle(Theme.text2)
                Text("Approved by this watch while it follows the run.").font(.rounded(.caption2)).foregroundStyle(Theme.muted)
                Button("Ask again") { model.revokeTrust(); WKInterfaceDevice.current().play(.click) }
                    .buttonStyle(FilledButtonStyle(fill: Theme.neutralButton, font: .rounded(.footnote, weight: .semibold)))
                    .accessibilityIdentifier("tools.trust.revoke")
            }
        }
    }

    private var heading: String {
        switch scope { case .defaults: "Defaults"; case .session: "This conversation"; case .draft: "This automation" }
    }
    private var caption: String {
        switch scope {
        case .defaults: "Conversations and new automations use these unless changed."
        case .session: "Applies from your next question."
        case .draft: "It runs on its own: a tool on Ask waits for you in Needs you."
        }
    }

    /// "9 auto · 3 ask · 2 off" for the tools that can be offered.
    private var summary: String {
        let modes = model.tools.values.filter(\.offered).map { model.toolMode($0, scope: scope) }
        return ToolGroup.counts(modes)
    }

    private func groupRow(_ g: ToolGroup) -> some View {
        Card {
            HStack(spacing: 8) {
                Image(systemName: g.symbol).font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(g.usable ? Theme.cyan : Theme.muted).frame(width: 20)
                VStack(alignment: .leading, spacing: 1) {
                    HStack(spacing: 5) {
                        Text(g.title).font(.rounded(.footnote, weight: .semibold))
                            .foregroundStyle(g.usable ? Theme.text : Theme.muted).lineLimit(1)
                        Text("\(g.tools.count)").font(.rounded(.caption2, weight: .semibold)).foregroundStyle(Theme.muted)
                            .padding(.horizontal, 5).padding(.vertical, 1).background(Theme.line, in: Capsule())
                    }
                    Text(g.usable ? ToolGroup.counts(g.tools.filter(\.offered).map { model.toolMode($0, scope: scope) }) : g.offLine)
                        .font(.rounded(.caption2)).foregroundStyle(Theme.muted).lineLimit(1)
                }
                Spacer(minLength: 2)
                Image(systemName: "chevron.right").font(.caption2).foregroundStyle(Theme.muted)
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("tools.group.\(g.id)")
    }
}

/// One group's tools: All (Off · Auto · Ask) for the group, then each tool with its risk, what it
/// can do and its own Off · Auto · Ask. A group the gateway has not set up lists its tools' names.
struct ToolGroupView: View {
    @EnvironmentObject private var model: AppModel
    let scope: AppModel.ToolScope
    let groupId: String
    @State private var note: String?
    @State private var expanded: Set<String> = []

    private var group: ToolGroup? { ToolGroup.all(Array(model.tools.values)).first { $0.id == groupId } }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 6) {
                if let g = group {
                    let usable = g.tools.filter(\.offered)
                    if usable.isEmpty {
                        notSetUp(g)
                    } else {
                        all(usable, g)
                        ForEach(usable, id: \.name) { tool in row(tool) }
                        let rest = g.tools.filter { !$0.offered }
                        if !rest.isEmpty { notSetUp(ToolGroup(id: g.id, tools: rest)) }
                    }
                }
            }
            .padding(.horizontal, 4)
        }
        .overlay { if model.tools.isEmpty { ProgressView() } }
        .screen(group?.title ?? "Tools")
        .task { if model.tools.isEmpty { await model.ensureTools() } }
    }

    /// All: pressed when every tool is on that mode (Auto: every tool it reaches); "Mixed" else.
    private func all(_ usable: [ToolInfo], _ g: ToolGroup) -> some View {
        let reach = usable.filter(ToolChoices.allAutoReaches)
        let modes = usable.map { model.toolMode($0, scope: scope) }
        let mode: ToolMode? =
            modes.allSatisfy { $0 == .off } ? .off
            : modes.allSatisfy { $0 == .ask } ? .ask
            : (!reach.isEmpty && reach.allSatisfy { model.toolMode($0, scope: scope) == .auto } && !modes.contains(.off)) ? .auto
            : nil
        return VStack(alignment: .leading, spacing: 3) {
            HStack {
                Text("All").font(.rounded(.caption2, weight: .semibold)).foregroundStyle(Theme.muted)
                Spacer()
                if mode == nil { Text("Mixed").font(.rounded(.caption2)).foregroundStyle(Theme.muted) }
            }
            ModeControl(selected: mode, title: "All \(g.title) tools", id: "tools.all.\(g.id)",
                        unavailable: reach.isEmpty ? [.auto] : []) { setAll(usable, reach, $0) }
            if let note { Text(note).font(.rounded(.caption2)).foregroundStyle(Theme.amber) }
        }
        .padding(.bottom, 2)
    }

    private func setAll(_ usable: [ToolInfo], _ reach: [ToolInfo], _ mode: ToolMode) {
        if mode == .auto {
            let rest = usable.filter { !ToolChoices.allAutoReaches($0) }
            model.setTools(reach.map(\.name), .auto, scope: scope)
            // The others are on, asking first: Auto for them is a choice made one tool at a time.
            model.setTools(rest.filter { model.toolMode($0, scope: scope) == .off }.map(\.name), .ask, scope: scope)
            note = rest.isEmpty ? nil : "Tools that reach outside, can destroy, or go where the assistant picks stay on Ask."
        } else {
            model.setTools(usable.map(\.name), mode, scope: scope)
            note = nil
        }
        WKInterfaceDevice.current().play(.click)
    }

    private func row(_ tool: ToolInfo) -> some View {
        let title = ToolGroup.title(of: tool.name)
        let mode = model.toolMode(tool, scope: scope)
        let base = model.toolMode(tool, scope: .defaults)
        let changed = scope != .defaults && mode != base
        return Card {
            VStack(alignment: .leading, spacing: 4) {
                HStack(alignment: .firstTextBaseline, spacing: 5) {
                    Text(title).font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.text).lineLimit(2)
                    if changed { Circle().fill(Theme.amber).frame(width: 6, height: 6) }
                }
                if let risk = ToolGroup.risk(tool) {
                    Text(risk.label).font(.rounded(.caption2, weight: .semibold)).foregroundStyle(risk.color)
                        .padding(.horizontal, 6).padding(.vertical, 1)
                        .overlay(Capsule().strokeBorder(risk.color.opacity(0.5), lineWidth: 0.5))
                }
                if !tool.facts.isEmpty, tool.facts != ["read-only"] {   // "Reads only" already says it
                    Text(ToolGroup.sentence(tool.facts)).font(.rounded(.caption2)).foregroundStyle(Theme.text2)
                }
                if let about = tool.description, !about.isEmpty {
                    if expanded.contains(tool.name) {
                        Text(about).font(.rounded(.caption2)).foregroundStyle(Theme.muted)
                    }
                    Button(expanded.contains(tool.name) ? "Less" : "More") {
                        if expanded.contains(tool.name) { expanded.remove(tool.name) } else { expanded.insert(tool.name) }
                    }
                    .buttonStyle(.tap).font(.rounded(.caption2, weight: .semibold)).foregroundStyle(Theme.cyan)
                    .accessibilityLabel(expanded.contains(tool.name) ? "Less about \(title)" : "More about \(title)")
                }
                ModeControl(selected: mode, title: title, id: "tool.\(tool.name)") { m in
                    model.setTools([tool.name], m, scope: scope)
                    note = nil
                    WKInterfaceDevice.current().play(.click)
                }
                if changed {
                    Text("Default: \(base.label)").font(.rounded(.caption2)).foregroundStyle(Theme.amber)
                        .accessibilityIdentifier("tool.\(tool.name).default")
                }
            }
        }
    }

    /// Tools the gateway has not set up: their names, once, under one line (nothing to switch).
    private func notSetUp(_ g: ToolGroup) -> some View {
        Card {
            VStack(alignment: .leading, spacing: 3) {
                Text(g.offTitle).font(.rounded(.caption2, weight: .semibold)).foregroundStyle(Theme.muted)
                ForEach(g.tools, id: \.name) { t in
                    Text(ToolGroup.title(of: t.name)).font(.rounded(.caption2)).foregroundStyle(Theme.muted).lineLimit(1)
                }
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("tools.notsetup.\(g.id)")
    }
}

/// Off · Auto · Ask as one capsule; the selected segment is filled (none when a group is mixed).
struct ModeControl: View {
    let selected: ToolMode?
    /// What the control sets (VoiceOver reads it with each segment).
    let title: String
    let id: String
    var unavailable: Set<ToolMode> = []
    let pick: (ToolMode) -> Void

    var body: some View {
        HStack(spacing: 2) {
            ForEach(ToolMode.allCases, id: \.self) { mode in
                let on = selected == mode
                let off = unavailable.contains(mode)
                Button { pick(mode) } label: {
                    Text(mode.label).font(.rounded(.caption2, weight: .semibold))
                        .foregroundStyle(on ? mode.ink : off ? Theme.muted.opacity(0.4) : Theme.muted)
                        .frame(maxWidth: .infinity, minHeight: 34)
                        .background(on ? mode.fill : .clear, in: Capsule())
                        .contentShape(Capsule())
                }
                .buttonStyle(.tap)
                .disabled(off)
                .accessibilityLabel("\(title): \(mode.label)")
                .accessibilityAddTraits(on ? .isSelected : [])
                .accessibilityIdentifier("\(id).\(mode.rawValue)")
            }
        }
        .padding(2)
        .background(Theme.ground, in: Capsule())
        .overlay(Capsule().strokeBorder(Theme.line, lineWidth: 0.5))
    }
}

extension ToolMode {
    var label: String {
        switch self { case .off: "Off"; case .auto: "Auto"; case .ask: "Ask" }
    }
    var fill: Color {
        switch self { case .off: Theme.muted.opacity(0.4); case .auto: Theme.greenButton.opacity(0.85); case .ask: Theme.amber.opacity(0.22) }
    }
    var ink: Color {
        switch self { case .off: Theme.text; case .auto: .white; case .ask: Theme.amber }
    }
}

/// A gateway toolset (`files`, `web`, `comms.email`, …) with its tools, as the watch shows it.
struct ToolGroup: Identifiable {
    let id: String
    let tools: [ToolInfo]
    var usable: Bool { tools.contains(where: \.offered) }
    /// Why its tools are off. Email is per account (the account's own mailbox); the others are
    /// set up for the whole gateway.
    var offLine: String { id == "comms.email" ? "Not connected for this account" : "Not set up" }
    var offTitle: String {
        id == "comms.email" ? "No mailbox connected for this account (gateway Settings → Email)" : "Not set up on your gateway"
    }

    /// The groups, those that can be used first, each alphabetical.
    static func all(_ tools: [ToolInfo]) -> [ToolGroup] {
        Dictionary(grouping: tools) { $0.toolset ?? "other" }
            .map { ToolGroup(id: $0.key, tools: $0.value.sorted { title(of: $0.name) < title(of: $1.name) }) }
            .sorted { ($0.usable ? 0 : 1, $0.title) < ($1.usable ? 0 : 1, $1.title) }
    }

    var title: String {
        if id.hasPrefix("mcp:") { return "MCP " + id.dropFirst(4) }
        switch id {
        case "files": return "Files"
        case "web": return "Web"
        case "system": return "System"
        case "shell": return "Shell"
        case "agora": return "Agora"
        case "camera": return "Camera"
        case "comms.email": return "Email"
        case "comms.whatsapp": return "WhatsApp"
        case "comms.telegram": return "Telegram"
        default: return (id.split(separator: ".").last.map(String.init) ?? id).capitalized
        }
    }

    var symbol: String {
        if id.hasPrefix("mcp:") { return "puzzlepiece" }
        switch id {
        case "files": return "folder"
        case "web": return "globe"
        case "system", "shell": return "terminal"
        case "agora": return "person.3"
        case "camera": return "camera"
        case "comms.email": return "envelope"
        case "comms.whatsapp": return "message"
        case "comms.telegram": return "paperplane"
        default: return "wrench.and.screwdriver"
        }
    }

    /// `get_email_attachment` → "Get email attachment", `fetch_url` → "Fetch URL".
    static func title(of name: String) -> String {
        let acronyms = ["url": "URL", "urls": "URLs", "id": "ID", "ids": "IDs", "ui": "UI", "api": "API", "pdf": "PDF",
                        "dm": "DM", "dms": "DMs", "mcp": "MCP"]
        let words = name.split(separator: "_").map { acronyms[String($0)] ?? String($0) }.joined(separator: " ")
        return words.prefix(1).uppercased() + words.dropFirst()
    }

    /// The facts as one sentence: "Changes files or state, reaches remote services."
    static func sentence(_ facts: [String]) -> String {
        let s = facts.joined(separator: ", ")
        return s.prefix(1).uppercased() + s.dropFirst() + "."
    }

    /// The risk in the desktop assistant's words.
    static func risk(_ tool: ToolInfo) -> (label: String, color: Color)? {
        switch tool.riskTier {
        case "observe": ("Reads only", Theme.green)
        case "act": ("Makes changes", Theme.amber)
        case "outreach": ("Reaches outside", Theme.cyan)
        case "destroy": ("Destructive", Theme.red)
        default: nil
        }
    }

    /// "5 auto · 2 ask · 1 off", leaving out what is zero.
    static func counts(_ modes: [ToolMode]) -> String {
        let parts = [(ToolMode.auto, "auto"), (.ask, "ask"), (.off, "off")]
            .map { m, word in (modes.filter { $0 == m }.count, word) }.filter { $0.0 > 0 }.map { "\($0.0) \($0.1)" }
        return parts.isEmpty ? "None" : parts.joined(separator: " · ")
    }
}
