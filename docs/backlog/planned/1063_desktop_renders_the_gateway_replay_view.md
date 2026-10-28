# 1063: The desktop renders runs from the gateway's replay view

**Status**: planned, in progress (branch `feat/replay-view-desktop`, draft PR). Not released.
**Cross-package**: framework root 0993 (`docs/backlog/planned/0993_one_ledger_replay_many_views.md`
in the root repo); AbstractRuntime 0854 (`abstractruntime/docs/backlog/planned/0854_replay_view.md`,
inventory of this app's private reconstruction: "AbstractAssistant (desktop Python/Qt, iPhone,
watch)"); ADR 0010 (one replay, many views) in AbstractRuntime. Supersedes the desktop half of 0008.
**Scope**: the desktop app only. `phone/` and `watch/` are another track.

## What was done

- Client: `GatewayClient.supports_replay_view()` (OpenAPI paths; a failed discovery raises, never
  "no"), `get_run_view()` (ETag, 304, `?at=`), `stream_run_view()` (SSE `view`/`delta`/`done`,
  `Last-Event-ID`); the SSE parser keeps `id:`.
- `abstractassistant/gateway/replay_view.py`: `ViewFold` (the client copy, folded with
  `abstractruntime.replay.apply_delta`; a delta whose cursor is not newer than the copy is
  dropped), `ViewProjector` (view -> the palette's events), `follow_run_view` (GET, stream,
  bounded reconnects with the copy's cursor), `follow_run_ledger_locally` (a gateway before
  0.17.0: ledger pages + run summaries folded with the runtime's `ReplayView`), `follow_run`
  (chooses, says which), `LiveText` (the ledger stream's `llm.delta` frames only, beside the
  view), `stats_from_view`, `finished_llm_calls`.
- Worker and CLI follow the view; the palette closes an approval batch (`withdraw`) or ask
  dialog when the view says the wait is no longer open; `replay_mode` is shown in the status
  line on an older gateway.
- Deleted (the private reconstruction listed in runtime 0854): `gateway/adapter.py`,
  `gateway/run_controller.py`, the record parsers of `gateway/events.py`, and in
  `ui/gateway_worker.py` `_handle_events`, `_normalize_wait_dict`, `_all_ledger_wait_occurrences`,
  `_answered_wait_occurrences`, `_suppress_resolved_waits_for_attach`,
  `_find_latest_wait_from_ledgers`, `_find_wait_from_run_summaries`, `_make_synthetic_wait_record`,
  `_maybe_emit_pending_wait`, `_record_output_artifact_candidates`, `_note_finished_llm_call`,
  `_is_foreground_run`, `_update_follow_run_id_from_record`, `_record_run_stats`, the post-run
  gap-filler reseed, and the unused approval/answer `threading.Event`s (assistant 0008).
- Kept on purpose: `gateway/history_seed.py` is the SESSION transcript seed (many turns from the
  history bundle); the view is per run. A session-level view is gateway 0939's sessions index.

## Live text (operator ruling 2026-10-28)

The view stream carries no ephemeral text. Until the runtime and gateway ship one (a planned item
upstream), `LiveText` reads `GET /runs/{root}/ledger/stream` for `llm.delta` / `llm.delta_end`
only (from the view's root seq, so history is not re-read; step rows are skipped). A call the
view holds as finished gets no more live text, decided under one lock with the delta forwarder.
Test: `tests/basic/test_replay_view_live.py::test_live_text_appears_then_the_committed_message_replaces_it_and_a_late_delta_is_dropped`.

## Known differences (to file upstream in AbstractRuntime)

- `llm` activities carry no output text: the activity card's per-cycle "thinking" text is gone.
- Emit-event artifacts are not recorded (`_fold_event` returns before `_note_artifacts`): an
  `abstract.media.image.generated` event is no longer its own message.
- No prompt-cache counters in the view's usage.

## Tests and evidence

See the PR. Conformance: `tests/basic/test_replay_view_client.py` (15 cases); worker, CLI,
local fold, live text: `tests/basic/test_replay_view_live.py`; ported: tool identity, session tool
policy, worker run/attach tests (folded by the runtime reducer).
