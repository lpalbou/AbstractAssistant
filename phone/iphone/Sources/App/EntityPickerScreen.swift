import SwiftUI
import AssistantKit
import PhoneGatewayClient

struct EntityPickerScreen: View {
    var canSwitch: Bool
    var blockedReason: String?
    var onSelect: (String?) -> Void
    @Environment(AssistantStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    @State private var search = ""
    private var matches: [EntitySummary] { store.entities.filter { search.isEmpty || $0.displayName.localizedCaseInsensitiveContains(search) } }
    var body: some View {
        NavigationStack {
            List {
                Section {
                    row(name: nil, title: "Assistant", detail: "Tasks and questions", symbol: "sparkle")
                }
                Section {
                    if store.loadingEntities && store.entities.isEmpty { ProgressView("Loading entities…") }
                    if let error = store.entitiesError {
                        Text(error).font(.footnote).foregroundStyle(PhoneTheme.amber)
                        Button("Try again") { Task { await store.loadEntities() } }
                    } else if store.entities.isEmpty && !store.loadingEntities {
                        Text("No entities yet").foregroundStyle(PhoneTheme.secondary)
                    }
                    ForEach(matches) { entity in
                        row(name: entity.name, title: entity.displayName, detail: entity.extra["error"]?.stringValue ?? entity.detail ?? "A continuing conversation", symbol: "person.crop.circle", available: entity.extra["error"] == nil)
                    }
                    if !search.isEmpty && matches.isEmpty && !store.entities.isEmpty { Text("No matching entities").foregroundStyle(PhoneTheme.secondary) }
                    NavigationLink { NewEntityScreen(onCreated: { onSelect($0.name) }) } label: { Label("New entity", systemImage: "plus") }
                        .disabled(!canSwitch).accessibilityIdentifier("entities.new")
                } header: { Text("Entities") } footer: {
                    Text(blockedReason ?? "Switching starts a new conversation. Entities keep their memory.")
                }.listRowBackground(PhoneTheme.surface)
            }
            .searchable(text: $search, prompt: "Find an entity")
            .scrollContentBackground(.hidden).background(PhoneTheme.ground)
            .navigationTitle("Who answers").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
            .task { await store.loadEntities() }.refreshable { await store.loadEntities() }
        }
    }
    private func row(name: String?, title: String, detail: String, symbol: String, available: Bool = true) -> some View {
        Button { onSelect(name) } label: {
            HStack(spacing: 12) {
                Image(systemName: symbol).font(.title3).foregroundStyle(name == nil ? PhoneTheme.mint : PhoneTheme.lavender).frame(width: 26)
                VStack(alignment: .leading, spacing: 3) { Text(title).foregroundStyle(PhoneTheme.ink); Text(detail).font(.caption).foregroundStyle(PhoneTheme.secondary) }
                Spacer(minLength: 8)
                if store.selectedEntity == name { Image(systemName: "checkmark").foregroundStyle(PhoneTheme.mint) }
            }.frame(minHeight: 42)
        }.disabled(!canSwitch || !available).accessibilityLabel("Talk with " + title)
            .accessibilityAddTraits(store.selectedEntity == name ? .isSelected : []).listRowBackground(PhoneTheme.surface)
    }
}

private struct NewEntityScreen: View {
    var onCreated: (EntitySummary) -> Void
    @Environment(AssistantStore.self) private var store
    @State private var name = ""
    @State private var checkedName = ""
    @State private var validation: EntityValidation?
    @State private var checking = false
    @State private var creating = false
    @State private var error: String?
    @State private var result: CreatedEntity?
    private var draft: EntityDraft { EntityDraft(name: name) }
    private var canCreate: Bool { draft.valid && checkedName == draft.name && validation?.ok == true && validation?.exists == false && !checking && !creating && result == nil }
    var body: some View {
        Form {
            if let result {
                Section {
                    Label(result.created ? "Entity created" : "Entity already exists", systemImage: "checkmark.circle").foregroundStyle(PhoneTheme.mint)
                    Text(result.entity.displayName).font(.headline)
                    ForEach(result.warnings, id: \.self) { Text($0).font(.footnote).foregroundStyle(PhoneTheme.amber) }
                    if !result.warnings.isEmpty { Text("The entity exists. Some setup needs attention in the gateway console.").font(.footnote) }
                    Button("Open conversation") { onCreated(result.entity) }
                }
            } else {
                Section {
                    TextField("e.g. Atlas", text: $name).textInputAutocapitalization(.words).autocorrectionDisabled().accessibilityIdentifier("entity.name")
                    if checking { ProgressView("Checking name…") }
                    if !name.isEmpty && !draft.valid { Text("Use up to 64 English letters (A–Z), numbers, spaces, hyphens or underscores; start with a letter or number.").font(.footnote).foregroundStyle(PhoneTheme.amber) }
                    if checkedName == draft.name, let validation {
                        if validation.exists { Text("This name is already in use. Choose its entity from the list, or use another name.").font(.footnote).foregroundStyle(PhoneTheme.amber) }
                        ForEach(validation.errors + validation.warnings, id: \.self) { Text($0).font(.footnote).foregroundStyle(PhoneTheme.amber) }
                    }
                } header: { Text("Name") } footer: { Text("Starts with the gateway’s default settings. Its identity and memory are permanent; it cannot be deleted.") }.listRowBackground(PhoneTheme.surface)
                if let error { Section { ErrorBanner(message: error); if checkedName != draft.name { Button("Try again") { Task { await validate() } } } }.listRowBackground(PhoneTheme.surface) }
                Section {
                    Button { Task { await create() } } label: {
                        HStack { Spacer(); if creating { ProgressView() }; Text(creating ? "Creating…" : "Create entity").fontWeight(.semibold).foregroundStyle(canCreate || creating ? PhoneTheme.mint : PhoneTheme.secondary); Spacer() }.frame(minHeight: 30)
                    }.disabled(!canCreate).accessibilityIdentifier("entity.create")
                }.listRowBackground(PhoneTheme.surface)
            }
        }
        .disabled(creating).scrollDismissesKeyboard(.interactively)
        .scrollContentBackground(.hidden).background(PhoneTheme.ground)
        .navigationTitle("New entity").navigationBarTitleDisplayMode(.inline)
        .navigationBarBackButtonHidden(creating).interactiveDismissDisabled(creating)
        .task(id: name) { await validate() }
    }
    private func validate() async {
        validation = nil; checkedName = ""; error = nil; checking = false
        let draft = draft
        guard draft.valid, let client = store.client else { return }
        let context = store.contextID; checking = true
        do {
            try await Task.sleep(for: .milliseconds(350))
            let answer = try await client.validateEntity(draft)
            guard !Task.isCancelled, context == store.contextID, draft.name == self.draft.name else { return }
            validation = answer; checkedName = draft.name; checking = false
        } catch {
            guard !Task.isCancelled, context == store.contextID, draft.name == self.draft.name else { return }
            checking = false; self.error = error.localizedDescription
            if error as? GatewayError == .unauthorized { store.authenticationExpired() }
        }
    }
    private func create() async {
        guard canCreate, let client = store.client else { return }
        let context = store.contextID, draft = draft; creating = true; error = nil
        defer { creating = false }
        do {
            let created = try await client.createEntity(draft)
            guard context == store.contextID else { return }
            store.rememberEntity(created.entity)
            if created.created && created.warnings.isEmpty { onCreated(created.entity) }
            else { result = created }
        } catch {
            guard context == store.contextID else { return }
            self.error = error.localizedDescription + " Check the entity list before trying again; creation may have completed."
            if error as? GatewayError == .unauthorized { store.authenticationExpired() }
        }
    }
}
