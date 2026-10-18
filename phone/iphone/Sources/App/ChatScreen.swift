import SwiftUI
import PhotosUI
import UniformTypeIdentifiers
import QuickLook
import AssistantKit
import AbstractGatewayClient

struct ChatScreen: View {
    var openSettings: () -> Void
    @Environment(AssistantStore.self) private var store
    @Environment(\.scenePhase) private var scenePhase
    @State private var draft = ""
    @State private var history = false
    @State private var choosingEntity = false
    @State private var showWait: Wait?
    @State private var voice = VoiceController.forApp()
    @State private var voiceOrigin: (UUID, String)?
    @State private var voiceTask: Task<Void, Never>?
    @State private var attachments = AttachmentsController()
    @State private var importing = false
    @State private var photoLibrary = false
    @State private var pickedMedia: PhotosPickerItem?
    @State private var camera: CaptureMode?
    @State private var showFiles = false
    @State private var showTools = false
    @State private var mediaTask: Task<Void, Never>?
    @State private var mediaLoading = false
    @State private var mediaGeneration = UUID()
    @State private var pickerOrigin: (UUID, String)?
    private enum CaptureMode: String, Identifiable { case photo, video; var id: String { rawValue } }
    @State private var composing = false
    @FocusState private var typing: Bool

    var body: some View {
        NavigationStack {
            ScrollViewReader { scroll in
                ScrollView {
                    VStack(alignment: .leading, spacing: 24) {
                        if let message = store.error, message != store.activityFailure, store.activityIssue?.contains(message) != true { ErrorBanner(message: message, dismiss: store.dismissError) }
                        if let message = attachments.error { ErrorBanner(message: message, dismiss: { attachments.error = nil }) }
                        if let message = voice.error { ErrorBanner(message: message, dismiss: { voice.error = nil }) }
                        if store.messages.isEmpty { emptyState }
                        ForEach(store.messages) { message in messageView(message) }
                        if store.activityState != .idle || store.phase != .ready || store.isStopping { RunActivityPanel { showWait = $0 } }
                        else if store.isRestoring || store.isOpening { ProgressView("Opening your conversation…").padding(.vertical, 28).frame(maxWidth: .infinity) }
                        Color.clear.frame(height: 1).id("bottom")
                    }.padding(22)
                }
                .scrollDismissesKeyboard(.interactively)
                .onChange(of: store.messages.last?.text) { _, _ in withAnimation(.easeOut(duration: 0.2)) { scroll.scrollTo("bottom", anchor: .bottom) } }
            }
            .background(PhoneTheme.ground)
            .sheet(isPresented: $showTools) { ConversationToolsScreen() }
            .task(id: store.preferences.showMessageStats) { await store.loadMessageStats() }
            .background(OutsideInputDismissal(focused: typing, dismiss: { typing = false; composing = false }))
            .navigationTitle(store.conversationTitle).navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .principal) {
                    HStack(spacing: 8) {
                        Button { typing = false; composing = false; cancelVoice(); choosingEntity = true } label: {
                            HStack(spacing: 6) { NavigationCaption(title: store.conversationTitle, demo: store.isDemo); Image(systemName: "chevron.down").font(.caption2.weight(.semibold)) }
                                .lineLimit(1)
                        }.accessibilityLabel("Choose who answers").accessibilityValue(store.conversationTitle)
                        Button { typing = false; composing = false; cancelVoice(); showTools = true } label: {
                            Image(systemName: "wrench.and.screwdriver").font(.subheadline)
                                .frame(width: 44, height: 44).contentShape(Rectangle())
                        }.accessibilityLabel("Tools").accessibilityIdentifier("chat.tools")
                    }
                }
                ToolbarItem(placement: .topBarLeading) { Button { typing = false; composing = false; cancelVoice(); history = true } label: { Image(systemName: "rectangle.stack") }.accessibilityLabel("Conversations").disabled(attachments.busy || mediaLoading || !attachments.pending.isEmpty) }
                ToolbarItem(placement: .topBarTrailing) {
                    Menu {
                        Button("Conversation files", systemImage: "folder") { typing = false; composing = false; cancelVoice(); showFiles = true }
                        Button("New conversation", systemImage: "square.and.pencil") { typing = false; composing = false; cancelVoice(); store.newConversation(entity: store.selectedEntity) }.disabled(!store.canSend || attachments.busy || mediaLoading || !attachments.pending.isEmpty)
                        Button("Settings", systemImage: "slider.horizontal.3") { typing = false; composing = false; cancelVoice(); openSettings() }.disabled(attachments.busy || mediaLoading || !attachments.pending.isEmpty)
                    } label: { Image(systemName: "ellipsis") }.accessibilityLabel("More options")
                }
            }
            .safeAreaInset(edge: .bottom, spacing: 0) { composer }
            .sheet(isPresented: $choosingEntity) {
                EntityPickerScreen(canSwitch: store.canSend && !attachments.busy && !mediaLoading && attachments.pending.isEmpty,
                    blockedReason: !attachments.pending.isEmpty ? "Send or remove your attachments before switching." : !store.canSend ? "Finish or stop the current reply before switching." : nil) { entity in
                    guard store.canSend, !attachments.busy, !mediaLoading, attachments.pending.isEmpty else { return }
                    cancelVoice(); cancelMedia(); store.newConversation(entity: entity); choosingEntity = false
                }
            }
            .sheet(isPresented: $history) { ConversationsSheet { history = false } }
            .sheet(item: $showWait) { wait in WaitDetailScreen(wait: wait) }
            .sheet(isPresented: $showFiles) { filesSheet }
            .fileImporter(isPresented: $importing, allowedContentTypes: [.item]) { result in
                switch result { case .success(let url): stage(url, origin: pickerOrigin); case .failure(let error): attachments.error = error.localizedDescription }
            }
            .photosPicker(isPresented: $photoLibrary, selection: $pickedMedia, matching: .any(of: [.images, .videos]))
            .onChange(of: pickedMedia) { _, item in
                guard let item, let origin = pickerOrigin else { return }; let context = origin.0, session = origin.1
                guard context == store.contextID, session == store.sessionID else { pickedMedia = nil; return }
                mediaGeneration = UUID(); let operation = mediaGeneration; mediaLoading = true
                mediaTask?.cancel()
                mediaTask = Task {
                    defer { if operation == mediaGeneration { mediaLoading = false } }
                    do {
                        if let media = try await item.loadTransferable(type: ImportedMedia.self) {
                            guard !Task.isCancelled, context == store.contextID, session == store.sessionID else { ImportedMedia.remove(media.url); return }
                            stage(media.url, owned: true, origin: origin)
                        }
                    } catch { if context == store.contextID && !(error is CancellationError) { attachments.error = error.localizedDescription } }
                    pickedMedia = nil
                }
            }
            .fullScreenCover(item: $camera) { mode in CameraCapture(video: mode == .video) { result in
                switch result { case .success(let url): stage(url, owned: true, origin: pickerOrigin); case .failure(let error): attachments.error = error.localizedDescription }
            }.ignoresSafeArea() }
            .task(id: store.contextID.uuidString + store.sessionID) { attachments.bind(store.contextID.uuidString + store.sessionID); if let client = store.client { await attachments.refresh(client: client, sessionId: store.sessionID) } }
            .onChange(of: store.sessionID) { _, _ in typing = false; composing = false; cancelVoice(); cancelMedia() }
            .onChange(of: store.phase) { _, phase in if phase != .ready { typing = false; composing = false } }
            .onChange(of: store.contextID) { _, _ in typing = false; composing = false; cancelVoice(); cancelMedia(); draft = "" }
            .onChange(of: store.completedReply?.id) { _, _ in
                guard let reply = store.completedReply else { return }
                if store.preferences.readAloud && scenePhase == .active && !voice.inputPending { read(reply) }
                if let client = store.client { Task { await attachments.refresh(client: client, sessionId: store.sessionID) } }
            }
            .onChange(of: scenePhase) { _, phase in
                if phase == .background || (phase == .inactive && voice.inputPhase != .authorizing) { cancelVoice() }
            }
            .onDisappear { composing = false; cancelVoice(); attachments.cancel(); cancelMedia() }
            .onAppear { let context = store.contextID; voice.onUnauthorized = { if context == store.contextID { store.authenticationExpired() } }; attachments.onUnauthorized = voice.onUnauthorized }
            .onChange(of: voice.inputPhase) { _, phase in if phase == .ready { finishVoice() } }
            .onChange(of: typing) { _, focused in
                if !focused { composing = false }
                if focused && voice.inputPending { cancelVoice() }
            }
        }
    }
    private var emptyState: some View {
        VStack(alignment: .leading, spacing: 24) {
            Text("What’s on your mind?").font(.system(.title2, design: .rounded, weight: .semibold)).padding(.top, 12)
            VStack(spacing: 10) {
                suggestion("Find a little focus", detail: "Make room for what matters", symbol: "sun.max", prompt: "Help me make room for focused work this week.")
                suggestion("Untangle an idea", detail: "A fresh pair of eyes", symbol: "point.3.connected.trianglepath.dotted", prompt: "I have an idea I'd like to think through. Ask me a few questions to help me clarify it.")
            }.padding(.top, 4)
        }
    }
    private func suggestion(_ title: String, detail: String, symbol: String, prompt: String) -> some View {
        Button { draft = prompt; beginTyping() } label: {
            HStack(spacing: 14) {
                Image(systemName: symbol).font(.title3).foregroundStyle(PhoneTheme.lavender).frame(width: 28)
                VStack(alignment: .leading, spacing: 3) { Text(title).font(.subheadline.weight(.medium)); Text(detail).font(.caption).foregroundStyle(PhoneTheme.secondary) }
                Spacer(); Image(systemName: "arrow.up.left").font(.caption).foregroundStyle(PhoneTheme.secondary)
            }.padding(16).background(PhoneTheme.surface, in: RoundedRectangle(cornerRadius: 18))
        }.buttonStyle(.plain).disabled(!store.canSend).accessibilityLabel(title)
    }
    @ViewBuilder private func messageView(_ message: ConversationMessage) -> some View {
        switch message.role {
        case .user:
            Text(message.text).textSelection(.enabled).padding(17).background(PhoneTheme.lavender.opacity(0.12), in: RoundedRectangle(cornerRadius: 22)).frame(maxWidth: .infinity, alignment: .trailing)
        case .notice: Text(message.text).font(.footnote).foregroundStyle(PhoneTheme.secondary)
        case .assistant:
            VStack(alignment: .leading, spacing: 14) {
                HStack(spacing: 8) { Image(systemName: "sparkle").foregroundStyle(PhoneTheme.mint); QuietLabel(text: store.conversationTitle) }
                PhoneMarkdown(text: message.text)
                if store.preferences.showMessageStats, let stats = message.stats {
                    MessageStatsView(wallTimeSeconds: stats.wallTimeSeconds, inputTokens: stats.inputTokens, outputTokens: stats.outputTokens, toolCalls: stats.toolCalls)
                }
                HStack(spacing: 22) {
                    ShareLink(item: message.text) { Image(systemName: "square.and.arrow.up") }.accessibilityLabel("Share answer")
                    Button { UIPasteboard.general.string = message.text } label: { Image(systemName: "document.on.document") }.accessibilityLabel("Copy answer")
                    if let client = store.client, let scope = store.selectedEntity.map({ SpeechScope.entity($0) }) ?? message.runID.map({ SpeechScope.run($0) }) {
                        Button { if voice.speaking && voice.readingID == message.id { voice.togglePause() } else { cancelVoice(); voice.read(message.text, client: client, scope: scope, choice: store.preferences.voice, speed: store.preferences.speed, messageID: message.id) } } label: { Image(systemName: voice.speaking && voice.readingID == message.id ? (voice.paused ? "play.fill" : "pause.fill") : "speaker.wave.2") }.accessibilityLabel(voice.speaking && voice.readingID == message.id ? "Pause or resume reading" : "Read answer aloud")
                    }
                    if voice.speaking && voice.readingID == message.id { Button { cancelVoice() } label: { Image(systemName: "stop.fill") }.accessibilityLabel("Stop reading") }
                }.font(.subheadline).foregroundStyle(PhoneTheme.secondary).buttonStyle(.plain).frame(minHeight: 44)
                if message.id == store.messages.last(where: { $0.role == .assistant })?.id && !attachments.files.isEmpty {
                    Button { typing = false; composing = false; cancelVoice(); showFiles = true } label: { Label("View conversation files (\(attachments.files.count))", systemImage: "paperclip") }.font(.footnote).foregroundStyle(PhoneTheme.mint)
                }
            }
        }
    }
    private var composer: some View {
        VStack(spacing: 10) {
            if attachments.busy || mediaLoading { HStack { ProgressView(); Text(mediaLoading ? "Importing media…" : attachments.status).font(.caption); Spacer(); Button("Cancel") { cancelMedia(); attachments.cancel() } } }
            if !attachments.pending.isEmpty {
                ScrollView(.horizontal) { HStack { ForEach(attachments.pending) { file in
                    HStack { Image(systemName: "paperclip"); Text(file.filename).lineLimit(1); Button { attachments.remove(file) } label: { Image(systemName: "xmark.circle.fill") }.accessibilityLabel("Remove " + file.filename) }.font(.caption).padding(9).background(PhoneTheme.surface, in: Capsule())
                } } }
            }
            if store.selectedEntity != nil { Text("File attachments are available in Assistant conversations.").font(.caption2).foregroundStyle(PhoneTheme.secondary) }
            HStack(alignment: .center, spacing: 12) {
                attachmentMenu
                Group {
                    if composing {
                        HStack(alignment: .bottom, spacing: 8) {
                            TextField("Type a message…", text: $draft, axis: .vertical)
                                .font(.subheadline).lineLimit(1...4).focused($typing).padding(.vertical, 14)
                                .accessibilityIdentifier("composer.input")
                                .disabled(!store.canSend || voice.transcribing)
                            Button(action: sendText) { Image(systemName: "arrow.up").font(.subheadline.weight(.semibold)).foregroundStyle(PhoneTheme.ground).frame(width: 36, height: 36).background(PhoneTheme.mint, in: Circle()) }
                                .disabled(!store.canSend || voice.inputPending || attachments.busy || mediaLoading || (draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && attachments.pending.isEmpty))
                                .opacity(!store.canSend || voice.inputPending || attachments.busy || mediaLoading || (draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && attachments.pending.isEmpty) ? 0.35 : 1)
                                .padding(.bottom, 9).accessibilityLabel("Send message")
                        }
                        .padding(.horizontal, 14)
                        .background(PhoneTheme.surface, in: RoundedRectangle(cornerRadius: 25))
                        .overlay(RoundedRectangle(cornerRadius: 25).stroke(PhoneTheme.stroke))
                        .task {
                            await Task.yield()
                            guard composing, !Task.isCancelled else { return }
                            guard scenePhase == .active else { composing = false; return }
                            typing = true
                        }
                    } else {
                        Button(action: beginTyping) {
                            Image(systemName: "keyboard").font(.title3).foregroundStyle(PhoneTheme.lavender)
                                .frame(width: 48, height: 48)
                                .background(PhoneTheme.surface, in: Circle())
                                .overlay(Circle().stroke(PhoneTheme.stroke))
                        }
                        .accessibilityLabel("Type a message").accessibilityIdentifier("composer.keyboard")
                        .accessibilityValue(draft.isEmpty ? "" : "Draft saved")
                        .disabled(!store.canSend || voice.transcribing)
                    }
                }
                .frame(width: composing ? nil : 48)
                .frame(maxWidth: composing ? .infinity : nil)
                .frame(height: composing ? nil : 80)
                .clipped()
                if !composing {
                    Spacer(minLength: 0)
                    VoicePresence(voice: voice, working: store.canStop, stopping: store.isStopping, enabled: store.canStop ? !store.isStopping : store.canSend && !attachments.busy && !mediaLoading, onTap: beginVoice, onCancel: cancelVoice, onStop: { voice.stop(); Task { await store.stopRun() } })
                        .transition(.opacity.combined(with: .scale(scale: 0.9)))
                }
            }
            .frame(minHeight: 80)
            .animation(composerAnimation, value: composing)
        }.padding(.horizontal, 16).padding(.top, 18).padding(.bottom, 4)
    }
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    private var composerAnimation: Animation? { reduceMotion ? nil : .spring(duration: 0.35, bounce: 0.05) }
    private var attachmentMenu: some View {
        Menu {
            Button("Choose a file", systemImage: "doc") { cancelVoice(); pickerOrigin = (store.contextID, store.sessionID); importing = true }
            Button("Photo or video library", systemImage: "photo.on.rectangle") { cancelVoice(); pickerOrigin = (store.contextID, store.sessionID); photoLibrary = true }
            if UIImagePickerController.isSourceTypeAvailable(.camera) {
                Button("Take a photo", systemImage: "camera") { cancelVoice(); pickerOrigin = (store.contextID, store.sessionID); camera = .photo }
                Button("Record a video", systemImage: "video") { cancelVoice(); pickerOrigin = (store.contextID, store.sessionID); camera = .video }
            }
        } label: { Image(systemName: "plus").font(.title3.weight(.light)).foregroundStyle(PhoneTheme.lavender).frame(width: 48, height: 48).background(PhoneTheme.surface, in: Circle()).overlay(Circle().stroke(PhoneTheme.stroke)) }
        .accessibilityLabel("Add attachment").disabled(!store.canSend || attachments.busy || mediaLoading || voice.inputPending || store.selectedEntity != nil)
    }
    private func beginTyping() {
        guard store.canSend, scenePhase == .active else { return }
        if voice.inputPending { cancelVoice() }
        composing = true
    }
    private func sendText() {
        guard store.canSend, !voice.inputPending else { return }
        let prompt = draft; typing = false; composing = false; cancelVoice(); store.send(prompt, attachments: attachments.pending)
        if store.phase == .sending { draft = ""; attachments.sent() }
    }
    private func beginVoice() {
        if voice.inputPending { cancelVoice(); return }
        guard store.canSend, scenePhase == .active, !attachments.busy, !mediaLoading else { return }
        typing = false; composing = false; voiceOrigin = (store.contextID, store.sessionID); voice.activate()
    }
    private func cancelVoice() { voiceTask?.cancel(); voiceTask = nil; voiceOrigin = nil; voice.stop() }
    private func finishVoice() {
        guard let origin = voiceOrigin, origin.0 == store.contextID, origin.1 == store.sessionID, scenePhase == .active, store.canSend, let client = store.client else { cancelVoice(); return }
        let model = store.preferences.transcription
        voiceTask = Task {
            guard let text = await voice.finish(client: client, sessionID: origin.1, model: model), !Task.isCancelled,
                  origin.0 == store.contextID, origin.1 == store.sessionID, scenePhase == .active, store.canSend else { return }
            store.send(text, attachments: attachments.pending)
            if store.phase == .sending { attachments.sent() }
            voiceOrigin = nil
        }
    }
    private func read(_ reply: ConversationMessage) {
        guard let client = store.client, !voice.recording, !reply.text.isEmpty else { return }
        let scope = store.selectedEntity.map(SpeechScope.entity) ?? reply.runID.map(SpeechScope.run)
        if let scope { voice.read(reply.text, client: client, scope: scope, choice: store.preferences.voice, speed: store.preferences.speed, messageID: reply.id) }
    }
    private func cancelMedia() { mediaGeneration = UUID(); mediaTask?.cancel(); mediaTask = nil; mediaLoading = false }
    private func stage(_ url: URL, owned: Bool = false, origin: (UUID, String)?) {
        guard let origin, origin.0 == store.contextID, origin.1 == store.sessionID else { if owned { ImportedMedia.remove(url) }; return }
        guard let client = store.client, store.canSend, store.selectedEntity == nil else { if owned { ImportedMedia.remove(url) }; return }
        attachments.importFile(url, client: client, sessionId: store.sessionID, owned: owned)
    }
    private var filesSheet: some View {
        NavigationStack {
            List {
                if let error = attachments.error { ErrorBanner(message: error) }
                if attachments.files.isEmpty { ContentUnavailableView("No files yet", systemImage: "folder", description: Text("Files you attach and files returned by your assistant appear here.")) }
                ForEach(attachments.files) { file in
                    Button { if let client = store.client { attachments.open(file, client: client) } } label: {
                        HStack { Image(systemName: file.contentType.hasPrefix("image/") ? "photo" : file.contentType.hasPrefix("video/") ? "video" : "doc"); VStack(alignment: .leading) { Text(file.filename); Text(ByteCountFormatter.string(fromByteCount: Int64(file.size), countStyle: .file)).font(.caption).foregroundStyle(PhoneTheme.secondary) }; Spacer(); Image(systemName: "arrow.down.circle") }
                    }.disabled(attachments.busy)
                }
                if attachments.busy { HStack { ProgressView(); Text(attachments.status); Button("Cancel") { attachments.cancel() } } }
            }.scrollContentBackground(.hidden).background(PhoneTheme.ground).navigationTitle("Conversation files").navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { showFiles = false } } }
                .task { if let client = store.client { await attachments.refresh(client: client, sessionId: store.sessionID) } }
                .refreshable { if let client = store.client { await attachments.refresh(client: client, sessionId: store.sessionID) } }
                .quickLookPreview($attachments.preview)
        }
    }

}

struct ConversationsSheet: View {
    var onOpen: () -> Void
    @Environment(AssistantStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    @State private var search = ""
    var body: some View {
        NavigationStack {
            List {
                Button { store.newConversation(); onOpen() } label: { Label("New conversation", systemImage: "square.and.pencil").padding(.vertical, 7) }.disabled(!store.canSend)
                ForEach(store.sessions.filter { search.isEmpty || (store.titles[$0.id] ?? "Conversation").localizedCaseInsensitiveContains(search) }) { session in
                    Button {
                        Task { await store.openSession(session); if store.error == nil { onOpen() } }
                    } label: {
                        VStack(alignment: .leading, spacing: 6) {
                            Text(store.titles[session.id] ?? "Conversation").foregroundStyle(PhoneTheme.ink).fontWeight(.medium)
                            HStack { Text("\(session.turns) \(session.turns == 1 ? "exchange" : "exchanges")"); if let date = session.updatedAt { Text("·"); Text(date, style: .relative) }; if !session.latest.isTerminal { Text("· " + session.latest.status).foregroundStyle(PhoneTheme.amber) } }.font(.caption).foregroundStyle(PhoneTheme.secondary)
                        }.padding(.vertical, 6)
                    }.disabled(!store.canOpenConversation)
                }
                if store.sessions.isEmpty { ContentUnavailableView("A fresh start", systemImage: "bubble.left.and.bubble.right", description: Text("Your gateway conversations will appear here.")) }
            }.scrollContentBackground(.hidden).background(PhoneTheme.ground)
                .searchable(text: $search, prompt: "Find a conversation")
                .navigationTitle("Conversations").toolbar { ToolbarItem(placement: .cancellationAction) { Button("Done") { dismiss() } } }
                .refreshable { await store.refresh() }
        }
    }
}
