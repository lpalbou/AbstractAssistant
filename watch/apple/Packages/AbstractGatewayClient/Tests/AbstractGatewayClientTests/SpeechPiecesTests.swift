import Foundation
import Testing
@testable import AbstractGatewayClient

/// `SpeechText.pieces`: the plain text of a reading in sentence-bounded pieces, one speech
/// request each, so a piece lost over the watch's link is requested again, not the whole reading.
@Suite struct SpeechPiecesTests {
    private func words(_ s: String) -> [String] { s.split(whereSeparator: \.isWhitespace).map(String.init) }

    @Test func piecesEndAtSentenceBoundariesAndGatherUpToTheTarget() {
        let text = "One is short. Two is a little longer than one! Three asks a question? Four ends it."
        let pieces = SpeechText.pieces(text, target: 40, cap: 80)
        #expect(pieces == ["One is short.", "Two is a little longer than one!", "Three asks a question? Four ends it."])
        // A larger target gathers whole sentences, never cutting inside one.
        #expect(SpeechText.pieces(text, target: 60, cap: 80) == ["One is short. Two is a little longer than one!", "Three asks a question? Four ends it."])
    }

    @Test func aPeriodInsideANumberOrWithoutASpaceIsNoBoundary() {
        let text = "The CV was 3.1 % on plate P07.Then it passed. Done."
        #expect(SpeechText.pieces(text, target: 30, cap: 80) == ["The CV was 3.1 % on plate P07.Then it passed.", "Done."])
    }

    @Test func aSentenceLongerThanTheCapIsCutAtASpaceBeforeIt() {
        let long = Array(repeating: "word", count: 50).joined(separator: " ")   // 249 chars, no sentence end
        let pieces = SpeechText.pieces(long, target: 60, cap: 80)
        #expect(pieces.count == 4)
        #expect(pieces.allSatisfy { $0.count <= 80 && !$0.hasPrefix(" ") && !$0.hasSuffix(" ") })
        #expect(words(pieces.joined(separator: " ")) == words(long))
        // A cap smaller than the longest word still ends (the cut lands on the cap itself).
        #expect(SpeechText.pieces("supercalifragilistic", target: 5, cap: 5) == ["super", "calif", "ragil", "istic"])
    }

    /// The Read page's sample answer under `--piece-chars 80` (StalledVoiceUITests): its two
    /// sentences, one piece each, the first longer than the target and still whole.
    @Test func theSampleAnswerSplitsIntoItsTwoSentencesAtEighty() {
        let pieces = SpeechText.pieces(MockGatewayClient.World.watch.cannedAnswer, target: 80, cap: 106)
        #expect(pieces.count == 2)
        #expect(pieces.first?.hasSuffix("287 events.") == true)
        #expect(pieces.last?.hasPrefix("Proportional hazards") == true)
    }

    @Test func noPieceIsEmptyAndTheWordsRoundTrip() {
        let empty = SpeechText.pieces("", target: 600, cap: 800)
        #expect(empty.isEmpty)
        #expect(SpeechText.pieces("   \n  ", target: 600, cap: 800).isEmpty)
        let md = "## Lesson 1: What MS is\n\nMS is an immune-mediated disease.  It damages myelin!\n\n- Relapsing. - Progressive?\n\nA closing line with no end"
        let plain = SpeechText.plain(md)
        for target in [10, 40, 600] {
            let pieces = SpeechText.pieces(plain, target: target, cap: max(target, 20) * 4 / 3)
            #expect(pieces.allSatisfy { !$0.trimmingCharacters(in: .whitespaces).isEmpty })
            #expect(words(pieces.joined(separator: " ")) == words(plain), "target \(target)")
        }
        // The default sizes on a long reading: every piece under the cap, most near the target.
        let reading = Array(repeating: "A sentence of forty characters, almost.", count: 120).joined(separator: " ")
        let pieces = SpeechText.pieces(reading)
        #expect(pieces.allSatisfy { $0.count <= 800 })
        #expect(pieces.dropLast().allSatisfy { $0.count > 500 })
        #expect(words(pieces.joined(separator: " ")) == words(reading))
    }
}
