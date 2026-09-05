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

- `--gateway-url URL`
- `--gateway-token TOKEN`
- `--version`

```bash
assistant --gateway-url http://127.0.0.1:9090 --gateway-token "$ABSTRACTGATEWAY_AUTH_TOKEN" run --prompt "Summarize today's AI news with sources."
```

## `assistant`

Starts the menu-bar app and palette. It loads local state from `~/.abstractassistant/`, connects
to the gateway, resolves the published `abstractassistant-orchestrator` workflow and follows runs
over SSE.

## `assistant run --prompt TEXT`

Executes one turn in the terminal through the same published workflow. Tool approvals are asked
interactively. The turn honors the same local overrides as the tray: chat model pin, media pins,
reasoning effort and workspace grant from `preferences.json`.

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
- `sessions.json`, `sessions/<id>/session.json` — chat registry, transcript snapshot, last run id,
  granted workspace root
- `downloads/`, `gateway_audio/` — downloaded artifacts and cached speech audio

## Run input pins

Each run carries only what the user chose locally; blank values are omitted so the gateway
default applies:

| Pin | Source |
|---|---|
| `provider`, `model`, `base_url` and `_runtime.provider/model/base_url` | chat model override |
| `_runtime.thinking` | reasoning effort |
| `workspace_root`, `workspace_access_mode`, `workspace_allowed_paths` | workspace settings (or the chat's remembered root) |
| `image_provider/image_model`, `image_edit_*`, `image_upscale_*`, `video_*`, `image_to_video_*`, `music_*`, `sound_output` | media route overrides |
| `_runtime.allowed_tools`, `_runtime.tool_policy` | per-tool modes (Off / Auto / Ask) |
| `system` | the workflow's base prompt plus an addendum (voice conversation) when one applies |

## Gateway routes used

- Workflow: `/api/gateway/workflow-catalog`, `/api/gateway/visualflows`,
  `/api/gateway/visualflows/{flow_id}/publish`, `/api/gateway/admin/workflow-catalog/promote`
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
  attachments: `/api/gateway/sessions/{session_id}/attachments`
- Artifacts: `/api/gateway/runs/{run_id}/artifacts`, artifact metadata and content download

## Python API status

The Python modules (gateway client, controller, session stores, voice manager, workers, UI) are
implementation surfaces for the desktop app, not a committed public embedding API. To automate the
assistant, use the CLI, or AbstractGateway directly for durable workflow execution.
