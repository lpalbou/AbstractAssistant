import AbstractGatewayClient
import SwiftUI
import WatchKit

/// One tool approval. What will run is the big text; the tool and its risk are the caption.
/// Allow and Deny stay in the bottom bar, always reachable; Back is "later". "Allow all in this
/// session" (from Ask, never for sends) sits behind the "…" button.
struct ApprovalView: View {
    let wait: Wait
    @EnvironmentObject private var model: AppModel
    @State private var sending = false
    @State private var askAll = false

    private var call: ToolCallDetail? { wait.details?.first }
    private var command: String? { call?.arguments["command"]?.stringValue }
    private var cwd: String? {
        guard let p = call?.arguments["working_directory"]?.stringValue else { return nil }
        return "…/" + p.split(separator: "/").suffix(2).joined(separator: "/")
    }
    private var outreach: Bool { model.isOutreach(wait) }
    private var destructive: Bool { model.isDestructive(wait) }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 5) {
                    Text(wait.toolName).font(.mono(.caption2, weight: .semibold)).foregroundStyle(Theme.text2)
                        .lineLimit(1).truncationMode(.middle)
                    tierPill
                }
                if outreach { outreachCard } else { callCard }
                HStack(spacing: 4) {
                    Text(wait.workflow.map(Self.workflowName) ?? "run")
                    if let askedAt = wait.askedAt { Text("· " + Self.ago(askedAt)) }
                }
                .font(.rounded(.caption2)).foregroundStyle(Theme.muted).lineLimit(1)
            }
        }
        .screen(outreach ? "Send?" : "Allow?")
        .toolbar {
            if model.approvalFromAsk && !outreach {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { askAll = true } label: { BarIcon(symbol: "ellipsis") }
                        .tint(Theme.neutralButton)
                        .accessibilityLabel("More choices")
                }
            }
            ToolbarItemGroup(placement: .bottomBar) {
                Button { decide(.deny) } label: { BarIcon(symbol: "xmark") }
                    .tint(Theme.redButton)
                    .accessibilityLabel("Deny")
                    .disabled(sending)
                allowButton
            }
        }
        .confirmationDialog("Allow every tool in this conversation? Sends still ask.", isPresented: $askAll) {
            Button("Allow all in this session") { decide(.approve, trustSession: true) }
            Button("Cancel", role: .cancel) {}
        }
        #if DEBUG
        .task {
            guard let how = model.testApprove else { return }
            model.testApprove = nil
            try? await Task.sleep(for: .seconds(2))
            print("test-approve \(how) for \(wait.toolName), from Ask: \(model.approvalFromAsk)")
            decide(.approve, trustSession: how == "all")
        }
        #endif
    }

    @ViewBuilder private var callCard: some View {
        VStack(alignment: .leading, spacing: 3) {
            if let command {
                Text(command).font(.mono(.body, weight: .medium)).foregroundStyle(destructive ? Theme.red : Theme.text)
                if let cwd { Text("in \(cwd)").font(.mono(.caption2)).foregroundStyle(Theme.muted).lineLimit(1) }
            } else if let (key, value) = wait.primaryArgument {
                if let url = URL(string: value), url.scheme?.hasPrefix("http") == true {
                    Link(destination: url) {
                        Text(value).font(.mono(.footnote, weight: .medium)).foregroundStyle(Theme.cyan).underline()
                            .lineLimit(4).multilineTextAlignment(.leading)
                    }
                    .buttonStyle(.plain)
                    Text("tap to read the page").font(.rounded(.caption2)).foregroundStyle(Theme.muted)
                } else {
                    Text(key).font(.rounded(.caption2)).foregroundStyle(Theme.muted)
                    Text(value).font(.mono(.body, weight: .medium)).foregroundStyle(Theme.text).lineLimit(5)
                }
            }
            ForEach(wait.secondaryArguments, id: \.0) { key, value in
                Text("\(key) \(value)").font(.mono(.caption2)).foregroundStyle(Theme.muted).lineLimit(2)
            }
        }
    }

    @ViewBuilder private var outreachCard: some View {
        VStack(alignment: .leading, spacing: 3) {
            if let to = wait.recipient {
                Text(to).font(.rounded(.body, weight: .semibold)).foregroundStyle(Theme.text).lineLimit(2)
            }
            if let subject = wait.subject {
                Text(subject).font(.rounded(.footnote)).foregroundStyle(Theme.text2).lineLimit(3)
            }
            NavigationLink(value: Route.draft(wait)) {
                Label("Draft", systemImage: "doc.text").font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.cyan)
            }
            .buttonStyle(.plain)
        }
    }

    @ViewBuilder private var allowButton: some View {
        let button = Button { decide(.approve) } label: {
            BarIcon(symbol: outreach ? "paperplane.fill" : "checkmark")
        }
        .tint(Theme.greenButton)
        .accessibilityLabel(outreach ? "Send" : "Allow once")
        .disabled(sending)
        // Double Tap only when the call is neither destructive nor a send to someone else.
        if destructive || outreach { button } else { button.handGestureShortcut(.primaryAction) }
    }

    @ViewBuilder private var tierPill: some View {
        switch model.tier(of: wait) {
        case "destroy": Pill(text: "can delete", color: Theme.red)
        case "outreach": Pill(text: "sends", color: Theme.amber)
        case "act": Pill(text: "acts", color: Theme.cyan)
        case "observe": Pill(text: "reads", color: Theme.green)
        default: if wait.isOutreach { Pill(text: "sends", color: Theme.amber) }
        }
    }

    private func decide(_ answer: WaitAnswer, trustSession: Bool = false) {
        sending = true
        let fromAsk = model.approvalFromAsk
        Task {
            let ok = await model.answer(wait, with: answer)
            sending = false
            guard ok else { return }
            model.markDecided(wait)
            if trustSession { model.trustSession() }
            if fromAsk || answer != .approve {
                model.path.removeLast()   // back to the orb (or wherever the approval was opened from)
            } else {
                model.path = [.approvalDone(workflow: wait.workflow ?? "run")]
            }
        }
    }

    /// "basic-agent@0.0.5:81795ea9" → "basic agent".
    static func workflowName(_ id: String) -> String {
        let base = id.split(separator: "@").first.map(String.init) ?? id
        return base.replacingOccurrences(of: "-", with: " ").replacingOccurrences(of: "_", with: " ")
    }

    /// "now", "45 s ago", "3 min ago", "2 h ago", "4 d ago".
    static func ago(_ d: Date) -> String {
        let s = max(0, Int(Date().timeIntervalSince(d)))
        return s < 5 ? "now" : s < 60 ? "\(s) s ago" : s < 3600 ? "\(s / 60) min ago" : s < 86_400 ? "\(s / 3600) h ago" : "\(s / 86_400) d ago"
    }
}
