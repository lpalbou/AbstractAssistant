# 1041 — iPhone CI and human-gated Apple delivery

> Package: abstractassistant
> Type: task
> Created: 2026-10-19
> Status: Completed
> Completed: 2026-10-19
> Priority: P1
> Labels: iphone, ci, release, approval

## Goal and current code reality

Add iPhone CI/CD comparable to Watch, with a real human approval boundary before App Store
Connect receives an upload. Separate credential-free CI testing, TestFlight beta delivery and
public App Store release. The iPhone has independent project.yml/bundle ID and local guarded
build/tests, but no workflow/archive distribution setup. watch.yml uses the xcode-27 hosted
runner and a protected app-store environment with ASC_KEY_ID/ASC_ISSUER_ID/ASC_KEY_P8.
Read-only GitHub audit confirms required reviewer lpalbou and main-only deployment policies.
Existing Apple secrets cannot be read/copied; reuse the existing protected upload environment.

## Scope and acceptance

- [x] PR/main/manual CI: package tests, native hosted tests and critical UI journeys, unsigned
      Release archive, pinned source/build provenance and retained test/candidate artifacts.
- [x] Explicit manual upload choice only on main; successful full native suite required;
      existing human-reviewed app-store environment gates all Apple credentials and upload.
- [x] Upload exactly the checked candidate, validate identity/version/source/archive integrity,
      no untrusted PR secret access, no automatic upload on push, scoped key cleanup.
- [x] TestFlight-ready normal App Store Connect upload, preserving eligibility for promotion;
      no automatic App Review submission or public release; document manual same-build promotion.
- [x] Verify workflow/scripts, negative provenance/version checks, local candidate archive and
      package/native checks as appropriate; push configuration and inspect actual CI outcome.

## Boundaries and decisions

No Watch/framework/server edits, app/gateway selection changes, separate staging bundle,
secret extraction, paid provider calls, actual Apple upload/submission/release or new app metadata
without the protected approval. Reuse released Xcode27 runner selection. ADR0002 records stage
boundaries and same-build promotion. User was offered separate staging app as an optional choice;
proceeding with the recommended TestFlight same-build path pending any steering.

## Validation

Use standard-library tests for artifact/version/integrity validation and script failures,
actionlint/shell checks where available, project generation and unsigned archive inspection,
package tests and credential-free native CI. Document first-time App Store Connect app record
requirements and human actions separately from completed upload claims. Coredoc updates and
regenerated LLM indexes in the same change. No live deployment bypass during verification.

## Initial CI findings — 2026-10-19

Push run 39179097643 passed 246 package and 35 native checks and archived a verified unsigned
candidate; upload skipped. Full-suite run 39179422246 passed 74/79 native tests, then correctly
blocked candidate creation/upload on five UI failures. Failure reports and screenshot/hierarchy
inspection identify stale direct New conversation navigation (two tests), an immediate toolbar
assertion before share dismissal settled, a button query for a native Link, and a voice preview
stop tapped after screenshot capture allowed the short synthetic sample to finish. Update the
existing journeys to navigate via Conversations, wait for dismissal, query Link and stop the
sample before capturing. Keep all 48 UI journeys and rerun; no production behavior changes.

Focused iOS 26.5 rerun passed four affected journeys and exposed an OS-specific accessibility
classification: the same SwiftUI search-result Link appears as Button on 26.5 and Link on 27.0.
Retain the link label and actionable-type assertions while accepting either native type. A
second local attempt yielded to a newly active Watch build (exit75), without interrupting Watch.

A later standard CI run (39182836287) passed 34/35 native tests; the actual orb-return snapshot
was unchanged at the test's fixed 140 ms sleep. Replace that fixed-delay assertion with bounded
observation of a changed rendered frame, retaining the threshold and adding a check that the
frame differs from the final sphere before mid-flight reversal. All rendering and reversal
checks remain required. `ci-critical-second-native-summary.json` preserves the failure.

Full run 39182853154 passed 78/79, resolving all five earlier UI failures. The remaining voice
fixture stayed Listening instead of auto-sending after silence. Failure hierarchy confirms
the controller remained recording. VoiceTurn intentionally resets silence on unobserved
sample gaps over 250 ms; main-thread CI stalls made the wall-clock synthetic recorder
non-deterministic. Give the DEBUG-only, --demo/--ui-test/--voice-fixture recorder an observed-
sample clock, so fixture frames and controller timestamps advance together. Production
recorder, strict silence policy and real monotonic clock remain unchanged. Allow 30 s for the
UI's transcription/answer observation under a throttled runner. Native policy tests continue
to verify real sampling gaps are never counted as silence. Rerun full native suite.

## Completion report

- **Completed:** 2026-10-19; created 2026-10-19.
- **Original path:** docs/backlog/planned/1041_iphone_ci_and_gated_apple_delivery.md.
- **Final path:** docs/backlog/completed/1041_iphone_ci_and_gated_apple_delivery.md.
- **Outcome:** iPhone CI/CD implemented and pushed. PR/main/manual checks run without Apple keys;
  upload requires a main-only explicit manual request, full native tests and the existing human
  app-store review. The uploader verifies and signs the checked archive without rebuilding.
  TestFlight testing and same-build manual Store review/release are documented stages.
- **Implementation:** ab58c47 (workflow, release helpers/tests, ADR0002, distribution guide,
  public docs/LLM indexes), integrated with release 0.14.3 in 7af42ee. f102970/80e6f1f update existing
  native UI journeys; 514d041 observes actual rendered animation frames; b555e63 gives the DEBUG
  microphone fixture an observed-sample clock. Production recording/silence policy is unchanged.
- **Validation:** automatic run 39186943700 and manual full run 39186968522 both succeed on b555e63.
  Ten release contract/failure tests, actionlint and Bash checks pass. Both lanes pass 246 package
  tests; standard native 35/35, full native 79/79 including 48 UI journeys. Local focused 3/3 pass
  on iOS 26.5. The actual full archive 0.6.21 (109.1) passes the real source/bundle/version/digest/
  safe-extraction/test-scope verifier. Apple upload is skipped in both successful lanes.
- **Deviation:** local archive work yielded to Watch priority; actual hosted archives provide
  complete device archive validation. Focused local attempts also yielded when Watch compiled.
- **Docs/policy:** [ADR0002](../../adr/0002_iphone_release_stages.md), distribution guide, build/
  architecture/README links and regenerated public LLM indexes. Committed coredoc freshness passes.
- **Evidence:** [receipts, diagnosis and reproduction](../evidence/1041/README.md), including
  earlier failures and their refinements, successful run/native summaries and full archive manifest.
- **Limits and triage:** real Apple signing/upload still requires an iOS app record and protected
  human approval; beta groups, Store metadata, review and public release remain operator actions.
  Existing audio-session runtime diagnostics are retained for app-performance investigation;
  they do not fail CI. Separate staging bundle/server accounts are not created by this item.
  These are documented distribution/setup boundaries, not unfinished CI implementation.

## Post-completion first release request — 2026-10-19

The operator requested a real iPhone release and supplied two local ASC key files and Apple
certificate files. Triggered main workflow [39190954901](https://github.com/lpalbou/AbstractAssistant/actions/runs/39190954901)
with upload=true and full_ui_suite=true on 73cd2fe. Existing app-store secrets and reviewer gate
remain unchanged. Both local key files parse; both certificates match the configured team.
A read-only individual-key authentication probe returns 401, which does not establish whether
these files are valid team keys (the issuer ID is not present locally). Existing protected secrets
previously passed Apple's API and Watch upload in run 39100823978. No credentials are committed.

CI execution is pending. The iPhone app record and actual signing/upload are unverified until
Apple can be queried behind the protected job. Public App Store review/release remains manual
under ADR0002. [Release-request receipt](../evidence/1041/first-release-request.json).
