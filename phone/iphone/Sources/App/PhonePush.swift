import AssistantKit
import AssistantPush
import OSLog
import UIKit
import UserNotifications

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
        case .registered(let relay): log.info("push registration accepted (relay \(relay, privacy: .public))"); PhoneTrace.note("push: registered (relay \(relay))")
        case .skipped(let why): log.debug("push registration not sent: \(why, privacy: .public)"); PhoneTrace.note("push: not sent: \(why)")
        case .failed(let why): log.error("push registration failed: \(why, privacy: .public)"); PhoneTrace.note("push: failed: \(why)")
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
        PhoneTrace.note("push: no token: \(error.localizedDescription)")
    }
}

/// Debug builds: what the launch sign-in, the watch handoff and push registration did, as
/// `phone-trace` lines on the console (`xcrun devicectl device process launch --console …`) and the
/// last 40 kept; `--dump-trace` prints those at launch. Never a credential. Release: nothing.
enum PhoneTrace {
    static let key = "phone.trace"
    static func note(_ line: @autoclosure () -> String) {
        #if DEBUG
        let stamped = "\(ISO8601DateFormatter().string(from: Date())) \(line())"
        print("phone-trace \(stamped)"); fflush(stdout)
        let d = UserDefaults.standard
        d.set(Array(((d.stringArray(forKey: key) ?? []) + [stamped]).suffix(40)), forKey: key)
        #endif
    }
    static func dump() {
        #if DEBUG
        for line in UserDefaults.standard.stringArray(forKey: key) ?? [] { print("phone-trace-kept \(line)") }
        fflush(stdout)
        #endif
    }
}
