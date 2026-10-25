import AbstractGatewayClient
import SwiftUI
import WatchKit

@main
struct AbstractAssistantWatchApp: App {
    @StateObject private var model: AppModel
    @Environment(\.scenePhase) private var scenePhase
    @AppStorage(OrbDesign.chosenKey) private var orbChosen = false
    @AppStorage(OrbDesign.storageKey) private var orbDesign = OrbDesign.a.rawValue
    private let options: LaunchOptions
    /// The APNs token arrives here (WatchPush registers it with the gateway).
    @WKApplicationDelegateAdaptor(WatchAppDelegate.self) private var appDelegate

    init() {
        let options = LaunchOptions.parse()
        self.options = options
        let model = options.makeModel()
        model.show(options.initialPath(model))
        _model = StateObject(wrappedValue: model)
        // Answers that arrive while the app is not on screen come back as notifications.
        AnswerNotifier.shared.activate()
        // A tapped answer: when the orb is already on screen (it shows and speaks that answer),
        // just come back to it; a second Ask page would show a still orb over the live one.
        AnswerNotifier.shared.open = { [weak model] ref in
            guard let model else { return }
            switch model.path.last { case .ask, .answer: return; default: model.show([.answer(ref)]) }
        }
        AnswerNotifier.shared.openAutomation = { [weak model] id in model?.openAutomation(id: id) }
        AnswerNotifier.shared.openWait = { [weak model] w in model?.show([w.kind == .askUser ? .askUser(w) : .approval(w)]) }
        AnswerNotifier.shared.openWaits = { [weak model] in model?.show([.waits]) }
        // One sign-in for the product: the iPhone's, handed over WatchConnectivity, signs the watch in.
        WatchLink.shared.adopt = { [weak model] signIn in model?.connect(signIn) }
        // What happened while the app was closed (one read of the event stream; a launch in the
        // background is the refresh's, which reads it itself).
        Task { await AnswerNotifier.shared.catchUpAtLaunch() }
        #if DEBUG
        // `--dump-notify`: the notifier's readout on the console (xcrun devicectl … launch --console).
        if CommandLine.arguments.contains("--dump-notify") {
            Task { for line in await AnswerNotifier.shared.readout() { print("notify-readout \(line)") } }
        }
        #endif
    }

    /// `--screen face` (debug builds): the watch face's Assistant complication on each slot, to look at.
    private var showsFace: Bool {
        #if DEBUG
        options.screen == "face"
        #else
        false
        #endif
    }

    var body: some Scene {
        WindowGroup {
            Group {
            if showsFace {
                FacePreview()
            } else if model.needsSignIn {
                SignInView()
            } else if !orbChosen {
                // First launch, after sign-in: the orb is the assistant, so its look is the first choice.
                NavigationStack {
                    OrbStylePicker(onboarding: true)
                        .navigationDestination(for: Route.self) { route in
                            if case .orbStylePreview(let raw) = route, let d = OrbDesign(rawValue: raw) { OrbStylePreview(design: d, onboarding: true) }
                        }
                }
            } else {
            ZStack(alignment: .topLeading) {
                NavigationStack(path: model.stackPath) {
                    HomeView()
                        .navigationDestination(for: Route.self) { RoutePage(route: $0) }
                }
                // Settings slides in from the left, where its gear is, and its pages after it: a
                // stack of the app's own (a navigation stack would push from the right).
                if let pages = model.settingsPath {
                    ZStack {
                        SettingsView().zIndex(0)
                        // A page's identity is its place and its route: a page replacing another at the
                        // same depth starts fresh.
                        ForEach(Array(pages.enumerated()), id: \.element.hashValue) { i, route in
                            RoutePage(route: route).transition(.move(edge: .leading)).zIndex(Double(i + 1))
                        }
                    }
                    .animation(.easeInOut(duration: AppModel.settingsSlide), value: pages)
                    .background(Theme.ground.ignoresSafeArea())
                    .offset(x: model.settingsIn ? 0 : -WKInterfaceDevice.current().screenBounds.width)
                    .zIndex(1)
                }
                // The one corner button, over every page: the gear on Home, Back elsewhere.
                CornerButton().zIndex(2)
            }
            // Swipes as in a browser: to the right goes back (as the system's own Back), to the left
            // goes forward (to a page went back from, or from the orb page to its conversation). A
            // swipe right from the very left edge is the system's Back already: it is left to it.
            .simultaneousGesture(DragGesture(minimumDistance: 30)
                .onChanged { v in
                    if !model.swipesPaused, abs(v.translation.width) > 2.2 * abs(v.translation.height) { model.swiped() }
                }
                .onEnded { v in
                    let dx = v.translation.width, dy = v.translation.height
                    guard !model.swipesPaused, abs(dx) > 60, abs(dx) > 2.2 * abs(dy) else { return }
                    model.swiped()
                    if dx < 0 { model.goForward() } else if v.startLocation.x > 16 { model.goBack() }
                })
            }
            }
            // Every tapped web link opens the Link screen (the page's text, Read aloud, Handoff to
            // the iPhone); other schemes go to the system.
            .environment(\.openURL, OpenURLAction { url in
                guard url.scheme == "http" || url.scheme == "https" else { return .systemAction(url) }
                model.push(.link(url)); return .handled
            })
            .environmentObject(model)
            .tint(Theme.indigo)
            .preferredColorScheme(.dark)
            // The watch face's avatar follows the orb style chosen.
            .onChange(of: orbDesign, initial: true) { _, d in FaceSnapshot.drawAvatar(OrbDesign(rawValue: d) ?? .a) }
        }
        // The background session that follows an Ask's run wakes the app here when the run ends.
        .backgroundTask(.urlSession(AnswerNotifier.sessionIdentifier)) {
            await AnswerNotifier.shared.handleBackgroundEvents()
        }
        // About every 15 minutes while closed: new approvals and questions become notifications.
        .backgroundTask(.appRefresh(AnswerNotifier.refreshIdentifier)) { _ in
            await AnswerNotifier.shared.checkWaits()
        }
        .onChange(of: scenePhase, initial: true) { _, phase in
            #if DEBUG
            print("scene \(Date().formatted(date: .omitted, time: .standard)) \(phase)")
            #endif
            // Polls while someone looks (active); the dimmed wrist-down state (.inactive) lets the
            // poll in flight finish (a first one takes 10-15 s over the watch's radio) and stops
            // there; background stops at once and asks for a refresh later.
            model.scene(phase)
            if phase == .background { AnswerNotifier.shared.scheduleRefresh() }
        }
    }
}

/// The page a route opens (the same on both stacks).
struct RoutePage: View {
    let route: Route
    var body: some View {
        switch route {
        case .approval(let w): ApprovalView(wait: w)
        case .askUser(let w): AskUserView(wait: w)
        case .draft(let w): DraftView(wait: w)
        case .waits: WaitsView()
        case .automation(let a): AskView(automation: a)
        case .automationInfo(let a): AutomationInfoView(automation: a)
        case .automationSearch(let q): AutomationSearchView(query: q)
        case .automationEdit(let a): AutomationEditView(automation: a)
        case .newAutomation: NewAutomationView()
        case .message(let title, let e): MessageView(title: title, exchange: e)
        case .ask(let phase): AskView(initialPhase: phase)
        case .picker: ResponderPickerView()
        case .sessions: SessionsView()
        case .session(let s): SessionDetailView(session: s)
        case .automations: AutomationsView()
        case .settings: SettingsView()
        case .read(let item): ReadView(item: item)
        case .about: AboutView()
        case .voiceSettings: VoiceSettingsView()
        case .tools(let scope): ToolsView(scope: scope)
        case .connection: ConnectionView()
        case .workflow(let scope): WorkflowPickView(scope: scope)
        case .media(let item): MediaPage(item: item)
        case .activity(let runId): ActivityDetailView(runId: runId)
        case .archivedSessions: ArchivedSessionsView()
        case .sessionSearch(let q): SessionSearchView(query: q)
        case .archivedAutomations: ArchivedAutomationsView()
        case .toolGroup(let scope, let id): ToolGroupView(scope: scope, groupId: id)
        case .link(let url): LinkView(url: url)
        case .answer(let ref): AskView(initialPhase: .idle, opening: ref)
        case .conversation(let id): ConversationInfoView(sessionId: id)
        case .filePreview(let files, let i): FilePreviewView(files: files, index: i)
        case .orbStyle: OrbStylePicker()
        case .orbStylePreview(let raw): OrbStylePreview(design: OrbDesign(rawValue: raw) ?? .a)
        }
    }
}
