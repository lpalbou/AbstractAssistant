import Foundation
import CryptoKit
import PhoneGatewayClient

public struct ConversationExportFile: Identifiable, Sendable {
    public let id: String
    public let url: URL
    public let contentType: String
    public var name: String { url.lastPathComponent }
}
public struct ConversationExportTurn: Sendable {
    public let speaker: String
    public let text: String
    public let fileIDs: [String]
}
public struct ConversationExport: Sendable {
    public let folder: URL
    public let turns: [ConversationExportTurn]
    public let files: [ConversationExportFile]
}
public enum ConversationExportError: Error, LocalizedError {
    case incompleteHistory, missingFile(String), tooLarge, tooManyFiles
    public var errorDescription: String? {
        switch self {
        case .incompleteHistory: "Some file activity could not be loaded. Try sharing again once the gateway is available."
        case .missingFile(let name): "“\(name)” could not be included. It may have moved or been deleted."
        case .tooLarge: "These files are too large to share together. Share large files individually from Conversation files."
        case .tooManyFiles: "This conversation has too many files to share together. Share files individually from Conversation files."
        }
    }
}

/// Share explicit media and positively recorded writes, never an unrelated workspace tree.
public struct ConversationExportBuilder: Sendable {
    public let storage: PhoneTemporaryStorage
    public init(storage: PhoneTemporaryStorage = .init()) { self.storage = storage }
    public func prepare(messages: [ConversationMessage], responder: String, client: any GatewayClient,
                        activities: [String: AnswerActivity] = [:]) async throws -> ConversationExport {
        let folder = try storage.makeDirectory(for: .exports)
        do {
            let filesFolder = folder.appending(path: "Files", directoryHint: .isDirectory)
            try FileManager.default.createDirectory(at: filesFolder, withIntermediateDirectories: true)
            var files: [ConversationExportFile] = [], turns: [ConversationExportTurn] = []
            var identities: [String: String] = [:], contentIDs: [String: String] = [:], names: Set<String> = []
            var totalBytes = 0
            func filename(_ original: String) -> String {
                let safe = PhoneArtifact.safeFilename(original), base = (safe as NSString).deletingPathExtension, ext = (safe as NSString).pathExtension
                var result = safe, index = 2
                while !names.insert(result.lowercased()).inserted { result = base + " (\(index))" + (ext.isEmpty ? "" : "." + ext); index += 1 }
                return result
            }
            func accept(_ url: URL, identity: String, originalName: String, contentType: String) throws -> String {
                let handle = try FileHandle(forReadingFrom: url); defer { try? handle.close() }
                var hash = SHA256(), bytes = 0
                while let part = try handle.read(upToCount: 1_048_576), !part.isEmpty {
                    try Task.checkCancellation(); bytes += part.count; hash.update(data: part)
                    if bytes > 200_000_000 { throw ConversationExportError.tooLarge }
                }
                let contentKey = PhoneArtifact.safeFilename(originalName).lowercased() + ":" + hash.finalize().map { String(format: "%02x", $0) }.joined()
                if let existing = contentIDs[contentKey] { try FileManager.default.removeItem(at: url); identities[identity] = existing; return existing }
                guard bytes + totalBytes <= 200_000_000 else { throw ConversationExportError.tooLarge }
                guard files.count < 100 else { throw ConversationExportError.tooManyFiles }
                let id = UUID().uuidString
                files.append(.init(id: id, url: url, contentType: contentType)); identities[identity] = id; contentIDs[contentKey] = id; totalBytes += bytes
                return id
            }
            for message in messages where message.role != .notice {
                try Task.checkCancellation()
                var ids: [String] = []
                for file in message.artifacts where !file.isConversationVoice {
                    let identity = "artifact:" + file.id
                    if let id = identities[identity] { if !ids.contains(id) { ids.append(id) }; continue }
                    guard file.size <= 200_000_000 else { throw ConversationExportError.tooLarge }
                    let url = filesFolder.appending(path: filename(file.filename))
                    try await client.download(file, to: url); try Task.checkCancellation()
                    ids.append(try accept(url, identity: identity, originalName: file.filename, contentType: file.contentType))
                }
                if message.role == .assistant, let run = message.runID {
                    let summary: AnswerActivity
                    if let cached = activities[run], cached.issues.isEmpty { summary = cached }
                    else { summary = try await AnswerActivity.load(runID: run, client: client) }
                    guard summary.issues.isEmpty else { throw ConversationExportError.incompleteHistory }
                    guard summary.activity.access.items(.filesChanged).count == summary.activity.access.count(.filesChanged) else { throw ConversationExportError.incompleteHistory }
                    for entry in summary.activity.access.items(.filesChanged) {
                        let space = try await client.workspace(runID: entry.runID)
                        let prefix = space.root.hasSuffix("/") ? space.root : space.root + "/"
                        let path = entry.target.hasPrefix(prefix) ? String(entry.target.dropFirst(prefix.count)) : entry.target
                        guard !path.isEmpty, WorkspaceEntry.validPath(path) else { throw ConversationExportError.missingFile((entry.target as NSString).lastPathComponent) }
                        let identity = "workspace:" + space.root + ":" + path
                        if let id = identities[identity] { if !ids.contains(id) { ids.append(id) }; continue }
                        let listing = try await client.workspaceFiles(runID: space.runID, path: (path as NSString).deletingLastPathComponent, recursive: false, limit: nil)
                        guard let file = listing.entries.first(where: { $0.path == path && !$0.isDirectory }) else { throw ConversationExportError.missingFile((path as NSString).lastPathComponent) }
                        guard (file.size ?? 0) <= 200_000_000 else { throw ConversationExportError.tooLarge }
                        let url = filesFolder.appending(path: filename(file.name))
                        try await client.downloadWorkspaceFile(runID: space.runID, entry: file, to: url); try Task.checkCancellation()
                        ids.append(try accept(url, identity: identity, originalName: file.name, contentType: ""))
                    }
                }
                if !message.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !ids.isEmpty {
                    var seen: Set<String> = []
                    turns.append(.init(speaker: message.role == .user ? "You" : responder, text: message.text, fileIDs: ids.filter { seen.insert($0).inserted }))
                }
            }
            try Task.checkCancellation()
            return .init(folder: folder, turns: turns, files: files)
        } catch { try? storage.discard(folder); throw error }
    }
}
