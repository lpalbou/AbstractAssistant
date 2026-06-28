# Planned: Durable Session Topics and Summaries

## Metadata
- Created: 2026-06-21
- Status: Planned
- Completed: N/A

## ADR status
- Governing ADRs: [ADR 0001](../../adr/0001_gateway_native_assistant_v2.md)
- ADR impact: Extends the gateway-native tray shell with durable session metadata requirements.

## Context

The v2 shell now benefits from a rapid recent-session picker in the header, but the picker is only
as good as the session topic metadata behind it. Today the app has durable sessions and a durable
`title` field, yet gateway-native mode does not automatically generate or persist meaningful
session topics or summaries.

## Current code reality

- `abstractassistant/core/session_index.py` persists `SessionRecord.title`, `created_at`, and
  `updated_at` in `sessions.json`, but there is no separate summary/topic schema.
- `abstractassistant/core/llm_manager.py` exposes `list_sessions()` and falls back to a
  transcript-derived local label when `title` is empty or `New session`.
- In gateway mode, `update_active_session_title_async()` is intentionally disabled, so the current
  shell cannot rely on background LLM title generation.
- The new v2 picker therefore uses a pragmatic fallback: the first user query, formatted as
  `yy/mm/dd - topic`.

## Problem

The current fallback is useful, but it is not a product-quality metadata strategy. Long first
messages, ambiguous openings, and topic drift all reduce scanability when users need to jump across
many past sessions quickly.

## What we want to do

Define and persist durable session topic/summary metadata for the gateway-native shell.

## Why

Without a defined topic/summary model, session navigation stays brittle and every surface that
needs a compact session identity will keep re-deriving it differently from raw transcript content.

## Requirements

- Define the canonical metadata fields needed for session navigation and recap.
- Persist those fields durably with the existing multi-session index or an adjacent per-session
  metadata file.
- Keep a local fallback when generated metadata is unavailable.
- Make the recent-session picker, future session lists, and possible search surfaces read from the
  same canonical metadata.
- Avoid blocking chat turns on metadata generation.

## Suggested implementation

- Introduce explicit `topic` and optional `summary` semantics for sessions.
- Decide whether the durable home is `SessionRecord`, per-session metadata beside `session.json`,
  or another lightweight store.
- Keep first-user-query fallback as the zero-network baseline.
- Add a best-effort background updater for gateway-native mode once the source of truth is defined.

## Scope

- session metadata model
- durable storage
- recent-session picker fidelity
- background topic generation policy

## Non-goals

- Do not redesign the full session browser in this item.
- Do not require a network round-trip just to render existing session lists.

## Dependencies and related tasks

- [ADR 0001](../../adr/0001_gateway_native_assistant_v2.md)
- [0002](0002_gateway_native_assistant_v2_rollout.md)
- [0004](0004_production_ux_and_catalog_default_hardening.md)

## Expected outcomes

- Session navigation surfaces have one canonical source of topic metadata.
- Users can skim recent sessions quickly without reading raw transcript excerpts.
- Gateway-native mode has a documented, durable answer for session topics and summaries.

## Validation

- `python -m pytest tests/basic tests/integration -q`
- Manual verification that the header session picker shows stable, readable labels across sessions
  with and without generated metadata.
- Confirm that no network dependency is required to render the picker for existing local sessions.

## Progress checklist
- [x] Add a recent-session picker to the v2 header with a first-query fallback
- [ ] Define durable session topic/summary fields
- [ ] Persist session topic metadata canonically
- [ ] Add best-effort gateway-native topic generation/update behavior
- [ ] Reuse the canonical metadata in all session-navigation surfaces

## Guidance for the implementing agent

Treat session topic metadata as a product contract, not a cosmetic string. If multiple UI surfaces
would display different session identities for the same transcript, the design is still incomplete.
