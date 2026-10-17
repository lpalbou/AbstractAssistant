# Proposed: Wait payload carries the risk tier; allow all in this run

> Created: 2026-10-16 22:30:00 +0200
> Type: improvement
> Priority: P2
> Labels: watch, runtime, gateway, approvals

## Metadata
- Created: 2026-10-16
- Status: Proposed
- Completed: N/A
- Owning packages: abstractruntime (wait payload), abstractgateway (commands), abstractassistant (desktop and watch)
- Track: [watch-apple](README.md) (Apple Watch client)

## ADR status
- Governing ADRs: [ADR 0001](../../../adr/0001_gateway_native_assistant_v2.md) (gateway-native thin client: the gateway owns workflows, runs, tools, policy and speech)
- ADR impact: None. The watch is one more thin client of the same gateway contract.

## Summary
Expose on the `tool_approval` wait the risk tier the runtime already derives from declared
tool facts (observe / act / outreach / destroy and the words the desktop assistant shows,
`Destructive`, `can delete`), and add a standing answer "allow all in this run" that the gateway
records as a per-run grant. The watch uses the tier to enable Double Tap only for read-only
tools and to colour the card; the desktop assistant stops deriving the tier client-side.

## Why
The desktop assistant shows risk pills, but the documented wait shape has no risk field
(abstractgateway/docs/automations.md §wait shape), so every client re-derives it or shows
nothing. The runtime's tool-approval policy already computes the band from declared facts
(abstractruntime/docs/tool-approval.md). "Approve all" is not a documented wait answer; the
only standing consent is per automation (`policy.tool_approval: auto`).

## Scope
- Runtime: add `risk: {tier, facts: [...]}` to the `tool_approval` wait payload and to the `waiting` block of `GET /runs/{id}`.
- Gateway: accept `payload: {approved: true, scope: "run"}` on `resume`, record the grant as a ledger record, and auto-approve later calls of the same tier or lower in that run; the grant never covers `outreach` or `destroy`.
- Clients: desktop assistant reads the tier from the payload; watch enables Double Tap for `observe` only and shows "Allow all in this run" on long press.

## Non-goals
No change to the tool facts vocabulary; no cross-run or per-user standing grants.

## Current code reality
- Tool facts and the four bands: abstractruntime/docs/tool-approval.md (declared `mutating`, `comms_send`, `destructive_capable`; host-injected ceiling; undeclared MCP tools gated as unvetted).
- Wait shape without a risk field: abstractgateway/docs/automations.md §Waits on a person.
- `tool_ids` subset approval exists; `scope` does not (api.md §commands).

## Dependencies
Agreement with the runtime and gateway seats on the payload field name and the grant record.

## Expected outcomes
- Every client shows the same tier from the same field.
- A run with many read-only calls can be approved once on the wrist without lowering the bar for destructive calls.

## Acceptance Criteria
- [ ] `tool_approval` waits carry `risk.tier`; the four tiers are covered by tests against declared facts
- [ ] `resume {approved: true, scope: "run"}` is recorded and auto-approves later `observe`/`act` calls in the run; `outreach` and `destroy` still wait
- [ ] The desktop assistant renders the tier from the payload (its client-side derivation removed)
- [ ] The watch enables Double Tap only when `risk.tier == "observe"`

## Testing
- `cd abstractruntime && python -m pytest tests -k tool_approval -q`
- `cd abstractgateway && python -m pytest tests -k resume_scope -q`

## Progress (2026-10-17)
- The watch reads risk tiers from `GET /api/gateway/discovery/tools` (`risk_tier`, `risk_rank`) and shows them on the approval card; the wait payload itself still has none.
- "Allow all in this session" is built client-side, as the desktop's chat trust is: the watch answers later approvals of the Ask run and starts new runs with `_runtime.tool_policy {auto_approve_max_risk_rank: 4, require_approval_tools: outreach tools}`. A gateway-held, revocable session grant (visible on every client) remains the open part of this item.
