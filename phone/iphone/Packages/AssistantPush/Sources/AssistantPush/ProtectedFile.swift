import CryptoKit
import Foundation

/// A secret kept in a plain file the operating system protects: written with Data Protection
/// "complete until first user authentication" (encrypted at rest by the device, readable once the
/// device has been unlocked after a boot, so a notification service extension can read it while
/// the device is locked), owner-only permissions, excluded from backups, deleted on request.
/// The framework's rule: no OS keychain, the same behaviour on every installation; and no
/// encryption of our own on top (a key kept beside the data protects nothing and adds code).
///
/// Until 0.16.0 the file was sealed with ChaChaPoly under a key file in the same folder
/// (`signin.sealed` + `sealing.key`): a first read of that pair moves its content into the plain
/// file and deletes both, so a person signed in before the change stays signed in.
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
