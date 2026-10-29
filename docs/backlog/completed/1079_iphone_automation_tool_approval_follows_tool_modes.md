# 1079 — An iPhone-created automation's tool approval follows the person's tool modes

**Status**: completed (2026-10-29, unreleased) · **Priority**: P0 · **Created**: 2026-10-29
**Cross-package**: AbstractObserver 0006 (the waiting card says where this is decided). AbstractRuntime unchanged:
its automation controller does what the definition says.

## Why (operator QA, 2026-10-29)
On the operator's gateway, an automation run had waited 7 h 22 m on "needs your approval: fetch_url, fetch_url,
skim_websearch +1". The operator said the authorizations had been given at setup.

## Root cause (read-only, from the operator's data dir)
- **Both waiting automations were created on the iPhone.** The audit log records `POST /api/gateway/automations`
  from `AbstractAssistantWatch/1` (the shared Apple client) for 7734cbcb (2026-10-20) and 7f7613b4 (2026-10-21).
  Both definitions say `policy.tool_approval: "ask"`, with no `policy.tool_policy`. Every automation created from
  the web, the CLI or the desktop says `"auto"`.
- **The iPhone forced "ask".** `NewAutomationScreen` passes `askBeforeTools: true` hard-coded (since 2026-10-17),
  but the screen offers no Ask choice, and its footer promises "Tool permissions are saved with the automation so it
  can run while this iPhone is closed". Before 2026-10-26 the per-tool modes were not sent at all.
- **The runtime is not the cause.** With "ask" and no named policy, the controller grants nothing, so the static
  executor policy gates the network tools, and every occurrence parks. Occurrences 1 and 2 also waited and were
  approved by hand. The subrun is not the cause either: there was no grant for it to inherit, and children inherit
  `_runtime.tool_policy` (`test_automation_tool_approval`). The session tool policy store is empty, and by design its
  "approve" never reaches an automation run.

## What shipped
- `watch/apple/Packages/AbstractGatewayClient/.../Models.swift`: `NewAutomation.toolApproval` sets
  `policy.tool_approval`.
  - An explicit `askBeforeTools`, when given.
  - Otherwise the iPhone's tool modes decide: "ask" only when one of them is on Ask, else "auto".
  - Otherwise the watch's plan, else "auto".
  - `askBeforeTools` is now optional (`nil` by default).
- `phone/iphone/Sources/App/NewAutomationScreen.swift`: no longer passes `askBeforeTools: true`.
- Already-waiting runs, and automations created as "ask" before this: nothing approves them for the person, since
  no consent was recorded. They are told instead. AbstractObserver 0006's card reads "Waiting for your approval of
  4 tools since 7h 22m" and adds "This automation asks before these tools. To let it run unattended, set them to
  Run in the automation's Tools." Revising the two definitions is the operator's decision.

## Evidence
- `AutomationToolsTransportTests.toolApprovalFollowsTheToolModesWhenNotChosen`: with every tool on Auto, the request
  says `tool_approval: "auto"` and lists the auto tools; one tool on Ask gives "ask"; an explicit choice wins; no
  tools at all gives "auto". It is red with the old rule (mutation-checked).
- AbstractGatewayClient: 176 tests passed. AssistantKit: 205 tests passed.
