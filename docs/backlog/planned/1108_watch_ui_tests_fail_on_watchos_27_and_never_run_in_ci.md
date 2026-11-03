# 1108: Watch UI tests: 20 fail on watchOS 27.0 and no CI job runs them

**Status**: planned (next round, not the 2026-11-03 release wave). Filed 2026-11-03 by the release wave (W1),
coordinator's decision.
**Found by**: the 2026-11-03 TestFlight work on the iPhone's full UI suite (PR #50). The audit noted that the watch's
UI tests never run in CI.

## What is true today

- `AbstractAssistantWatchUITests` (`watch/apple/UITests`, own scheme in `phone/iphone/project.yml`) is not run by any
  workflow. `watch.yml` and `iphone.yml` run the watch package tests and build the watch app only.
- One local run on 2026-11-03: watchOS 27.0, Apple Watch Series 11 (46 mm) simulator, Xcode 27.1, main 1ec64e2 +
  PR #50. 117 tests: 86 passed, 20 failed, 11 skipped.
  - The 11 skipped are the live-gateway tests (`Live*UITests`) plus `NewAutomationUITests.testWorkflowsFromTheGateway`
    and `VoiceSettingsUITests.testSpinnerWhileTheSampleIsMade`. They skip without a gateway.
- None of the 20 is classified yet (test wrong or product wrong). They are mostly orb, voice and navigation
  interactions. Two rewind tests measure a playhead that moved forward (1.6 s -> 3.9 s), so a hold on the orb did not
  take the voice back. That would be a product defect if it holds on a device.

## The 20 failures (first assertion of each)

| Suite | Test | First failing assertion |
|---|---|---|
| AskShareUITests | `testShareAndRewindOnTheOrb()` | XCTAssertLessThan failed: ("3.9") is not less than ("1.1") - holding did not take the voice back (1.6 s -> 3.9 s) |
| AskStatusUITests | `testANoteOnListeningEndsWhenTheOrbSpeaks()` | XCTAssertTrue failed - the conversation's last answer is not shown |
| BrowserNavigationUITests | `testAReopenedConversationSwipesToItsStats()` | XCTAssertTrue failed - round 1: the orb did not open |
| BrowserNavigationUITests | `testBackAndForwardLikeABrowser()` | XCTAssertTrue failed |
| FilePreviewUITests | `testSwipingThroughAConversationsFiles()` | XCTAssertTrue failed |
| HomeOrbNewConversationUITests | `testTheHomeOrbOpensAnEmptyConversation()` | XCTAssertTrue failed |
| OrbHistoryUITests | `testLastInFullEarlierCardsShowOlder()` | XCTAssertTrue failed - the last message is not shown in full |
| OrbPageLayoutUITests | `testTheOrbStaysWhereAFreshPagePutsIt()` | XCTAssertTrue failed |
| RewindUITests | `testVoiceButtonPausesAndRewinds()` | XCTAssertLessThan failed: ("3.8") is not less than ("1.1") - holding did not rewind (1.6 s -> 4.1 s) |
| ScheduleChoicesUITests | `testTheChoicesRunFromThirtySecondsToAWeek()` | XCTAssertTrue failed |
| SendNowUITests | `testSendEndsTheListeningNow()` | XCTAssertTrue failed - Send did not end the listening at once |
| SessionPageUITests | `testLastFiveShowOlderAndReadAloud()` | XCTAssertTrue failed - no Read aloud for the latest answer |
| SessionSearchUITests | `testSearchFindsAndOpensAConversation()` | XCTAssertTrue failed |
| StopVoiceUITests | `testHoldingTheOrbTogglesReadingAndListening()` | XCTAssertTrue failed |
| StopVoiceUITests | `testStopButtonEndsTheVoice()` | XCTAssertTrue failed |
| VoiceButtonUITests | `testATapOnTheOrbListens()` | XCTAssertTrue failed - a tap on the orb did not listen |
| VoiceButtonUITests | `testHoldOnAFinishedVoicePlaysItFromTheStart()` | XCTAssertEqual failed: ("Read aloud") is not equal to ("Pause") - a hold on a finished voice did not play it |
| VoiceButtonUITests | `testNearMissesNeverStartListening()` | XCTAssertTrue failed - voice button hidden once scrolled |
| VoiceGoesOnUITests | `testAnotherPagesPlayerLeavingDoesNotStopTheVoice()` | XCTAssertTrue failed |
| VoiceSettingsUITests | `testClonePreviewFailureExplainsHowToRetry()` | XCTAssertTrue failed - Supertonic M2, English · male, Making the sample |

## Plan

1. Reproduce each failure on the same simulator. Classify it from the assertion, the UI hierarchy and the recording,
   as test wrong or product wrong, and fix that side. No skips, no weaker assertions, no sleeps as logic.
2. Add a CI job that runs `AbstractAssistantWatchUITests` (non-live) on a watchOS simulator chosen the way `iphone.yml`
   chooses the iPhone, so a red watch UI test reaches a PR.

## Acceptance

- The suite is green locally on watchOS 27.0 (live tests skipped without a gateway), each fix stated with its evidence.
- A CI job runs it on every PR that touches `watch/apple` and is green.
