# ADR 0004: Notes live inside the assistant's apps; AbstractNote stays a service

Status: Accepted
Date: 2026-10-26 (revised the same day after an adversarial review and the one-project merge of ADR 0005)

## Context

AbstractNote (`../../../abstractnote`) is the framework's everyday-memory product: capture a
thought, a recording or a document, let the gateway file it with its time, place and source, link
it to what is already known, and recall it later with evidence. In the repository it is a
gateway-side service (two flows, `note-capture` and `note-recall`; read routes under
`/api/gateway/note/*`; a per-user processor automation; a revision log as the source of truth) plus
a web app, a watch-only Apple Watch client and a planned iPhone app. Its watch client is a
documented fork of this repository's watch code (`abstractnote/watch/apple/Packages/AbstractWatchKit/SNAPSHOT.json`).

The operator asked whether the two products should fuse. Two Apple apps with the same sign-in,
forked Swift and two capture habits would be two silos on one wrist. Merging the Python packages
or the data models would entangle a chat assistant with a memory service whose revision log and
reconciliation rules must stay its own.

## Decision

- **One Apple app family for the person: AbstractAssistant.** The iPhone app and its Watch
  companion ([ADR 0005](0005_one_apple_project.md), amending [ADR 0003](0003_unified_apple_product.md))
  are where notes are captured and recalled on Apple devices. AbstractNote ships no Apple app once
  the Notes surface exists here; its watch target is retired then, not kept in sync. On Apple
  devices, memory without the assistant is the web app in a browser.
- **AbstractNote stays a service and a web app.** Its flows, routes, processor automation, data
  model and revision log remain in the `abstractnote` package. This repository models, stores and
  reconciles no note data. The apps call only: `POST /api/gateway/runs/start` with the
  `note-capture` flow (with `idempotency_key` and `occurred_at`) and the `note-recall` flow,
  `GET /api/gateway/note/status`, and the read routes a screen needs (search, a note, its
  processing state). A new route used by the apps is added to this list.
- **The Notes surface is capability-gated by one probe.** `GET /api/gateway/note/status` answers:
  Notes is offered; 404: the assistant shows no Notes, and asks again on the next sign-in or
  launch (no day-long memory of the 404: a gateway that gains AbstractNote shows Notes at once).
  A gateway without AbstractNote is an assistant without Notes, never a broken one.
- **What the fusion means for the assistant.** Recall as context: the gateway already binds the
  note tools to each user's own notebook when `abstractnote` is installed
  (`abstractgateway/src/abstractgateway/abstractnote_seam.py`); the work is offering them in the
  assistant's tool plan, not building a tool. Capture with honest
  receipts (saved on the device, received, organizing, organized). The assistant's conversations
  and automation results offered as sources. AbstractNote's open loops and insights on the
  gateway's event stream, not a second notification channel. Order and sizing are backlog work.
- **Shared Swift is shared in this repository.** The two Apple clients of this repository share
  code through their packages (`AssistantPush` today, ADR 0005). Nothing is copied to or from
  `abstractnote` again: what its watch did better (the four receipt states, the Ask effort
  levels) lands here once, as part of the Notes surface. Backlog [1053](../backlog/proposed/1053_shared_swift_client_kit_for_apple_clients.md)
  holds the remaining duplication between the two apps.
- **Non-goals.** No merge of the Python packages. No shared data model. No note organization on
  the device: a note saved locally is not a note received.

## Consequences

### Positive
- One login, one inbox, one capture habit on the wrist and the phone; one place for Apple
  client fixes.
- The assistant gains memory recall without owning a memory engine.

### Negative
- The Notes surface depends on an alpha service (AbstractNote 0.1.1); the probe above is what
  keeps that dependency from breaking the assistant.
- AbstractNote's own Apple plans (its ADR 0006 on credentials, backlog 0014 iPhone app, 0016 shared
  kit in abstractuic, 0017 rulings) contradict this decision and must be superseded by the
  abstractnote seat; until then the two repositories disagree on paper.

### Neutral
- The web app remains AbstractNote's full workspace; the Apple apps cover capture and recall,
  not the graph explorer.

## Enforcement
- A change in this repository that adds note storage, reconciliation or a note schema is out of
  scope and is redirected to `abstractnote`.
- Every Notes screen is reached only after the status probe answered; a UI test runs the mock
  gateway with the probe answering 404 and proves the assistant has no Notes entry and no error.
- A new Swift file that duplicates one in `abstractnote/watch/apple` is a review rejection.

## Validation
- UI tests with the mock gateway in both states of the probe.
- The route list in the decision is the contract; a change on either side revises this ADR.

## Backlog links
- [1053 — Shared Swift between the two Apple apps](../backlog/proposed/1053_shared_swift_client_kit_for_apple_clients.md)
- [1054 — Offline note queue on the wrist](../backlog/proposed/watch-apple/1054_offline_capture_queue_on_the_wrist.md)
- Framework backlog 1049 (push), whose device side ships in `AssistantPush`
- AbstractNote: ADR 0006, backlog 0014, 0016, 0017, 0019 (to be superseded there)

## Related
- [ADR 0001](0001_gateway_native_assistant_v2.md), [ADR 0003](0003_unified_apple_product.md), [ADR 0005](0005_one_apple_project.md)
- The product decks of 2026-10-25 (AbstractNote positioning; AbstractAssistant on Apple Watch, showcase and vision), kept outside the repository
