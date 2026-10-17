import SwiftUI
import AssistantKit

struct SettingsScreen: View {
    var onDisconnect: () -> Void
    var notice: String?
    @Environment(AssistantStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    @State private var confirm = false
    var body: some View {
        NavigationStack {
            List {
                Section("Assistant") {
                    NavigationLink("Voice & reading") { VoiceSettingsScreen() }
                    NavigationLink("Workflow") { WorkflowSettingsScreen() }
                }
                Section("Account") {
                    if let notice { ErrorBanner(message: notice) }
                    LabeledContent("Signed in as", value: store.connection?.user ?? "Sample account")
                    DisclosureGroup("Connection") {
                        if let gateway = store.connection?.gateway { Text(gateway.absoluteString).font(.footnote).textSelection(.enabled) }
                        else { Text("Demo · no requests leave this iPhone").font(.footnote).foregroundStyle(PhoneTheme.mint) }
                        if let date = store.lastRefresh { LabeledContent("Last checked") { Text(date, style: .relative).foregroundStyle(PhoneTheme.secondary) } }
                        Button("Refresh now") { Task { await store.refresh() } }.disabled(store.isRefreshing)
                        if let url = store.connection?.gateway.appending(path: "console") { Link("Open gateway console", destination: url) }
                    }
                }
                Section("AbstractAssistant · iPhone preview") {
                    Link("AbstractFramework", destination: URL(string: "https://abstractframework.ai")!)
                    Link("Source & community", destination: URL(string: "https://github.com/lpalbou/AbstractAssistant")!)
                    Link("Get in touch", destination: URL(string: "mailto:contact@abstractframework.ai")!)
                    Text("Version 0.5.0 · iOS 26 or later").font(.caption).foregroundStyle(PhoneTheme.secondary)
                }
                Section { Button(store.isDemo ? "Leave demo" : "Disconnect this iPhone", role: .destructive) { confirm = true } }
            }.scrollContentBackground(.hidden).background(PhoneTheme.ground).navigationTitle("Settings").navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
                .confirmationDialog(store.isDemo ? "Leave the demo?" : "Disconnect this iPhone?", isPresented: $confirm, titleVisibility: .visible) {
                    Button("Disconnect", role: .destructive, action: onDisconnect)
                } message: { Text("Your gateway conversations and automations are kept.") }
        }
    }
}
