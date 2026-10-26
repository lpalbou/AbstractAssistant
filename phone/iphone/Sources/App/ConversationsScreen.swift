import SwiftUI
import AssistantKit
import AbstractGatewayClient

struct ConversationsSheet: View {
    var onOpen: () -> Void
    var body: some View {
        NavigationStack {
            ConversationHistoryList(archived: false, onOpen: onOpen)
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Done", action: onOpen) } }
        }
    }
}

private struct ConversationHistoryList: View {
    let archived: Bool
    var onOpen: () -> Void
    @Environment(AssistantStore.self) private var store
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var search = ""
    @State private var archiving: SessionSummary?
    private var sessions: [SessionSummary] { archived ? store.archivedSessions : store.sessions }
    private var filtered: [SessionSummary] {
        sessions.filter { search.isEmpty || (store.titles[$0.id] ?? "Conversation").localizedStandardContains(search) }
    }
    var body: some View {
        List {
            if !archived {
                Button { store.newConversation(entity: store.selectedEntity); onOpen() } label: {
                    Label("New conversation", systemImage: "square.and.pencil")
                        .font(.body.weight(.semibold)).foregroundStyle(PhoneTheme.mint)
                        .frame(maxWidth: .infinity, minHeight: 34, alignment: .leading).padding(16)
                        .background(PhoneTheme.mint.opacity(0.12), in: RoundedRectangle(cornerRadius: 20))
                }.buttonStyle(.plain).disabled(!store.canSend).accessibilityIdentifier("conversations.new")
                    .listRowInsets(.init(top: 8, leading: 20, bottom: 10, trailing: 20))
                    .listRowBackground(Color.clear).listRowSeparator(.hidden)
                NavigationLink {
                    ConversationHistoryList(archived: true, onOpen: onOpen)
                } label: {
                    Label("Archived", systemImage: "archivebox").font(.subheadline).foregroundStyle(PhoneTheme.secondary)
                        .padding(.vertical, 8)
                }.accessibilityIdentifier("conversations.archived").listRowBackground(Color.clear).listRowSeparator(.hidden)
            }
            if let error = store.historyError {
                VStack(alignment: .leading, spacing: 10) {
                    Text(error).font(.footnote).foregroundStyle(PhoneTheme.amber)
                    if archived { Button("Try again") { Task { await store.loadArchivedConversations() } } }
                }.padding(.vertical, 8)
            }
            if archived && store.loadingArchived { ProgressView("Loading archived conversations…").padding(.vertical, 12) }
            if filtered.isEmpty && !store.loadingArchived {
                ContentUnavailableView(search.isEmpty ? (archived ? "Nothing archived" : "A fresh start") : "No conversations found",
                    systemImage: search.isEmpty ? (archived ? "archivebox" : "bubble.left.and.bubble.right") : "magnifyingglass",
                    description: Text(search.isEmpty ? (archived ? "Archived conversations can be restored here." : "Your conversations will appear here.") : "Try another search."))
            }
            ForEach(ConversationHistorySection.grouped(filtered)) { group in
                Section {
                    ForEach(group.sessions) { session in
                        row(session)
                            .listRowInsets(.init(top: 5, leading: 20, bottom: 5, trailing: 20))
                            .task(id: session.id) { await store.loadHistoryTitle(session) }
                    }
                } header: {
                    Text(group.id).font(.caption.weight(.semibold)).foregroundStyle(PhoneTheme.secondary).textCase(nil)
                }.listRowBackground(Color.clear).listRowSeparator(.hidden)
            }
        }
        .listStyle(.plain).listRowSeparator(.hidden).listRowBackground(Color.clear)
        .scrollContentBackground(.hidden).background(PhoneTheme.ground)
        .navigationTitle(archived ? "Archived" : "Conversations")
        .navigationBarTitleDisplayMode(.large)
        .searchable(text: $search, placement: .navigationBarDrawer(displayMode: .always), prompt: "Find a conversation")
        .searchPresentationToolbarBehavior(.avoidHidingContent)
        .refreshable { if archived { await store.loadArchivedConversations() } else { await store.refresh() } }
        .task { if archived { await store.loadArchivedConversations() } else { store.clearHistoryError() } }
        .onChange(of: store.contextID) { _, _ in archiving = nil; search = "" }
        .animation(reduceMotion ? nil : .snappy(duration: 0.25), value: sessions.map(\.id))
        .confirmationDialog("Archive conversation?", isPresented: Binding(get: { archiving != nil }, set: { if !$0 { archiving = nil } }), titleVisibility: .visible) {
            if let session = archiving {
                Button("Archive") { archiving = nil; Task { await store.setArchived(session, true) } }
            }
            Button("Cancel", role: .cancel) { archiving = nil }
        } message: { Text((archiving.flatMap { store.titles[$0.id] }.map { "“" + $0 + "”\n\n" } ?? "") + "This hides the conversation on all your devices. Nothing is deleted. You can restore it from Archived.") }
    }
    private func row(_ session: SessionSummary) -> some View {
        HStack(spacing: 12) {
            if archived { summary(session).frame(maxWidth: .infinity, alignment: .leading) }
            else {
                Button {
                    Task { await store.openSession(session); if store.error == nil { onOpen() } }
                } label: { summary(session).frame(maxWidth: .infinity, alignment: .leading).contentShape(Rectangle()) }
                    .buttonStyle(.plain).disabled(!store.canOpenConversation).accessibilityIdentifier("conversation.open." + session.id)
            }
            Button {
                if archived { Task { await store.setArchived(session, false) } }
                else { archiving = session }
            } label: {
                Group {
                    if store.sessionArchiveBusy.contains(session.id) { ProgressView().controlSize(.small) }
                    else { Image(systemName: archived ? "arrow.uturn.backward" : "archivebox").font(.system(size: 17, weight: .medium)) }
                }.foregroundStyle(PhoneTheme.lavender).frame(width: 44, height: 44)
                    .background(PhoneTheme.lavender.opacity(0.08), in: Circle())
            }.buttonStyle(.plain)
                .disabled(archived ? !store.sessionArchiveBusy.isEmpty : !store.canArchive(session))
                .opacity(!archived && session.anyTurnLive ? 0.35 : 1)
                .accessibilityLabel(archived ? "Restore conversation" : "Archive conversation")
                .accessibilityHint(!archived && session.anyTurnLive ? "Available after this conversation finishes." : "")
                .accessibilityIdentifier((archived ? "conversation.restore." : "conversation.archive.") + session.id)
        }.padding(16).background(PhoneTheme.surface, in: RoundedRectangle(cornerRadius: 20))
    }
    private func summary(_ session: SessionSummary) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(store.titles[session.id] ?? "Conversation").font(.subheadline.weight(.semibold))
                .foregroundStyle(PhoneTheme.ink).lineLimit(2).multilineTextAlignment(.leading)
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 14) { stats(session); state(session) }.fixedSize(horizontal: true, vertical: false)
                VStack(alignment: .leading, spacing: 8) {
                    ViewThatFits(in: .horizontal) {
                        HStack(spacing: 14) { stats(session) }.fixedSize(horizontal: true, vertical: false)
                        VStack(alignment: .leading, spacing: 6) { stats(session) }
                    }
                    state(session).fixedSize(horizontal: true, vertical: false)
                }
            }.font(.caption).foregroundStyle(PhoneTheme.secondary)
        }.accessibilityElement(children: .combine)
    }
    private func stat(_ text: String, symbol: String, color: Color = PhoneTheme.secondary) -> some View {
        HStack(spacing: 5) { Image(systemName: symbol); Text(text).monospacedDigit() }
            .foregroundStyle(color).lineLimit(1).fixedSize(horizontal: true, vertical: false)
    }
    @ViewBuilder private func stats(_ session: SessionSummary) -> some View {
        stat(session.turns.formatted() + (!archived && store.recentHistoryMayBePartial ? "+" : ""), symbol: "bubble.left.and.bubble.right")
            .accessibilityLabel((!archived && store.recentHistoryMayBePartial ? "At least " : "") + "\(session.turns) exchanges")
        if session.toolCalls > 0 {
            stat(session.toolCalls.formatted() + (!archived && store.recentHistoryMayBePartial ? "+" : ""), symbol: "wrench.and.screwdriver", color: PhoneTheme.tool)
                .accessibilityLabel((!archived && store.recentHistoryMayBePartial ? "At least " : "") + "\(session.toolCalls) tool calls")
        }
        if let at = session.updatedAt {
            TimelineView(.periodic(from: .now, by: 60)) { timeline in
                stat(ConversationHistorySection.age(at, now: timeline.date), symbol: "clock")
            }.fixedSize(horizontal: true, vertical: false).accessibilityLabel("Last activity " + ConversationHistorySection.age(at))
        }
    }
    @ViewBuilder private func state(_ session: SessionSummary) -> some View {
        if session.anyTurnNeedsPerson { stat("Needs you", symbol: "hand.raised", color: PhoneTheme.amber) }
        else if session.anyTurnLive { stat("Working", symbol: "circle.dotted", color: PhoneTheme.mint) }
        else if session.status == "failed" { stat("Failed", symbol: "exclamationmark.circle", color: PhoneTheme.amber) }
    }
}
