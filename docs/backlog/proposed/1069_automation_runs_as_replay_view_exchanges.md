# 1069: An automation's runs as full conversation exchanges (replay view per occurrence)

**Status**: proposed · **Created**: 2026-10-28
**Found by**: operator QA 2026-10-28 (g) ("an automation must open like a chat session where each run is one
exchange, the new result marked"). Client part done in 1068 (exchanges, "New result" mark, opens on it).
**Related**: framework root 1063 (typed runs) and AbstractRuntime 0858 (run type stamped at start); 1063 here
(the desktop renders a run from the gateway replay view); AbstractRuntime 0862 (bookkeeping refs in a message's
artifacts).

## Problem

The automation view renders each occurrence from the automations route's row: `user_turn`, `answer` (text),
`failure`, `waits`, `artifacts` (names). A chat turn renders far more from the run's replay view: tool rows and
their approvals, live text, media tiles, the steps chip, statistics. An automation run is therefore a poorer
exchange than the same work done in a chat, and a person cannot see what a run did.

## Proposal

- Render each occurrence's answer side from `GET /runs/{run_id}/view` (the projector the chat already uses,
  `gateway/replay_view.py`), lazily for the runs in view; keep the occurrence row for the task turn and the
  trigger caption.
- With typed runs (root 1063), the gateway can list an automation's occurrences as runs of type `automation` with
  their view cursors, so the client needs no second listing.
- The "New result" mark and the attention acknowledgement stay as in 1068.
