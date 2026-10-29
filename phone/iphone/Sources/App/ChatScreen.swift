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
    @State private var editingStoppedRequest: ConversationMessage?
    @State private var history = false
    @State private var choosingEntity = false
    @State private var showWait: Wait?
    @State private var voice = VoiceController.forApp()
    @State private var voiceOrigin: (UUID, String)?
    @State private var voiceTask: Task<Void, Never>?
    @State private var attachments = AttachmentsController()
    @State private var media = MessageMediaController()
    @State private var importing = false
    @State private var photoLibrary = false
    @State private var pickedMedia: PhotosPickerItem?
    @State private var camera: CaptureMode?
    @State private var showFiles = false
    @State private var sessionFiles = SessionFilesController()
    @State private var showTools = false
    @State private var sharedConversation: ConversationShareSnapshot?
    @State private var mediaTask: Task<Void, Never>?
    @State private var mediaLoading = false
    @State private var mediaGeneration = UUID()
    @State private var pickerOrigin: (UUID, String)?
    private enum CaptureMode: String, Identifiable { case photo, video; var id: String { rawValue } }
    @State private var composing = false
    @FocusState private var typing: Bool

    var body: some View {
        NavigationStack {
            ConversationScrollView(conversationID: store.contextID.uuidString + store.sessionID,
                userTurnID: store.messages.last(where: { $0.role == .user })?.id,
                latestID: store.messages.last?.id, latestText: store.messages.last?.text) {
                LazyVStack(alignment: .leading, spacing: 24) {
                    if let message = store.error, message != store.activityFailure, store.activityIssue?.contains(message) != true { ErrorBanner(message: message, dismiss: store.dismissError) }
                    if let message = attachments.error { ErrorBanner(message: message, dismiss: { attachments.error = nil }) }
                    if let message = voice.error { ErrorBanner(message: message, dismiss: { voice.error = nil }) }
                    if store.messages.isEmpty { emptyState }
                    ForEach(store.messages) { message in messageView(message) }
                    if (store.activityState != .idle && store.activityState != .completed) || store.phase != .ready || store.isStopping || (store.selectedEntity != nil && store.activityIssue != nil) { RunActivityPanel { showWait = $0 } }
                    else if store.isRestoring || store.isOpening { ProgressView("Opening your conversation…").padding(.vertical, 28).frame(maxWidth: .infinity) }
                    Color.clear.frame(height: 1).id("bottom")
                }.padding(22)
            }
            .background(PhoneTheme.ground)
            .fullScreenCover(isPresented: Binding(get: { media.preview != nil }, set: { if !$0 { media.preview = nil } })) {
                if let url = media.preview { ArtifactPreview(url: url) { media.preview = nil } }
            }
            .sheet(isPresented: $showTools) { ConversationToolsScreen() }
            .task(id: store.preferences.showMessageStats) { await store.loadMessageStats() }
            .background(OutsideInputDismissal(focused: typing, dismiss: { typing = false; composing = false }))
            .navigationTitle(store.conversationTitle).navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button { prepareNavigation(); history = true } label: { Image(systemName: "rectangle.stack") }
                        .accessibilityLabel("Conversations").accessibilityIdentifier("chat.conversations")
                        .disabled(attachments.busy || mediaLoading || !attachments.pending.isEmpty)
                }
                ToolbarItem(placement: .principal) {
                    HStack(spacing: 0) {
                        Button {
                            prepareNavigation()
                            if let client = store.client, ConversationTranscript.hasContent(store.messages) {
                                sharedConversation = ConversationShareSnapshot(messages: store.messages, responder: store.conversationTitle, client: client, activities: store.answerActivities, contextID: store.contextID, sessionID: store.sessionID)
                            }
                        } label: { Image(systemName: "square.and.arrow.up").frame(width: 44, height: 44) }
                            .accessibilityLabel("Share conversation").accessibilityIdentifier("chat.share")
                            .disabled(!store.canSend || store.isOpening || store.isRestoring || !ConversationTranscript.hasContent(store.messages))
                        Button { prepareNavigation(); showFiles = true } label: {
                            Image(systemName: "folder").frame(width: 44, height: 44)
                        }.accessibilityLabel("Conversation files").accessibilityIdentifier("chat.files")
                        Button { prepareNavigation(); showTools = true } label: {
                            Image(systemName: "wrench.and.screwdriver").foregroundStyle(PhoneTheme.tool).frame(width: 44, height: 44)
                        }.accessibilityLabel("Tools").accessibilityIdentifier("chat.tools")
                        if !store.sessionApprovalGrants.isEmpty || !store.legacySessionApprovalNames.isEmpty {
                            Button {
                                if !store.legacySessionApprovalNames.isEmpty { prepareNavigation(); showTools = true }
                                else { store.revokeSessionApprovals() }
                            } label: {
                                Image(systemName: "checkmark.shield.fill").foregroundStyle(PhoneTheme.amber)
                                    .frame(width: 44, height: 44)
                            }.accessibilityLabel(store.legacySessionApprovalNames.isEmpty ? "Ask tools again" : "Review earlier tool approvals")
                                .accessibilityValue(store.legacySessionApprovalNames.isEmpty ? "\(store.sessionApprovalGrants.count) tools allowed in this session" : "Earlier approvals need review")
                                .accessibilityHint("Auto tools keep their settings.")
                                .accessibilityIdentifier("chat.approvals.revoke")
                        }
                    }.font(.body).buttonStyle(.plain).padding(.horizontal, 6)
                        .glassEffect(.regular, in: Capsule())
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button { prepareNavigation(); openSettings() } label: { Image(systemName: "gearshape") }
                        .accessibilityLabel("Settings").accessibilityIdentifier("chat.settings")
                        .disabled(attachments.busy || mediaLoading || !attachments.pending.isEmpty)
                }
            }
            .safeAreaInset(edge: .top, spacing: 0) {
                Button { prepareNavigation(); choosingEntity = true } label: {
                    HStack(spacing: 6) {
                        NavigationCaption(title: store.conversationTitle, demo: store.isDemo)
                        Image(systemName: "chevron.down").font(.caption2.weight(.semibold))
                    }.lineLimit(1).padding(.horizontal, 20).frame(maxWidth: 280, minHeight: 44)
                }.buttonStyle(.plain).accessibilityLabel("Choose who answers").accessibilityValue(store.conversationTitle)
                    .frame(maxWidth: .infinity).background(PhoneTheme.ground.opacity(0.96))
            }
            .sheet(item: $editingStoppedRequest) { request in
                StoppedRequestEditor(request: request, session: store.sessionID, context: store.contextID)
            }
            .onChange(of: store.contextID) { _, _ in editingStoppedRequest = nil }
            .onChange(of: store.sessionID) { _, _ in editingStoppedRequest = nil }
            .sheet(item: $sharedConversation) { ConversationSharePreparation(snapshot: $0) }
            .onChange(of: store.contextID) { _, _ in sharedConversation = nil }
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
            .task(id: store.contextID.uuidString + store.sessionID) {
                let context = store.contextID
                voice.onUnauthorized = { if context == store.contextID { store.authenticationExpired() } }
                attachments.onUnauthorized = voice.onUnauthorized; media.onUnauthorized = voice.onUnauthorized; sessionFiles.onUnauthorized = voice.onUnauthorized
                attachments.bind(context.uuidString + store.sessionID); media.bind(context.uuidString + store.sessionID); sessionFiles.bind(context.uuidString + store.sessionID)
                let session = store.sessionID, ids = sessionRunIDs, explicitFiles = Set(store.messages.flatMap(\.artifacts).map(\.artifactId))
                if let client = store.client {
                    await attachments.refresh(client: client, sessionId: session)
                    guard context == store.contextID, session == store.sessionID, !Task.isCancelled else { return }
                    await sessionFiles.refresh(client: client, sessionID: session, runIDs: ids, explicitFileIDs: explicitFiles)
                }
            }
            .onChange(of: store.sessionID) { _, _ in typing = false; composing = false; cancelVoice(); cancelMedia() }
            .onChange(of: store.phase) { _, phase in if phase != .ready { typing = false; composing = false } }
            .onChange(of: store.contextID) { _, _ in typing = false; composing = false; cancelVoice(); cancelMedia(); draft = "" }
            .onChange(of: store.completedReply?.id) { _, _ in
                guard let reply = store.completedReply else { return }
                if store.preferences.readAloud && !reply.text.isEmpty && !reply.artifacts.contains(where: \.isAudio) && scenePhase == .active && !voice.inputPending { media.stop(); read(reply) }
                if let client = store.client {
                    let context = store.contextID, session = store.sessionID, ids = sessionRunIDs, explicitFiles = Set(store.messages.flatMap(\.artifacts).map(\.artifactId))
                    Task {
                        await attachments.refresh(client: client, sessionId: session)
                        guard context == store.contextID, session == store.sessionID, !Task.isCancelled else { return }
                        await sessionFiles.refresh(client: client, sessionID: session, runIDs: ids, explicitFileIDs: explicitFiles)
                    }
                }
            }
            .onChange(of: scenePhase) { _, phase in
                if phase == .background || (phase == .inactive && voice.inputPhase != .authorizing) { cancelVoice(); media.stop() }
            }
            .onDisappear { composing = false; cancelVoice(); if media.preview == nil { media.reset() } else { media.stop() }; attachments.cancel(); cancelMedia() }
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
            VStack(alignment: .trailing, spacing: 8) {
                Text(message.text).textSelection(.enabled).padding(17).background(PhoneTheme.lavender.opacity(0.12), in: RoundedRectangle(cornerRadius: 22))
                    .accessibilityIdentifier(message.id == store.messages.last(where: { $0.role == .user })?.id ? "chat.latest-question" : "question." + message.id)
                if message.wasStopped {
                    Button {
                        prepareNavigation(); media.stop(); editingStoppedRequest = message
                    } label: { Label("Edit and resend", systemImage: "square.and.pencil").font(.subheadline.weight(.medium)) }
                        .foregroundStyle(PhoneTheme.mint).buttonStyle(.plain).frame(minHeight: 44)
                        .disabled(!store.canSend || attachments.busy || mediaLoading)
                        .accessibilityIdentifier("request.edit." + message.id)
                }
            }.frame(maxWidth: .infinity, alignment: .trailing)
        case .notice: Text(message.text).font(.footnote).foregroundStyle(PhoneTheme.secondary)
        case .assistant:
            VStack(alignment: .leading, spacing: 14) {
                HStack(spacing: 8) { Image(systemName: "sparkle").foregroundStyle(PhoneTheme.mint); QuietLabel(text: store.conversationTitle) }
                if !message.text.isEmpty { PhoneMarkdown(text: message.text) }
                if let client = store.client {
                    ForEach(message.artifacts) { file in
                        MessageArtifactView(file: file, media: media, client: client, useImage: { attachments.use(file) }, beforePlayback: { cancelVoice() })
                    }
                }
                if store.preferences.showMessageStats, let stats = message.stats {
                    MessageStatsView(wallTimeSeconds: stats.wallTimeSeconds, inputTokens: stats.inputTokens, outputTokens: stats.outputTokens, toolCalls: stats.toolCalls)
                }
                ScrollView(.horizontal) {
                HStack(spacing: 16) {
                    if !message.text.isEmpty {
                    Button { UIPasteboard.general.string = message.text } label: { Image(systemName: "document.on.document") }.accessibilityLabel("Copy answer").accessibilityIdentifier(message.id == store.messages.last(where: { $0.role == .assistant })?.id ? "chat.latest-copy" : "answer.copy." + message.id)
                    if let client = store.client, let scope = store.selectedEntity.map({ SpeechScope.entity($0) }) ?? message.runID.map({ SpeechScope.run($0) }) {
                        // A speaker reads aloud (filled while paused: a tap resumes); never a play triangle.
                        Button { if voice.speaking && voice.readingID == message.id { voice.togglePause() } else { cancelVoice(); media.stop(); voice.read(message.text, client: client, scope: scope, choice: store.preferences.voice, speed: store.preferences.speed, messageID: message.id) } } label: { Image(systemName: voice.speaking && voice.readingID == message.id ? (voice.paused ? "speaker.wave.2.fill" : "pause.fill") : "speaker.wave.2") }.accessibilityLabel(voice.speaking && voice.readingID == message.id ? "Pause or resume reading" : "Read answer aloud")
                    }
                    if voice.speaking && voice.readingID == message.id { Button { cancelVoice() } label: { Image(systemName: "stop.fill") }.accessibilityLabel("Stop reading") }
                    #if DEBUG
                    // UI tests: the largest silence between two voice segments (ms), and whether a reading is on.
                    if ProcessInfo.processInfo.arguments.contains("--ui-test"), message.id == store.messages.last(where: { $0.role == .assistant })?.id {
                        Text("\(Int(voice.maxGapMilliseconds.rounded())) \(voice.speaking ? "on" : "off")").font(.system(size: 1)).opacity(0.01).accessibilityIdentifier("debug.gaps")
                    }
                    #endif
                    }
                    if let id = message.runID { AnswerActivityButtons(runID: id, browseFiles: { typing = false; composing = false; cancelVoice(); showFiles = true }) }
                    else if store.answerActivities[message.id] != nil { AnswerActivityButtons(runID: message.id, cachedOnly: true, browseFiles: { typing = false; composing = false; cancelVoice(); showFiles = true }) }

                }.font(.caption).foregroundStyle(PhoneTheme.secondary).buttonStyle(.plain)
                }.scrollIndicators(.hidden).frame(height: 44).accessibilityIdentifier("answer.actions." + (message.runID ?? message.id))
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
                    VoicePresence(voice: voice, generatedMedia: media, autoSendVoice: store.preferences.autoSendVoice, working: store.canStop, stopping: store.isStopping, enabled: store.canStop ? !store.isStopping : store.canSend && !attachments.busy && !mediaLoading,
                        needsApproval: store.conversationWait?.kind == .toolApproval,
                        onReviewApproval: {
                            guard let wait = store.conversationWait, wait.kind == .toolApproval, !store.isStopping else { return }
                            cancelVoice(); showWait = wait
                        }, onTap: beginVoice, onCancel: cancelVoice, onStop: { voice.stop(); Task { await store.stopRun() } })
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
        typing = false; composing = false; media.stop(); voiceOrigin = (store.contextID, store.sessionID); voice.activate()
    }
    private func cancelVoice() { voiceTask?.cancel(); voiceTask = nil; voiceOrigin = nil; voice.stop() }
    private func finishVoice() {
        guard let origin = voiceOrigin, origin.0 == store.contextID, origin.1 == store.sessionID, scenePhase == .active, store.canSend, let client = store.client else { cancelVoice(); return }
        let model = store.preferences.transcription
        let autoSend = store.preferences.autoSendVoice
        voiceTask = Task {
            guard let text = await voice.finish(client: client, sessionID: origin.1, model: model), !Task.isCancelled,
                  origin.0 == store.contextID, origin.1 == store.sessionID, scenePhase == .active, store.canSend else { return }
            voiceOrigin = nil
            if autoSend {
                store.send(text, attachments: attachments.pending)
                if store.phase == .sending { attachments.sent() }
            } else {
                draft = draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? text : draft + (draft.hasSuffix("\n") ? "" : "\n") + text
                beginTyping()
            }
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
    private func prepareNavigation() { typing = false; composing = false; cancelVoice() }
    private var sessionRunIDs: [String] {
        var seen: Set<String> = []
        return (store.messages.compactMap(\.runID) + [store.activeRunID].compactMap { $0 }).filter { seen.insert($0).inserted }
    }
    private var filesSheet: some View { SessionFilesScreen(files: sessionFiles, runIDs: sessionRunIDs) }

}

/// A separate draft preserves the conversation and anything already typed in the composer.
private struct StoppedRequestEditor: View {
    let request: ConversationMessage
    let session: String
    let context: UUID
    @Environment(AssistantStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    @State private var text: String
    @State private var files: [PhoneArtifact]
    @FocusState private var focused: Bool
    init(request: ConversationMessage, session: String, context: UUID) {
        self.request = request; self.session = session; self.context = context
        _text = State(initialValue: request.requestText ?? request.text)
        _files = State(initialValue: request.artifacts)
    }
    private var available: Bool { store.canSend && store.sessionID == session && store.contextID == context }
    var body: some View {
        NavigationStack {
            Form {
                Section("Request") {
                    TextField("Your request…", text: $text, axis: .vertical)
                        .lineLimit(3...10).focused($focused).accessibilityIdentifier("request.edit.text")
                }
                if !files.isEmpty {
                    Section("Attachments") {
                        ForEach(files) { file in
                            HStack {
                                Label(file.filename, systemImage: "paperclip")
                                Spacer()
                                Button { files.removeAll { $0.id == file.id } } label: { Image(systemName: "xmark.circle.fill") }
                                    .buttonStyle(.plain).foregroundStyle(PhoneTheme.secondary)
                                    .accessibilityLabel("Remove " + file.filename)
                            }
                        }
                    }
                }
                Section { Text("Your stopped request stays in the conversation. Send starts a new reply.").font(.footnote).foregroundStyle(PhoneTheme.secondary) }
            }
            .scrollContentBackground(.hidden).background(PhoneTheme.ground)
            .scrollDismissesKeyboard(.interactively)
            .navigationTitle("Edit request").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Send") {
                        if store.resendStoppedRequest(messageID: request.id, text: text, attachments: files, session: session, context: context) { dismiss() }
                    }.disabled(!available || (text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && files.isEmpty))
                        .accessibilityIdentifier("request.edit.send")
                }
            }
            .task { focused = true }
        }
    }
}
