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
    /// This conversation's exchanges, oldest first (the earlier ones of a resumed session are read
    /// in the background): shown below the orb (the last 5, then older), shared by Share.
    @State private var exchanges: [Exchange] = []
    /// The exchange the voice is reading (the voice button reads the last one).
    @State private var readingId: String?
    @State private var shownCount = 5
    /// The server may hold older turns than those read (a resumed conversation).
    @State private var moreOnServer = false
    @State private var loadingOlder = false
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
                        ScreenCentered(width: geo.size.width) { side in
                            Orb(mode: orbMode, size: side, level: orbLevel, countdown: orbCountdown, since: listenSince, look: orbLook)
                                .contentShape(BelowTopRow())
                                .onTapGesture(perform: orbTapped)
                                // Hold: talk now, even while it speaks or is paused (cut in).
                                .onLongPressGesture(minimumDuration: 0.5) { if phase == .answer { startListening() } }
                                .accessibilityAddTraits(.isButton)
                                .accessibilityLabel(orbHint)
                        } bottom: {
                            VStack(spacing: 4) {
                                // Who answers, below the orb: only while the orb is at rest.
                                if controlsShown { responderSwitch }
                                Text(status).font(.rounded(.footnote)).foregroundStyle(statusColor)
                                    .multilineTextAlignment(.center).lineLimit(2).minimumScaleFactor(0.85)
                                    .shadow(color: .black, radius: 3)
                            }
                            .padding(.bottom, 8)   // low, clear of the orb and the round corners
                        }
                        // The keyboard, top right under the time: only while the orb is at rest (the
                        // same moments as who answers).
                        .overlay(alignment: .topTrailing) {
                            if controlsShown {
                                keyboardLink.buttonStyle(GlassPress()).padding(.trailing, 6).padding(.top, 2)
                            }
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
        // Beside Back: share this conversation (markdown), and go back 10 s while the orb speaks.
        #if DEBUG
        // UI tests read the voice's position here (a rewind must move it back).
        .overlay(alignment: .bottomLeading) {
            TimelineView(.periodic(from: .now, by: 0.25)) { _ in
                Text(String(format: "%.1f", speaker.position())).font(.system(size: 1)).opacity(0.01)
                    .accessibilityIdentifier("debug.position")
            }
        }
        #endif
        // Beside Back: share the conversation, and the voice button (play / pause the selected
        // message, hold to rewind), hidden while the orb listens or works, or with nothing to read.
        .besideBack {
            if !exchanges.isEmpty {
                ShareIcon(item: transcript, subject: model.responder.title)
            }
            if phase != .listening, phase != .thinking, let e = selected, !e.answer.isEmpty, e.scope != nil {
                VoiceButton(speaker: speaker, isCurrent: readingId == e.id) { read(e) }
            }
        }
        .task { await onOpen() }
        .onChange(of: model.path) { _, path in pathChanged(path) }
        // "New conversation" (in the Assistant ⌄ choice): this screen starts empty.
        // A new conversation, or another session: this screen starts over, unless it is the
        // session being resumed (its exchange is about to show).
        .onChange(of: model.askSessionId) { _, id in
            if model.resuming?.sessionId != id { model.resuming = nil; clearConversation() }
        }
        // The run on screen (followed or answered) is never also posted as a notification while active.
        .onChange(of: runId) { _, id in AnswerNotifier.shared.setShowing(id) }
    }

    /// Below the orb (scroll): what you said, the answer, the controls, who answers.
    /// The conversation as markdown: who asked what, and each answer as written.
    private var transcript: String {
        var out = "# \(model.responder.title)\n"
        for e in exchanges {
            if !e.prompt.isEmpty { out += "\n**You:** \(e.prompt)\n" }
            if !e.answer.isEmpty { out += "\n**\(model.responder.title):**\n\n\(e.answer)\n" }
        }
        return out
    }

    private var hasBelow: Bool {
        !exchanges.isEmpty || (!prompt.isEmpty && phase == .thinking) || model.sessionTrusted
    }

    /// The message shown in full (the conversation's last), the one the voice button reads.
    private var selected: Exchange? { exchanges.last }

    /// Reads one exchange's answer with the orb (the button, or a newly arrived answer).
    private func read(_ e: Exchange) {
        guard !e.answer.isEmpty, let scope = e.scope else { return }
        readingId = e.id
        if phase == .idle { phase = .answer }
        speaker.read(e.answer, scope: scope, client: model.client)
    }

    /// The earlier messages, newest first (as an automation's earlier runs).
    private var earlier: [Exchange] { Array(exchanges.dropLast().reversed()) }

    private func showOlder() async {
        shownCount += 5
        guard earlier.count < shownCount, moreOnServer, model.responder == .assistant else { return }
        loadingOlder = true
        defer { loadingOlder = false }
        let session = model.askSessionId
        let limit = shownCount + 1 + 5
        let more = await model.sessionExchanges(session, limit: limit)
        guard model.askSessionId == session, more.count >= exchanges.count else { return }
        exchanges = more
        moreOnServer = more.count >= limit
    }

    private var below: some View {
        VStack(alignment: .leading, spacing: 6) { belowContent }.padding(.horizontal, 10)
    }

    /// Below the orb, as an automation's page: the last message in full (its question, then the
    /// answer), then the earlier messages as small cards (5, Show older for the rest); a card opens
    /// that message.
    @ViewBuilder private var belowContent: some View {
        if let last = exchanges.last {
            MessageCard(text: last.answer) { QuestionCaption(text: last.prompt) }
        }
        // The question being worked on (its answer joins the exchanges when it arrives).
        if phase == .thinking, !prompt.isEmpty, exchanges.last?.prompt != prompt || exchanges.last?.answer.isEmpty == false {
            Text(prompt).font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.text2)
                .frame(maxWidth: .infinity, alignment: .leading).lineLimit(3)
        }
        if !earlier.isEmpty || moreOnServer {
            Text("Earlier messages").font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.text2).padding(.top, 6)
            ForEach(earlier.prefix(shownCount)) { e in
                NavigationLink(value: Route.message(title: model.responder.title, e)) { MessageRow(exchange: e) }
                    .buttonStyle(.plain)
            }
            if earlier.count > shownCount || moreOnServer {
                Button(loadingOlder ? "Loading…" : "Show older") { Task { await showOlder() } }
                    .buttonStyle(.plain).font(.rounded(.footnote)).foregroundStyle(Theme.cyan).disabled(loadingOlder)
            }
        }
        if model.sessionTrusted {
            Label("Tools allowed", systemImage: "checkmark.seal.fill")
                .font(.rounded(.caption2)).foregroundStyle(Theme.green.opacity(0.85))
                .frame(maxWidth: .infinity, alignment: .leading).padding(.top, 4)
        }
    }

    // MARK: - Pieces

    /// Who answers, below the orb: "Assistant ⌄", one tap opens the choice.
    private var responderSwitch: some View {
        NavigationLink(value: Route.picker) {
            HStack(spacing: 3) {
                Text(model.responder.title).font(.rounded(.headline, weight: .semibold))
                    .lineLimit(1).minimumScaleFactor(0.7)
                    .shadow(color: .black, radius: 3)
                Image(systemName: "chevron.down").font(.rounded(.caption2, weight: .bold))
            }
            .foregroundStyle(Theme.text)
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

    /// The keyboard and who answers show together, only while the orb is at rest: not listening,
    /// not working, not speaking (a paused or finished answer is at rest).
    private var controlsShown: Bool { phase == .idle || (phase == .answer && !speaker.isActive) }

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
                let text = try await model.client.transcribe(wav: wav, sessionId: model.askSessionId, model: VoicePrefs.transcription)
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
                    await model.ensureTools()
                    let id = try await model.client.startRun(prompt: text, sessionId: model.askSessionId, toolPolicy: model.runToolPolicy,
                                                                  tools: model.offeredTools)
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
        // A followed turn already listed (a resumed conversation) gets its answer; else it is new.
        let e = Exchange(id: runId ?? UUID().uuidString, prompt: prompt, answer: text,
                         scope: answerEntity.map { SpeechScope.entity($0) } ?? runId.map { SpeechScope.run($0) })
        if let i = exchanges.firstIndex(where: { $0.id == e.id }) { exchanges[i] = e } else { exchanges.append(e) }
        WKInterfaceDevice.current().play(.notification)
        speak()                                     // the speaker holds the app awake while it reads
        RuntimeKeeper.shared.release("ask")
        // Asked once, after the first answer (never over the orb while it listens): answers that
        // arrive while the app is not on screen come back as notifications.
        AnswerNotifier.shared.requestPermission()
    }

    private func speak() {
        guard speakAnswers, let e = exchanges.last, !e.answer.isEmpty else { return }
        read(e)
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
        exchanges = []; readingId = nil; shownCount = 5; moreOnServer = false
        phase = .idle
    }

    /// Opened from a notification (an answer to show and speak), from "Continue" on a session,
    /// or by a device test hook.
    private func onOpen() async {
        if let r = model.resuming {
            // Continue a session: open on its last exchange, quiet; the next tap talks in it.
            model.resuming = nil
            prompt = r.prompt; answer = r.answer; runId = r.runId
            note = r.title                                   // which conversation this is
            if !answer.isEmpty || !prompt.isEmpty { phase = .answer }
            exchanges = [Exchange(id: r.runId, prompt: r.prompt, answer: r.answer, scope: .run(r.runId))]
            // Its last turn is still working (or waits on an approval): follow it, as when asked here
            // (the status line then says what it does, not the title).
            if r.status == "running" || r.status == "waiting" { note = nil; resumeFollowing(r.runId) }
            let session = model.askSessionId
            let earlier = await model.sessionExchanges(session)
            if !earlier.isEmpty, model.askSessionId == session, exchanges.count <= 1 {
                exchanges = earlier; moreOnServer = earlier.count >= 10
            }
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
        await showCurrentConversation()
    }

    /// From Home, the orb talks in the current conversation: when it already has turns, it opens on
    /// its last exchange and its title (never a blank orb that files the next question under an old
    /// topic). New conversation (Sessions) starts an empty one.
    private func showCurrentConversation() async {
        guard model.responder == .assistant, exchanges.isEmpty, prompt.isEmpty,
              let s = model.sessions.first(where: { $0.id == model.askSessionId }) else { return }
        let last = await model.lastExchange(of: s)
        // Meanwhile the person may have started talking, or switched conversation.
        guard model.askSessionId == s.id, phase == .idle, prompt.isEmpty, !(last.prompt.isEmpty && last.answer.isEmpty) else { return }
        prompt = last.prompt; answer = last.answer; runId = last.runId
        note = model.title(of: s)
        phase = .answer
        exchanges = [Exchange(id: last.runId, prompt: last.prompt, answer: last.answer, scope: .run(last.runId))]
        if last.status == "running" || last.status == "waiting" { note = nil; resumeFollowing(last.runId); return }
        let session = s.id
        let earlier = await model.sessionExchanges(session)
        if !earlier.isEmpty, model.askSessionId == session, exchanges.count <= 1 {
            exchanges = earlier; moreOnServer = earlier.count >= 10
        }
    }
}
