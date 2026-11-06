import Foundation
import AssistantKit
import AbstractGatewayClient
import AssistantPush

/// The iPhone's sign-in, a Keychain item shared through the app group (`SharedSignInStore`) so the
/// notification service extension reads the same one.
/// Saving is a sign-in: it takes a new push registration handle (`reg`).
enum ConnectionVault {
    static func read() throws -> SavedConnection? {
        guard let s = try SharedSignInStore.loadVerified(), s.hasCredential else { return nil }
        return connection(s)
    }
    static func connection(_ s: SharedSignIn) -> SavedConnection {
        let credential: GatewayCredential = s.token.map { .token($0) } ?? .session(id: s.session ?? "", csrf: s.csrf ?? "")
        return SavedConnection(gateway: s.gateway, user: s.user ?? "", tenant: s.tenant ?? "default", credential: credential)
    }
    /// The stored record itself (its push handle and sign-in time).
    static func current() -> SharedSignIn? { SharedSignInStore.load() }
    static func currentVerified() throws -> SharedSignIn? { try SharedSignInStore.loadVerified() }
    static func save(_ connection: SavedConnection) throws {
        do { try SharedSignInStore.save(signIn(connection)) } catch { throw VaultError() }
    }
    static func remove() throws { try SharedSignInStore.clearVerified() }

    // Dormant credentials are deliberately separate from the active sign-in read by push and launch.
    private static let keptName = "phone-kept-signins"
    static func kept(_ store: SecretStore = SharedSignInStore.store) throws -> [SharedSignIn] {
        guard let data = try store.read(keptName) else { return [] }
        return try JSONDecoder().decode([SharedSignIn].self, from: data)
    }
    private static func matches(_ a: SharedSignIn, _ b: SharedSignIn) -> Bool {
        guard a.gateway == b.gateway, (a.tenant ?? "default") == (b.tenant ?? "default") else { return false }
        return a.sameCredential(as: b) || (!(a.user ?? "").isEmpty && a.user?.lowercased() == b.user?.lowercased())
    }
    static func forgetKept(_ signIn: SharedSignIn, _ store: SecretStore = SharedSignInStore.store) throws {
        let remaining = try kept(store).filter { !matches($0, signIn) }
        try store.write(keptName, JSONEncoder().encode(remaining))
        guard try kept(store) == remaining else { throw VaultError() }
    }
    static func signOut(_ signIn: SharedSignIn, keep: Bool, _ store: SecretStore = SharedSignInStore.store) throws {
        if keep {
            let entries = [signIn] + (try kept(store)).filter { !matches($0, signIn) }
            try store.write(keptName, JSONEncoder().encode(entries))
            guard try kept(store) == entries else { throw VaultError() }
        } else { try forgetKept(signIn, store) }
        // A failed keep never clears the active credential. No network is involved.
        try SharedSignInStore.clearVerified(store)
    }
    static func signIn(_ c: SavedConnection) -> SharedSignIn {
        SharedSignIn(gateway: c.gateway, user: c.user, tenant: c.tenant, token: c.token, session: c.session, csrf: c.csrf)
    }
    struct VaultError: LocalizedError {
        var errorDescription: String? { "The iPhone couldn’t save your sign-in. Unlock your phone and try again." }
    }
}
