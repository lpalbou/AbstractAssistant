# Gateway-first AbstractAssistant (design draft)

## Goal

Make AbstractAssistant a **gateway-first thin client** while preserving a tray UX.
All execution remains in AbstractGateway (local or remote). The tray UI renders by
**ledger replay + SSE streaming** and resumes waits via **durable commands**, just
like `abstractcode/web`.

## Reference implementation

- `abstractcode/web` is the authoritative thin-client example:
  - `web/src/lib/gateway_client.ts` — gateway HTTP/SSE client
  - `web/src/ui/app.tsx` — ledger replay + wait resolution
- Shared UI components live in `abstractuic/` and should be reused in any web UI.

## Why this design

- Demonstrates the gateway as the **single durable runtime**.
- Enables **AbstractFlow workflows** in the tray app without local execution.
- Supports **local-first** when the gateway runs on-device (no network needed).
- Supports **cross-device continuity** when the gateway is remote.

## Architecture (target)

```
Tray UI (Qt) or Web UI (abstractuic)
  -> GatewayClient (HTTP + SSE)
    -> AbstractGateway (/api/gateway/*)
      -> AbstractRuntime (durable runs, ledger, waits)
```

### Client loop (same as abstractcode/web)

1) Start a run (`POST /api/gateway/runs/start`)
2) Replay ledger (`GET /api/gateway/runs/{id}/ledger`)
3) Stream ledger (`GET /api/gateway/runs/{id}/ledger/stream`)
4) Resolve waits with commands (`POST /api/gateway/commands`)

## Phased delivery

### Phase 1 — Python client + adapter (Qt stays)

- Implement a Python `GatewayClient` matching `abstractcode/web` endpoints.
- Implement a **ledger event adapter** that maps `emit_event` + flow outputs to
  the existing AbstractAssistant UI event shape:
  - `status`, `assistant`, `tool_request`, `tool_result`, `ask_user`, `error`
- Use the adapter to drive the Qt bubble **without** a local runtime.

### Phase 2 — Optional web UI in tray

- Introduce a WebView/Electron/Tauri host if we want a unified UI stack.
- Reuse `abstractuic/` components and `abstractcode/web` logic directly.

## Cross-platform tray note

- **Qt (current)**: macOS-first; can be extended to Linux/Windows but with native
  packaging + QA overhead.
- **Electron/Tauri**: easier cross-platform tray support and direct reuse of
  `abstractuic` components, but introduces a new runtime surface.

## Local vs remote gateway

- **Local gateway**: still local/offline if providers are local.
- **Remote gateway**: enables cross-device session continuity (shared `session_id`).

## Default workflow

- The tray uses the gateway’s declared default agent entrypoint when one is exposed.
- Workflow availability comes entirely from `list_bundles`.
- The gateway, not the tray app, must be configured to load bundles (for local dev, typically via `ABSTRACTGATEWAY_FLOWS_DIR`).

## Open decisions

- **Tray runtime**: keep Qt (Phase 1) vs migrate to web‑based tray (Phase 2).
- **Session identity**: reuse existing `session_id` file or map to gateway session IDs.
- **Voice**: prefer gateway audio endpoints; keep local voice only if explicitly enabled.

## Implementation references (do not diverge)

- SSE handling + wait resolution: `abstractcode/web/src/ui/app.tsx`
- Gateway HTTP surface: `abstractcode/web/src/lib/gateway_client.ts`
