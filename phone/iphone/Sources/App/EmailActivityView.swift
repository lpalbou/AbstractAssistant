import SwiftUI
import AssistantKit

enum EmailDirection: String, Identifiable {
    case read, sent
    var id: String { rawValue }
    var title: String { self == .read ? "Read emails" : "Sent emails" }
}

struct EmailDirectionIcon: View {
    let direction: EmailDirection
    var body: some View {
        Image(systemName: "envelope")
            .overlay(alignment: .bottomTrailing) {
                Image(systemName: direction == .read ? "arrow.down.left" : "arrow.up.right")
                    .font(.system(size: 8, weight: .bold)).padding(1.5)
                    .background(PhoneTheme.ground, in: Circle()).offset(x: 4, y: 3)
            }.frame(width: 22, height: 18)
    }
}

struct EmailActivityView: View {
    let runID: String
    let direction: EmailDirection
    @Environment(AssistantStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    @State private var query = ""
    private var summary: AnswerActivity? { store.answerActivities[runID] }
    private var messages: [EmailContent] {
        guard let summary else { return [] }
        return direction == .sent ? summary.activity.sentEmails.map(EmailContent.init) : summary.activity.readEmails.map(EmailContent.init)
    }
    private var filtered: [EmailContent] {
        let needle = query.trimmingCharacters(in: .whitespacesAndNewlines)
        return needle.isEmpty ? messages : messages.filter { ([$0.subject, $0.sender] + $0.to + $0.cc + $0.bcc).joined(separator: " ").localizedCaseInsensitiveContains(needle) }
    }
    private var total: Int { direction == .sent ? summary?.activity.sentEmailCount ?? 0 : summary?.activity.readEmailCount ?? 0 }
    var body: some View {
        NavigationStack {
            List {
                if summary?.issues.isEmpty == false {
                    Text("Some activity could not be loaded. Showing confirmed email actions available so far.")
                        .font(.footnote).foregroundStyle(PhoneTheme.amber).listRowBackground(PhoneTheme.surface)
                }
                Section {
                    ForEach(Array(filtered.enumerated()), id: \.element.id) { index, email in
                        NavigationLink { EmailDetail(email: email, close: { dismiss() }) } label: { EmailSummaryRow(email: email) }
                            .accessibilityIdentifier("email.row.\(index)")
                            .listRowBackground(PhoneTheme.surface)
                    }
                } footer: {
                    if total > messages.count { Text("Showing the latest 100 messages.") }
                }
                if filtered.isEmpty {
                    Text(query.isEmpty ? (direction == .read ? "No emails read for this answer." : "No emails sent for this answer.") : "No matching emails.")
                        .foregroundStyle(PhoneTheme.secondary).listRowBackground(PhoneTheme.surface)
                }
            }
            .listStyle(.insetGrouped).scrollContentBackground(.hidden)
            .background(PhoneTheme.ground).foregroundStyle(PhoneTheme.ink)
            .searchable(text: $query, placement: .navigationBarDrawer(displayMode: .automatic), prompt: "Find an email")
            .navigationTitle(direction.title).navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        }
    }
}

private struct EmailContent: Identifiable {
    var id: String
    var direction: EmailDirection
    var sender: String
    var to: [String]
    var cc: [String]
    var bcc: [String] = []
    var subject: String
    var body: String
    var html: String
    var attachments: [String]
    var messageID: String
    var timestamp: Date?
    var messageDate = ""
    var refused: [String] = []
    var notice: String?
    var status: String
    init(_ mail: SentEmail) {
        id = mail.id; direction = .sent; sender = mail.sender; to = mail.to; cc = mail.cc; bcc = mail.bcc
        subject = mail.subject; body = mail.body; html = mail.html; attachments = mail.attachments
        messageID = mail.messageID; timestamp = mail.sentAt; refused = mail.refused
        if to.isEmpty && cc.isEmpty && bcc.isEmpty { to = mail.accepted }
        status = mail.isReply ? "Reply sent" : "Sent"
    }
    init(_ mail: ReadEmail) {
        id = mail.id; direction = .read; sender = mail.sender; to = mail.to; cc = mail.cc
        subject = mail.subject; body = mail.body; html = mail.html; attachments = mail.attachments
        messageID = mail.messageID; timestamp = mail.readAt; messageDate = mail.messageDate; notice = mail.bodyNotice
        status = mail.bodyNotice == nil ? "Read" : "Headers only"
    }
    var title: String { subject.isEmpty ? "Subject unavailable" : subject }
    var addresses: String { direction == .sent ? "To: " + to.joined(separator: ", ") : "From: " + sender }
    var snippet: String { notice ?? (body.isEmpty ? (html.isEmpty ? "Message body unavailable" : "HTML message") : body.replacingOccurrences(of: "\n", with: " ")) }
}

private struct EmailSummaryRow: View {
    let email: EmailContent
    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack(alignment: .firstTextBaseline, spacing: 12) {
                Text(email.title).font(.subheadline.weight(.semibold)).lineLimit(2)
                Spacer(minLength: 0)
                if let timestamp = email.timestamp {
                    Text(timestamp.formatted(.dateTime.month(.abbreviated).day().hour().minute()))
                        .font(.caption2).foregroundStyle(PhoneTheme.secondary).multilineTextAlignment(.trailing)
                }
            }
            Text(email.addresses).font(.caption).foregroundStyle(PhoneTheme.mint).lineLimit(2)
            Text(email.snippet).font(.caption).foregroundStyle(PhoneTheme.secondary).lineLimit(2)
        }.padding(.vertical, 8)
    }
}

private struct EmailDetail: View {
    let email: EmailContent
    let close: () -> Void
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                VStack(alignment: .leading, spacing: 8) {
                    Label(email.status, systemImage: email.direction == .read ? "envelope.open" : "checkmark.circle.fill")
                        .foregroundStyle(email.notice == nil ? PhoneTheme.mint : PhoneTheme.amber).font(.caption)
                    Text(email.timestamp.map { $0.formatted(date: .abbreviated, time: .shortened) } ?? "Time unavailable")
                        .font(.caption).foregroundStyle(PhoneTheme.secondary)
                }
                Text(email.title).font(.title3.weight(.semibold)).textSelection(.enabled)
                VStack(alignment: .leading, spacing: 10) {
                    if !email.sender.isEmpty { address("From", [email.sender]) }
                    if !email.to.isEmpty { address("To", email.to) }
                    if !email.cc.isEmpty { address("Cc", email.cc) }
                    if !email.bcc.isEmpty { address("Bcc", email.bcc) }
                }
                if !email.refused.isEmpty {
                    Label("Not accepted: " + email.refused.joined(separator: ", "), systemImage: "exclamationmark.triangle")
                        .font(.footnote).foregroundStyle(PhoneTheme.amber).textSelection(.enabled)
                }
                Divider().overlay(PhoneTheme.secondary.opacity(0.15))
                if let notice = email.notice { Text(notice).font(.footnote).foregroundStyle(PhoneTheme.amber).textSelection(.enabled) }
                if !email.body.isEmpty {
                    Text(email.body).font(.body).lineSpacing(5).textSelection(.enabled)
                } else if !email.html.isEmpty {
                    DisclosureGroup("HTML message") {
                        Text(email.html).font(.system(.footnote, design: .monospaced)).textSelection(.enabled).padding(.top, 8)
                    }.font(.subheadline)
                } else if email.notice == nil {
                    Text("The message body is not available in this run’s history.").font(.footnote).foregroundStyle(PhoneTheme.secondary)
                }
                if !email.attachments.isEmpty || !email.messageID.isEmpty || !email.messageDate.isEmpty {
                    DisclosureGroup("Details") {
                        VStack(alignment: .leading, spacing: 12) {
                            if !email.attachments.isEmpty { Label(email.attachments.joined(separator: "\n"), systemImage: "paperclip").textSelection(.enabled) }
                            if !email.messageDate.isEmpty { address("Date", [email.messageDate]) }
                            if !email.messageID.isEmpty {
                                Text("Message ID").foregroundStyle(PhoneTheme.secondary)
                                Text(email.messageID).font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                            }
                        }.font(.footnote).padding(.top, 10)
                    }.font(.footnote).tint(PhoneTheme.secondary)
                }
            }
            .foregroundStyle(PhoneTheme.ink).padding(20).frame(maxWidth: .infinity, alignment: .leading)
            .background(PhoneTheme.surface, in: RoundedRectangle(cornerRadius: 24)).padding(20)
        }
        .background(PhoneTheme.ground).navigationTitle(email.direction == .read ? "Read email" : "Sent email").navigationBarTitleDisplayMode(.inline)
        .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done", action: close) } }
    }
    private func address(_ title: String, _ values: [String]) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Text(title).foregroundStyle(PhoneTheme.secondary).frame(width: 40, alignment: .leading)
            Text(values.joined(separator: ", ")).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
        }.font(.subheadline)
    }
}
