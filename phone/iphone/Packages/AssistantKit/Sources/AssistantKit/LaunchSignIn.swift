import Foundation

#if DEBUG
/// Debug builds only (compiled out of Release): a sign-in provisioned from the Mac at launch, the
/// iPhone's counterpart of the watch's `--gateway URL --token TOKEN`.
/// `xcrun devicectl device process launch … ai.abstractframework.assistant --gateway URL --token TOKEN [--user ID]`
/// signs in exactly as the account-token path does (verified with GET /api/gateway/me, sealed,
/// registered for push); `--forget-gateway` clears the saved sign-in.
public enum LaunchSignIn: Equatable, Sendable {
    case signIn(gateway: URL, token: String, user: String?)
    case forget

    public struct Invalid: Error, LocalizedError, Equatable {
        public let reason: String
        public var errorDescription: String? { "Launch sign-in refused: \(reason)" }
    }

    /// `nil` when the launch names no sign-in (the saved one, if any, stands).
    public static func parse(_ args: [String]) throws -> LaunchSignIn? {
        func value(_ flag: String) throws -> String? {
            guard let i = args.firstIndex(of: flag) else { return nil }
            guard i + 1 < args.count, !args[i + 1].hasPrefix("--") else { throw Invalid(reason: "\(flag) needs a value") }
            let v = args[i + 1].trimmingCharacters(in: .whitespacesAndNewlines)
            guard !v.isEmpty else { throw Invalid(reason: "\(flag) needs a value") }
            return v
        }
        let gateway = try value("--gateway"), token = try value("--token"), user = try value("--user")
        if args.contains("--forget-gateway") {
            guard gateway == nil, token == nil, user == nil else { throw Invalid(reason: "--forget-gateway takes no --gateway, --token or --user") }
            return .forget
        }
        switch (gateway, token) {
        case (nil, nil):
            guard user == nil else { throw Invalid(reason: "--user needs --gateway and --token") }
            return nil
        case (let g?, let t?):
            do { return .signIn(gateway: try SavedConnection.parseURL(g), token: t, user: user) }
            catch { throw Invalid(reason: "--gateway \(g) is not a gateway address") }
        case (nil, _?): throw Invalid(reason: "--token needs --gateway")
        case (_?, nil): throw Invalid(reason: "--gateway needs --token")
        }
    }
}
#endif
