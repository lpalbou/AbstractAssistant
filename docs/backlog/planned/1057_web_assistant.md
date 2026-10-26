# 1057 — The Assistant on the web

> Package: abstractassistant (web/)
> Type: feature
> Created: 2026-10-26
> Status: Planned
> Completed: N/A
> Priority: P1
> Labels: web, gateway-app, voice, host-agnostic
> Governing ADR: [ADR 0007](../../adr/0007_web_assistant.md) (Proposed), [ADR 0001](../../adr/0001_gateway_native_assistant_v2.md)

## Current code reality

- `web/` holds a scaffold (2026-10-26, W3): Vite + React + TypeScript; `bin/server.js` (abstractuic
  app-server: mount under `/apps/assistant-web/`, gateway session proxy, abstractcode's guards);
  `src/host/` (the host interface and the browser host); `src/gateway/` (client, SSE over fetch,
  the stack follower); `src/lib/` (session fold, workflow choice, run input, turn reducer,
  history, voice) and a first Assistant space in `src/ui/`. `npm test` 58 tests, `npm run build`
  green; the fold, the follower and the reducer were run read-only against the local gateway
  (evidence: `untracked/apple-web-wave/w3-web-architecture.md`).
- `web/design/` (W4) holds the design tokens; the scaffold consumes them, the orb is not built.
- The gateway's app catalog does not list this app (`abstractgateway/src/abstractgateway/apps_manager.py:150-158`),
  so it cannot be installed or opened signed in from the console yet. It runs by hand
  (`web/README.md`).
- Nothing was sent to a live gateway (no run started, no wait answered): sending, approving,
  answering, read aloud and dictation are unproven end to end.

## Scope and expected outcome

A person opens **Assistant (web)** from the gateway console, or a bookmark of
`<gateway>/apps/assistant-web/`, on any computer or phone that reaches the gateway, and talks with
the same Assistant, in the same conversations, as on the desktop, the iPhone and the watch. No
token in the browser, no copy of a conversation in the browser, no workflow installed by the page.

## Phases

| # | What | Owner | Size |
|---|---|---|---|
| 0 | ADR 0007 accepted (or amended) by the operator; the catalog id, port and display name decided | operator + assistant | S |
| 1 | **Live v1 proof on a local gateway, by the operator or with their go-ahead (runs cost tokens):** send, streamed answer, stop, a tool approval on a child run, an `ask_user`, an answer from another device closing the card, attachments, read aloud, dictation on `http://127.0.0.1`; fix what breaks. Decide here whether panel-chat's `WorkflowSessionController` passes `src/lib/run_events.test.ts` (adopt it and delete the reducer) or not | assistant (+ uic for the controller) | M |
| 2 | **Gateway catalog row** (ask G1 below) and the npm package `@abstractframework/assistant` published (drop `private`), installable and openable signed in from the console | gateway + assistant | M |
| 3 | v1.1: the orb (W4 design) on the same voice flows, hands-free turn; generated media and attachment previews in the conversation (`runs/{id}/artifacts/{id}/content`); "load more" conversations; rename and archive | assistant | L |
| 4 | Browser tests: Playwright smoke against a fake gateway (as abstractcode/web/e2e), the relative-URL check in CI, `npm ci` from the lock file | assistant | M |
| 5 | v2 Inbox (open waits across conversations and automations, the `attention.raised` − `attention.seen` fold) and Automations (ui-kit `AutomationPanel`) | assistant + uic | L |
| 6 | v2 web push while the tab is closed (ask G2) | gateway + assistant | L |
| 7 | The desktop host: ADR 0008 (Tauri 2 shell around this frontend) implements `web/src/host/types.ts`; out of this item once 0008 has its own | lead + assistant | — |

## Asks to other seats

- **G1 (gateway):** an `AppSpec` for `assistant-web` (package `@abstractframework/assistant`, cookie
  prefix `abstractassistant`, title `AbstractAssistant`, port 3008, `--gateway-url`/`--port`/`--host`
  flags so `FLAG_CONFIGURED_APPS`), the port in the stack map (framework `scripts/start-local.sh`
  too: framework seat), and the console's wording for the two Assistant rows (desktop and web).
- **G2 (gateway, v2):** Web Push for the person's event stream (VAPID keys, a
  `me/push/devices` kind for browsers), as Apple push exists (`abstractgateway/docs/push.md`).
- **G3 (gateway, optional):** confirm that `detail=replay` history bundles keep
  `session.turns[].attachments` and `answer` as a contract (read on the local gateway, not documented
  as such in `api.md:1751-1754`).
- **U1 (uic):** move abstractcode's three server guards (same-origin mutations, JSON sign-in,
  DNS-rebinding guard) into `@abstractframework/app-server`, so the web Assistant and the other
  apps stop copying `bin/server.js` code.
- **A1 (assistant, packaging):** `prune web` in `MANIFEST.in` (belt: today neither the wheel nor
  the sdist includes `web/`, proven by a build from a copy with `web/node_modules`).
- **A2 (assistant, desktop):** overview item 0 (stop publishing the managed workflow from the
  desktop): the web client only checks presence and fails loudly, so the workflow must reach the
  gateway without a desktop having run.

## Validation

- `cd web && npm install && npm test && npm run build`; the fold test reads
  `tests/basic/fixtures/gateway_runs/`, the run-input test reads cases produced by
  `PYTHONPATH=. python -P web/scripts/gen_run_input_parity.py`. Each guard was mutation-checked
  (subworkflow key, resume clearing, child-run exclusion, top-level override, late deltas, rooted
  URL).
- Phase 1 evidence under `docs/backlog/evidence/1057/` (screens and the ledger ids of the runs used).

## ADR state

ADR 0007 Proposed. ADR 0001 applies unchanged (the gateway owns workflows, defaults and history).
