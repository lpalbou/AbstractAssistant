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
    /// saved sign-in; nil when it cannot be read in time, with the reason.
    public static func fetchEvent(seq: Int, signIn: SharedSignIn, session: URLSession, timeout: TimeInterval = 8) async -> (event: [String: Any]?, failure: String?) {
        var url = signIn.gateway.appending(path: "api/gateway/me/events")
        url.append(queryItems: [URLQueryItem(name: "after", value: String(seq - 1)), URLQueryItem(name: "limit", value: "1")])
        var request = URLRequest(url: url)
        request.timeoutInterval = timeout
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        signIn.authorize(&request, write: false)
        let data: Data, response: URLResponse
        do { (data, response) = try await session.data(for: request) }
        catch { return (nil, "\(signIn.gateway.host() ?? "gateway"): \(error.localizedDescription)") }
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard status == 200 else { return (nil, "\(signIn.gateway.host() ?? "gateway") answered \(status)") }
        guard let page = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
              let events = page["events"] as? [[String: Any]] else { return (nil, "the events page could not be read") }
        guard let event = events.first(where: { ($0["sequence"] as? NSNumber)?.intValue == seq }) else {
            return (nil, "event \(seq) is not in the page (\(events.count) events)")
        }
        return (event, nil)
    }

    /// The whole service-extension step: nil keeps the generic localized text. Every way it gives
    /// up is told to `trace` (the app group's trace, read by the apps' readouts), so a push that
    /// kept its generic words can be explained afterwards.
    public static func content(for payload: PushPayload, platform: PushPlatform, signIn: SharedSignIn?,
                               session: URLSession, text: @Sendable (String) -> String,
                               name: @Sendable (String) -> String?,
                               trace: @Sendable (String) -> Void = { PushTrace.note($0) }) async -> PushRendering? {
        let what = "\(payload.kind ?? "?") s=\(payload.seq)"
        guard let signIn, signIn.hasCredential else { trace("\(what): no sign-in to read it with"); return earlier(kind: payload.kind, text: text) }
        guard signIn.reg == payload.reg else { trace("\(what): for an earlier sign-in"); return earlier(kind: payload.kind, text: text) }
        let fetched = await fetchEvent(seq: payload.seq, signIn: signIn, session: session)
        guard let event = fetched.event else { trace("\(what): not read: \(fetched.failure ?? "?")"); return nil }
        guard let rendering = render(event: event, platform: platform, text: text, name: name) else {
            trace("\(what): read, not rendered (kind \(event["kind"] ?? "?"))"); return nil
        }
        trace("\(what): shown as \"\(rendering.title)\"")
        return rendering
    }
}

/// What the notification service extensions did with each push, the last 12 lines in the app
/// group's defaults, for the apps' readouts (the watch's `--dump-notify`): the one place to look
/// when a push kept its generic words.
public enum PushTrace {
    public static let key = "push.extension.trace"
    public static func note(_ line: String) {
        let d = UserDefaults(suiteName: SharedSignInStore.appGroup) ?? .standard
        var lines = d.stringArray(forKey: key) ?? []
        lines.append("\(ISO8601DateFormatter().string(from: Date())) \(line)")
        d.set(Array(lines.suffix(12)), forKey: key)
    }
    public static var lines: [String] {
        (UserDefaults(suiteName: SharedSignInStore.appGroup) ?? .standard).stringArray(forKey: key) ?? []
    }
}
