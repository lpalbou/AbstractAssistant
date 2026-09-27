# 0853 — Sessions are gateway-first: the local session index is a rebuildable cache, never a source of truth

**Status**: planned · **Priority**: high · **Created**: 2026-09-27
**Package**: abstractassistant · **Found by**: operator, 2026-09-27 (uninstall with data purge,
reinstall: the Assistant still listed old sessions, "but not fully")
**Related**: 0852 (Automations in the Assistant — depends on this), 0006 (durable session
topics), abstractframework backlog 0928 / automations contracts C11 (`session_kind` on `/runs`),
the uninstall purge fix in the framework repo (`scripts/install.sh`)

## Summary

The Assistant's session list, titles and transcripts come from its own files under
`~/.abstractassistant/`, not from the gateway that holds the runs. Make the gateway the only
source of truth: the session list is the gateway's root runs folded by `session_id` (the same
fold AbstractCode uses), titles come from the first user turn server-side with an optional local
label, transcripts come from the gateway history, and the local files shrink to a cache keyed by
gateway run ids that can be deleted at any time and is rebuilt when it disagrees with the gateway.

## Why

The operator's question (2026-09-27), restated neutrally: the sessions should come from the
gateway — is the local store there for speed, or is it a mistake? If for speed, is it guaranteed
1:1 with the runtime?

Answer from the code: **it is a second store, not a speed cache, and nothing keeps it 1:1.**

- **It predates the thin client.** The index's own docstring still describes the embedded-runtime
  era: "AbstractAssistant already persists a single session under the data dir: `session.json`
  (transcript snapshot + ids), `runtime/` (AbstractRuntime stores)" (`core/session_index.py:1-10`).
  The multi-session registry was layered on that, and survived the move to a gateway client.
- **Session identity is minted locally.** `SessionIndex.create_session` makes `sess_<uuid>` and
  `actor_<uuid>` and a directory `<data_dir>/sessions/<id>/` (`core/session_index.py:191-216`).
  The gateway learns the id only when a turn is submitted with it
  (`ui/gateway_worker.py:1216`, `start_run(session_id=...)`).
- **The list never asks the gateway.** `SessionIndex.records()` (`core/session_index.py:120-122`)
  → `LLMManager.list_sessions` / `session_digests` (`core/llm_manager.py:433-479`) →
  `controller.list_sessions` / `session_digests` (`controller.py:961-984`, docstring :965 "Reads
  local files only") → `app.py:6231-6249` `_session_records` and `_open_session_switcher`
  (`app.py:6313-6332`) → `SessionSwitcher.set_digests` (`ui/session_switcher.py:667`), grouped
  by local recency (`:698-702`). `GatewayClient.list_runs` exists (`gateway/client.py:492`) but
  nothing in the package calls it.
- **Speed is argued in comments, but only for the digest, and it is not a cache.**
  `core/session_store.py:3-5` calls the snapshot "a convenience for fast app startup and UX
  continuity" with "the runtime [as] the source of truth", and `core/session_digest.py:1-14`
  justifies a local read at 42 ms for 74 chats. A cache would be filled from the source and
  invalidated against it. This one is written by the client as turns happen
  (`LLMManager.append_message`, `core/llm_manager.py:568-602`) and is never compared with the
  gateway's session list; no code path adds, drops or corrects a row from gateway state.
- **The gateway is consulted only per run, never per session list.** The transcript is replaced
  from `get_run_history_bundle` only when a worker attaches to a known run
  (`ui/gateway_worker.py:274-308` `_seed_history_from_gateway`, called at :1158/:1161), which
  happens at launch for the ACTIVE session's `last_run_id` only
  (`controller.py:1187-1220` `probe_reattach_candidate`, fired once from `app.py:6076-6095`).
  The other history-bundle reads merge attachment refs into an existing transcript
  (`core/llm_manager.py:279-361`, call at :307) or mark answered waits
  (`ui/gateway_worker.py:422-447`, call at :436); neither creates or removes a session.

AbstractCode does it the other way: its session board is `/runs?root_only=true` folded by
`session_id` (`abstractcode/tui/src/runner.rs:715` `fold_session_rows`, route pinned in
`tui/src/gateway/mod.rs:874-888`; web `web/src/workspace/catalog.ts:599`
`normalizeSessionSummaries`, route at `use_workspace_catalog.ts:91`), keeping only preferences
locally. An Assistant session therefore shows up in AbstractCode, but not the other way round.

## Consequences today (verified)

1. **Sessions created on the gateway never appear.** Anything that runs under a `session_id`
   the Assistant did not mint locally — another client of the same user (AbstractCode, Observer,
   a second Assistant install), a schedule, an Automations discussion (0852) — has no local row,
   and the list has no other source (see Why).
2. **Local rows outlive the gateway.** After a gateway purge (or a gateway-side run purge,
   `abstractgateway/run_retention.py`) every local row and transcript still shows: the text is
   local, so it renders. What lived on the gateway does not: attachment and media previews
   backed by gateway artifacts, and the per-run workspace folders, which live under the gateway
   data dir (`abstractgateway/data_homes.py:120`, `<data>/workspaces`) and are deleted with it.
   `probe_reattach_candidate` swallows the 404 and returns `None` (`controller.py:1200-1203`),
   so nothing tells the user the session's runs are gone. This matches the operator's "old
   sessions, but not fully".
3. **The local transcript can lose what the gateway kept, and is only repaired in one case.**
   The user turn is written locally before `start_run` (`ui/gateway_worker.py:1173-1187`), the
   answer only when the run's events arrive. A quit or crash mid-run leaves a transcript ending on
   the user; the answer is pulled back at next launch only if that session is still the active
   one, its `last_run_id` was stored (`:1236`, after `start_run` returns), the gateway answers
   during bootstrap (no retry), and a still-running run is not older than 600 s
   (`controller.py:1213-1216`). Every other session keeps the gap forever: switching sessions
   reads the local file only (`core/llm_manager.py:507-515`) plus the attachment merge. Worse, an
   unreadable `session.json` is silently replaced by an empty one (`SessionStore.load` returns
   `None` on any parse error, `core/session_store.py:78-90`; `_load_gateway_snapshot` then saves
   an empty snapshot, `core/llm_manager.py:156-168`), while the gateway still holds every turn.
4. **Two devices diverge.** Each install mints its own ids and keeps its own index
   (`core/session_index.py:191-216`); the same user on two Macs against one gateway sees two
   disjoint lists, and a rename (`update_title`, `:167-189`) exists on one machine only.
5. **The framework uninstall purge does not touch the Assistant's store.** The Assistant's data
   dir is `~/.abstractassistant` (`controller.py:179`, `core/llm_manager.py:82`; no CLI or env
   override — `cli.py:233`, `cli.py:425`, `macos_entry.py:51` all pass `data_dir=None`). The
   framework's `install.sh --uninstall --purge` deletes only the gateway data dir
   (`abstractframework/scripts/install.sh:351-352` for its location, `:501-509` for the
   `rm -rf "$DATA_DIR"`). So a purge + reinstall starts a fresh gateway under the old Assistant
   index — consequence 2 on every reinstall. (`~/.abstractassistant` also holds
   `gateway_connection.json` and `preferences.json`, `controller.py:180`, `:189`.)
6. **Deleting a session's folder hides runs that still exist.** `_load_or_bootstrap` drops any
   record whose directory is missing (`core/session_index.py:290-297`); the runs remain on the
   gateway, unreachable from the Assistant.

## Scope

### In scope

1. **Session list = gateway root runs folded by `session_id`.** `GET /api/gateway/runs` with
   `root_only=true&include_ledger_len=false`, paged to completion with `offset` / `has_more`
   (the route refuses unknown query parameters with a 400, `abstractgateway/routes/gateway.py:
   8535-8567`, so the exact query string is pinned by a test, as AbstractCode pins
   `session_listing_path`). Fold rules and fixtures are AbstractCode's, not re-invented: one row
   per `session_id`; runs without one are not sessions; child runs excluded; recency from
   `updated_at` (fallback `created_at`); state as the liveliest run (waiting > running >
   failed/cancelled > completed; unknown status is unknown, never "done"); turn count = root
   runs in the session; `has_more` absent means truncated. Synthetic `session_memory_*` runs
   (`gateway/generated_media.py:10-13`) are not turns. Reuse the web fold's fixture cases;
   where abstractuic already vendors a gateway-rows fixture (checked by the root
   `scripts/check_identity_sync.py`), vendor it byte-identical rather than writing look-alikes.
2. **`session_kind` when the gateway ships it** (framework 0928, contracts C11): regular list =
   `chat` + `discussion`, sent as a filter only once the gateway advertises it — today it would
   400. Automation and occurrence sessions are 0852's section, never regular rows. Never infer a
   kind from an id prefix.
3. **Titles.** Default title = the first user turn of the session, read server-side (the oldest
   root run's prompt via its history bundle, or the session history bloc route), fetched in
   bounded batches for the visible rows as AbstractCode does (`SESSION_PROMPT_MAX` / `_BATCH`,
   `runner.rs:700-703`). A local label override (rename) is kept per `session_id` in the cache
   and shown instead when present; "Untitled session" only when the gateway has no prompt.
4. **Transcripts from the gateway.** Opening a session renders from
   `GET /runs/{run_id}/history_bundle` (`include_session=true`) or
   `GET /sessions/{session_id}/history/bloc` (`routes/gateway.py:9377`, `:9452`), through the
   existing `seed_messages_from_history_bundle` (`ui/gateway_worker.py:29`, `:287`). The local
   snapshot may be shown first for speed, then replaced when the gateway answer differs — the
   replacement path already exists (`replace_gateway_messages`, `core/llm_manager.py:222-250`).
5. **Local files become a cache.** Keyed by gateway run ids (the newest root `run_id` the cache
   was built from, per session); a mismatch with the gateway row rebuilds that entry; an
   unreadable entry is rebuilt from the gateway, never overwritten with an empty transcript;
   the whole cache is deletable at any time with no loss beyond local labels. `workspace_root`
   is read back from the gateway run (it is already recovered from the run today,
   `_remember_workspace_root`, `ui/gateway_worker.py:1240`), not trusted from the cache alone.
6. **A new chat before its first turn** is a local draft row marked as such, not a gateway
   session; it becomes a gateway session when its first run starts.
7. **Offline.** When the gateway cannot be reached, show the cached rows marked stale (one
   visible notice, not per row), allow reading cached transcripts, and refuse to send. The list
   read runs off the GUI thread with a short timeout (the 0851 rule); the switcher opens on the
   cached rows and updates when the gateway answers.
8. **One-time migration of existing local sessions.** On first launch of the new version, for
   each local `sess_*` record ask the gateway for that `session_id`: keep rows that resolve
   (carrying their rename as the local label), drop the rest, and say so once ("N local sessions
   were not found on this gateway and were removed from the list"). The dropped transcripts are
   moved aside, not deleted, for one release. The legacy base session (`path == "."`,
   `core/session_index.py:317-339`) is migrated by the same rule.

### Out of scope

- Any gateway change (routes, `session_kind`, a sessions route). Gaps are raised to the gateway
  seat, not worked around.
- Making the framework uninstall purge `~/.abstractassistant` — that is the framework repo's fix;
  with this item the Assistant stays correct either way.
- Automations surfaces (0852).

## Current code reality (verified at 481b2df, 0.6.1)

- Index and record: `core/session_index.py:1-10` (era docstring), `:47-84` `SessionRecord`
  (`session_id, actor_id, title, path, created_at, updated_at`), `:87` `SessionIndex`,
  `:120-122` `records()`, `:167-189` `update_title`, `:191-216` `create_session`
  (`sess_<uuid>`, `<data_dir>/sessions/<id>/`), `:218-255` `delete_session`,
  `:257-309` `_load_or_bootstrap` (drops records with missing dirs at :290-297),
  `:317-339` legacy base session.
- Snapshot: `core/session_store.py:19-67` `SessionSnapshot` (`messages`, `last_run_id`,
  `workspace_root`), `:78-90` `load` returns `None` on any error.
- Digest: `core/session_digest.py:1-14` ("computed from local files only … never a gateway
  call"), `:62` `SessionDigest`.
- Manager: `core/llm_manager.py:82-83` data dir + index, `:156-168` empty-snapshot overwrite,
  `:222-250` `replace_gateway_messages`, `:279-361` attachment backfill (history bundle at
  :307), `:433-479` `list_sessions` / `session_digests`, `:507-515` `switch_session`,
  `:536-566` local fallback title, `:568-602` `append_message`.
- Controller: `controller.py:179` `~/.abstractassistant`, `:961-997` session facade,
  `:1187-1220` `probe_reattach_candidate`.
- App: `app.py:6076-6095` bootstrap probe, `:6231-6249` `_session_records`, `:6289-6303`
  `_warm_session_digests` (synchronous, local), `:6313-6332` `_open_session_switcher`,
  `:6348` `_switch_to_session`.
- Switcher: `ui/session_switcher.py:570` `SessionSwitcher`, `:667` `set_digests`,
  `:698-702` recency grouping.
- Worker: `ui/gateway_worker.py:274-308` history re-seed, `:422-447` answered-wait
  suppression, `:1136` session id from the local index, `:1173-1187` local user turn before
  start, `:1216` `session_id` sent with the run, `:1236` `last_run_id` stored.
- Client: `gateway/client.py:492-500` `list_runs` (unused), `:502-528` `get_run_history_bundle`.
  No call to `/sessions/{id}/history/bloc`; no `session_kind` anywhere in the package.

## Seams

- **abstractgateway** — `GET /api/gateway/runs` (`routes/gateway.py:8535`, params at
  :8555-8558), `GET /runs/{run_id}/history_bundle` (:9377), `GET /sessions/{session_id}/history/bloc`
  (:9452). `session_kind` on `/runs` rows and as a filter is owned by gateway 0928 (C11) and is
  NOT live at the time of writing — the client gates on it; it does not send it blind.
- **abstractcode** — reference fold: `tui/src/runner.rs:715` `fold_session_rows` (tests from
  :4783), `tui/src/gateway/mod.rs:874` pinned listing path, `web/src/workspace/catalog.ts:599`
  `normalizeSessionSummaries`. Read them before implementing; divergence from them is a bug in
  one of the three.
- **abstractuic** — shared fixtures, if/when the session-row fixture is vendored there.
- **abstractframework** — the uninstall purge (`scripts/install.sh:501-509`).

## Validation

- A session created through the gateway by another client (fake transport: a `/runs` page with
  a `session_id` this install never minted) appears in the switcher with its first prompt as
  title. Remove the fold call → RED.
- Purging the local cache (delete `~/.abstractassistant/sessions*` in a scratch `HOME`) loses
  nothing: the same rows, titles and transcripts come back from the gateway; only local labels
  are gone.
- A local row whose runs are absent from the gateway is dropped by the migration with one
  notice; a row that resolves keeps its rename.
- An unreadable cached `session.json` is rebuilt from the gateway, not replaced by an empty one.
- Offline: cached rows shown once-marked stale; nothing blocks the GUI thread longer than the
  settings timeout of 0851.
- The pinned `/runs` query string test (a renamed parameter must fail the suite, not degrade).
- `tests/basic/test_session_switch_overlap.py` (0.6.0 switch-overlap fix) and
  `tests/basic/test_session_switcher.py` still pass.
- Tests never reach the operator's live gateway (unset the admin token; fake transport; scratch
  `HOME`).

## Dependencies

- None to start: `/runs?root_only=true`, the history bundle and the history bloc route are live.
- `session_kind` filtering waits for gateway 0928 (C11); 0852 builds its regular/automation
  split on this item.

## Implementation (2026-09-27, unreleased)
Commits 8006dcd + 524978f on main (local): `core/gateway_sessions.py` (fold like AbstractCode's web fold: skip child/id-less runs, newest
first by `updated_at`, liveliest state, page without `has_more:false` = truncated), `core/session_cache.py` replaces `session_index.py`
(cache keyed by gateway session id; hashed folder for unsafe ids; `remove_from_list` MOVES text to `sessions-legacy/`; hidden ids;
`show_all` toggle; `session.unreadable.json` marker), `gateway/client.py` pins `/api/gateway/runs?limit=5000&root_only=true&include_ledger_len=false`,
one-time resumable migration (cache written BEFORE the legacy index is set aside; orphans moved to `sessions-legacy/` after the first
complete list, one notice), own sessions by default (`sess_` prefix = this client's own naming; the gateway's `session_kind` replaces it,
framework 0928/C11) with an "All gateway sessions" toggle, offline marker, follow-up sync after a quick switch, switcher grows as rows land.
Suite 933. Reviews 37 and 39 (framework untracked/missions-2026-09-25/REVIEW/37-…md): GO; migration lost nothing under SIGKILL at five
points and the 0.6.1↔0.6.2 round trip. Deployed on the operator's machine 2026-09-27 08:25 CEST from the checkout (backup
`~/.abstractassistant.bak-2026-09-27`; migration moved 16 entries to `sessions-legacy/`). Ships in the next Assistant release.
Follow-ups: `sessions-legacy/` grows with each removal (FAQ line); abstractcode 0002 (TUI fold defects found by the comparison).
