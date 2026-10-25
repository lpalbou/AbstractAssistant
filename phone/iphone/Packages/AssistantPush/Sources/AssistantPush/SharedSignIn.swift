import Foundation

/// The sign-in of an AbstractAssistant app: the gateway, the account and its credential (an account
/// token, or a 30-day session with its CSRF value), plus `reg`, this sign-in's push registration
/// handle (16 bytes as hex, new at every sign-in: a push carrying another one is from an earlier
/// sign-in). Kept sealed in the app group (`SharedSignInStore`) so the app's notification service
/// extension reads the same sign-in; never in UserDefaults, never in the OS keychain.
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

/// The sealed sign-in in the app group `group.ai.abstractframework.assistant` (shared by the app,
/// its notification service extension and, on the watch, the complication): `Library/Sealed/`
/// holds `sealing.key` and `signin.sealed`. A build without the app group (an unsigned simulator
/// build) keeps it in the app's own Application Support.
public enum SharedSignInStore {
    public static let appGroup = "group.ai.abstractframework.assistant"

    public static func directory() -> URL {
        if let group = FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: appGroup) {
            return group.appending(path: "Library/Sealed", directoryHint: .isDirectory)
        }
        let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? FileManager.default.temporaryDirectory
        return support.appending(path: "Sealed", directoryHint: .isDirectory)
    }

    private static func file(_ dir: URL) -> SealedFile { SealedFile(directory: dir, name: "signin") }

    public static func load(from dir: URL = directory()) -> SharedSignIn? {
        guard let data = try? file(dir).read() else { return nil }
        return try? JSONDecoder().decode(SharedSignIn.self, from: data)
    }

    public static func save(_ signIn: SharedSignIn, to dir: URL = directory()) throws {
        try file(dir).write(JSONEncoder().encode(signIn))
    }

    public static func clear(at dir: URL = directory()) {
        file(dir).remove()
    }
}
