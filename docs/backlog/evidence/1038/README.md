# 1038 — Category controls and actionable conversation history

Local iPhone-only work; target 0.6.19 (27), baseline 0.6.18 (26). No root AbstractFramework,
Watch, server API/deployment or package publication changes.

## Verified package behavior

246 tests passed: 170 AssistantKit + 76 client. Five core additions cover full-category overrides,
inherited/mixed/disabled behavior, local-calendar date boundaries, ages, active roots and
archive/restore/current-session lifecycle. Six HTTP/state tests cover established archive routes,
identifier rejection, all-page archived listing/repeated pages, write failure, fresh active
state, preserved partial-count metadata, late account response and old archived-list failure.
[Package log](package-verified.log). Initial compile passes corrected a missing contains(where:)
label and missing workflowId:nil fixture arguments; retained for audit, not product failures.

## Implementation

- Full-inventory category controls preserve unrelated modes and keep disabled tools Off.
  Inherited defaults materialize before category override; mixed choices have no selection.
  Search visibly states the full category count because hidden siblings also change.
- Separate rounded conversation rows group Today/Yesterday/Earlier, cap titles at two lines,
  show icon counts/explicit last-activity ages and Needs you/Working/Failed labels.
- Archive confirms cross-device scope; archived view restores through existing Watch routes.
  Active roots block archive and a fresh gateway turn check precedes the POST.
- Archive listing walks all pages. Bounded recent-history counts use '+' with preserved
  completeness metadata, unaffected by local archive/restore changes.
- Failed writes retain rows. Context/revision guards reject old results/errors, and a busy
  mutation blocks local send/open transitions. Archiving the idle current session starts a
  new conversation with the same responder.

Initial native validation waited in the Watch-priority Xcode queue; final receipts are below.
Repeated iPhone attempts yielded75 and stopped only their own process group. The parent then
stopped its retry queue and switched to a strict wait for other Xcode work to finish.
No real user conversation is archived/restored in validation; mock mutations prove the path.


## Native and physical verification

**Two final UI journeys passed**, no failures/skips/runtime warnings:
[native summary](native-summary.json), [log](native-verified.log). Bulk selector test searches a
single tool, sets the full category, verifies hidden sibling selection, disabled tool Off,
unrelated category preservation, saved selection and visible Mixed label. History journey
verifies groups/statuses, active archive disabled, confirmation, archived row/restore, and
return to recent history. Explicit geometry/hittability assertions keep status text visible
on a single line at the tested native size.

Parent rejected [wrapped stats](initial-wrapped-history.png), then an adaptive Label variant
that rendered [icons only](rejected-icon-only-history.png). Explicit icon/Text rows and intrinsic
widths fix both. A superseded own verification process group was stopped for that refinement;
no unrelated Xcode process was interrupted. Final inspected captures:

- [Category controls and visible Mixed](category-mixed.png)
- [Bulk search scope](category-search.png)
- [Compact conversation cards](conversations.png), [history groups](history-groups.png)
- [Archive confirmation](archive-confirmation.png), [Archived/Restore](archived.png)

[Independent review](adversarial-review.md): Approved, source plus final visible artifacts.

**One physical read-only test passed**, no runtime warnings:
[device summary](device-summary.json), [log](device-verified.log), [counts only](device-history-counts.json).
Existing Keychain connection queried current recent/archived routes and tool inventory: 11 recent
sessions/35 roots, eight categories,20 unavailable tools, zero archived sessions. No real user
conversation was archived/restored, and no credentials or conversation contents were exported.
Server-side mutation is covered by hermetic HTTP/state/native mock journeys using the established
Watch routes; live verification covers reads, not actual user archive writes.

The Watch-priority queue yielded and was then held strictly until other Xcode work completed.
Only iPhone DerivedData/Build was cleared to avoid stale device package layouts; no Watch
source/products were edited. Public README/architecture/validation and LLM aggregate updated.

## Reproduction

From abstractassistant:

```sh
swift test --package-path phone/iphone/Packages/AssistantKit --jobs 1
python3 phone/iphone/scripts/build.py --ui-test SIMULATOR_ID \
  --only-testing AbstractAssistantPhoneUITests/PhoneUITests/testCategoryBulkControlsRespectHiddenAndDisabledTools \
  --only-testing AbstractAssistantPhoneUITests/PhoneUITests/testGroupedHistoryArchivesAndRestoresUsingExistingActions
python3 phone/iphone/scripts/build.py --live-media-test DEVICE_ID --team TEAM_ID \
  --only-testing AbstractAssistantPhoneTests/LiveGatewayMediaTests/testConversationArchiveInventoryReadOnly
python3 phone/iphone/scripts/build.py --device DEVICE_ID --team TEAM_ID
```

Limits: recent list is bounded to60 roots, with stable lower-bound count metadata; archive list
loads all pages. Fresh active checks cannot eliminate a remote start between check and write;
the existing server route retains final authority. Text search covers loaded titles. No new
cross-package policy/ADR or speculative follow-up was introduced.


## Delivered

Normal signed **0.6.19 (27)** built with no test PlugIns and was installed/launched on the
physical iPhone: [app metadata](normal-app.json), [normal build](normal-build.log),
[install](install.json), [launch](launch.json). Final source and visible UI approved by the
independent reviewer. All changes remain uncommitted.
