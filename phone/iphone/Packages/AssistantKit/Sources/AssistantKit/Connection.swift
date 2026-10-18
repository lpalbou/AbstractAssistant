import Foundation
import CryptoKit
import AbstractGatewayClient

public enum ConnectionError: Error, LocalizedError, Equatable {
    case invalidURL
    public var errorDescription: String? { "Use an HTTPS gateway address, or HTTP on your local network. Leave out passwords, queries and fragments." }
}

public struct SavedConnection: Codable, Sendable, Equatable {
    public var gateway: URL
    public var user: String
    public var tenant: String
    public var token: String?
    public var session: String?
    public var csrf: String?

    public init(gateway: URL, user: String, tenant: String = "default", credential: GatewayCredential) {
        self.gateway = gateway; self.user = user; self.tenant = tenant
        switch credential {
        case .token(let value): token = value
        case .session(let id, let value): session = id; csrf = value
        }
    }
    public var credential: GatewayCredential {
        if let token { return .token(token) }
        return .session(id: session ?? "", csrf: csrf ?? "")
    }
    /// An account-scoped local preference key; never contains the credential.
    public var scope: String {
        SHA256.hash(data: Data("\(gateway.absoluteString)|\(tenant)|\(user)".utf8)).map { String(format: "%02x", $0) }.joined()
    }
    public static func parseURL(_ input: String) throws -> URL {
        let value = input.trimmingCharacters(in: .whitespacesAndNewlines)
        let full = value.contains("://") ? value : "https://" + value
        guard var parts = URLComponents(string: full), let host = parts.host, !host.isEmpty,
              parts.user == nil, parts.password == nil, parts.query == nil, parts.fragment == nil,
              ["https", "http"].contains(parts.scheme?.lowercased() ?? ""),
              parts.path.isEmpty || parts.path == "/" || parts.path == "/console" else { throw ConnectionError.invalidURL }
        if parts.scheme?.lowercased() == "http" {
            let octets = host.split(separator: ".", omittingEmptySubsequences: false).compactMap { Int($0) }
            let isIPv4 = host.split(separator: ".", omittingEmptySubsequences: false).count == 4 && octets.count == 4 && octets.allSatisfy { (0...255).contains($0) }
            let local = host == "localhost" || host == "127.0.0.1" || host == "::1" || host == "[::1]" || host.hasSuffix(".local")
                || (isIPv4 && (octets[0] == 10 || (octets[0] == 192 && octets[1] == 168)
                    || (octets[0] == 172 && (16...31).contains(octets[1]))))
            guard local else { throw ConnectionError.invalidURL }
        }
        parts.path = ""; parts.scheme = parts.scheme?.lowercased()
        guard let url = parts.url else { throw ConnectionError.invalidURL }
        return url
    }
}

/// Credentials are explicit headers. Cookies are not shared with Safari or another account,
/// and redirects cannot forward a gateway session/token to another host.
public enum PhoneTransport {
    public static func makeSession() -> URLSession {
        let config = URLSessionConfiguration.ephemeral
        config.httpShouldSetCookies = false; config.httpCookieStorage = nil
        config.requestCachePolicy = .reloadIgnoringLocalCacheData
        return URLSession(configuration: config, delegate: NoRedirects(), delegateQueue: nil)
    }
    private final class NoRedirects: NSObject, URLSessionTaskDelegate, Sendable {
        func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                        newRequest request: URLRequest, completionHandler: @escaping @Sendable (URLRequest?) -> Void) { completionHandler(nil) }
    }
}

public struct ConversationMessage: Identifiable, Equatable, Sendable {
    public enum Role: String, Sendable { case user, assistant, notice }
    public var id: String
    public var role: Role
    public var text: String
    public var runID: String?
    public var stats: MessageStats?
    public init(id: String = UUID().uuidString, role: Role, text: String, runID: String? = nil, stats: MessageStats? = nil) {
        self.id = id; self.role = role; self.text = text; self.runID = runID; self.stats = stats
    }
}
