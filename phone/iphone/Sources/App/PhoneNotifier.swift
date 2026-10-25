import Foundation
import UserNotifications
import AbstractGatewayClient

/// Local notifications from the person's event stream (framework backlog 1047): what needs you is
/// time-sensitive ("Approval needed", "A question for you"; a tap opens the Inbox, whose wait screens
/// read the waits live), automation news is passive ("Morning digest has a result"; a tap opens
/// Automations). One notification per item: the identifier is the item's, so a repeat replaces it.
/// Not recorded on the stream: the gateway's notification channels are tray, assistant, code and
/// watch, with no phone channel yet.
@MainActor
final class PhoneNotifier: NSObject, UNUserNotificationCenterDelegate {
    static let shared = PhoneNotifier()
    /// The tab a tapped notification opens (1 Inbox, 2 Automations); set by the app.
    var open: ((Int) -> Void)?
    private var asked = false

    func activate() { UNUserNotificationCenter.current().delegate = self }

    func post(_ notice: AttentionNotice, automationNames: [String: String]) {
        let content = UNMutableNotificationContent()
        content.sound = .default
        switch notice {
        case .needsYou(_, _, let kind, _, _):
            content.title = kind == "question" ? "A question for you" : "Approval needed"
            content.body = "Open the Inbox to answer."
            content.interruptionLevel = .timeSensitive
            content.userInfo = ["tab": 1]
        case .news(let id, _, let failed, _):
            content.title = (automationNames[id] ?? "An automation") + (failed ? " failed" : " has a result")
            content.body = "Tap to read it."
            content.interruptionLevel = .passive
            content.userInfo = ["tab": 2]
        case .automationFinished(let id, _, let status, _):
            content.title = (automationNames[id] ?? "An automation") + (status == "failed" ? " failed" : " finished")
            content.body = "Tap to read it."
            content.interruptionLevel = .passive
            content.userInfo = ["tab": 2]
        }
        let request = UNNotificationRequest(identifier: notice.identifier, content: content, trigger: nil)
        Task {
            let center = UNUserNotificationCenter.current()
            if !asked {
                asked = true
                _ = try? await center.requestAuthorization(options: [.alert, .sound, .badge])
            }
            try? await center.add(request)
        }
    }

    nonisolated func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification) async -> UNNotificationPresentationOptions {
        [.banner, .sound, .list]
    }

    nonisolated func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse) async {
        guard response.actionIdentifier != UNNotificationDismissActionIdentifier,
              let tab = response.notification.request.content.userInfo["tab"] as? Int else { return }
        await MainActor.run { PhoneNotifier.shared.open?(tab) }
    }
}
