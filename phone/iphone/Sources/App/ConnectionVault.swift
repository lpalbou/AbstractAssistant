import Foundation
import Security
import AssistantKit

enum ConnectionVault {
    private static let service = "ai.abstractframework.assistant.iphone.connection"
    private static var query: [String: Any] { [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: "gateway"] }
    static func read() throws -> SavedConnection? {
        var request = query
        request[kSecReturnData as String] = true; request[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        let status = SecItemCopyMatching(request as CFDictionary, &result)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess, let data = result as? Data else { throw VaultError(status: status) }
        return try JSONDecoder().decode(SavedConnection.self, from: data)
    }
    static func save(_ connection: SavedConnection) throws {
        let data = try JSONEncoder().encode(connection)
        let values: [String: Any] = [kSecValueData as String: data, kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly]
        let status = SecItemUpdate(query as CFDictionary, values as CFDictionary)
        if status == errSecItemNotFound {
            let added = SecItemAdd(query.merging(values) { _, new in new } as CFDictionary, nil)
            guard added == errSecSuccess else { throw VaultError(status: added) }
        } else if status != errSecSuccess { throw VaultError(status: status) }
    }
    static func remove() throws {
        let status = SecItemDelete(query as CFDictionary)
        if status != errSecSuccess && status != errSecItemNotFound { throw VaultError(status: status) }
    }
    struct VaultError: LocalizedError {
        let status: OSStatus
        var errorDescription: String? { "The iPhone couldn’t access your saved sign-in. Unlock your phone and try again." }
    }
}
