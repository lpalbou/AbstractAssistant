import Testing
import AbstractGatewayClient
@testable import AssistantKit

struct ConversationTranscriptTests {
    @Test func exportsVisibleRolesInOrderWithoutDiagnosticsOrArtifactCredentials() throws {
        let file = PhoneArtifact(artifactId: "private-artifact", runId: "private-run", filename: "summary.md", contentType: "text/markdown")
        let messages: [ConversationMessage] = [
            .init(role: .user, text: "First question"),
            .init(role: .assistant, text: "First answer", runID: "private-run"),
            .init(role: .notice, text: "Internal notice"),
            .init(role: .user, text: "Second question"),
            .init(role: .assistant, text: "", artifacts: [file])
        ]
        let text = try #require(ConversationTranscript.text(messages: messages, responder: "Castor"))
        #expect(ConversationTranscript.hasContent(messages))
        #expect(text.contains("## You\n\nFirst question\n\n## Castor\n\nFirst answer"))
        #expect(text.contains("Second question\n\n## Castor\n\nAttachments: summary.md"))
        #expect(text.contains("Attachment files are not included"))
        #expect(!text.contains("private-") && !text.contains("Internal notice"))
    }
    @Test func emptyOrNoticeOnlyCannotShareAndExistingSnapshotDoesNotChange() throws {
        #expect(!ConversationTranscript.hasContent([]))
        #expect(ConversationTranscript.text(messages: [.init(role: .notice, text: "Diagnostic"), .init(role: .assistant, text: " \n")], responder: "Assistant") == nil)
        var messages: [ConversationMessage] = [.init(role: .user, text: "Original")]
        let snapshot = try #require(ConversationTranscript.text(messages: messages, responder: "Assistant"))
        messages[0].text = "Different account conversation"
        #expect(snapshot.contains("Original") && !snapshot.contains("Different account"))
    }
}
