import CryptoKit
import Foundation

/// The files of earlier builds, read once so their content moves into the Keychain
/// (`SharedSignInStore`): `<name>.json` (plain, under Data Protection; a few days of 0.16) and
/// before it the ChaChaPoly pair `<name>.sealed` + `sealing.key` (0.15). `write` is kept for the
/// tests that plant those files; the apps no longer write here. Delete this type once no watch or
/// iPhone can still carry those files.
public struct ProtectedFile: Sendable {
    public let directory: URL
    public let name: String

    public init(directory: URL, name: String) {
        self.directory = directory; self.name = name
    }

    public var url: URL { directory.appending(path: name + ".json") }

    /// The content; nil when nothing is kept.
    public func read() throws -> Data? {
        let fm = FileManager.default
        if fm.fileExists(atPath: url.path) { return try Data(contentsOf: url) }
        if let legacy = try openLegacy() {
            try write(legacy)
            try? fm.removeItem(at: legacyDataURL); try? fm.removeItem(at: legacyKeyURL)
            return legacy
        }
        return nil
    }

    public func write(_ data: Data) throws {
        let fm = FileManager.default
        try fm.createDirectory(at: directory, withIntermediateDirectories: true)
        try data.write(to: url, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
        try fm.setAttributes([.posixPermissions: 0o600], ofItemAtPath: url.path)
        try Self.excludeFromBackup(url); try Self.excludeFromBackup(directory)
    }

    /// Forgets the content.
    public func remove() {
        try? FileManager.default.removeItem(at: url)
    }

    /// Whether the file is marked to stay out of backups (what `write` sets).
    public var isExcludedFromBackup: Bool {
        (try? url.resourceValues(forKeys: [.isExcludedFromBackupKey]).isExcludedFromBackup) == true
    }

    private static func excludeFromBackup(_ target: URL) throws {
        var u = target, values = URLResourceValues()
        values.isExcludedFromBackup = true
        try u.setResourceValues(values)
    }

    // MARK: The sealed pair of 0.15 (read once, then gone)

    var legacyDataURL: URL { directory.appending(path: name + ".sealed") }
    var legacyKeyURL: URL { directory.appending(path: "sealing.key") }

    private func openLegacy() throws -> Data? {
        let fm = FileManager.default
        guard fm.fileExists(atPath: legacyDataURL.path), fm.fileExists(atPath: legacyKeyURL.path) else { return nil }
        let raw = try Data(contentsOf: legacyKeyURL)
        guard raw.count == 32 else { return nil }
        let box = try ChaChaPoly.SealedBox(combined: Data(contentsOf: legacyDataURL))
        return try ChaChaPoly.open(box, using: SymmetricKey(data: raw))
    }
}
