import AbstractGatewayClient
import Foundation
import UserNotifications
import WatchKit

/// Which answer to open: a run of the Assistant, or an entity's reply (no run).
struct AnswerRef: Hashable, Codable {
    var runId: String?
    var text: String?
    var entity: String?
    var prompt: String?
}

/// The assistant reaching you while you are not looking. When the app leaves the foreground with a
/// run still working, the run's ledger stream (`GET /runs/{id}/ledger/stream`, which the gateway
/// closes when the run ends) is handed to a background URLSession: watchOS keeps it open with the
/// app suspended and wakes the app when it closes. The app reads the answer and posts it as a
/// notification, which you open (the orb speaks it) or ignore like any other message. Nothing is
/// posted for an answer you are already watching. The stream is the radio's cost while the app
/// sleeps (a keep-alive every 50 s): it is started only once the app is not in front, once per run,
/// ended when the app sees the run end, and given up after an hour.
final class AnswerNotifier: NSObject, @unchecked Sendable {
    static let shared = AnswerNotifier()
    static let sessionIdentifier = "ai.abstractframework.assistant.answers"
    static let category = "assistant.answer"
    static let listenAction = "assistant.listen"
    static let approvalCategory = "assistant.approval"
    static let reviewCategory = "assistant.review"
    static let allowAction = "assistant.allow"
    static let denyAction = "assistant.deny"
    /// Opens the waits on screen (set by the app).
    var openWait: (@MainActor (Wait) -> Void)?

    /// Opens an answer in the app (set by the app; called on the main actor).
    var open: (@MainActor (AnswerRef) -> Void)?
    /// Opens an automation's page (a tap on "… finished").
    var openAutomation: (@MainActor (String) -> Void)?

    private let lock = NSLock()
    private var notified: Set<String> = []
    private var showing: String?
    private var eventsFinished: CheckedContinuation<Void, Never>?
    /// The session's events were delivered before the app asked to wait for them.
    private var eventsAlreadyFinished = false
    private lazy var session: URLSession = {
        let cfg = URLSessionConfiguration.background(withIdentifier: Self.sessionIdentifier)
        cfg.isDiscretionary = false
        cfg.sessionSendsLaunchEvents = true
        cfg.timeoutIntervalForRequest = 5 * 60              // three missed keep-alives
        cfg.timeoutIntervalForResource = 15 * 60
        return URLSession(configuration: cfg, delegate: self, delegateQueue: nil)
    }()

    /// Called at launch: re-attaches the background session and installs the notification actions.
    func activate() {
        _ = session
        let listen = UNNotificationAction(identifier: Self.listenAction, title: "Listen", options: [.foreground])
        let cat = UNNotificationCategory(identifier: Self.category, actions: [listen], intentIdentifiers: [], options: [])
        // Approvals: Allow needs the watch unlocked; Deny is marked destructive. Sends and
        // destructive calls get no inline Allow (category "review": open the app to decide).
        let allow = UNNotificationAction(identifier: Self.allowAction, title: "Allow", options: [.authenticationRequired])
        let deny = UNNotificationAction(identifier: Self.denyAction, title: "Deny", options: [.destructive])
        let approval = UNNotificationCategory(identifier: Self.approvalCategory, actions: [allow, deny], intentIdentifiers: [], options: [])
        let review = UNNotificationCategory(identifier: Self.reviewCategory, actions: [deny], intentIdentifiers: [], options: [])
        let center = UNUserNotificationCenter.current()
        center.setNotificationCategories([cat, approval, review])
        center.delegate = self
    }

    /// Asks once for permission to post answers (the first time the person asks something).
    func requestPermission() {
        let d = UserDefaults.standard
        guard !d.bool(forKey: "notify.asked") else { return }
        d.set(true, forKey: "notify.asked")
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { _, _ in }
    }

    /// The answer on screen right now (nil when none): no notification for it while the app is active.
    func setShowing(_ key: String?) { lock.withLock { showing = key } }

    /// Follows a run in the background until it ends (one stream per run: a second call for the
    /// same run changes nothing).
    func watch(runId: String, title: String, prompt: String, attempt: Int = 0) {
        guard let saved = SavedSignIn.load() else { return }
        var url = saved.gateway.appending(path: "api/gateway/runs/\(runId)/ledger/stream")
        url.append(queryItems: [URLQueryItem(name: "heartbeat_s", value: "50")])
        var req = URLRequest(url: url)
        saved.credential.apply(to: &req, write: false)
        req.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        let desc = (try? String(decoding: JSONEncoder().encode(Watched(runId: runId, title: title, prompt: prompt, attempt: attempt)), as: UTF8.self))
        session.getAllTasks { tasks in
            if attempt == 0, tasks.contains(where: { Self.runId(of: $0) == runId && $0.state == .running }) {
                self.trace("already watching run \(runId.prefix(8))"); return
            }
            let task = self.session.downloadTask(with: req)
            task.taskDescription = desc
            task.resume()
            self.trace("watching run \(runId.prefix(8)) in the background (attempt \(attempt))")
        }
    }

    /// The app saw the run end (or park on a person): its stream has nothing left to tell.
    func unwatch(runId: String) {
        session.getAllTasks { tasks in
            for t in tasks where Self.runId(of: t) == runId { t.cancel() }
        }
    }

    private static func runId(of task: URLSessionTask) -> String? {
        task.taskDescription.flatMap { try? JSONDecoder().decode(Watched.self, from: Data($0.utf8)) }?.runId
    }

    private func trace(_ s: String) {
        #if DEBUG
        print("notifier \(s)")
        #endif
    }

    /// Posts an answer as a notification unless the person is looking at it in the app.
    func deliver(key: String, title: String, ref: AnswerRef, answer: String) async {
        let state = await MainActor.run { WKApplication.shared().applicationState }
        let skip: Bool = lock.withLock {
            if notified.contains(key) { return true }
            // On screen (even dimmed, wrist down): the orb shows and speaks it; only a person who
            // left the app gets the notification.
            if state != .background && showing == key { return true }
            notified.insert(key); return false
        }
        if skip { trace("not posted for \(key.prefix(8)) (already notified or on screen)"); return }
        AutomationNotices.delivered(run: key)                 // an automation's run: not posted again by the check
        let content = UNMutableNotificationContent()
        content.title = title
        if let p = ref.prompt, !p.isEmpty { content.subtitle = "“\(p)”" }
        let spoken = SpeechText.plain(answer)
        content.body = spoken.count > 600 ? String(spoken.prefix(600)) + "…" : spoken
        content.sound = .default
        content.categoryIdentifier = Self.category
        if let data = try? JSONEncoder().encode(ref) { content.userInfo = ["answer": String(decoding: data, as: UTF8.self)] }
        let settings = await UNUserNotificationCenter.current().notificationSettings()
        do {
            try await UNUserNotificationCenter.current().add(UNNotificationRequest(identifier: key, content: content, trigger: nil))
            trace("posted \(key.prefix(8)) (authorization \(settings.authorizationStatus.rawValue), app state \(state.rawValue))")
        } catch { trace("post failed \(error)") }
    }

    // MARK: Waits while the app is closed (background refresh, about every 15 minutes)

    /// Asks watchOS to wake the app in about 15 minutes to look for new waits.
    static let refreshIdentifier = "assistant.waits"

    @MainActor func scheduleRefresh() {
        WKApplication.shared().scheduleBackgroundRefresh(withPreferredDate: Date().addingTimeInterval(15 * 60),
                                                         userInfo: Self.refreshIdentifier as NSString) { _ in }
    }

    /// Background refresh: posts each new wait (an approval or a question) once, and each
    /// automation that finished a run (Settings → Automation results), then reschedules.
    func checkWaits() async {
        await MainActor.run { scheduleRefresh() }
        guard let saved = SavedSignIn.load() else { return }
        let client = LiveGatewayClient(baseURL: saved.gateway, credential: saved.credential)
        // Both reads go out together (on the watch's radio each one costs seconds).
        await withTaskGroup(of: Void.self) { group in
            group.addTask { await self.checkAutomations(client) }
            group.addTask { await self.postWaits(client) }
        }
    }

    /// Each automation that finished a run since the last look: "Morning digest finished" and the
    /// first words of its answer (a tap opens it). Not for a run already posted (Run now, then left).
    private func checkAutomations(_ client: LiveGatewayClient) async {
        guard AutomationNotices.on, let list = try? await client.automations() else { return }
        for a in AutomationNotices.finished(in: list) where !AutomationNotices.wasDelivered(a.lastOccurrence?.runId) {
            let content = UNMutableNotificationContent()
            let failed = a.lastOccurrence?.status == "failed"
            content.title = (a.name ?? "An automation") + (failed ? " failed" : " finished")
            let text = SpeechText.plain(a.lastOccurrence?.excerpt ?? "")
            content.body = text.count > 300 ? String(text.prefix(300)) + "…" : text
            content.sound = .default
            content.userInfo = ["automation": a.id]
            try? await UNUserNotificationCenter.current().add(UNNotificationRequest(
                identifier: "automation-\(a.id)-\(a.lastOccurrence?.index ?? 0)", content: content, trigger: nil))
            trace("posted automation \(a.id.prefix(8))")
        }
    }

    private func postWaits(_ client: LiveGatewayClient) async {
        guard let waits = try? await client.waits() else { return }
        var seen = Set(UserDefaults.standard.stringArray(forKey: "notify.waits") ?? [])
        let unseen = waits.filter { !seen.contains($0.id) }
        guard !unseen.isEmpty else { return }                     // nothing new: no more requests
        // The tools' risk tiers (which approvals may be allowed from the notification): read only
        // when there is something to post.
        let tools = unseen.contains { $0.kind != .askUser } ? ((try? await client.tools()) ?? []) : []
        let tiers = Dictionary(tools.map { ($0.name, $0.riskTier ?? "") }, uniquingKeysWith: { a, _ in a })
        for w in unseen {
            seen.insert(w.id)
            let content = UNMutableNotificationContent()
            content.sound = .default
            if w.kind == .askUser {
                content.title = "A question for you"
                content.body = w.prompt ?? ""
                // No category: a question has no Allow or Deny; a tap opens it.
            } else {
                let tier = tiers[w.toolName] ?? ""
                let risky = tier == "outreach" || tier == "destroy" || tier.isEmpty || w.isOutreach
                content.title = w.headline + "?"
                content.body = w.recipient.map { [$0, w.subject].compactMap { $0 }.joined(separator: " · ") } ?? w.primaryArgument?.value ?? ""
                content.categoryIdentifier = risky ? Self.reviewCategory : Self.approvalCategory
            }
            if let data = try? JSONEncoder().encode(w) { content.userInfo = ["wait": String(decoding: data, as: UTF8.self)] }
            try? await UNUserNotificationCenter.current().add(UNNotificationRequest(identifier: "wait-" + w.id, content: content, trigger: nil))
            trace("posted wait \(w.toolName)")
        }
        UserDefaults.standard.set(Array(seen.suffix(80)), forKey: "notify.waits")
    }

    /// The system woke the app for this session's events: wait until they are delivered.
    func handleBackgroundEvents() async {
        _ = session
        await withCheckedContinuation { (c: CheckedContinuation<Void, Never>) in
            let resumeNow: Bool = lock.withLock {
                if eventsAlreadyFinished { eventsAlreadyFinished = false; return true }
                eventsFinished?.resume()          // a second wake: never leak the first
                eventsFinished = c
                return false
            }
            if resumeNow { c.resume() }
        }
    }

    private struct Watched: Codable {
        let runId: String; let title: String; let prompt: String
        var attempt: Int? = 0
    }

    /// The stream may close before the run ends (a proxy's idle timeout, the 30-minute limit):
    /// follow it again, three times at most.
    private func rewatch(_ w: Watched) {
        let next = (w.attempt ?? 0) + 1
        guard next <= 3 else { trace("gave up following \(w.runId.prefix(8))"); return }
        watch(runId: w.runId, title: w.title, prompt: w.prompt, attempt: next)
    }

    /// The stream closed: the run ended. Read its answer and deliver it.
    private func runEnded(_ w: Watched) async {
        trace("stream closed for run \(w.runId.prefix(8))")
        guard let saved = SavedSignIn.load() else { return }
        let client = LiveGatewayClient(baseURL: saved.gateway, credential: saved.credential)
        guard let run = try? await client.run(id: w.runId) else { return }
        guard run.isTerminal || run.status == "waiting" else { rewatch(w); return }
        let text: String
        if let out = run.outputText, !out.isEmpty { text = out }
        else if run.status == "waiting" { text = "I need your OK to continue." }
        else { text = "I couldn't finish this one." }
        await deliver(key: w.runId, title: w.title, ref: AnswerRef(runId: w.runId, prompt: w.prompt), answer: text)
    }
}

extension AnswerNotifier: URLSessionDownloadDelegate {
    func urlSession(_ session: URLSession, downloadTask: URLSessionDownloadTask, didFinishDownloadingTo location: URL) {
        guard let desc = downloadTask.taskDescription, let w = try? JSONDecoder().decode(Watched.self, from: Data(desc.utf8)) else { return }
        // An error answer (403, 404, a proxy page) is not the run ending: say nothing.
        if let http = downloadTask.response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            trace("stream answered \(http.statusCode) for \(w.runId.prefix(8))"); return
        }
        let done = DispatchSemaphore(value: 0)
        Task { await self.runEnded(w); done.signal() }
        _ = done.wait(timeout: .now() + 20)
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        guard let error, let desc = task.taskDescription,
              let w = try? JSONDecoder().decode(Watched.self, from: Data(desc.utf8)) else { return }
        if (error as NSError).code == NSURLErrorCancelled { return }
        trace("stream failed for \(w.runId.prefix(8)): \(error.localizedDescription)")
        rewatch(w)
    }

    func urlSessionDidFinishEvents(forBackgroundURLSession session: URLSession) {
        let c: CheckedContinuation<Void, Never>? = lock.withLock {
            let c = eventsFinished; eventsFinished = nil
            if c == nil { eventsAlreadyFinished = true }
            return c
        }
        c?.resume()
    }
}

extension AnswerNotifier: UNUserNotificationCenterDelegate {
    /// The app is frontmost (often dimmed, wrist down): still show it, as a message would be.
    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification) async -> UNNotificationPresentationOptions {
        [.banner, .sound]
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse) async {
        // A wait: Allow / Deny answer it right here; a tap opens the waits.
        if let raw = response.notification.request.content.userInfo["wait"] as? String,
           let w = try? JSONDecoder().decode(Wait.self, from: Data(raw.utf8)) {
            switch response.actionIdentifier {
            case Self.allowAction, Self.denyAction:
                guard let saved = SavedSignIn.load() else { return }
                let client = LiveGatewayClient(baseURL: saved.gateway, credential: saved.credential)
                try? await client.answer(w, with: response.actionIdentifier == Self.allowAction ? .approve : .deny)
            case UNNotificationDismissActionIdentifier: break
            default: await MainActor.run { self.openWait?(w) }
            }
            return
        }
        if let id = response.notification.request.content.userInfo["automation"] as? String {
            if response.actionIdentifier != UNNotificationDismissActionIdentifier { await MainActor.run { self.openAutomation?(id) } }
            return
        }
        guard response.actionIdentifier != UNNotificationDismissActionIdentifier,
              let raw = response.notification.request.content.userInfo["answer"] as? String,
              let ref = try? JSONDecoder().decode(AnswerRef.self, from: Data(raw.utf8)) else { return }
        await MainActor.run { self.open?(ref) }
    }
}

/// "An automation finished": on by default (Settings → Automation results). The numbers of the
/// automations' latest runs known on this watch (shared by the app and its background check, so a
/// run is news once), and the runs already posted by the answer stream.
enum AutomationNotices {
    static let key = "notify.automations"
    private static let knownKey = "notify.automations.known", deliveredKey = "notify.automations.delivered"
    static var on: Bool { UserDefaults.standard.object(forKey: key) as? Bool ?? true }

    /// The automations that finished a run since the last look (and notes them as looked at).
    static func finished(in list: [AutomationSummary]) -> [AutomationSummary] {
        let known = UserDefaults.standard.dictionary(forKey: knownKey) as? [String: Int] ?? [:]
        let r = FinishedRuns.since(known, in: list)
        UserDefaults.standard.set(r.known, forKey: knownKey)
        return r.finished
    }

    static func delivered(run: String) {
        var runs = UserDefaults.standard.stringArray(forKey: deliveredKey) ?? []
        runs.append(run)
        UserDefaults.standard.set(Array(runs.suffix(40)), forKey: deliveredKey)
    }
    static func wasDelivered(_ run: String?) -> Bool {
        guard let run else { return false }
        return (UserDefaults.standard.stringArray(forKey: deliveredKey) ?? []).contains(run)
    }
}
