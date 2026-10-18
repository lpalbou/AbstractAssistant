import SwiftUI
import AssistantKit
import AbstractGatewayClient

@main struct AbstractAssistantPhoneApp: App {
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
                    Tab("Inbox", systemImage: "tray", value: 1) { InboxScreen() }.badge(store.waits.count)
                    Tab("Automations", systemImage: "clock.arrow.circlepath", value: 2) { AutomationsScreen() }
                }
                .sheet(isPresented: $settings) { SettingsScreen(onDisconnect: disconnect, notice: storageError) }
            } else { WelcomeScreen(onConnect: { connect($0) }, onDemo: demo, notice: storageError ?? store.error) }
        }
        .environment(store)
        .preferredColorScheme(.dark).tint(PhoneTheme.lavender)
        .foregroundStyle(PhoneTheme.ink)
        .task {
            store.onUnauthorized = { do { try ConnectionVault.remove() } catch { storageError = error.localizedDescription } }
            #if DEBUG
            if ProcessInfo.processInfo.arguments.contains("--demo") { demo(); return }
            #endif
            do { if let saved = try ConnectionVault.read() { connect(saved, persist: false) } }
            catch { storageError = error.localizedDescription }
        }
        .onChange(of: scenePhase, initial: true) { _, phase in store.setForeground(phase == .active) }
    }
    private func connect(_ connection: SavedConnection, persist: Bool = true) {
        do {
            if persist { try ConnectionVault.save(connection) }
            storageError = nil
            store.connect(connection, client: LiveGatewayClient(baseURL: connection.gateway, credential: connection.credential, session: PhoneTransport.makeSession()))
        } catch { storageError = error.localizedDescription }
    }
    private func demo() {
        #if DEBUG
        let emptyAutomations = ProcessInfo.processInfo.arguments.contains("--empty-automations")
        #else
        let emptyAutomations = false
        #endif
        store.connect(nil, client: MockGatewayClient(emptyAutomations: emptyAutomations))
        #if DEBUG
        if ProcessInfo.processInfo.arguments.contains("--ui-test") { store.preferences.readAloud = false; store.preferences.showMessageStats = false; store.preferences.voice = nil; store.preferences.speed = 1; store.preferences.transcription = nil }
        #endif
        #if DEBUG
        if let index = ProcessInfo.processInfo.arguments.firstIndex(of: "--screen"), ProcessInfo.processInfo.arguments.indices.contains(index + 1) {
            switch ProcessInfo.processInfo.arguments[index + 1] {
            case "inbox": tab = 1
            case "automations": tab = 2
            case "conversation": store.send("Help me make room for focused work this week.")
            default: break
            }
        }
        #endif
    }
    private func disconnect() {
        let connection = store.connection
        do { if !store.isDemo { try ConnectionVault.remove() } }
        catch { storageError = error.localizedDescription; return }
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
