import AbstractGatewayClient
import SwiftUI

@main
struct AbstractAssistantWatchApp: App {
    @StateObject private var model: AppModel
    @Environment(\.scenePhase) private var scenePhase
    @AppStorage(OrbDesign.chosenKey) private var orbChosen = false
    private let options: LaunchOptions

    init() {
        let options = LaunchOptions.parse()
        self.options = options
        let model = options.makeModel()
        model.path = options.initialPath(model)
        _model = StateObject(wrappedValue: model)
        // Answers that arrive while the app is not on screen come back as notifications.
        AnswerNotifier.shared.activate()
        // A tapped answer: when the orb is already on screen (it shows and speaks that answer),
        // just come back to it; a second Ask page would show a still orb over the live one.
        AnswerNotifier.shared.open = { [weak model] ref in
            guard let model else { return }
            switch model.path.last { case .ask, .answer: return; default: model.path = [.answer(ref)] }
        }
        AnswerNotifier.shared.openWait = { [weak model] w in model?.path = [w.kind == .askUser ? .askUser(w) : .approval(w)] }
    }

    var body: some Scene {
        WindowGroup {
            Group {
            if model.needsSignIn {
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
            NavigationStack(path: model.stackPath) {
                HomeView()
                    .navigationDestination(for: Route.self) { route in
                        switch route {
                        case .approval(let w): ApprovalView(wait: w)
                        case .askUser(let w): AskUserView(wait: w)
                        case .draft(let w): DraftView(wait: w)
                        case .waits: WaitsView()
                        case .automation(let a): AutomationDetailView(automation: a)
                        case .automationEdit(let a): AutomationEditView(automation: a)
                        case .newAutomation: NewAutomationView()
                        case .message(let title, let e): MessageView(title: title, exchange: e)
                        case .occurrence(let title, let o): OccurrenceView(title: title, occurrence: o)
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
                model.path.append(.link(url)); return .handled
            })
            .environmentObject(model)
            .tint(Theme.indigo)
            .preferredColorScheme(.dark)
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
