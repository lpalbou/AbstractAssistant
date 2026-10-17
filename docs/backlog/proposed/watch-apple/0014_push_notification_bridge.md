# Proposed: Push notification bridge for waits and failures (APNs)

> Created: 2026-10-16 22:30:00 +0200
> Type: feature
> Priority: P1
> Labels: watch, gateway, notifications

## Metadata
- Created: 2026-10-16
- Status: Proposed
- Completed: N/A
- Owning packages: abstractgateway (bridge), abstractassistant (watch client, notification actions)
- Track: [watch-apple](README.md) (Apple Watch client)

## ADR status
- Governing ADRs: [ADR 0001](../../../adr/0001_gateway_native_assistant_v2.md) (gateway-native thin client: the gateway owns workflows, runs, tools, policy and speech)
- ADR impact: None. The watch is one more thin client of the same gateway contract.

## Summary
Deliver tool approvals, questions and failures to the watch within seconds as actionable
notifications (Allow once / Deny / Open). The gateway gains an outbound notification channel:
registered device tokens per user, and a notifier that sends an APNs push when a run owned by
that user enters a wait or fails. The watch registers its token and handles the actions.

## Why
Without push, the watch learns about a wait on its next poll, and watchOS suspends the app
seconds after the wrist drops. Background refresh runs a few times per hour at best. The
email channel ("Approval needed", abstractgateway/docs/email.md) works today but needs the
mail to reach the phone and the user to open the app.

## Scope
- `POST /api/gateway/me/push-tokens` (platform, token, device id), `DELETE`.
- A gateway notifier observing the active-run index for waits and terminal failures of the user's runs and automations, sending `{title, body, run_id, wait_key, kind, tool, risk}` with a collapse id per wait; actions answered by the app through `POST /commands`.
- APNs delivery through a small relay (the gateway holds the APNs key, or a hosted relay for people who do not want to manage certificates); the choice is a design decision to record.
- Watch: `UNUserNotificationCenter` categories with the two actions; the action calls `resume` and posts a confirmation.
- Minimal payload: reference ids and a user-safe preview, never the full tool arguments or transcript on a locked screen; the app fetches the CURRENT wait before rendering or acting, so a stale notification can never approve another step (adopted from the cross-review spec).

## Non-goals
No notifications for routine completions (quiet by default, as the desktop assistant); no
Android (Wear OS) push in this item.

## Current code reality
- The docs mention no push, APNs, webhook or gateway-wide event stream; clients poll or receive email (abstractgateway/docs/automations.md §notifications; email.md).
- `GET /runs?status=waiting` is served from the active-run index and is cheap (api.md §runs), so a notifier can poll it internally at 1–2 s without cost.
- The watch SDK on this machine has `UserNotifications`; actionable notifications on watchOS are standard (`untracked/watch/research/toolchain-check.md` §D).

## Dependencies
- Item 0013 (per-device tokens) so a push token is bound to a device.
- Paid Apple developer account for APNs (enrolment pending for contact@abstractframework.ai).

## Expected outcomes
- An approval appears on the wrist within 5 s of the wait being created, with Allow once / Deny actions that resume the run.
- A failed automation taps the wrist once; completions stay silent.

## Acceptance Criteria
- [ ] A wait created on the gateway produces one push per device token of the owning user within 5 s on a LAN test
- [ ] Answering from the notification action records a `resume` on the ledger and the run continues
- [ ] No push is sent for a plain completion; one push is sent for a failure
- [ ] Revoking a push token stops deliveries to that device

## Testing
- `cd abstractgateway && python -m pytest tests -k notifier -q`
- `xcrun simctl push booted ai.abstractframework.assistant.watch payload.json`
