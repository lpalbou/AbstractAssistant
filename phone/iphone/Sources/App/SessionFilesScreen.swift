import SwiftUI
import AssistantKit
import AbstractGatewayClient

struct SessionFilesScreen: View {
    let files: SessionFilesController
    let runIDs: [String]
    @Environment(AssistantStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        @Bindable var files = files
        NavigationStack {
            List {
                Section {
                    Toggle("Conversation audio", isOn: $files.includeVoice).tint(PhoneTheme.mint).accessibilityIdentifier("files.voice")
                } footer: {
                    if files.artifacts.contains(where: \.inferredConversationVoice) { Text("Older conversation audio is identified from this conversation’s history.") }
                }
                if let error = files.error { Section { ErrorBanner(message: error) } }
                if files.loading { ProgressView("Loading files…") }
                ForEach(Array(files.workspaces.enumerated()), id: \.element.id) { index, space in
                    Section(files.workspaces.count == 1 ? "Workspace" : "Workspace \(index + 1)") {
                        WorkspaceRows(entries: space.inventory.entries.filter { ($0.path as NSString).deletingLastPathComponent.isEmpty && files.visible($0) }, workspace: space.workspace, files: files)
                        if space.inventory.truncated {
                            NavigationLink("Browse all folders") { WorkspaceFolderScreen(workspace: space.workspace, path: "", title: "Workspace", files: files) }
                        }
                        if space.inventory.entries.isEmpty { Text("No workspace files yet").foregroundStyle(PhoneTheme.secondary) }
                    }
                }
                if !files.visibleArtifacts.isEmpty {
                    Section("Attachments") { ArtifactFolderRows(artifacts: files.visibleArtifacts, prefix: "", files: files) }
                }
                if files.hasMoreArtifacts, let client = store.client {
                    Button("Load more attachments") { Task { await files.loadMore(client: client, sessionID: store.sessionID) } }.disabled(files.loading)
                }
                ForEach(files.issues, id: \.self) { issue in Text(issue).font(.footnote).foregroundStyle(PhoneTheme.amber).textSelection(.enabled) }
                if files.loaded && files.count == 0 && !files.loading {
                    ContentUnavailableView("No files to show", systemImage: "folder", description: Text(files.includeVoice ? "Files saved or attached in this conversation appear here." : "Conversation audio is hidden. Other saved and attached files appear here."))
                }
            }
            .navigationTitle("Conversation files").navigationBarTitleDisplayMode(.inline)
            .scrollContentBackground(.hidden).background(PhoneTheme.ground)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
            .task { await refresh() }.refreshable { await refresh() }
            .onDisappear { if files.preview == nil { files.cancelDownload() } }
            .safeAreaInset(edge: .bottom) { if files.downloading { HStack { ProgressView(); Text("Opening file…").font(.footnote); Spacer(); Button("Cancel") { files.cancelDownload() } }.padding().background(PhoneTheme.ground) } }
            .fullScreenCover(isPresented: Binding(get: { files.preview != nil }, set: { if !$0 { files.preview = nil } })) {
                if let url = files.preview { ArtifactPreview(url: url) { files.preview = nil } }
            }
        }
    }
    private func refresh() async { if let client = store.client { await files.refresh(client: client, sessionID: store.sessionID, runIDs: runIDs, explicitFileIDs: Set(store.messages.flatMap(\.artifacts).map(\.artifactId))) } }
}

private struct WorkspaceRows: View {
    let entries: [WorkspaceEntry]
    let workspace: RunWorkspace
    let files: SessionFilesController
    @Environment(AssistantStore.self) private var store
    var body: some View {
        ForEach(entries.sorted { a, b in a.isDirectory != b.isDirectory ? a.isDirectory : a.name.localizedStandardCompare(b.name) == .orderedAscending }) { entry in
            if entry.isDirectory {
                NavigationLink { WorkspaceFolderScreen(workspace: workspace, path: entry.path, title: entry.name, files: files) } label: {
                    Label(entry.name, systemImage: "folder").foregroundStyle(PhoneTheme.ink).padding(.vertical, 5)
                }
            } else {
                Button { if let client = store.client { files.open(entry, workspace: workspace, client: client) } } label: {
                    FileBrowserRow(name: entry.name, detail: sizeText(entry.size), symbol: "doc.text")
                }.disabled(files.downloading).accessibilityIdentifier("files.workspace." + entry.path)
            }
        }
    }
}

private struct WorkspaceFolderScreen: View {
    let workspace: RunWorkspace
    let path: String
    let title: String
    let files: SessionFilesController
    @Environment(AssistantStore.self) private var store
    @State private var listing: WorkspaceListing?
    @State private var issue: String?
    @State private var loading = false
    var body: some View {
        List {
            if let issue { ErrorBanner(message: issue); Button("Try again") { Task { await load() } } }
            if let listing {
                WorkspaceRows(entries: listing.entries.filter(files.visible), workspace: workspace, files: files)
                if listing.truncated { Button("Load entire folder") { Task { await load(limit: nil) } } }
                if let hidden = listing.hidden, hidden.values.reduce(0, +) > 0 { Text("Some entries are hidden by the gateway’s access rules.").font(.caption).foregroundStyle(PhoneTheme.secondary) }
                if listing.entries.filter(files.visible).isEmpty { Text("This folder has no visible files.").foregroundStyle(PhoneTheme.secondary) }
            }
            if loading { ProgressView() }
        }.scrollContentBackground(.hidden).background(PhoneTheme.ground)
            .navigationTitle(title).navigationBarTitleDisplayMode(.inline)
            .task(id: path) { await load() }.refreshable { await load() }
    }
    private func load(limit: Int? = 1000) async {
        guard let client = store.client else { return }
        loading = true; issue = nil; let context = store.contextID, session = store.sessionID
        defer { loading = false }
        do {
            let value = try await client.workspaceFiles(runID: workspace.runID, path: path, recursive: false, limit: limit)
            guard !Task.isCancelled, context == store.contextID, session == store.sessionID else { return }
            listing = value
        } catch {
            guard context == store.contextID, session == store.sessionID, !(error is CancellationError) else { return }
            issue = error.localizedDescription
            if error as? GatewayError == .unauthorized { store.authenticationExpired() }
        }
    }
}

private struct ArtifactFolderRows: View {
    let artifacts: [PhoneArtifact]
    let prefix: String
    let files: SessionFilesController
    @Environment(AssistantStore.self) private var store
    private func path(_ file: PhoneArtifact) -> String {
        guard var path = file.sourcePath else { return file.filename }
        if path.hasPrefix("client:") { path = String(path.dropFirst(7)) }
        guard WorkspaceEntry.validPath(path), !path.isEmpty else { return file.filename }
        return path
    }
    private var children: [String] {
        Array(Set(artifacts.compactMap { file -> String? in
            let value = path(file); guard value.hasPrefix(prefix) else { return nil }
            return String(value.dropFirst(prefix.count)).split(separator: "/").first.map(String.init)
        })).sorted { $0.localizedStandardCompare($1) == .orderedAscending }
    }
    var body: some View {
        ForEach(children, id: \.self) { name in
            let child = prefix + name
            let folder = artifacts.contains { path($0).hasPrefix(child + "/") }
            if folder {
                NavigationLink {
                    List { ArtifactFolderRows(artifacts: artifacts, prefix: child + "/", files: files) }
                        .scrollContentBackground(.hidden).background(PhoneTheme.ground).navigationTitle(name).navigationBarTitleDisplayMode(.inline)
                } label: { Label(name, systemImage: "folder").foregroundStyle(PhoneTheme.ink).padding(.vertical, 5) }
            }
            ForEach(artifacts.filter { path($0) == child }) { file in
                Button { if let client = store.client { files.open(file, client: client) } } label: {
                    FileBrowserRow(name: file.filename, detail: (file.semanticKind == "transcript" ? "Transcript · " : "") + sizeText(file.size), symbol: file.symbol)
                }.disabled(files.downloading).accessibilityIdentifier("files.artifact." + file.artifactId)
            }
        }
    }
}

private struct FileBrowserRow: View {
    let name: String
    let detail: String
    let symbol: String
    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: symbol).font(.title3).foregroundStyle(PhoneTheme.mint).frame(width: 26)
            VStack(alignment: .leading, spacing: 4) { Text(name).font(.subheadline).foregroundStyle(PhoneTheme.ink).lineLimit(2); Text(detail).font(.caption).foregroundStyle(PhoneTheme.secondary) }
            Spacer(minLength: 8); Image(systemName: "arrow.up.left.and.arrow.down.right").font(.caption).foregroundStyle(PhoneTheme.secondary)
        }.padding(.vertical, 7).frame(minHeight: 44)
    }
}
private func sizeText(_ size: Int?) -> String { size.map { ByteCountFormatter.string(fromByteCount: Int64($0), countStyle: .file) } ?? "File" }
