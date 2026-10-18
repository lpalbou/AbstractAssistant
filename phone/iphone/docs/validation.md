# Developer preview validation

For **0.6.8 (16)** restored replies after reload and shared Settings/session/automation tool
controls, see the [review and evidence](../design/validation/history-and-shared-tools-review.md).

For **0.6.7 (15)** directly editable tool overrides and iPhone defaults, see the
[tool defaults review and evidence](../design/validation/tool-defaults-review.md).

For **0.6.6 (14)** live activity, visible child approvals and conversation trust, see the
[activity review and evidence](../design/validation/activity-review.md).

For **0.6.5 (13)** inherited tools reaching the agent's model request, see the
[workflow regression and evidence](../design/validation/inherited-tools-review.md).

For **0.6.4 (12)** temporary-file cleanup and measured device storage, see the
[storage investigation and evidence](../design/validation/storage-review.md).

For **0.6.3 (11)** gateway compatibility and existing visit-route reuse, see the
[contract review and evidence](../design/validation/tool-contract-review.md).

For **0.6.2 (10)** microphone normalization and grouped session tools, see the [review and evidence](../design/validation/microphone-and-tools-review.md).

For the **0.6.1 (9)** orb/Stop refinement, see the [interaction review and evidence](../design/validation/orb-interaction-review.md).
The feature validation below records the 0.6.0 baseline.

Version **0.6.0 (8)** preserves the saved 0.5.0 baseline (`762b4a9`) and adds
conversation tool modes, isolated answer playback, optional answer statistics and an
automation history budget. The implementation stays within `phone/iphone`; the matching
gateway implementation is commit `3769d62e`. Watch source and builds are independently owned.

## Verified behavior

- Tools are reachable from Settings and the chat More menu. Explicit Off, Auto and Approve
  choices are scoped to the account, responder and session. Defaults remain visible; starting
  another conversation restores inheritance. Attachments and tool policy travel together.
- Only the speaking answer shows Stop. The native check creates two answers and verifies
  exactly one Stop control while the other answer retains Read.
- Statistics default off. Enabling them shows an answer-owned time/input/output/tools row;
  disabling them restores the lean layout. Missing usage is not inferred from total tokens.
- Growing history reveals a positive token budget. Blank inherits the gateway value; switching
  history off omits the override. The native flow tests zero rejection, custom values,
  preservation across toggles, default inheritance and successful creation.
- Entity approvals persist before execution. Approving executes through the entity's own
  executor; denial, Off, stale decisions and revoked home grants cannot execute the blocked
  tool. Foreign-owner reads/turns/decisions through both managed and legacy routes are refused.

## Evidence

**72 package tests** pass (44 phone state/transport/feature tests and 28 inherited client
tests). They include quiet entity restoration, terminal-visit cleanup, a lost turn response
recovering its pending approval without resending, and preserving the current conversation
when ending its visit fails.

**29 native tests** pass (13 hosted and 16 UI), followed by **16 focused tests** after the
scope/header refinements and **one final inheritance-toggle test**. The full result is `build/UITests-1792283589234957000.xcresult`;
the focused result is `build/UITests-1792284015547476000.xcresult`, and the final inheritance
result is `build/UITests-1792284134776882000.xcresult`.

**63 gateway tests** pass, including real HTTP routes, durable SQLite execution, the entity's
native ReAct visit workflow and existing visit/memory-tool regressions. Scripted model
responses make execution and denial counts deterministic; they do not contact an external
provider or create production email, entities or automations.

Rendered screens inspected by the parent and reviewers:

- [Inherited tools](../design/screenshots/conversation-tools-defaults.png) and [custom tools](../design/screenshots/conversation-tools.png)
- [Answer statistics](../design/screenshots/answer-statistics.png) and [isolated playback](../design/screenshots/isolated-answer-playback.png)
- [Inherited budget](../design/screenshots/history-budget-default.png) and [custom budget](../design/screenshots/history-budget-custom.png)

The full native run reports the previously recorded SwiftUI frame-dimension warning during
automation creation; its creation checks pass and rendered controls remain usable. The
focused run reports no runtime warnings. Physical microphone sensitivity and live provider
quality remain device/environment dependent.

## Review and compatibility

Two adversarial reviewers covered everyday usability and technical behavior. As each also
implemented an isolated piece, the other reviewer and parent checked those changes;
self-review is not counted as independent approval. Review findings led to server-side
owner checks, quiet restoration, lifecycle recovery and accurate inherited-mode displays.
See the [decision and review record](../design/validation/conversation-controls-review.md).

Assistant tool controls use the established discovery and run-start contract without
a capability probe. Entity session approvals require the entity session-tool extension;
ordinary entity chat remains available without it. Optional statistics require their
own gateway endpoint and stay absent when unavailable.
