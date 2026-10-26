import Foundation
import Security

/// Where a secret of the apps lives, by name. The apps use the Keychain (`KeychainSecretStore`);
/// the tests a `MemorySecretStore`.
public protocol SecretStore: Sendable {
    func read(_ name: String) throws -> Data?
    func write(_ name: String, _ data: Data) throws
    func remove(_ name: String) throws
}

/// The Keychain, the platform's own store for a credential: an item of this app's service, named,
/// readable after the first unlock of the device (so the notification service extension reads it
/// while the device is locked), bound to this device (never in a backup, never synced), shared
/// with the extension and the complication through the app group, which doubles as the keychain
/// access group. A build without the app group (an unsigned simulator build) keeps the item in
/// the app's own keychain.
public struct KeychainSecretStore: SecretStore {
    public static let service = "ai.abstractframework.assistant"
    public let accessGroup: String?

    public init(accessGroup: String?) { self.accessGroup = accessGroup }

    /// Whether this build may use the Keychain with `accessGroup` (a probe read): an unsigned
    /// simulator build has no entitlements at all and is refused with `errSecMissingEntitlement`,
    /// with or without a group.
    public var isUsable: Bool {
        var probe = query("probe")
        probe[kSecReturnData as String] = false
        return SecItemCopyMatching(probe as CFDictionary, nil) != errSecMissingEntitlement
    }

    private func query(_ name: String) -> [String: Any] {
        var q: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
                                kSecAttrService as String: Self.service,
                                kSecAttrAccount as String: name,
                                kSecUseDataProtectionKeychain as String: true]
        if let accessGroup { q[kSecAttrAccessGroup as String] = accessGroup }
        return q
    }

    public func read(_ name: String) throws -> Data? {
        var q = query(name)
        q[kSecReturnData as String] = true
        q[kSecMatchLimit as String] = kSecMatchLimitOne
        var out: CFTypeRef?
        let status = SecItemCopyMatching(q as CFDictionary, &out)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess else { throw KeychainError(status: status) }
        return out as? Data
    }

    public func write(_ name: String, _ data: Data) throws {
        let attributes: [String: Any] = [kSecValueData as String: data,
                                         kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly]
        var add = query(name)
        attributes.forEach { add[$0.key] = $0.value }
        let status = SecItemAdd(add as CFDictionary, nil)
        if status == errSecDuplicateItem {
            let update = SecItemUpdate(query(name) as CFDictionary, attributes as CFDictionary)
            guard update == errSecSuccess else { throw KeychainError(status: update) }
            return
        }
        guard status == errSecSuccess else { throw KeychainError(status: status) }
    }

    public func remove(_ name: String) throws {
        let status = SecItemDelete(query(name) as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else { throw KeychainError(status: status) }
    }
}

public struct KeychainError: Error, Equatable {
    public let status: OSStatus
    public var localizedDescription: String {
        (SecCopyErrorMessageString(status, nil) as String?) ?? "Keychain error \(status)"
    }
}

/// A store in memory, for the tests (and nothing else).
public final class MemorySecretStore: SecretStore, @unchecked Sendable {
    private let lock = NSLock()
    private var items: [String: Data] = [:]
    public init() {}
    public func read(_ name: String) throws -> Data? { lock.withLock { items[name] } }
    public func write(_ name: String, _ data: Data) throws { lock.withLock { items[name] = data } }
    public func remove(_ name: String) throws { lock.withLock { _ = items.removeValue(forKey: name) } }
    public var names: [String] { lock.withLock { Array(items.keys) } }
}

/// A plain file the OS protects (`ProtectedFile`), the store of a build that has no Keychain: an
/// unsigned simulator build (UI tests, screenshots). The apps on a device never use it.
public struct FileSecretStore: SecretStore {
    public let directory: URL
    public init(directory: URL) { self.directory = directory }
    public func read(_ name: String) throws -> Data? { try ProtectedFile(directory: directory, name: name).read() }
    public func write(_ name: String, _ data: Data) throws { try ProtectedFile(directory: directory, name: name).write(data) }
    public func remove(_ name: String) throws { ProtectedFile(directory: directory, name: name).remove() }
}
