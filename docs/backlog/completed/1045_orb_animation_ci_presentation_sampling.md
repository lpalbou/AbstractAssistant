# 1045 — Reliable orb presentation checks on hosted CI

> Package: abstractassistant
> Type: task
> Created: 2026-10-19
> Status: Completed
> Completed: 2026-10-19
> Priority: P1
> Labels: iphone, tests, release

## Current code reality

Release run39250011911 on922b039 passed80/81 native checks, all new automation/update UI cases,
package250 and Watch73. OrbRenderingTests.testMorphPresentationAndMidflightReversal failed
at line95: the first changed return screenshot already matched the final sphere (mean pixel
difference0.00000219). The real renderer can finish its650ms animation before a hosted simulator
schedules drawHierarchy. The old test assumes that the first observed changed frame must be
intermediate. This is a test scheduling assumption, not evidence of a broken morph.

## Scope and expected outcome

Keep real native endpoint, return and interruption checks. Verify intermediate and reversed
artwork with explicit sampled progress, using the production renderer, without wall-clock
frame assumptions. Keep visual difference thresholds and default production timing. No
framework/server or unrelated Watch source changes; do not bypass the full release gate.

## Validation

Run affected native visual checks, inspect retained rendering frames, then rerun the full
combined release pipeline. Preserve the original80/81 failure evidence. A release remains
blocked until its own full suite passes. ADR0002/0003 apply unchanged.

## Implementation and local validation

Preserved all original endpoint/intermediate/reversal assertions and thresholds. A two-second
test-only instance duration leaves time for hosted frame sampling; normal AssistantOrb calls
retain650ms. View-resolution pixel comparison avoids blocking the UI thread with high-DPI
byte loops; explicit production-renderer samples also cover0.7→0.35→0.65. Revised native6/6
and package251/251 pass; frames inspected. Full hosted rerun remains required.

## Completion evidence

Full hosted run39257198880 on d2aec7ba706fa0e162a0eb4a852ee9a91069bacc passed81/81
native checks with zero failures and skips. Contracts14, Watch package73, companion build,
Phone package251 and the combined Release archive passed. Candidate0.6.22(126.1) verified
with release.py: schema2, matching source SHA, full-test requirement, both bundle identities
and archive digest5dd71f025425e5a0b9ba7e5e89bc07fb7e8c06f43b13628ee3f79ef109453788.
Upload remains waiting at the existing human gate. No gate bypass. This completion record is
left uncommitted under the user's new validation-before-commit instruction.
