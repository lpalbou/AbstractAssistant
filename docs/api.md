# API And CLI Reference

AbstractAssistant is a desktop app and a CLI. Its stable public surface is the user entry points,
the local files they maintain, and the gateway routes they rely on.

See also:

- [getting-started.md](getting-started.md)
- [settings.md](settings.md)
- [architecture.md](architecture.md)
- [troubleshooting.md](troubleshooting.md)

## CLI entry points

From `pyproject.toml`: `assistant`, `abstractassistant` (same program) and `build-macos-app`.

```bash
assistant --help
assistant run --help
```

## Global flags

Connection settings resolve from global flags first, then the environment. Global flags must
appear before a subcommand.

- `--gateway-url URL` — the gateway to use. Without `--gateway-token`, the sign-in saved for that
  gateway in `gateway_connection.json` is used.
- `--gateway-token TOKEN`
- `--gateway-handover-file PATH` — set by the AbstractGateway console when you click **Open** on
  the assistant's card. The file holds a one-time sign-in code (valid once, for two minutes); the
  app reads it, deletes it, trades the code with the gateway for a session and saves that
  session. You do not pass this flag yourself. Only a file the gateway wrote is accepted (a
  regular file you own, mode 0600, in the gateway's hand-over format, naming the gateway user who
  clicked **Open**); any other path, or a file that does not name the user, is refused and left
  untouched. If you are already signed in to that gateway as that same user, that sign-in is
  kept; a sign-in to another gateway or as another user is signed out and replaced, and the app
  tells you who is signed in and who was signed out. An Assistant that is already running does not
  receive a hand-over: quit it and click **Open** again. The flow is drawn in
  [architecture.md](architecture.md#auth-boundary).
- `--version` — prints the version from `abstractassistant/_version.py`, the same value
  Settings → About and the macOS app bundle show.

```bash
assistant --gateway-url http://127.0.0.1:9090 --gateway-token "$ABSTRACTGATEWAY_AUTH_TOKEN" run --prompt "Summarize today's AI news with sources."
```

## `assistant`

Starts the menu-bar app and palette. It loads local state from `~/.abstractassistant/`, connects
to the gateway, resolves the workflow chosen in Settings → Models → Workflow and follows runs over
SSE.

Workflow resolution:

- **Gateway default** (the default choice): when the gateway reports a default workflow for
  `abstractassistant.agent.v1` (`default_agent_workflows` on `/api/gateway/workflow-catalog`),
  each run starts with `flow_id: "@default"` and `interface: "abstractassistant.agent.v1"`, and the
  gateway resolves it at run start. When it reports none, the built-in
  `abstractassistant-orchestrator` workflow runs, and Settings shows the gateway's reason. The app
  publishes that workflow to the tenant catalog with explicit versions (the first is 0.0.1) and
  labels it without a number until one exists. When
  neither is available, sending is blocked with a message saying why; the app never picks another
  workflow on its own.
- **A chosen workflow** runs its latest published version. If it is removed from the catalog,
  sending is blocked with a message naming it until you pick another one.

The gateway's `resolved_workflow` for the last run start is shown in Settings → About.

## `assistant run --prompt TEXT`

Executes one turn in the terminal through the same workflow choice as the tray. Tool approvals are asked
interactively. The turn honors the same local overrides as the tray: chat model pin, media pins,
reasoning effort, reply streaming and workspace grant from `preferences.json`.

`--stream on|off` overrides the saved **Stream replies** choice for this turn. `off` is always
sent; `on` is sent only to a gateway that advertises live replies, otherwise a bracketed line on
stderr says it was not sent. While the reply
streams, its text is written to **stderr** as it arrives (the model's reasoning is not printed), a
line in brackets says when a step could not stream or its live text was discarded, and the final
answer is printed once on **stdout** — so `assistant run --prompt … > answer.txt` captures only the
answer. Without a saved sign-in or
`--gateway-token`, a gateway that requires sign-in answers 401; the command then prints how to
sign in (open the Assistant from the gateway console, connect once in Settings → Connection, or
pass `--gateway-token`) and exits with status 2.

## Environment variables

- `ABSTRACTGATEWAY_URL` / `ABSTRACTFLOW_GATEWAY_URL` — gateway base URL (default
  `http://127.0.0.1:8080`)
- `ABSTRACTGATEWAY_AUTH_TOKEN` / `ABSTRACTFLOW_GATEWAY_AUTH_TOKEN` — bearer token
- `ABSTRACTASSISTANT_GATEWAY_TTS_MODEL`, `ABSTRACTASSISTANT_GATEWAY_TTS_PROVIDER`,
  `ABSTRACTASSISTANT_GATEWAY_TTS_VOICE`, `ABSTRACTASSISTANT_GATEWAY_STT_MODEL`,
  `ABSTRACTASSISTANT_GATEWAY_STT_PROVIDER` — optional speech engine pins for environments without
  the Settings window

## Local files

All under `~/.abstractassistant/`:

- `preferences.json` — local overrides and UI preferences (reference in
  [settings.md](settings.md#preferences-file))
- `gateway_connection.json` — gateway URL, sign-in mode, token or session state
- `session_cache.json`, `sessions/<id>/session.json` — the rebuildable session cache: active
  session, local labels, fetched titles, the last gateway list, cached transcripts, last run id,
  granted workspace root ([architecture.md](architecture.md#sessions))
- `sessions-legacy/` — files kept from the 0.6.1-and-earlier local session index and unreadable cache files
- `automations_notified.json` — which automation results, failures and waits were already
  shown as a tray notification, so a relaunch does not repeat them
  ([automations.md](automations.md#notifications-and-the-two-polls)). Deleting it can repeat
  notifications for items still unseen on the gateway; nothing else is lost.
- `downloads/`, `gateway_audio/` — downloaded artifacts and cached speech audio

## Run input pins

Each run carries only what the user chose locally; blank values are omitted so the gateway
default applies:

| Pin | Source |
|---|---|
| `provider`, `model`, `base_url` and `_runtime.provider/model/base_url` | chat model override |
| `_runtime.thinking` | reasoning effort |
| `_runtime.speculation` | MTP depth: `false` for Off, `{"mode": "native_mtp", "num_draft_tokens": N, "require_acceleration": true}` for a depth; omitted to follow the gateway default |
| `_runtime.stream` | Stream replies: `false` for Off (always sent); `true` for On, sent only when `/discovery/capabilities` advertises `streaming.deltas: true`; omitted to follow the gateway's streaming default (`streaming.default`) |
| `workspace_root`, `workspace_access_mode`, `workspace_allowed_paths` | workspace settings (or the chat's remembered root) |
| `image_provider/image_model`, `image_edit_*`, `image_upscale_*`, `video_*`, `image_to_video_*`, `music_*`, `sound_output` | media route overrides |
| `_runtime.allowed_tools`, `_runtime.tool_policy` | per-tool modes (Off / Auto / Ask) |
| `system` | the workflow's base prompt plus an addendum (voice conversation) when one applies |

## Live reply events

The run stream (`/api/gateway/runs/{run_id}/ledger/stream`) carries, next to the durable `step`
events, two live events with no `id:` line: `llm.delta`
(`call_id`, `seq`, `text`, `channel` = `content` | `reasoning`, `snapshot`, `truncated`, `run_id`,
`root_run_id`, `parent_run_id`, `node_id`) and `llm.delta_end` (`call_id`, `seq`, `reason` =
`completed` | `failed` | `cancelled` | `unavailable`, `detail`; `cancelled` with `detail: "reinvoked"`
means the call is being run again under the call id `<step_id>:reinvoke`). The app resumes the stream only
from the cursor of durable `step` events, so live events never move it. On every (re)connect it drops
its live text and applies the snapshots the gateway re-sends; it ignores deltas for a call whose
durable `llm_call` record it already holds, and never shows live text again once the final answer
is on screen. A malformed live frame is skipped (reported once per connection) and never ends
the stream. Whether the gateway offers live replies is read from
`/discovery/capabilities` → `streaming.deltas`.

## Gateway routes used

- Sign-in and identity: `/api/gateway/apps/desktop-handover` (console hand-over, loopback),
  `/api/gateway/session/login`, `/api/gateway/session/logout`, `/api/gateway/about` (version rows
  for Settings → About; `/api/gateway/discovery/capabilities` is read when it is absent)
- Workflow: `/api/gateway/workflow-catalog`, `/api/gateway/visualflows`,
  `/api/gateway/visualflows/{flow_id}/publish`, `/api/gateway/admin/workflow-catalog/promote`
- Sessions: `GET /api/gateway/runs?limit=200&offset=N&root_only=true&include_ledger_len=false`
  pages (the session list, 100 sessions at a time; `&session_kind=chat,discussion` is added when
  the gateway lists `session_kind` among `runs.list.filters` in its capabilities); titles come from a session's first run's
  `input_data` and transcripts from its latest run's `history_bundle`
  ([architecture.md](architecture.md#sessions))
- Runs: `/api/gateway/runs/start`, `/api/gateway/runs/{run_id}`,
  `/api/gateway/runs/{run_id}/input_data`, `/api/gateway/runs/{run_id}/history_bundle`,
  `/api/gateway/runs/{run_id}/ledger`, `/api/gateway/runs/{run_id}/ledger/stream`,
  `/api/gateway/commands` (pause, resume, cancel, inject_guidance, resume of waits)
- Discovery and configuration (read): `/api/gateway/me`, `/api/gateway/discovery/capabilities`,
  `/api/gateway/discovery/providers`, `/api/gateway/discovery/providers/{provider}/models`,
  `/api/gateway/discovery/models/capabilities`, `/api/gateway/discovery/tools`,
  `/api/gateway/config/capability-defaults`, `/api/gateway/workspace/policy`,
  `/api/gateway/workspace/policy/self`
- Speech and media catalogs: `/api/gateway/audio/speech/models`,
  `/api/gateway/audio/transcriptions/models`, `/api/gateway/voice/voices`,
  `/api/gateway/vision/provider_models`, `/api/gateway/vision/adapters`,
  `/api/gateway/audio/music/providers`, `/api/gateway/audio/music/models`
- Speech execution: run-scoped `voice/tts`, `voice/tts/stream` and `audio/transcribe` routes;
  attachments: `/api/gateway/attachments/upload`
- Artifacts: `/api/gateway/runs/{run_id}/artifacts`, artifact metadata and content download
- Automations ([automations.md](automations.md)), used only when the capabilities advertise
  `contracts.common.automations.available: true`:
  - `GET /api/gateway/automations` (every page, following `next_cursor`) and
    `POST /api/gateway/automations` (create, with a `request_id`; the Schedule window sends
    `title`, `target` with the task as `input_data.prompt`, a `schedule@1` trigger, `context.mode`
    and `policy.tool_approval` = `auto` | `ask`)
  - `GET /api/gateway/automations/{id}` and `PATCH /api/gateway/automations/{id}` (edit: the
    changed fields among `title`, `trigger` and `context`, with `expected_revision` and
    `command_id`; the Assistant never sends `target` or `policy`, which only a direct `PATCH`
    changes)
  - `POST …/{id}/commands` (`automation.pause`, `automation.resume`, `automation.run_now`,
    `automation.stop_current`, `automation.archive`)
  - `GET …/{id}/occurrences` (runs, newest first), `GET …/{id}/attention` (unseen items),
    `POST …/{id}/seen` (the last displayed item's cursor), `POST …/{id}/discuss`
    (`occurrence_index`, `prompt`)
  - `GET /api/gateway/trigger-sources` (the Schedule window requires `schedule` version 1)

  Every refusal is read from the `detail.reason_code` envelope. A waiting run of an automation is
  answered with the `resume` command on `/api/gateway/commands`, whose payload follows the wait's
  kind: `{"response": text}` for `ask_user`, `{"approved": true|false}` for `tool_approval`,
  `{"payload": <JSON>}` for `event`.

## Python API status

The Python modules (gateway client, controller, session stores, voice manager, workers, UI) are
implementation surfaces for the desktop app, not a committed public embedding API. To automate the
assistant, use the CLI, or AbstractGateway directly for durable workflow execution.
