@preconcurrency import AVFoundation
import SwiftUI
import UniformTypeIdentifiers
import AssistantKit
import AbstractGatewayClient

/// Settings → Voice → Create a voice (the gateway's voice library, AbstractGateway 0.16.0): from a
/// description (`POST voice/design`) or from a recording made here or chosen from Files
/// (`POST voice/clones`). The request runs in the background with its progress shown; the new voice
/// becomes the assistant's voice when it speaks on the assistant's engine, and the screen says so
/// plainly when it does not.
struct CreateVoiceScreen: View {
    /// Called with the catalog read after the voice was created (the voice lists refresh from it).
    var onCatalog: (VoiceCatalog) -> Void = { _ in }
    @Environment(AssistantStore.self) private var store
    @State private var mode: VoiceCreationMode = .description
    @State private var design = VoiceDesignForm()
    @State private var recording = VoiceRecordingForm()
    @State private var recorder = CloneRecorder()
    @State private var importing = false
    @State private var working = false
    @State private var progress = ""
    @State private var outcome: VoiceCreationOutcome?
    @State private var error: String?

    private var problem: String? { mode == .description ? design.problem : recording.problem }

    var body: some View {
        Form {
            Section {
                Picker("Create from", selection: $mode) {
                    ForEach(VoiceCreationMode.allCases) { Text($0.rawValue).tag($0) }
                }.pickerStyle(.segmented).disabled(working).accessibilityIdentifier("voice.create.mode")
            }.listRowBackground(Color.clear)
            if mode == .description { descriptionForm } else { recordingForm }
            Section {
                Button { create() } label: {
                    HStack {
                        if working { ProgressView().padding(.trailing, 6) }
                        Text(working ? progress : "Create voice")
                    }
                }
                .disabled(working || problem != nil || store.client == nil)
                .accessibilityIdentifier("voice.create.submit")
                if !working, let problem { Text(problem).font(.footnote).foregroundStyle(PhoneTheme.secondary) }
                if let outcome {
                    Label(outcome.message, systemImage: { if case .selected = outcome { "checkmark.circle" } else { "info.circle" } }())
                        .font(.footnote).foregroundStyle({ if case .selected = outcome { PhoneTheme.mint } else { PhoneTheme.amber } }())
                        .accessibilityIdentifier("voice.create.outcome")
                }
                if let error { ErrorBanner(message: error).accessibilityIdentifier("voice.create.error") }
            } footer: {
                Text(store.connection == nil
                     ? "Voices are created on your gateway."
                     : "With user accounts on, the voice is yours alone. On a gateway with one shared voice store, only an administrator can create voices.")
            }.listRowBackground(PhoneTheme.surface)
        }
        .scrollContentBackground(.hidden).background(PhoneTheme.ground)
        .navigationTitle("Create a voice").navigationBarTitleDisplayMode(.inline)
        .fileImporter(isPresented: $importing, allowedContentTypes: [.audio]) { result in
            switch result {
            case .success(let url): load(url)
            case .failure(let failure): error = failure.localizedDescription
            }
        }
        .onChange(of: recorder.finished) { _, take in
            guard let take else { return }
            recording.audio = take.audio; recording.filename = take.filename; recording.recordedSeconds = take.seconds
        }
        .onChange(of: store.contextID) { _, _ in recorder.cancel() }
        .onDisappear { recorder.cancel() }
    }

    private var descriptionForm: some View {
        Section {
            TextField("A calm, warm adult female voice with a slight British accent, speaking slowly.", text: $design.description, axis: .vertical)
                .lineLimit(3...6).accessibilityIdentifier("voice.create.description")
            TextField("Name", text: $design.name).accessibilityIdentifier("voice.create.name")
            Picker("Language", selection: $design.language) {
                ForEach(VoiceLibrary.creationLanguages, id: \.self) { Text(VoiceLibrary.languageName($0)).tag($0) }
            }.accessibilityIdentifier("voice.create.language")
        } header: { Text("Describe the voice") } footer: {
            Text("Your gateway designs it with Qwen3-TTS. The first voice can take a minute while the engine loads.")
        }.listRowBackground(PhoneTheme.surface)
    }

    @ViewBuilder private var recordingForm: some View {
        Section {
            HStack {
                Button { recorder.recording ? recorder.stop() : recorder.start() } label: {
                    Label(recorder.recording ? "Stop" : "Record", systemImage: recorder.recording ? "stop.circle.fill" : "mic.circle")
                }.disabled(working).accessibilityIdentifier("voice.create.record")
                Spacer()
                if recorder.recording {
                    Text(Self.clock(recorder.elapsed) + " / 0:20").monospacedDigit().foregroundStyle(PhoneTheme.secondary)
                }
            }
            Button("Choose a recording…") { importing = true }.disabled(working || recorder.recording).accessibilityIdentifier("voice.create.file")
            if let audio = recording.audio, !recorder.recording {
                LabeledContent(recording.filename, value: recording.recordedSeconds.map { Self.clock($0) } ?? ByteCountFormatter.string(fromByteCount: Int64(audio.count), countStyle: .file))
                    .accessibilityIdentifier("voice.create.take")
            }
            if let note = recorder.error { Text(note).font(.footnote).foregroundStyle(PhoneTheme.amber) }
        } header: { Text("Recording") } footer: {
            Text("Record 5 to 20 seconds of one person speaking clearly, or choose a WAV, FLAC, OGG, MP3, M4A or WEBM file.")
        }.listRowBackground(PhoneTheme.surface)
        Section {
            TextField("What the recording says (optional)", text: $recording.transcript, axis: .vertical).lineLimit(1...4)
                .accessibilityIdentifier("voice.create.transcript")
            TextField("Name", text: $recording.name).accessibilityIdentifier("voice.create.cloneName")
            Picker("Language", selection: $recording.language) {
                Text("Detect from the recording").tag(VoiceRecordingForm.detect)
                ForEach(VoiceLibrary.creationLanguages, id: \.self) { Text(VoiceLibrary.languageName($0)).tag($0) }
            }.accessibilityIdentifier("voice.create.cloneLanguage")
        }.listRowBackground(PhoneTheme.surface)
    }

    static func clock(_ seconds: TimeInterval) -> String {
        let s = Int(seconds.rounded(.down)); return "\(s / 60):" + String(format: "%02d", s % 60)
    }

    private func load(_ url: URL) {
        let scoped = url.startAccessingSecurityScopedResource()
        defer { if scoped { url.stopAccessingSecurityScopedResource() } }
        do {
            let data = try Data(contentsOf: url)
            recording.audio = data; recording.filename = url.lastPathComponent; recording.recordedSeconds = nil; error = nil
        } catch { self.error = "The recording could not be read: \(error.localizedDescription)" }
    }

    /// Off the main thread's way: the request runs in a task, the screen stays usable, and a
    /// result for another account (signed out meanwhile) is dropped.
    private func create() {
        guard let client = store.client, problem == nil else { return }
        let context = store.contextID
        let designRequest = design.request
        recording.engine = store.preferences.voice?.provider
        let upload = recording.upload
        working = true; error = nil; outcome = nil
        progress = mode == .description ? "Designing the voice… the first one can take a minute." : "Cloning the voice from your recording…"
        Task {
            do {
                let created: CreatedVoice
                if let designRequest, mode == .description {
                    created = try await client.designVoice(description: designRequest.description, name: designRequest.name, language: designRequest.language)
                } else if let upload {
                    created = try await client.cloneVoice(upload)
                } else { working = false; return }
                progress = "Adding it to your voices…"
                let catalog = try await client.voiceCatalog()
                guard context == store.contextID else { return }
                onCatalog(catalog)
                let result = VoiceCreationOutcome.of(created, in: catalog, current: store.preferences.voice)
                if case .selected(let choice, _) = result { store.preferences.voice = choice }
                outcome = result
                if mode == .description { design = VoiceDesignForm(language: design.language) } else { recording = VoiceRecordingForm() }
            } catch {
                guard context == store.contextID else { return }
                self.error = error.localizedDescription
                if error as? GatewayError == .unauthorized { store.authenticationExpired() }
            }
            working = false
        }
    }
}

/// One recording of 5 to 20 seconds for cloning: 24 kHz 16-bit mono WAV, stopped at 20 seconds.
@MainActor @Observable final class CloneRecorder {
    struct Take: Equatable { var audio: Data; var filename: String; var seconds: TimeInterval }
    private(set) var recording = false
    private(set) var elapsed: TimeInterval = 0
    private(set) var error: String?
    private(set) var finished: Take?
    @ObservationIgnored private var recorder: AVAudioRecorder?
    @ObservationIgnored private var file: URL?
    @ObservationIgnored private var ticker: Task<Void, Never>?

    func start() {
        error = nil; finished = nil
        Task {
            guard await AVAudioApplication.requestRecordPermission() else {
                error = "Microphone access is off. You can enable it in iPhone Settings, or choose a recording instead."; return
            }
            do {
                let audio = AVAudioSession.sharedInstance()
                try audio.setCategory(.record, mode: .default); try audio.setActive(true)
                let folder = try PhoneTemporaryStorage().makeDirectory(for: .voice)
                let url = folder.appending(path: "voice-sample-\(UUID().uuidString.prefix(8)).wav")
                let r = try AVAudioRecorder(url: url, settings: [AVFormatIDKey: kAudioFormatLinearPCM, AVSampleRateKey: 24_000, AVNumberOfChannelsKey: 1,
                                                                AVLinearPCMBitDepthKey: 16, AVLinearPCMIsFloatKey: false, AVLinearPCMIsBigEndianKey: false])
                guard r.record(forDuration: VoiceRecordingForm.maximumSeconds) else { throw CocoaError(.fileWriteUnknown) }
                recorder = r; file = url; recording = true; elapsed = 0
                ticker = tick(r)
            } catch { self.error = "The microphone couldn’t start. You can choose a recording instead."; cancel() }
        }
    }

    /// The elapsed time while recording; stops the take when the recorder ends it (20 seconds).
    private func tick(_ r: AVAudioRecorder) -> Task<Void, Never> {
        Task { [weak self] in
            while let self, self.recording {
                self.elapsed = r.currentTime > 0 ? r.currentTime : self.elapsed
                if !r.isRecording { self.stop(); return }   // stopped by itself at 20 seconds
                try? await Task.sleep(for: .milliseconds(200))
            }
        }
    }

    func stop() {
        guard recording, let recorder, let file else { return }
        let seconds = max(elapsed, recorder.currentTime)
        recorder.stop(); recording = false; ticker?.cancel()
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        if let data = try? Data(contentsOf: file) { finished = Take(audio: data, filename: "voice-sample.wav", seconds: seconds) }
        else { error = "The recording could not be read. Try again." }
        try? FileManager.default.removeItem(at: file)
        self.recorder = nil; self.file = nil
    }

    func cancel() {
        ticker?.cancel()
        if recording { recorder?.stop(); recording = false; try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation) }
        if let file { try? FileManager.default.removeItem(at: file) }
        recorder = nil; file = nil
    }
}
