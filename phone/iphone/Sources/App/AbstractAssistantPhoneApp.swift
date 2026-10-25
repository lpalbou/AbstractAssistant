import SwiftUI
import AssistantKit
import AbstractGatewayClient
import AssistantPush
import OSLog

@main struct AbstractAssistantPhoneApp: App {
    private static let prepareTemporaryStorage: Void = {
        do { try PhoneTemporaryStorage().removeStaleFiles() }
        catch { Logger(subsystem: "ai.abstractframework.assistant.iphone", category: "storage").error("Disposable file cleanup failed: \(error.localizedDescription, privacy: .public)") }
        #if DEBUG
        if ProcessInfo.processInfo.arguments.contains("--storage-audit") {
            do {
                let stats = try FileManager.default.attributesOfFileSystem(forPath: NSHomeDirectory())
                let values = ["volume_capacity_bytes": (stats[.systemSize] as? NSNumber)?.int64Value ?? -1,
                              "volume_free_bytes": (stats[.systemFreeSize] as? NSNumber)?.int64Value ?? -1]
                let root = PhoneTemporaryStorage().root
                try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
                try JSONEncoder().encode(values).write(to: root.appending(path: "storage-audit.json"), options: .atomic)
            } catch { Logger(subsystem: "ai.abstractframework.assistant.iphone", category: "storage").error("Storage audit failed: \(error.localizedDescription, privacy: .public)") }
        }
        #endif
    }()
    /// The APNs token arrives here (PhonePush registers it with the gateway).
    @UIApplicationDelegateAdaptor(PhoneAppDelegate.self) private var appDelegate
    init() { _ = Self.prepareTemporaryStorage }
    var body: some Scene { WindowGroup { PhoneRoot() } }
}

struct PhoneRoot: View {
    @State private var store = AssistantStore()
    @State private var settings = false
    @State private var tab = 0
    @State private var storageError: String?
    @Environment(\.scenePhase) private var scenePhase
    var body: some View {
        Group {
            if store.isConnected {
                TabView(selection: $tab) {
                    Tab("Assistant", systemImage: "sparkle", value: 0) { ChatScreen(openSettings: { settings = true }) }
                    Tab("Inbox", systemImage: "tray", value: 1) { InboxScreen() }.badge(store.inboxBadge)
                    Tab("Automations", systemImage: "clock.arrow.circlepath", value: 2) { AutomationsScreen() }.badge(store.attention.newResults)
                }
                .sheet(isPresented: $settings) { SettingsScreen(onDisconnect: disconnect, notice: storageError) }
            } else { WelcomeScreen(onConnect: { connect($0) }, onDemo: demo, notice: storageError ?? store.error) }
        }
        .environment(store)
        .preferredColorScheme(.dark).tint(PhoneTheme.lavender)
        .foregroundStyle(PhoneTheme.ink)
        .onChange(of: automationNames, initial: true) { _, names in AutomationNameBook.remember(names) }
        .task {
            // Push (backlog 1049) and the watch: this iPhone's device id, the sign-in handed to the watch.
            PhonePush.deviceID = store.attention.deviceID
            WatchLink.shared.activate()
            store.onUnauthorized = { do { try ConnectionVault.remove() } catch { storageError = error.localizedDescription } }
            // The person's event stream: a local notification per new item; a tap opens its tab.
            PhoneNotifier.shared.activate()
            PhoneNotifier.shared.open = { tab = $0 }
            store.attention.onNotice = { notice in
                PhoneNotifier.shared.post(notice, automationNames: Dictionary(store.automations.map { ($0.id, $0.name ?? "") }.filter { !$0.1.isEmpty },
                                                                              uniquingKeysWith: { a, _ in a }),
                                          shown: { store.attention.reportShown(notice) })
            }
            #if DEBUG
            if ProcessInfo.processInfo.arguments.contains("--demo") { demo(); return }
            // Development-device provisioning: verify before replacing the saved sign-in.
            // Credentials arrive through the launch environment, never source files.
            let environment = ProcessInfo.processInfo.environment
            if let address = environment["ASSISTANT_PAIR_GATEWAY"],
               let token = environment["ASSISTANT_PAIR_TOKEN"], !token.isEmpty {
                do {
                    let gateway = try SavedConnection.parseURL(address)
                    let credential = GatewayCredential.token(token)
                    let client = LiveGatewayClient(baseURL: gateway, credential: credential, session: PhoneTransport.makeSession())
                    let principal = try await client.me()
                    guard let user = principal.userId, !user.isEmpty else { throw GatewayError.invalidResponse }
                    connect(SavedConnection(gateway: gateway, user: user, tenant: principal.tenantId ?? "default", credential: credential))
                } catch { storageError = error.localizedDescription }
                return
            }
            #endif
            do { if let saved = try ConnectionVault.read() { connect(saved, persist: false) } }
            catch { storageError = error.localizedDescription }
        }
        .onChange(of: scenePhase, initial: true) { _, phase in store.setForeground(phase == .active) }
    }
    /// The automations' names for the notification service extension ("Morning digest has a result").
    private var automationNames: [String: String] {
        Dictionary(store.automations.compactMap { a in a.name.flatMap { $0.isEmpty ? nil : (a.id, $0) } }, uniquingKeysWith: { a, _ in a })
    }
    /// `persist`: a sign-in (both paths: an account token or an emailed code), saved sealed with a
    /// new push handle and handed to the watch; otherwise the saved sign-in at launch.
    private func connect(_ connection: SavedConnection, persist: Bool = true) {
        do {
            if persist { try ConnectionVault.save(connection) }
            storageError = nil
            store.connect(connection, client: LiveGatewayClient(baseURL: connection.gateway, credential: connection.credential, session: PhoneTransport.makeSession()))
            if persist, let signIn = ConnectionVault.current() {
                WatchLink.shared.send(signIn, queue: true)
                PhonePush.askPermissionOnce()
            }
            PhonePush.start()
        } catch { storageError = error.localizedDescription }
    }
    private func demo() {
        #if DEBUG
        let emptyAutomations = ProcessInfo.processInfo.arguments.contains("--empty-automations")
        #else
        let emptyAutomations = false
        #endif
        #if DEBUG
        let speechPreparationDelay: TimeInterval = ProcessInfo.processInfo.arguments.contains("--ui-test") && ProcessInfo.processInfo.arguments.contains("--speech-delay-fixture") ? 4 : 0
        let activityScenario = ProcessInfo.processInfo.arguments.first { $0.hasPrefix("--activity=") }?.replacingOccurrences(of: "--activity=", with: "")
        #else
        let speechPreparationDelay: TimeInterval = 0
        let activityScenario: String? = nil
        #endif
        store.connect(nil, client: MockGatewayClient(emptyAutomations: emptyAutomations, activityScenario: activityScenario,
            historyFixture: ProcessInfo.processInfo.arguments.contains("--history-fixture"),
            conversationListFixture: ProcessInfo.processInfo.arguments.contains("--conversation-list-fixture"),
            categoryFixture: ProcessInfo.processInfo.arguments.contains("--category-fixture"),
            emailFixture: ProcessInfo.processInfo.arguments.contains("--email-fixture"),
            accessFixture: ProcessInfo.processInfo.arguments.contains("--access-fixture"),
            mediaImage: MediaDesignFixture.enabled ? MediaDesignFixture.image : nil, mediaVoice: MediaDesignFixture.enabled ? SyntheticSpeech.wav(seconds: 12, seed: 2) : nil, speechPreparationDelay: speechPreparationDelay))
        #if DEBUG
        if ProcessInfo.processInfo.arguments.contains("--reset-tool-defaults") { store.setAppTools(nil) }
        if ProcessInfo.processInfo.arguments.contains("--ui-test") { store.preferences.readAloud = false; store.preferences.autoSendVoice = false; store.preferences.showMessageStats = false; store.preferences.voice = nil; store.preferences.speed = 1; store.preferences.transcription = nil }
        #endif
        #if DEBUG
        if let index = ProcessInfo.processInfo.arguments.firstIndex(of: "--screen"), ProcessInfo.processInfo.arguments.indices.contains(index + 1) {
            switch ProcessInfo.processInfo.arguments[index + 1] {
            case "inbox": tab = 1
            case "automations": tab = 2
            case "media":
                if let session = SessionSummary.group([MockGatewayClient.mediaRun]).first { Task { await store.openSession(session) } }
            case "history":
                if let session = SessionSummary.group(MockGatewayClient.historyRuns).first { Task { await store.openSession(session) } }
            case "conversation": store.send("Help me make room for focused work this week.")
            default: break
            }
        }
        #endif
    }
    private func disconnect() {
        let connection = store.connection
        let signIn = store.isDemo ? nil : ConnectionVault.current()
        do { if !store.isDemo { try ConnectionVault.remove() } }
        catch { storageError = error.localizedDescription; return }
        PhonePush.signedOut(signIn)
        settings = false; store.disconnect(); tab = 0
        if let connection, connection.session != nil {
            Task {
                var request = URLRequest(url: connection.gateway.appending(path: "api/gateway/session/logout"))
                request.httpMethod = "POST"; connection.credential.apply(to: &request, write: true)
                _ = try? await PhoneTransport.makeSession().data(for: request)
            }
        }
    }
}
