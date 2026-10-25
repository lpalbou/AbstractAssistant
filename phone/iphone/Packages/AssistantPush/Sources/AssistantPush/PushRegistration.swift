import Foundation

/// Which app registers: the gateway's `app` field.
public enum PushApp: String, Codable, Sendable { case watch, phone }

/// What this app and device tell the gateway about themselves (framework backlog 1049).
public struct PushDevice: Equatable, Sendable {
    /// The app's own opaque id for this device: the same id its notification reports carry.
    public var deviceID: String
    public var app: PushApp
    /// The APNs topic: the app's exact bundle id.
    public var topic: String
    /// `sandbox` (development signing) or `production`.
    public var env: String
    /// A name the person recognizes in the console's device list (at most 60 characters).
    public var name: String?

    public init(deviceID: String, app: PushApp, topic: String, env: String, name: String?) {
        self.deviceID = deviceID; self.app = app; self.topic = topic; self.env = env
        self.name = name.map { String($0.prefix(60)) }.flatMap { $0.isEmpty ? nil : $0 }
    }
}

/// The body of `PUT /api/gateway/me/push/devices/{device_id}`: exactly
/// `{token, topic, env, app, reg, name?}` (the gateway answers 422 to any other field).
public struct PushRegistrationBody: Encodable, Equatable, Sendable {
    public var token: String
    public var topic: String
    public var env: String
    public var app: String
    public var reg: String
    public var name: String?

    public init(token: String, device: PushDevice, reg: String) {
        self.token = token; topic = device.topic; env = device.env; app = device.app.rawValue
        self.reg = reg; name = device.name
    }
}

/// The last registration the gateway accepted, kept by the app (it holds no credential).
public struct PushRecord: Codable, Equatable, Sendable {
    public var token: String
    public var reg: String
    public var gateway: String
    public var user: String?
    public var deviceID: String
    public var topic: String
    public var env: String
    public var at: Date
    /// The gateway's `relay`: `on`, `off` (it sends no pushes yet) or `unreachable`. Never shown.
    public var relay: String?

    /// Whether `other` registers the same thing (the time and the relay's answer aside).
    func sameRegistration(as other: PushRecord) -> Bool {
        token == other.token && reg == other.reg && gateway == other.gateway && user == other.user
            && deviceID == other.deviceID && topic == other.topic && env == other.env
    }
}

public enum PushSchedule {
    /// A registration is refreshed at most once a day (it expires on the gateway after 7 days).
    public static let refreshInterval: TimeInterval = 86_400

    /// True when the gateway must be told: nothing registered yet, a new token, a new sign-in
    /// (another handle, gateway or account), or the last registration is a day old.
    public static func needsPut(last: PushRecord?, next: PushRecord, now: Date) -> Bool {
        guard let last, last.sameRegistration(as: next) else { return true }
        return now.timeIntervalSince(last.at) >= refreshInterval || now < last.at
    }
}

/// The APNs environment of this build: the `aps-environment` of its embedded provisioning profile
/// (`development` → `sandbox`); a build without a profile is an App Store / TestFlight one
/// (`production`); the simulator is `sandbox`.
public enum PushEnvironment {
    public static func current(bundle: Bundle = .main) -> String {
        #if targetEnvironment(simulator)
        return "sandbox"
        #else
        guard let url = bundle.url(forResource: "embedded", withExtension: "mobileprovision"),
              let data = try? Data(contentsOf: url) else { return "production" }
        return parse(provision: data) ?? "production"
        #endif
    }

    /// Reads `Entitlements.aps-environment` from a provisioning profile (a signed plist).
    public static func parse(provision: Data) -> String? {
        let text = String(decoding: provision, as: UTF8.self)
        guard let start = text.range(of: "<?xml"), let end = text.range(of: "</plist>", range: start.upperBound..<text.endIndex),
              let plist = try? PropertyListSerialization.propertyList(from: Data(text[start.lowerBound..<end.upperBound].utf8), format: nil) as? [String: Any],
              let entitlements = plist["Entitlements"] as? [String: Any],
              let aps = entitlements["aps-environment"] as? String else { return nil }
        return aps == "production" ? "production" : "sandbox"
    }
}

/// What a registration attempt did.
public enum PushOutcome: Equatable, Sendable {
    /// The gateway took it; `relay` is its answer (`off`: no pushes are sent yet, nothing to do).
    case registered(relay: String)
    /// Nothing to send: not signed in, no token yet, or registered less than a day ago.
    case skipped(String)
    /// Not taken (an HTTP status, or the network): tried again at the next token or launch.
    case failed(String)
}

/// Registers this app's APNs token with the person's gateway: at both sign-in paths (a new `reg`),
/// on every new token and at most daily; forgets it at sign-out. It works the same whether the
/// gateway's relay is on or off (`relay: off` is kept and nothing else changes), and there is no
/// setting: the system's notification permission is the only switch.
public actor PushRegistrar {
    private let defaults: UserDefaults
    private let session: URLSession
    private let now: @Sendable () -> Date
    static let tokenKey = "push.token", recordKey = "push.record"

    public init(defaults: UserDefaults = .standard, session: URLSession = PushRegistrar.makeSession(),
                now: @escaping @Sendable () -> Date = { Date() }) {
        self.defaults = defaults; self.session = session; self.now = now
    }

    /// Credentials are explicit headers: no cookies, no redirects carrying them elsewhere.
    public static func makeSession() -> URLSession {
        let c = URLSessionConfiguration.ephemeral
        c.httpShouldSetCookies = false; c.httpCookieStorage = nil
        c.timeoutIntervalForRequest = 20
        return URLSession(configuration: c, delegate: NoRedirects(), delegateQueue: nil)
    }

    public static func hex(_ token: Data) -> String { token.map { String(format: "%02x", $0) }.joined() }

    /// The token APNs gave this app (hex), as last received.
    public var token: String? { defaults.string(forKey: Self.tokenKey) }

    public var lastRecord: PushRecord? {
        defaults.data(forKey: Self.recordKey).flatMap { try? JSONDecoder().decode(PushRecord.self, from: $0) }
    }

    /// The system gave the app its token (each launch, and whenever it changes).
    @discardableResult
    public func tokenArrived(_ token: Data, device: PushDevice, signIn: SharedSignIn?) async -> PushOutcome {
        defaults.set(Self.hex(token), forKey: Self.tokenKey)
        return await refresh(device: device, signIn: signIn)
    }

    /// Registers when needed (see `PushSchedule.needsPut`).
    @discardableResult
    public func refresh(device: PushDevice, signIn: SharedSignIn?) async -> PushOutcome {
        guard let signIn, signIn.hasCredential else { return .skipped("signed out") }
        guard let token else { return .skipped("no token yet") }
        let next = PushRecord(token: token, reg: signIn.reg, gateway: signIn.gateway.absoluteString, user: signIn.user,
                              deviceID: device.deviceID, topic: device.topic, env: device.env, at: now(), relay: nil)
        guard PushSchedule.needsPut(last: lastRecord, next: next, now: now()) else { return .skipped("registered recently") }
        var request = URLRequest(url: Self.deviceURL(signIn.gateway, device.deviceID))
        request.httpMethod = "PUT"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        signIn.authorize(&request, write: true)
        do {
            request.httpBody = try JSONEncoder().encode(PushRegistrationBody(token: token, device: device, reg: signIn.reg))
            let (data, response) = try await session.data(for: request)
            let status = (response as? HTTPURLResponse)?.statusCode ?? 0
            guard (200..<300).contains(status) else { return .failed("HTTP \(status)") }
            let relay = ((try? JSONSerialization.jsonObject(with: data)) as? [String: Any])?["relay"] as? String ?? "on"
            var record = next; record.relay = relay
            if let encoded = try? JSONEncoder().encode(record) { defaults.set(encoded, forKey: Self.recordKey) }
            return .registered(relay: relay)
        } catch {
            return .failed(error.localizedDescription)
        }
    }

    /// Sign-out: `DELETE …/devices/{device_id}` with the credential that is being forgotten (best
    /// effort: a registration nobody refreshes expires after 7 days anyway).
    @discardableResult
    public func signedOut(_ signIn: SharedSignIn, deviceID: String) async -> Bool {
        defaults.removeObject(forKey: Self.recordKey)
        guard signIn.hasCredential else { return false }
        var request = URLRequest(url: Self.deviceURL(signIn.gateway, deviceID))
        request.httpMethod = "DELETE"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        signIn.authorize(&request, write: true)
        guard let (_, response) = try? await session.data(for: request) else { return false }
        return ((response as? HTTPURLResponse)?.statusCode).map { (200..<300).contains($0) } ?? false
    }

    static func deviceURL(_ gateway: URL, _ deviceID: String) -> URL {
        gateway.appending(path: "api/gateway/me/push/devices").appending(path: deviceID)
    }
}

private final class NoRedirects: NSObject, URLSessionTaskDelegate, Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping @Sendable (URLRequest?) -> Void) {
        completionHandler(nil)
    }
}
