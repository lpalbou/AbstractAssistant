import Foundation

/// Disposable app-owned copies only. Originals and gateway artifacts are never removed.
public struct PhoneTemporaryStorage: Sendable {
    public enum Kind: String, CaseIterable, Sendable { case voice, imports, previews }
    public let temporaryDirectory: URL
    public var root: URL { temporaryDirectory.appending(path: "AbstractAssistant", directoryHint: .isDirectory) }

    public init(temporaryDirectory: URL = FileManager.default.temporaryDirectory) {
        self.temporaryDirectory = temporaryDirectory.standardizedFileURL
    }

    public func makeDirectory(for kind: Kind) throws -> URL {
        for ancestor in [root, root.appending(path: kind.rawValue)] {
            if (try? FileManager.default.destinationOfSymbolicLink(atPath: ancestor.path)) != nil {
                throw CocoaError(.fileWriteNoPermission)
            }
        }
        let folder = root.appending(path: kind.rawValue, directoryHint: .isDirectory)
            .appending(path: UUID().uuidString, directoryHint: .isDirectory)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        return folder
    }

    public func discard(_ url: URL) throws {
        let parts = url.standardizedFileURL.pathComponents
        let base = root.standardizedFileURL.pathComponents
        let folder: URL
        if parts.starts(with: base), parts.count >= base.count + 2,
           Kind(rawValue: parts[base.count]) != nil, UUID(uuidString: parts[base.count + 1]) != nil {
            for ancestor in [root, root.appending(path: parts[base.count])] {
                if (try? FileManager.default.destinationOfSymbolicLink(atPath: ancestor.path)) != nil {
                    throw CocoaError(.fileWriteNoPermission)
                }
            }
            folder = root.appending(path: parts[base.count]).appending(path: parts[base.count + 1])
        } else if url.deletingLastPathComponent().standardizedFileURL == temporaryDirectory,
                  Self.isLegacyOwned(url.lastPathComponent) {
            folder = url
        } else if url.deletingLastPathComponent().deletingLastPathComponent().standardizedFileURL == temporaryDirectory,
                  Self.isLegacyOwned(url.deletingLastPathComponent().lastPathComponent) {
            folder = url.deletingLastPathComponent()
        } else { throw CocoaError(.fileWriteNoPermission) }
        if FileManager.default.fileExists(atPath: folder.path) { try FileManager.default.removeItem(at: folder) }
    }

    /// Call once at process startup, before any capture/import/preview can begin.
    public func removeStaleFiles() throws {
        let manager = FileManager.default
        for url in try manager.contentsOfDirectory(at: temporaryDirectory, includingPropertiesForKeys: nil) {
            if url.lastPathComponent == root.lastPathComponent || Self.isLegacyOwned(url.lastPathComponent) {
                try manager.removeItem(at: url)
            }
        }
    }

    private static func isLegacyOwned(_ name: String) -> Bool {
        for prefix in ["phone-import-", "phone-attachment-"] where name.hasPrefix(prefix) {
            if UUID(uuidString: String(name.dropFirst(prefix.count))) != nil { return true }
        }
        for (prefix, suffix) in [("iphone-voice-", ".wav"), ("Photo-", ".jpg")] where name.hasPrefix(prefix) && name.hasSuffix(suffix) {
            if UUID(uuidString: String(name.dropFirst(prefix.count).dropLast(suffix.count))) != nil { return true }
        }
        return false
    }
}
