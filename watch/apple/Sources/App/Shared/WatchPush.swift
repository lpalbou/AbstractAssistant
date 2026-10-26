import AssistantPush
import Foundation
import UserNotifications
import WatchKit

/// Apple push on the watch (framework backlog 1049): the app registers its APNs token with the
/// person's gateway at sign-in (a new `reg`), on every new token and at most daily, and forgets it
/// at sign-out. Nothing to configure: a gateway answering `relay: off` keeps the registration and
/// nothing else changes. The watch's notification service extension renders what arrives.
@MainActor
enum WatchPush {
    static let registrar = PushRegistrar()

    static var device: PushDevice {
        PushDevice(deviceID: AnswerNotifier.deviceId, app: .watch,
                   topic: Bundle.main.bundleIdentifier ?? "ai.abstractframework.assistant.watchkitapp",
                   env: PushEnvironment.current(), name: WKInterfaceDevice.current().name)
    }

    /// At launch with a sign-in, and after each sign-in: the system answers with the token in
    /// `WatchAppDelegate` (every launch), which registers when needed.
    static func start() {
        guard SavedSignIn.current() != nil else { return }
        WKApplication.shared().registerForRemoteNotifications()
        let device = device, signIn = SavedSignIn.current()
        Task { trace(await registrar.refresh(device: device, signIn: signIn)) }
    }

    static func tokenArrived(_ token: Data) {
        let device = device, signIn = SavedSignIn.current()
        Task { trace(await registrar.tokenArrived(token, device: device, signIn: signIn)) }
    }

    /// Sign-out: the gateway forgets this watch (with the credential being forgotten).
    static func signedOut(_ signIn: SharedSignIn?) {
        guard let signIn else { return }
        let id = AnswerNotifier.deviceId
        Task { _ = await registrar.signedOut(signIn, deviceID: id) }
    }

    static func trace(_ outcome: PushOutcome) {
        #if DEBUG
        print("push \(outcome)")
        #endif
    }
}

/// The APNs token arrives here.
final class WatchAppDelegate: NSObject, WKApplicationDelegate {
    func applicationDidFinishLaunching() {
        // Push registration at launch with a saved sign-in (a sign-in registers in `connect`);
        // the simulator's mock screens never register.
        if !ProcessInfo.processInfo.arguments.contains("--mock") { MainActor.assumeIsolated { WatchPush.start() } }
    }

    func didRegisterForRemoteNotifications(withDeviceToken deviceToken: Data) {
        MainActor.assumeIsolated { WatchPush.tokenArrived(deviceToken) }
    }

    func didFailToRegisterForRemoteNotificationsWithError(_ error: Error) {
        #if DEBUG
        print("push no token: \(error.localizedDescription)")
        #endif
    }
}
