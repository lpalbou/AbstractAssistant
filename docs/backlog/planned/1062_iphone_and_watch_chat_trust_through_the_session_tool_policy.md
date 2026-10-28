# 1062 — iPhone and watch: "Approve all" through the gateway's session tool policy

> Package: abstractassistant (iPhone and Apple Watch apps); depends on abstractgateway, abstractruntime
> Type: improvement
> Created: 2026-10-27
> Status: Planned
> Completed: N/A
> Priority: P2
> Labels: approvals, tools, iphone, watch, gateway

## Summary

The desktop now writes a chat's "allow all" grant to the gateway's **session tool policy**
(`/api/gateway/sessions/{session_id}/tool-policy`, contract v1, gateway and runtime branch
`feat/session-tool-policy`), so the runtime never emits a wait for a covered call and the approval
gate no longer flashes. The iPhone and the watch still keep conversation trust on the device and
answer each wait after it arrived: the gate shows and disappears on every client, and the replayable
ledger records a wait and a resume for each covered batch. Move them to the same route.

## Current code reality (2026-10-27)

- `phone/iphone/Packages/AssistantKit/Sources/AssistantKit/AssistantStore.swift`
  - `approveAll(_:)` (l.854): answers the shown wait `approved: true`, then stores the conversation's
    Ask tools in `UserDefaults` under `<toolsKey>.approvalTrust` (comment: "conversation trust is client
    owned").
  - `applyConversationTrust(epoch:)` (l.882): for every later approval wait whose calls are all Auto
    or granted, answers it after it arrived (`autoAnsweredWaits`).
  - `canApproveAll(_:)` (l.849), `sessionApprovalGrants`, `approvalTrustRevision`.
- Tests: `phone/iphone/Packages/AssistantKit/Tests/AssistantKitTests/ActivityStoreTests.swift`;
  UI: `phone/iphone/Sources/App/InboxScreen.swift`.
- Desktop reference (this repo): `AssistantController.grant_session_tool_auto_approval` /
  `revoke_session_tool_auto_approval` / `session_tool_policy_path`, `AssistantPalette._on_tool_decision`,
  and the `abstract.tool_policy_decision` activity line (`gateway/events.py`, `ui/activity.py`).

## Scope and expected outcome

1. Feature-gate on `GET /api/gateway/discovery/capabilities` → `capabilities.session_tool_policy.supported == true`.
2. `approveAll`: POST `{approve: {tools: <the granted Ask tools>}, client: "abstractassistant-iphone"}`
   (the phone grants by name today; `approve.all` + `max_risk_rank` only if the product wants the
   desktop's wording), THEN answer the shown wait as today. Show `clamped` entries to the person.
3. With the capability, `applyConversationTrust` no longer answers waits: a wait that arrives is a real
   question. Reset (DELETE) where the phone resets conversation trust; read the stored policy (GET) on
   opening a conversation so a grant made elsewhere is shown and can be reset.
4. Render `abstract.tool_policy_decision` (`emit_event`) as an activity line ("Allowed by this chat's
   policy: <tool>" / "Denied by …"), never as a wait; the watch the same.
5. Older gateway (capability absent): keep today's client-owned trust and say so (log and, where the
   phone shows tool status, the UI).

## Non-goals

- Changing what "Approve all" covers on the phone (by name, Ask tools of this conversation).
- Answering waits that already exist when the policy is written (contract v1 §7).

## Promotion criteria

The gateway and runtime `feat/session-tool-policy` branches are merged and released, and the desktop
change (`feat/session-tool-policy` in this repo) is merged.

## Validation

- `swift test --package-path phone/iphone/Packages/AssistantKit` with a fake gateway: POST before the
  wait answer, DELETE on reset, no auto-answer with the capability, the old path without it; each test
  red with the change reverted.
- A real gateway: approve all on the phone, then a covered tool call shows no approval card on the
  phone, the watch or the desktop, and the activity shows the policy line.
