# 1041 — iPhone CI and human-gated Apple delivery

## Scope and release boundary

Implementation: `ab58c47`; integrated with the independent 0.14.3 release in `7af42ee`.
The new workflow affects iPhone only. No Watch workflow, signing keys, deployment reviewers,
Framework packages, gateway configuration or installed phone app were changed.

PR/main checks have no Apple credentials. A manual main-only upload request requires the full
native suite and the existing protected `app-store` review before its job receives keys. It
verifies the same archived source/version/build/digest and exports with normal App Store Connect
settings. No automated App Review submission, tester-group distribution or public release exists.
ADR0002 and the linked distribution guide document same-build TestFlight → manual Store promotion.

## Approval audit

`approval-environment.json` and `deployment-branches.json` are read-only GitHub configuration
receipts. Existing `app-store` requires reviewer `lpalbou` and allows branch `main`. The environment
already has the three named ASC secrets; no secret values were read, copied or changed. The
single maintainer may approve their own initiated upload; GitHub still requires an explicit human
review action. No upload request or environment approval was made during these checks.

## Validation

- `release-contract-tests.txt`: 10/10 Python3.12+ tests pass. Includes wrong source/bundle/version,
  modified bytes, malicious tar paths, test plugins, critical-only native coverage rejection,
  Apple numeric version limits and private-key cleanup on successful/failed mocked export.
- Pinned actionlint1.7.12 validates the workflow; Bash syntax checks pass. Additional runner-label
  metadata permits GitHub’s documented hosted `xcode-27` label in that actionlint version.
- XcodeGen project generation passes. A local unsigned archive attempt yielded to concurrent
  Watch work under the local build guard; GitHub is used for complete native/archive validation.
- CI candidate artifacts and native results are retained by Actions for 30 and 14 days.
  The first run and candidate inspection are recorded below; the first full-suite result is recorded below.

## Reproduce

```sh
python3 -m unittest discover -s phone/iphone/scripts/tests -v
bash -n phone/iphone/scripts/select-xcode.sh phone/iphone/scripts/upload-candidate.sh
actionlint -shellcheck= .github/workflows/iphone.yml
gh workflow run iphone.yml --ref main -f upload=false -f full_ui_suite=true
```

A first actual Apple upload still needs an iOS app record for
`ai.abstractframework.assistant.iphone`, eligible Apple team credentials and the protected human
approval. Mocked export tests do not establish that signing, Apple processing or public-store
submission have succeeded. Store metadata, review and manual release are operator actions.

## Critical-suite CI receipt

[Push run 39179097643](https://github.com/lpalbou/AbstractAssistant/actions/runs/39179097643)
succeeded on source `7af42eef17d25d30894c410b28ca37c2c7b35bf6`. Release contracts, package
and native checks, unsigned archive generation and artifact retention all succeeded; Apple
upload was **skipped**. Machine-readable receipts are `ci-critical-run.json` and
`ci-critical-artifacts.json`.

`ci-critical-package-summary.txt`: 170 + 76 = **246 package tests passed**.
`ci-critical-native-summary.json`: **35 passed, 0 failed, 0 skipped** on iPhone17Pro/iOS27.0;
31 hosted tests and four critical UI journeys. The report retains eight existing audio-session
main-thread runtime warnings. Xcode also printed Swift optional-promotion warnings and a
non-fatal compiler diagnostic with exit code0; the native test report, archive and job all succeeded.

Downloaded candidate **0.6.21 (101.1)** has the expected source, iPhone bundle ID, device platform,
ARM64 executable, no test plugins and a matching SHA256. It is unsigned, as expected in the
credential-free job. The manifest and inspection are in `ci-critical-candidate.json` and
`ci-critical-inspection.json`. The real candidate is rejected by the upload verifier because its
native coverage is `critical` instead of `full`; its manifest was not changed for this check.

## First full-suite result and refinement

[Full run 39179422246](https://github.com/lpalbou/AbstractAssistant/actions/runs/39179422246)
passed 74/79 native tests, with five UI failures. Candidate creation and Apple upload were blocked.
`ci-full-first-native-summary.json` and `ci-full-first-run.json` preserve this result.
Failure screenshots and accessibility trees were inspected. Two tests still attempted New
conversation directly from the main screen; the supported action lives in Conversations. The
share assertion raced native sheet dismissal. Web result links are exposed as Link, not Button.
Voice preview is a short synthetic recording that had ended during screenshot capture before
the test tapped Stop. Update these existing journeys without removing tests: use Conversations,
wait for share dismissal, query Link and stop samples before capturing, then verify stop cleanup.
A complete native rerun is required before closing this item.

Focused local rerun on iOS26.5: four fixes pass; the web-link assertion identifies a native
classification difference (Button on26.5, Link on27.0). Preserve both label and actionable-type
requirements with a Button-or-Link predicate. `local-focused-first-native-summary.json` records
the first focused result. A subsequent local build yielded to Watch priority (exit75). The
complete hosted native suite is rerun after the compatibility adjustment.

A later standard CI run (39182836287) passed34/35 native tests; the actual orb-return snapshot
was unchanged at the test's fixed140ms sleep. Replace that fixed-delay assertion with bounded
observation of a changed rendered frame, retaining the threshold and adding a check that the
frame differs from the final sphere before mid-flight reversal. All rendering and reversal
checks remain required. `ci-critical-second-native-summary.json` preserves the failure.

## Final standard CI receipt

[Run39184707211](https://github.com/lpalbou/AbstractAssistant/actions/runs/39184707211)
succeeded on514d041 after the rendering-test refinement: release contracts,246 package tests,
35 native tests, unsigned Release archive and artifact retention. Apple upload was skipped.
`ci-final-critical-*.json` preserve the run, artifact metadata, native summary and candidate.
The candidate checksum matches its archive. The full UI run uses80e6f1f; the only subsequent
change is the native orb test, exercised here. Application and release-workflow sources match
between these validation commits. `orb-stop.png` and `orb-restored-sphere.png` were visually
inspected from the earlier fixed-delay failure; both endpoints render correctly.

Full run39182853154 passed78/79, resolving all five earlier UI failures. The remaining voice
fixture stayed Listening instead of auto-sending after silence. Failure hierarchy confirms
the controller remained recording. VoiceTurn intentionally resets silence on unobserved
sample gaps over250ms; main-thread CI stalls made the wall-clock synthetic recorder
non-deterministic. Give the DEBUG-only, --demo/--ui-test/--voice-fixture recorder an observed-
sample clock, so fixture frames and controller timestamps advance together. Production
recorder, strict silence policy and real monotonic clock remain unchanged. Allow30s for the
UI's transcription/answer observation under a throttled runner. Native policy tests continue
to verify real sampling gaps are never counted as silence. Rerun full native suite.
