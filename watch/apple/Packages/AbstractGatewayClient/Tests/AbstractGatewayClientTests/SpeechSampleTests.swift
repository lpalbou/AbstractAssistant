import Testing
@testable import AbstractGatewayClient

// Operator 2026-10-29: choosing a voice sometimes played nothing and said nothing. A reading that
// ends without sound is a failure with a reason, never silence.

@Test func aReadingThatPlayedIsNoFailure() {
    #expect(SpeechSample.failure(receivedSeconds: 2.6, clipsPlayed: false, streamError: nil) == nil)
    #expect(SpeechSample.failure(receivedSeconds: 0, clipsPlayed: true, streamError: nil) == nil)
}

@Test func silenceIsAFailureWithAReason() {
    #expect(SpeechSample.failure(receivedSeconds: 0, clipsPlayed: false, streamError: nil) == "The gateway sent no sound for this voice.")
}

@Test func theGatewaysErrorIsKept() {
    #expect(SpeechSample.failure(receivedSeconds: 0, clipsPlayed: false, streamError: "The gateway's voice failed: 502") == "The gateway's voice failed: 502")
    #expect(SpeechSample.failure(receivedSeconds: 1.2, clipsPlayed: false, streamError: "The voice stopped early.") == "The voice stopped early.")
}

@Test func theRowSaysItInOneLine() {
    #expect(SpeechSample.line("The gateway sent no sound for this voice.") == "The sample did not play: The gateway sent no sound for this voice.")
    #expect(SpeechSample.line("  ") == "The sample did not play.")
}

@Test(arguments: [
    "ClonedVoiceNotAppliedError: speaker score 0.872 below threshold 0.950",
    "The gateway's voice failed (502): ClonedVoiceNotAppliedError: speaker score 0.936 below threshold 0.950",
    "The voice stopped early. {\"detail\":\"ClonedVoiceNotAppliedError: verification failed\"}"
])
func cloneVerificationFailureOffersARetryWithoutTechnicalDetails(reason: String) {
    let line = SpeechSample.line(reason)
    #expect(line == "The sample could not match this voice. Tap to try again.")
    #expect(!line.contains("ClonedVoiceNotAppliedError"))
    #expect(!line.contains("0.950"))
}

@Test func unrelatedVoiceErrorsKeepTheirUsefulReason() {
    #expect(SpeechSample.line("The gateway is offline.") == "The sample did not play: The gateway is offline.")
}
