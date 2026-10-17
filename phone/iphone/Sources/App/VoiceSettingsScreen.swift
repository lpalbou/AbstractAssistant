import SwiftUI
import AssistantKit
import AbstractGatewayClient

struct VoiceSettingsScreen: View {
    @Environment(AssistantStore.self) private var store
    @State private var catalog: VoiceCatalog?
    @State private var error: String?
    @State private var voice = VoiceController()
    var body: some View {
        @Bindable var prefs = store.preferences
        List {
            Section {
                Toggle("Read replies aloud", isOn: $prefs.readAloud).accessibilityIdentifier("voice.readAloud")
            } footer: { Text("Automatically read new completed replies. Your conversation history stays quiet.") }
            Section("Speaking voice") {
                Picker("Voice", selection: $prefs.voice) {
                    Text("Gateway default" + (catalog?.defaultVoice.map { " · " + $0 } ?? "")).tag(VoiceChoice?.none)
                    ForEach(catalog?.voices ?? []) { v in Text(v.label).tag(Optional(v)) }
                }.pickerStyle(.navigationLink)
                if let selected = prefs.voice, !(catalog?.voices.contains(selected) ?? true) { Text("Saved voice is currently unavailable. Choose another voice or Gateway default.").font(.footnote).foregroundStyle(PhoneTheme.amber) }
                Button(voice.speaking ? "Stop preview" : "Preview voice") {
                    guard let client = store.client else { return }
                    if voice.speaking { voice.stop() }
                    else { voice.read("Hello, I’m AbstractAssistant. What’s on your mind?", client: client, scope: .run(PhoneSession.owner(store.sessionID)), choice: prefs.voice) }
                }
                if let message = voice.error { Text(message).foregroundStyle(PhoneTheme.amber) }
            }
            Section {
                Picker("Transcription model", selection: $prefs.transcription) {
                    Text("Gateway default" + (catalog?.defaultTranscription.map { " · " + $0 } ?? "")).tag(TranscriptionChoice?.none)
                    ForEach(catalog?.transcription ?? []) { t in Text(t.provider + " · " + t.model).tag(Optional(t)) }
                }.pickerStyle(.navigationLink)
                if let selected = prefs.transcription, !(catalog?.transcription.contains(selected) ?? true) { Text("Saved transcription model is currently unavailable. Choose another model or Gateway default.").font(.footnote).foregroundStyle(PhoneTheme.amber) }
            } header: { Text("Listening") } footer: { Text("Record, then review the transcript before sending. Larger transcription models can take longer.") }
            Section { Text("These choices apply to this account on this iPhone. They do not change gateway defaults. Entities keep their own speaking voice.").font(.footnote).foregroundStyle(PhoneTheme.secondary) }
            if let error { Section { ErrorBanner(message: error); Button("Try again") { Task { await load() } } } }
            if catalog == nil && error == nil { ProgressView("Loading voices…") }
        }.navigationTitle("Voice & reading").scrollContentBackground(.hidden).background(PhoneTheme.ground)
            .task { voice.onUnauthorized = { store.authenticationExpired() }; await load() }.onDisappear { voice.stop() }
    }
    private func load() async {
        guard let client = store.client else { return }; let context = store.contextID; error = nil
        do { let result = try await client.voiceCatalog(); guard context == store.contextID else { return }; catalog = result } catch { guard context == store.contextID else { return }; self.error = error.localizedDescription; if error as? GatewayError == .unauthorized { store.authenticationExpired() } }
    }
}

struct WorkflowSettingsScreen: View {
    @Environment(AssistantStore.self) private var store
    @State private var row: JSONValue?
    @State private var selected = ""
    @State private var error: String?
    @State private var saving = false
    @State private var saved = false
    private var choices: [JSONValue] { if case .array(let v)? = row?["choices"] { return v }; return [] }
    var body: some View {
        List {
            Section {
                Picker("Assistant workflow", selection: $selected) {
                    Text(row?["gateway_default_label"]?.stringValue ?? "Gateway default").tag("")
                    ForEach(Array(choices.enumerated()), id: \.offset) { _, c in Text(c["label"]?.stringValue ?? c["name"]?.stringValue ?? "Workflow").tag(c["value"]?.stringValue ?? "") }
                }.pickerStyle(.inline).disabled(saving || row == nil || !store.canSend)
            } footer: { Text("Changes the Assistant workflow for your account on every device. Applies to your next message. Other apps and your gateway’s default are unchanged.") }
            if let reason = row?["reason"]?.stringValue { Text(reason).foregroundStyle(PhoneTheme.amber) }
            if !store.canSend { Text("Finish or stop the current run before changing workflows.").font(.footnote) }
            if let error { ErrorBanner(message: error) }
            Button(saving ? "Saving…" : "Save workflow") { Task { await save() } }.disabled(saving || row == nil || !store.canSend)
            if saved { Label("Saved for your account", systemImage: "checkmark.circle").foregroundStyle(PhoneTheme.mint) }
            if row == nil { Button("Reload workflows") { Task { await load() } } }
        }.navigationTitle("Workflow").scrollContentBackground(.hidden).background(PhoneTheme.ground).task { await load() }
    }
    private func apply(_ v: JSONValue) {
        guard case .array(let apps)? = v["apps"] else { return }
        row = apps.first { $0["interface"]?.stringValue == "abstractassistant.agent.v1" }; selected = row?["value"]?.stringValue ?? ""
    }
    private func load() async {
        guard let client = store.client else { return }; let context = store.contextID
        do { let result = try await client.accountPreferences(); guard context == store.contextID else { return }; apply(result); error = nil } catch { if context == store.contextID { fail(error) } }
    }
    private func save() async {
        guard let client = store.client, store.canSend else { return }; let context = store.contextID; saving = true; saved = false; error = nil
        defer { saving = false }
        do { let result = try await client.setAssistantWorkflow(selected.isEmpty ? nil : selected); guard context == store.contextID else { return }; apply(result); saved = true } catch { if context == store.contextID { fail(error) } }
    }
    private func fail(_ e: Error) { error = e.localizedDescription; if e as? GatewayError == .unauthorized { store.authenticationExpired() } }
}
