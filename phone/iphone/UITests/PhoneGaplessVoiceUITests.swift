import XCTest

/// Operator 2026-10-29: the voice was cut for 2–4 s between the gateway's segments. Each segment is
/// booked on the audio clock where the previous one ends: a long streamed reply (the demo's six
/// segments, 2.4 s, 2 s, then four of 8 s arriving 1.5 s apart while the voice speaks) plays with no
/// silence between segments (< 100 ms, measured from the players themselves), all of it. Sample data.
final class PhoneGaplessVoiceUITests: XCTestCase {
    @MainActor func testALongStreamedReplyPlaysWithoutGaps() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--demo", "--ui-test", "--history-fixture", "--long-voice", "--screen", "history"]
        app.launch()
        let readers = app.buttons.matching(identifier: "Read answer aloud")
        XCTAssertTrue(readers.firstMatch.waitForExistence(timeout: 15))
        let gaps = app.staticTexts["debug.gaps"].firstMatch
        XCTAssertTrue(gaps.waitForExistence(timeout: 10), "no gap probe:\n\(app.debugDescription)")
        readers.element(boundBy: readers.count - 1).tap()                    // the latest answer
        let on = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label ENDSWITH ' on'"), object: gaps)
        XCTAssertEqual(XCTWaiter.wait(for: [on], timeout: 10), .completed, gaps.label)
        let started = Date()
        var maxGap = 0
        while Date().timeIntervalSince(started) < 70 {
            let parts = gaps.label.split(separator: " ")
            maxGap = max(maxGap, Int(parts.first ?? "0") ?? 0)
            if parts.last == "off" { break }
            usleep(500_000)
        }
        let lasted = Date().timeIntervalSince(started)
        print("PHONE GAPLESS largest silence \(maxGap) ms, reading lasted \(String(format: "%.1f", lasted)) s")
        XCTAssertEqual(gaps.label.split(separator: " ").last, "off", "the reading did not end:\n\(gaps.label)")
        XCTAssertLessThan(maxGap, 100, "a silence of \(maxGap) ms between two segments")
        // 36.4 s of speech: a reading that ended much sooner skipped some of it.
        XCTAssertGreaterThan(lasted, 34, "the whole reply was not spoken (\(lasted) s)")
    }
}
