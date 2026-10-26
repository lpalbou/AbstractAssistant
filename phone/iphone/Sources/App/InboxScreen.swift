import SwiftUI
import AssistantKit
import PhoneGatewayClient

struct InboxScreen: View {
    @Environment(AssistantStore.self) private var store
    @State private var selectedWait: Wait?
    @State private var selectedRun: RunSummary?
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    if let error = store.error { ErrorBanner(message: error, dismiss: store.dismissError) }
                    if store.lastRefresh == nil { ProgressView("Checking your gateway…").padding(.vertical, 18) }
                    QuietLabel(text: store.waits.isEmpty ? (store.lastRefresh == nil ? "Needs you" : "Nothing needs you") : "Needs you · \(store.waits.count)", color: PhoneTheme.amber)
                    if store.waits.isEmpty && store.lastRefresh != nil {
                        PhoneCard { HStack(spacing: 16) { Image(systemName: "checkmark.seal").font(.title2).foregroundStyle(PhoneTheme.mint); VStack(alignment: .leading, spacing: 6) { Text("You’re all caught up.").font(.headline); Text("Questions and approvals will find a home here.").font(.subheadline).foregroundStyle(PhoneTheme.secondary) } } }
                    }
                    ForEach(store.waits) { wait in
                        Button { selectedWait = wait } label: { PendingWaitCard(wait: wait) }.buttonStyle(.plain)
                    }
                    QuietLabel(text: "Recent activity").padding(.top, 10)
                    ForEach(store.runs.prefix(15)) { run in
                        Button { selectedRun = run } label: {
                            HStack(alignment: .top, spacing: 14) {
                                Image(systemName: run.status == "completed" ? "checkmark.circle" : run.status == "failed" ? "exclamationmark.circle" : "circle.dotted").foregroundStyle(run.status == "failed" ? PhoneTheme.amber : PhoneTheme.mint).padding(.top, 2)
                                VStack(alignment: .leading, spacing: 5) {
                                    Text(run.sessionId.flatMap { store.titles[$0] } ?? run.workflowId ?? "Assistant").font(.subheadline.weight(.medium)).foregroundStyle(PhoneTheme.ink)
                                    Text(run.status.capitalized).font(.caption).foregroundStyle(PhoneTheme.secondary)
                                }
                                Spacer(); Image(systemName: "chevron.right").font(.caption).foregroundStyle(PhoneTheme.secondary)
                            }.padding(.vertical, 12)
                        }.buttonStyle(.plain)
                    }
                }.padding(22)
            }.background(PhoneTheme.ground).navigationTitle("Inbox").navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .principal) { NavigationCaption(title: "Inbox", demo: store.isDemo) } }
                .refreshable { await store.refresh() }
                .sheet(item: $selectedWait) { WaitDetailScreen(wait: $0) }
                .sheet(item: $selectedRun) { RunDetailScreen(initial: $0) }
        }
    }
}

private struct PendingWaitCard: View {
    let wait: Wait
    private var question: Bool { wait.kind == .askUser }
    var body: some View {
        PhoneCard {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Image(systemName: question ? "bubble.left.and.text.bubble.right" : "hand.raised")
                    Text(question ? "A question for you" : "Permission to proceed")
                    Spacer()
                    Image(systemName: "arrow.up.right")
                }.font(.caption.weight(.medium)).foregroundStyle(PhoneTheme.amber)
                Text(wait.prompt ?? wait.toolName.replacingOccurrences(of: "_", with: " ").capitalized).font(.headline).multilineTextAlignment(.leading)
                if let workflow = wait.workflow { Text(workflow).font(.caption).foregroundStyle(PhoneTheme.secondary) }
            }
        }
    }
}

struct WaitDetailScreen: View {
    let wait: Wait
    @Environment(AssistantStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    @State private var response = ""
    private var busy: Bool { store.deciding.contains(wait.id) || store.approvingAll.contains(wait.id) }
    private var pending: Bool { store.waits.contains { $0.id == wait.id } }
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    Image(systemName: wait.kind == .askUser ? "bubble.left.and.text.bubble.right" : "hand.raised").font(.largeTitle).foregroundStyle(PhoneTheme.amber)
                    Text(wait.kind == .askUser ? "A question for you." : "Approve these tools?").font(.system(.title, design: .rounded, weight: .semibold))
                    if let error = store.error { ErrorBanner(message: error, dismiss: store.dismissError) }
                    if !pending { Label("Already handled or no longer waiting.", systemImage: "checkmark.circle").foregroundStyle(PhoneTheme.mint) }
                    if let prompt = wait.prompt { Text(prompt).textSelection(.enabled) }
                    if wait.kind == .toolApproval {
                        Text(store.canApproveAll(wait) ? "Approve allows this request. Approve all also allows enabled tools in this conversation without asking again. You can change this in Tools." : "Approve allows all actions in this request.").font(.subheadline).foregroundStyle(PhoneTheme.secondary)
                        ForEach(Array((wait.details ?? []).enumerated()), id: \.offset) { index, call in
                            PhoneCard {
                                VStack(alignment: .leading, spacing: 14) {
                                    QuietLabel(text: "Action \(index + 1)", color: PhoneTheme.amber)
                                    Text(call.name.replacingOccurrences(of: "_", with: " ").capitalized).font(.headline)
                                    ForEach(argumentKeys(call), id: \.self) { key in
                                        VStack(alignment: .leading, spacing: 6) { Text(argumentLabel(key)).font(.caption).foregroundStyle(PhoneTheme.secondary); Text(call.arguments[key]?.displayText ?? "").font(.system(.footnote, design: .monospaced)).textSelection(.enabled).fixedSize(horizontal: false, vertical: true) }
                                    }
                                }
                            }
                        }
                        if !(wait.details ?? []).isEmpty {
                            Button { decide(.approve) } label: { Label("Approve", systemImage: "checkmark").frame(maxWidth: .infinity).padding(.vertical, 7) }.buttonStyle(.borderedProminent).controlSize(.large).disabled(busy || !pending)
                        } else { Text("This request has no action details. Open your gateway console to inspect it before allowing it.").foregroundStyle(PhoneTheme.amber) }
                        if store.canApproveAll(wait) {
                            Button { Task { if await store.approveAll(wait) { dismiss() } } } label: {
                                Text("Approve all").frame(maxWidth: .infinity, minHeight: 44)
                            }.buttonStyle(.bordered).disabled(busy || !pending).accessibilityIdentifier("approval.all")
                        }
                        Button("Deny", role: .destructive) { decide(.deny) }.frame(maxWidth: .infinity, minHeight: 44).disabled(busy || !pending)
                    } else if wait.kind == .askUser {
                        ForEach(wait.choices ?? [], id: \.self) { choice in Button(choice) { decide(.respond(choice)) }.buttonStyle(.bordered).controlSize(.large).disabled(busy || !pending) }
                        if wait.allowFreeText != false {
                            TextField("Your answer", text: $response, axis: .vertical).lineLimit(3...8).padding(16).background(PhoneTheme.surface, in: RoundedRectangle(cornerRadius: 18))
                            Button("Send answer") { decide(.respond(response.trimmingCharacters(in: .whitespacesAndNewlines))) }.buttonStyle(.borderedProminent).controlSize(.large).disabled(busy || !pending || response.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                        }
                    } else { Text("Open your gateway console to handle this request.").foregroundStyle(PhoneTheme.secondary) }
                    if busy { ProgressView("Sending your decision…") }
                    if let url = store.connection?.gateway.appending(path: "console") { Link("Open gateway console", destination: url).font(.footnote) }
                }.padding(24)
            }.background(PhoneTheme.ground).navigationTitle("Needs you").navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .principal) { NavigationCaption(title: "Needs you", demo: store.isDemo) }
                    ToolbarItem(placement: .cancellationAction) { Button("Done") { dismiss() }.disabled(busy) }
                }
        }.interactiveDismissDisabled(busy)
        .onChange(of: pending) { _, pending in if !pending && !busy { dismiss() } }
    }
    private func decide(_ answer: WaitAnswer) { Task { if await store.answer(wait, answer) { dismiss() } } }
    private func argumentKeys(_ call: ToolCallDetail) -> [String] {
        let order = ["to", "cc", "bcc", "subject", "body_text", "body_html"]
        return call.arguments.keys.sorted { a, b in
            let left = order.firstIndex(of: a) ?? 99, right = order.firstIndex(of: b) ?? 99
            return left == right ? a < b : left < right
        }
    }
    private func argumentLabel(_ key: String) -> String {
        ["to": "To", "cc": "Cc", "bcc": "Bcc", "subject": "Subject", "body_text": "Message", "body_html": "Message (HTML)"][key] ?? key.replacingOccurrences(of: "_", with: " ").capitalized
    }
}

struct RunDetailScreen: View {
    let initial: RunSummary
    @Environment(AssistantStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    @State private var run: RunSummary?
    @State private var prompt: String?
    @State private var error: String?
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    QuietLabel(text: (run ?? initial).status, color: PhoneTheme.mint)
                    if let error { ErrorBanner(message: error) }
                    if let prompt { Text(prompt).font(.system(.title2, design: .rounded, weight: .medium)).textSelection(.enabled) }
                    if let answer = (run ?? initial).outputText { PhoneMarkdown(text: answer); ShareLink(item: answer) { Label("Share answer", systemImage: "square.and.arrow.up") } }
                    else { ContentUnavailableView("No answer yet", systemImage: "ellipsis.bubble", description: Text("Pull down to check for an update.")) }
                    if let failure = (run ?? initial).error { ErrorBanner(message: failure) }
                }.padding(24)
            }.background(PhoneTheme.ground).navigationTitle("Activity").navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Done") { dismiss() } } }
                .task { await load() }.refreshable { await load() }
        }
    }
    private func load() async {
        guard let client = store.client else { return }
        do { run = try await client.run(id: initial.runId); prompt = try await client.prompt(ofRun: initial.runId); error = nil }
        catch { self.error = error.localizedDescription }
    }
}
