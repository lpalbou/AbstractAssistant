import XCTest

/// Operator 2026-10-29: the watch cut the voice for 2–4 s between the gateway's segments. Each
/// segment is booked on the audio clock where the previous one ends: a long streamed reply (the
/// mock's six segments, 1.3 s then 8 s each, arriving while the voice speaks) plays with no silence
/// between segments (< 100 ms; measured by the speaker on its own clock), then ends. Sample data.
final class GaplessVoiceUITests: XCTestCase {
    func testALongStreamedReplyPlaysWithoutGaps() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--long-voice"]
        app.launch()
        XCTAssertTrue(app.buttons["Settings"].waitForExistence(timeout: 15))
        app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Sessions'")).firstMatch.tap()
        XCTAssertTrue(app.buttons["New conversation"].waitForExistence(timeout: 10))
        let row = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", "QC")).firstMatch
        app.bring(row)
        row.tap()
        let voice = app.buttons["voice.button"]
        XCTAssertTrue(voice.waitForExistence(timeout: 20), app.debugDescription)
        sleep(1)
        voice.tap()                                                           // read the answer aloud
        let position = app.staticTexts["debug.position"].firstMatch
        let gaps = app.staticTexts["debug.gaps"].firstMatch
        XCTAssertTrue(gaps.waitForExistence(timeout: 10), "no gap probe:\n\(app.debugDescription)")
        // The whole reply: 1.3 + 5 × 8 s of speech; the probe says "done" at its end.
        let started = Date()
        var maxGap = 0
        var last = -1.0, stalls = 0.0
        while Date().timeIntervalSince(started) < 75 {
            let parts = gaps.label.split(separator: " ")
            maxGap = max(maxGap, Int(parts.first ?? "0") ?? 0)
            if parts.last == "done" { break }
            let now = Double(position.label) ?? -1
            if now > 0, now == last { stalls += 0.5 }                            // the position did not move
            last = now
            usleep(500_000)
        }
        print("GAPLESS largest silence \(maxGap) ms, position \(position.label) s, stalls \(stalls) s")
        XCTAssertEqual(gaps.label.split(separator: " ").last, "done", "the reply did not end:\n\(gaps.label)")
        XCTAssertLessThan(maxGap, 100, "a silence of \(maxGap) ms between two segments")
        XCTAssertGreaterThan(Double(position.label) ?? 0, 40, "the whole reply was not spoken (\(position.label) s)")
        XCTAssertLessThan(stalls, 2.0, "the voice stood still for \(stalls) s")
    }
}
