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
    @ObservationIgnored private var connectionID = UUID()
    @ObservationIgnored private var runID = UUID()
    @ObservationIgnored private var reconciled = false
    @ObservationIgnored private var validationWaiters: [UUID: CheckedContinuation<Void, Never>] = [:]

    public init(defaults: UserDefaults = .standard) { self.defaults = defaults }

    public func isCurrent(_ notice: AttentionNotice) -> Bool { client != nil && reconciled && state.isCurrent(notice) }

    /// Permission and notification-center calls can suspend. Keep the connection identity as well
    /// as the unread identity, so a late callback cannot post into a different signed-in account.
    public func noticeValidator(_ notice: AttentionNotice) -> @MainActor () async -> Bool {
        let connection = connectionID
        return { [weak self] in
            guard let self else { return false }
            return await self.validate(notice, connection: connection)
        }
    }

    private func validate(_ notice: AttentionNotice, connection: UUID) async -> Bool {
        while connectionID == connection, client != nil, status != .unsupported, !Task.isCancelled {
            if reconciled { return state.isCurrent(notice) }
            let id = UUID()
            await withTaskCancellationHandler {
                await withCheckedContinuation { continuation in
                    if Task.isCancelled { continuation.resume() }
                    else { validationWaiters[id] = continuation }
                }
            } onCancel: {
                Task { @MainActor [weak self] in self?.resumeValidationWaiter(id) }
            }
        }
        return false
    }

    private func resumeValidationWaiter(_ id: UUID) { validationWaiters.removeValue(forKey: id)?.resume() }
    private func resumeValidationWaiters() {
        let pending = Array(validationWaiters.values)
        validationWaiters.removeAll()
        for continuation in pending { continuation.resume() }
    }

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
        connectionID = UUID(); runID = UUID(); reconciled = false; state = AttentionState()
        resumeValidationWaiters()
    }

    public func setForeground(_ value: Bool) {
        guard value != foreground else { return }
        foreground = value
        if value { run() } else {
            task?.cancel(); task = nil; runID = UUID(); reconciled = false
            if status != .unsupported { status = .idle }
        }
    }

    private func run() {
        guard let client, status != .unsupported else { return }
        task?.cancel()
        reconciled = false
        let currentRun = UUID(); runID = currentRun
        task = Task { [weak self] in
            guard let self else { return }
            while !Task.isCancelled, self.runID == currentRun {
                do {
                    // Every reopened tail first reconciles history as a batch. Replaying SSE
                    // records one by one would alert before a later desktop-seen record arrives.
                    try await self.catchUp(client, run: currentRun)
                    guard !Task.isCancelled, self.runID == currentRun else { return }
                    guard self.foreground else { self.status = .idle; return }
                    self.status = .following
                    for try await event in client.userEventStream(lastEventID: self.state.cursor) {
                        try Task.checkCancellation()
                        guard self.runID == currentRun else { return }
                        self.fold(UserEventsPage(events: [event], nextAfter: event.sequence, head: event.sequence, more: false))
                    }
                } catch {
                    guard !Task.isCancelled, self.runID == currentRun else { return }
                    self.reconciled = false
                    if case GatewayError.http(let code, _) = error, code == 404 {
                        self.status = .unsupported; self.resumeValidationWaiters(); return
                    }
                    if case GatewayError.unauthorized = error {
                        self.status = .idle; self.connectionID = UUID(); self.resumeValidationWaiters(); return
                    }
                }
                guard !Task.isCancelled, self.runID == currentRun, self.foreground else { return }
                do { try await Task.sleep(for: .seconds(self.reconnectDelay)) } catch { return }
            }
        }
    }

    /// Publish a complete replay, never a partially folded page. A failure leaves the prior cursor
    /// intact, so the next attempt cannot lose still-unread candidates from earlier pages.
    private func catchUp(_ client: any GatewayClient, run: UUID) async throws {
        reconciled = false
        status = .catchingUp
        var replay = state
        var candidates: [AttentionNotice] = []
        var changed = false
        while true {
            let previous = replay.cursor
            let page = try await client.events(after: previous, limit: 1000)
            try Task.checkCancellation()
            guard runID == run else { throw CancellationError() }
            candidates += replay.apply(page)
            changed = changed || page.events.contains(where: Self.changesLists)
            if !page.more {
                state = replay
                reconciled = true
                resumeValidationWaiters()
                save()
                tell(candidates)
                if changed { onChange?() }
                return
            }
            guard replay.cursor > previous else { throw GatewayError.invalidResponse }
        }
    }

    private func fold(_ page: UserEventsPage) {
        let notices = state.apply(page)
        save()
        tell(notices)
        if page.events.contains(where: Self.changesLists) { onChange?() }
    }

    private func save() {
        if let data = try? JSONEncoder().encode(state) { defaults.set(data, forKey: key) }
    }

    private func tell(_ notices: [AttentionNotice]) {
        let device = deviceID
        for notice in notices where isCurrent(notice) {
            if let record = notice.recordKey, state.notifiedElsewhere(record, channel: "phone", device: device) { continue }
            onNotice?(notice)
        }
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
