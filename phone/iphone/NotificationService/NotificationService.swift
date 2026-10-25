import AssistantPush
import Foundation
import UserNotifications

/// The notification service extension of the iPhone app and of the watch app (one source, two
/// targets; framework backlog 1049). The relay's push carries no words of the person's: a kind
/// (its generic localized text), `s` (the event's number in the person's stream) and `r` (the
/// sign-in it was meant for). This reads that one event from the person's own gateway with the
/// sign-in kept sealed in the app group and shows it as the app's catch-up would. A push for
/// another sign-in becomes a passive "From an earlier sign-in"; an event not read in time keeps
/// the generic text. The notification's identifier is APNs' collapse id (the gateway's), the same
/// id the app's catch-up uses, so nothing alerts twice.
final class NotificationService: UNNotificationServiceExtension, @unchecked Sendable {
    private let lock = NSLock()
    private var handler: ((UNNotificationContent) -> Void)?
    private var original: UNNotificationContent?
    private var work: Task<Void, Never>?

    #if os(watchOS)
    private static let platform = PushPlatform.watch
    #else
    private static let platform = PushPlatform.phone
    #endif

    override func didReceive(_ request: UNNotificationRequest, withContentHandler contentHandler: @escaping (UNNotificationContent) -> Void) {
        lock.withLock { handler = contentHandler; original = request.content }
        guard let payload = PushPayload(userInfo: request.content.userInfo) else { finish(nil); return }
        work = Task { [self] in
            let rendering = await PushRenderer.content(
                for: payload, platform: Self.platform, signIn: SharedSignInStore.load(),
                session: PushRegistrar.makeSession(),
                text: { NSLocalizedString($0, comment: "") },
                name: { AutomationNameBook.name($0) })
            finish(rendering)
        }
    }

    override func serviceExtensionTimeWillExpire() {
        work?.cancel()
        finish(nil)
    }

    /// Hands the notification to the system once: the rendering, or the push as it came.
    private func finish(_ rendering: PushRendering?) {
        let (handler, original) = lock.withLock { () -> (((UNNotificationContent) -> Void)?, UNNotificationContent?) in
            let h = self.handler; self.handler = nil
            return (h, self.original)
        }
        guard let handler, let original else { return }
        guard let rendering, let content = original.mutableCopy() as? UNMutableNotificationContent else { handler(original); return }
        content.title = rendering.title
        content.body = rendering.body
        content.interruptionLevel = rendering.timeSensitive ? .timeSensitive : .passive
        var info = content.userInfo
        for (key, value) in rendering.userInfo { info[key] = value }
        content.userInfo = info
        handler(content)
    }
}
