# Architecture: AbstractAssistant for Apple Watch

The watch app follows ADR 0001 of this repository: the gateway is the authority for workflows,
runs, tools, policy and speech; the client holds a credential and a cache, and every action it
takes is a gateway request that becomes a ledger record.

```mermaid
flowchart LR
  subgraph Watch["Apple Watch (watchOS 26, standalone)"]
    UI[SwiftUI views]
    Model[AppModel\npolling · haptics · cache]
    Kit[AbstractGatewayClient\nSwift package]
    KC[(Keychain\nbase_url · token)]
    UI --> Model --> Kit
    Kit --> KC
  end
  subgraph Net["Reachability"]
    LAN[LAN http\n(development)]
    TLS[HTTPS endpoint\nTailscale Funnel · Cloudflare Tunnel · reverse proxy]
  end
  subgraph GW["AbstractGateway"]
    API[/api/gateway/*/]
    Runs[(runs · ledgers\nwaits · artifacts)]
    Auto[automations]
    Voice[run-scoped STT / TTS]
    API --> Runs
    API --> Auto
    API --> Voice
  end
  Kit -- Bearer token --> LAN --> API
  Kit -- Bearer token --> TLS --> API
  Mac[Desktop assistant · terminal · browser] --> API
```

The desktop assistant, the terminal client and the browser talk to the same gateway. A wait
answered on the watch is answered for all of them; a question asked on the watch is a run in the
same session pool.

## Components

| Component | Responsibility | Notes |
|---|---|---|
| `Sources/App` (SwiftUI) | Screens and navigation; no networking | One `NavigationStack`, screens as in `design.md` |
| `AppModel` (`@MainActor`) | Holds the client, the cached state (waits, runs, automations), the polling loop, haptics | Polls every 15 s while active; stops on 401 |
| `AbstractGatewayClient` (SwiftPM) | Typed, async `URLSession` client: models, endpoints, SSE follow, resume commands | Platforms watchOS, iOS, macOS so a future native client reuses it; tested with `swift test` on macOS |
| `MockGatewayClient` | The same protocol with canned data | Default in Debug and for screenshots |
| Keychain | `base_url`, `user_id`, token | Never logged, never exported |
| WidgetKit extension (0.2) | Smart Stack widget and corner complication | Reads a shared snapshot written by the app |
| Notification service (0.2) | Actionable approval notifications | Needs APNs and a gateway notification bridge |

## API mapping (0.1)

All calls carry `Authorization: Bearer <token>`; none use cookies or CSRF.

| Screen / action | Gateway call |
|---|---|
| Reachability, sign-in check | `GET /api/health`, `GET /api/gateway/me` |
| Waiting for you | `GET /api/gateway/runs?status=waiting` (active-run index, cheap) and `GET /api/gateway/automations` (`attention.pending_waits`) |
| Approval card | the run detail's `waiting` block: `{reason: "user", wait_key: "tool_approval:<run>:act:<hash>", details: {mode: "approval_required", tool_calls: [{name, arguments}]}}`; the list row carries only `waiting.reason`, and the approval lives on the agent's child run (the root waits on `subworkflow`) |
| Allow once / Deny | `POST /api/gateway/commands` `{command_id, run_id, type: "resume", payload: {wait_key, payload: {approved: true|false}}}` |
| Question | wait `kind: ask_user` with `prompt`, `choices`; answer `payload: {response}` |
| Ask | `POST /api/gateway/runs/start` `{flow_id: "@default", interface: "abstractcode.agent.v1", session_id?, input_data: {prompt, use_session_history: true}}` |
| Thinking | `GET /api/gateway/runs/{id}` (`status`, `waiting`, `output`) on a 2 s poll; SSE `GET /api/gateway/runs/{id}/ledger/stream?after=N` when the connection allows |
| Cancel | `POST /api/gateway/commands` `{type: "cancel"}` |
| Runs | `GET /api/gateway/runs?root_only=true&limit=20` |
| Automations, Run now | `GET /api/gateway/automations`, `POST /api/gateway/automations/{id}/commands` `{type: "automation.run_now"}`, `GET .../occurrences?limit=1`, `POST .../seen` |
| Voice (0.2) | `POST /api/gateway/attachments/upload` then `POST /api/gateway/runs/{id}/audio/transcribe`; `GET /api/gateway/runs/{id}/voice/tts/stream` |

The assistant interface `abstractassistant.agent.v1` is used when the gateway reports a default
workflow for it; otherwise the watch uses `abstractcode.agent.v1`, which every gateway serves.

Verified live on 2026-10-16 through Tailscale Funnel: the app listed a real tool approval, sent the
`resume` command, and the gateway ledger recorded it; the run completed with the tool's output.
Before answering, the client re-reads the run and refuses to send when the wait key changed
(answered elsewhere): a stale approval never resumes another step.

## Polling, push and budgets

- Foreground: waits and runs every 15 s; the thinking screen polls its run every 2 s. watchOS
  suspends the app seconds after the wrist drops, so the loop is restarted on every activation.
- Background: `WKApplicationRefreshBackgroundTask` runs at the system's discretion (typically a few
  times per hour). It refreshes the widget snapshot and posts a local notification for a new wait.
  It is best-effort and is not the plan for approvals.
- Push (0.2): approvals and failures as APNs notifications with Allow once / Deny actions. The
  gateway has no push channel today; the plan is a small notification bridge that watches
  `runs?status=waiting` and automation attention for a user and forwards to APNs, with the device
  token registered against the user. The email channel ("Approval needed") works today as an
  interim: the mail arrives on the phone and mirrors to the watch, and the app opens the wait.
- Rate and lockout: the gateway locks out an address after repeated failed sign-ins and caps SSE
  connections. The client never retries a 401, backs off on 5xx, and holds at most one SSE stream.

## Security

- The token is stored in the Keychain with `kSecAttrAccessibleAfterFirstUnlock`; the app never
  writes it to logs or crash reports.
- Transport is HTTPS; a LAN `http://` address is accepted only in Debug with the local-networking
  App Transport Security exception.
- The watch sends no `user_id` or `tenant_id`: the gateway derives the principal from the token.
- 0.1 uses the account token, which is shared with the desktop assistant. Rotating it signs out
  every client. 0.2 moves to a per-device, revocable token minted by a short pairing code entered
  in the console; see the backlog track.
- Nothing is stored on the watch beyond the last snapshot of waits, runs and automations.

## Gaps that need gateway work

| Gap | Effect on the watch | Backlog |
|---|---|---|
| No device pairing, one token per account | 0.1 pastes the account token; rotation signs out the Mac | 0013 |
| No push channel | approvals arrive on the next poll, not within a second | 0014 |
| Wait payload has no risk tier, no "approve all in this run" | the card cannot show `Destructive` from the payload; Double Tap stays off; long-press is disabled | 0015 |
| Transcription is run-scoped | the Ask screen must start a run before it can transcribe audio; a session-scoped route would avoid the empty first run | 0016 |

## Build and verification

`scripts/build.sh` regenerates the Xcode project with XcodeGen, runs the Swift package tests on
macOS, builds the app for the simulator without signing, installs and launches it on
"Apple Watch Series 11 (46mm)", and captures one screenshot per screen through the `--screen`
launch argument. A device compile (`generic/platform=watchOS`) checks that nothing simulator-only
leaked in. The `.xcodeproj` is generated and not committed.
