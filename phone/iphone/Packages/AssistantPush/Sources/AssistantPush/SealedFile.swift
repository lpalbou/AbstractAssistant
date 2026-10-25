import CryptoKit
import Foundation

/// A secret kept in a file, sealed with ChaChaPoly under a 256-bit key kept in its own private
/// file (`sealing.key`, 0600) in the same folder: the framework's file-sealed rule (no OS keychain).
/// Both files are readable after the first unlock, so a notification service extension can read
/// the sign-in while the device is locked.
public struct SealedFile: Sendable {
    public let directory: URL
    public let name: String

    public init(directory: URL, name: String) {
        self.directory = directory; self.name = name
    }

    public var keyURL: URL { directory.appending(path: "sealing.key") }
    public var dataURL: URL { directory.appending(path: name + ".sealed") }

    /// The opened content; nil when nothing is kept (or its key is gone: it cannot be opened).
    public func read() throws -> Data? {
        let fm = FileManager.default
        guard fm.fileExists(atPath: dataURL.path), let key = try existingKey() else { return nil }
        let box = try ChaChaPoly.SealedBox(combined: Data(contentsOf: dataURL))
        return try ChaChaPoly.open(box, using: key)
    }

    public func write(_ data: Data) throws {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let key = try existingKey() ?? makeKey()
        let sealed = try ChaChaPoly.seal(data, using: key).combined
        try sealed.write(to: dataURL, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: dataURL.path)
    }

    /// Forgets the content (the key stays for the next write).
    public func remove() {
        try? FileManager.default.removeItem(at: dataURL)
    }

    private func existingKey() throws -> SymmetricKey? {
        guard FileManager.default.fileExists(atPath: keyURL.path) else { return nil }
        let raw = try Data(contentsOf: keyURL)
        guard raw.count == 32 else { throw SealedFileError.badKey }
        return SymmetricKey(data: raw)
    }

    private func makeKey() throws -> SymmetricKey {
        let key = SymmetricKey(size: .bits256)
        let raw = key.withUnsafeBytes { Data($0) }
        try raw.write(to: keyURL, options: [.withoutOverwriting, .completeFileProtectionUntilFirstUserAuthentication])
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: keyURL.path)
        return key
    }
}

public enum SealedFileError: Error, Equatable {
    case badKey
}
