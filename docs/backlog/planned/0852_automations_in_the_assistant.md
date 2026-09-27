# 0852 — Automations in the Assistant: gateway-fed section, "Schedule this", notifications, Discuss

**Status**: planned · **Priority**: high · **Created**: 2026-09-26
**Package**: abstractassistant · **Wave**: Automations v1 (next minor wave; mission **A**)
**Related**: abstractframework backlog 0928 (root Automations v1 item)

Design: untracked/design/automations-PLAN.md (2026-09-26)

## Summary

Make the Assistant a first-class Automations client for v1: a gateway-fed **Automations**
section in the session switcher (grouped by `automation_id`), a tray entry
**Automations…**, a palette action **Schedule this conversation…**, polling of
`GET /automations?changed_since=` that surfaces new answers, failures and human waits
through the existing tray notification path, an automation view that shows its occurrences
as a chat, **Discuss** that opens a normal durable session seeded from a chosen occurrence,
and answering a pending human wait of an occurrence from the Assistant. The regular session
list shows only `chat` and `discussion` sessions, told apart by the gateway's
`session_kind` — never by string prefixes.

The Assistant executes nothing itself. Automations are runtime roots owned by the gateway;
this item is a view, a creator and a responder over contract F.

## Why

Today the Assistant cannot see any run it did not start. Its session list is built from
local files only (see Current code reality), and its only "an answer is ready" notification
fires for runs it started itself while its window was hidden. A scheduled task created
anywhere — Observer, the Assistant tomorrow, the gateway directly — is invisible here.

Operator constraints (2026-09-26 automations brief, quoted as given to this seat):

- "we should be able to do it also from the abstractassistant"
- "distinguish regular sessions and sessions created for automated tasks"

Plan principles this item must hold (PLAN §1):

- **Conversation representation.** "Each occurrence contributes a trigger/task turn and
  answer. Independent mode starts fresh; Growing mode supplies bounded prior conversation."
- **Isolated discussion.** "Discuss creates a separate session seeded at a selected
  occurrence. It cannot write into automation context or resources."
- **Visible and manageable.** "Users can inspect results and steps, edit definitions,
  pause/resume, run manually, stop current work and archive."

Operator rulings (PLAN appendix, 2026-09-26) that amend the plan and bind this item:

- Ruling 4: "**Discuss is NOT read-only and NOT tool-restricted.** A discussion is a new
  durable runtime session, forked/seeded from the automation's conversation through the
  chosen occurrence, replayable like any session, with the target's normal tools. Isolation
  means only that it never writes back into the automation's session/context (a fork)."
  Contract B's `DISCUSSION_READERS_V1` allowlist is dropped — the Assistant must not
  present a Discuss session as restricted.
- Ruling 5: "Quiet results (notify:false / empty answer stay quiet; failures and human
  waits always surface): accepted provisionally."
- Ruling 6: "App breadth for v1: **Observer and Assistant only.**"
- Ruling 2: Independent is the default context mode.

## Scope

### In scope

1. **Gateway client + controller.** `GatewayClient` methods for the F routes below
   (list/get/create/patch/commands/occurrences/discuss/seen, trigger sources) and an
   `AssistantController` facade. Capability-gated: when the gateway does not advertise the
   Automation API, every Automations surface is absent (not greyed, not faked).
2. **Switcher section.** A second, gateway-fed section **Automations** in `SessionSwitcher`,
   one row per `AutomationSummary`, grouped by `automation_id` (never by session-id
   prefix): title, cadence (from `trigger.config.every` / one-shot), `next_fire_at`, last
   status, `last_occurrence.excerpt`, and an unread badge from `attention.unread`
   (plus a wait marker when `attention.pending_waits > 0`). The existing recency groups
   stay for regular sessions.
3. **Regular list = `chat` + `discussion` only**, using the gateway's `session_kind`.
   Discussion rows carry an "about <automation title>" badge that opens the automation.
   Automation (`automation`) and `occurrence` sessions never appear as regular rows.
4. **Tray entry "Automations…"** in `_build_tray_menu`, opening the switcher on the
   Automations section.
5. **Palette action "Schedule this conversation…"**: a small sheet with
   - What — prefilled from the current conversation's workflow (the managed workflow's
     `workflow_id`/`bundle_ref`/`flow_id`) and its last user prompt; editable title;
   - When — presets mapped onto `schedule@1` (`start_at`, `every` as `<n>[smhd]`,
     `count`/`until`): once at…, every N minutes/hours, daily from HH:MM (`every:"1d"`
     anchored at `start_at`), weekly (`every:"7d"`);
   - Context — Independent (default) / Growing;
   - submits `POST /automations` with a client `request_id`; shows the returned summary.
6. **Polling** `GET /automations?changed_since=<change_cursor>` on a background thread
   (never on the GUI thread — see 0851), persisting the last `change_cursor` per gateway
   and principal. A new occurrence with `notify:true` and a non-empty answer, a failed
   occurrence, and a new pending wait each raise one notification through the existing
   `_notify` path; quiet results update the list but do not notify (ruling 5).
   `cursor_expired` (409) resets to a full list without replaying old notifications.
7. **Automation view as a chat.** Opening an automation loads
   `GET /automations/{id}/occurrences` and renders each `OccurrenceRow` as two turns —
   the trigger/task turn (`user_turn`, `trigger.summary`, `fired_at`) and the answer turn
   (`answer`, `status`, artifacts) — with paging via `cursor`. Opening marks it seen via
   `POST /automations/{id}/seen` with the summary's `attention.cursor`. Row actions:
   pause / resume / run now / stop current / archive through
   `POST /automations/{id}/commands`, showing `CommandReceipt` acceptance and the
   ledger-recorded outcome separately.
8. **Discuss.** Per occurrence: "Discuss" → prompt → `POST /automations/{id}/discuss`
   `{request_id, occurrence_index, prompt}`; the returned `session_id` becomes a normal
   Assistant session (`session_kind:"discussion"`), switched to immediately, with normal
   tools, normal history replay, rename/delete — nothing special beyond the badge.
9. **Answer a pending human wait** of an occurrence from the Assistant: the wait's
   `prompt`/`choices` rendered in the automation view (and reachable from its
   notification); the answer is a `resume` command with `{wait_key, payload}` on the wait's
   `run_id` — the same command shape `ui/gateway_worker.py:799` already sends for waits of
   runs the Assistant started.

### Out of scope

- Any local scheduler, timer or execution in the Assistant (PLAN §1 "One system").
- Editing a definition beyond title/trigger/context through `PATCH` (target re-selection is
  Observer/Flow's job in v1); cron/weekday/time-zone rules — `schedule@1` has none
  (PLAN §3 C, §5 V3).
- External/event triggers, delivery channels (Telegram/email/webhook), automatic
  summaries (PLAN §5 V2/V3; next-phase item per ruling 3).
- Legacy schedules beyond showing them read-only with `legacy:true` and the gateway's
  own capabilities list.
- A slash-command registry (none exists; "Schedule this" is a palette action, not
  `/schedule`).
- Choosing a Discuss workspace policy — open operator question under ruling 4; the
  Assistant uses whatever the discuss route returns.

## Contract consumed (F, verbatim from PLAN §3)

```text
AutomationSummary={
 automation_id,title,status,trigger:TriggerBinding,context_mode,next_fire_at?,
 occurrence_count,last_occurrence?:{
  run_id,index,status,fired_at,finished_at?,excerpt,notify},
 attention:{pending_waits:int,unread:bool,cursor:string},
 legacy:bool,revision:int|null,updated_at,capabilities:string[],
 session_kind:"automation"
}
OccurrenceRow={
 run_id,index,fired_at,finished_at?,status,
 trigger:{source_id,summary},user_turn,answer,notify,
 artifacts:[{artifact_id,name,mime_type,url}],
 waits:[{run_id,wait_key,reason,prompt?,choices?}],
 ledger_url,workspace_url?
}
CommandReceipt={command_id,accepted,duplicate,seq}
```

| Route | Request → response |
|---|---|
| `POST /automations` | `{request_id,title,target,trigger,context?,policy?}` → `{automation_id,revision,summary}` |
| `GET /automations` | `status,changed_since,cursor,limit` → `Page<AutomationSummary>` |
| `GET /automations/{id}` | → `{definition,active_revision,summary}` |
| `PATCH /automations/{id}` | `{command_id,expected_revision?,changes:{title?,target?,trigger?,context?}}` → receipt |
| `POST /automations/{id}/commands` | `{command_id,type,payload?}` → receipt |
| `GET /automations/{id}/occurrences` | `cursor,limit` → `Page<OccurrenceRow>` |
| `POST /automations/{id}/discuss` | `{request_id,occurrence_index,prompt}` → `{session_id,run_id,session_kind:"discussion"}` |
| `POST /automations/{id}/seen` | `{attention_cursor}` → `{attention_cursor}` |
| `GET /trigger-sources` | → `{items:[TriggerSource+{available,unavailable_reason?}]}` |

`Page={items,next_cursor,change_cursor}`. Errors `{error:{code,message,field?,command_id?}}`
with the PLAN §3 F code set (404/409/422). Command types
`automation.revise|pause|resume|run_now|stop_current|archive`.

**Fixtures.** Tests run against the canonical abstractuic fixtures
`fixtures/automations/{list,occurrences,trigger-sources,commands,errors}.json`, vendored
into `tests/fixtures/automations/` with a recorded SHA-256 per file; a test recomputes the
checksums and fails on drift (the fixtures are checksum-shared with Qt/Rust per PLAN §3 G).
Hand-written look-alike fixtures are not acceptable.

## Current code reality (verified at 4861218, 0.6.0)

- **Sessions are local-only.** `SessionIndex.create_session` mints `sess_<uuid>` in a
  local directory (`core/session_index.py:191`); the record is `SessionRecord`
  (`core/session_index.py:47`: `session_id, actor_id, title, path, created_at,
  updated_at` — no kind, no automation linkage). Transcript snapshot:
  `SessionSnapshot` (`core/session_store.py:19`). Switcher digest: `SessionDigest`
  (`core/session_digest.py:62`).
- **The list is built from local files.** `controller.list_sessions` /
  `session_digests` (`controller.py:961-997`; the docstring at :965 says "Reads local
  files only"). A gateway-created run can never appear.
- **Switcher.** `SessionSwitcher` (`ui/session_switcher.py:570`), `SessionRow`
  (`:270`), grouping in `_rebuild` (`:698-702`) by `recency_group(last_activity)` only.
- **Palette.** Session picker button `app.py:5803`; `_open_session_switcher` `:6293`;
  `_switch_to_session` `:6328`.
- **Notifications.** `_notify` `app.py:10039` (tray `showMessage`, 220-char cap);
  `_notify_completion_ready` `:10068` fires only for runs the Assistant itself started
  and only when the window was hidden (`app.py:8245-8251`: `hidden = not
  self.isVisible()` on the final event of the active worker).
- **Tray menu.** `_build_tray_menu` `app.py:11065`: Show / Hide / New Session /
  Settings / About / Quit.
- **Waits.** Answered only inside a live `GatewayWorker` for its own run
  (`ui/gateway_worker.py:799` `_submit_resume`, type `resume`,
  `payload:{wait_key,payload}`); `controller.resume_run` (`controller.py:1686`) is the
  pause-resume command, not a wait answer.
- **Gateway client.** `list_runs` (`gateway/client.py:492`) hits `/api/gateway/runs`;
  `submit_command` `:1096`. No automation or `session_kind` knowledge anywhere in the
  package (grep for `automation`, `session_kind`: no hits).
- **History.** `use_session_history` defaults on (`gateway/run_input.py:95`, documented
  :127): the gateway seeds prior turns, so a Discuss session behaves like any session once
  its seed is stored gateway-side (PLAN §3 B).
- **Settings.** `SettingsDialog` `ui/settings/dialog.py:112` (`SECTIONS` tuple), pages
  wired at `:151`; an optional "Automations" notification toggle would land here.
- **No slash-command registry exists.**

## Seams

- **G (abstractgateway)** owns every route, shape, `session_kind`, attention cursor and
  the capability flag. A reads them; it does not re-derive them. Before writing code, READ
  G's live routes and response examples; where a shape is missing, raise a `blocked` ask
  to G — no fallback that silently degrades.
- **Known gaps to raise with G before implementation:**
  - F has no route that lists *sessions* with `session_kind`. The regular list needs it
    for discussions created elsewhere (e.g. Observer) and for badging local chats; PLAN
    §3 E adds `session_kind` to `list_run_index` at runtime level, but no F route exposes
    it. Ask G for `GET /runs?session_kind=` (or equivalent) with `automation_id` on rows.
  - F routes are written as `/automations`; the client's existing base is
    `/api/gateway/...` (`gateway/client.py:500`). Confirm the mount.
- **U (abstractuic)** owns the fixtures. They do not exist yet (`abstractuic/fixtures/`
  absent at the time of writing); vendoring waits for U.
- The presentation contract (`AutomationPanelProps`, PLAN §3 G) is React; the Qt view
  mirrors its behaviour and callbacks, not its code.

## Tests

- `tests/basic/test_automation_sessions.py` (repo tests live under `tests/basic/`):
  - fixtures checksum gate (delete one fixture → RED);
  - summaries → switcher Automations rows grouped by `automation_id`; regular list keeps
    `chat` + `discussion` only, keyed on `session_kind`, with a prefix-named decoy
    (`automation:…`/`scheduled:…` session id with `session_kind:"chat"`) staying a chat;
  - polling: `notify:true` answer → one notification; `notify:false` / empty answer → none;
    failure and new wait → always one; repeated poll with the same cursor → no duplicates;
    `cursor_expired` → full reload, no replayed notifications;
  - "Schedule this conversation…" builds the exact `POST /automations` body
    (target from the current workflow, last prompt, `schedule@1` config per preset,
    `context.mode`);
  - Discuss posts `{request_id, occurrence_index, prompt}` and switches to the returned
    session as an ordinary session;
  - wait answer sends `resume` with the fixture's `run_id` and `wait_key`;
  - Automations absent when the capability is not advertised.
- Offscreen UI check per the repo's headless review method (`QT_QPA_PLATFORM=offscreen`;
  disable the traffic-light bridge `_MAC_NATIVE_TRAFFIC_LIGHTS_AVAILABLE = False` and the
  global hotkey first): grab the switcher with both sections, the automation chat view,
  the Schedule sheet and a wait answer.
- Tests never reach the operator's live gateway (unset the admin token; fake transport).

## Definition of Done

The three operator scenarios are reachable end to end from the Assistant against a real
gateway with the Automation API:

1. **Three news monitors** — three automations created via "Schedule this conversation…",
   listed separately in the Automations section with cadence, next run, excerpt and unread
   badge; each opens as a chat of its occurrences; Discuss on one occurrence yields a
   normal session badged "about <monitor>".
2. **Email triage** — a recurrent automation whose normal results are quiet
   (`notify:false`) and whose urgent results notify; a reply gated on a human wait
   surfaces as a tray notification and is answered from the Assistant, after which the
   occurrence completes.
3. **Weekly journal monitor** — a weekly (`every:"7d"`) Growing automation whose
   occurrences read as one continuing conversation.

Plus: gateway-created automations (e.g. from Observer) appear without any local action;
failures always notify; no automation or occurrence session appears among regular chats;
the Discuss session has the target's normal tools.

## Dependencies

- G — gateway Automation API (routes, `session_kind`, attention, capability flag).
- U — abstractuic `fixtures/automations/*.json`.
- Minor release of abstractassistant with a raised gateway floor, in the v1 wave order
  (PLAN §3 I).

## Contracts pass (2026-09-27)

Final contracts: untracked/design/automations-CONTRACTS.md (root repo; rev 2 with Astra turn-6 amendments 1–11). They supersede the contract text copied above; earlier text is kept as history. Concrete changes for this item:

- Poll full paginated `GET /api/gateway/automations` (no `changed_since`; remove the `cursor_expired` path). Tray notifications come from `GET /api/gateway/automations/{id}/attention` pages (oldest unseen first) and from new interactive waits; ack = cursor of the last item notified.
- Quiet is the default: no notification for answers without a `notify` output; failures notify only after all retries; drop `notify:false` wording.
- Interactive waits include EVENT waits with prompt/choices, not only USER waits.
- Typed `GatewayApiError(status, reason_code, message, field, command_id)` parsed from `detail`; `_read_error` must not `json.dumps` it.
- Regular list = `GET /api/gateway/runs?root_only=true&session_kind=chat,discussion`.
- "Schedule this conversation…" presets are fixed intervals labelled "every N hours/days".
- Discuss sessions run on a read-only workspace; the badge says so.
- Fixtures vendored byte-identical in `tests/fixtures/automations/` (incl. `attention.json`), checked by the root `scripts/check_identity_sync.py`, not a local SHA list.

## Progress (mission A, 2026-09-27) — built against the fixtures, not yet against G

Local commits e3a0445, 2f38ef5, 2768176 (+ docs). Status stays **planned** until the integration pass
against the hermetic gateway once G ships the routes.

- Client `gateway/automations.py` (ten calls, `AutomationApiError` from `detail.reason_code`,
  `unreachable` for no answer); rules `core/automations.py`; Qt `ui/automations.py`
  (`AutomationRow`, `AutomationView`, `ScheduleSheet`, `AutomationsHub`); switcher section; palette
  view; tray **Automations…**; notifications with a persisted ledger.
- Fixtures vendored byte-identically (abstractuic b70db16) in `tests/basic/fixtures/automations/`
  with `CHECKSUMS.sha256` (the mission's location; the root `check_identity_sync.py` group must point
  there).
- Regular list: `fold_session_rows` drops `session_kind` `automation|occurrence` rows client-side;
  the pinned `/runs` query is unchanged (no `session_kind=` parameter yet — the current gateway
  refuses unknown parameters with a 400).
- Capability-gated (coordinator decision, 2026-09-27): `contracts.common.automations.available is
  true` in the existing capabilities call shows the section and the tray entry; absent or false hides
  them and no automation route is called; unreadable capabilities are an error, never "absent".
  (G answers unknown automation routes with a `not_found` envelope, so a 404 is not a signal.)
- Poll: 60 s while the palette is visible, 5 min while hidden (the only background traffic; kept so
  tray notifications arrive with the palette closed).
