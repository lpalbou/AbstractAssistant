import AbstractGatewayClient
import SwiftUI

@main
struct AbstractAssistantWatchApp: App {
    @StateObject private var model: AppModel
    @Environment(\.scenePhase) private var scenePhase
    private let options: LaunchOptions

    init() {
        let options = LaunchOptions.parse()
        self.options = options
        let model = options.makeModel()
        model.path = options.initialPath(model)
        _model = StateObject(wrappedValue: model)
        // Answers that arrive while the app is not on screen come back as notifications.
        AnswerNotifier.shared.activate()
        AnswerNotifier.shared.open = { [weak model] ref in model?.path = [.answer(ref)] }
        AnswerNotifier.shared.openWaits = { [weak model] in model?.path = [.waits] }
    }

    var body: some Scene {
        WindowGroup {
            Group {
            if model.needsSignIn {
                SignInView()
            } else {
            NavigationStack(path: $model.path) {
                HomeView()
                    .navigationDestination(for: Route.self) { route in
                        switch route {
                        case .approval(let w): ApprovalView(wait: w)
                        case .askUser(let w): AskUserView(wait: w)
                        case .approvalDone(let wf): ApprovalDoneView(workflow: wf)
                        case .draft(let w): DraftView(wait: w)
                        case .waits: WaitsView()
                        case .automation(let a): AutomationDetailView(automation: a)
                        case .ask(let phase): AskView(initialPhase: phase)
                        case .picker: ResponderPickerView()
                        case .sessions: SessionsView()
                        case .session(let s): SessionDetailView(session: s)
                        case .run(let r): RunDetailView(run: r)
                        case .automations: AutomationsView()
                        case .settings: SettingsView()
                        case .pairing: SignInView()
                        case .read(let item): ReadView(item: item)
                        case .link(let url): LinkView(url: url)
                        case .answer(let ref): AskView(initialPhase: .idle, opening: ref)
                        }
                    }
            }
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
            // Poll while the app is on screen, including the dimmed wrist-down state (.inactive):
            // cancelling there killed a first poll that takes 10-15 s over the watch's radio.
            // Background stops it.
            if phase == .background { model.stopPolling(); AnswerNotifier.shared.scheduleRefresh() } else { model.startPolling() }
        }
    }
}
