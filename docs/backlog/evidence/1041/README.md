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
`ci-critical-native-summary.json`: **35 passed, 0 failed, 0 skipped** on iPhone17Pro/iOS 27.0;
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

Focused local rerun on iOS 26.5: four fixes pass; the web-link assertion identifies a native
classification difference (Button on 26.5, Link on 27.0). Preserve both label and actionable-type
requirements with a Button-or-Link predicate. `local-focused-first-native-summary.json` records
the first focused result. A subsequent local build yielded to Watch priority (exit75). The
complete hosted native suite is rerun after the compatibility adjustment.

A later standard CI run (39182836287) passed 34/35 native tests; the actual orb-return snapshot
was unchanged at the test's fixed 140 ms sleep. Replace that fixed-delay assertion with bounded
observation of a changed rendered frame, retaining the threshold and adding a check that the
frame differs from the final sphere before mid-flight reversal. All rendering and reversal
checks remain required. `ci-critical-second-native-summary.json` preserves the failure.

## Rendering follow-up standard CI receipt

[Run 39184707211](https://github.com/lpalbou/AbstractAssistant/actions/runs/39184707211)
succeeded on 514d041 after the rendering-test refinement: release contracts,246 package tests,
35 native tests, unsigned Release archive and artifact retention. Apple upload was skipped.
`ci-final-critical-*.json` preserve the run, artifact metadata, native summary and candidate.
The candidate checksum matches its archive. The full UI run uses 80e6f1f; the only subsequent
change is the native orb test, exercised here. Application and release-workflow sources match
between these validation commits. `orb-stop.png` and `orb-restored-sphere.png` were visually
inspected from the earlier fixed-delay failure; both endpoints render correctly.

Full run 39182853154 passed 78/79, resolving all five earlier UI failures. The remaining voice
fixture stayed Listening instead of auto-sending after silence. Failure hierarchy confirms
the controller remained recording. VoiceTurn intentionally resets silence on unobserved
sample gaps over 250 ms; main-thread CI stalls made the wall-clock synthetic recorder
non-deterministic. Give the DEBUG-only, --demo/--ui-test/--voice-fixture recorder an observed-
sample clock, so fixture frames and controller timestamps advance together. Production
recorder, strict silence policy and real monotonic clock remain unchanged. Allow 30 s for the
UI's transcription/answer observation under a throttled runner. Native policy tests continue
to verify real sampling gaps are never counted as silence. Rerun full native suite.

Final focused iOS 26.5 checks passed 3/3: observed orb return/reversal, sample-clock-based voice
silence/cancel/automatic send with the typed draft preserved, and the Button-or-Link web
source assertion. `local-final-focused-native-summary.json` records the result. No runtime
warnings. The guarded local run completed without interrupting Watch. Bundle:
phone/iphone/build/UITests-1792374369552111000.xcresult (ignored). Full CI on the same b555e63
revision is required before closure.

## Verified completion — 2026-10-19

Both lanes succeeded on **b555e638b128b93c1392a0757fc04a891b291a27**:

- [Standard run 39186943700](https://github.com/lpalbou/AbstractAssistant/actions/runs/39186943700):
  release contracts, 246 package tests, 35 native tests and unsigned candidate **0.6.21 (108.1)**.
- [Full run 39186968522](https://github.com/lpalbou/AbstractAssistant/actions/runs/39186968522):
  release contracts, 246 package tests, **79 native tests passed, 0 failed, 0 skipped**
  (31 hosted tests + all 48 UI journeys), and unsigned candidate **0.6.21 (109.1)**.
- Apple upload is **skipped** in both successful runs. Manual full-suite testing did not request
  deployment approval or expose Apple credentials. The existing human/main-only gate was audited.

`ci-verified-*.json` and `ci-verified-package-summary.txt` retain these receipts. The actual full
candidate was downloaded and passed the real `release.py verify` path, including its source,
iPhone bundle ID, version/build, full native coverage, archive checksum, safe extraction, device
executable and absence of test plugins. Its SHA256 is
`7da53b4f7c5a2c1f7bbe56072ea22a83c4ed922d3994a832de34a7ec44a83190`.
The archive is retained by Actions for 30 days; complete native results for 14 days.

The full native report retains 39 existing audio-session main-thread runtime warnings. Those
are diagnostics rather than failed tests and remain visible in the receipt. Production voice
policy and recording clocks were not relaxed: the clock adjustment applies only to the synthetic
DEBUG UI fixture. There is no actual Apple signing, processing or public Store release claim.

`coredoc-committed-check.json` verifies the committed documentation and LLM aggregate are fresh.
Concurrent Watch documentation edits make the shared working-tree aggregate temporarily stale;
those unrelated changes were left to their owner. The final changes affect backlog evidence only,
which is outside the public LLM aggregation inputs.

First real upload remains an operator action: create the iOS App Store Connect app record,
request upload on main, inspect the successful full-suite candidate and approve the protected
app-store deployment. Apple signing/upload and processing have not been exercised with real
credentials. Store metadata, App Review submission and manual public release follow beta testing.

## First real release request

[first-release-request.json](first-release-request.json) records manual upload run 39190954901,
its source and flags, local credential-format checks and the unchanged protected environment.
No private key material or authentication tokens are recorded. Apple signing and upload are
pending the first real run and its human approval gate.

[first-release-outcome.json](first-release-outcome.json) closes the first attempt: successful
CI/archive/verification, operator approval, then Apple export exit70 for a missing app record.
No iPhone upload succeeded. Operator wants the existing Watch listing to contain both clients;
1042 tracks the required combined packaging and shared upload ownership.
