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
                Section("Your connection") {
                    if let notice { ErrorBanner(message: notice) }
                    LabeledContent("Account", value: store.connection?.user ?? "Sample account")
                    if let gateway = store.connection?.gateway { Text(gateway.absoluteString).font(.footnote).textSelection(.enabled) }
                    else { Text("Demo · no requests leave this iPhone").font(.footnote).foregroundStyle(PhoneTheme.mint) }
                    if let date = store.lastRefresh { LabeledContent("Last checked") { Text(date, style: .relative).foregroundStyle(PhoneTheme.secondary) } }
                    Button("Refresh now") { Task { await store.refresh() } }.disabled(store.isRefreshing)
                    if let url = store.connection?.gateway.appending(path: "console") { Link("Open gateway console", destination: url) }
                }
                Section("Assistant") {
                    NavigationLink("Voice & reading") { VoiceSettingsScreen() }
                    NavigationLink("Workflow") { WorkflowSettingsScreen() }
                }
                Section("Made for a little less friction") {
                    Text("Your conversations, tools, automations and model choices live on your gateway. This phone follows your account’s Assistant workflow preference.")
                    Text("Updates are checked while the app is open. Runs and automations keep going on your gateway when you leave. Open the app again to catch up.")
                    Text("Hold the orb to speak. Release for a three-second countdown, then your gateway transcribes and sends the message automatically. Touch the orb during the countdown to cancel; no audio is uploaded before it ends. Temporary audio is removed after use.")
                }.font(.footnote).foregroundStyle(PhoneTheme.secondary)
                Section("AbstractAssistant · iPhone preview") {
                    Link("AbstractFramework", destination: URL(string: "https://abstractframework.ai")!)
                    Link("Source & community", destination: URL(string: "https://github.com/lpalbou/AbstractAssistant")!)
                    Link("Get in touch", destination: URL(string: "mailto:contact@abstractframework.ai")!)
                    Text("Version 0.3.1 · iOS 26 or later").font(.caption).foregroundStyle(PhoneTheme.secondary)
                }
                Section { Button(store.isDemo ? "Leave demo" : "Disconnect this iPhone", role: .destructive) { confirm = true } }
            }.scrollContentBackground(.hidden).background(PhoneTheme.ground).navigationTitle("Your space").navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
                .confirmationDialog(store.isDemo ? "Leave the demo?" : "Disconnect this iPhone?", isPresented: $confirm, titleVisibility: .visible) {
                    Button("Disconnect", role: .destructive, action: onDisconnect)
                } message: { Text("Your gateway conversations and automations are kept.") }
        }
    }
}
