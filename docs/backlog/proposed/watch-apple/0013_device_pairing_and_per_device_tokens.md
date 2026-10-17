# Proposed: Device pairing by short code and per-device revocable tokens

> Created: 2026-10-16 22:30:00 +0200
> Type: feature
> Priority: P1
> Labels: watch, gateway, auth

## Metadata
- Created: 2026-10-16
- Status: Proposed
- Completed: N/A
- Owning packages: abstractgateway (routes, security), abstractassistant (watch client)
- Track: [watch-apple](README.md) (Apple Watch client)

## ADR status
- Governing ADRs: [ADR 0001](../../../adr/0001_gateway_native_assistant_v2.md) (gateway-native thin client: the gateway owns workflows, runs, tools, policy and speech)
- ADR impact: None. The watch is one more thin client of the same gateway contract.

## Summary
Add a device-code pairing flow to the gateway: a client without a browser or camera shows a
short code; the signed-in user enters it in the console (Devices page); the gateway mints a
per-device token bound to that user, revocable on its own, listed with its device name and
last use. The watch polls for completion and stores the token in the Keychain.

## Why
Today there is one bearer token per account and rotating it signs out every client
(abstractgateway/docs/security.md §tokens). A watch cannot type a long token, and a lost watch
must not force the Mac to sign out. The only typed-code flow today is the email sign-in code,
which rotates the account token.

## Scope
- `POST /api/gateway/devices/code` (unauthenticated, rate-limited, returns `{device_code, user_code, expires_in, interval}`), `POST /api/gateway/devices/claim` (authenticated session or token; binds `user_code` to the caller's principal), `POST /api/gateway/devices/poll` (returns `authorization_pending` or the device token once), `GET/DELETE /api/gateway/me/devices` (list, revoke), console Devices page.
- Device tokens are hashed at rest like account tokens, carry the same principal, and can be scoped to `scopes: ["runs:read", "waits:answer", "runs:start", "automations:read"]` when scopes become enforced.
- Audit log events: `device_paired`, `device_revoked`.
- Never persist the gateway's bootstrap admin token on a watch: enrolment binds a user-scoped device credential (adopted from the cross-review spec).
- High-impact approvals on the watch (destructive tier, item 0015) may require the local owner check `LAPolicy.deviceOwnerAuthenticationWithWristDetection` before sending; this is a local gate, not an identity attestation to the gateway.

## Non-goals
No OAuth provider, no SSO, no QR flow (an iPhone companion could add QR later, item 0019).

## Current code reality
- `POST /admin/users` and `PATCH /admin/users/{id} {rotate_token}` are the only token mints; the token is shown once (security.md §tokens; routes/gateway.py around 251–287).
- Named keys exist only for `/v1` and are refused on `/api/gateway/*` (security.md §/v1 keys).
- The email recovery code (`session/recovery/request|redeem`, purpose `reset_token`) is the closest typed-code flow and it rotates the account token (abstractgateway/docs/email.md §sign-in by email).
- `scopes` is a free list on the user record; no scope values are enforced yet (routes/gateway.py around 263).

## Dependencies
- Design agreement with the gateway seat on the route names and the token format.
- Console UI work for the Devices page (abstractgateway console) or the TUI equivalent.

## Expected outcomes
- A watch pairs in under a minute without typing a token; revoking it on the console signs out only the watch.
- The audit log records who paired which device and when.

## Acceptance Criteria
- [ ] A device code flow mints a token that authenticates `GET /api/gateway/me` with the pairing user's principal
- [ ] Revoking the device token returns 401 for that token only; the account token keeps working
- [ ] Codes expire (10 min) and are single-use; polling before claim returns `authorization_pending`
- [ ] Rate limiting on `devices/code` and `devices/poll` is covered by a test
- [ ] `device_paired` and `device_revoked` appear in `audit_log.jsonl`

## Testing
- `cd abstractgateway && python -m pytest tests -k device -q`
- `curl -s -X POST http://127.0.0.1:8080/api/gateway/devices/code`

## Progress (2026-10-17)
- The watch has a sign-in page (first launch, Sign out, session ended): user name + token, or a registered email + an emailed 8-digit code redeemed for a 30-day gateway session (existing `/session/recovery/*` routes, `X-AbstractGateway-Session` + CSRF headers).
- abstractgateway: `/session/recovery/request|redeem` accept the account's registered email in place of the id (`mail/recovery.py` `account_for`; test `test_registered_email_works_in_place_of_the_account_id`). Uncommitted, unreleased.
- Still open here: device-code pairing and per-device revocable tokens (the session from an emailed code is per sign-in and expires; a token is per account).
