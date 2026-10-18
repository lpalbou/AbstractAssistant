# Live activity and visible approvals — 0.6.6 (14)

## Outcome

The conversation follows the parent workflow and its agent descendants. A child approval
changes the main status to **Approval needed**, with **Review tools** visible even when
activity is collapsed. Questions show **Waiting for your reply**. The parent remains the
owner of Stop and the final answer.

Expanding activity reveals durable model cycles, tool calls, public results and failures.
It shows the last event and status-check age. A lost connection offers reconnection and
is distinct from a confirmed run failure. Terminal activity remains inspectable; reopening
history restores the latest turn's diagnostics without reading its answer aloud again.

Approvals offer **Deny**, **Approve**, and **Approve all** for the open conversation.
Approve covers the pending batch. Approve all snapshots currently enabled tool names into
this conversation's Auto selection and auto-answers qualifying subsequent waits in its
active workflow. Off, unavailable, unknown and newly added tools remain excluded. Questions
are never auto-answered. Saving Tools revokes the grant. An unrelated Inbox item cannot
change the open conversation's permissions.

## Evidence

- **130 Swift tests pass** (90 AssistantKit, 40 gateway client), including 16 Store tests:
  nested and parallel child waits with different session IDs; hydration of summary-only
  waits; exact child decisions; root-only final output; 405-record pagination; final drain
  of children no longer referenced by older gateways; failures surviving refresh;
  account-switch isolation; approval scope, availability and Off preservation; repeated
  wait occurrences; quiet history reopening.
- Transport checks cover authenticated SSE, split UTF-8/multiline frames, private-frame
  suppression, malformed frames, bounded-buffer overflow, 404/405 polling fallback,
  sign-in expiry, incomplete-stream reconnection, child-list pagination and filtering.
  Entity ledger tests use the actual wrapped `records/cursor/record/next_cursor` contract.
- **23 native tests pass** (18 hosted, 5 UI), with zero runtime warnings in
  `build/UITests-1792301769471230000.xcresult`. They cover collapsed/expanded activity,
  selectable tool results, full-row approval navigation, all three approval choices,
  completion, failure versus lost connection, unrelated Inbox denial and orb cancellation.
- The parent directly inspected the rendered screenshots below. An independent Astra 6
  reviewer at medium reasoning reviewed transport/state contracts, added adversarial Store
  tests, and inspected the collapsed approval and expanded tool-result renders.

The first native pass exposed a Review tools hit target that excluded its empty center.
The full row now has a 44-point minimum target; the second pass successfully navigates
through that center. A duplicate failure banner was also removed and its final render
inspected. These repairs are covered by the successful native run.

## Inspected renders

- [Compact activity](../screenshots/activity-live.png)
- [Expanded tool result](../screenshots/activity-tool-result.png)
- [Approval in conversation](../screenshots/activity-approval.png)
- [Three approval choices](../screenshots/activity-approval-choices.png)
- [Completion](../screenshots/activity-complete.png)
- [Failure](../screenshots/activity-failure.png)
- [Lost connection](../screenshots/activity-disconnected.png)

## Review verdict and limits

**Approved** for the inspected phone layouts, interaction checks and tested contracts.
Feedback explains the user's next step without requiring an Inbox visit. Counts distinguish
cycles from tool calls; queued approval calls are not labeled as executed tools. Public
results provide discoveries without exposing model prompts or hidden reasoning.

Detail is capped at 250 retained rows and 4,000 characters per result with visible labels;
counts remain cumulative. Traversal is bounded to 64 runs and depth 16 with a coverage
notice. Four simultaneous SSE streams preserve HTTP capacity, with other children polled.
Generic status polling is every three seconds; scoped entity activity polls every second.
Backgrounding pauses observation. Automatic decisions for an already running workflow
therefore need this client to be active; future turns carry the persisted named Auto policy.
A resume decision still uses the gateway's existing exact wait-key contract.

Native UI cases use reproducible fixtures; transport tests use local responses faithful to
server source. They do not claim a new external-provider production run was performed.
Hardware keyboard navigation, larger Dynamic Type sizes and other screen sizes were not
visually reviewed in this pass. No gateway endpoint was added and no gateway update is
required. Watch source and builds remain separately owned.

## Device delivery

Built with the guarded iPhone-only script, one low-priority job and isolated DerivedData.
Strict code-signature verification passed. Installed and launched on the connected iPhone
17 Pro Max; device app inventory confirms **0.6.6 (14)**. Executable SHA-256:
`ae114b6abb2aeb72f8e7d314781f2df2ab25c22141a4b30997b06e8652521992`.
The final device build includes quiet history reopening and avoids refreshing tool inventory
when no approval batch can qualify for a conversation grant. Those state changes are covered
by the final 130-test Swift run; the 23-test native run covers the rendered interaction flows.
