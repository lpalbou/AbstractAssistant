import SwiftUI
import AssistantKit
import PhoneGatewayClient
import Observation

struct ConversationShareSnapshot: Identifiable {
    let id = UUID()
    let messages: [ConversationMessage]
    let responder: String
    let client: any GatewayClient
    let activities: [String: AnswerActivity]
    let contextID: UUID
    let sessionID: String
    @MainActor func isCurrent(_ store: AssistantStore) -> Bool { contextID == store.contextID && sessionID == store.sessionID }
}

@MainActor final class PreparedConversationShare {
    let export: ConversationExport
    let rich: RichConversation
    let storage: PhoneTemporaryStorage
    private var closed = false
    init(export: ConversationExport, rich: RichConversation, storage: PhoneTemporaryStorage = .init()) { self.export = export; self.rich = rich; self.storage = storage }
    func close() { guard !closed else { return }; closed = true; try? storage.discard(export.folder) }
    isolated deinit { if !closed { try? storage.discard(export.folder) } }
}

struct ConversationSharePreparation: View {
    let snapshot: ConversationShareSnapshot
    @Environment(AssistantStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    @State private var preparation = ConversationShareController()
    @State private var attempt = 0
    var body: some View {
        Group {
            if let prepared = preparation.prepared { ConversationShareSheet(prepared: prepared, finished: { dismiss() }) }
            else {
                NavigationStack {
                    VStack(spacing: 18) {
                        if let issue = preparation.issue {
                            Image(systemName: "exclamationmark.circle").font(.title).foregroundStyle(PhoneTheme.amber)
                            Text(issue).font(.subheadline).multilineTextAlignment(.center).textSelection(.enabled)
                            Button("Try again") { attempt += 1 }.buttonStyle(.bordered)
                        } else {
                            ProgressView()
                            Text("Preparing conversation and files…").font(.subheadline)
                        }
                    }.padding(28).frame(maxWidth: .infinity, maxHeight: .infinity).background(PhoneTheme.ground)
                        .navigationTitle("Share conversation").navigationBarTitleDisplayMode(.inline)
                        .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } } }
                }
            }
        }.task(id: attempt) { await preparation.prepare(snapshot: snapshot, store: store) }
    }
}

@MainActor @Observable final class ConversationShareController {
    private(set) var prepared: PreparedConversationShare?
    private(set) var issue: String?
    let storage: PhoneTemporaryStorage
    init(storage: PhoneTemporaryStorage = .init()) { self.storage = storage }
    func prepare(snapshot: ConversationShareSnapshot, store: AssistantStore) async {
        issue = nil
        guard snapshot.isCurrent(store) else { return }
        do {
            let export = try await ConversationExportBuilder(storage: storage).prepare(messages: snapshot.messages, responder: snapshot.responder, client: snapshot.client, activities: snapshot.activities)
            do {
                try Task.checkCancellation()
                guard snapshot.isCurrent(store) else { throw CancellationError() }
                prepared = PreparedConversationShare(export: export, rich: try RichConversation(export: export), storage: storage)
            } catch { try? storage.discard(export.folder); throw error }
        } catch {
            guard !Task.isCancelled, !(error is CancellationError), snapshot.isCurrent(store) else { return }
            if error as? GatewayError == .unauthorized { store.authenticationExpired(); return }
            issue = error.localizedDescription
        }
    }
}

/// The controller retains its export lease until the receiving activity finishes or cancels.
struct ConversationShareSheet: UIViewControllerRepresentable {
    let prepared: PreparedConversationShare
    var finished: () -> Void
    func makeUIViewController(context: Context) -> UIActivityViewController {
        let controller = UIActivityViewController(activityItemsConfiguration: prepared.rich.configuration(export: prepared.export))
        controller.completionWithItemsHandler = { [prepared] _, _, _, _ in
            prepared.close(); finished()
        }
        return controller
    }
    func updateUIViewController(_ controller: UIActivityViewController, context: Context) {}
}
