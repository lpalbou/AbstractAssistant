import AbstractGatewayClient
import SwiftUI
import WatchKit

/// The orb page, one for every conversation: the current conversation (the Assistant or an entity)
/// and an automation (whose messages its trigger sends) look and behave the same; an automation
/// adds (i) for its details. The orb fills the screen; tap it to talk (its dots ripple with your
/// voice; a dotted countdown runs once you stop); tap again, or stay silent 3 s, to send. It thinks,
/// then speaks the answer while it scrolls in markdown below. Tap while it speaks to pause or
/// resume; hold to stop. The keyboard sits top right, the tools bottom right. The Assistant is a
/// durable run (`POST /runs/start`); an entity is a hosted conversation (`chat/open` then `turn`);
/// talking on an automation's page opens a conversation about it (`/discuss`), which the page
/// continues as a chat (`AutomationFeed`).
struct AskView: View {
    enum Phase: Hashable { case idle, listening, thinking, answer }

    @EnvironmentObject private var model: AppModel
    @Environment(\.scenePhase) private var scenePhase
    @StateObject private var listener = Listener()
    @StateObject private var speaker = Speaker()
    /// The run working on the question: its steps under the orb, its pulses in the orb.
    @StateObject private var activity = RunActivity()
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
    /// The conversation's history is being read (one request, after its last exchange shows).
    @State private var loadingOlder = false
    /// The history could not be read: the session and its newest run, for Retry.
    @State private var historyFailed: (id: String, run: String)?
    /// The conversation's images and recordings could not be read (the text did): Retry reads them.
    @State private var mediaFailed: String?
    @State private var runId: String?
    @State private var answerEntity: String?
    @State private var error: String?
    @State private var note: String?
    /// A question whose sending failed, its recording kept (`KeptQuestion`): Retry and Discard
    /// under the orb while it is at rest, until the person chooses.
    @State private var kept: URL? = KeptQuestion.url
    /// A hold on the orb under way, and how far its ring has closed.
    @State private var holding = false
    @State private var holdProgress: CGFloat = 0
    /// When the finger landed on the orb: a press longer than a tap is a hold, even let go early.
    @State private var pressedAt: Date?
    @State private var transcribing = false
    @State private var listenSince: Date?
    /// An approval or question opened from here and not yet decided (Back keeps it pending).
    @State private var pendingWait: Wait?
    /// Bumped by Cancel, Back, New and every new turn: a late result from an older turn is dropped.
    @State private var turn = 0
    private let opening: AnswerRef?
    /// What it talks in (an automation becomes a chat once you talk about it).
    @State private var conversation: Conversation
    /// The automation's runs, run in progress, Stop and Seen (nil for a chat).
    @State private var feed: AutomationFeed?
    /// A conversation this page moved into itself (a notification's, an automation's discussion):
    /// the current conversation changing to it is no reason to start over.
    @State private var adopted: String?
    /// The page has opened (a later appearance is a return to it).
    @State private var opened = false
    /// An automation's runs have been read once (or the read failed): its spinner goes.
    @State private var runsRead = false
    /// Each time the page comes to the front (an automation's page checks its runs again then).
    @State private var appearances = 0
    /// An automation's run stopped here (the automation goes on): it is not followed again.
    @State private var stoppedRun: String?
    /// The automation's runs followed live on this page (kept when its runs are read again), and
    /// when the one followed now started.
    @State private var liveRuns: Set<String> = []
    @State private var liveWhen: String?
    /// The automation's page has read its runs, their media and marked them seen (a first opening
    /// cut short finishes when the page is back).
    @State private var automationRead = false
    /// Where an automation page's spoken question is filed before it has a conversation of its own
    /// (never the automation's conversation, nor the current chat).
    @State private var voiceSession = AppModel.newSessionId()

    private static let demoPrompt = "Compare overall survival by treatment arm in the ADTTE I sent you"

    init(initialPhase: Phase = .idle, opening: AnswerRef? = nil, automation: AutomationSummary? = nil) {
        self.opening = opening
        _phase = State(initialValue: initialPhase)
        _conversation = State(initialValue: automation.map { .automation($0) } ?? .chat)
        _feed = State(initialValue: automation.map(AutomationFeed.init))
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
                        // The orb fills the screen, centred on it; everything else is below.
                        ScreenCentered(width: geo.size.width, top: geo.frame(in: .global).minY) { side in
                            Orb(mode: orbMode, size: side * 0.9, voice: orbVoice, countdown: orbCountdown, since: listenSince, look: orbLook,
                                work: phase == .thinking && activity.isFollowing ? { @MainActor @Sendable t in activity.orb(at: t) } : nil)
                                .contentShape(Circle())
                                .onTapGesture(perform: orbTapped)
                                // Hold: a ring closes round the orb in about a second, then it stops what
                                // it is doing (listening, working, speaking), or at rest reads the last
                                // answer aloud (let go before: nothing happens). The ring stays well
                                // inside the screen (the orb's glow reaches its edge).
                                .onLongPressGesture(minimumDuration: Self.holdToToggle, perform: holdDone, onPressingChanged: holdChanged)
                                .overlay { if holding { HoldRing(progress: holdProgress).frame(width: side * 0.62, height: side * 0.62) } }
                                // Its conversation is still on its way: a large spinner over a quiet orb.
                                .opacity(loadingConversation ? 0.3 : 1)
                                .overlay {
                                    if loadingConversation {
                                        ProgressView().controlSize(.large).tint(Theme.text).scaleEffect(1.4)
                                            .accessibilityLabel("Loading").accessibilityIdentifier("ask.loading")
                                    }
                                }
                                .animation(.easeOut(duration: 0.25), value: loadingConversation)
                                .accessibilityAddTraits(.isButton)
                                .accessibilityLabel(orbHint)
                                .accessibilityAction(named: busy ? "Stop" : "Read aloud") { holdDone() }
                        } bottom: {
                            VStack(spacing: 4) {
                                // Who answers, below the orb: only while the orb is at rest.
                                if controlsShown { if let a = automationFeed { automationName(a) } else { responderSwitch } }
                                Text(status).font(.rounded(.footnote)).foregroundStyle(statusColor)
                                    .multilineTextAlignment(.center).lineLimit(2).minimumScaleFactor(0.85)
                                    .accessibilityIdentifier("ask.status")

                                    .shadow(color: .black, radius: 3)
                                if keptShown { keptActions }
                            }
                            .padding(.bottom, 8)   // low, clear of the orb and the round corners
                        }
                        // The keyboard, top right under the time: only while the orb is at rest (the
                        // same moments as who answers).
                        .overlay(alignment: .topTrailing) {
                            if controlsShown {
                                keyboardLink.buttonStyle(GlassPress()).padding(.trailing, 6 - Self.reach).padding(.top, 2 - Self.reach)
                            }
                        }
                        // The tools of this conversation, bottom right, mirroring the keyboard (as far
                        // above the bottom as the keyboard is below the top: the row's band and 2 pt); shown with the keyboard
                        // (the Assistant's tools; an entity brings its own).
                        // While it listens, Send sits there instead: what was said goes now (a noise
                        // that starts would otherwise keep the silence that sends from coming).
                        .overlay(alignment: .bottomTrailing) {
                            if controlsShown, let a = automationFeed {
                                // An automation's tools are in its details (Edit), with when it runs.
                                infoLink(a).padding(.trailing, 6 - Self.reach).padding(.bottom, CornerButton.band + 2 - Self.reach)
                            } else if controlsShown, model.responder == .assistant {
                                toolsLink.padding(.trailing, 6 - Self.reach).padding(.bottom, CornerButton.band + 2 - Self.reach)
                            } else if phase == .listening {
                                sendNow.padding(.trailing, 6 - Self.reach).padding(.bottom, CornerButton.band + 2 - Self.reach)
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
            if UITestHooks.on { TimelineView(.periodic(from: .now, by: 0.25)) { _ in
                Text(String(format: "%.1f", speaker.position())).font(.system(size: 1)).opacity(0.01)
                    .accessibilityIdentifier("debug.position")
            } }
        }
        #endif
        // Beside Back, following what it does: Stop while it is busy, Share at rest; the shield while
        // it works after an Accept all; the voice button (play / pause the selected message, hold to
        // rewind), hidden while the orb listens or works, or with nothing to read.
        .besideBack {
            // The first slot follows what it does: Stop while it is busy (listening, working, speaking),
            // Share at rest. While it works after an Accept all, the shield beside it takes it back.
            ZStack {
                if busy {
                    Button(action: stopBusy) { GlassIcon(symbol: "stop.fill", size: CornerButton.size).rowReach() }
                        .buttonStyle(GlassPress())
                        .accessibilityLabel(phase == .listening ? "Stop listening" : "Stop")
                        .accessibilityIdentifier("ask.stop")
                        .transition(.scale(scale: 0.6).combined(with: .opacity))
                } else if !exchanges.isEmpty {
                    ShareIcon(item: transcript, subject: speakerTitle)
                        .transition(.scale(scale: 0.6).combined(with: .opacity))
                }
            }
            .animation(.easeInOut(duration: 0.25), value: busy)
            if phase == .thinking, !model.trust(trustOwner).isEmpty {
                TrustShield(owner: trustOwner).transition(.scale(scale: 0.6).combined(with: .opacity))
            }
            if phase != .listening, phase != .thinking, let e = selected, !e.answer.isEmpty, e.scope != nil {
                VoiceButton(speaker: speaker, isCurrent: readingId == e.id) { read(e) }
            }
        }
        .task { await onOpen() }
        // An automation's page notices a run starting (its schedule, or Run now on its details).
        // The task ends when the page is covered or left, and starts again when it is back in front.
        .onAppear { appearances += 1; kept = KeptQuestion.url }
        .task(id: automationFeed.map { "\($0.id)#\(appearances)" }) { await watchAutomation() }
        // A message of the Assistant's conversation on screen: a swipe forward opens its stats page
        // (an entity's exchanges, or an answer opened from a notification, may be another conversation's).
        .onChange(of: exchanges.last?.id, initial: true) { _, run in
            if run != nil, opening == nil, conversation == .chat, model.responder == .assistant { model.noteMessages(in: model.askSessionId, runId: run) }
        }
        .onChange(of: model.path) { _, path in pathChanged(path) }
        // "New conversation" (in the Assistant ⌄ choice): this screen starts empty.
        // A new conversation, or another session: this screen starts over, unless it is the
        // session being resumed (its exchange is about to show).
        .onChange(of: model.askSessionId) { _, id in
            guard conversation == .chat, id != adopted else { return }
            if model.resuming?.sessionId != id { model.resuming = nil; clearConversation() }
        }
        // The run on screen (followed or answered) is never also posted as a notification while active.
        .onChange(of: runId) { _, id in AnswerNotifier.shared.setShowing(id) }
        // Screen off or app not in front: the steps are not read (the answer still is). Leaving the
        // app with a run still working: its end is followed in the background, to be posted.
        .onChange(of: scenePhase) { _, p in
            activity.paused = p != .active
            if p == .background, phase == .thinking, !transcribing, pendingWait == nil, let id = runId, !model.client.isMock {
                AnswerNotifier.shared.watch(runId: id, title: speakerTitle, prompt: prompt)
            }
        }
    }

    /// The page's automation while it is one (not yet a conversation about it).
    private var automationFeed: AutomationFeed? { if case .automation = conversation { feed } else { nil } }

    /// Whose Approve all this page shows (its shield): the automation's, or the conversation's.
    private var trustOwner: WaitOwner { automationFeed.map { .automation($0.id) } ?? .session(model.askSessionId) }

    /// Who speaks here: the automation, or whoever answers the conversation.
    private var speakerTitle: String { automationFeed?.title ?? model.responder.title }

    /// The automation's name below the orb (where a conversation shows who answers).
    private func automationName(_ a: AutomationFeed) -> some View {
        Text(a.title).font(.rounded(.headline, weight: .semibold)).foregroundStyle(Theme.text)
            .lineLimit(1).minimumScaleFactor(0.7).shadow(color: .black, radius: 3)
            .accessibilityIdentifier("ask.automation")
    }

    /// Below the orb (scroll): what you said, the answer, the controls, who answers.
    /// The conversation as markdown: who asked what, and each answer as written.
    private var transcript: String {
        var out = "# \(speakerTitle)\n"
        for e in exchanges {
            if !e.prompt.isEmpty { out += "\n**\(e.when.map { "Sent \($0)" } ?? "You"):** \(e.prompt)\n" }
            if !e.answer.isEmpty { out += "\n**\(speakerTitle):**\n\n\(e.answer)\n" }
        }
        return out
    }

    private var hasBelow: Bool {
        !exchanges.isEmpty || (!prompt.isEmpty && phase == .thinking)
    }

    /// The message shown in full (the conversation's last), the one the voice button reads.
    private var selected: Exchange? { exchanges.last }

    /// Reads one exchange's answer with the orb (the button, or a newly arrived answer), then plays
    /// the recordings it made.
    private func read(_ e: Exchange) {
        guard !e.answer.isEmpty, let scope = e.scope else { return }
        readingId = e.id
        note = nil; error = nil                             // a note on the last listening ends as it speaks
        if phase == .idle { phase = .answer }
        speaker.read(e.answer, scope: scope, client: model.client, clips: e.media)
    }

    /// A recording's row on the orb page: it plays through the orb.
    private func playClip(_ item: MediaItem) {
        if phase == .listening || phase == .thinking { return }
        // Its own row again: pause, or go on.
        if readingId == "clip:" + item.id, speaker.isActive || speaker.isPaused {
            if speaker.isActive { speaker.pause() } else { speaker.resume() }
            WKInterfaceDevice.current().play(.click)
            return
        }
        readingId = "clip:" + item.id
        note = nil; error = nil
        if phase == .idle { phase = .answer }
        speaker.play(clips: [item], client: model.client)
        WKInterfaceDevice.current().play(.click)
    }

    /// The earlier messages, newest first (as an automation's earlier runs).
    private var earlier: [Exchange] { Array(exchanges.dropLast().reversed()) }

    private func showOlder() { shownCount += 5 }

    private var below: some View {
        VStack(alignment: .leading, spacing: 6) { belowContent }.padding(.horizontal, 10)
    }

    /// Below the orb, as an automation's page: the last message in full (its question, then the
    /// answer), then the earlier messages as small cards (5, Show older for the rest); a card opens
    /// that message.
    @ViewBuilder private var belowContent: some View {
        // While it works: its steps, live, in place of the conversation (which returns with the answer).
        if phase == .thinking, activity.runId != nil, automationFeed != nil || model.responder == .assistant {
            ActivityPanel(activity: activity, prompt: prompt, openWait: pendingWait.map { w in { open(w) } })
        } else {
            messages
        }
    }

    @ViewBuilder private var messages: some View {
        if let last = exchanges.last {
            MessageCard(text: last.answer, failed: last.failed, media: last.media, play: playClip) { ExchangeCaption(exchange: last) }
            WorkLink(runId: last.id)
        }
        // The question being worked on (its answer joins the exchanges when it arrives).
        if phase == .thinking, !prompt.isEmpty, exchanges.last?.prompt != prompt || exchanges.last?.answer.isEmpty == false {
            Text(prompt).font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.text2)
                .frame(maxWidth: .infinity, alignment: .leading).lineLimit(3)
        }
        if !earlier.isEmpty {
            Text("Earlier messages").font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.text2).padding(.top, 6)
            ForEach(earlier.prefix(shownCount)) { e in
                NavigationLink(value: Route.message(title: speakerTitle, e)) { MessageRow(exchange: e) }
                    .buttonStyle(.tap)
                    .accessibilityIdentifier("message.row")
            }
            if earlier.count > shownCount {
                Button("Show older") { showOlder() }
                    .buttonStyle(.tap).font(.rounded(.footnote)).foregroundStyle(Theme.cyan)
            }
        }
        // The conversation's history is read in one request; when it fails the page says so
        // (a partial list must never pass for the whole conversation).
        if loadingOlder {
            HStack(spacing: 6) { ProgressView().frame(width: 16); Text("Loading earlier messages…") }
                .font(.rounded(.footnote)).foregroundStyle(Theme.muted).padding(.top, 6)
        } else if let session = historyFailed {
            Button("Couldn't load earlier messages. Retry") {
                Task { if let a = automationFeed { await openAutomation(a) } else { await loadHistory(session.id, latestRun: session.run) } }
            }
                .buttonStyle(.tap).font(.rounded(.footnote)).foregroundStyle(Theme.amber).padding(.top, 6)
        } else if let session = mediaFailed {
            Button("Couldn't load images and recordings. Retry") { Task { await loadMedia(session) } }
                .buttonStyle(.tap).font(.rounded(.footnote)).foregroundStyle(Theme.amber).padding(.top, 6)
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
        .buttonStyle(.tap)
        .disabled(phase == .thinking || phase == .listening)
        .accessibilityLabel("Talking to \(model.responder.title). Choose who answers")
    }

    /// The tools this conversation may use (Off · Auto · Ask each); a dot when they differ from the
    /// defaults of Settings → Tools.
    private var toolsLink: some View {
        NavigationLink(value: Route.tools(.session)) {
            GlassIcon(symbol: "wrench.and.screwdriver")
                .overlay(alignment: .topTrailing) {
                    if model.sessionDiffers {
                        Circle().fill(Theme.amber).frame(width: 8, height: 8).offset(x: 1, y: -1)
                    }
                }
                .padding(Self.reach).contentShape(Rectangle())
        }
        .buttonStyle(GlassPress())
        .accessibilityLabel(model.sessionDiffers ? "Tools, changed for this conversation" : "Tools")
        .accessibilityIdentifier("ask.tools")
    }

    /// An automation's details (when it runs, Edit, Run now), where a conversation has its tools; a
    /// swipe forward opens them too.
    private func infoLink(_ a: AutomationFeed) -> some View {
        Button { model.path.append(.automationInfo(a.automation)) } label: {
            GlassIcon(symbol: "info").padding(Self.reach).contentShape(Rectangle())
        }
        .buttonStyle(GlassPress())
        .accessibilityLabel("About this automation")
        .accessibilityIdentifier("ask.info")
    }

    /// Ends the listening now and sends what was said (the orb's tap does the same).
    private var sendNow: some View {
        Button { listener.send() } label: {
            GlassIcon(symbol: "paperplane.fill").padding(Self.reach).contentShape(Rectangle())
        }
        .buttonStyle(GlassPress())
        .accessibilityLabel("Send now")
        .accessibilityIdentifier("ask.send")
    }

    /// The watch's text input (dictation, Scribble, keyboard) behind one keyboard icon.
    private var keyboardLink: some View {
        TextFieldLink(prompt: Text("Ask \(speakerTitle)")) {
            GlassIcon(symbol: "keyboard").padding(Self.reach).contentShape(Rectangle())
        } onSubmit: { text in
            let t = text.trimmingCharacters(in: .whitespacesAndNewlines)
            if !t.isEmpty { speaker.stop(); send(t) }
        }
        .accessibilityLabel("Type or dictate")
    }

    /// The orb of whoever answers: the entity that wrote the answer on screen (it may not be the
    /// responder now selected), else the selected responder.
    private var orbLook: OrbLook {
        if automationFeed != nil { return model.look(for: .assistant) }
        return answerEntity.map { model.look(for: .entity($0)) } ?? model.responderLook
    }

    /// The keyboard and who answers show together, only while the orb is at rest: not listening,
    /// not working, not speaking (a paused or finished answer is at rest).
    /// The voice is engaged: it speaks, or is paused (a tap pauses or resumes; Stop ends it, and the
    /// next tap listens).
    private var voiceEngaged: Bool { phase == .answer && (speaker.isActive || speaker.isPaused) }

    /// How far beyond its circle a corner icon still takes a tap (the orb takes every tap around it,
    /// and a 35 pt circle is a narrow target on the wrist).
    static let reach: CGFloat = 10

    /// How long a hold on the orb takes to toggle between listening and reading (1.05 s: 30 %
    /// less than the 1.5 s it was, which read as a wait).
    static let holdToToggle: Double = 1.05

    /// At rest with an answer to read: a hold reads it aloud (the last one).
    private var canReadLast: Bool {
        guard phase == .idle || phase == .answer, !voiceEngaged, let e = selected else { return false }
        return !e.answer.isEmpty && e.scope != nil
    }

    /// Busy: it listens, works (thinking, tools) or its voice is engaged; Stop (and a hold) ends it.
    private var busy: Bool { phase == .listening || phase == .thinking || voiceEngaged }

    /// Ends what it is doing: the voice; or the listening or the work (the run is cancelled). The
    /// next tap listens.
    private func stopBusy() {
        holding = false; holdProgress = 0
        if voiceEngaged { stopVoice() } else { cancel() }
    }

    /// The hold: busy, it stops (the next tap listens); at rest, it reads the last answer aloud.
    private func holdDone() {
        if busy { stopBusy(); return }
        holding = false; holdProgress = 0
        guard canReadLast, let e = selected else { return }
        WKInterfaceDevice.current().play(.start)
        read(e)
    }

    /// Ends the voice: the orb is at rest on its answer, and the next tap listens.
    private func stopVoice() {
        holding = false; holdProgress = 0
        guard voiceEngaged else { return }
        speaker.stop()
        WKInterfaceDevice.current().play(.stop)
    }

    /// The hold's ring: it starts closing a moment after the finger lands (a tap shows nothing) and
    /// is full when the hold stops the voice; let go before, it goes away.
    private func holdChanged(_ pressing: Bool) {
        if pressing { pressedAt = Date() }
        guard pressing, busy || canReadLast else {
            withAnimation(.easeOut(duration: 0.15)) { holdProgress = 0 }
            holding = false
            return
        }
        holding = true; holdProgress = 0
        withAnimation(.linear(duration: Self.holdToToggle - 0.2).delay(0.2)) { holdProgress = 1 }
    }

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

    private var orbVoice: (@MainActor (Double) -> VoiceFeatures)? {
        if phase == .listening, listener.isListening { return { listener.features(at: $0) } }
        if speaker.state == .speaking { return { speaker.features(at: $0) } }
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
        default: "Talk to \(speakerTitle)"
        }
    }

    /// The page's conversation (an automation's runs, a notification's answer) is not in yet.
    private var loadingConversation: Bool {
        exchanges.isEmpty && phase != .listening && phase != .thinking && historyFailed == nil
            && ((automationFeed != nil && !runsRead) || (automationFeed == nil && loadingOlder)
                || (opening != nil && answer.isEmpty && error == nil))
    }

    private var status: String {
        if loadingConversation { return "Loading…" }
        // While the orb speaks its line is empty: nothing said before (a note, an error) shows over it.
        if phase == .answer, speaker.isActive { return "" }
        if let error { return error }
        if let note { return note }
        if keptShown { return Self.keptLine }
        switch phase {
        case .idle: return "Tap to talk"
        case .listening: return "Listening…"
        case .thinking: return pendingWait != nil ? "Needs you" : (activity.now.map { $0 + "…" } ?? "Thinking…")
        case .answer:
            switch speaker.state {
            case .preparing, .speaking: return ""
            case .paused: return "Paused"
            case .failed: return "Voice unavailable"
            default: return "Tap to talk"                    // at rest the orb listens again
            }
        }
    }

    private var statusColor: Color {
        if error != nil { return Theme.red }
        if keptShown, note == nil { return Theme.amber }
        if case .failed = speaker.state, phase == .answer { return Theme.red }
        switch phase {
        case .listening: return Theme.cyan
        case .thinking: return pendingWait == nil ? Theme.indigo : Theme.amber
        default: return Theme.muted
        }
    }

    /// The line under the orb while a failed question's recording is kept.
    static let keptLine = "Not sent."   // short: the line shares its row with the tools icon

    /// A kept recording is offered while the orb is at rest (not while it listens, works or speaks).
    private var keptShown: Bool { kept != nil && controlsShown && !loadingConversation }

    /// Under the kept line: Retry sends the recording again, Discard deletes it.
    private var keptActions: some View {
        HStack(spacing: 6) {
            Button("Retry", action: retryKept)
                .buttonStyle(KeptButtonStyle(fill: Theme.indigoButton))
                .accessibilityIdentifier("ask.retry")
            Button("Discard", action: discardKept)
                .buttonStyle(KeptButtonStyle(fill: Theme.neutralButton))
                .accessibilityIdentifier("ask.discard")
        }
        .padding(.horizontal, 44)       // clear of the corner icons and the round corners
    }

    // MARK: - Actions

    private func orbTapped() {
        // A hold let go before the ring closed is not a tap: nothing happens.
        defer { pressedAt = nil }
        if let at = pressedAt, Date().timeIntervalSince(at) > 0.35 { return }
        switch phase {
        case .answer where speaker.isActive: speaker.pause(); WKInterfaceDevice.current().play(.click)
        case .answer where speaker.isPaused: speaker.resume(); WKInterfaceDevice.current().play(.click)
        case .idle, .answer: startListening()
        case .listening: listener.send()
        case .thinking: if let w = pendingWait { open(w) }   // otherwise nothing to do: no feedback
        }
    }

    private func pathChanged(_ path: [Route]) {
        let stillHere = path.contains(where: \.isOrbPage)
        if !stillHere {
            // Leaving Ask (Back): nothing from this screen may keep running, speaking or pushing screens.
            turn += 1
            listener.cancel(); speaker.stop(); activity.reset(); AnswerNotifier.shared.setShowing(nil)
            RuntimeKeeper.shared.release("ask")
            // The run goes on without this screen: the notification at its end still matters only
            // once the app itself is left (then scenePhase starts the stream, from the orb page).
            return
        }
        guard let last = path.last, last.isOrbPage, let w = pendingWait else { return }
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
        WKInterfaceDevice.current().play(.start)         // felt: the microphone opens
        listener.start { outcome in
            guard mine == turn else { return }
            switch outcome {
            case .speech(let wav): transcribeAndSend(wav, turn: mine, back: back)
            case .nothingHeard: phase = back; note = "I didn't hear anything"; RuntimeKeeper.shared.release("ask")
            case .failed(let why): phase = back; error = why; RuntimeKeeper.shared.release("ask")
            }
        }
    }

    /// Sends a recorded question: the gateway transcribes it, then it is asked. When the upload or
    /// the transcription fails, the recording is kept (Retry, Discard); `retrying`: `wav` is the
    /// kept recording, sent again by Retry (sent, it is deleted; failed again, it stays).
    private func transcribeAndSend(_ wav: Data, turn mine: Int, back: Phase, retrying: Bool = false) {
        phase = .thinking; transcribing = true; prompt = ""
        if !retrying { WKInterfaceDevice.current().play(.stop) }   // heard: the microphone is closed, sending
        Task {
            do {
                #if DEBUG
                if FailSendHook.on { try await Task.sleep(for: .milliseconds(1800)); throw URLError(.notConnectedToInternet) }   // long enough for a test to see it sending
                #endif
                let text = try await model.client.transcribe(wav: wav, sessionId: automationFeed == nil ? model.askSessionId : voiceSession,
                                                             model: VoicePrefs.transcription)
                guard mine == turn else { return }
                transcribing = false
                if retrying { KeptQuestion.discard(); kept = nil }
                if text.isEmpty { phase = back; note = "I didn't catch that"; RuntimeKeeper.shared.release("ask"); return }
                send(text)
            } catch {
                guard mine == turn else { return }
                transcribing = false; phase = back
                kept = retrying ? KeptQuestion.url : KeptQuestion.keep(wav)
                // Kept: the line under the orb says it, with Retry and Discard.
                self.error = kept == nil ? "I couldn't hear that." : nil
                note = nil
                RuntimeKeeper.shared.release("ask")
            }
        }
    }

    /// Retry: the kept recording goes again through the same path as when it was recorded.
    private func retryKept() {
        guard let url = KeptQuestion.url, let wav = try? Data(contentsOf: url) else {
            KeptQuestion.discard(); kept = nil; error = "The recording is gone."
            return
        }
        RuntimeKeeper.shared.hold("ask")
        speaker.stop()
        turn += 1
        error = nil; note = nil; pendingWait = nil
        transcribeAndSend(wav, turn: turn, back: answer.isEmpty ? .idle : .answer, retrying: true)
    }

    /// Discard: the kept recording is deleted; the orb is at rest.
    private func discardKept() {
        KeptQuestion.discard(); kept = nil
        error = nil; note = nil
    }

    private func send(_ text: String) {
        RuntimeKeeper.shared.hold("ask")
        turn += 1
        let mine = turn
        prompt = text; answer = ""; error = nil; note = nil; runId = nil; answerEntity = nil; pendingWait = nil
        phase = .thinking; transcribing = false
        activity.reset()
        Task {
            do {
                if let a = automationFeed {
                    // About the automation: a conversation of its own, its first turn started.
                    guard let d = try await a.discuss(model, text) else {
                        if mine == turn { fail("It hasn't run yet: nothing to talk about.") }
                        return
                    }
                    guard mine == turn else { try? await model.client.cancel(runId: d.runId); return }
                    adopt(d.sessionId)
                    runId = d.runId
                    activity.start(runId: d.runId, client: model.client)
                    try await follow(d.runId, turn: mine)
                    return
                }
                switch model.responder {
                case .assistant:
                    // The tools this conversation allows, read fresh; without them no question goes
                    // out (the workflow's own defaults would ignore what was turned off).
                    await model.ensureTools(maxAge: 600)
                    guard let plan = model.toolPlan else {
                        if mine == turn { fail("Couldn't read your tools. Try again.") }
                        return
                    }
                    // The conversation's workflow (the Assistant's also makes images and voice).
                    let workflow = try await model.runWorkflow()
                    guard mine == turn else { return }
                    // The conversation's newest image: what "edit it", "make it simpler" start from.
                    let source = exchanges.reversed().lazy.flatMap(\.media).first { $0.kind == .image }
                    let id = try await model.client.startRun(prompt: text, sessionId: model.askSessionId, toolPolicy: plan.policy,
                                                                  tools: plan.offered, workflow: workflow, primaryImage: source)
                    guard mine == turn else {
                        // Cancelled (or left) while the run was starting: stop it on the gateway too.
                        try? await model.client.cancel(runId: id); return
                    }
                    runId = id
                    activity.start(runId: id, client: model.client)
                    if scenePhase == .background, !model.client.isMock {   // sent, then the wrist went down
                        AnswerNotifier.shared.watch(runId: id, title: model.responder.title, prompt: text)
                    }
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

    /// The run ended: its steps close and are kept for its answer card.
    private func keepWork(_ id: String, success: Bool) {
        guard activity.runId == id else { return }
        activity.stopLoop()
        let client = model.client
        Task { if let work = await activity.finish(success: success, client: client) { model.keep(work, for: id) } }
    }

    /// A turn that ends without an answer: one short line in the status, the last answer kept.
    private func fail(_ message: String) {
        // Following gave up (or the run ended without an answer): its steps are not read any more.
        if activity.isFollowing { activity.reset() }
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
                // The Assistant's workflow starts the agent two runs down: walk to the run that waits.
                var wait = run.personWait
                var next = run.waitingOnChild
                var depth = 0
                while wait == nil, let child = next, depth < 4 {
                    guard let r = try? await model.client.run(id: child) else { break }
                    wait = r.personWait; next = r.waitingOnChild; depth += 1
                }
                if let w = wait, !model.decidedWaits.contains(w.id) {
                    // The watch approves for you what the run's owner (its conversation, or its
                    // automation) runs unasked or what you allowed it with Approve all.
                    if await model.approveIfAllowed(w, byDefaults: true) {
                        // allowed: the run goes on
                    } else {
                        // A person decides now; the screen is on. Waiting on them must not keep the app
                        // awake, nor the radio (the background refresh posts a wait left undecided).
                        pendingWait = w
                        RuntimeKeeper.shared.release("ask")
                        AnswerNotifier.shared.unwatch(runId: id)
                        open(w)
                        return
                    }
                }
            }
            if run.isTerminal {
                AnswerNotifier.shared.unwatch(runId: id)       // seen here: nothing to post
                keepWork(id, success: run.status == "completed")
                let media = MediaItem.of(output: run.output, runId: id)
                if let out = run.outputText, !out.isEmpty { show(out, media: media) }
                else if !media.isEmpty { show("", media: media) }
                else {
                    fail(run.status == "cancelled" ? "Stopped" : automationFeed != nil ? "The run failed." : "That didn't work. Try again.")
                    return
                }
                if scenePhase == .background {   // wrist down, app still in front: the orb speaks it
                    await AnswerNotifier.shared.deliver(key: id, title: speakerTitle, ref: AnswerRef(runId: id, prompt: prompt), answer: answer)
                }
                return
            }
            try await Task.sleep(for: interval)
        }
    }

    private func resumeFollowing(_ id: String) {
        RuntimeKeeper.shared.hold("ask")
        let mine = turn                                   // callers check their turn is still this one
        phase = .thinking
        if activity.runId != id { activity.start(runId: id, client: model.client) }
        Task {
            do { try await follow(id, turn: mine) }
            catch {
                guard mine == turn else { return }
                fail(Self.human(error))
            }
        }
    }

    /// The answer arrives: shown below the orb, spoken by it (then its recordings play).
    private func show(_ text: String, media: [MediaItem] = []) {
        answer = text; phase = .answer
        // A followed turn already listed (a resumed conversation) gets its answer; else it is new.
        var e = Exchange(id: runId ?? UUID().uuidString, prompt: prompt, answer: text,
                         scope: answerEntity.map { SpeechScope.entity($0) } ?? runId.map { SpeechScope.run($0) }, media: media)
        // An automation's run keeps its trigger's time (read, or when it was seen starting here).
        if automationFeed != nil { e.when = liveWhen }
        if let i = exchanges.firstIndex(where: { $0.id == e.id }) { e.when = exchanges[i].when ?? e.when; exchanges[i] = e } else { exchanges.append(e) }
        if let a = automationFeed { Task { await a.markSeen(model) } }
        else if answerEntity == nil, let id = runId { model.markSeen(session: model.askSessionId, run: id) }
        WKInterfaceDevice.current().play(.notification)
        speak()                                     // the speaker holds the app awake while it reads
        RuntimeKeeper.shared.release("ask")
        // Asked once, after the first answer (never over the orb while it listens): answers that
        // arrive while the app is not on screen come back as notifications.
        AnswerNotifier.shared.requestPermission()
    }

    private func speak() {
        guard speakAnswers, let e = exchanges.last else { return }
        if !e.answer.isEmpty { read(e) }
        else if let clip = e.media.first(where: { $0.kind == .audio }) { playClip(clip) }
    }

    private func cancel() {
        if phase == .listening {
            listener.cancel(); turn += 1; phase = answer.isEmpty ? .idle : .answer
            RuntimeKeeper.shared.release("ask"); return
        }
        if phase == .thinking {
            turn += 1
            activity.reset()
            if let id = runId, !transcribing {
                AnswerNotifier.shared.unwatch(runId: id)
                if let a = automationFeed {
                    // The automation goes on with its schedule; this run is not followed again.
                    stoppedRun = id
                    Task { do { try await a.stop(model) } catch { self.error = "Couldn't stop it" } }
                }
                else { Task { try? await model.client.cancel(runId: id) } }
            }
            transcribing = false; pendingWait = nil
            phase = .idle; note = "Cancelled"; prompt = ""
            RuntimeKeeper.shared.release("ask")
            WKInterfaceDevice.current().play(.click)
            return
        }
        speaker.stop()
    }

    private func clearConversation() {
        speaker.stop(); listener.cancel(); activity.reset(); turn += 1
        RuntimeKeeper.shared.release("ask")                      // a turn dropped here must not keep the watch awake
        if let id = runId { AnswerNotifier.shared.unwatch(runId: id) }
        prompt = ""; answer = ""; runId = nil; answerEntity = nil; note = nil; error = nil; pendingWait = nil
        exchanges = []; readingId = nil; shownCount = 5; historyFailed = nil; mediaFailed = nil
        phase = .idle
    }

    /// Opened from a notification (an answer to show and speak), from "Continue" on a session,
    /// or by a device test hook.
    private func onOpen() async {
        guard !opened else { return }                       // back from a page above: as it was left
        defer { opened = true }
        if let a = automationFeed {
            await openAutomation(a)
            #if DEBUG
            if let t = model.testAsk { model.testAsk = nil; send(t) }   // talking about it (tests)
            #endif
            return
        }
        if let r = model.resuming {
            // Continue a session: open on its last exchange, quiet; the next tap talks in it.
            model.resuming = nil
            prompt = r.prompt; answer = r.answer; runId = r.runId
            if !answer.isEmpty || !prompt.isEmpty { phase = .answer }
            exchanges = [Exchange(id: r.runId, prompt: r.prompt, answer: r.answer, scope: .run(r.runId), media: r.media)]
            model.markSeen(session: r.sessionId, run: r.runId)
            // Its last turn is still working (or waits on an approval): follow it, as when asked here
            // (the status line then says what it does, not the title).
            if r.status == "running" || r.status == "waiting" { note = nil; resumeFollowing(r.runId) }
            await loadHistory(model.askSessionId, latestRun: r.runId)
            return
        }
        if let ref = opening, answer.isEmpty {
            prompt = ref.prompt ?? ""
            answerEntity = ref.entity
            runId = ref.runId
            if let text = ref.text { show(text); return }
            if let id = ref.runId, let run = try? await model.client.run(id: id) {
                // The answer's own conversation: its tools, its next question and its history are
                // that conversation's (never the one that happened to be current).
                // An automation's run: its own page (talking there never writes into its conversation).
                if !run.isConversation, let last = model.path.indices.last,
                   let a = await model.automation(of: run) {
                    model.path[last] = .automation(a); return
                }
                if ref.entity == nil, let session = run.sessionId, run.isConversation, session != model.askSessionId { adopt(session) }
                let media = MediaItem.of(output: run.output, runId: id)
                if let out = run.outputText, !out.isEmpty { show(out, media: media) } else { error = "No answer." }
                if ref.entity == nil, let session = run.sessionId, session == model.askSessionId { await loadHistory(session, latestRun: id) }
            }
            return
        }
        #if DEBUG
        if let t = model.testAsk { model.testAsk = nil; send(t); return }
        if model.testListen { model.testListen = false; startListening() }
        // `--test-fail-send`: a question just recorded (sample audio) whose sending fails.
        if FailSendHook.pending {
            FailSendHook.pending = false
            RuntimeKeeper.shared.hold("ask"); turn += 1
            transcribeAndSend(SyntheticSpeech.wav(seconds: 1.5, seed: 7), turn: turn, back: .idle)
            return
        }
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
        phase = .answer
        exchanges = [Exchange(id: last.runId, prompt: last.prompt, answer: last.answer, scope: .run(last.runId), media: last.media)]
        model.markSeen(session: s.id, run: last.runId)
        if last.status == "running" || last.status == "waiting" { note = nil; resumeFollowing(last.runId) }
        await loadHistory(s.id, latestRun: last.runId)
    }

    /// Moves the page into a conversation (a notification's, an automation's discussion): it is the
    /// current conversation from now on, and what is on screen stays.
    private func adopt(_ session: String) {
        adopted = session
        model.adopt(session, about: automationFeed?.id)
        conversation = .chat
    }

    // MARK: - An automation

    /// An automation's page: its runs as messages (at once from what was read before, then read
    /// again; quiet, on the latest), Seen, and its run in progress followed as a turn is.
    private func openAutomation(_ a: AutomationFeed) async {
        if exchanges.isEmpty, let known = model.results[a.id], !known.isEmpty {
            exchanges = known.reversed().map(AutomationFeed.exchange)
            showLatestQuietly()
        } else if exchanges.isEmpty, let last = a.automation.lastOccurrence, last.runId != nil {
            // Its latest run as the list has it (the start of its answer), while its runs are read.
            exchanges = [AutomationFeed.exchange(last)]
            showLatestQuietly()
        }
        await finishAutomation(a)
    }

    /// The runs read, the latest run's media, Seen: what an opening does once the page has it.
    private func finishAutomation(_ a: AutomationFeed) async {
        await readRuns(a)
        guard !Task.isCancelled, historyFailed == nil else { return }
        // The latest run's images and recordings (an automation's runs may each have a session of their own).
        if let last = exchanges.last, last.media.isEmpty, last.scope != nil, let run = try? await model.client.run(id: last.id) {
            let media = MediaItem.of(output: run.output, runId: last.id)
            if !media.isEmpty, let i = exchanges.firstIndex(where: { $0.id == last.id }) { exchanges[i].media = media }
        }
        guard !Task.isCancelled else { return }
        await a.markSeen(model)
        if !Task.isCancelled { automationRead = true }
    }

    /// Reads the automation's runs again: the runs as read, in their order, then those followed here
    /// and not listed yet. A read cut short (the page covered, left) is no failure: the page reads
    /// them again when it is back.
    private func readRuns(_ a: AutomationFeed) async {
        loadingOlder = true
        defer { loadingOlder = false; runsRead = true }
        do {
            let fresh = try await a.exchanges(model)
            guard !Task.isCancelled, automationFeed === a else { return }
            historyFailed = nil
            let ids = Set(fresh.map(\.id))
            exchanges = fresh + exchanges.filter { !ids.contains($0.id) && liveRuns.contains($0.id) }
            showLatestQuietly()
        } catch {
            if !Task.isCancelled, !(error is CancellationError), (error as? URLError)?.code != .cancelled { historyFailed = ("", "") }
        }
    }

    /// At rest on the latest run, without reading it aloud (a tap reads it).
    private func showLatestQuietly() {
        guard phase == .idle || (phase == .answer && !speaker.isActive), let last = exchanges.last else { return }
        answer = last.answer; prompt = last.prompt; runId = last.scope == nil ? nil : last.id
        if phase == .idle { phase = .answer }
    }

    /// A run of the automation in progress, not yet followed here: follow it (its message, then
    /// its steps under the orb, then its answer). Nothing happens once the page is left or covered,
    /// once something else is under way, or for the run you stopped.
    private func checkAutomationRun(_ a: AutomationFeed) async {
        guard automationFeed === a, phase != .listening, phase != .thinking else { return }
        let mine = turn
        // Run on its details handed over the run it saw start: followed at once (its message after).
        if let handed = model.startedRuns.removeValue(forKey: a.id), Date().timeIntervalSince(handed.since) < 600 {
            let run = handed.runId
            guard run != stoppedRun, exchanges.first(where: { $0.id == run })?.answer.isEmpty != false else { return }
            followAutomationRun(run, prompt: "", since: handed.since)
            let sent = (try? await model.client.prompt(ofRun: run)) ?? nil
            guard let sent, !sent.isEmpty, runId == run else { return }
            if phase == .thinking { prompt = sent }
            if let i = exchanges.firstIndex(where: { $0.id == run }), exchanges[i].prompt.isEmpty { exchanges[i].prompt = sent }
            return
        }
        let starting = model.automations.first { $0.id == a.id }?.currentOccurrence != nil || a.automation.currentOccurrence != nil
        let found = starting ? await a.liveRun(model) : await a.refresh(model)
        guard !Task.isCancelled, mine == turn else { return }
        // A run that ended while the page was covered or dimmed: the runs again.
        if found == nil, let last = a.automation.lastOccurrence?.runId, !exchanges.contains(where: { $0.id == last }) {
            await readRuns(a)
            return
        }
        guard let run = found, run != stoppedRun, automationFeed === a,
              phase != .listening, phase != .thinking,
              exchanges.first(where: { $0.id == run })?.answer.isEmpty != false else { return }
        let sent = (try? await model.client.prompt(ofRun: run)) ?? nil
        guard !Task.isCancelled, mine == turn, phase != .listening, phase != .thinking else { return }
        followAutomationRun(run, prompt: sent ?? "")          // never another run's message
    }

    /// Follows a run of the automation on this page: its message, its steps under the orb (timed
    /// from `since`), then its answer.
    private func followAutomationRun(_ run: String, prompt sent: String, since: Date = Date()) {
        speaker.stop()
        liveRuns.insert(run)
        liveWhen = AutomationInfoView.short(ISO8601DateFormatter().string(from: since))
        runId = run
        prompt = sent
        note = nil; error = nil
        if activity.runId != run { activity.start(runId: run, client: model.client, since: since) }
        resumeFollowing(run)
    }

    /// While an automation's page is in front (this task ends when it is covered or left, and
    /// starts again when it is back): once its runs are shown, at once, then every 10 s, a run its
    /// schedule or Run now started, or one that ended meanwhile. One task: one check at a time.
    private func watchAutomation() async {
        guard let a = automationFeed else { return }
        while !opened, !Task.isCancelled { try? await Task.sleep(for: .milliseconds(300)) }
        guard !Task.isCancelled else { return }                                // replaced by the page's next appearance
        // A run handed over by Run on its details is followed first: the page's reading waits for it.
        if model.startedRuns[a.id] != nil, scenePhase == .active { await checkAutomationRun(a) }
        if !automationRead { await finishAutomation(a) }                       // the first opening was cut short
        while !Task.isCancelled {
            if scenePhase == .active { await checkAutomationRun(a) }
            try? await Task.sleep(for: .seconds(10))
        }
    }

    /// The whole conversation below the orb, from the gateway's replay of the session (one
    /// request; "Show older" then pages through it without the network).
    private func loadHistory(_ session: String, latestRun: String) async {
        loadingOlder = true
        historyFailed = nil
        defer { loadingOlder = false }
        // The turns' media come from the session's artifacts (the replay's turns do not list them).
        async let media = loadMedia(session)
        do {
            let turns = try await model.client.sessionHistory(latestRun: latestRun, limit: 1000)
            guard model.askSessionId == session else { return }
            // Before the exchanges on screen (read fresh, or asked meanwhile), which stay as they are.
            let known = Set(exchanges.map(\.id))
            exchanges = turns.filter { !known.contains($0.runId) && ($0.prompt?.isEmpty == false || $0.answer?.isEmpty == false) }
                .map { Exchange(id: $0.runId, prompt: $0.prompt ?? "", answer: $0.answer ?? "", scope: .run($0.runId)) } + exchanges
        } catch {
            guard model.askSessionId == session else { _ = await media; return }
            historyFailed = (session, latestRun)
        }
        if let byRun = await media { attach(byRun) }
    }

    /// The conversation's media, by turn; nil when it could not be read (Retry offers it again).
    @discardableResult private func loadMedia(_ session: String) async -> [String: [MediaItem]]? {
        mediaFailed = nil
        do {
            let byRun = try await model.client.sessionMedia(sessionId: session)
            guard model.askSessionId == session else { return nil }
            attach(byRun)
            return byRun
        } catch {
            if model.askSessionId == session { mediaFailed = session }
            return nil
        }
    }

    /// Each exchange shows what its turn made (a turn's own output, already shown, is kept).
    private func attach(_ byRun: [String: [MediaItem]]) {
        for i in exchanges.indices where exchanges[i].media.isEmpty {
            if let m = byRun[exchanges[i].id], !m.isEmpty { exchanges[i].media = m }
        }
    }
}

/// The ring a hold on the orb closes: a faint track and the arc drawn from the top, clockwise.
struct HoldRing: View {
    let progress: CGFloat
    var body: some View {
        ZStack {
            Circle().stroke(Theme.text.opacity(0.12), lineWidth: 3)
            Circle().trim(from: 0, to: progress)
                .stroke(Theme.text.opacity(0.85), style: StrokeStyle(lineWidth: 3, lineCap: .round))
                .rotationEffect(.degrees(-90))
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

/// Retry and Discard under the orb: the app's filled capsules (`FilledButtonStyle`), at the size
/// of a line, so both fit under the orb without covering it.
private struct KeptButtonStyle: ButtonStyle {
    let fill: Color
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.rounded(.footnote, weight: .semibold)).lineLimit(1).minimumScaleFactor(0.75)
            .foregroundStyle(Theme.text)
            .padding(.horizontal, 8).frame(maxWidth: .infinity, minHeight: 30)
            .background(fill.opacity(configuration.isPressed ? 0.7 : 1), in: Capsule())
    }
}

#if DEBUG
/// `--test-fail-send`: the orb page opens on a question just recorded whose sending fails, and every
/// send fails while the app runs (the kept-recording tests). Debug builds only.
@MainActor private enum FailSendHook {
    static let on = ProcessInfo.processInfo.arguments.contains("--test-fail-send")
    static var pending = on
}
#endif
