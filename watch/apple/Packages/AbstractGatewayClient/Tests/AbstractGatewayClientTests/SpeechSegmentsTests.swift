import Foundation
import Testing
@testable import AbstractGatewayClient

@Test func speechPiecesFollowTheBlocksFirstAlone() {
    let md = "## Title\nFirst paragraph is here.\n\n- item one\n- item two\n\nA closing paragraph that is long enough to stand on its own."
    let pieces = SpeechText.segments(md, target: 40)
    #expect(pieces.first == "Title.")
    #expect(pieces.count >= 3 && pieces.joined(separator: " ") == SpeechText.plain(md))
}
