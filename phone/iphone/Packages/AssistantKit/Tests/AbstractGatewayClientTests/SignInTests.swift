import Foundation
import Testing
@testable import AbstractGatewayClient

@Test func credentialsSetTheRightHeaders() {
    var a = URLRequest(url: URL(string: "https://g/x")!)
    GatewayCredential.token("agw_1").apply(to: &a, write: true)
    #expect(a.value(forHTTPHeaderField: "Authorization") == "Bearer agw_1")
    var r = URLRequest(url: URL(string: "https://g/x")!)
    GatewayCredential.session(id: "s1", csrf: "c1").apply(to: &r, write: false)
    #expect(r.value(forHTTPHeaderField: "X-AbstractGateway-Session") == "s1" && r.value(forHTTPHeaderField: "X-AbstractGateway-CSRF") == nil)
    var w = URLRequest(url: URL(string: "https://g/x")!)
    GatewayCredential.session(id: "s1", csrf: "c1").apply(to: &w, write: true)
    #expect(w.value(forHTTPHeaderField: "X-AbstractGateway-CSRF") == "c1" && w.value(forHTTPHeaderField: "Authorization") == nil)
}

@Test func codeAnswersDecode() throws {
    let sent = try JSONDecoder().decode(GatewaySignIn.CodeAnswer.self, from: Data(#"{"ok":true,"sent":true,"to":"l•••@•••","expires_in_s":600,"message":"A sign-in code is on its way"}"#.utf8))
    #expect(sent.sent && sent.to == "l•••@•••")
    let limited = try JSONDecoder().decode(GatewaySignIn.CodeAnswer.self, from: Data(#"{"ok":true,"sent":false,"reason_code":"too_many_requests","retry_after_s":600,"message":"Too many"}"#.utf8))
    #expect(!limited.sent && limited.reasonCode == "too_many_requests" && limited.retryAfterS == 600)
    #expect(GatewaySignIn.detail(Data(#"{"detail":{"reason_code":"recovery_code_refused","message":"That code is not valid."}}"#.utf8)) == "That code is not valid.")
    #expect(GatewaySignIn.isEmail("me@x.org") && !GatewaySignIn.isEmail("laurent"))
}

/// Answers every request with the canned redeem response of a real gateway (cookies + principal).
final class RedeemStub: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var lastBody: [String: Any] = [:]
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        if let stream = request.httpBodyStream {
            stream.open(); var data = Data(); var buf = [UInt8](repeating: 0, count: 4096)
            while stream.hasBytesAvailable { let n = stream.read(&buf, maxLength: 4096); if n <= 0 { break }; data.append(buf, count: n) }
            Self.lastBody = (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
        }
        let resp = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: "HTTP/1.1", headerFields: [
            "Content-Type": "application/json",
            "Set-Cookie": "abstractgateway_session=sess-123; HttpOnly; Path=/; SameSite=lax; Secure, abstractgateway_csrf=csrf-456; Path=/; SameSite=lax; Secure",
        ])!
        client?.urlProtocol(self, didReceive: resp, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(#"{"ok":true,"principal":{"user_id":"alice","roles":["user"]}}"#.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@Test func redeemKeepsTheSessionFromTheCookies() async throws {
    let cfg = URLSessionConfiguration.ephemeral
    cfg.protocolClasses = [RedeemStub.self]
    let (cred, me) = try await GatewaySignIn.redeem(gateway: URL(string: "https://gateway.example")!, identifier: "alice@example.org",
                                                    code: "1234 5678", session: URLSession(configuration: cfg))
    #expect(cred == .session(id: "sess-123", csrf: "csrf-456"))
    #expect(me.userId == "alice")
    #expect(RedeemStub.lastBody["user_id"] as? String == "alice@example.org" && RedeemStub.lastBody["remember"] as? Bool == true)
}
