# 1063: The desktop renders runs from the gateway's replay view

**Status**: planned, in progress (branch `feat/replay-view-desktop`, draft PR). Not released.
**Cross-package**: framework root 0993 (`docs/backlog/planned/0993_one_ledger_replay_many_views.md`
in the root repo); AbstractRuntime 0854 (`abstractruntime/docs/backlog/planned/0854_replay_view.md`,
inventory of this app's private reconstruction: "AbstractAssistant (desktop Python/Qt, iPhone,
watch)"); ADR 0010 (one replay, many views) in AbstractRuntime. Supersedes the desktop half of 0008.
**Scope**: the desktop app only. `phone/` and `watch/` are another track.

## What exists on the branch

- `GatewayClient.supports_replay_view()` (OpenAPI paths; a failed discovery raises, never "no"),
  `get_run_view()` (ETag, 304, `?at=`), `stream_run_view()` (SSE `view`/`delta`/`done`,
  `Last-Event-ID`); the SSE parser now keeps `id:`.
- `abstractassistant/gateway/replay_view.py`: `ViewFold` (the client copy, folded with
  `abstractruntime.replay.apply_delta`; a delta whose cursor is not newer than the copy is
  dropped), `ViewProjector` (view -> the events the palette already renders: status, assistant,
  tool_started, tool, tool_request, ask_user, interaction_closed, cycle, tool_policy_decision),
  `follow_run_view` (GET, stream, bounded reconnects with the copy's cursor).
- `GatewayWorker`: on a gateway with the routes, both a new run and an attach follow the view
  (`_follow_view`); otherwise it emits `replay_mode: legacy` (shown in the run status line) and
  keeps the 0.15.0 ledger path. The palette closes an approval sheet batch (`withdraw`) or ask
  dialog when the view says the wait is no longer open (answered on another client).
- Tests: `tests/basic/test_replay_view_client.py` (15 runtime conformance cases: the folded copy
  equals the expected view; a skipped delta makes it differ; a duplicate or late delta is
  dropped, and without the guard a late delta rolls the copy back; projection of a delegated
  child approval, a closed interaction, attach).

## Live check (abstractgateway==0.17.0, abstractruntime 0.15.0, scratch venv, file stores)

3,000-record completed run (750 llm_call + tool_calls cycles, snapshot output, no terminal record):
- discovery true; GET 200 with ETag = cursor, `If-None-Match` -> 304; stream `view` then `done`,
  frame id == ETag; resume with that id -> only `done`; folded copy == GET.
- Time to first render: view 62-72 ms cold (5 ms warm) vs the 0.15.0 ledger path 418-431 ms
  (ledger pages + adapter fold + history bundle). The ledger path never produced the final
  answer for this run (output only in the snapshot); the view has `<root>:final`.

## Next steps (not done)

1. Live token text: the view stream carries no `llm.delta`; on the view path a streaming run
   shows its reply only when the message lands. Read the ledger stream's `llm.delta` frames
   only (or ask the gateway to forward them on `/view/stream`) before shipping.
2. Delete the private reconstruction the view replaces, keeping only what the labeled legacy
   path needs (or fold legacy ledger pages with `abstractruntime.replay.replay` and delete it
   all): `ui/gateway_worker.py` `_answered_wait_occurrences`, `_suppress_resolved_waits_for_attach`,
   `_find_latest_wait_from_ledgers`, `_find_wait_from_run_summaries`, `_make_synthetic_wait_record`,
   `_maybe_emit_pending_wait`, `_update_follow_run_id_from_record`; `gateway/adapter.py`;
   `gateway/run_controller.py` subworkflow stack; `gateway/history_seed.py` root-ledger tool cards.
3. Artifacts panel from `view.artifacts`; run stats from `view.usage` (today only per-llm usage).
4. Live test of the GUI path with a real run (LLM) on 0.17.0: approval from a delegated child,
   answered from the console, sheet closes.
5. Adversarial read-only review; full suite; PR to ready; merge on green; release 0.16.0 by
   workflow_dispatch from main; verify PyPI.
