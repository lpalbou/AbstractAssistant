# 1041 — iPhone CI and human-gated Apple delivery

> Package: abstractassistant
> Type: task
> Created: 2026-10-19
> Status: Planned
> Completed: N/A
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

- [ ] PR/main/manual CI: package tests, native hosted tests and critical UI journeys, unsigned
      Release archive, pinned source/build provenance and retained test/candidate artifacts.
- [ ] Explicit manual upload choice only on main; successful full native suite required;
      existing human-reviewed app-store environment gates all Apple credentials and upload.
- [ ] Upload exactly the checked candidate, validate identity/version/source/archive integrity,
      no untrusted PR secret access, no automatic upload on push, scoped key cleanup.
- [ ] TestFlight-ready normal App Store Connect upload, preserving eligibility for promotion;
      no automatic App Review submission or public release; document manual same-build promotion.
- [ ] Verify workflow/scripts, negative provenance/version checks, local candidate archive and
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
