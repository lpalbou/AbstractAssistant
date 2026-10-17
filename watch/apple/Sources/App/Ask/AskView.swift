import AbstractGatewayClient
import SwiftUI
import WatchKit

/// Ask: the orb is the assistant, pinned at the top and always visible; it is the only control
/// you need. Tap it to talk (its dots ripple with your voice; a dotted countdown runs once you
/// stop); tap again, or stay silent 3 s, to send. It thinks, then speaks the answer (rings with its
/// voice) while the answer scrolls in markdown just below. Tap while it speaks to pause or resume;
/// hold to cut in. The bottom bar has the keyboard (dictation, Scribble, keyboard), New, and Cancel
/// while something runs. The Assistant is a durable run (`POST /runs/start`); an entity is a
/// hosted conversation (`chat/open` then `turn`).
struct AskView: View {
    enum Phase: Hashable { case idle, listening, thinking, answer }

    @EnvironmentObject private var model: AppModel
    @Environment(\.scenePhase) private var scenePhase
    @StateObject private var listener = Listener()
    @StateObject private var speaker = Speaker()
    @AppStorage("ask.speak") private var speakAnswers = true

    @State private var phase: Phase
    @State private var prompt = ""
    @State private var answer = ""
    @State private var runId: String?
    @State private var answerEntity: String?
    @State private var error: String?
    @State private var note: String?
    @State private var step: String?
    @State private var transcribing = false
    @State private var ledgerCursor = 0
    @State private var listenSince: Date?
    /// An approval or question opened from here and not yet decided (Back keeps it pending).
    @State private var pendingWait: Wait?
    /// Bumped by Cancel, Back, New and every new turn: a late result from an older turn is dropped.
    @State private var turn = 0
    private let opening: AnswerRef?

    private static let demoPrompt = "Compare overall survival by treatment arm in the ADTTE I sent you"
    /// Ledger effect types in words for the status line; unknown types show nothing.
    private static let stepWords: [String: String] = [
        "llm_call": "thinking", "tool_calls": "using a tool", "start_subworkflow": "starting",
        "ask_user": "has a question", "wait_event": "waiting", "wait_until": "waiting", "answer_user": "answering",
    ]

    init(initialPhase: Phase = .idle, opening: AnswerRef? = nil) {
        self.opening = opening
        _phase = State(initialValue: initialPhase)
        // Screenshot states carry the mockups' content.
        switch initialPhase {
        case .listening: _listenSince = State(initialValue: Date())
        case .thinking: _prompt = State(initialValue: Self.demoPrompt)
        case .answer:
            _prompt = State(initialValue: Self.demoPrompt)
            _answer = State(initialValue: MockGatewayClient.markdownAnswer)
            _runId = State(initialValue: "7c1e02aa")
        case .idle: break
        }
    }

    var body: some View {
        VStack(spacing: 4) {
            header
            Orb(mode: orbMode, size: phase == .answer ? 58 : 104, level: orbLevel, countdown: orbCountdown, since: listenSince)
                .contentShape(Circle())
                .onTapGesture(perform: orbTapped)
                // Hold: talk now, even while it speaks or is paused (cut in).
                .onLongPressGesture(minimumDuration: 0.5) { if phase == .answer { startListening() } }
                .accessibilityAddTraits(.isButton)
                .accessibilityLabel(orbHint)
            Text(status).font(.rounded(.footnote)).foregroundStyle(statusColor)
                .multilineTextAlignment(.center).lineLimit(2).minimumScaleFactor(0.85)
            if phase == .answer, !answer.isEmpty {
                ScrollView {
                    VStack(alignment: .leading, spacing: 6) {
                        if !prompt.isEmpty {
                            Text(prompt).font(.rounded(.caption2)).foregroundStyle(Theme.muted).lineLimit(1)
                        }
                        MarkdownText(answer, font: .rounded(.body))
                        if let error { Text(error).font(.rounded(.caption2)).foregroundStyle(Theme.red) }
                        // After the answer, not over it: type a reply, or start a new conversation.
                        HStack(spacing: 6) {
                            keyboardLink.buttonStyle(.bordered)
                            Button { newConversation() } label: { BarIcon(symbol: "square.and.pencil") }
                                .buttonStyle(.bordered)
                                .accessibilityLabel("New conversation")
                        }
                        .padding(.top, 4)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            } else {
                if !prompt.isEmpty, phase == .thinking {
                    Text(prompt).font(.rounded(.footnote)).foregroundStyle(Theme.text2)
                        .multilineTextAlignment(.center).lineLimit(3)
                }
                if let error { Text(error).font(.rounded(.caption2)).foregroundStyle(Theme.red).multilineTextAlignment(.center).lineLimit(3) }
                Spacer(minLength: 0)
            }
        }
        .padding(.horizontal, 4)
        .background(Theme.ground)
        .navigationTitle(phase == .answer ? "Answer" : "Ask")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar { bottomBar }
        .task { await onOpen() }
        .onChange(of: model.path) { _, path in pathChanged(path) }
        // The run on screen (followed or answered) is never also posted as a notification while active.
        .onChange(of: runId) { _, id in AnswerNotifier.shared.setShowing(id) }
    }

    // MARK: - Pieces

    /// Who answers (one tap to change) and, when granted, the session's trust.
    private var header: some View {
        HStack(spacing: 4) {
            NavigationLink(value: Route.picker) {
                HStack(spacing: 3) {
                    Text(model.responder.title).font(.rounded(.caption2, weight: .semibold)).foregroundStyle(Theme.cyan)
                    Image(systemName: "chevron.down").font(.caption2).foregroundStyle(Theme.muted)
                }
            }
            .buttonStyle(.plain)
            .disabled(phase == .thinking || phase == .listening)
            Spacer()
            if model.sessionTrusted {
                Label("Trusted", systemImage: "checkmark.seal.fill").labelStyle(.titleAndIcon)
                    .font(.rounded(.caption2)).foregroundStyle(Theme.green.opacity(0.85))
                    .accessibilityLabel("Every tool in this conversation runs without asking, except sends")
            }
        }
    }

    /// The watch's text input (dictation, Scribble, keyboard) behind one keyboard icon.
    private var keyboardLink: some View {
        TextFieldLink(prompt: Text("Ask \(model.responder.title)")) {
            BarIcon(symbol: "keyboard")
        } onSubmit: { text in
            let t = text.trimmingCharacters(in: .whitespacesAndNewlines)
            if !t.isEmpty { speaker.stop(); send(t) }
        }
        .accessibilityLabel("Type or dictate")
    }

    /// Not in the answer state: the bar would cover the answer's first lines; the orb replies and
    /// pauses there, and the keyboard and New follow the answer.
    @ToolbarContentBuilder private var bottomBar: some ToolbarContent {
        ToolbarItemGroup(placement: .bottomBar) {
            if phase == .answer {
                EmptyView()
            } else if busy {
                Button(action: cancel) { BarIcon(symbol: "xmark") }
                    .tint(Theme.neutralButton)
                    .accessibilityLabel(phase == .listening ? "Stop listening" : phase == .thinking ? "Cancel" : "Stop the voice")
            } else {
                keyboardLink.tint(Theme.neutralButton)
            }
        }
    }

    private var busy: Bool { phase == .listening || (phase == .thinking && pendingWait == nil) || speaker.isActive }

    private var orbMode: Orb.Mode {
        switch phase {
        case .listening: return .listening
        case .thinking: return pendingWait == nil ? .thinking : .idle
        case .answer:
            switch speaker.state {
            case .speaking: return .speaking
            case .preparing: return .thinking
            default: return .idle
            }
        case .idle: return .idle
        }
    }

    private var orbLevel: (@MainActor () -> Double)? {
        if phase == .listening, listener.isListening { return { listener.currentLevel() } }
        if speaker.state == .speaking { return { speaker.level() } }
        return nil
    }

    private var orbCountdown: (@MainActor () -> Double)? {
        guard phase == .listening else { return nil }
        return { listener.sendProgress() }
    }

    private var orbHint: String {
        switch phase {
        case .listening: "Send what you said"
        case .answer where speaker.isActive: "Pause the voice"
        case .answer where speaker.isPaused: "Resume the voice"
        case .thinking: pendingWait == nil ? "Working" : "Review what is waiting for you"
        default: "Talk to \(model.responder.title)"
        }
    }

    private var status: String {
        if let note { return note }
        switch phase {
        case .idle: return "Tap and speak"
        case .listening: return listener.heardSpeech ? "Listening · tap to send" : "Listening…"
        case .thinking:
            if pendingWait != nil { return "Waiting for you · tap the orb" }
            if transcribing { return "Writing it down…" }
            return step.map { "Working · \($0)" } ?? "Working…"
        case .answer:
            switch speaker.state {
            case .preparing: return "Finding the voice…"
            case .speaking: return "Tap to pause · hold to reply"
            case .paused: return "Paused · tap to resume"
            case .failed(let why): return why
            default: return "Tap to reply"
            }
        }
    }

    private var statusColor: Color {
        if case .failed = speaker.state, phase == .answer { return Theme.red }
        switch phase {
        case .listening: return Theme.cyan
        case .thinking: return pendingWait == nil ? Theme.indigo : Theme.amber
        default: return Theme.muted
        }
    }

    // MARK: - Actions

    private func orbTapped() {
        switch phase {
        case .answer where speaker.isActive: speaker.pause(); WKInterfaceDevice.current().play(.click)
        case .answer where speaker.isPaused: speaker.resume(); WKInterfaceDevice.current().play(.click)
        case .idle, .answer: startListening()
        case .listening: listener.send()
        case .thinking: if let w = pendingWait { open(w) }   // otherwise nothing to do: no feedback
        }
    }

    private func pathChanged(_ path: [Route]) {
        let stillHere = path.contains { route in
            switch route { case .ask, .answer: return true; default: return false }
        }
        if !stillHere {
            // Leaving Ask (Back): nothing from this screen may keep running, speaking or pushing screens.
            turn += 1
            listener.cancel(); speaker.stop(); AnswerNotifier.shared.setShowing(nil)
            RuntimeKeeper.shared.release("ask")
            return
        }
        guard let last = path.last, let w = pendingWait else { return }
        switch last { case .ask, .answer: break; default: return }
        // Back on the orb from the approval or question: follow again only if it was decided.
        if model.decidedWaits.contains(w.id), let id = runId {
            pendingWait = nil
            resumeFollowing(id)
        }
    }

    private func open(_ w: Wait) {
        model.path.append(w.kind == .askUser ? .askUser(w) : .approval(w))
    }

    private func startListening() {
        RuntimeKeeper.shared.hold("ask")
        speaker.stop()
        turn += 1
        let mine = turn
        let back: Phase = answer.isEmpty ? .idle : .answer
        error = nil; note = nil; pendingWait = nil; phase = .listening; listenSince = Date()
        listener.start { outcome in
            guard mine == turn else { return }
            switch outcome {
            case .speech(let wav): transcribeAndSend(wav, turn: mine, back: back)
            case .nothingHeard: phase = back; note = "I didn't hear anything"; RuntimeKeeper.shared.release("ask")
            case .failed(let why): phase = back; error = why; RuntimeKeeper.shared.release("ask")
            }
        }
    }

    private func transcribeAndSend(_ wav: Data, turn mine: Int, back: Phase) {
        phase = .thinking; transcribing = true; prompt = ""
        WKInterfaceDevice.current().play(.stop)          // heard: the microphone is closed, sending
        Task {
            do {
                let text = try await model.client.transcribe(wav: wav, sessionId: model.askSessionId)
                guard mine == turn else { return }
                transcribing = false
                if text.isEmpty { phase = back; note = "I couldn't make out any words"; RuntimeKeeper.shared.release("ask"); return }
                send(text)
            } catch {
                guard mine == turn else { return }
                transcribing = false; phase = back
                self.error = "Transcription failed: \(error.localizedDescription)"
                RuntimeKeeper.shared.release("ask")
            }
        }
    }

    private func send(_ text: String) {
        RuntimeKeeper.shared.hold("ask")
        turn += 1
        let mine = turn
        prompt = text; answer = ""; error = nil; note = nil; step = nil; runId = nil; answerEntity = nil; pendingWait = nil
        phase = .thinking; transcribing = false
        Task {
            do {
                switch model.responder {
                case .assistant:
                    ledgerCursor = 0
                    let id = try await model.client.startRun(prompt: text, sessionId: model.askSessionId, toolPolicy: model.runToolPolicy)
                    guard mine == turn else {
                        // Cancelled (or left) while the run was starting: stop it on the gateway too.
                        try? await model.client.cancel(runId: id); return
                    }
                    runId = id
                    if !model.client.isMock { AnswerNotifier.shared.watch(runId: id, title: model.responder.title, prompt: text) }
                    try await follow(id, turn: mine)
                case .entity(let name):
                    let reply = try await model.entityTurn(name, text: text)
                    guard mine == turn else { return }
                    answerEntity = name
                    show(reply.isEmpty ? "(no reply)" : reply)
                    if scenePhase != .active {
                        await AnswerNotifier.shared.deliver(key: "entity-\(name)-\(Int(Date().timeIntervalSince1970))", title: model.responder.title,
                                                            ref: AnswerRef(text: answer, entity: name, prompt: text), answer: answer)
                    }
                }
            } catch {
                guard mine == turn else { return }
                self.error = error.localizedDescription
                phase = answer.isEmpty ? .idle : .answer
                RuntimeKeeper.shared.release("ask")
            }
        }
    }

    /// Polls GET /runs/{id} (and its ledger, for the step line) until the run ends or needs a person.
    /// A transient network error is retried (a watch's radio drops); 401/404 end it.
    private func follow(_ id: String, turn mine: Int) async throws {
        let interval: Duration = model.client.isMock ? .milliseconds(120) : .seconds(1)
        var failures = 0
        while mine == turn {
            let run: RunSummary
            do { run = try await model.client.run(id: id); failures = 0 }
            catch GatewayError.unauthorized { throw GatewayError.unauthorized }
            catch GatewayError.http(let status, let body) where status == 404 { throw GatewayError.http(status: status, body: body) }
            catch {
                failures += 1
                if failures >= 8 { throw error }
                try await Task.sleep(for: .seconds(2)); continue
            }
            if let page = try? await model.client.ledger(runId: id, after: ledgerCursor) {
                ledgerCursor = page.nextAfter ?? (ledgerCursor + page.items.count)
                if let last = page.items.last(where: { $0.status != "completed" || $0.effectType != nil }) {
                    step = Self.stepWords[last.effectType ?? ""] ?? (last.status == "waiting" ? "waiting" : nil)
                }
            }
            guard mine == turn else { return }
            if run.status == "waiting" {
                // The turn needs a person (approval/question) on this run or on the agent's child run.
                var wait = run.personWait
                if wait == nil, let child = run.waitingOnChild { wait = try? await model.client.run(id: child).personWait }
                if let w = wait, !model.decidedWaits.contains(w.id) {
                    if model.autoApprovable(w), await model.answer(w, with: .approve) {
                        step = "allowed \(w.toolName)"          // trusted session: the run goes on
                        model.markDecided(w)
                    } else {
                        // A person decides now; the screen is on. Waiting on them must not keep the app awake.
                        pendingWait = w
                        RuntimeKeeper.shared.release("ask")
                        open(w)
                        return
                    }
                }
            }
            if run.isTerminal {
                if run.status != "completed" { error = run.error ?? run.status }
                show(run.outputText ?? "(no output)")
                if scenePhase != .active {
                    await AnswerNotifier.shared.deliver(key: id, title: model.responder.title, ref: AnswerRef(runId: id, prompt: prompt), answer: answer)
                }
                return
            }
            try await Task.sleep(for: interval)
        }
    }

    private func resumeFollowing(_ id: String) {
        RuntimeKeeper.shared.hold("ask")
        let mine = turn
        phase = .thinking; step = nil
        Task {
            do { try await follow(id, turn: mine) }
            catch {
                guard mine == turn else { return }
                self.error = error.localizedDescription; phase = answer.isEmpty ? .idle : .answer
                RuntimeKeeper.shared.release("ask")
            }
        }
    }

    /// The answer arrives: shown below the orb, spoken by it.
    private func show(_ text: String) {
        answer = text; phase = .answer
        WKInterfaceDevice.current().play(.notification)
        speak()                                     // the speaker holds the app awake while it reads
        RuntimeKeeper.shared.release("ask")
        // Asked once, after the first answer (never over the orb while it listens): answers that
        // arrive while the app is not on screen come back as notifications.
        AnswerNotifier.shared.requestPermission()
    }

    private func speak() {
        guard speakAnswers, !answer.isEmpty else { return }
        if let name = answerEntity { speaker.read(answer, scope: .entity(name), client: model.client) }
        else if let id = runId { speaker.read(answer, scope: .run(id), client: model.client) }
    }

    private func cancel() {
        if phase == .listening {
            listener.cancel(); turn += 1; phase = answer.isEmpty ? .idle : .answer
            RuntimeKeeper.shared.release("ask"); return
        }
        if phase == .thinking {
            turn += 1
            if let id = runId, !transcribing { Task { try? await model.client.cancel(runId: id) } }
            transcribing = false; step = nil; pendingWait = nil
            phase = .idle; note = "Cancelled"; prompt = ""
            RuntimeKeeper.shared.release("ask")
            WKInterfaceDevice.current().play(.click)
            return
        }
        speaker.stop()
    }

    private func newConversation() {
        speaker.stop(); turn += 1
        prompt = ""; answer = ""; runId = nil; answerEntity = nil; note = nil; error = nil; pendingWait = nil
        model.newAskSession(); phase = .idle
    }

    /// Opened from a notification (an answer to show and speak), from "Continue" on a session,
    /// or by a device test hook.
    private func onOpen() async {
        if let r = model.resuming {
            // Continue a session: open on its last exchange, quiet; the next tap talks in it.
            model.resuming = nil
            prompt = r.prompt; answer = r.answer; runId = r.runId
            note = "Continuing · tap to talk"
            if !answer.isEmpty { phase = .answer }
            return
        }
        if let ref = opening, answer.isEmpty {
            prompt = ref.prompt ?? ""
            answerEntity = ref.entity
            runId = ref.runId
            if let text = ref.text { show(text); return }
            if let id = ref.runId, let run = try? await model.client.run(id: id) {
                show(run.outputText ?? run.error ?? "The run ended (\(run.status)).")
            }
            return
        }
        #if DEBUG
        if let t = model.testAsk { model.testAsk = nil; send(t); return }
        if model.testListen { model.testListen = false; startListening() }
        #endif
    }
}
