import AssistantKit
import AssistantPush
import OSLog
import UIKit
import UserNotifications
import WatchConnectivity

/// Apple push on the iPhone (framework backlog 1049): the app registers its APNs token with the
/// person's gateway at sign-in (a new `reg`), on every new token and at most daily, and forgets it
/// at sign-out. Nothing to configure: a gateway answering `relay: off` keeps the registration and
/// nothing else changes. The notification service extension renders what arrives.
@MainActor
enum PhonePush {
    static let registrar = PushRegistrar()
    nonisolated static let log = Logger(subsystem: "ai.abstractframework.assistant", category: "push")

    /// This iPhone's device id: the one its notification reports already carry (AttentionFeed).
    static var deviceID = ""

    static var device: PushDevice {
        PushDevice(deviceID: deviceID, app: .phone, topic: Bundle.main.bundleIdentifier ?? "ai.abstractframework.assistant",
                   env: PushEnvironment.current(), name: UIDevice.current.name)
    }

    /// At launch with a sign-in, and after each sign-in: asks the system for the token (it answers
    /// in `PhoneAppDelegate`, every launch), which registers when needed.
    static func start() {
        guard !deviceID.isEmpty, ConnectionVault.current() != nil else { return }
        UIApplication.shared.registerForRemoteNotifications()
        Task { await refresh() }
    }

    static func tokenArrived(_ token: Data) {
        let device = device, signIn = ConnectionVault.current()
        Task { report(await registrar.tokenArrived(token, device: device, signIn: signIn)) }
    }

    static func refresh() async {
        report(await registrar.refresh(device: device, signIn: ConnectionVault.current()))
    }

    /// Sign-out: the gateway forgets this device (with the credential being forgotten).
    static func signedOut(_ signIn: SharedSignIn?) {
        guard let signIn, !deviceID.isEmpty else { return }
        let id = deviceID
        Task { _ = await registrar.signedOut(signIn, deviceID: id) }
    }

    private static func report(_ outcome: PushOutcome) {
        switch outcome {
        case .registered(let relay): log.info("push registration accepted (relay \(relay, privacy: .public))")
        case .skipped(let why): log.debug("push registration not sent: \(why, privacy: .public)")
        case .failed(let why): log.error("push registration failed: \(why, privacy: .public)")
        }
    }

    /// Asked once, right after the first sign-in: a push can only show with the person's permission.
    static func askPermissionOnce() {
        let d = UserDefaults.standard
        guard !d.bool(forKey: "phone.notify.asked") else { return }
        d.set(true, forKey: "phone.notify.asked")
        Task { _ = try? await UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) }
    }
}

final class PhoneAppDelegate: NSObject, UIApplicationDelegate {
    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        MainActor.assumeIsolated { PhonePush.tokenArrived(deviceToken) }
    }

    func application(_ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error) {
        PhonePush.log.error("no push token: \(error.localizedDescription, privacy: .public)")
    }
}

/// The iPhone hands its sign-in to the watch app (one sign-in for the product): the application
/// context holds the latest one (delivered whenever the watch app next runs), and
/// `transferUserInfo` queues it as well at each sign-in. The watch takes it when it is newer than
/// its own; a watch without its iPhone signs in on its own.
final class WatchLink: NSObject, WCSessionDelegate, @unchecked Sendable {
    static let shared = WatchLink()

    func activate() {
        guard WCSession.isSupported() else { return }
        WCSession.default.delegate = self
        WCSession.default.activate()
    }

    /// A sign-in on the iPhone: to the watch now (context) and queued (user info).
    func send(_ signIn: SharedSignIn, queue: Bool) {
        guard WCSession.isSupported(), WCSession.default.activationState == .activated,
              WCSession.default.isPaired, WCSession.default.isWatchAppInstalled else { return }
        let message = SignInHandoff(signIn).message
        do { try WCSession.default.updateApplicationContext(message) }
        catch { PhonePush.log.error("watch context not sent: \(error.localizedDescription, privacy: .public)") }
        if queue { WCSession.default.transferUserInfo(message) }
    }

    func session(_ session: WCSession, activationDidCompleteWith activationState: WCSessionActivationState, error: Error?) {
        guard activationState == .activated, let current = SharedSignInStore.load(), current.hasCredential else { return }
        // The context stays current (a watch app installed after the sign-in gets it too).
        send(current, queue: false)
    }

    func sessionDidBecomeInactive(_ session: WCSession) {}
    func sessionDidDeactivate(_ session: WCSession) { WCSession.default.activate() }
    func sessionWatchStateDidChange(_ session: WCSession) {
        if let current = SharedSignInStore.load(), current.hasCredential { send(current, queue: false) }
    }
}
