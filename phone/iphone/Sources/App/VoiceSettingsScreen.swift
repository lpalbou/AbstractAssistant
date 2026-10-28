import SwiftUI
import AssistantKit
import AbstractGatewayClient

struct VoiceSettingsScreen: View {
    @Environment(AssistantStore.self) private var store
    @Environment(\.scenePhase) private var scenePhase
    @State private var catalog: VoiceCatalog?
    @State private var error: String?
    @State private var sample = VoiceController()
    var body: some View {
        @Bindable var prefs = store.preferences
        List {
            Section {
                Toggle("Send voice messages automatically", isOn: $prefs.autoSendVoice)
                    .accessibilityIdentifier("voice.autoSend")
            } header: { Text("Voice messages") } footer: {
                Text(prefs.autoSendVoice ? "Send after you stop speaking. Your separate typed draft stays saved." : "Review and edit your transcription in the text composer, then tap Send.")
            }.listRowBackground(PhoneTheme.surface)
            Section { Toggle("Read replies aloud", isOn: $prefs.readAloud).accessibilityIdentifier("voice.readAloud") }
                footer: { Text("Read new replies automatically.") }.listRowBackground(PhoneTheme.surface)
            if let catalog {
                Section {
                    NavigationLink { VoiceChoicesScreen(catalog: catalog, onCatalog: { self.catalog = $0 }) } label: {
                        LabeledContent("Voice", value: Self.title(prefs.voice, in: catalog))
                    }.accessibilityIdentifier("voice.choices")
                    if let selected = prefs.voice, catalog.entry(for: selected) == nil {
                        Text("This voice is unavailable. Choose another.").font(.footnote).foregroundStyle(PhoneTheme.amber)
                    } else if let summary = catalog.entry(for: prefs.voice)?.summary {
                        Text(summary).font(.footnote).foregroundStyle(PhoneTheme.secondary).accessibilityIdentifier("voice.description")
                    }
                    NavigationLink { CreateVoiceScreen(onCatalog: { self.catalog = $0 }) } label: {
                        Label("Create a voice", systemImage: "waveform.badge.plus")
                    }.accessibilityIdentifier("voice.create")
                }
                .listRowBackground(PhoneTheme.surface)
                Section("Speed") {
                    Picker("Speaking speed", selection: $prefs.speed) {
                        ForEach(PhonePreferences.speeds, id: \.self) { speed in Text(speed == 1 ? "1×" : speed.formatted() + "×").tag(speed) }
                    }.pickerStyle(.segmented).accessibilityIdentifier("voice.speed")
                    if sample.speaking || sample.error != nil { VoiceSampleStatus(voice: sample) }
                }.listRowBackground(PhoneTheme.surface)
                Section {
                    NavigationLink { TranscriptionChoicesScreen(catalog: catalog) } label: {
                        LabeledContent("Speech recognition", value: prefs.transcription?.model ?? "Gateway default")
                    }.accessibilityIdentifier("voice.transcription")
                    if let selected = prefs.transcription, !catalog.transcription.contains(selected) {
                        Text("This model is unavailable. Choose another.").font(.footnote).foregroundStyle(PhoneTheme.amber)
                    }
                } footer: { Text("Saved for this account on this iPhone. Entities keep their own voice.") }.listRowBackground(PhoneTheme.surface)
            } else if let error {
                Section { ErrorBanner(message: error); Button("Try again") { Task { await load() } } }
            } else { Section { ProgressView("Loading voices…") } }
        }
        .listRowSpacing(4).listStyle(.insetGrouped)
        .navigationTitle("Voice").navigationBarTitleDisplayMode(.inline)
        .scrollContentBackground(.hidden).background(PhoneTheme.ground)
        .task(id: store.contextID) { sample.onUnauthorized = { store.authenticationExpired() }; await load() }
        .onChange(of: prefs.speed) { _, _ in preview() }
        .onChange(of: store.contextID) { _, _ in sample.stop() }
        .onChange(of: scenePhase) { _, phase in if phase != .active { sample.stop() } }
        .onDisappear { sample.stop() }
    }
    /// "Camille · French": the chosen voice and its language (the gateway's default: "Gateway default").
    static func title(_ choice: VoiceChoice?, in catalog: VoiceCatalog) -> String {
        guard let choice else { return "Gateway default" }
        let entry = catalog.entry(for: choice)
        return [entry?.choice.label ?? choice.label, entry?.language.map(VoiceLibrary.languageName)].compactMap { $0 }.joined(separator: " · ")
    }

    private func preview() {
        guard let client = store.client, scenePhase == .active else { return }
        sample.read("Hello, I’m AbstractAssistant.", client: client, scope: .run(PhoneSession.owner(store.sessionID)), choice: store.preferences.voice, speed: store.preferences.speed)
    }
    private func load() async {
        guard let client = store.client else { return }; let context = store.contextID; error = nil; catalog = nil; sample.stop()
        do { let result = try await client.voiceCatalog(); guard context == store.contextID, !Task.isCancelled else { return }; catalog = result }
        catch { guard context == store.contextID, !Task.isCancelled else { return }; self.error = error.localizedDescription; if error as? GatewayError == .unauthorized { store.authenticationExpired() } }
    }
}

/// The speaking voices, in groups (your voices, the engine's, the shared ones) with each voice's
/// language, a "Voices that speak…" filter when the catalog speaks several, the chosen voice's
/// description, and rename / delete on the person's own voices (shared voices are read-only).
private struct VoiceChoicesScreen: View {
    @State var catalog: VoiceCatalog
    var onCatalog: (VoiceCatalog) -> Void
    @Environment(AssistantStore.self) private var store
    @Environment(\.scenePhase) private var scenePhase
    @State private var sample = VoiceController()
    @State private var chosen: String?
    @State private var language = ""
    @State private var renaming: VoiceEntry?
    @State private var newName = ""
    @State private var deleting: VoiceEntry?
    @State private var working = false
    @State private var error: String?
    @State private var note: String?

    private var languages: [String] { VoiceLibrary.languages(of: catalog.entries) }

    var body: some View {
        List {
            if languages.count > 1 {
                Section {
                    Picker("Voices that speak…", selection: $language) {
                        Text("Any language").tag("")
                        ForEach(languages, id: \.self) { Text(VoiceLibrary.languageName($0)).tag($0) }
                    }.accessibilityIdentifier("voice.language")
                }.listRowBackground(PhoneTheme.surface)
            }
            Section { choice(nil, title: "Gateway default", detail: catalog.defaultVoice, summary: nil) }
                .listRowBackground(PhoneTheme.surface)
            ForEach(VoiceLibrary.grouped(catalog.entries, speaking: language, keep: store.preferences.voice), id: \.group) { section in
                Section {
                    ForEach(section.entries) { entry in
                        choice(entry.choice, title: entry.choice.label, detail: detail(entry), summary: entry.summary)
                            .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                                if entry.isOwn {
                                    Button(role: .destructive) { deleting = entry } label: { Label("Delete", systemImage: "trash") }
                                    Button { newName = entry.choice.label; renaming = entry } label: { Label("Rename", systemImage: "pencil") }.tint(PhoneTheme.lavender)
                                }
                            }
                    }
                } header: { Text(section.group.title) } footer: {
                    if section.group == .yours { Text("Swipe left on one of your voices to rename or delete it.") }
                    else if section.group == .shared { Text("Shared with everyone on this gateway. Only an administrator can change them.") }
                }
            }
            Section {
                NavigationLink { CreateVoiceScreen(onCatalog: { catalog = $0; onCatalog($0) }) } label: {
                    Label("Create a voice", systemImage: "waveform.badge.plus")
                }.accessibilityIdentifier("voice.choices.create")
            } footer: { Text("Tap a voice to hear it.") }.listRowBackground(PhoneTheme.surface)
            if let note { Section { Text(note).font(.footnote).foregroundStyle(PhoneTheme.mint) }.listRowBackground(PhoneTheme.surface) }
            if let error { Section { ErrorBanner(message: error) { self.error = nil } }.accessibilityIdentifier("voice.library.error") }
            if working { Section { ProgressView() } }
        }
        // The sample's status and Stop stay in view however far the list is scrolled.
        .safeAreaInset(edge: .bottom) {
            if sample.speaking || sample.error != nil {
                VoiceSampleStatus(voice: sample).padding(.horizontal, 16).padding(.vertical, 8)
                    .background(PhoneTheme.surface, in: RoundedRectangle(cornerRadius: 16)).padding(.horizontal, 12)
            }
        }
        .navigationTitle("Speaking voice").navigationBarTitleDisplayMode(.inline)
        .scrollContentBackground(.hidden).background(PhoneTheme.ground)
        .alert("Rename voice", isPresented: Binding(get: { renaming != nil }, set: { if !$0 { renaming = nil } })) {
            TextField("Name", text: $newName).accessibilityIdentifier("voice.rename.field")
            Button("Cancel", role: .cancel) { renaming = nil }
            Button("Save") { if let entry = renaming { rename(entry, to: newName) } }
        }
        .confirmationDialog("Delete “\(deleting?.choice.label ?? "")”?", isPresented: Binding(get: { deleting != nil }, set: { if !$0 { deleting = nil } }), titleVisibility: .visible) {
            Button("Delete voice", role: .destructive) { if let entry = deleting { delete(entry) } }
        } message: { Text("The voice and its recording are deleted from your gateway.") }
        .onAppear { sample.onUnauthorized = { store.authenticationExpired() } }
        .onChange(of: catalog.entries.count) { _, _ in if !languages.contains(language) { language = "" } }
        .onChange(of: store.contextID) { _, _ in sample.stop() }
        .onChange(of: scenePhase) { _, phase in if phase != .active { sample.stop() } }
        .onDisappear { sample.stop() }
    }

    private func detail(_ entry: VoiceEntry) -> String? {
        let duplicate = catalog.entries.filter { $0.choice.label == entry.choice.label }.count > 1
        let parts = [entry.language.map(VoiceLibrary.languageName), duplicate ? entry.choice.provider : entry.choice.gender].compactMap { $0 }.filter { !$0.isEmpty }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }

    private func choice(_ value: VoiceChoice?, title: String, detail: String?, summary: String?) -> some View {
        let selected = value.map { catalog.entry(for: store.preferences.voice)?.id == $0.id } ?? (store.preferences.voice == nil)
        return Button {
            store.preferences.voice = value; chosen = value?.id ?? "default"
            guard let client = store.client, scenePhase == .active else { return }
            sample.read("Hello, I’m AbstractAssistant.", client: client, scope: .run(PhoneSession.owner(store.sessionID)), choice: value, speed: store.preferences.speed)
        } label: {
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(title).foregroundStyle(PhoneTheme.ink)
                    if let detail, !detail.isEmpty { Text(detail).font(.caption).foregroundStyle(PhoneTheme.secondary) }
                    if selected, let summary { Text(summary).font(.caption).foregroundStyle(PhoneTheme.secondary).accessibilityIdentifier("voice.choice.description") }
                }
                Spacer(minLength: 8)
                if sample.preparing && chosen == (value?.id ?? "default") { ProgressView().accessibilityLabel("Loading sample") }
                else if selected { Image(systemName: "checkmark").foregroundStyle(PhoneTheme.mint) }
            }.frame(minHeight: 36)
        }.accessibilityAddTraits(selected ? .isSelected : []).listRowBackground(PhoneTheme.surface)
    }

    private func rename(_ entry: VoiceEntry, to name: String) {
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        renaming = nil
        guard !trimmed.isEmpty, trimmed != entry.choice.label else { return }
        change { client in
            try await client.renameVoice(id: entry.voiceID, name: trimmed)
            if store.preferences.voice?.id == entry.id { store.preferences.voice?.label = trimmed }
            return "Renamed to “\(trimmed)”."
        }
    }

    private func delete(_ entry: VoiceEntry) {
        deleting = nil
        change { client in
            try await client.deleteVoice(id: entry.voiceID)
            if store.preferences.voice?.id == entry.id {
                store.preferences.voice = nil
                return "“\(entry.choice.label)” is deleted. Your assistant speaks with the gateway’s default voice."
            }
            return "“\(entry.choice.label)” is deleted."
        }
    }

    /// A library change, then the catalog read again; a refusal shows the gateway's sentence.
    private func change(_ action: @escaping (any GatewayClient) async throws -> String) {
        guard let client = store.client else { return }
        let context = store.contextID
        working = true; error = nil; note = nil
        Task {
            do {
                let said = try await action(client)
                let fresh = try await client.voiceCatalog()
                guard context == store.contextID else { return }
                catalog = fresh; onCatalog(fresh); note = said
            } catch {
                guard context == store.contextID else { return }
                self.error = error.localizedDescription
                if error as? GatewayError == .unauthorized { store.authenticationExpired() }
            }
            working = false
        }
    }
}

private struct VoiceSampleStatus: View {
    let voice: VoiceController
    var body: some View {
        if let error = voice.error { Text(error).font(.footnote).foregroundStyle(PhoneTheme.amber) }
        if voice.speaking {
            HStack {
                if voice.preparing { ProgressView() } else { Image(systemName: "waveform").foregroundStyle(PhoneTheme.mint) }
                Text(voice.preparing ? "Loading sample…" : "Playing sample").font(.footnote).foregroundStyle(PhoneTheme.secondary)
                Spacer()
                Button { voice.stop() } label: { Image(systemName: "stop.circle").font(.title3).frame(width: 44, height: 44) }.accessibilityLabel("Stop sample")
            }.accessibilityIdentifier("voice.sample")
        }
    }
}

private struct TranscriptionChoicesScreen: View {
    let catalog: VoiceCatalog
    @Environment(AssistantStore.self) private var store
    var body: some View {
        List {
            choice(nil, title: "Gateway default", detail: catalog.defaultTranscription)
            ForEach(catalog.transcription) { model in choice(model, title: model.model, detail: model.provider + Self.hint(model.model)) }
        }
        .navigationTitle("Speech recognition").navigationBarTitleDisplayMode(.inline)
        .scrollContentBackground(.hidden).background(PhoneTheme.ground)
    }
    private func choice(_ value: TranscriptionChoice?, title: String, detail: String?) -> some View {
        let selected = store.preferences.transcription == value
        return Button { store.preferences.transcription = value } label: {
            HStack {
                VStack(alignment: .leading, spacing: 3) { Text(title).foregroundStyle(PhoneTheme.ink); if let detail { Text(detail).font(.caption).foregroundStyle(PhoneTheme.secondary) } }
                Spacer(); if selected { Image(systemName: "checkmark").foregroundStyle(PhoneTheme.mint) }
            }.frame(minHeight: 36)
        }.accessibilityAddTraits(selected ? .isSelected : []).listRowBackground(PhoneTheme.surface)
    }
    private static func hint(_ model: String) -> String {
        switch model { case "tiny": " · Fastest"; case "base": " · Fast"; case "small": " · Balanced"; case "medium": " · Accurate"; case "large", "large-v3": " · Most accurate"; case "turbo", "large-v3-turbo": " · Accurate, faster"; default: "" }
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
