import Foundation

/// How the watch proves who it is to the gateway.
public enum GatewayCredential: Sendable, Equatable {
    /// An account token (`Authorization: Bearer`), entered once with the user id.
    case token(String)
    /// A gateway session opened by an emailed sign-in code: the session id travels in
    /// `X-AbstractGateway-Session` and every write carries `X-AbstractGateway-CSRF`.
    case session(id: String, csrf: String)

    public func apply(to req: inout URLRequest, write: Bool) {
        switch self {
        case .token(let t):
            req.setValue("Bearer \(t)", forHTTPHeaderField: "Authorization")
        case .session(let id, let csrf):
            req.setValue(id, forHTTPHeaderField: "X-AbstractGateway-Session")
            if write { req.setValue(csrf, forHTTPHeaderField: "X-AbstractGateway-CSRF") }
        }
    }
}

/// The sign-in page's calls; none of them needs a credential.
public enum GatewaySignIn {
    /// The gateway's answer to "email me a code": sent to a masked address, or why not.
    public struct CodeAnswer: Decodable, Sendable, Equatable {
        public var sent: Bool
        public var to: String?
        public var message: String?
        public var reasonCode: String?
        public var retryAfterS: Int?
        enum CodingKeys: String, CodingKey { case sent, to, message, reasonCode = "reason_code", retryAfterS = "retry_after_s" }
        public init(sent: Bool, to: String? = nil, message: String? = nil, reasonCode: String? = nil, retryAfterS: Int? = nil) {
            self.sent = sent; self.to = to; self.message = message; self.reasonCode = reasonCode; self.retryAfterS = retryAfterS
        }
    }

    public enum Failure: Error, LocalizedError, Equatable {
        case refused(String)
        case unreachable(String)
        public var errorDescription: String? {
            switch self { case .refused(let m), .unreachable(let m): m }
        }
    }

    /// An email address names an account by its registered email; anything else is an account id.
    public static func isEmail(_ identifier: String) -> Bool { identifier.contains("@") }

    /// `POST /api/gateway/session/recovery/request` `{user_id: <id or registered email>}`.
    public static func requestCode(gateway: URL, identifier: String, session: URLSession = .shared) async throws -> CodeAnswer {
        let (data, status) = try await post(gateway, "api/gateway/session/recovery/request", ["user_id": identifier], session: session)
        if status == 404 { return CodeAnswer(sent: false, message: "Email sign-in is off. Use your user name.", reasonCode: "recovery_off") }
        guard (200..<300).contains(status) else { throw Failure.refused("Sign-in failed. Try again.") }
        return try JSONDecoder().decode(CodeAnswer.self, from: data)
    }

    /// `POST /api/gateway/session/recovery/redeem` with `remember: true` (a 30-day session):
    /// the session and CSRF values come back as cookies and are kept as a credential.
    public static func redeem(gateway: URL, identifier: String, code: String, session: URLSession? = nil) async throws -> (GatewayCredential, Principal) {
        let s = session ?? URLSession(configuration: .ephemeral)
        let url = gateway.appending(path: "api/gateway/session/recovery/redeem")
        var req = URLRequest(url: url)
        req.httpMethod = "POST"; req.timeoutInterval = 30
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONSerialization.data(withJSONObject: ["user_id": identifier, "code": code, "remember": true] as [String: Any])
        let data: Data, resp: URLResponse
        do { (data, resp) = try await s.data(for: req) } catch { throw Failure.unreachable("Can't reach the server.") }
        guard let http = resp as? HTTPURLResponse else { throw Failure.unreachable("Can't reach the server.") }
        guard (200..<300).contains(http.statusCode) else {
            throw Failure.refused("Wrong or expired code.")
        }
        let headers = http.allHeaderFields.reduce(into: [String: String]()) { out, kv in
            if let k = kv.key as? String, let v = kv.value as? String { out[k] = v }
        }
        let cookies = HTTPCookie.cookies(withResponseHeaderFields: headers, for: url)
        guard let sid = cookies.first(where: { $0.name == "abstractgateway_session" })?.value,
              let csrf = cookies.first(where: { $0.name == "abstractgateway_csrf" })?.value else {
            throw Failure.refused("Sign-in failed. Try again.")
        }
        let principal = try JSONDecoder().decode(Principal.self, from: data)
        return (.session(id: sid, csrf: csrf), principal)
    }

    /// Checks a token: `GET /api/gateway/me`. The account must be the one that was typed.
    public static func verify(gateway: URL, user: String, token: String, session: URLSession = .shared) async throws -> Principal {
        var req = URLRequest(url: gateway.appending(path: "api/gateway/me"))
        req.timeoutInterval = 20
        GatewayCredential.token(token).apply(to: &req, write: false)
        let data: Data, resp: URLResponse
        do { (data, resp) = try await session.data(for: req) } catch { throw Failure.unreachable("Can't reach the server.") }
        let status = (resp as? HTTPURLResponse)?.statusCode ?? 0
        if status == 401 { throw Failure.refused("Wrong token.") }
        guard (200..<300).contains(status) else { throw Failure.refused("Sign-in failed. Try again.") }
        let me = try JSONDecoder().decode(Principal.self, from: data)
        if let id = me.userId, id.lowercased() != user.lowercased() {
            throw Failure.refused("This token is for \(id).")
        }
        return me
    }

    private static func post(_ gateway: URL, _ path: String, _ body: [String: String], session: URLSession) async throws -> (Data, Int) {
        var req = URLRequest(url: gateway.appending(path: path))
        req.httpMethod = "POST"; req.timeoutInterval = 30
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONEncoder().encode(body)
        do {
            let (data, resp) = try await session.data(for: req)
            return (data, (resp as? HTTPURLResponse)?.statusCode ?? 0)
        } catch { throw Failure.unreachable("Can't reach the server.") }
    }

    /// FastAPI's `detail`, a string or `{message}`.
    static func detail(_ data: Data) -> String? {
        guard let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
        if let d = obj["detail"] as? String { return d }
        if let d = obj["detail"] as? [String: Any], let m = d["message"] as? String { return m }
        return obj["message"] as? String
    }
}
