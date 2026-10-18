import XCTest

/// Opening a conversation from Sessions lands on that conversation: the orb screen, with that
/// conversation's last question below (sample data).
final class SessionsUITests: XCTestCase {
    func testOpeningASessionShowsItsTitleAndLastExchange() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--screen", "sessions"]
        app.launch()
        // A row is titled by its latest question, as the gateway has it (never its first, never made up).
        let row = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", "Now split it by age group")).firstMatch
        XCTAssertTrue(row.waitForExistence(timeout: 15), app.debugDescription)
        XCTAssertFalse(app.buttons.matching(NSPredicate(format: "label CONTAINS %@", "Compare overall survival")).firstMatch.exists,
                       "a row is titled by an older question:\n\(app.debugDescription)")
        row.tap()
        // The orb screen opens in that conversation: its last question shows (and, once answered,
        // its title in the status line; a turn still running says what it does instead).
        // (The orb is working on that turn here: "who answers" is hidden while it works.)
        let question = app.staticTexts["Now split it by age group"].firstMatch   // its last question
        XCTAssertTrue(question.waitForExistence(timeout: 15), "not the conversation tapped:\n\(app.debugDescription)")
        XCTAssertFalse(app.buttons["New conversation"].exists)
        if let dir = ProcessInfo.processInfo.environment["SHOTS_DIR"] {
            try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent("s1-opened.png"))
        }
    }
}

/// A conversation's page: its last 5 exchanges, Show older for the rest (then gone), and Read aloud
/// for the latest answer beside the title (sample conversation of 8 turns).
final class SessionPageUITests: XCTestCase {
    func testLastFiveShowOlderAndReadAloud() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--screen", "session-long"]
        app.launch()
        let older = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "Did the assay QC pass,"))
        let showOlder = app.buttons["Show older"].firstMatch
        XCTAssertTrue(showOlder.waitForExistence(timeout: 15), "no Show older:\n\(app.debugDescription)")
        XCTAssertEqual(older.count, 4, "the last 5 exchanges are the latest and 4 earlier ones")
        for _ in 0..<6 where !showOlder.isHittable { app.swipeDown() }
        showOlder.tap()
        sleep(2)
        XCTAssertEqual(older.count, 7, "all 8 exchanges after Show older:\n\(app.debugDescription)")
        XCTAssertFalse(app.buttons["Show older"].exists, "nothing older left")
        for _ in 0..<8 { app.swipeDown() }
        let read = app.buttons["Read aloud"].firstMatch
        XCTAssertTrue(read.waitForExistence(timeout: 5) && read.isHittable, "no Read aloud for the latest answer:\n\(app.debugDescription)")
        read.tap()
        XCTAssertTrue(app.buttons["voice.button"].waitForExistence(timeout: 10), "read aloud did not open")
    }
}

/// The orb page of a resumed conversation, as an automation's page: the last message in full, then
/// "Earlier messages" as cards (5, Show older for the rest); a card opens that message (with Read
/// aloud); the voice button plays / pauses the last message.
final class OrbHistoryUITests: XCTestCase {
    func testLastInFullEarlierCardsShowOlder() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--mock", "--no-notification-prompt", "--screen", "sessions"]
        app.launch()
        let row = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", "QC")).firstMatch
        XCTAssertTrue(app.buttons["New conversation"].waitForExistence(timeout: 15))
        for _ in 0..<6 where !(row.exists && row.isHittable) { app.swipeUp(); usleep(300_000) }   // rows build as they scroll in
        XCTAssertTrue(row.exists, app.debugDescription)
        row.tap()
        // The last message in full.
        XCTAssertTrue(app.staticTexts["The nightly assay QC passed: all 96 wells within range, CV 3.1 %."].waitForExistence(timeout: 20),
                      "the last message is not shown in full:\n\(app.debugDescription)")
        if let dir = ProcessInfo.processInfo.environment["SHOTS_DIR"] {   // the last message, just below the orb
            app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.7))
                .press(forDuration: 0.05, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.3)), withVelocity: .slow, thenHoldForDuration: 0.3)
            sleep(1)
            try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent("h0-last.png"))
        }
        // Earlier messages: 5 cards, then Show older.
        let cards = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "Did the assay QC pass,"))
        XCTAssertTrue(app.staticTexts["Earlier messages"].waitForExistence(timeout: 20), app.debugDescription)
        XCTAssertEqual(cards.count, 5, "5 earlier messages:\n\(app.debugDescription)")
        let showOlder = app.buttons["Show older"].firstMatch
        for _ in 0..<8 where !(showOlder.exists && showOlder.isHittable) { app.swipeUp() }
        if let dir = ProcessInfo.processInfo.environment["SHOTS_DIR"] {
            try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent("h2-earlier.png"))
        }
        showOlder.tap()
        sleep(2)
        XCTAssertEqual(cards.count, 7, "all 7 earlier messages after Show older")
        XCTAssertFalse(app.buttons["Show older"].exists, "nothing older left")
        // A card opens its message, with Read aloud.
        // Where a finger would tap it: below the top row (which takes the taps in its strip) and on
        // screen. Found by its question (a lazy list's n-th card changes as cards scroll in and out).
        let card = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "Did the assay QC pass, 3 nights ago")).firstMatch
        func drag(_ dy: CGFloat) {
            app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5))
                .press(forDuration: 0.05, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5 + dy)),
                       withVelocity: .slow, thenHoldForDuration: 0.2)
        }
        for _ in 0..<14 {
            if card.exists && card.frame.minY >= 70 && card.frame.maxY <= app.frame.maxY { break }
            if card.exists && card.frame.minY >= 70 { drag(-0.25) } else { drag(0.25) }   // below: up; above or not built: down
            usleep(300_000)
        }
        print("card frame \(card.frame) in \(app.frame)")
        card.tap()
        XCTAssertTrue(app.buttons["Read aloud"].waitForExistence(timeout: 10), "the message page has no Read aloud (card at \(card.frame))")
        app.buttons["Back"].firstMatch.tap()
        // The voice button reads the last message.
        let voice = app.buttons["voice.button"].firstMatch
        XCTAssertTrue(voice.waitForExistence(timeout: 10) && voice.label == "Play", app.debugDescription)
        voice.tap()
        var labels: [String] = []
        for _ in 0..<30 where voice.label != "Pause" { labels.append(voice.label + "/" + ((voice.value as? String) ?? "")); usleep(500_000) }
        if let dir = ProcessInfo.processInfo.environment["SHOTS_DIR"] {
            try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent("h3-read.png"))
        }
        XCTAssertEqual(voice.label, "Pause", "the last message is not read; labels \(labels)")
    }
}
