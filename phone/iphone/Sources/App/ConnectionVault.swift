import Foundation
import AssistantKit
import AbstractGatewayClient
import AssistantPush

/// The iPhone's sign-in, sealed in the app group (`SharedSignInStore`: a ChaChaPoly file under a
/// 0600 key file, never the OS keychain) so the notification service extension reads the same one.
/// Saving is a sign-in: it takes a new push registration handle (`reg`).
enum ConnectionVault {
    static func read() throws -> SavedConnection? {
        guard let s = SharedSignInStore.load(), s.hasCredential else { return nil }
        let credential: GatewayCredential = s.token.map { .token($0) } ?? .session(id: s.session ?? "", csrf: s.csrf ?? "")
        return SavedConnection(gateway: s.gateway, user: s.user ?? "", tenant: s.tenant ?? "default", credential: credential)
    }
    /// The sealed record itself (its push handle and sign-in time).
    static func current() -> SharedSignIn? { SharedSignInStore.load() }
    static func save(_ connection: SavedConnection) throws {
        do { try SharedSignInStore.save(signIn(connection)) } catch { throw VaultError() }
    }
    static func remove() throws { SharedSignInStore.clear() }
    static func signIn(_ c: SavedConnection) -> SharedSignIn {
        SharedSignIn(gateway: c.gateway, user: c.user, tenant: c.tenant, token: c.token, session: c.session, csrf: c.csrf)
    }
    struct VaultError: LocalizedError {
        var errorDescription: String? { "The iPhone couldn’t save your sign-in. Unlock your phone and try again." }
    }
}
