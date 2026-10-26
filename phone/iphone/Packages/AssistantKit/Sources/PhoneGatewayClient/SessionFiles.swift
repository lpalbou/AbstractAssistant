import Foundation

public struct SessionArtifactPage: Sendable {
    public var items: [PhoneArtifact]
    public var total: Int
    public var hasMore: Bool
    public var nextOffset: Int
    public var warnings: [String]
    public init(items: [PhoneArtifact], total: Int? = nil, hasMore: Bool = false, nextOffset: Int? = nil, warnings: [String] = []) {
        self.items = items; self.total = total ?? items.count; self.hasMore = hasMore; self.nextOffset = nextOffset ?? items.count; self.warnings = warnings
    }
}
public struct RunWorkspace: Decodable, Equatable, Sendable, Identifiable {
    public var runID: String
    public var root: String
    public var exists: Bool
    public var kind: String?
    public var id: String { root }
    public init(runID: String, root: String, exists: Bool = true, kind: String? = nil) { self.runID = runID; self.root = root; self.exists = exists; self.kind = kind }
    enum CodingKeys: String, CodingKey { case runID = "run_id", root = "workspace_root", exists, kind }
}
public struct WorkspaceEntry: Decodable, Hashable, Sendable, Identifiable {
    public var name: String
    public var path: String
    public var type: String
    public var size: Int?
    public var modified: String?
    public var id: String { path }
    public var isDirectory: Bool { type == "dir" }
    public init(name: String, path: String, type: String = "file", size: Int? = nil, modified: String? = nil) {
        self.name = name; self.path = path; self.type = type; self.size = size; self.modified = modified
    }
    enum CodingKeys: String, CodingKey { case name, path, type, size = "size_bytes", modified = "mtime" }
    public static func validPath(_ path: String) -> Bool {
        !path.hasPrefix("/") && !path.contains("\\") && !path.contains("\0") && !(path.count > 1 && path[path.index(after: path.startIndex)] == ":") && !path.split(separator: "/").contains("..")
    }
}
public struct WorkspaceListing: Decodable, Sendable {
    public var path: String
    public var entries: [WorkspaceEntry]
    public var truncated: Bool
    public var hidden: [String: Int]?
    public init(path: String = "", entries: [WorkspaceEntry], truncated: Bool = false, hidden: [String: Int]? = nil) {
        self.path = path; self.entries = entries; self.truncated = truncated; self.hidden = hidden
    }
}
public extension GatewayClient {
    func artifactPage(sessionID: String, offset: Int, includeVoice: Bool) async throws -> SessionArtifactPage {
        let items = try await artifacts(sessionId: sessionID); return .init(items: items)
    }
    func workspace(runID: String) async throws -> RunWorkspace { throw PhoneAttachmentError.unsupported }
    func workspaceFiles(runID: String, path: String, recursive: Bool, limit: Int?) async throws -> WorkspaceListing { throw PhoneAttachmentError.unsupported }
    func downloadWorkspaceFile(runID: String, entry: WorkspaceEntry, to destination: URL) async throws { throw PhoneAttachmentError.unsupported }
}
