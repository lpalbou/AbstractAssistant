import Foundation
import Observation
import UniformTypeIdentifiers
import AbstractGatewayClient
import AssistantKit

struct SessionWorkspace: Identifiable {
    var workspace: RunWorkspace
    var inventory: WorkspaceListing
    var id: String { workspace.root }
}

@MainActor @Observable final class SessionFilesController {
    private(set) var artifacts: [PhoneArtifact] = []
    private(set) var workspaces: [SessionWorkspace] = []
    private(set) var issues: [String] = []
    private(set) var loading = false
    private(set) var downloading = false
    private(set) var hasMoreArtifacts = false
    private(set) var loaded = false
    var includeVoice = false
    var preview: URL? { didSet { if preview == nil { clearPreview() } } }
    var error: String?
    var onUnauthorized: (() -> Void)?
    private var binding: String?
    private var epoch = UUID()
    private var refreshID = UUID()
    private var downloadID = UUID()
    private var nextOffset = 0
    private var explicitFileIDs: Set<String>?
    private var rawArtifacts: [PhoneArtifact] = []
    private var task: Task<Void, Never>?
    private var ownedFolder: URL?
    private let storage: PhoneTemporaryStorage
    init(storage: PhoneTemporaryStorage = .init()) { self.storage = storage }
    isolated deinit { task?.cancel(); if let ownedFolder { try? FileManager.default.removeItem(at: ownedFolder) } }
    func bind(_ key: String) {
        guard key != binding else { return }
        epoch = UUID(); refreshID = UUID(); downloadID = UUID(); task?.cancel(); task = nil; preview = nil; clearPreview()
        binding = key; artifacts = []; workspaces = []; issues = []; error = nil
        loading = false; downloading = false; loaded = false; includeVoice = false; hasMoreArtifacts = false; nextOffset = 0; explicitFileIDs = nil; rawArtifacts = []
    }
    var visibleArtifacts: [PhoneArtifact] { includeVoice ? artifacts : artifacts.filter { !$0.isConversationVoice } }
    func visible(_ entry: WorkspaceEntry) -> Bool {
        includeVoice || !Self.isConversationVoicePath(entry.path)
    }
    static func isConversationVoicePath(_ path: String) -> Bool {
        path.hasPrefix("voice/dictation/")
    }
    var count: Int {
        visibleArtifacts.count + workspaces.reduce(0) { $0 + $1.inventory.entries.filter { !$0.isDirectory && visible($0) }.count }
    }
    var countLabel: String { loaded ? (count == 0 && !issues.isEmpty ? "…" : String(count) + (hasMoreArtifacts || !issues.isEmpty || workspaces.contains(where: { $0.inventory.truncated }) ? "+" : "")) : "…" }
    func refresh(client: any GatewayClient, sessionID: String, runIDs: [String], explicitFileIDs: Set<String>? = nil) async {
        let context = epoch, operation = UUID(); refreshID = operation; loading = true; issues = []; error = nil; self.explicitFileIDs = explicitFileIDs
        defer { if context == epoch, operation == refreshID { loading = false } }
        do {
            let page = try await client.artifactPage(sessionID: sessionID, offset: 0, includeVoice: true)
            guard context == epoch, operation == refreshID, !Task.isCancelled else { return }
            rawArtifacts = page.items; artifacts = PhoneArtifact.classifyingConversationVoice(page.items); nextOffset = page.nextOffset; hasMoreArtifacts = page.hasMore; issues += page.warnings.filter { $0 != "query_or_scope_requires_gateway_post_filter" }
        } catch {
            guard context == epoch, operation == refreshID else { return }
            problem(error, prefix: "Attachments could not be loaded. ")
            if error as? GatewayError == .unauthorized { return }
        }
        var sessionRuns = runIDs
        if explicitFileIDs != nil {
            do {
                let turns = try await client.turns(ofSession: sessionID)
                guard context == epoch, operation == refreshID, !Task.isCancelled else { return }
                var unique: Set<String> = []; sessionRuns = (sessionRuns + turns.map(\.runId)).filter { unique.insert($0).inserted }
                guard turns.count <= 64 else { throw FileHistoryIssue.tooLong }
                let protected = try await withThrowingTaskGroup(of: Set<String>.self) { group in
                    func add(_ index: Int) {
                        let id = turns[index].runId
                        group.addTask {
                            let run = try await client.run(id: id), input = try await client.input(ofRun: id)
                            return Set((run.mediaArtifacts + input.attachments).map(\.artifactId))
                        }
                    }
                    var next = min(4, turns.count), result = explicitFileIDs ?? []
                    for i in 0..<next { add(i) }
                    while let ids = try await group.next() {
                        result.formUnion(ids)
                        if next < turns.count { add(next); next += 1 }
                    }
                    return result
                }
                guard context == epoch, operation == refreshID, !Task.isCancelled else { return }
                self.explicitFileIDs = protected
                artifacts = PhoneArtifact.classifyingConversationVoice(rawArtifacts, explicitFileIDs: protected)
            } catch {
                guard context == epoch, operation == refreshID else { return }
                if error is CancellationError { return }
                self.explicitFileIDs = nil
                issues.append("Some older audio remains visible because its conversation history could not be fully checked.")
                if error as? GatewayError == .unauthorized { onUnauthorized?(); return }
            }
        }
        var queue = Array(sessionRuns.reversed()), seen: Set<String> = [], discovered: [RunWorkspace] = []
        var runsWithoutWorkspace = 0
        while !queue.isEmpty, seen.count < 64 {
            guard context == epoch, operation == refreshID, !Task.isCancelled else { return }
            let id = queue.removeFirst(); guard seen.insert(id).inserted else { continue }
            do {
                let info = try await client.workspace(runID: id)
                guard context == epoch, operation == refreshID else { return }
                if !discovered.contains(where: { $0.root == info.root }) { discovered.append(info) }
            } catch {
                guard context == epoch, operation == refreshID else { return }
                if case .unsupported? = error as? PhoneAttachmentError { }
                else if case .http(status: 409, body: _)? = error as? GatewayError { runsWithoutWorkspace += 1 }
                else { problem(error, prefix: "A run's workspace could not be opened. ") }
                if error as? GatewayError == .unauthorized { return }
            }
            do {
                let children = try await client.childRuns(ofRunID: id)
                guard context == epoch, operation == refreshID else { return }
                for child in children where child.parentRunId == id && !seen.contains(child.runId) && !queue.contains(child.runId) { queue.append(child.runId) }
            } catch {
                guard context == epoch, operation == refreshID else { return }
                problem(error, prefix: "Some nested run workspaces could not be loaded. ")
                if error as? GatewayError == .unauthorized { return }
            }
        }
        if !queue.isEmpty { issues.append("Showing workspaces from the first 64 runs. Open an earlier conversation to inspect its files.") }
        var spaces: [SessionWorkspace] = []
        for info in discovered {
            guard context == epoch, operation == refreshID, !Task.isCancelled else { return }
            if !info.exists { issues.append("A workspace has not been created yet."); continue }
            do {
                let listing = try await client.workspaceFiles(runID: info.runID, path: "", recursive: true, limit: 1000)
                guard context == epoch, operation == refreshID else { return }
                spaces.append(.init(workspace: info, inventory: listing))
            } catch {
                guard context == epoch, operation == refreshID else { return }; problem(error, prefix: "Workspace files could not be loaded. ")
                if error as? GatewayError == .unauthorized { return }
            }
        }
        guard context == epoch, operation == refreshID else { return }
        if spaces.isEmpty && runsWithoutWorkspace > 0 { issues.append("No workspace is available for this conversation yet.") }
        workspaces = spaces; loaded = true; issues = Array(Set(issues)).sorted()
    }
    func loadMore(client: any GatewayClient, sessionID: String) async {
        guard hasMoreArtifacts, !loading else { return }
        let context = epoch, operation = refreshID, offset = nextOffset; loading = true
        defer { if context == epoch, operation == refreshID { loading = false } }
        do {
            let page = try await client.artifactPage(sessionID: sessionID, offset: offset, includeVoice: true)
            guard context == epoch, operation == refreshID, !Task.isCancelled else { return }
            guard !page.hasMore || page.nextOffset > offset else { throw LedgerStreamError.invalidCursor }
            let seen = Set(rawArtifacts.map(\.id)), fresh = page.items.filter { !seen.contains($0.id) }
            guard !page.hasMore || !fresh.isEmpty else { throw LedgerStreamError.invalidCursor }
            rawArtifacts += fresh
            artifacts = PhoneArtifact.classifyingConversationVoice(rawArtifacts, explicitFileIDs: explicitFileIDs)
            nextOffset = page.nextOffset; hasMoreArtifacts = page.hasMore; issues += page.warnings.filter { $0 != "query_or_scope_requires_gateway_post_filter" }
        } catch { if context == epoch, operation == refreshID { problem(error, prefix: "More attachments could not be loaded. ") } }
    }
    func open(_ file: PhoneArtifact, client: any GatewayClient) {
        download(filename: file.filename) { url in try await client.download(file, to: url) }
    }
    func open(_ entry: WorkspaceEntry, workspace: RunWorkspace, client: any GatewayClient) {
        download(filename: entry.name) { url in try await client.downloadWorkspaceFile(runID: workspace.runID, entry: entry, to: url) }
    }
    private func download(filename: String, operation: @escaping @Sendable (URL) async throws -> Void) {
        guard !downloading else { return }
        preview = nil; clearPreview(); error = nil; downloading = true
        let context = epoch, operationID = UUID(); downloadID = operationID
        task = Task {
            defer { if context == epoch, operationID == downloadID { downloading = false } }
            var folder: URL?
            do {
                let created = try storage.makeDirectory(for: .previews); folder = created
                let url = created.appending(path: PhoneArtifact.safeFilename(filename))
                try await operation(url); try Task.checkCancellation()
                guard context == epoch, operationID == downloadID else { try? storage.discard(created); return }
                ownedFolder = created; preview = url
            } catch {
                if let folder { try? storage.discard(folder) }
                if context == epoch, operationID == downloadID, !(error is CancellationError) { self.error = error.localizedDescription; if error as? GatewayError == .unauthorized { onUnauthorized?() } }
            }
        }
    }
    func cancelDownload() { downloadID = UUID(); task?.cancel(); task = nil; downloading = false }
    private func clearPreview() { if let ownedFolder { try? storage.discard(ownedFolder) }; ownedFolder = nil }
    private func problem(_ error: Error, prefix: String) {
        guard !(error is CancellationError) else { return }
        issues.append(prefix + error.localizedDescription)
        if error as? GatewayError == .unauthorized { onUnauthorized?() }
    }
}

private enum FileHistoryIssue: Error { case tooLong }
