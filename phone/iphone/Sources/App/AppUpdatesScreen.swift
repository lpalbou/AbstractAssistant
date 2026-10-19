import SwiftUI
import StoreKit
import AssistantKit

enum InstalledPhoneApp {
    static var metadata: AppUpdateInfo {
        let bundle = Bundle.main
        return AppUpdateInfo(version: bundle.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String,
                             build: bundle.object(forInfoDictionaryKey: "CFBundleVersion") as? String,
                             channel: bundle.bundleIdentifier?.hasSuffix(".iphone") == true ? .development : .unknown)
    }
    static func verified() async -> AppUpdateInfo {
        var info = metadata
        #if DEBUG
        // Fixtures never change distribution behavior in a Release/TestFlight installation.
        if ProcessInfo.processInfo.arguments.contains("--updates=testflight") { info.channel = .testFlight; return info }
        #endif
        guard info.channel != .development else { return info }
        if let result = try? await AppTransaction.shared, case .verified(let transaction) = result {
            if transaction.environment == .sandbox { info.channel = .testFlight }
            else if transaction.environment == .production { info.channel = .appStore; info.storeID = transaction.appID }
            else if transaction.environment == .xcode { info.channel = .development }
        }
        return info
    }
}

struct AppUpdatesScreen: View {
    @Environment(\.openURL) private var openURL
    @State private var info = InstalledPhoneApp.metadata
    @State private var openFailed = false
    var body: some View {
        List {
            Section {
                LabeledContent("Installed version", value: info.installedVersion).accessibilityIdentifier("updates.version")
                LabeledContent("Installed through", value: info.channelTitle)
                Button { check() } label: { Label(info.checkTitle, systemImage: "arrow.down.circle") }
                    .accessibilityIdentifier("updates.check")
                if openFailed {
                    Text(info.channel == .appStore ? "Couldn’t open the App Store. Open it from your Home Screen to check for updates." : "Couldn’t open TestFlight. Open it from your Home Screen, select AbstractAssistant, then tap Update if it is available.")
                        .font(.footnote).foregroundStyle(PhoneTheme.amber)
                }
            } footer: {
                Text(info.channel == .development ? "This copy was installed by a developer. Install a newer build through Xcode, or use your TestFlight invitation." : "Select AbstractAssistant in TestFlight or the App Store to see updates available to your account.")
            }
            if info.channel != .development {
                Section {
                    if info.channel == .testFlight || info.channel == .unknown {
                        Label("Managed by TestFlight", systemImage: "arrow.triangle.2.circlepath")
                        Text("Open TestFlight → AbstractAssistant → App Information → Automatic Updates. Turn it on to install new beta builds automatically.")
                            .font(.subheadline).foregroundStyle(PhoneTheme.secondary).accessibilityIdentifier("updates.automatic")
                        Link("TestFlight update help", destination: AppUpdateInfo.betaHelp)
                    }
                    if info.channel == .appStore || info.channel == .unknown {
                        Text("For an App Store copy, open iPhone Settings → Apps → App Store → App Updates to manage automatic updates.")
                            .font(.subheadline).foregroundStyle(PhoneTheme.secondary)
                        Link("App Store update help", destination: AppUpdateInfo.appStoreHelp)
                    }
                } header: { Text("Automatic updates") } footer: { Text("Automatic updates are managed in TestFlight or iPhone Settings.") }
            }
            Section("Release notes") {
                Link("iPhone version history", destination: URL(string: "https://github.com/lpalbou/AbstractAssistant/blob/main/phone/iphone/CHANGELOG.md")!)
            }
        }.scrollContentBackground(.hidden).background(PhoneTheme.ground).navigationTitle("Version & updates").navigationBarTitleDisplayMode(.inline)
            .task { info = await InstalledPhoneApp.verified() }
    }
    private func check() {
        openFailed = false
        openURL(info.destination) { accepted in openFailed = !accepted }
    }
}
