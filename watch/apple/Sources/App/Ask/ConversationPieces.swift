import AbstractGatewayClient
import SwiftUI

enum ConversationCue: String, CaseIterable {
    case question, approval, completion
    var title: String {
        switch self { case .question: "Question"; case .approval: "Approval"; case .completion: "Completion" }
    }
    func enabled(_ channel: String, default fallback: Bool) -> Bool {
        UserDefaults.standard.object(forKey: "conversation.cue.\(rawValue).\(channel)") as? Bool ?? fallback
    }
}

struct ConversationCueSettings: View {
    @State private var expanded = false
    var body: some View {
        VStack(alignment: .leading) {
            Button { expanded.toggle() } label: {
                HStack { Text("Conversation cues"); Spacer(); Image(systemName: expanded ? "chevron.up" : "chevron.down") }
            }.buttonStyle(.tap)
            if expanded { ForEach(ConversationCue.allCases, id: \.self) { ConversationCueSettingsRow(cue: $0) } }
        }.font(.rounded(.footnote)).foregroundStyle(Theme.text)
    }
}

private struct ConversationCueSettingsRow: View {
    let cue: ConversationCue
    @AppStorage private var visual: Bool
    @AppStorage private var audio: Bool
    @AppStorage private var haptic: Bool
    init(cue: ConversationCue) {
        self.cue = cue
        _visual = AppStorage(wrappedValue: true, "conversation.cue.\(cue.rawValue).visual")
        _audio = AppStorage(wrappedValue: false, "conversation.cue.\(cue.rawValue).audio")
        _haptic = AppStorage(wrappedValue: true, "conversation.cue.\(cue.rawValue).haptic")
    }
    var body: some View {
        VStack(alignment: .leading) {
            Text(cue.title).font(.rounded(.footnote, weight: .semibold))
            Toggle("Visual cue", isOn: $visual)
            Toggle("Spoken cue", isOn: $audio)
            Toggle("Haptic cue", isOn: $haptic)
        }.font(.rounded(.caption)).tint(Theme.indigoButton).padding(.vertical, 4)
    }
}

/// The server deadline is information, never a local resume timer or approval.
struct ConversationQuestionInfo: View {
    let question: ConversationQuestion
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            if question.importance == "essential" {
                Text("Your answer is needed. There is no time limit.")
            } else if let deadline = question.deadlineDate {
                TimelineView(.periodic(from: .now, by: 1)) { context in
                    if deadline > context.date {
                        HStack { Text("Time to reply:"); Text(deadline, style: .timer) }
                    } else { Text("The reply time has ended. Checking with the assistant…") }
                }
                if let fallback = question.fallback { Text("Without a reply: \(fallback)") }
                Text("Silence does not give permission.")
            }
        }.font(.rounded(.footnote)).foregroundStyle(Theme.text2)
        .accessibilityIdentifier("conversation.questionPolicy")
    }
}
