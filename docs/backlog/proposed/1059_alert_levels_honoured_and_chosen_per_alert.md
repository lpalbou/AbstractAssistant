# 1059 — Alert levels: the apps honour the gateway's, and an alert can choose its own

> Package: abstractassistant (iPhone and Apple Watch apps); touches abstractgateway, abstractflow
> Type: improvement
> Created: 2026-10-26
> Status: Proposed
> Completed: N/A
> Priority: P2
> Labels: push, notifications, apple, watch, iphone

## Summary

Two levels exist today, fixed by the kind of alert: approvals and questions are
**time-sensitive**, everything else (an automation's result or failure, a flow's "Notify me") is
**active**. The gateway sends exactly that, but the apps override every non-urgent alert to
**passive**, so results and "Notify me" land silently on both devices. First make the apps honour
the level they were sent; then, if wanted, let an alert choose its level.

## Current code reality (2026-10-26)

- Gateway: `abstractgateway/src/abstractgateway/push/relay.py:150` sends
  `"interruption-level": "time-sensitive" if urgent else "active"`, with the comment citing the
  operator's ruling "nothing is passive" (gateway `CHANGELOG.md:10`).
- iPhone and watch notification service extension:
  `phone/iphone/NotificationService/NotificationService.swift:53` sets
  `rendering.timeSensitive ? .timeSensitive : .passive`, overriding the gateway's `active`.
- Local catch-up notifications: `watch/apple/Sources/App/Shared/AnswerNotifier.swift:310,316`
  and `phone/iphone/Sources/App/PhoneNotifier.swift:33,38` post results as `.passive`.
- `PushRendering` (`phone/iphone/Packages/AssistantPush/Sources/AssistantPush/PushRendering.swift`)
  carries a single `timeSensitive` flag; no level travels with an alert.
- A flow's "Notify me" node (abstractflow) has no level field; `attention.raised` carries
  `channels` and `recipient` but no level (gateway `docs/api.md:1320`).
- Apple's levels: passive, active, time-sensitive, critical (critical needs an Apple-granted
  entitlement; out of reach).

## Scope and expected outcome

1. **Honour the level (small).** Non-urgent alerts render `.active` in the extension and in both
   apps' catch-up notifications, matching the gateway. Tests in `AssistantPush` for the mapping.
2. **A level per alert (larger, only if wanted).** An optional `level` on a published alert
   (`passive | active | time-sensitive`), set by the "Notify me" node, carried by
   `attention.raised`, used by the relay, rendered as sent by the apps. Absent = today's rule.

## Non-goals

- Critical alerts.
- Per-device or per-user overrides of the level (the system's own notification settings and
  Focus modes already cover that).
- Clearing an alert on other devices once consumed: the apps replay the ledger and events, so an
  answered item leaves every app by design (operator, 2026-10-26).

## Promotion criteria

The operator confirms they want step 1 now, or asks for alerts with their own level. Step 2
needs the gateway and flow seats (event shape and node field) before the apps.

## Validation

- Step 1: `swift test --package-path phone/iphone/Packages/AssistantPush`, then a result push on a
  real iPhone and watch: banner and sound, not silent.
- Step 2: gateway `tests/test_notify_me_channels.py` extended for `level`; a flow with "Notify me"
  at each level, checked on the devices.
