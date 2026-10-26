import Foundation

/// The sign-in of an AbstractAssistant app: the gateway, the account and its credential (an account
/// token, or a 30-day session with its CSRF value), plus `reg`, this sign-in's push registration
/// handle (16 bytes as hex, new at every sign-in: a push carrying another one is from an earlier
/// sign-in). A Keychain item shared through the app group (`SharedSignInStore`) so the app's
/// notification service extension reads the same sign-in; never in UserDefaults.
public struct SharedSignIn: Codable, Equatable, Sendable {
    public var gateway: URL
    public var user: String?
    public var tenant: String?
    public var token: String?
    public var session: String?
    public var csrf: String?
    public var reg: String
    public var signedInAt: Date

    public init(gateway: URL, user: String?, tenant: String? = nil, token: String? = nil, session: String? = nil,
                csrf: String? = nil, reg: String = SharedSignIn.newReg(), signedInAt: Date = Date()) {
        self.gateway = gateway; self.user = user; self.tenant = tenant
        self.token = token; self.session = session; self.csrf = csrf
        self.reg = reg; self.signedInAt = signedInAt
    }

    /// A new registration handle: 32 lowercase hex characters (the gateway takes 16 to 32).
    public static func newReg() -> String {
        var g = SystemRandomNumberGenerator()
        return (0..<16).map { _ in String(format: "%02x", UInt8.random(in: 0...255, using: &g)) }.joined()
    }

    public var hasCredential: Bool {
        if let token, !token.isEmpty { return true }
        if let session, !session.isEmpty, let csrf, !csrf.isEmpty { return true }
        return false
    }

    /// The same account with the same credential (the handle and the time aside).
    public func sameCredential(as other: SharedSignIn) -> Bool {
        gateway.absoluteString.lowercased() == other.gateway.absoluteString.lowercased()
            && (user ?? "").lowercased() == (other.user ?? "").lowercased()
            && token == other.token && session == other.session && csrf == other.csrf
    }

    /// The gateway's headers: `Authorization: Bearer` for a token; for a session its id, and the
    /// CSRF value on every write.
    public func authorize(_ request: inout URLRequest, write: Bool) {
        if let token, !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        } else if let session {
            request.setValue(session, forHTTPHeaderField: "X-AbstractGateway-Session")
            if write, let csrf { request.setValue(csrf, forHTTPHeaderField: "X-AbstractGateway-CSRF") }
        }
    }
}

/// The sign-in: a Keychain item (`KeychainSecretStore`) shared by the app, its notification service
/// extension and, on the watch, the complication, through the app group
/// `group.ai.abstractframework.assistant`, which is also the keychain access group. The same store
/// holds the watch's kept sign-ins (`read(named:)`, `write(named:)`, `remove(named:)`).
///
/// Earlier builds kept it in files in the app group (`Library/Sealed/`: `signin.json` for a few
/// days, a ChaChaPoly pair before that, see `ProtectedFile`): the first read that finds nothing
/// in the Keychain moves what those files hold and deletes them, so nobody signs in again.
public enum SharedSignInStore {
    public static let appGroup = "group.ai.abstractframework.assistant"
    static let signInName = "signin"

    /// The apps' store, decided once: the Keychain through the app group's access group; without
    /// the group when the build has the Keychain but not the group; a protected file in the app's
    /// own storage when the build has no Keychain at all (an unsigned simulator build).
    public static let store: any SecretStore = {
        let grouped = KeychainSecretStore(accessGroup: appGroup)
        if grouped.isUsable { return grouped }
        let own = KeychainSecretStore(accessGroup: nil)
        if own.isUsable { return own }
        return FileSecretStore(directory: directory())
    }()

    /// Where the earlier builds' files are (and the fallback of a build without the app group).
    public static func directory() -> URL {
        if let group = FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: appGroup) {
            return group.appending(path: "Library/Sealed", directoryHint: .isDirectory)
        }
        let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? FileManager.default.temporaryDirectory
        return support.appending(path: "Sealed", directoryHint: .isDirectory)
    }

    public static func load(from store: SecretStore = store, legacy dir: URL = directory()) -> SharedSignIn? {
        guard let data = try? read(named: signInName, from: store, legacy: dir) else { return nil }
        return try? JSONDecoder().decode(SharedSignIn.self, from: data)
    }

    public static func save(_ signIn: SharedSignIn, to store: SecretStore = store) throws {
        try store.write(signInName, JSONEncoder().encode(signIn))
    }

    public static func clear(_ store: SecretStore = store, legacy dir: URL = directory()) {
        try? store.remove(signInName)
        ProtectedFile(directory: dir, name: signInName).remove()
    }

    /// A named secret beside the sign-in (the watch's kept sign-ins): what the store holds, else
    /// what an earlier build's file holds, moved into the store and deleted.
    public static func read(named name: String, from store: SecretStore = store, legacy dir: URL = directory()) throws -> Data? {
        if let data = try store.read(name) { return data }
        let file = ProtectedFile(directory: dir, name: name)
        guard let moved = try file.read() else { return nil }
        try store.write(name, moved)
        file.remove()
        return moved
    }

    public static func write(named name: String, _ data: Data, to store: SecretStore = store) throws {
        try store.write(name, data)
    }

    public static func remove(named name: String, from store: SecretStore = store, legacy dir: URL = directory()) {
        try? store.remove(name)
        ProtectedFile(directory: dir, name: name).remove()
    }
}
