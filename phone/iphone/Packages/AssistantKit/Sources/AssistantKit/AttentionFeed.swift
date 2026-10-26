import Foundation
import AbstractGatewayClient

/// The person's event stream on the iPhone (framework backlog 1047): one catch-up read at launch and
/// each time the app comes to the front (`GET /me/events?after=`), then the SSE tail
/// (`/me/events/stream`, resumed with `Last-Event-ID`) for as long as the app is in front; nothing
/// in the background. Folds raised minus seen (`AttentionState`): `newResults` (automation results not
/// seen) feeds the Automations badge; the Inbox badge is the store's wait list, which a raised or seen
/// wait makes the store read again (`onChange`), never the fold's own count; each NEW item after the
/// first catch-up is handed to `onNotice` (the app posts the local notification) unless another
/// client on this same device already showed it (the gateway's per-device rule — on a phone no
/// other client reports, so the phone notifies); once shown, `reportShown` records it on the stream
/// (`channel: "phone"`, this iPhone's device id). The state is kept per connection, so a relaunch
/// resumes where it stopped and never replays history as notifications.
@MainActor @Observable
public final class AttentionFeed {
    public private(set) var state = AttentionState()
    /// `following` while the tail is open; `unsupported` on a gateway without the stream (404).
    public private(set) var status: Status = .idle
    public var newResults: Int { state.newResults }

    public enum Status: Equatable, Sendable { case idle, catchingUp, following, unsupported }

    /// A new item the person should be told about (called on the main actor).
    @ObservationIgnored public var onNotice: (@MainActor (AttentionNotice) -> Void)?
    /// Something about automations or waits changed: the lists should be read again.
    @ObservationIgnored public var onChange: (@MainActor () -> Void)?
    /// Delay before reopening a closed tail (seconds; tests shorten it).
    @ObservationIgnored public var reconnectDelay: Double = 1

    @ObservationIgnored private var client: (any GatewayClient)?
    @ObservationIgnored private var scope = ""
    @ObservationIgnored private var foreground = false
    @ObservationIgnored private var task: Task<Void, Never>?
    @ObservationIgnored private let defaults: UserDefaults

    public init(defaults: UserDefaults = .standard) { self.defaults = defaults }

    private var key: String { "phone.attention." + scope }

    /// This iPhone's opaque device id for notification records (16 hex, kept on the phone).
    public var deviceID: String {
        if let id = defaults.string(forKey: "phone.notify.device"), !id.isEmpty { return id }
        let id = String(UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased().prefix(16))
        defaults.set(id, forKey: "phone.notify.device")
        return id
    }

    /// The app showed `notice`: one `POST /me/events/notifications {channel: "phone"}` (none for a
    /// notice without an attention record, such as a quiet automation finish).
    public func reportShown(_ notice: AttentionNotice) {
        guard let client, let record = notice.recordKey else { return }
        let report = NotificationReport(channel: "phone", recordKey: record, device: deviceID)
        Task { try? await client.reportNotification(report) }
    }

    public func start(client: any GatewayClient, scope: String, foreground: Bool) {
        stop()
        self.client = client; self.scope = scope; self.foreground = foreground
        if let data = defaults.data(forKey: key), let kept = try? JSONDecoder().decode(AttentionState.self, from: data) { state = kept }
        else { state = AttentionState() }
        run()
    }

    public func stop() {
        task?.cancel(); task = nil; client = nil; status = .idle
    }

    public func setForeground(_ value: Bool) {
        guard value != foreground else { return }
        foreground = value
        if value { run() } else { task?.cancel(); task = nil; if status != .unsupported { status = .idle } }
    }

    private func run() {
        guard let client, status != .unsupported else { return }
        task?.cancel()
        task = Task { [weak self] in
            guard let self else { return }
            do { try await self.catchUp(client) } catch {
                if case GatewayError.http(let code, _) = error, code == 404 { self.status = .unsupported; return }
            }
            while !Task.isCancelled, self.foreground {
                self.status = .following
                do {
                    for try await event in client.userEventStream(lastEventID: self.state.cursor) {
                        self.fold(UserEventsPage(events: [event], nextAfter: event.sequence, head: event.sequence, more: false))
                    }
                } catch {
                    if case GatewayError.http(let code, _) = error, code == 404 { self.status = .unsupported; return }
                    if case GatewayError.unauthorized = error { self.status = .idle; return }
                }
                do { try await Task.sleep(for: .seconds(self.reconnectDelay)) } catch { return }
            }
            if !Task.isCancelled { self.status = .idle }
        }
    }

    /// Every page after the cursor (the history of a fresh state only takes stock).
    func catchUp(_ client: any GatewayClient) async throws {
        status = .catchingUp
        for _ in 0..<100 {
            let page = try await client.events(after: state.cursor, limit: 1000)
            try Task.checkCancellation()
            fold(page)
            if !page.more { return }
        }
    }

    private func fold(_ page: UserEventsPage) {
        let notices = state.apply(page)
        if let data = try? JSONEncoder().encode(state) { defaults.set(data, forKey: key) }
        let device = deviceID
        for notice in notices {
            if let record = notice.recordKey, state.notifiedElsewhere(record, channel: "phone", device: device) { continue }
            onNotice?(notice)
        }
        if page.events.contains(where: Self.changesLists) { onChange?() }
    }

    /// Events after which the inbox or the automations should be read again.
    static func changesLists(_ e: UserEvent) -> Bool {
        switch e.type {
        case "attention.raised", "attention.seen", "trigger.event": return true
        case "run.finished":
            if case .object(let origin)? = e.data?["origin"] { return origin["kind"]?.stringValue == "trigger" }
            return false
        default: return false
        }
    }
}
