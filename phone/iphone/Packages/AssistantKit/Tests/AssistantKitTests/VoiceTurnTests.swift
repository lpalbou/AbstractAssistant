import Testing
import AssistantKit

@Test func releaseRequiresThreeLocalSecondsBeforeTranscription() {
    var turn = VoiceTurn()
    #expect({ turn.begin() }()); #expect({ turn.recordingStarted(at: 10) }())
    turn.advance(to: 50) // Pausing while holding never sends.
    #expect(turn.phase == .recording); #expect({ !turn.claimForTranscription() }())
    turn.release(at: 51)
    #expect(turn.secondsRemaining(at: 51) == 3)
    turn.advance(to: 53.999)
    #expect({ !turn.claimForTranscription() }())
    turn.advance(to: 54)
    #expect({ turn.claimForTranscription() }())
    #expect({ !turn.claimForTranscription() }()) // Only one network handoff.
}

@Test func touchingTheOrbDuringGraceCancelsBeforeDeadline() {
    var turn = VoiceTurn()
    #expect({ turn.begin() }()); #expect({ turn.recordingStarted(at: 0) }()); turn.release(at: 1)
    #expect({ !turn.begin() }()) // Touch DOWN cancels; holding that touch cannot restart capture.
    turn.advance(to: 20); turn.release(at: 21)
    #expect(turn.phase == .idle); #expect({ !turn.claimForTranscription() }())
}

@Test func releasedPermissionRequestAndShortTapsCannotCreateVoiceMessages() {
    var turn = VoiceTurn()
    #expect({ turn.begin() }()); turn.release(at: 1)
    #expect({ !turn.recordingStarted(at: 2) }())
    #expect({ turn.begin() }()); #expect({ turn.recordingStarted(at: 3) }()); turn.release(at: 3.1)
    turn.advance(to: 10); #expect({ !turn.claimForTranscription() }())
}

@Test func cancelInvalidatesReadyAndInFlightVoiceTurns() {
    for claim in [false, true] {
        var turn = VoiceTurn()
        #expect({ turn.begin() }()); #expect({ turn.recordingStarted(at: 0) }()); turn.release(at: 1); turn.advance(to: 4)
        if claim { #expect({ turn.claimForTranscription() }()) }
        turn.cancel(); #expect(turn.phase == .idle); #expect({ !turn.claimForTranscription() }())
    }
}

@Test func audioEnvelopeRespondsToRealEnergyAndDecaysWithoutInvalidLevels() {
    var envelope = AudioEnvelope()
    for _ in 0..<10 { envelope.sample(averageDB: -160, peakDB: -160) }
    #expect(envelope.level == 0)
    let quiet = envelope.sample(averageDB: -42, peakDB: -34)
    let loud = envelope.sample(averageDB: -18, peakDB: -10)
    #expect(quiet > 0.1 && loud > quiet * 2)
    for _ in 0..<20 { envelope.sample(averageDB: -160, peakDB: -160) }
    #expect(envelope.level < 0.01)
    for value: Float in [.nan, .infinity, -.infinity, 10, -200] {
        let level = envelope.sample(averageDB: value, peakDB: value)
        #expect(level.isFinite && (0...1).contains(level))
    }
}

@Test func maximumCaptureStillWaitsForActualRelease() {
    var turn = VoiceTurn()
    #expect({ turn.begin() }()); #expect({ turn.recordingStarted(at: 0) }())
    turn.reachedLimit(); turn.advance(to: 100)
    #expect(turn.phase == .atLimit); #expect({ !turn.claimForTranscription() }())
    turn.release(at: 100); turn.advance(to: 102.9)
    #expect({ !turn.claimForTranscription() }())
    turn.advance(to: 103); #expect({ turn.claimForTranscription() }())
}
