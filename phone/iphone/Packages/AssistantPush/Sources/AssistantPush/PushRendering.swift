import CryptoKit
import Foundation

/// The notification identifier of an attention item, the same on every path: the gateway's APNs
/// collapse id, `sha256("attention:" + record_key)` cut to 32 hex characters. A pushed alert gets it
/// from APNs; the app's own catch-up posts under it too and skips an id already delivered, so one
/// item never alerts twice.
public enum AttentionID {
    public static func collapse(_ recordKey: String) -> String {
        SHA256.hash(data: Data(("attention:" + recordKey).utf8)).map { String(format: "%02x", $0) }.joined().prefix(32).lowercased()
    }
}

/// The relay's push (`{aps: {alert: {title-loc-key, loc-key}, …, thread-id: <kind>}, s: <seq>, r: <reg>}`):
/// which event of the person's stream it is about and which sign-in it was meant for.
public struct PushPayload: Equatable, Sendable {
    public var seq: Int
    public var reg: String
    /// `approval`, `question`, `notify`, `result` or `failure` (the APNs thread id).
    public var kind: String?

    public init(seq: Int, reg: String, kind: String?) { self.seq = seq; self.reg = reg; self.kind = kind }

    public init?(userInfo: [AnyHashable: Any]) {
        let s: Int?
        switch userInfo["s"] {
        case let n as Int: s = n
        case let n as NSNumber: s = n.intValue
        case let t as String: s = Int(t)
        default: s = nil
        }
        guard let s, s > 0, let r = userInfo["r"] as? String, !r.isEmpty else { return nil }
        let aps = userInfo["aps"] as? [String: Any]
        self.init(seq: s, reg: r, kind: aps?["thread-id"] as? String)
    }
}

public enum PushPlatform: Sendable { case phone, watch }

/// What a notification says once the extension read its event.
public struct PushRendering: Equatable, Sendable {
    public var title: String
    public var body: String
    public var timeSensitive: Bool
    /// What a tap opens: `needs` (the run: the list of what waits), `automation` (its id), `notify`
    /// (the published item's record key); on the iPhone also `tab` (1 Inbox, 2 Automations).
    public var info: [String: String]
    public var tab: Int?

    public init(title: String, body: String, timeSensitive: Bool, info: [String: String] = [:], tab: Int? = nil) {
        self.title = title; self.body = body; self.timeSensitive = timeSensitive; self.info = info; self.tab = tab
    }

    public var userInfo: [AnyHashable: Any] {
        var u: [AnyHashable: Any] = [:]
        for (k, v) in info { u[k] = v }
        if let tab { u["tab"] = tab }
        return u
    }
}

/// Turns the pushed event into the notification the app's catch-up would have posted.
/// `text(key)` reads the app's own strings (`push.<kind>.title`, `push.<kind>.body`,
/// `push.result.named`, `push.failure.named`, `push.earlier`); `name(id)` an automation's name.
public enum PushRenderer {
    /// A push for another sign-in than the current one: passive, the generic title, "From an
    /// earlier sign-in" (an extension cannot drop an alert).
    public static func earlier(kind: String?, text: (String) -> String) -> PushRendering {
        PushRendering(title: text("push.\(kind ?? "notify").title"), body: text("push.earlier"), timeSensitive: false)
    }

    /// `event` is one event of `GET /me/events` (`{type, sequence, data: {...}}`); nil when it is not
    /// one the gateway pushes (the generic text then stays).
    public static func render(event: [String: Any], platform: PushPlatform, text: (String) -> String,
                              name: (String) -> String?) -> PushRendering? {
        guard event["type"] as? String == "attention.raised", let data = event["data"] as? [String: Any] else { return nil }
        let kind = data["kind"] as? String ?? ""
        let record = data["record_key"] as? String ?? ""
        if let waitKey = data["wait_key"] as? String, !waitKey.isEmpty, let run = data["run_id"] as? String {
            let k = kind == "question" ? "question" : "approval"
            return PushRendering(title: text("push.\(k).title"), body: text("push.\(k).body"), timeSensitive: true,
                                 info: ["needs": run], tab: platform == .phone ? 1 : nil)
        }
        if kind == "notify", record.hasPrefix("publish:") {
            let title = (data["title"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? text("push.notify.title")
            var body = (data["body"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? text("push.notify.body")
            if body.count > 300 { body = String(body.prefix(300)) + "…" }
            return PushRendering(title: title, body: body, timeSensitive: false, info: ["notify": record])
        }
        if let automation = data["automation_id"] as? String, !automation.isEmpty, kind == "notify" || kind == "failure" {
            let k = kind == "failure" ? "failure" : "result"
            let title = name(automation).map { String(format: text("push.\(k).named"), $0) } ?? text("push.\(k).title")
            return PushRendering(title: title, body: text("push.\(k).body"), timeSensitive: false,
                                 info: ["automation": automation], tab: platform == .phone ? 2 : nil)
        }
        return nil
    }

    /// The event the push is about: `GET /api/gateway/me/events?after=<s-1>&limit=1`, read with the
    /// saved sign-in; nil when it cannot be read in time.
    public static func fetchEvent(seq: Int, signIn: SharedSignIn, session: URLSession, timeout: TimeInterval = 8) async -> [String: Any]? {
        var url = signIn.gateway.appending(path: "api/gateway/me/events")
        url.append(queryItems: [URLQueryItem(name: "after", value: String(seq - 1)), URLQueryItem(name: "limit", value: "1")])
        var request = URLRequest(url: url)
        request.timeoutInterval = timeout
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        signIn.authorize(&request, write: false)
        guard let (data, response) = try? await session.data(for: request),
              (response as? HTTPURLResponse)?.statusCode == 200,
              let page = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
              let events = page["events"] as? [[String: Any]] else { return nil }
        return events.first { ($0["sequence"] as? NSNumber)?.intValue == seq }
    }

    /// The whole service-extension step: nil keeps the generic localized text.
    public static func content(for payload: PushPayload, platform: PushPlatform, signIn: SharedSignIn?,
                               session: URLSession, text: @Sendable (String) -> String,
                               name: @Sendable (String) -> String?) async -> PushRendering? {
        guard let signIn, signIn.hasCredential, signIn.reg == payload.reg else {
            return earlier(kind: payload.kind, text: text)
        }
        guard let event = await fetchEvent(seq: payload.seq, signIn: signIn, session: session) else { return nil }
        return render(event: event, platform: platform, text: text, name: name)
    }
}
