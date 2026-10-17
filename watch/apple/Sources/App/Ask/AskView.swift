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
    @State private var transcribing = false
    @State private var listenSince: Date?
    /// An approval or question opened from here and not yet decided (Back keeps it pending).
    @State private var pendingWait: Wait?
    /// Bumped by Cancel, Back, New and every new turn: a late result from an older turn is dropped.
    @State private var turn = 0
    private let opening: AnswerRef?

    private static let demoPrompt = "Compare overall survival by treatment arm in the ADTTE I sent you"

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
        GeometryReader { geo in
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(spacing: 6) {
                        // The orb fills the screen, centred in what is visible; everything else is below.
                        ZStack(alignment: .bottom) {
                            Orb(mode: orbMode, size: min(geo.size.width, geo.size.height + geo.safeAreaInsets.bottom), level: orbLevel, countdown: orbCountdown,
                                since: listenSince, look: orbLook)
                                .frame(width: geo.size.width, height: geo.size.height + geo.safeAreaInsets.bottom)   // the text below starts off screen
                                .contentShape(Rectangle())
                                .onTapGesture(perform: orbTapped)
                                // Hold: talk now, even while it speaks or is paused (cut in).
                                .onLongPressGesture(minimumDuration: 0.5) { if phase == .answer { startListening() } }
                                .accessibilityAddTraits(.isButton)
                                .accessibilityLabel(orbHint)
                            Text(status).font(.rounded(.footnote)).foregroundStyle(statusColor)
                                .multilineTextAlignment(.center).lineLimit(2).minimumScaleFactor(0.85)
                                .shadow(color: .black, radius: 3)
                                .padding(.bottom, geo.safeAreaInsets.bottom * 0.25)   // low, clear of the orb and the round corners
                        }
                        // One row, centred on one line: who answers left, the input icon right.
                        .overlay(alignment: .top) {
                            HStack(alignment: .center) { responderSwitch; Spacer(minLength: 4); inputButton }
                                .offset(y: -12)        // snug under the Back button and the time
                        }
                        .id("orb")
                        below
                    }
                }
                // Nothing below the orb yet (no question, no answer): the page does not move.
                .scrollDisabled(!hasBelow)
                .onChange(of: phase) { _, _ in withAnimation(.easeInOut(duration: 0.35)) { proxy.scrollTo("orb", anchor: .top) } }
            }
        }
        .background(Theme.ground)
        .task { await onOpen() }
        .onChange(of: model.path) { _, path in pathChanged(path) }
        // "New conversation" (in the Assistant ⌄ choice): this screen starts empty.
        .onChange(of: model.askSessionId) { _, _ in if model.resuming == nil { clearConversation() } }
        // The run on screen (followed or answered) is never also posted as a notification while active.
        .onChange(of: runId) { _, id in AnswerNotifier.shared.setShowing(id) }
    }

    /// Below the orb (scroll): what you said, the answer, the controls, who answers.
    private var hasBelow: Bool {
        (!prompt.isEmpty && phase != .idle && phase != .listening) || (phase == .answer && !answer.isEmpty) || model.sessionTrusted
    }

    private var below: some View {
        VStack(alignment: .leading, spacing: 6) { belowContent }.padding(.horizontal, 10)
    }

    @ViewBuilder private var belowContent: some View {
        if !prompt.isEmpty, phase != .idle, phase != .listening {
            Text(prompt).font(.rounded(.footnote)).foregroundStyle(Theme.text2)
                .frame(maxWidth: .infinity, alignment: .leading).lineLimit(3)
        }
        if phase == .answer, !answer.isEmpty {
            MarkdownText(answer, font: .rounded(.body))
        }
        if model.sessionTrusted {
            Label("Tools allowed", systemImage: "checkmark.seal.fill")
                .font(.rounded(.caption2)).foregroundStyle(Theme.green.opacity(0.85))
                .frame(maxWidth: .infinity, alignment: .leading).padding(.top, 4)
        }
    }

    // MARK: - Pieces

    /// The other input, top left: a tiny glass keyboard (dictation, Scribble, keyboard); while the orb
    /// listens, works or speaks the same button is ✕ (stop or cancel). The orb itself is the voice.
    @ViewBuilder private var inputButton: some View {
        Group {
            if busy {
                Button(action: cancel) { GlassIcon(symbol: "xmark") }
                    .accessibilityLabel(phase == .listening ? "Stop listening" : phase == .thinking ? "Cancel" : "Stop the voice")
            } else {
                keyboardLink
            }
        }
        .buttonStyle(.plain)
        .padding(.trailing, 6)
    }

    /// Who answers, top right under the clock: "Assistant ⌄", one tap opens the choice.
    private var responderSwitch: some View {
        NavigationLink(value: Route.picker) {
            HStack(spacing: 3) {
                Text(model.responder.title).font(.rounded(.headline, weight: .semibold))
                    .lineLimit(1).minimumScaleFactor(0.7)
                Image(systemName: "chevron.down").font(.rounded(.caption2, weight: .bold))
            }
            .foregroundStyle(phase == .thinking || phase == .listening ? Theme.muted : Theme.text)
            .padding(.leading, 8)
        }
        .buttonStyle(.plain)
        .disabled(phase == .thinking || phase == .listening)
        .accessibilityLabel("Talking to \(model.responder.title). Choose who answers")
    }

    /// The watch's text input (dictation, Scribble, keyboard) behind one keyboard icon.
    private var keyboardLink: some View {
        TextFieldLink(prompt: Text("Ask \(model.responder.title)")) {
            GlassIcon(symbol: "keyboard")
        } onSubmit: { text in
            let t = text.trimmingCharacters(in: .whitespacesAndNewlines)
            if !t.isEmpty { speaker.stop(); send(t) }
        }
        .accessibilityLabel("Type or dictate")
    }

    /// The orb of whoever answers: the entity that wrote the answer on screen (it may not be the
    /// responder now selected), else the selected responder.
    private var orbLook: OrbLook { answerEntity.map { model.look(for: .entity($0)) } ?? model.responderLook }

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
        if let error { return error }
        if let note { return note }
        switch phase {
        case .idle: return "Tap to talk"
        case .listening: return "Listening…"
        case .thinking: return pendingWait != nil ? "Needs you" : "Thinking…"
        case .answer:
            switch speaker.state {
            case .preparing, .speaking: return ""
            case .paused: return "Paused"
            case .failed: return "Voice unavailable"
            default: return ""
            }
        }
    }

    private var statusColor: Color {
        if error != nil { return Theme.red }
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
                if text.isEmpty { phase = back; note = "I didn't catch that"; RuntimeKeeper.shared.release("ask"); return }
                send(text)
            } catch {
                guard mine == turn else { return }
                transcribing = false; phase = back
                self.error = "I couldn't hear that."
                RuntimeKeeper.shared.release("ask")
            }
        }
    }

    private func send(_ text: String) {
        RuntimeKeeper.shared.hold("ask")
        turn += 1
        let mine = turn
        prompt = text; answer = ""; error = nil; note = nil; runId = nil; answerEntity = nil; pendingWait = nil
        phase = .thinking; transcribing = false
        Task {
            do {
                switch model.responder {
                case .assistant:
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
                    if reply.isEmpty { fail("No answer.") } else { show(reply) }
                    if scenePhase == .background {   // wrist down, app still in front: the orb speaks it
                        await AnswerNotifier.shared.deliver(key: "entity-\(name)-\(Int(Date().timeIntervalSince1970))", title: model.responder.title,
                                                            ref: AnswerRef(text: answer, entity: name, prompt: text), answer: answer)
                    }
                }
            } catch {
                guard mine == turn else { return }
                fail(Self.human(error))
            }
        }
    }

    /// A turn that ends without an answer: one short line in the status, the last answer kept.
    private func fail(_ message: String) {
        error = message
        phase = answer.isEmpty ? .idle : .answer
        RuntimeKeeper.shared.release("ask")
    }

    static func human(_ e: Error) -> String { AppModel.say(e) }

    /// Polls GET /runs/{id} until the run ends or needs a person.
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
            guard mine == turn else { return }
            if run.status == "waiting" {
                // The turn needs a person (approval/question) on this run or on the agent's child run.
                var wait = run.personWait
                if wait == nil, let child = run.waitingOnChild { wait = try? await model.client.run(id: child).personWait }
                if let w = wait, !model.decidedWaits.contains(w.id) {
                    if model.autoApprovable(w), await model.answer(w, with: .approve) {
                        model.markDecided(w)                   // trusted session: the run goes on
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
                if let out = run.outputText, !out.isEmpty { show(out) }
                else { fail(run.status == "cancelled" ? "Stopped" : "That didn't work. Try again."); return }
                if scenePhase == .background {   // wrist down, app still in front: the orb speaks it
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
        phase = .thinking
        Task {
            do { try await follow(id, turn: mine) }
            catch {
                guard mine == turn else { return }
                fail(Self.human(error))
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
            transcribing = false; pendingWait = nil
            phase = .idle; note = "Cancelled"; prompt = ""
            RuntimeKeeper.shared.release("ask")
            WKInterfaceDevice.current().play(.click)
            return
        }
        speaker.stop()
    }

    private func clearConversation() {
        speaker.stop(); listener.cancel(); turn += 1
        prompt = ""; answer = ""; runId = nil; answerEntity = nil; note = nil; error = nil; pendingWait = nil
        phase = .idle
    }

    /// Opened from a notification (an answer to show and speak), from "Continue" on a session,
    /// or by a device test hook.
    private func onOpen() async {
        if let r = model.resuming {
            // Continue a session: open on its last exchange, quiet; the next tap talks in it.
            model.resuming = nil
            prompt = r.prompt; answer = r.answer; runId = r.runId
            if !answer.isEmpty { phase = .answer }
            return
        }
        if let ref = opening, answer.isEmpty {
            prompt = ref.prompt ?? ""
            answerEntity = ref.entity
            runId = ref.runId
            if let text = ref.text { show(text); return }
            if let id = ref.runId, let run = try? await model.client.run(id: id) {
                if let out = run.outputText, !out.isEmpty { show(out) } else { error = "No answer." }
            }
            return
        }
        #if DEBUG
        if let t = model.testAsk { model.testAsk = nil; send(t); return }
        if model.testListen { model.testListen = false; startListening() }
        #endif
    }
}
