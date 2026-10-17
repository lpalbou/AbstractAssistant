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

/// The assistant reaching you while you are not looking. When an Ask is sent, the run's ledger
/// stream (`GET /runs/{id}/ledger/stream`, which the gateway closes when the run ends) is handed to
/// a background URLSession: watchOS keeps it open with the app suspended and wakes the app when it
/// closes. The app reads the answer and posts it as a notification, which you open (the orb speaks
/// it) or ignore like any other message. Nothing is posted for an answer you are already watching.
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
    var openWaits: (@MainActor () -> Void)?

    /// Opens an answer in the app (set by the app; called on the main actor).
    var open: (@MainActor (AnswerRef) -> Void)?

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
        cfg.timeoutIntervalForRequest = 15 * 60
        cfg.timeoutIntervalForResource = 30 * 60
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

    /// Follows a run in the background until it ends.
    func watch(runId: String, title: String, prompt: String, attempt: Int = 0) {
        guard let saved = SavedSignIn.load() else { return }
        var req = URLRequest(url: saved.gateway.appending(path: "api/gateway/runs/\(runId)/ledger/stream"))
        saved.credential.apply(to: &req, write: false)
        req.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        let task = session.downloadTask(with: req)
        task.taskDescription = (try? String(decoding: JSONEncoder().encode(Watched(runId: runId, title: title, prompt: prompt, attempt: attempt)), as: UTF8.self))
        task.resume()
        trace("watching run \(runId.prefix(8)) in the background")
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
            if state == .active && showing == key { return true }
            notified.insert(key); return false
        }
        if skip { trace("not posted for \(key.prefix(8)) (already notified or on screen)"); return }
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

    /// Background refresh: posts each new wait (an approval or a question) once, then reschedules.
    func checkWaits() async {
        await MainActor.run { scheduleRefresh() }
        guard let saved = SavedSignIn.load() else { return }
        let client = LiveGatewayClient(baseURL: saved.gateway, credential: saved.credential)
        guard let waits = try? await client.waits() else { return }
        let tools = (try? await client.tools()) ?? []
        let tiers = Dictionary(tools.map { ($0.name, $0.riskTier ?? "") }, uniquingKeysWith: { a, _ in a })
        var seen = Set(UserDefaults.standard.stringArray(forKey: "notify.waits") ?? [])
        for w in waits where !seen.contains(w.id) {
            seen.insert(w.id)
            let content = UNMutableNotificationContent()
            content.sound = .default
            if w.kind == .askUser {
                content.title = "A question for you"
                content.body = w.prompt ?? "Open to answer."
                content.categoryIdentifier = Self.reviewCategory
            } else {
                let tier = tiers[w.toolName] ?? ""
                let risky = tier == "outreach" || tier == "destroy" || tier.isEmpty || w.isOutreach
                content.title = tier == "outreach" || w.isOutreach ? "Send?" : "Allow \(w.toolName)?"
                content.body = w.primaryArgument.map { "\($0.key): \($0.value)" } ?? w.toolName
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
        else if run.status == "waiting" { text = "Waiting for you: open to decide." }
        else { text = run.error ?? "The run ended (\(run.status))." }
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
            default: await MainActor.run { self.openWaits?() }
            }
            return
        }
        guard response.actionIdentifier != UNNotificationDismissActionIdentifier,
              let raw = response.notification.request.content.userInfo["answer"] as? String,
              let ref = try? JSONDecoder().decode(AnswerRef.self, from: Data(raw.utf8)) else { return }
        await MainActor.run { self.open?(ref) }
    }
}
