# 1042 — Unified Apple delivery evidence

The intended Store product is the existing AbstractAssistant listing: iPhone
`ai.abstractframework.assistant` embedding independent Watch
`ai.abstractframework.assistant.watch`. Developer identities/sources are retained.

## Reproduction and implementation

- [First implementation checks](implementation-checks.json): 14 contract tests, both workflows
  pass actionlint, reproduced duplicate SwiftPM products and resolved composition graph.
- [Initial combined request](combined-release-request.json): run 39199477853 on 5614b25;
  [compiler failure](companion-import-failure.txt) exposed a framework-product/import-name mismatch.
- [Resolved framework settings](static-framework-settings.json): Xcode confirms product/module
  AbstractGatewayClient, static binary, Skip Install and Watch deployment target26.
- [Actual generated copy phase](watch-embedding-phase.json): Watch app copied to the standard
  products directory / $(CONTENTS_FOLDER_PATH)/Watch, not the root Resources phase.
- Run39199862597 passed all73 Watch package tests and the companion simulator build. It was
  cancelled before the full suite after generated-project inspection found the copy destination
  needed to be explicit.

## Combined archive and native validation

[Combined archive step](combined-archive-step.json) records run 39200275528 oncd6bbf3. Both package
suites (Watch73, iPhone246), Watch companion compilation and a real generic iOS Release archive
pass. The archive inspector verifies both executables, platform/bundle identity, matching
versions and independent-companion configuration. Full native testing is pending in this receipt.

[Critical candidate](critical-candidate.json) records the downloaded automatic build 118.1, digest
verification and actual app metadata/executable sizes. [Native result summary](critical-native-summary.json)
confirms 35/35 passed, zero failed/skipped. The full/manual build 119.1 remains the upload candidate.

- [Full/manual release run](https://github.com/lpalbou/AbstractAssistant/actions/runs/39200275528)
- [Automatic critical run](https://github.com/lpalbou/AbstractAssistant/actions/runs/39200274109)

Legacy pending Watch-only runs39181516347 and39104390056 were cancelled. A subsequent list of
100 Watch runs finds no active legacy upload. app-store still requires reviewer lpalbou and a
custom deployment-branch policy; credentials/protections were not changed.

## Release boundary

The combined candidate must pass full native checks before the protected upload job. A required
human approval is retained. Actual Apple signing/upload/processing is not claimed by the receipts
above. Public App Review and Store publication remain separate operator actions.

## Full/manual result

[Full native summary](full-native-summary.json) confirms 79/79 passed, zero failures/skips.
[Full candidate](full-candidate.json) records the real source/full-suite/schema/digest/extraction
verification of 0.6.21 (119.1), plus both device apps' metadata. [CI state](full-ci-state.json)
records all test/archive jobs green and the required human app-store approval waiting.

The tested binary is pinned tocd 6bbf3. Subsequent Watch feature commit 015c9da is not included;
new source changes require a new candidate. Apple signing/upload/processing of this combined
candidate still needs the operator's protected approval and is not claimed complete.
