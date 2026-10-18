import AbstractGatewayClient
import SwiftUI
import WatchKit

/// One tool approval: what the assistant wants to do, in plain words, then what exactly (the
/// command, the page, the recipient). Deny and Allow stay in the bottom bar; Back is "later".
/// From a conversation a third icon allows all tools for the rest of it (never for sends).
struct ApprovalView: View {
    let wait: Wait
    @EnvironmentObject private var model: AppModel
    @State private var sending = false

    private var call: ToolCallDetail? { wait.details?.first }
    private var command: String? { call?.arguments["command"]?.stringValue }
    private var folder: String? {
        let a = call?.arguments
        return (a?["working_directory"] ?? a?["cwd"])?.stringValue.flatMap { $0.split(separator: "/").last.map(String.init) }
    }
    private var outreach: Bool { model.isOutreach(wait) }
    private var destructive: Bool { model.isDestructive(wait) }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 6) {
                Text(wait.headline).font(.rounded(.headline)).foregroundStyle(destructive ? Theme.red : Theme.text).lineLimit(2)
                if outreach { outreachCard } else { callCard }
            }
            .padding(.horizontal, 4)
        }
        .screen("")
        .toolbar {
            ToolbarItemGroup(placement: .bottomBar) {
                Button { decide(.deny) } label: { BarIcon(symbol: "xmark") }
                    .tint(Theme.redButton)
                    .accessibilityLabel("Deny")
                    .disabled(sending)
                allowButton
                // From a conversation: allow every tool for the rest of it (sends still ask).
                if model.approvalFromAsk && !outreach {
                    Button { decide(.approve, trustSession: true) } label: { BarIcon(symbol: "checkmark.seal.fill") }
                        .tint(Theme.indigoButton)
                        .accessibilityLabel("Allow these tools in this conversation")
                        .disabled(sending)
                }
            }
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
                Text(command).font(.mono(.footnote, weight: .medium)).foregroundStyle(destructive ? Theme.red : Theme.text2).lineLimit(6)
                if let folder { Text("in \(folder)").font(.rounded(.caption2)).foregroundStyle(Theme.muted).lineLimit(1) }
            } else if let (_, value) = wait.primaryArgument {
                if let url = URL(string: value), url.scheme?.hasPrefix("http") == true {
                    Link(destination: url) {
                        Text(value).font(.mono(.footnote, weight: .medium)).foregroundStyle(Theme.cyan).underline()
                            .lineLimit(4).multilineTextAlignment(.leading)
                    }
                    .buttonStyle(.plain)
                } else {
                    Text(value).font(.rounded(.footnote)).foregroundStyle(Theme.text2).lineLimit(5)
                }
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
                Label("Read the email", systemImage: "envelope.open").font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.cyan)
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

    private func decide(_ answer: WaitAnswer, trustSession: Bool = false) {
        sending = true
        Task {
            let ok = await model.answer(wait, with: answer)
            sending = false
            guard ok else {
                if !model.waits.contains(where: { $0.id == wait.id }) { model.path.removeLast() }   // answered elsewhere
                return
            }
            model.markDecided(wait)
            if trustSession { model.trustSession(approving: wait) }
            model.path.removeLast()   // back where it was opened: the orb, Home or the list
        }
    }
}

extension Wait {
    /// What the assistant wants to do, in plain words.
    var headline: String {
        if kind == .askUser { return prompt ?? "A question for you" }
        switch toolName {
        case "execute_command", "shell_exec": return "Run a command"
        case "send_email", "reply_email": return "Send an email"
        case "send_telegram_message", "send_telegram_artifact": return "Send a Telegram message"
        case "send_whatsapp_message": return "Send a WhatsApp message"
        case "write_file": return "Write a file"
        case "edit_file": return "Edit a file"
        case "read_file", "skim_files": return "Read a file"
        case "list_files", "search_files", "skim_folders": return "Look through your files"
        case "fetch_url", "skim_url", "render_url_html": return "Open a web page"
        case "web_search", "skim_websearch": return "Search the web"
        case "read_email", "list_emails", "search_emails": return "Read your email"
        default:
            let w = toolName.replacingOccurrences(of: "_", with: " ")
            return w.prefix(1).uppercased() + w.dropFirst()
        }
    }
}
