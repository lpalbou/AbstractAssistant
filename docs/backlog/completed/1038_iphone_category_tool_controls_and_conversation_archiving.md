# 1038 — iPhone category tool controls and actionable conversations

> Package: abstractassistant
> Type: task
> Created: 2026-10-18
> Status: Completed
> Completed: 2026-10-18
> Priority: P1
> Labels: iphone, tools, sessions, archive, ux

## Summary

Add Off/Auto/Approve category controls and Watch-style grouped conversation rows with compact
statistics, visible states, and server-backed archive/restore.

## Current code reality

ConversationToolsScreen supports only individual modes. ToolCatalogGroup filters row lists for
search; category mutations must use the full inventory rather than search results. Inherited
Settings defaults must be materialized before modifying a category; unavailable tools stay Off.
ConversationsSheet is an ungrouped list with unbounded titles and text stats. SessionSummary
already aggregates exchanges/tools/time. The Watch uses existing POST sessions/{id}/archive,
POST sessions/{id}/unarchive and GET runs?archived_only=true routes; iPhone lacks their wiring.

## Scope and acceptance

- [x] Category selector is visible collapsed/expanded, supports mixed state, affects all available
      tools in that category only, preserves other categories and default precedence.
- [x] Today/Yesterday/Earlier groups, two-line titles, icon counts and explicit last-activity age.
- [x] Working/Needs you/Failed states, archive confirmation, archived list and Restore.
- [x] No archive of active/stale sessions; preserve drafts, account isolation and current-session
      lifecycle; failed requests retain data and allow retry.
- [x] Existing gateway routes, tests and inspected native screens, normal iPhone installation.

## Boundaries

iPhone only. No Watch writes, AbstractFramework/root changes, new server APIs, server deployment
or package publication. No real user conversation archive during validation. ADR impact None:
existing gateway authority and cross-device archive semantics.

## Validation plan

Meaningful transport/state tests for mixed/inherited/category behavior, disabled tools, date
boundaries, archive/restore and stale/failure guards; native UI journeys for category selection
and history archive/restore; inspect screenshots and refine before normal signed install.


## Completion report

Completed 2026-10-18. Original path `planned/1038_iphone_category_tool_controls_and_conversation_archiving.md`;
final path `completed/1038_iphone_category_tool_controls_and_conversation_archiving.md`.
Original implementation scope preserved above.

Category selection, full-inventory/mixed/inherited semantics and disabled-tool protection are
shared by Settings/session/automation editors. Conversations now use compact two-line cards,
local-day groups, icon stats/explicit ages and clear states. Archive confirms its cross-device
scope; Archived restores through existing gateway routes. Store context/revision guards,
fresh active checks, mutation gates, complete archived pagination and preserved lower-bound
count metadata protect history consistency. Symbols: ConversationToolsScreen,
ToolCategorySelection, ConversationHistory/ConversationsScreen, SessionSummary, AssistantStore,
GatewayClient, mock/native fixtures and focused HTTP/state/UI tests.

**246 package tests + two final native journeys + one physical read-only test passed.**
No runtime warnings in final native/device results. Parent visual QA rejected wrapped and
icon-only intermediate stat layouts, then confirmed final explicit icon/text rows. Added native
visibility/hittability/geometry checks and visible Mixed label. tools_astra independently
approved source and final rendered artifacts. Evidence preserves initial compile and visual
iterations. No real user conversation archived/restored during verification.

Normal **0.6.19 (27)** installed/launched on iPhone with no test PlugIns. Watch priority retained;
no Watch, AbstractFramework/root, server API/deployment or package publication changes. Public
phone README/architecture/validation and Assistant LLM aggregate updated. All changes uncommitted.
[Evidence and reproduction](../evidence/1038/README.md).

Residual limits: recent history is bounded to 60 roots and marks count lower bounds with “+”;
archived history follows all pages. Search covers loaded titles. Fresh checks cannot eliminate
a remote start after the check; the existing server remains authoritative. Cross-device archive
semantics use the existing Watch contract; live test verified reads, while write/restore paths
were checked by hermetic transport/state/native journeys. No new speculative follow-up or ADR:
ADR impact None, existing authority/contract and local presentation only. No priority impact.
