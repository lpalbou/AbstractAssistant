import XCTest

final class PhoneUITests: XCTestCase {
    @MainActor func testCategoryBulkControlsRespectHiddenAndDisabledTools() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test", "--reset-tool-defaults", "--category-fixture"]; app.launch(); openTools(app)
        let category = app.segmentedControls["tools.categoryMode.files"]
        XCTAssertTrue(category.waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["Mixed"].exists)
        capture(app, "Tools — category controls with mixed inherited Files choices")
        searchTools(app, for: "read_file")
        XCTAssertTrue(app.staticTexts["All 3 Files tools"].waitForExistence(timeout: 5))
        app.segmentedControls["tools.categoryMode.files"].buttons["Approve"].tap()
        searchTools(app, for: "files")
        XCTAssertTrue(app.segmentedControls["tool.read_file"].buttons["Approve"].isSelected)
        XCTAssertTrue(app.segmentedControls["tool.write_file"].buttons["Approve"].isSelected)
        XCTAssertFalse(app.segmentedControls["tool.blocked_file"].isEnabled)
        XCTAssertTrue(app.segmentedControls["tool.blocked_file"].buttons["Off"].isSelected)
        capture(app, "Tools — category choice includes hidden tools and keeps disabled tools Off")
        app.buttons["tools.save"].tap(); openTools(app)
        searchTools(app, for: "read_file")
        XCTAssertTrue(app.segmentedControls["tool.read_file"].buttons["Approve"].isSelected)
        searchTools(app, for: "fetch_url")
        XCTAssertTrue(app.segmentedControls["tool.fetch_url"].buttons["Approve"].isSelected)
    }
    @MainActor func testGroupedHistoryArchivesAndRestoresUsingExistingActions() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test", "--conversation-list-fixture"]; app.launch()
        app.buttons["chat.conversations"].tap()
        XCTAssertTrue(app.staticTexts["Today"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["Needs you"].exists); XCTAssertTrue(app.staticTexts["Working"].exists)
        XCTAssertTrue(app.staticTexts["Needs you"].isHittable)
        XCTAssertGreaterThan(app.staticTexts["Needs you"].frame.width, 35)
        XCTAssertGreaterThan(app.staticTexts["Working"].frame.width, 35)
        XCTAssertLessThan(app.staticTexts["Needs you"].frame.height, 26, "Status must remain readable on one line")
        XCTAssertLessThan(app.staticTexts["Working"].frame.height, 26)
        XCTAssertFalse(app.buttons["conversation.archive.s-build"].isEnabled)
        capture(app, "Conversations — Today groups, icon stats and visible states")
        app.swipeUp()
        let archive = app.buttons["conversation.archive.s-docs"]
        XCTAssertTrue(archive.waitForExistence(timeout: 5)); if !archive.isHittable { app.swipeUp() }
        capture(app, "Conversations — Yesterday and Earlier with archive actions")
        archive.tap(); XCTAssertTrue(app.buttons["Archive"].waitForExistence(timeout: 5))
        capture(app, "Archive — cross-device scope and restore confirmation")
        app.buttons["Archive"].tap()
        XCTAssertTrue(archive.waitForNonExistence(timeout: 5))
        app.swipeDown(); app.swipeDown()
        app.buttons["conversations.archived"].tap()
        let restore = app.buttons["conversation.restore.s-docs"]
        XCTAssertTrue(restore.waitForExistence(timeout: 10))
        capture(app, "Archived — original stats and restore action")
        restore.tap(); XCTAssertTrue(restore.waitForNonExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["Nothing archived"].waitForExistence(timeout: 5))
        app.navigationBars["Archived"].buttons.firstMatch.tap()
        app.swipeUp()
        XCTAssertTrue(app.buttons["conversation.archive.s-docs"].waitForExistence(timeout: 5))
    }
    @MainActor func testCycleGraphAndToolCallsHaveDistinctDestinationsAndDetails() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test", "--media-fixture", "--activity=cycle-detail", "--screen", "media"]; app.launch()
        let cycles = app.buttons["answer.cycles.media-demo"], tools = app.buttons["answer.tools.media-demo"]
        XCTAssertTrue(cycles.waitForExistence(timeout: 15)); XCTAssertTrue(tools.exists)
        cycles.tap(); XCTAssertTrue(app.navigationBars["Agent cycles"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["Cycle 1"].exists && app.staticTexts["Cycle 2"].exists)
        XCTAssertFalse(app.textFields["activity.tools.search"].exists)
        capture(app, "Cycles — connected progression with amber approval")
        app.buttons["activity.step.media-demo:cycle-1:model"].tap()
        XCTAssertTrue(app.staticTexts["I’ll read the notes and save a short summary."].waitForExistence(timeout: 5))
        capture(app, "Cycles — selected model output and timing")
        app.buttons["Done"].tap(); tools.tap()
        XCTAssertTrue(app.navigationBars["Tool calls"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.textFields["activity.tools.search"].exists)
        XCTAssertFalse(app.staticTexts["Cycle 1"].exists)
        capture(app, "Tools — individual calls in lavender")
        app.buttons["activity.step.media-demo:tool:read-notes"].tap()
        XCTAssertTrue(app.staticTexts["Input"].waitForExistence(timeout: 5)); XCTAssertTrue(app.staticTexts["Output"].exists)
        XCTAssertTrue(app.staticTexts.containing(NSPredicate(format: "label CONTAINS '[Hidden]'")).firstMatch.exists)
        XCTAssertFalse(app.staticTexts.containing(NSPredicate(format: "label CONTAINS 'fixture-private-key'")).firstMatch.exists)
        capture(app, "Tools — redacted input and public output")
        app.buttons["activity.step.media-demo:tool:read-notes"].tap()
        let search = app.textFields["activity.tools.search"]; search.tap(); search.typeText("summary")
        XCTAssertTrue(app.buttons["activity.step.media-demo:tool:write-summary"].exists)
        XCTAssertFalse(app.buttons["activity.step.media-demo:tool:read-notes"].exists)
        search.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: 7) + "fetch")
        app.buttons["activity.step.media-demo:tool:fetch-timeout"].tap()
        XCTAssertTrue(app.staticTexts["The server timed out."].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["Failed"].exists)
        capture(app, "Tools — failed call keeps lavender identity and red status")
    }
    @MainActor func testEmptyHistoryShowsActivityAccessWithoutZeroCounters() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test", "--media-fixture", "--activity=empty-history", "--screen", "media"]; app.launch()
        let activity = app.buttons["answer.activity.media-demo"]
        XCTAssertTrue(activity.waitForExistence(timeout: 15))
        XCTAssertFalse(app.buttons["answer.cycles.media-demo"].exists)
        XCTAssertFalse(app.buttons["answer.tools.media-demo"].exists)
        XCTAssertFalse(app.buttons["answer.emails.media-demo"].exists)
        capture(app, "Activity — no zero or unresolved count placeholders")
        activity.tap()
        XCTAssertTrue(app.staticTexts["No recorded activity for this answer."].waitForExistence(timeout: 5))
    }
    @MainActor func testDirectToolbarExposesActionsWithSettingsRightmost() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test", "--media-fixture", "--activity=timed-history", "--screen", "media"]; app.launch()
        let history = app.buttons["chat.conversations"], share = app.buttons["chat.share"], files = app.buttons["chat.files"], tools = app.buttons["chat.tools"], settings = app.buttons["chat.settings"]
        XCTAssertTrue(settings.waitForExistence(timeout: 15))
        for button in [history, share, files, tools, settings] { XCTAssertTrue(button.isHittable) }
        XCTAssertLessThan(history.frame.midX, share.frame.midX)
        XCTAssertLessThan(share.frame.midX, files.frame.midX); XCTAssertLessThan(files.frame.midX, tools.frame.midX)
        XCTAssertLessThan(tools.frame.midX, settings.frame.midX)
        XCTAssertGreaterThan(share.frame.minX - history.frame.maxX, 10)
        XCTAssertGreaterThan(settings.frame.minX - tools.frame.maxX, 10)
        XCTAssertFalse(app.buttons["chat.new"].exists)
        XCTAssertFalse(app.buttons["Share answer"].exists)
        XCTAssertTrue(app.buttons["answer.cycles.media-demo"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.buttons["answer.tools.media-demo"].exists)
        capture(app, "Navigation — three islands and quiet responder picker")
        files.tap(); XCTAssertTrue(app.navigationBars["Conversation files"].waitForExistence(timeout: 5)); app.buttons["Done"].tap()
        tools.tap(); XCTAssertTrue(app.navigationBars["Tools"].waitForExistence(timeout: 5)); app.buttons["tools.close"].tap()
        settings.tap(); XCTAssertTrue(app.navigationBars["Settings"].waitForExistence(timeout: 5)); app.buttons["Done"].tap()
        share.tap()
        XCTAssertTrue(app.cells["Copy"].waitForExistence(timeout: 10))
        capture(app, "Share — conversation text in native share sheet")
        app.cells["Copy"].tap()
        history.tap(); XCTAssertTrue(app.navigationBars["Conversations"].waitForExistence(timeout: 5))
        capture(app, "New conversation — accented action above history")
        app.buttons["New conversation"].tap()
        XCTAssertTrue(app.buttons["Type a message"].waitForExistence(timeout: 5))
        XCTAssertFalse(share.isEnabled)
        capture(app, "Navigation — empty conversation sharing disabled")
    }
    @MainActor func testSharedConversationIncludesBothSpeakers() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test", "--screen", "conversation"]; app.launch()
        XCTAssertTrue(app.buttons["Copy answer"].firstMatch.waitForExistence(timeout: 30))
        let share = app.buttons["chat.share"]
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true AND hittable == true"), object: share)], timeout: 15), .completed)
        share.tap()
        let copy = app.cells["Copy"]
        XCTAssertTrue(copy.waitForExistence(timeout: 10))
        capture(app, "Share — user and assistant conversation snapshot")
        copy.tap()
        XCTAssertTrue(app.buttons["chat.share"].isHittable)
    }
    @MainActor func testModelStepsExpandToTimingUsageAndPublicOutput() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test", "--activity=running", "--screen", "conversation"]; app.launch()
        let toggle = app.buttons["activity.toggle"]
        XCTAssertTrue(toggle.waitForExistence(timeout: 15)); toggle.tap()
        let row = app.buttons["activity.step.activity-child:cycle-1:model"]
        XCTAssertTrue(row.waitForExistence(timeout: 5)); row.tap()
        XCTAssertTrue(app.staticTexts["assistant-model"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["1,254 in · 32 out"].exists || app.staticTexts["1254 in · 32 out"].exists)
        XCTAssertTrue(app.staticTexts["I’ll inspect the host’s operating system and architecture."].exists)
        XCTAssertTrue(app.staticTexts["3.0 s"].exists)
        capture(app, "Activity — expanded model timing and public output")
    }
    @MainActor func testHistoricalActivityExplainsRoutingAndMediaWithTime() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test", "--media-fixture", "--activity=timed-history", "--screen", "media"]; app.launch()
        let cycles = app.buttons["answer.cycles.media-demo"]
        XCTAssertTrue(cycles.waitForExistence(timeout: 15)); cycles.tap()
        XCTAssertTrue(app.staticTexts["Oldest first · Times on this iPhone"].waitForExistence(timeout: 5))
        capture(app, "Activity — chronological completed media steps")
        let route = app.buttons["activity.step.media-demo:route:model"]
        XCTAssertTrue(route.exists); route.tap()
        XCTAssertTrue(app.staticTexts["Routing decision"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["router-model"].exists)
        capture(app, "Activity — routing decision and recorded timings")
        route.tap()
        capture(app, "Activity — routing collapsed before opening generation")
        app.buttons["activity.step.media-demo:image:model"].tap()
        XCTAssertTrue(app.staticTexts.containing(NSPredicate(format: "label CONTAINS 'Requested output: image'")).firstMatch.waitForExistence(timeout: 5))
        capture(app, "Activity — generation result and elapsed time")
    }
    @MainActor func testSentEmailReceiptsShowMessageRecipientsAndRecordedTime() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test", "--media-fixture", "--email-fixture", "--screen", "media"]; app.launch()
        let sent = app.buttons["answer.emails.media-demo"], read = app.buttons["answer.read-emails.media-demo"]
        XCTAssertTrue(sent.waitForExistence(timeout: 15)); XCTAssertTrue(read.exists)
        XCTAssertEqual(sent.label, "3 sent emails. View receipts")
        XCTAssertEqual(read.label, "3 read emails. View messages")
        capture(app, "Email collections — separate directional counts")
        sent.tap()
        XCTAssertTrue(app.navigationBars["Sent emails"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["Our discussion"].exists)
        XCTAssertTrue(app.staticTexts["Re: Our discussion"].exists)
        XCTAssertTrue(app.staticTexts.containing(NSPredicate(format: "label BEGINSWITH 'Project handoff'")).firstMatch.exists)
        capture(app, "Email collections — three sent messages")
        app.buttons["email.row.0"].tap()
        XCTAssertTrue(app.navigationBars["Sent email"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["alex@example.com"].firstMatch.exists)
        XCTAssertTrue(app.staticTexts["you@example.com"].firstMatch.exists)
        XCTAssertTrue(app.staticTexts.containing(NSPredicate(format: "label CONTAINS 'Here is a short summary'")).firstMatch.exists)
        XCTAssertFalse(app.staticTexts["Time unavailable"].exists)
        capture(app, "Email collections — individual sent message")
        app.navigationBars["Sent email"].buttons.element(boundBy: 0).tap()
        app.buttons["email.row.2"].tap()
        XCTAssertTrue(app.staticTexts["alex@example.com, sam@example.com, design-team@example.com"].waitForExistence(timeout: 5))
        capture(app, "Email collections — long subject and several recipients")
        app.buttons["Done"].tap()
        XCTAssertTrue(read.waitForExistence(timeout: 5)); read.tap()
        XCTAssertTrue(app.navigationBars["Read emails"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["Project notes"].exists)
        XCTAssertTrue(app.staticTexts["Large message"].exists)
        capture(app, "Email collections — three read messages")
        app.buttons["email.row.0"].tap()
        XCTAssertTrue(app.staticTexts["Alex <alex@example.com>"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts.containing(NSPredicate(format: "label CONTAINS 'The project notes are ready'")).firstMatch.exists)
        capture(app, "Email collections — individual read message")
        app.navigationBars["Read email"].buttons.element(boundBy: 0).tap()
        app.buttons["email.row.2"].tap()
        XCTAssertTrue(app.staticTexts["Headers only"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["Only headers were read. Message exceeds the reading limit."].exists)
    }
    @MainActor func testEmailCollectionSearchOpensTheMatchingMessage() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test", "--media-fixture", "--email-fixture", "--screen", "media"]; app.launch()
        XCTAssertTrue(app.buttons["answer.emails.media-demo"].waitForExistence(timeout: 15))
        app.buttons["answer.emails.media-demo"].tap()
        let search = app.searchFields.firstMatch
        if !search.isHittable { app.swipeDown() }
        XCTAssertTrue(search.waitForExistence(timeout: 5)); search.tap(); search.typeText("design-team")
        XCTAssertTrue(app.staticTexts.containing(NSPredicate(format: "label BEGINSWITH 'Project handoff'")).firstMatch.waitForExistence(timeout: 5))
        XCTAssertFalse(app.staticTexts["Our discussion"].exists)
        app.buttons["email.row.0"].tap()
        XCTAssertTrue(app.navigationBars["Sent email"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["alex@example.com, sam@example.com, design-team@example.com"].exists)
        capture(app, "Email collections — searched message detail")
    }

    @MainActor func testOptionalFileActionsShowRecordedReadsAndChangesAndOpenWorkspace() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test", "--media-fixture", "--access-fixture", "--screen", "media"]; app.launch()
        let read = app.buttons["answer.access.filesRead.media-demo"], changed = app.buttons["answer.access.filesChanged.media-demo"]
        XCTAssertTrue(read.waitForExistence(timeout: 15)); XCTAssertEqual(read.label,"2 files read. View sources")
        XCTAssertEqual(changed.label,"1 files changed. View sources")
        XCTAssertFalse(app.buttons["answer.read-emails.media-demo"].exists); XCTAssertFalse(app.buttons["answer.emails.media-demo"].exists)
        capture(app,"Sources — positive file actions")
        read.tap(); XCTAssertTrue(app.navigationBars["Files read"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["notes.md"].exists); XCTAssertTrue(app.staticTexts["plan.md"].exists)
        XCTAssertFalse(app.staticTexts["missing.md"].exists)
        capture(app,"Sources — files read collection")
        app.buttons["access.row.0"].tap()
        XCTAssertTrue(app.staticTexts.containing(NSPredicate(format:"label CONTAINS 'Review the available evidence'")).firstMatch.waitForExistence(timeout:5))
        capture(app,"Sources — read and skim excerpts")
        app.buttons["access.browse-files"].tap()
        XCTAssertTrue(app.navigationBars["Conversation files"].waitForExistence(timeout: 10))
        app.buttons["files.workspace.discussion-summary.md"].tap()
        XCTAssertTrue(app.staticTexts["Discussion summary"].waitForExistence(timeout:10)); app.buttons["media.preview.close"].tap(); app.buttons["Done"].tap()
        changed.tap(); XCTAssertTrue(app.staticTexts["discussion-summary.md"].waitForExistence(timeout:5)); app.buttons["access.row.0"].tap()
        XCTAssertTrue(app.staticTexts["Written"].waitForExistence(timeout:5)); XCTAssertTrue(app.staticTexts["Edited"].exists)
        capture(app,"Sources — write and edit receipts")
    }
    @MainActor func testWebSearchAndPageReceiptsStaySeparateAndScrollable() throws {
        let app=XCUIApplication();app.launchArguments=["--demo","--ui-test","--media-fixture","--email-fixture","--access-fixture","--screen","media"];app.launch()
        let search=app.buttons["answer.access.searches.media-demo"], pages=app.buttons["answer.access.pages.media-demo"]
        XCTAssertTrue(search.waitForExistence(timeout:15)); let strip=app.scrollViews["answer.actions.media-demo"]
        if !search.isHittable {strip.swipeLeft()}
        XCTAssertEqual(search.label,"2 web searches. View sources");XCTAssertEqual(pages.label,"2 web pages fetched. View sources")
        capture(app,"Sources — full optional strip scrolled")
        search.tap();XCTAssertTrue(app.navigationBars["Web searches"].waitForExistence(timeout:5))
        XCTAssertTrue(app.staticTexts["Swift UI accessibility"].firstMatch.exists);XCTAssertTrue(app.staticTexts["Swift file previews"].firstMatch.exists)
        capture(app,"Sources — skim and full searches")
        app.buttons["access.row.0"].tap();XCTAssertTrue(app.buttons["Accessibility guide"].waitForExistence(timeout:5))
        capture(app,"Sources — search result leads")
        app.buttons["Done"].tap();if !pages.isHittable {strip.swipeLeft()};pages.tap()
        XCTAssertTrue(app.navigationBars["Web pages fetched"].waitForExistence(timeout:5));capture(app,"Sources — fetched pages")
        app.buttons["access.row.1"].tap();XCTAssertTrue(app.staticTexts["Requested: https://example.com/previews"].waitForExistence(timeout:5))
        XCTAssertTrue(app.staticTexts.containing(NSPredicate(format:"label CONTAINS 'A preview lets people inspect'")).firstMatch.exists)
        capture(app,"Sources — fetched page excerpt and redirect")
    }
    @MainActor func testZeroMailDirectionsAndUnusedSourcesAreHiddenIndependently() throws {
        let app=XCUIApplication()
        for mode in ["mail-sent","mail-read"] {
            app.launchArguments=["--demo","--ui-test","--media-fixture","--email-fixture","--activity="+mode,"--screen","media"];app.launch()
            let positive=app.buttons[mode=="mail-sent" ? "answer.emails.media-demo" : "answer.read-emails.media-demo"]
            XCTAssertTrue(positive.waitForExistence(timeout:15))
            XCTAssertFalse(app.buttons[mode=="mail-sent" ? "answer.read-emails.media-demo" : "answer.emails.media-demo"].exists)
            for kind in ["filesRead","filesChanged","searches","pages"] {XCTAssertFalse(app.buttons["answer.access."+kind+".media-demo"].exists)}
            XCTAssertFalse(app.buttons["answer.files"].exists)
        }
        capture(app,"Sources — no zero-count actions")
    }
    @MainActor func testCompletedActionsAreCompactAndOpenAnswerActivity() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test", "--media-fixture", "--screen", "media"]; app.launch()
        XCTAssertTrue(app.buttons["answer.cycles.media-demo"].waitForExistence(timeout: 15))
        XCTAssertFalse(app.buttons["answer.tools.media-demo"].exists)
        XCTAssertFalse(app.staticTexts["Activity complete"].exists)
        XCTAssertFalse(app.buttons["activity.toggle"].exists)
        XCTAssertFalse(app.buttons["answer.emails.media-demo"].exists)
        XCTAssertFalse(app.buttons["answer.read-emails.media-demo"].exists)
        XCTAssertFalse(app.buttons["answer.files"].exists)
        capture(app, "Files — compact completed answer actions")
        app.buttons["answer.cycles.media-demo"].tap()
        XCTAssertTrue(app.navigationBars["Model calls"].waitForExistence(timeout: 5))
        capture(app, "Files — answer activity sheet")
    }
    @MainActor func testSessionWorkspaceMarkdownAndHierarchyPreview() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test", "--media-fixture", "--screen", "media"]; app.launch()
        XCTAssertTrue(app.buttons["Conversation files"].waitForExistence(timeout: 15)); app.buttons["Conversation files"].tap()
        let summary = app.buttons["files.workspace.discussion-summary.md"]
        XCTAssertTrue(summary.waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["Research"].exists)
        capture(app, "Files — workspace documents and attachments")
        summary.tap()
        XCTAssertTrue(app.staticTexts["Discussion summary"].waitForExistence(timeout: 10))
        capture(app, "Files — rendered Markdown preview")
        app.buttons["media.preview.close"].tap()
        app.staticTexts["Research"].tap()
        XCTAssertTrue(app.buttons["files.workspace.Research/notes.md"].waitForExistence(timeout: 5))
        capture(app, "Files — nested workspace folder")
        app.buttons["files.workspace.Research/notes.md"].tap()
        XCTAssertTrue(app.staticTexts["Research notes"].waitForExistence(timeout: 10))
        app.buttons["media.preview.close"].tap()
    }
    @MainActor func testConversationAudioToggleKeepsGeneratedVoiceVisible() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test", "--media-fixture", "--screen", "media"]; app.launch()
        XCTAssertTrue(app.buttons["Conversation files"].waitForExistence(timeout: 15)); app.buttons["Conversation files"].tap()
        XCTAssertTrue(app.buttons["files.artifact.demo-voice"].waitForExistence(timeout: 10))
        XCTAssertFalse(app.buttons["files.artifact.demo-playback"].exists)
        app.switches["files.voice"].coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: 0.5)).tap()
        XCTAssertTrue(app.buttons["files.artifact.demo-playback"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["files.artifact.demo-voice"].exists)
        capture(app, "Files — optional conversation audio")
    }
    @MainActor func testGeneratedImageAndVoiceAreInlineAndImageCanBeReused() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test", "--media-fixture", "--screen", "media"]; app.launch()
        let image = app.buttons["media.image.demo-image"]
        XCTAssertTrue(image.waitForExistence(timeout: 15))
        XCTAssertTrue(NSPredicate(format: "value == 'Ready'").evaluate(with: image) || XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == 'Ready'"), object: image)], timeout: 10) == .completed)
        XCTAssertTrue(app.buttons["media.play.demo-voice"].exists)
        capture(app, "Media — generated image and voice in the restored AI message")
        app.buttons["media.reference.demo-image"].tap()
        XCTAssertTrue(app.buttons["Remove Quiet horizon.png"].exists || app.staticTexts["Quiet horizon.png"].exists)
        capture(app, "Media — generated image reused as a reference")
    }
    @MainActor func testRestoredImageSurvivesColdRelaunchPreviewAndTabChanges() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--demo", "--ui-test", "--media-fixture", "--screen", "media"]
        for launch in 0..<2 {
            app.launch()
            let image = app.buttons["media.image.demo-image"]
            XCTAssertTrue(image.waitForExistence(timeout: 15))
            XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == 'Ready'"), object: image)], timeout: 10), .completed)
            XCTAssertFalse(app.otherElements["media.error.demo-image"].exists)
            image.tap()
            XCTAssertTrue(app.images["media.preview.image"].waitForExistence(timeout: 10))
            app.buttons["media.preview.close"].tap()
            XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == 'Ready'"), object: image)], timeout: 10), .completed)
            app.tabBars.buttons["Inbox"].tap(); app.tabBars.buttons["Assistant"].tap()
            XCTAssertTrue(image.waitForExistence(timeout: 10))
            XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == 'Ready'"), object: image)], timeout: 10), .completed)
            XCTAssertFalse(app.staticTexts["cancelled"].exists)
            capture(app, "Restored image — cold launch \(launch + 1), preview and navigation")
            app.terminate()
        }
    }
    @MainActor func testGeneratedImageOpensNativePreview() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test", "--media-fixture", "--screen", "media"]; app.launch()
        let image = app.buttons["media.image.demo-image"]
        XCTAssertTrue(image.waitForExistence(timeout: 15))
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == 'Ready'"), object: image)], timeout: 10), .completed)
        image.tap()
        let close = app.buttons["media.preview.close"]
        XCTAssertTrue(close.waitForExistence(timeout: 5))
        XCTAssertTrue(app.images["media.preview.image"].waitForExistence(timeout: 10))
        capture(app, "Media — full screen native image preview")
        close.tap()
        XCTAssertTrue(image.waitForExistence(timeout: 5))
    }
    @MainActor func testGeneratedVoicePlaybackIsInlineAndStops() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test", "--media-fixture", "--screen", "media"]; app.launch()
        let play = app.buttons["media.play.demo-voice"]
        XCTAssertTrue(play.waitForExistence(timeout: 15)); play.tap()
        XCTAssertTrue(app.buttons["Stop audio"].waitForExistence(timeout: 5))
        capture(app, "Media — voice playback with scrubber")
        app.buttons["Stop audio"].tap()
        XCTAssertFalse(app.buttons["Stop audio"].exists)
    }
    @MainActor func testLiveActivityExpandsAndShowsToolResults() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test", "--activity=running", "--screen", "conversation"]; app.launch()
        let toggle = app.buttons["activity.toggle"]
        XCTAssertTrue(toggle.waitForExistence(timeout: 15))
        XCTAssertFalse(app.staticTexts["Your assistant is working…"].exists)
        capture(app, "Activity — compact live view")
        toggle.tap()
        XCTAssertTrue(app.staticTexts["read file, Done"].exists || app.staticTexts.containing(NSPredicate(format: "label CONTAINS 'read file'")).firstMatch.exists || app.buttons.containing(NSPredicate(format: "label CONTAINS 'read file'")).firstMatch.exists)
        let result = app.buttons.containing(NSPredicate(format: "label CONTAINS 'read file'")).firstMatch
        if result.exists { result.tap() }
        XCTAssertTrue(app.staticTexts["Operating system: Linux. Architecture: arm64."].waitForExistence(timeout: 5))
        capture(app, "Activity — tool result expanded")
        toggle.tap()
        XCTAssertFalse(app.staticTexts["Operating system: Linux. Architecture: arm64."].exists)
    }
    @MainActor func testChildApprovalIsVisibleInConversationAndOffersThreeChoices() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test", "--activity=approval", "--screen", "conversation"]; app.launch()
        XCTAssertTrue(app.buttons["activity.review"].waitForExistence(timeout: 15))
        XCTAssertTrue(app.staticTexts["Approval needed"].exists)
        XCTAssertFalse(app.staticTexts["Your assistant is working…"].exists)
        capture(app, "Activity — approval needs you")
        app.buttons["activity.review"].tap()
        XCTAssertTrue(app.buttons["Approve"].waitForExistence(timeout: 5))
        app.swipeUp()
        XCTAssertTrue(app.buttons["Deny"].exists)
        XCTAssertTrue(app.buttons["approval.all"].exists)
        capture(app, "Approval — three choices and conversation scope")
        app.buttons["approval.all"].tap()
        XCTAssertTrue(app.buttons["answer.tools.activity-root"].waitForExistence(timeout: 15))
        XCTAssertFalse(app.buttons["activity.review"].exists)
        capture(app, "Activity — completed after approval")
    }
    @MainActor func testFailedRunAndLostConnectionHaveDistinctFeedback() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test", "--activity=failure", "--screen", "conversation"]; app.launch()
        XCTAssertTrue(app.staticTexts["Couldn’t finish"].waitForExistence(timeout: 15))
        XCTAssertTrue(app.staticTexts["activity.failure"].exists)
        capture(app, "Activity — failure preserved")
        app.terminate(); app.launchArguments = ["--demo", "--ui-test", "--activity=offline", "--screen", "conversation"]; app.launch()
        XCTAssertTrue(app.buttons["Reconnect activity"].waitForExistence(timeout: 15))
        XCTAssertFalse(app.staticTexts["Couldn’t finish"].exists)
        capture(app, "Activity — connection lost")
    }
    @MainActor func testConversationAndNavigation() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--demo", "--ui-test"]
        app.launch()
        XCTAssertTrue(app.staticTexts["What’s on your mind?"].waitForExistence(timeout: 10))
        capture(app, "Assistant")
        app.buttons["Find a little focus"].firstMatch.tap()
        app.buttons["Send message"].tap()
        XCTAssertTrue(app.buttons["Copy answer"].firstMatch.waitForExistence(timeout: 30))
        let finished = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == %@", "Tap to speak"), object: app.buttons["voice.orb"])
        XCTAssertEqual(XCTWaiter.wait(for: [finished], timeout: 30), .completed)
        XCTAssertTrue(app.buttons["voice.orb"].exists)
        XCTAssertFalse(app.buttons["answer.files"].exists)
        XCTAssertTrue(app.buttons["Settings"].isHittable)
        XCTAssertTrue(app.buttons["voice.orb"].isHittable)
        capture(app, "Conversation")
        app.tabBars.buttons["Inbox"].tap()
        XCTAssertTrue(app.staticTexts["RECENT ACTIVITY"].exists)
        capture(app, "Inbox")
        app.tabBars.buttons["Automations"].tap()
        XCTAssertTrue(app.staticTexts["Morning digest"].exists)
        capture(app, "Automations")
    }
    @MainActor func testWorkingOrbIsTheOnlyStopAndReturnsAfterCancellation() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test"]; app.launch()
        XCTAssertTrue(app.buttons["Find a little focus"].firstMatch.waitForExistence(timeout: 10))
        app.buttons["Find a little focus"].firstMatch.tap(); app.buttons["Send message"].tap()
        let orb = app.buttons["voice.orb"]
        let working = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == %@ AND enabled == true", "Stop assistant"), object: orb)
        XCTAssertEqual(XCTWaiter.wait(for: [working], timeout: 10), .completed)
        XCTAssertFalse(app.staticTexts["Waiting for your assistant…"].exists)
        XCTAssertFalse(app.buttons["Stop"].exists)
        XCTAssertFalse(app.staticTexts["Your assistant needs you"].exists) // Unrelated Inbox waits stay in Inbox.
        XCTAssertTrue(app.buttons["activity.toggle"].exists)
        capture(app, "Working orb — single progress indicator")
        orb.tap()
        let restored = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == %@ AND enabled == true", "Tap to speak"), object: orb)
        XCTAssertEqual(XCTWaiter.wait(for: [restored], timeout: 10), .completed)
        XCTAssertTrue(app.staticTexts["Run stopped."].exists)
        XCTAssertTrue(app.buttons["composer.keyboard"].isEnabled)
        XCTAssertFalse(app.staticTexts["Your assistant is working…"].exists)
        capture(app, "Orb restored after stop")
    }
    @MainActor func testApprovalShowsActionAndReturnsToInbox() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--demo", "--ui-test", "--screen", "inbox"]
        app.launch()
        let permission = app.buttons.containing(.staticText, identifier: "Permission to proceed").firstMatch
        XCTAssertTrue(permission.waitForExistence(timeout: 10)); permission.tap()
        XCTAssertTrue(app.buttons["Approve"].waitForExistence(timeout: 10))
        capture(app, "Approval")
        app.buttons["Deny"].tap()
        XCTAssertTrue(app.staticTexts["RECENT ACTIVITY"].waitForExistence(timeout: 10))
    }
    @MainActor func testVoiceSettingsAndWorkflowAreAvailable() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test"]; app.launch()
        openSettings(app)
        app.buttons["Voice & reading"].tap()
        XCTAssertTrue(app.switches["voice.readAloud"].waitForExistence(timeout: 10))
        // iOS exposes the whole labelled row as a switch; tap the actual trailing control.
        app.switches["voice.readAloud"].coordinate(withNormalizedOffset: CGVector(dx: 0.88, dy: 0.5)).tap()
        let enabled = XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == '1'"), object: app.switches["voice.readAloud"])
        XCTAssertEqual(XCTWaiter.wait(for: [enabled], timeout: 5), .completed)
        XCTAssertTrue(app.buttons["voice.choices"].waitForExistence(timeout: 10))
        XCTAssertFalse(app.buttons["Preview voice"].exists)
        capture(app, "Voice settings")
        app.buttons["voice.choices"].tap()
        let choice = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Supertonic · M1'")).firstMatch
        XCTAssertTrue(choice.waitForExistence(timeout: 5)); choice.tap()
        XCTAssertTrue(app.buttons["Stop sample"].waitForExistence(timeout: 5))
        capture(app, "Voice choices")
        app.navigationBars.buttons.firstMatch.tap()
        app.buttons["1.5×"].tap()
        XCTAssertTrue(app.buttons["Stop sample"].waitForExistence(timeout: 5))
        capture(app, "Speaking speed")
        app.buttons["Stop sample"].tap()
        app.buttons["voice.transcription"].tap()
        XCTAssertTrue(app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'large-v3-turbo'")).firstMatch.waitForExistence(timeout: 5))
        capture(app, "Speech recognition")
        app.navigationBars.buttons.firstMatch.tap()
        app.navigationBars.buttons.firstMatch.tap()
        app.buttons["Workflow"].tap()
        XCTAssertTrue(app.buttons["Save workflow"].waitForExistence(timeout: 10))
        capture(app, "Workflow settings")
    }
    @MainActor func testCreateAutomationOnThePhone() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test", "--screen", "automations"]; app.launch()
        XCTAssertTrue(app.buttons["New automation"].waitForExistence(timeout: 10)); app.buttons["New automation"].tap()
        let field = app.textFields["automation.task"].exists ? app.textFields["automation.task"] : app.textViews["automation.task"]
        XCTAssertTrue(field.waitForExistence(timeout: 10)); field.tap(); field.typeText("My phone daily briefing")
        app.staticTexts["What should it do?"].tap()
        capture(app, "New automation")
        let create = app.buttons["automation.create"]
        for _ in 0..<4 { if create.isHittable { break }; app.swipeUp() }
        XCTAssertTrue(create.isHittable); create.tap()
        XCTAssertTrue(app.staticTexts["My phone daily briefing"].firstMatch.waitForExistence(timeout: 20))
        capture(app, "Created automation")
    }
    @MainActor func testConversationFilesAreVisible() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test"]; app.launch()
        XCTAssertTrue(app.buttons["Conversation files"].waitForExistence(timeout: 10)); app.buttons["Conversation files"].tap()
        XCTAssertTrue(app.staticTexts["A little focus.txt"].waitForExistence(timeout: 10))
        capture(app, "Conversation files")
    }
    @MainActor func testKeyboardExpandsInputHidesOrbAndOutsideTapRestoresButtons() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test"]; app.launch()
        let input = app.textFields["composer.input"]
        let keyboard = app.buttons["composer.keyboard"]
        let orb = app.buttons["voice.orb"]
        let attachment = app.buttons["Add attachment"]
        XCTAssertTrue(orb.waitForExistence(timeout: 10))
        XCTAssertTrue(keyboard.isHittable)
        XCTAssertFalse(input.exists)
        XCTAssertLessThan(abs(keyboard.frame.midY - attachment.frame.midY), 3)
        XCTAssertLessThan(abs(keyboard.frame.midY - orb.frame.midY), 3)
        XCTAssertGreaterThan(orb.frame.midX, app.frame.width * 0.75)
        capture(app, "Floating controls")
        keyboard.tap()
        XCTAssertTrue(input.waitForExistence(timeout: 5)); input.typeText("Keep this typed draft")
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 5))
        XCTAssertFalse(orb.exists)
        XCTAssertFalse(keyboard.exists)
        XCTAssertGreaterThan(input.frame.width, app.frame.width * 0.5)
        XCTAssertTrue(attachment.isHittable)
        XCTAssertTrue(app.buttons["Send message"].isHittable)
        XCTAssertFalse(app.buttons["Done"].exists)
        capture(app, "Keyboard composer")
        input.tap() // Caret and input taps keep editing active.
        XCTAssertTrue(app.keyboards.firstMatch.exists)
        app.staticTexts["What’s on your mind?"].tap()
        let dismissed = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: app.keyboards.firstMatch)
        XCTAssertEqual(XCTWaiter.wait(for: [dismissed], timeout: 5), .completed)
        XCTAssertTrue(orb.isHittable)
        XCTAssertTrue(keyboard.isHittable)
        XCTAssertFalse(input.exists)
        XCTAssertEqual(keyboard.value as? String, "Draft saved")
        capture(app, "Minimized draft")
        keyboard.tap()
        XCTAssertTrue(input.waitForExistence(timeout: 5))
        XCTAssertEqual(input.value as? String, "Keep this typed draft")
        app.buttons["Send message"].tap()
        XCTAssertTrue(app.staticTexts["Keep this typed draft"].waitForExistence(timeout: 10))
        XCTAssertTrue(orb.waitForExistence(timeout: 5))
    }
    @MainActor func testOutsideTapPreservesTheAttachmentButtonAction() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test"]; app.launch()
        XCTAssertTrue(app.buttons["composer.keyboard"].waitForExistence(timeout: 10))
        app.buttons["composer.keyboard"].tap()
        app.textFields["composer.input"].typeText("A draft")
        app.buttons["Add attachment"].tap()
        XCTAssertTrue(app.buttons["Choose a file"].waitForExistence(timeout: 5))
        let dismissed = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: app.keyboards.firstMatch)
        XCTAssertEqual(XCTWaiter.wait(for: [dismissed], timeout: 5), .completed)
    }
    @MainActor func testKeyboardSwitchCancelsLocalVoice() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test", "--voice-fixture"]; app.launch()
        let orb = app.buttons["voice.orb"]
        XCTAssertTrue(orb.waitForExistence(timeout: 10)); orb.tap()
        XCTAssertTrue(app.staticTexts["Listening"].waitForExistence(timeout: 5))
        app.buttons["composer.keyboard"].tap()
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 5))
        XCTAssertFalse(orb.exists)
        XCTAssertFalse(app.staticTexts["Listening"].exists)
        XCTAssertFalse(app.buttons["Copy answer"].waitForExistence(timeout: 5))
    }
    @MainActor func testSuggestionSwitchCancelsLocalVoice() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test", "--voice-fixture"]; app.launch()
        let orb = app.buttons["voice.orb"]
        XCTAssertTrue(orb.waitForExistence(timeout: 10)); orb.tap()
        XCTAssertTrue(app.staticTexts["Listening"].waitForExistence(timeout: 5))
        app.buttons["Find a little focus"].firstMatch.tap()
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 5))
        XCTAssertFalse(orb.exists)
        XCTAssertEqual(app.textFields["composer.input"].value as? String, "Help me make room for focused work this week.")
        XCTAssertFalse(app.buttons["Copy answer"].waitForExistence(timeout: 5))
    }
    @MainActor func testTapSilenceCancelAndAutomaticVoiceSend() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test", "--voice-fixture"]; app.launch()
        let orb = app.buttons["voice.orb"]
        XCTAssertTrue(orb.waitForExistence(timeout: 10))
        let input = app.textFields["composer.input"]
        app.buttons["composer.keyboard"].tap(); input.typeText("Keep my keyboard draft")
        app.staticTexts["What’s on your mind?"].tap()
        orb.tap()
        let countdown = app.buttons.matching(NSPredicate(format: "identifier == 'voice.orb' AND label BEGINSWITH 'Sending in '")).firstMatch
        XCTAssertTrue(countdown.waitForExistence(timeout: 6))
        XCTAssertTrue(app.staticTexts["Listening"].exists)
        XCTAssertFalse(app.buttons["Cancel voice message"].exists)
        XCTAssertFalse(app.buttons["Cancel"].exists)
        // Touch DOWN cancels even when it lifts after the previous silence deadline.
        orb.press(forDuration: 3.2)
        XCTAssertFalse(app.staticTexts["Listening"].exists)
        XCTAssertFalse(app.buttons["Copy answer"].waitForExistence(timeout: 4))
        orb.tap()
        XCTAssertTrue(countdown.waitForExistence(timeout: 6))
        capture(app, "Voice listening")
        XCTAssertTrue(app.staticTexts["Help me make room for focused work this week"].firstMatch.waitForExistence(timeout: 12))
        XCTAssertTrue(app.buttons["Copy answer"].firstMatch.waitForExistence(timeout: 30))
        XCTAssertTrue(orb.exists)
        // A partial answer appears before the gateway run completes; editing requires ready.
        let keyboard = app.buttons["composer.keyboard"]
        let ready = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true AND hittable == true"), object: keyboard)
        XCTAssertEqual(XCTWaiter.wait(for: [ready], timeout: 15), .completed)
        keyboard.tap()
        XCTAssertTrue(input.waitForExistence(timeout: 5))
        XCTAssertEqual(input.value as? String, "Keep my keyboard draft")
    }
    @MainActor func testEmptyAutomationHasOnePaddedCreateAction() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test", "--empty-automations", "--screen", "automations"]; app.launch()
        XCTAssertTrue(app.staticTexts["No automations yet"].waitForExistence(timeout: 10))
        let create = app.buttons["automations.create"]
        XCTAssertEqual(app.buttons.matching(NSPredicate(format: "label == 'New automation'")).count, 1)
        XCTAssertGreaterThanOrEqual(create.frame.height, 50)
        XCTAssertGreaterThan(create.frame.minX, 20)
        XCTAssertLessThan(create.frame.maxX, app.frame.width - 20)
        capture(app, "Empty automations")
        create.tap(); XCTAssertTrue(app.textFields["automation.task"].waitForExistence(timeout: 5))
    }
    @MainActor func testDirectToolbarRemainsReachableWithALongEntityName() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test"]; app.launch()
        let chooser = app.buttons["Choose who answers"]
        XCTAssertTrue(chooser.waitForExistence(timeout: 10)); chooser.tap(); app.buttons["entities.new"].tap()
        let name = app.textFields["entity.name"]
        XCTAssertTrue(name.waitForExistence(timeout: 5)); name.tap(); name.typeText("My research and writing companion")
        let create = app.buttons["entity.create"]
        let ready = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true AND hittable == true"), object: create)
        XCTAssertEqual(XCTWaiter.wait(for: [ready], timeout: 10), .completed); create.tap()
        let opened = XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == 'My research and writing companion'"), object: chooser)
        XCTAssertEqual(XCTWaiter.wait(for: [opened], timeout: 15), .completed)
        XCTAssertTrue(app.buttons["chat.files"].isHittable && app.buttons["chat.share"].isHittable && app.buttons["chat.settings"].isHittable && app.buttons["chat.tools"].isHittable)
        XCTAssertGreaterThanOrEqual(chooser.frame.minY, app.buttons["chat.settings"].frame.maxY)
        capture(app, "Navigation — long responder beneath three islands")
        app.buttons["chat.conversations"].tap(); app.buttons["New conversation"].tap()
        XCTAssertEqual(chooser.value as? String, "My research and writing companion")
    }
    @MainActor func testEntitiesCanBeListedSelectedAndCreated() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test"]; app.launch()
        let chooser = app.buttons["Choose who answers"]
        XCTAssertTrue(chooser.waitForExistence(timeout: 10)); chooser.tap()
        XCTAssertTrue(app.buttons["Talk with Castor"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.buttons["Talk with Assistant"].exists)
        capture(app, "Entities")
        app.buttons["Talk with Castor"].tap()
        XCTAssertEqual(chooser.value as? String, "Castor")
        capture(app, "Entity conversation")
        chooser.tap(); app.buttons["entities.new"].tap()
        let name = app.textFields["entity.name"]
        XCTAssertTrue(name.waitForExistence(timeout: 5)); name.tap(); name.typeText("Atlas One")
        let create = app.buttons["entity.create"]
        let ready = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true AND hittable == true"), object: create)
        XCTAssertEqual(XCTWaiter.wait(for: [ready], timeout: 10), .completed)
        capture(app, "New entity")
        create.tap()
        let opened = XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == 'Atlas One'"), object: chooser)
        XCTAssertEqual(XCTWaiter.wait(for: [opened], timeout: 15), .completed)
        chooser.tap(); XCTAssertTrue(app.buttons["Talk with Atlas One"].waitForExistence(timeout: 5))
        capture(app, "Created entity")
    }
    @MainActor func testIPhoneToolDefaultsAreEditableWithoutUnlockingAndCarryToNewChats() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test", "--reset-tool-defaults"]; app.launch()
        XCTAssertTrue(app.buttons["chat.tools"].waitForExistence(timeout: 10))
        capture(app, "Always-visible tools beside responder")
        openSettings(app); app.buttons["settings.tools"].tap()
        searchTools(app, for: "read_file")
        let read = app.segmentedControls["tool.read_file"]
        XCTAssertTrue(read.waitForExistence(timeout: 5)); XCTAssertTrue(read.isEnabled)
        read.buttons["Approve"].tap()
        XCTAssertEqual(app.switches["tools.defaults"].value as? String, "0")
        capture(app, "Settings defaults for all sessions")
        app.buttons["tools.save"].tap()
        app.buttons["Done"].tap()
        app.buttons["New conversation"].tap()
        openTools(app)
        XCTAssertEqual(app.switches["tools.defaults"].value as? String, "1")
        searchTools(app, for: "read_file"); XCTAssertTrue(read.buttons["Approve"].isSelected)
        read.buttons["Off"].tap()
        capture(app, "Session override of Settings defaults")
        app.buttons["tools.save"].tap()
        openTools(app); searchTools(app, for: "read_file"); XCTAssertTrue(read.buttons["Off"].isSelected)
        app.buttons["tools.close"].tap()
        app.buttons["New conversation"].tap()
        openTools(app); searchTools(app, for: "read_file"); XCTAssertTrue(read.buttons["Approve"].isSelected)
    }
    @MainActor func testReloadRestoresAllAssistantRepliesWithoutSpeaking() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test", "--history-fixture", "--screen", "history"]; app.launch()
        XCTAssertTrue(app.staticTexts["Restored reply 3: your conversation is here."].waitForExistence(timeout: 10))
        capture(app, "Restored latest reply above floating composer")
        app.swipeDown(); app.swipeDown()
        XCTAssertTrue(app.staticTexts["Restored reply 1: your conversation is here."].exists)
        XCTAssertTrue(app.staticTexts["Restored reply 2: your conversation is here."].exists)
        XCTAssertFalse(app.buttons["Stop reading"].exists)
        capture(app, "Restored earlier assistant replies")
        app.terminate(); app.launch()
        XCTAssertTrue(app.staticTexts["Restored reply 3: your conversation is here."].waitForExistence(timeout: 10))
        app.swipeDown(); app.swipeDown()
        XCTAssertTrue(app.staticTexts["Restored reply 1: your conversation is here."].exists)
        XCTAssertTrue(app.staticTexts["Restored reply 2: your conversation is here."].exists)
    }
    @MainActor func testAutomationToolsCanOverrideSettingsAndPersistOnTheDefinition() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test", "--reset-tool-defaults", "--screen", "automations"]; app.launch()
        XCTAssertTrue(app.buttons["New automation"].waitForExistence(timeout: 10)); app.buttons["New automation"].tap()
        let task = app.textFields["automation.task"]; XCTAssertTrue(task.waitForExistence(timeout: 5)); task.tap(); task.typeText("Read my workspace every morning")
        app.staticTexts["What should it do?"].tap()
        app.swipeUp()
        app.buttons["automation.tools"].tap()
        searchTools(app, for: "read_file")
        app.segmentedControls["tool.read_file"].buttons["Approve"].tap()
        XCTAssertLessThan(app.segmentedControls["tool.read_file"].frame.maxY, app.keyboards.firstMatch.frame.minY)
        capture(app, "Automation tool override")
        app.buttons["tools.save"].tap()
        app.buttons["automation.create"].tap()
        XCTAssertTrue(app.buttons["Run now"].waitForExistence(timeout: 12))
        app.buttons["automation.tools"].tap(); searchTools(app, for: "read_file")
        XCTAssertTrue(app.segmentedControls["tool.read_file"].buttons["Approve"].isSelected)
        app.segmentedControls["tool.read_file"].buttons["Off"].tap(); app.buttons["tools.save"].tap()
        XCTAssertTrue(app.buttons["Run now"].waitForExistence(timeout: 8))
        app.buttons["automation.tools"].tap(); searchTools(app, for: "read_file")
        XCTAssertTrue(app.segmentedControls["tool.read_file"].buttons["Off"].isSelected)
        capture(app, "Persisted automation tool changes")
    }
    @MainActor func testAutomationInheritsSettingsInsteadOfCurrentSessionTools() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test", "--reset-tool-defaults"]; app.launch()
        openSettings(app); app.buttons["settings.tools"].tap(); searchTools(app, for: "read_file")
        app.segmentedControls["tool.read_file"].buttons["Approve"].tap(); app.buttons["tools.save"].tap(); app.buttons["Done"].tap()
        openTools(app); searchTools(app, for: "read_file")
        app.segmentedControls["tool.read_file"].buttons["Off"].tap(); app.buttons["tools.save"].tap()
        app.tabBars.buttons["Automations"].tap()
        app.buttons["New automation"].tap()
        let task = app.textFields["automation.task"]; XCTAssertTrue(task.waitForExistence(timeout: 5))
        task.tap(); task.typeText("Read a file on schedule"); app.staticTexts["What should it do?"].tap(); app.swipeUp()
        app.buttons["automation.tools"].tap(); searchTools(app, for: "read_file")
        XCTAssertEqual(app.switches["tools.defaults"].value as? String, "1")
        XCTAssertTrue(app.segmentedControls["tool.read_file"].buttons["Approve"].isSelected)
        app.buttons["tools.save"].tap(); app.buttons["automation.create"].tap()
        XCTAssertTrue(app.buttons["Run now"].waitForExistence(timeout: 12))
        app.buttons["automation.tools"].tap(); searchTools(app, for: "read_file")
        XCTAssertTrue(app.segmentedControls["tool.read_file"].buttons["Approve"].isSelected)
        capture(app, "Automation saved Settings grant independently of session override")
    }
    @MainActor func testToolsRemainVisibleAndEditableWhileAgentIsWorking() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test", "--activity=running", "--screen", "conversation"]; app.launch()
        XCTAssertTrue(app.buttons["activity.toggle"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.buttons["chat.tools"].isEnabled); openTools(app)
        searchTools(app, for: "read_file")
        XCTAssertTrue(app.segmentedControls["tool.read_file"].isEnabled)
        app.segmentedControls["tool.read_file"].buttons["Off"].tap()
        XCTAssertTrue(app.buttons["tools.save"].isEnabled); app.buttons["tools.save"].tap()
        XCTAssertTrue(app.buttons["voice.orb"].exists)
        XCTAssertTrue(app.buttons["chat.tools"].exists)
        capture(app, "Tools remain reachable during work")
    }
    @MainActor func testToolsSaveOnlyForTheCurrentConversation() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test", "--reset-tool-defaults"]; app.launch()
        openTools(app)
        let defaults = app.switches["tools.defaults"]
        XCTAssertTrue(defaults.waitForExistence(timeout: 10)); XCTAssertEqual(defaults.value as? String, "1")
        XCTAssertTrue(app.buttons["tools.category.files"].exists)
        XCTAssertFalse(app.segmentedControls["tool.read_file"].exists)
        capture(app, "Grouped conversation tools")
        defaults.coordinate(withNormalizedOffset: CGVector(dx: 0.88, dy: 0.5)).tap()
        searchTools(app, for: "read_file")
        let read = app.segmentedControls["tool.read_file"]
        XCTAssertTrue(read.waitForExistence(timeout: 5)); read.buttons["Off"].tap()
        searchTools(app, for: "fetch_url"); app.segmentedControls["tool.fetch_url"].buttons["Auto"].tap()
        searchTools(app, for: "execute_command"); app.segmentedControls["tool.execute_command"].buttons["Approve"].tap()
        XCTAssertTrue(app.buttons["tools.save"].isHittable)
        capture(app, "Saving filtered tool choices")
        app.buttons["tools.save"].tap()
        openTools(app)
        XCTAssertEqual(defaults.value as? String, "0")
        searchTools(app, for: "read_file"); XCTAssertTrue(read.buttons["Off"].isSelected)
        searchTools(app, for: "fetch_url"); XCTAssertTrue(app.segmentedControls["tool.fetch_url"].buttons["Auto"].isSelected)
        searchTools(app, for: "execute_command"); XCTAssertTrue(app.segmentedControls["tool.execute_command"].buttons["Approve"].isSelected)
        searchTools(app, for: "read_file")
        defaults.coordinate(withNormalizedOffset: CGVector(dx: 0.88, dy: 0.5)).tap()
        XCTAssertTrue(read.buttons["Auto"].isSelected)
        defaults.coordinate(withNormalizedOffset: CGVector(dx: 0.88, dy: 0.5)).tap()
        XCTAssertTrue(read.buttons["Off"].isSelected)
        app.buttons["tools.close"].tap()
        app.buttons["New conversation"].tap()
        openTools(app)
        XCTAssertTrue(defaults.waitForExistence(timeout: 5)); XCTAssertEqual(defaults.value as? String, "1")
        defaults.coordinate(withNormalizedOffset: CGVector(dx: 0.88, dy: 0.5)).tap()
        searchTools(app, for: "read_file"); XCTAssertTrue(read.buttons["Auto"].isSelected)
    }
    @MainActor func testToolCategoriesExpandSearchAndRespectGatewayDisabledTools() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test", "--reset-tool-defaults"]; app.launch(); openTools(app)
        let comms = app.buttons["tools.category.comms"]
        XCTAssertTrue(comms.waitForExistence(timeout: 10)); XCTAssertEqual(comms.value as? String, "Collapsed, Available")
        comms.tap(); XCTAssertTrue(app.segmentedControls["tool.send_email"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["Reaches outside"].exists)
        app.switches["tools.defaults"].coordinate(withNormalizedOffset: CGVector(dx: 0.88, dy: 0.5)).tap()
        XCTAssertTrue(app.segmentedControls["tool.send_email"].isEnabled)
        capture(app, "Expanded communication tools")
        comms.tap(); XCTAssertFalse(app.segmentedControls["tool.send_email"].exists)
        searchTools(app, for: "camera")
        let camera = app.segmentedControls["tool.capture_camera"]
        XCTAssertTrue(camera.waitForExistence(timeout: 5)); XCTAssertFalse(camera.isEnabled)
        XCTAssertTrue(camera.buttons["Off"].isSelected)
        XCTAssertTrue(app.staticTexts["The gateway camera is not enabled."].exists)
        capture(app, "Gateway-disabled tool")
        searchTools(app, for: "No such tool"); XCTAssertTrue(app.staticTexts["No tools match your search."].waitForExistence(timeout: 5))
    }
    @MainActor private func searchTools(_ app: XCUIApplication, for text: String) {
        let field = app.searchFields.firstMatch
        XCTAssertTrue(field.waitForExistence(timeout: 5)); field.tap()
        if field.buttons["Clear text"].exists { field.buttons["Clear text"].tap() }
        field.typeText(text)
    }
    @MainActor func testAnswerStatisticsAreOptionalAndCanBeHiddenAgain() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test"]; app.launch()
        openSettings(app)
        let toggle = app.switches["settings.messageStats"]
        XCTAssertTrue(toggle.waitForExistence(timeout: 5))
        if toggle.value as? String == "1" { toggle.coordinate(withNormalizedOffset: CGVector(dx: 0.88, dy: 0.5)).tap() }
        app.buttons["Done"].tap()
        app.buttons["Find a little focus"].firstMatch.tap(); app.buttons["Send message"].tap()
        XCTAssertTrue(app.buttons["Copy answer"].firstMatch.waitForExistence(timeout: 30))
        let keyboard = app.buttons["composer.keyboard"]
        let ready = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true AND hittable == true"), object: keyboard)
        XCTAssertEqual(XCTWaiter.wait(for: [ready], timeout: 30), .completed)
        let stats = app.descendants(matching: .any).matching(identifier: "message.stats").firstMatch
        XCTAssertFalse(stats.exists)
        openSettings(app)
        toggle.coordinate(withNormalizedOffset: CGVector(dx: 0.88, dy: 0.5)).tap()
        XCTAssertEqual(toggle.value as? String, "1")
        app.buttons["Done"].tap()
        XCTAssertTrue(stats.waitForExistence(timeout: 10))
        XCTAssertTrue(stats.label.contains("Input:")); XCTAssertTrue(stats.label.contains("Output:"))
        XCTAssertTrue(stats.label.contains("tool calls"))
        capture(app, "Answer statistics")
        openSettings(app); toggle.coordinate(withNormalizedOffset: CGVector(dx: 0.88, dy: 0.5)).tap(); app.buttons["Done"].tap()
        let hidden = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: stats)
        XCTAssertEqual(XCTWaiter.wait(for: [hidden], timeout: 5), .completed)
    }
    @MainActor func testGrowingAutomationBudgetValidatesAndInheritsByDefault() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test", "--screen", "automations"]; app.launch()
        XCTAssertTrue(app.buttons["New automation"].waitForExistence(timeout: 10)); app.buttons["New automation"].tap()
        let task = app.textFields["automation.task"]
        XCTAssertTrue(task.waitForExistence(timeout: 10)); task.tap(); task.typeText("My inherited history briefing")
        app.staticTexts["What should it do?"].tap()
        let growing = app.switches["automation.growing"]
        let budget = app.textFields["automation.historyBudget"]
        XCTAssertFalse(budget.exists)
        growing.coordinate(withNormalizedOffset: CGVector(dx: 0.88, dy: 0.5)).tap()
        XCTAssertTrue(budget.waitForExistence(timeout: 5))
        XCTAssertTrue((budget.value as? String ?? "").contains("50,000"))
        budget.tap(); budget.typeText("0"); app.staticTexts["History token budget"].tap()
        let create = app.buttons["automation.create"]
        XCTAssertFalse(create.isEnabled)
        budget.tap(); budget.typeText(XCUIKeyboardKey.delete.rawValue + "24000"); app.staticTexts["History token budget"].tap()
        XCTAssertTrue(create.isEnabled)
        capture(app, "Custom history budget")
        growing.coordinate(withNormalizedOffset: CGVector(dx: 0.88, dy: 0.5)).tap()
        XCTAssertFalse(budget.exists)
        growing.coordinate(withNormalizedOffset: CGVector(dx: 0.88, dy: 0.5)).tap()
        XCTAssertEqual(budget.value as? String, "24000")
        budget.tap(); budget.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: 5)); app.staticTexts["History token budget"].tap()
        XCTAssertTrue((budget.value as? String ?? "").contains("50,000"))
        XCTAssertTrue(create.isEnabled)
        capture(app, "Inherited history budget")
        for _ in 0..<4 { if create.isHittable { break }; app.swipeUp() }
        XCTAssertTrue(create.isHittable); create.tap()
        XCTAssertTrue(app.staticTexts["My inherited history briefing"].firstMatch.waitForExistence(timeout: 20))
    }
    @MainActor func testOnlyTheSpeakingAnswerShowsStop() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test"]; app.launch()
        for index in 1...2 {
            let keyboard = app.buttons["composer.keyboard"]
            XCTAssertTrue(keyboard.waitForExistence(timeout: 10))
            let ready = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true AND hittable == true"), object: keyboard)
            XCTAssertEqual(XCTWaiter.wait(for: [ready], timeout: 30), .completed)
            keyboard.tap(); app.textFields["composer.input"].typeText("Answer \(index)"); app.buttons["Send message"].tap()
            let done = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true"), object: keyboard)
            XCTAssertEqual(XCTWaiter.wait(for: [done], timeout: 30), .completed)
        }
        let readers = app.buttons.matching(identifier: "Read answer aloud")
        XCTAssertEqual(readers.count, 2)
        readers.element(boundBy: 1).tap()
        XCTAssertTrue(app.buttons["Stop reading"].firstMatch.waitForExistence(timeout: 5))
        XCTAssertEqual(app.buttons.matching(identifier: "Stop reading").count, 1)
        XCTAssertEqual(app.buttons.matching(identifier: "Read answer aloud").count, 1)
        capture(app, "Isolated answer playback")
        app.buttons["Stop reading"].tap()
        XCTAssertEqual(app.buttons.matching(identifier: "Read answer aloud").count, 2)
    }
    @MainActor func testSettingsOpensGlobalToolDefaults() throws {
        let app = XCUIApplication(); app.launchArguments = ["--demo", "--ui-test", "--reset-tool-defaults"]; app.launch()
        openSettings(app)
        app.buttons["settings.tools"].tap()
        XCTAssertTrue(app.switches["tools.defaults"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["Defaults for sessions and automations"].exists)
        app.buttons["tools.close"].tap()
        XCTAssertTrue(app.switches["settings.messageStats"].waitForExistence(timeout: 5))
    }
    @MainActor private func openTools(_ app: XCUIApplication) {
        XCTAssertTrue(app.buttons["chat.tools"].waitForExistence(timeout: 10)); app.buttons["chat.tools"].tap()
    }
    @MainActor private func openSettings(_ app: XCUIApplication) {
        XCTAssertTrue(app.buttons["Settings"].waitForExistence(timeout: 10)); app.buttons["Settings"].tap()
    }
    @MainActor private func capture(_ app: XCUIApplication, _ name: String) {
        Thread.sleep(forTimeInterval: 0.7) // Capture settled native navigation, not an intermediate animation frame.
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
    }
}
