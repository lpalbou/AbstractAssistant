import Foundation

/// The iPhone's sign-in handed to the watch over WatchConnectivity (application context, with
/// `transferUserInfo` as the fallback): `{"signin": <JSON>}`. The watch adopts it when it is newer
/// than its own sign-in and names another account or credential (the latest sign-in wins, on either
/// device); a watch without a paired iPhone signs in on its own.
public struct SignInHandoff: Codable, Equatable, Sendable {
    public static let key = "signin"
    public var gateway: URL
    public var user: String?
    public var tenant: String?
    public var token: String?
    public var session: String?
    public var csrf: String?
    public var signedInAt: Date

    public init(_ s: SharedSignIn) {
        gateway = s.gateway; user = s.user; tenant = s.tenant
        token = s.token; session = s.session; csrf = s.csrf; signedInAt = s.signedInAt
    }

    /// The message for `updateApplicationContext` / `transferUserInfo`.
    public var message: [String: Any] {
        guard let data = try? JSONEncoder().encode(self) else { return [:] }
        return [Self.key: data]
    }

    public init?(message: [String: Any]) {
        guard let data = message[Self.key] as? Data,
              let h = try? JSONDecoder().decode(SignInHandoff.self, from: data) else { return nil }
        self = h
    }

    /// The sign-in the watch keeps from it (a new push handle: a sign-in on the watch).
    public var signIn: SharedSignIn {
        SharedSignIn(gateway: gateway, user: user, tenant: tenant, token: token, session: session, csrf: csrf,
                     signedInAt: signedInAt)
    }

    /// Whether the watch should take it over its current sign-in.
    public func shouldAdopt(over current: SharedSignIn?) -> Bool {
        let incoming = signIn
        guard incoming.hasCredential else { return false }
        guard let current else { return true }
        if incoming.sameCredential(as: current) { return false }
        return signedInAt > current.signedInAt
    }
}
