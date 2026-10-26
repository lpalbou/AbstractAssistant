import SwiftUI
import AssistantKit
import PhoneGatewayClient

enum ActivityDetail: String, Identifiable { case cycles, tools, all; var id: String { rawValue } }

struct AnswerActivityButtons: View {
    let runID: String
    var cachedOnly = false
    var browseFiles: (() -> Void)?
    @Environment(AssistantStore.self) private var store
    @State private var showing: ActivityDetail?
    @State private var accessKind: AccessKind?
    @State private var browseAfterDismiss = false
    @State private var emailDirection: EmailDirection?
    private var summary: AnswerActivity? { store.answerActivities[runID] }
    private func count(_ n: Int) -> String { summary?.issues.isEmpty == false ? "\(n)+" : String(n) }
    var body: some View {
        HStack(spacing: 16) {
            if summary?.scopeTitle == "Visit activity" {
                Button { showing = .all } label: { Label("Visit", systemImage: "clock.arrow.circlepath") }.accessibilityLabel("View this entity visit’s activity")
                if let summary, summary.activity.toolCalls > 0 {
                    Button { showing = .tools } label: { Label(count(summary.activity.toolCalls), systemImage: "wrench.and.screwdriver") }.foregroundStyle(PhoneTheme.tool)
                        .accessibilityLabel("\(summary.activity.toolCalls) tool calls. View tools").accessibilityIdentifier("answer.tools." + runID)
                }
            } else if let summary {
                let cycles = summary.activity.cycleCount > 0 ? summary.activity.cycleCount : summary.activity.modelCalls
                if cycles > 0 {
                    Button { showing = .cycles } label: { Label(count(cycles), systemImage: "arrow.triangle.2.circlepath") }
                        .accessibilityLabel("\(cycles) \(summary.activity.cycleCount > 0 ? "cycles" : "model calls"). View cycles")
                        .accessibilityIdentifier("answer.cycles." + runID)
                }
                if summary.activity.toolCalls > 0 {
                    Button { showing = .tools } label: { Label(count(summary.activity.toolCalls), systemImage: "wrench.and.screwdriver") }.foregroundStyle(PhoneTheme.tool)
                        .accessibilityLabel("\(summary.activity.toolCalls) tool calls. View tools")
                        .accessibilityIdentifier("answer.tools." + runID)
                }
                if (cycles == 0 && summary.activity.toolCalls == 0) || !summary.issues.isEmpty {
                    Button { showing = .all } label: { Image(systemName: summary.issues.isEmpty ? "clock.arrow.circlepath" : "exclamationmark.circle") }
                        .accessibilityLabel(summary.issues.isEmpty ? "View answer activity" : "Activity unavailable or incomplete. View and retry")
                        .accessibilityIdentifier("answer.activity." + runID)
                }
            } else {
                Button { showing = .all } label: { Image(systemName: "clock.arrow.circlepath") }
                    .accessibilityLabel("Load answer activity").accessibilityIdentifier("answer.activity." + runID)
            }
            if let summary, summary.activity.readEmailCount > 0 {
                Button { emailDirection = .read } label: {
                    Label { Text(count(summary.activity.readEmailCount)) } icon: { EmailDirectionIcon(direction: .read) }
                }.accessibilityLabel("\(summary.activity.readEmailCount) read emails. View messages")
                    .accessibilityIdentifier("answer.read-emails." + runID)
            }
            if let summary, summary.activity.sentEmailCount > 0 {
                Button { emailDirection = .sent } label: {
                    Label { Text(count(summary.activity.sentEmailCount)) } icon: { EmailDirectionIcon(direction: .sent) }
                }
                    .accessibilityLabel("\(summary.activity.sentEmailCount) sent emails. View receipts")
                    .accessibilityIdentifier("answer.emails." + runID)
            }
            if let summary {
                ForEach(AccessKind.allCases.filter { summary.activity.access.count($0) > 0 }) { kind in
                    Button { accessKind = kind } label: { Label { Text(count(summary.activity.access.count(kind))) } icon: { AccessActionIcon(kind: kind) } }
                        .accessibilityLabel("\(summary.activity.access.count(kind)) \(kind.title.lowercased()). View sources")
                        .accessibilityIdentifier("answer.access." + kind.rawValue + "." + runID)
                }
            }
        }.monospacedDigit()
            .task(id: runID) { if !cachedOnly && (store.activityRootID != runID || store.activityState == .completed) { await store.loadAnswerActivity(runID: runID) } }
            .sheet(item: $showing) { AnswerActivitySheet(runID: runID, cachedOnly: cachedOnly, kind: $0) }
            .sheet(item: $accessKind, onDismiss: { if browseAfterDismiss { browseAfterDismiss = false; browseFiles?() } }) { kind in
                AccessActivityView(runID: runID, kind: kind, browseFiles: { browseAfterDismiss = true; accessKind = nil })
            }
            .sheet(item: $emailDirection) { EmailActivityView(runID: runID, direction: $0) }
    }
}

struct AnswerActivitySheet: View {
    let runID: String
    var cachedOnly = false
    var kind: ActivityDetail = .all
    @State private var search = ""
    @Environment(AssistantStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    if let value = store.answerActivities[runID] {
                        if kind != .tools {
                            HStack(spacing: 20) {
                                Label(summary(value.activity.cycleCount > 0 ? value.activity.cycleCount : value.activity.modelCalls, singular: value.activity.cycleCount > 0 ? "cycle" : "model call"), systemImage: "arrow.triangle.2.circlepath").foregroundStyle(PhoneTheme.mint)
                                if value.activity.toolCalls > 0 { Label(summary(value.activity.toolCalls, singular: "tool call"), systemImage: "wrench.and.screwdriver").foregroundStyle(PhoneTheme.tool) }
                            }.font(.subheadline).padding(.bottom, 12)
                        } else {
                            Label(summary(value.activity.toolCalls, singular: "tool call"), systemImage: "wrench.and.screwdriver").font(.subheadline).foregroundStyle(PhoneTheme.tool)
                            HStack(spacing: 9) {
                                Image(systemName: "magnifyingglass").foregroundStyle(PhoneTheme.secondary)
                                TextField("Find a tool or file", text: $search).textInputAutocapitalization(.never).autocorrectionDisabled()
                                    .accessibilityIdentifier("activity.tools.search")
                            }.padding(12).background(PhoneTheme.surface, in: RoundedRectangle(cornerRadius: 13))
                        }
                        if let first = value.activity.items.compactMap({ $0.startedAt ?? $0.timestamp }).min() {
                            VStack(alignment: .leading, spacing: 5) {
                                Text(first, format: .dateTime.day().month(.abbreviated).year()).foregroundStyle(PhoneTheme.ink)
                                Text("Oldest first · Times on this iPhone").foregroundStyle(PhoneTheme.secondary)
                            }.font(.caption).padding(.bottom, 4)
                        }
                        ForEach(value.issues, id: \.self) { Text($0).font(.footnote).foregroundStyle(PhoneTheme.amber) }
                        if !value.issues.isEmpty && !cachedOnly { Button("Try again") { Task { await store.loadAnswerActivity(runID: runID, retry: true) } } }
                        if value.activity.items.isEmpty && value.issues.isEmpty { Text("No recorded activity for this answer.").foregroundStyle(PhoneTheme.secondary) }
                        switch kind {
                        case .all: ForEach(value.activity.items) { ActivityEventRow(item: $0) }
                        case .cycles: CycleGraphView(activity: value.activity)
                        case .tools:
                            let allCalls = value.activity.items.filter { $0.kind == .tool }
                            let calls = Array(allCalls.enumerated()).filter { _, item in search.isEmpty || (item.title + " " + (item.inputText ?? "") + " " + item.detail).localizedCaseInsensitiveContains(search) }
                            if calls.isEmpty { Text(search.isEmpty ? "No tool calls recorded." : "No matching tool calls.").font(.footnote).foregroundStyle(PhoneTheme.secondary) }
                            ForEach(calls, id: \.element.id) { index, item in
                                ActivityEventRow(item: item, ordinal: index + 1)
                            }
                        }
                        if value.activity.wasTrimmed { Text("Showing up to 250 retained events; counts include earlier events.").font(.caption).foregroundStyle(PhoneTheme.secondary) }
                    } else { ProgressView("Loading activity…").frame(maxWidth: .infinity).padding(.top, 24) }
                }.padding(22)
            }.scrollDismissesKeyboard(.interactively).background(PhoneTheme.ground).navigationTitle(title).navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
                .task(id: runID) { if !cachedOnly { await store.loadAnswerActivity(runID: runID, retry: store.answerActivities[runID]?.issues.isEmpty == false) } }
        }
    }
    private var title: String {
        switch kind {
        case .all: store.answerActivities[runID]?.scopeTitle ?? "Answer activity"
        case .tools: "Tool calls"
        case .cycles: (store.answerActivities[runID]?.activity.cycleCount ?? 0) > 0 ? "Agent cycles" : "Model calls"
        }
    }
    private func summary(_ count: Int, singular: String) -> String { "\(count) " + singular + (count == 1 ? "" : "s") }

}
