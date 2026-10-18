# History restoration and shared tool controls — 0.6.8 (16)

## Delivered behavior

Reopening a conversation restores each root turn’s public assistant reply and prompt,
in order. Run-index summaries can omit output, so every turn is hydrated from its full
run result. History follows all index pages, deduplicates roots, and bounds concurrent
turn hydration to four. The replacement is atomic: a failed read leaves the existing
conversation intact with an error. Internal child output and reasoning are excluded.
The freshly hydrated latest turn determines activity state; historical completions do
not trigger automatic speech, including when an older index row still says running.

One tool editor serves three entry points: Settings defaults for the gateway/account,
a session override beside the responder, and an automation override during creation or
from its detail screen. Session choices override Settings; automation choices independently
override Settings. Automations snapshot fresh inventory and save both the offered tool
list and runtime ceiling, including explicit deny-all. The current session’s exception
never becomes an automation default. Existing explicit session selections are preserved;
legacy Assistant defaults migrate once to the shared Settings key.

Available categories are mint and listed before muted categories needing gateway setup.
Available rows precede disabled rows within a category. Search retains category availability
from the full inventory and keeps the mode control above the keyboard. New automation
text and number input dismiss on outside taps, without a keyboard toolbar.

## Independent review and corrections

Astra 6 at medium reasoning performed adversarial code and contract review. Findings
resulted in regression tests and fixes for concurrent workflow edits being mistaken for a
successful tool save, skipped revisions, repeated Run Now taps, stale account results,
and stale run-list status replaying historical speech. The parent performed native visual
inspection and interaction review; this is not a multi-persona UX review.

Automation saves use the existing PATCH route and wait for the committed revision.
They verify the target and named policy before confirming success. Run Now never follows
an unconfirmed policy revision. A queued acknowledgment alone is insufficient.

## Verification

- **152 Swift tests pass:** 103 AssistantKit tests and 49 gateway-client tests, including
  omitted list output, all history pages, child filtering, stale statuses, newest-turn
  selection, quiet restoration, a subsequent new answer, defaults migration and isolation,
  disabled-tool handling, required workflow inputs, wire payloads, queued revision polling,
  deny-all, unsupported-server rejection and concurrent changes.
- **37 backend tests pass:** real HTTP automation creation/revision reaches the shipped
  agent’s model tool schemas; required tools park for approval; named Auto executes a tool;
  the next occurrence after a deny-all revision receives zero tool schemas. Existing
  automation approval and runtime-input protections remain covered.
- **Native UI waves pass:** four tests in `build/UITests-1792304402693017000.xcresult`,
  four in `build/UITests-1792304578003216000.xcresult`, and three final polish tests in
  `build/UITests-1792304714602790000.xcresult`. They cover termination/relaunch history,
  global/session precedence, automation creation and subsequent edits, tools during work,
  gateway-disabled tools, search and inherited/custom history budgets.
- A final native integration test passes with zero runtime warnings in
  `build/UITests-1792304910874366000.xcresult`: Settings Read File = Approve and session
  Read File = Off produce a new automation with Read File = Approve, verified again from
  its committed definition. This also compiles the final shared snapshot/category code.
  Across the four waves, nine distinct native scenarios passed (12 executions).
- The first two native waves recorded a frame warning when focusing the automation task
  field. Removing its keyboard toolbar cleared the warning; the final three-test wave has
  **zero runtime warnings** and asserts the tool selector is entirely above the keyboard.

Inspected native images: [earlier replies](../screenshots/history-restored-replies.png),
[latest reply and activity](../screenshots/history-restored-latest.png),
[Settings defaults](../screenshots/tools-settings-defaults.png),
[Settings grant saved to an automation](../screenshots/tools-settings-to-automation.png),
[automation override](../screenshots/tools-automation-override.png),
[persisted automation choices](../screenshots/tools-automation-persisted.png),
[available category](../screenshots/tools-available-category.png), and
[unavailable category](../screenshots/tools-unavailable-category.png).

Approved for these inspected layouts and flows. Larger Dynamic Type sizes and other
screen sizes were not visually inspected. Native cases use controlled demo data and do
not establish a fresh production agent/provider run.

## Compatibility and delivery

History restoration and app/session defaults use existing gateway APIs. Mixed per-tool
automation approvals need the additive Runtime `definition.policy.tool_policy` contract.
Runtime commit `d9ab07a` implements it; gateway HTTP proof is `5d544b4c` and its API guide
is `e1793562`. These backend changes are committed but **not published or deployed to the
remote gateway**. An older runtime’s 422 is shown without retrying after dropping policy.
Settings changes apply to new automation snapshots; existing routines retain their saved
grant until their Tools are saved again. No new endpoint was added.

The signed app **0.6.8 (16)** was installed and launched on the connected iPhone 17 Pro Max.
Device application metadata confirms version `0.6.8`, build `16`; launch returned PID
`7675`. The existing installation was updated in place. Binary SHA-256:
`51426b10e6bcb8b284d80f419753ddff8460002f4a369ebdfa2f7039b62119ec`.
The iPhone build yielded to the active Watch test before native validation began.
