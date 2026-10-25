# ADR 0004: Notes live inside the assistant's apps; AbstractNote stays a service

Status: Accepted
Date: 2026-10-26

## Context

AbstractNote (`../../../abstractnote`) is the framework's everyday-memory product: capture a
thought, a recording or a document, let the gateway file it with its time, place and source, link
it to what is already known, and recall it later with evidence. In the repository it is a
gateway-side service (two flows, `note-capture` and `note-recall`; about forty read routes under
`/api/gateway/note/*`; a per-user processor automation; a revision log as the source of truth) plus
a web app, a watch-only Apple Watch client and a planned iPhone app. Its watch client is a
documented copy of this repository's watch code (`abstractnote/watch/apple/Packages/AbstractWatchKit/SNAPSHOT.json`).

The operator asked whether the two products should fuse. Two Apple apps with the same sign-in,
the same copied Swift and two capture habits would be two silos on one wrist. Merging the Python
packages or the data models would entangle a chat assistant with a memory service whose revision
log and reconciliation rules must stay its own.

## Decision

- **One Apple app family for the person: AbstractAssistant.** The iPhone app and its Watch
  companion ([ADR 0003](0003_unified_apple_product.md)) are where notes are captured and recalled
  on Apple devices. AbstractNote ships no Apple app of its own once this is in place.
- **AbstractNote stays a service and a web app.** Its flows, routes, processor automation, data
  model and revision log remain in the `abstractnote` package. AbstractAssistant's apps are
  clients of `/api/gateway/note/*` and of the `note-capture` and `note-recall` flows, nothing
  more: no note data is modelled, stored or reconciled in this repository.
- **The Notes surface is capability-gated.** It appears only when the signed-in gateway answers
  on the note routes. A gateway without AbstractNote shows an assistant without Notes, never a
  broken one (the same rule as the event stream fallback in `watch/apple/Sources/App/Shared/AnswerNotifier.swift`).
- **What the assistant takes from AbstractNote, in this order:** recall as context (a notebook
  search tool for the assistant workflow), capture with honest receipts (saved on the device,
  received, organizing, organized), the assistant's own conversations and automation results as
  sources, and AbstractNote's open loops and insights on the gateway's event stream rather than a
  second notification channel.
- **Shared Swift code is shared once, not copied.** The two Apple clients share one client kit
  (transport, sign-in, credential storage, speech, theme). The shape and home of that kit are
  decided in backlog [1053](../backlog/proposed/1053_shared_swift_client_kit_for_apple_clients.md);
  until it exists, no further copying between the two repositories.
- **Non-goals.** No merge of the Python packages. No shared data model. No note features that
  only work with the assistant's own session store. No promise of offline note organization on
  the device: a note saved locally is not a note received.

## Consequences

### Positive
- One login, one inbox, one capture habit on the wrist and the phone; AbstractNote keeps its
  independence for people who want memory without an assistant.
- The assistant gains memory recall without owning a memory engine.

### Negative
- The assistant's apps depend on an alpha service (AbstractNote 0.1.1) for the Notes surface;
  the gate above is what keeps that dependency from breaking the assistant.
- AbstractNote's watch work (the four receipt states, the Ask effort levels) is ported, not
  reused as an app; its watch target is retired when the port lands.

### Neutral
- The web app remains AbstractNote's full workspace; the Apple apps cover capture and recall,
  not the graph explorer.

## Enforcement
- A pull request in this repository that adds note storage, reconciliation or a note schema is
  out of scope and must be redirected to `abstractnote`.
- Every Notes screen checks the gateway's note capability before it is offered; a UI test must
  prove the assistant runs with the routes absent.
- New Swift shared between the two Apple clients goes through the kit of 1053, not a copy.

## Validation
- UI tests run the apps against a mock gateway with and without note routes.
- The contract between the apps and AbstractNote is the routes and flows named here; a change on
  either side is a change to this ADR.

## Backlog links
- [1053 — Shared Swift client kit for the Apple clients](../backlog/proposed/1053_shared_swift_client_kit_for_apple_clients.md)
- [1054 — Offline capture queue on the wrist](../backlog/proposed/watch-apple/1054_offline_capture_queue_on_the_wrist.md)
- AbstractNote: backlog 0016 (shared Swift package), 0014 (iPhone app), 0017 (credential ruling), 0019 (notifications)

## Related
- [ADR 0001](0001_gateway_native_assistant_v2.md), [ADR 0003](0003_unified_apple_product.md)
- The product decks of 2026-10-25 (AbstractNote positioning; AbstractAssistant on Apple Watch, showcase and vision), kept outside the repository
