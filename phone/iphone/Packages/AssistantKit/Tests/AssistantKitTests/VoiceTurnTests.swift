import Testing
import AssistantKit

private func speakingTurn() -> VoiceTurn {
    var turn = VoiceTurn(); _ = turn.begin(); _ = turn.recordingStarted(at: 0)
    for i in 1...10 { turn.sample(at: Double(i) * 0.03, speech: true) }
    return turn
}
private func quiet(_ turn: inout VoiceTurn, from: Double, to: Double) {
    var time = from + 0.05
    while time < to { turn.sample(at: time, speech: false); time += 0.05 }
    turn.sample(at: to, speech: false)
}
@Test func threeSecondsOfSilenceAreRequiredBeforeTranscription() {
    var turn = speakingTurn()
    quiet(&turn, from: 0.3, to: 0.9)
    #expect(turn.phase == .countdown && turn.secondsRemaining(at: 0.9) == 3)
    quiet(&turn, from: 0.9, to: 3.299); #expect({ !turn.claimForTranscription() }())
    turn.sample(at: 3.3, speech: false); #expect({ turn.claimForTranscription() }())
    #expect({ !turn.claimForTranscription() }())
}
@Test func speechResumingAtTheDeadlineRestartsTheQuietWindow() {
    var turn = speakingTurn()
    quiet(&turn, from: 0.3, to: 3.29); #expect(turn.phase == .countdown)
    turn.sample(at: 3.3, speech: true)
    #expect(turn.phase == .recording && turn.deadline == nil)
    quiet(&turn, from: 3.3, to: 6.299); #expect({ !turn.claimForTranscription() }())
    turn.sample(at: 6.3, speech: false); #expect({ turn.claimForTranscription() }())
}
@Test func cancellingDuringListeningOrCountdownCannotReviveAVoiceTurn() {
    for quiet in [false, true] {
        var turn = speakingTurn()
        if quiet { turn.sample(at: 1, speech: false) }
        #expect({ !turn.begin() }()) // A second tap cancels, rather than replacing the turn.
        turn.sample(at: 20, speech: false)
        #expect(turn.phase == .idle); #expect({ !turn.claimForTranscription() }())
    }
}
@Test func initialSilenceAndBriefImpulsesNeverCreateAMessage() {
    for impulse in [false, true] {
        var turn = VoiceTurn(); _ = turn.begin(); _ = turn.recordingStarted(at: 0)
        if impulse { turn.sample(at: 0.03, speech: true) }
        turn.sample(at: 4, speech: false)
        #expect(!turn.heardSpeech && turn.phase == .recording)
        turn.sample(at: 8, speech: false)
        #expect(turn.phase == .idle); #expect({ !turn.claimForTranscription() }())
    }
}
@Test func permissionGrantAfterCancelCannotStartRecording() {
    var turn = VoiceTurn(); _ = turn.begin(); turn.cancel()
    #expect({ !turn.recordingStarted(at: 1) }())
}
@Test func speechActivityUsesRawPowerWithHysteresisAndRejectsInvalidSamples() {
    var detector = SpeechActivity()
    #expect({ !detector.sample(averageDB: -80) }())
    #expect({ detector.sample(averageDB: -30) }())
    #expect({ detector.sample(averageDB: -54) }()) // Below onset but above the offset threshold.
    #expect({ !detector.sample(averageDB: -80) }())
    #expect({ !detector.sample(averageDB: -.infinity) }())
    #expect({ !detector.sample(averageDB: .nan) }())
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

@Test func missingMicrophoneSamplesCannotBeAssumedSilent() {
    var turn = speakingTurn()
    quiet(&turn, from: 0.3, to: 2.9)
    turn.sample(at: 6, speech: false) // A UI stall could have hidden more speech.
    #expect(turn.phase == .recording); #expect({ !turn.claimForTranscription() }())
    quiet(&turn, from: 6, to: 8.99); #expect({ !turn.claimForTranscription() }())
    turn.sample(at: 9, speech: false); #expect({ turn.claimForTranscription() }())
}

@Test func unknownMeterValuesRestartTheQuietWindow() {
    var turn = speakingTurn()
    quiet(&turn, from: 0.3, to: 2.9)
    turn.sample(at: 3.0, speech: nil)
    quiet(&turn, from: 3.0, to: 5.99); #expect({ !turn.claimForTranscription() }())
    turn.sample(at: 6.0, speech: false); #expect({ turn.claimForTranscription() }())
}
@Test func disconnectedSpeechImpulsesDoNotAccumulateIntoSpeech() {
    var turn = VoiceTurn(); _ = turn.begin(); _ = turn.recordingStarted(at: 0)
    turn.sample(at: 0.1, speech: true); turn.sample(at: 1, speech: true)
    turn.sample(at: 2, speech: false); turn.sample(at: 8, speech: false)
    #expect(!turn.heardSpeech && turn.phase == .idle)
}

@Test func loudSpeechAndPlaybackRetainSyllableDynamicsInsteadOfClipping() {
    func steady(_ db: Float) -> Double {
        var envelope = AudioEnvelope()
        for _ in 0..<12 { envelope.sample(averageDB: db, peakDB: db + 6) }
        return envelope.level
    }
    let quiet = steady(-42), normal = steady(-20), loud = steady(-6)
    #expect(normal > quiet * 2)
    #expect(loud > steady(-12) + 0.04)
    #expect(steady(-2) > loud + 0.02)
    var envelope = AudioEnvelope()
    for _ in 0..<10 { envelope.sample(averageDB: -6, peakDB: 0) }
    for _ in 0..<4 { envelope.sample(averageDB: -45, peakDB: -39) }
    #expect(envelope.level < 0.3) // React within a syllable, rather than hanging near the peak.
}

@Test func quietMicrophoneSpeechUsesItsOwnRangeInsteadOfThePlaybackCurve() {
    for db: Float in [-49, -45, -38] {
        var microphone = MicrophoneEnvelope(), playback = AudioEnvelope()
        for _ in 0..<15 { microphone.sample(averageDB: -70, peakDB: -64, speech: false) }
        let pause = microphone.level
        for _ in 0..<5 {
            microphone.sample(averageDB: db, peakDB: db + 6, speech: true)
            playback.sample(averageDB: db, peakDB: db + 6)
        }
        #expect(microphone.level > 0.65)
        #expect(microphone.level > playback.level + 0.3)
        #expect(pause < 0.01)
    }
}

@Test func microphoneSyllablesMoveAcrossTheRangeAndPausesFallPromptly() {
    var envelope = MicrophoneEnvelope()
    for _ in 0..<8 { envelope.sample(averageDB: -30, peakDB: -24, speech: true) }
    let strong = envelope.level
    for _ in 0..<5 { envelope.sample(averageDB: -47, peakDB: -41, speech: true) }
    let quiet = envelope.level
    #expect(strong - quiet > 0.2 && quiet > 0.25)
    for _ in 0..<8 { envelope.sample(averageDB: -80, peakDB: -74, speech: false) }
    #expect(envelope.level < 0.01)
}

@Test func steadyInactiveRoomNoiseAndHeldPeaksDoNotBecomeFullVoiceMotion() {
    for room: Float in [-75, -62, -55] {
        var envelope = MicrophoneEnvelope()
        for _ in 0..<90 { envelope.sample(averageDB: room, peakDB: room + 6, speech: false) }
        #expect(envelope.level < 0.01)
        // A retained peak must not make an otherwise silent frame look like speech.
        for _ in 0..<20 { envelope.sample(averageDB: -90, peakDB: -10, speech: false) }
        #expect(envelope.level < 0.01)
    }
}

@Test func microphoneMeterInvalidValuesAndResetAreSafe() {
    var envelope = MicrophoneEnvelope()
    for value: Float in [.nan, .infinity, -.infinity, 10, -200] {
        let level = envelope.sample(averageDB: value, peakDB: value, speech: true)
        #expect(level.isFinite && (0...1).contains(level))
    }
    envelope.reset(); #expect(envelope.level == 0)
    for _ in 0..<5 { envelope.sample(averageDB: -160, peakDB: -160, speech: false) }
    #expect(envelope.level == 0)
}

@Test func microphoneDisplayLearnsSteadyRoomNoiseEvenWhenRawDetectorCallsItSpeech() {
    var detector = SpeechActivity(), envelope = MicrophoneEnvelope()
    for _ in 0..<150 {
        let speech = detector.sample(averageDB: -48)
        envelope.sample(averageDB: -48, peakDB: -42, speech: speech)
    }
    let stillSpeech = detector.sample(averageDB: -48)
    #expect(stillSpeech) // Display normalization did not change VAD.
    #expect(envelope.level < 0.01)
    var levels: [Double] = []
    for db: Float in [-40, -31, -45, -36, -47, -30] {
        for _ in 0..<4 { envelope.sample(averageDB: db, peakDB: db + 6, speech: detector.sample(averageDB: db)) }
        levels.append(envelope.level)
    }
    #expect((levels.max() ?? 0) > 0.7)
    #expect((levels.max() ?? 0) - (levels.min() ?? 0) > 0.4)
    for _ in 0..<15 { envelope.sample(averageDB: -90, peakDB: -84, speech: detector.sample(averageDB: -90)) }
    #expect(envelope.level < 0.01)
}
