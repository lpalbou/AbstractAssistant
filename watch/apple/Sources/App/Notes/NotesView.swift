import AbstractGatewayClient
import SwiftUI
import WatchKit

/// A note draft survives leaving the page, but never a change of gateway/account.
@MainActor
final class WatchNotes: ObservableObject {
    @Published var text = ""
    @Published private(set) var status: String?
    @Published private(set) var issue: String?
    @Published private(set) var saved = false
    @Published private(set) var pending: NoteCaptureRequest?
    private var runID: String?
    private var owner = ""
    private var revision = 0
    private var work: Task<Void, Never>?
    var busy: Bool { status != nil }

    func bind(to owner: String) {
        guard self.owner != owner else { return }
        reset(); self.owner = owner
    }
    func reset() {
        revision += 1; work?.cancel(); work = nil
        text = ""; status = nil; issue = nil; saved = false; pending = nil; runID = nil
    }
    func noSpeech(_ message: String) { issue = message }
    func transcribe(_ wav: Data, client: any GatewayClient) {
        guard !busy, pending == nil else { return }
        let mine = revision
        status = "Writing it down…"; issue = nil
        let session = "note-watch-" + UUID().uuidString.lowercased()
        work = Task {
            let hold = "note-voice-" + UUID().uuidString
            RuntimeKeeper.shared.hold(hold)
            defer { RuntimeKeeper.shared.release(hold) }
            do {
                let words = try await client.transcribe(wav: wav, sessionId: session)
                guard !Task.isCancelled, mine == revision else { return }
                if words.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { issue = "No words were heard. Try again." }
                else { text += (text.isEmpty ? "" : " ") + words }
            } catch {
                guard !Task.isCancelled, mine == revision else { return }
                issue = AppModel.say(error)
            }
            status = nil
        }
    }
    func save(client: any GatewayClient) {
        guard !busy, !saved else { return }
        if pending == nil {
            let words = text.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !words.isEmpty else { return }
            pending = NoteCaptureRequest(text: words)
        }
        guard let capture = pending else { return }
        let mine = revision
        status = "Saving…"; issue = nil
        work = Task {
            let hold = "note-save-" + UUID().uuidString
            RuntimeKeeper.shared.hold(hold)
            defer { RuntimeKeeper.shared.release(hold) }
            do {
                if runID == nil {
                    let id = try await client.startNoteCapture(capture)
                    guard !Task.isCancelled, mine == revision else { return }
                    runID = id
                }
                guard let id = runID else { return }
                let until = Date().addingTimeInterval(60)
                repeat {
                    let run = try await client.run(id: id)
                    guard !Task.isCancelled, mine == revision else { return }
                    switch NoteCaptureOutcome(run) {
                    case .saved:
                        saved = true; status = nil
                        WKInterfaceDevice.current().play(.success)
                        return
                    case .failed(let message):
                        // Retry may start another run, but always with the same note key.
                        runID = nil; status = nil; issue = message
                        return
                    case .needsApproval:
                        status = nil; issue = "Waiting for approval. Check again after approving it."
                        return
                    case .pending: break
                    }
                    try await Task.sleep(for: .seconds(1))
                } while Date() < until
                issue = "Still saving. Check again to see whether your note is ready."
            } catch {
                guard !Task.isCancelled, mine == revision else { return }
                if case GatewayError.http(let code, _) = error, code == 404 {
                    if runID == nil { issue = "AbstractNote isn’t set up on this gateway." }
                    else { runID = nil; issue = "The save status couldn’t be found. Try again to check the same note." }
                } else if case GatewayError.http(let code, _) = error, code == 503 {
                    issue = "Notes are temporarily unavailable. Try again."
                } else { issue = AppModel.say(error) }
            }
            status = nil
        }
    }
}

struct NotesView: View {
    @EnvironmentObject private var model: AppModel
    @ObservedObject var notes: WatchNotes
    @StateObject private var listener = Listener()
    @State private var discard = false

    var body: some View {
        FitScroll {
            VStack(alignment: .leading, spacing: 10) {
                if notes.saved {
                    Label("Saved to Notes", systemImage: "checkmark.circle.fill")
                        .font(.rounded(.headline)).foregroundStyle(Theme.cyan).accessibilityIdentifier("notes.saved")
                    Text(notes.text).font(.rounded(.footnote)).foregroundStyle(Theme.text2)
                    Button("New note") { notes.reset() }
                        .buttonStyle(FilledButtonStyle(fill: Theme.indigoButton)).accessibilityIdentifier("notes.new")
                } else {
                    Text("Capture a thought").font(.rounded(.headline)).foregroundStyle(Theme.text)
                    TextField("Write a note…", text: $notes.text)
                        .font(.rounded(.body)).accessibilityIdentifier("notes.text")
                        .disabled(notes.busy || notes.pending != nil || listener.isListening)
                    if listener.isListening {
                        Label("Listening…", systemImage: "waveform").foregroundStyle(Theme.cyan)
                        Button("Done speaking") { listener.send() }
                            .buttonStyle(FilledButtonStyle(fill: Theme.indigoButton)).accessibilityIdentifier("notes.voice.done")
                        Button("Cancel recording") { listener.cancel() }
                            .buttonStyle(.tap)
                    } else if let status = notes.status {
                        HStack { ProgressView(); Text(status).font(.rounded(.footnote)) }
                    } else {
                        if notes.pending == nil {
                            Button { record() } label: { Label("Dictate", systemImage: "mic") }
                                .buttonStyle(FilledButtonStyle(fill: Theme.neutralButton)).accessibilityIdentifier("notes.dictate")
                        }
                        Button(notes.pending == nil ? "Save note" : "Check again") { notes.save(client: model.client) }
                            .buttonStyle(FilledButtonStyle(fill: Theme.indigoButton))
                            .disabled(notes.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                            .accessibilityIdentifier("notes.save")
                    }
                    if let issue = notes.issue {
                        Text(issue).font(.rounded(.caption2)).foregroundStyle(Theme.amber).accessibilityIdentifier("notes.error")
                        if notes.pending != nil, !notes.busy {
                            Button("Discard draft") { discard = true }
                                .buttonStyle(.tap).foregroundStyle(Theme.muted).accessibilityIdentifier("notes.discard")
                        }
                    }
                    Text("Save to your AbstractNote notebook.").font(.rounded(.caption2)).foregroundStyle(Theme.muted)
                }
            }.padding(.horizontal, 4)
        }
        .screen("Notes")
        .onAppear { notes.bind(to: model.recordingConnectionKey) }
        .onDisappear { listener.cancel() }
        .confirmationDialog("Discard this draft?", isPresented: $discard, titleVisibility: .visible) {
            Button("Discard", role: .destructive) { notes.reset() }
            Button("Cancel", role: .cancel) {}
        } message: { Text("Any note already sent may still be saved in your notebook.") }
    }

    private func record() {
        let owner = model.recordingConnectionKey
        let client = model.client
        listener.start { outcome in
            guard owner == model.recordingConnectionKey else { return }
            switch outcome {
            case .speech(let wav): notes.transcribe(wav, client: client)
            case .nothingHeard: notes.noSpeech("No words were heard. Try again.")
            case .failed(let message): notes.noSpeech(message)
            }
        }
    }
}
