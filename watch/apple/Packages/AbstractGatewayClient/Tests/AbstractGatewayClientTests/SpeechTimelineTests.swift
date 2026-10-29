import Testing
@testable import AbstractGatewayClient

// Operator 2026-10-29: the watch cut the voice for 2–4 s between the gateway's segments. Every
// segment is booked on the audio clock where the previous one ends; a late one starts at once.

private let sr = 24_000.0
private func f(_ seconds: Double) -> Int64 { Int64(seconds * sr) }

@Test func segmentsAreBookedBackToBackWithNoGap() {
    var t = SpeechTimeline(sampleRate: sr)
    #expect(t.receive(frames: f(2.0), rendered: 0).map(\.start) == [0])
    // The next arrives while the first still plays: it starts exactly where the first ends.
    let second = t.receive(frames: f(3.0), rendered: f(0.7))
    #expect(second == [.init(start: f(2.0), frames: f(3.0), gap: 0)])
    let third = t.receive(frames: f(1.0), rendered: f(4.9))
    #expect(third.first?.start == f(5.0) && third.first?.gap == 0)
    #expect(t.maxGapMilliseconds == 0)
}

@Test func theFirstStartWaitsForOneAndAHalfSecondsOfSpeech() {
    var t = SpeechTimeline(sampleRate: sr)
    #expect(t.receive(frames: f(1.0), rendered: 0).isEmpty, "a first piece of 1 s alone does not start")
    let both = t.receive(frames: f(1.0), rendered: 0)
    #expect(both.map(\.start) == [0, f(1.0)] && both.allSatisfy { $0.gap == 0 })
    // A short reading that ends under the buffer still plays.
    var short = SpeechTimeline(sampleRate: sr)
    #expect(short.receive(frames: f(0.8), rendered: 0).isEmpty)
    #expect(short.finish(rendered: 0).map(\.start) == [0])
}

@Test func aLateSegmentStartsAtOnceAndTheGapIsTheLateness() {
    var t = SpeechTimeline(sampleRate: sr)
    _ = t.receive(frames: f(2.0), rendered: 0)
    // The voice ran dry at 2.0 s; the next segment arrives at 2.4 s: it starts now, not later.
    let late = t.receive(frames: f(1.0), rendered: f(2.4))
    #expect(late.first?.start == f(2.4) && late.first?.gap == f(0.4))
    #expect(abs(t.maxGapMilliseconds - 400) < 0.5)
}

@Test func thePlayingSegmentIsFoundOnTheClock() {
    var t = SpeechTimeline(sampleRate: sr)
    _ = t.receive(frames: f(2.0), rendered: 0)
    _ = t.receive(frames: f(2.0), rendered: f(0.1))
    #expect(t.segment(at: f(2.5))?.index == 1 && t.segment(at: f(2.5))?.offset == f(0.5))
    #expect(t.segment(at: f(4.5)) == nil, "past the end: nothing plays")
}
