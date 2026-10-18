import Foundation

/// Export only the conversation the user can see. Runtime records and drafts are not inputs.
public enum ConversationTranscript {
    public static func hasContent(_ messages: [ConversationMessage]) -> Bool {
        messages.contains { $0.role != .notice && (!$0.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !$0.artifacts.isEmpty) }
    }
    public static func text(messages: [ConversationMessage], responder: String) -> String? {
        let turns = messages.compactMap { message -> String? in
            guard message.role != .notice else { return nil }
            let text = message.text.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !text.isEmpty || !message.artifacts.isEmpty else { return nil }
            var parts = ["## " + (message.role == .user ? "You" : responder)]
            if !text.isEmpty { parts.append(text) }
            if !message.artifacts.isEmpty {
                parts.append("Attachments: " + message.artifacts.map(\.filename).joined(separator: ", "))
            }
            return parts.joined(separator: "\n\n")
        }
        guard !turns.isEmpty else { return nil }
        return (["# Conversation", "Text of messages currently loaded in the app. Attachment files are not included."] + turns).joined(separator: "\n\n")
    }
}
