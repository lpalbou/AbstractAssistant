# API And CLI Reference

AbstractAssistant is primarily a desktop app and CLI. Its stable public surface is the user
entrypoints plus the gateway-facing behavior they rely on.

See also:

- [getting-started.md](getting-started.md)
- [architecture.md](architecture.md)
- [troubleshooting.md](troubleshooting.md)

## CLI Entry Points

From `pyproject.toml`:

- `assistant`
- `abstractassistant`

Help:

```bash
assistant --help
assistant run --help
```

## Global Flags

The assistant resolves gateway connection settings from global flags first, then environment:

- `--gateway-url URL`
- `--gateway-token TOKEN`

Global flags must appear before a subcommand.

Example:

```bash
assistant --gateway-url http://127.0.0.1:9090 --gateway-token "$ABSTRACTGATEWAY_AUTH_TOKEN" run --prompt "Search the web for the latest AI news and summarize it with sources."
```

## `assistant`

With no subcommand, `assistant` starts the tray and palette UI.

Behavior:

- loads local session state from `~/.abstractassistant/`
- connects to the configured gateway
- resolves the published `abstractassistant-orchestrator` workflow from the gateway workflow catalog
- reads and edits gateway capability defaults for multimodal routes

## `assistant run`

`assistant run --prompt TEXT` executes one terminal turn through the gateway.

Example:

```bash
assistant run --prompt "Search the web for the latest OpenAI news and summarize it with sources."
```

Behavior:

- the assistant run path comes from the published `abstractassistant-orchestrator` workflow
- provider/model defaults are left to the gateway unless you change them on the gateway side
- tool approvals are surfaced interactively in the terminal

## Environment Variables

The desktop client uses these connection settings:

- `ABSTRACTGATEWAY_URL`
- `ABSTRACTFLOW_GATEWAY_URL`
- `ABSTRACTGATEWAY_AUTH_TOKEN`
- `ABSTRACTFLOW_GATEWAY_AUTH_TOKEN`

If no URL is provided, the assistant defaults to `http://127.0.0.1:8080`.

## Gateway Routes Used By The Assistant

The assistant is a thin client over these gateway surfaces:

- `/api/gateway/workflow-catalog`
- `/api/gateway/visualflows`
- `/api/gateway/visualflows/{flow_id}/publish`
- `/api/gateway/admin/workflow-catalog/promote`
- `/api/gateway/config/capability-defaults`
- `/api/gateway/discovery/capabilities`
- `/api/gateway/discovery/providers`
- `/api/gateway/discovery/providers/{provider}/models`
- `/api/gateway/audio/speech/models`
- `/api/gateway/audio/transcriptions/models`
- `/api/gateway/voice/voices`
- `/api/gateway/vision/provider_models`
- `/api/gateway/vision/adapters`
- `/api/gateway/audio/music/providers`
- `/api/gateway/audio/music/models`
- `/api/gateway/runs/start`
- `/api/gateway/runs/{run_id}/history_bundle`
- `/api/gateway/runs/{run_id}/ledger/stream`
- run-scoped media execution used by the published assistant workflow

For multimodal routes, the assistant client forwards Gateway/Core
fields such as `count`, `n`, `seeds`, `lora_adapters`, `guidance_2`, and
`flow_shift` instead of inventing a separate assistant-only request shape.

## Python API Status

This repository still contains internal Python modules such as the gateway client, session stores,
voice manager, and worker threads. They are implementation surfaces for the desktop app, not yet a
committed public embedding API.

If you want to automate the assistant, prefer:

- the CLI for user-style invocation
- AbstractGateway directly for durable workflow execution

## Related Docs

- [architecture.md](architecture.md)
- [faq.md](faq.md)
- [troubleshooting.md](troubleshooting.md)
