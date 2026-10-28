# 1072: Apple Watch: Run on an automation's details answers the tap

**Status**: completed in the Apple apps 0.16.1 (build 40) (branch `fix/watch-run-feedback`); shipped to testers
by the operator's TestFlight upload (`watch/apple/scripts/testflight.sh`).
**Source**: release-closing QA 2026-10-28, item (m).
**Scope**: the watch app (`watch/apple`); the shared client package only for a test delay (`MockGatewayClient`
`runDelay`); the shared version in `phone/iphone/project.yml`.

## Problem

On an automation's details (title, run count, schedule, "Builds on its earlier runs", Edit, Run), a tap on Run
gave no feedback, then the app showed the automation's orb page at rest, as if nothing had happened.

**Cause.** `AutomationInfoView.runNow()` only disabled the button (no visual change) while the command
`POST /api/gateway/automations/{id}/commands {type: automation.run_now}` was sent, then went back to the orb page
without the run. That page looked for the run again (`AutomationFeed.liveRun`: the automation's row every 3 s),
so the orb stayed at rest for several round trips; a run that ended before its first look (a short task on a fast
model, under a second on LM Studio `qwen/qwen3.5-9b`) was never shown there for 45 s. No navigation reset was
involved: the pop was the intended `goBack()`, just with nothing to show.

## Fix

- The tap: a click haptic, a spinner in the Run button (same width as its icon), a "Starting… 0:01" line
  (`automation.starting`); once the gateway accepts the command, the start haptic and "Running… 0:03".
- The details stay until the gateway has started the run (its row's `current_occurrence.run_id`, or a newer
  `last_occurrence` fired after the tap: a run already over), read every second for at most 20 s, then go back
  (only if the details are still in front) and hand the run to the orb page (`AppModel.startedRuns`).
- The orb page follows a handed run at once (`followAutomationRun`: the existing `ActivityPanel` steps, timed
  from the tap through `RunActivity.start(since:)`, then the answer, spoken), and fills in the run's message after.
- A refused Run says why, with the failure haptic; 409 `automation_busy` keeps "It is already running."

## Evidence

- Before/after sequences with simulator screenshots against a scratch gateway (LM Studio `qwen/qwen3.5-9b`,
  a 1.5 s delay per request as over a watch's radio): `untracked/release-closing/watch/sequence.md` in the
  workspace. Before: no feedback 1.5 s, orb at rest 3.2 s, followed 4.6 s after the tap (a 1 s run: never).
  After: "Starting…" within 0.1 s, the details until the run exists, the orb page following it on arrival.
- `RunFeedbackUITests.testRunShowsItIsStartingThenFollowsTheRun` (sample data, `--slow-run`: Run accepted after
  4 s): red on the previous build (no starting line), green now; in `scripts/test-watch.sh light`.
- `LiveRunFeedbackUITests` (LIVE_GW_URL, LIVE_GW_TOKEN; runs the first automation once): prints the sequence.
