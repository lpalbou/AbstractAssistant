import Foundation
import Testing
import AbstractGatewayClient
@testable import AssistantKit

@Test func actualGatewayOccurrenceFailureSurvivesDecodeAndRoundTrip() throws {
    let data = Data(#"{"status":"failed","answer":"","run_id":"failed-model-run","index":4,"attempts":3,"fired_at":"2026-10-19T11:38:02.719423+00:00","finished_at":"2026-10-19T11:39:33.137919+00:00","failure":{"reason_code":"occurrence_failed","message":"OpenAI-compatible server API error (401): Missing or invalid AIRelays bearer token.","attempts":3},"trigger":{"summary":"manual: run now"},"user_turn":"Check my inbox"}"#.utf8)
    let row = try JSONDecoder().decode(LastOccurrence.self, from: data)
    #expect(row.attemptCount == 3 && row.displayAnswer == nil)
    #expect(row.failure?.reasonCode == "occurrence_failed")
    #expect(row.triggerSummary == "manual: run now" && row.userTurn == "Check my inbox")
    #expect(ISO8601.date(row.firedAt!) != nil)
    let restored = try JSONDecoder().decode(LastOccurrence.self, from: JSONEncoder().encode(row))
    #expect(restored == row)
    let explanation = AutomationRunExplanation(occurrence: row)
    #expect(explanation.message.contains("Your iPhone is connected"))
    #expect(explanation.nextStep?.contains("gateway administrator") == true)
    #expect(explanation.technicalDetail == row.failure?.message)
}

@Test func runFailuresUseRootOrChildEvidenceWithoutInventingACause() {
    let failed = LastOccurrence(status: "failed", excerpt: "", runId: "x")
    let unknown = AutomationRunExplanation(occurrence: failed)
    #expect(unknown.message.contains("without an explanation"))
    #expect(unknown.technicalDetail == nil)
    #expect(AutomationRunExplanation(occurrence: failed, runError: "Timed out").message.contains("did not respond"))
    #expect(AutomationRunExplanation(occurrence: failed, stepError: "429 rate limit").message.contains("limited"))
    // A generic upstream failure code must not cause advice to change email permissions.
    #expect(AutomationRunExplanation(occurrence: failed, runError: "Unexpected workflow condition").message == "Unexpected workflow condition")
    #expect(AutomationRunExplanation(occurrence: failed, runError: "401 Unauthorized").message == "401 Unauthorized")
}

@Test func occurrenceStatesAndEmptyAnswersRemainDistinct() throws {
    let old = try JSONDecoder().decode(LastOccurrence.self, from: Data(#"{"status":"completed","excerpt":"  "}"#.utf8))
    #expect(old.displayAnswer == nil && old.attemptCount == nil)
    #expect(AutomationRunExplanation(occurrence: old).message.contains("without a text answer"))
    for status in ["waiting", "running", "admitted", "backoff"] {
        let row = LastOccurrence(status: status, excerpt: nil)
        #expect(row.isActive)
        #expect(!AutomationRunExplanation(occurrence: row).message.isEmpty)
    }
    let waiting = AutomationRunExplanation(occurrence: .init(status: "waiting", excerpt: nil))
    #expect(waiting.title == "Needs you" && waiting.nextStep?.contains("Inbox") == true)
}

@Test func updateDestinationsRespectDistributionAndNeverClaimAReleaseExists() {
    let beta = AppUpdateInfo(version: "0.6.22", build: "120.1", channel: .testFlight)
    #expect(beta.installedVersion == "0.6.22 (120.1)" && beta.channelTitle == "TestFlight")
    #expect(beta.destination.scheme == "itms-beta")
    let store = AppUpdateInfo(version: "1.0", build: "300", channel: .appStore, storeID: 123456789)
    #expect(store.destination.absoluteString == "https://apps.apple.com/app/id123456789")
    #expect(AppUpdateInfo(version: nil, build: "").installedVersion == "Unknown (Unknown)")
    #expect(AppUpdateInfo(version: "1", build: "2", channel: .development).destination.path.hasSuffix("BUILD.md"))
    #expect(AppUpdateInfo(version: "1", build: "2", channel: .appStore).destination == AppUpdateInfo.appStoreHelp)
    #expect(AppUpdateInfo(version: "1", build: "2").channelTitle == "Not verified")
}

@Test func retryAttemptsRemainOneOccurrenceAcrossRunIDs() {
    let first = LastOccurrence(status: "backoff", excerpt: nil, runId: "attempt-1", index: 4)
    let next = LastOccurrence(status: "running", excerpt: nil, runId: "attempt-2", index: 4)
    let later = LastOccurrence(status: "failed", excerpt: nil, runId: "attempt-3", index: 5)
    #expect(first.stableID != next.stableID)
    #expect(first.occurrenceKey == next.occurrenceKey)
    #expect(first.occurrenceKey != later.occurrenceKey)
}
