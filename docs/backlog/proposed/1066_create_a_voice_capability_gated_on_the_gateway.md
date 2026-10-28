# 1066 — "Create a voice" is offered only when the gateway serves the voice library (AbstractGateway >= 0.16.0)

> Package: abstractassistant (desktop; iPhone and watch share the check through `AbstractGatewayClient`)
> Type: fix
> Created: 2026-10-28
> Status: Proposed
> Completed: N/A
> Priority: P2
> Labels: voice, gateway, capability-gating, desktop, iphone

## Summary

The desktop's route editor always shows an enabled "Create…" button beside the voice picker
(`abstractassistant/ui/settings/route_editor.py` ~l.240, `create_voice_button`; enabled with the rest of the
form at ~l.490, no capability check). Against a gateway older than 0.16.0, which has no voice library
(`POST /api/gateway/voice/design`, multipart `POST /voice/clones`), the dialog
(`ui/settings/create_voice_dialog.py`) opens and the request fails with a 404 after the person has typed a
description or recorded a sample. Gate the button on the gateway's served capability (the thin-client
capability contract / discovery), hidden or disabled with the sentence "This gateway cannot create voices
(AbstractGateway 0.16.0 or later)", never a version-string comparison when a capability flag exists.

## Current code reality (origin/main, 0.15.0)

- Desktop: `route_editor.py` builds `create_voice_button` unconditionally; `gateway/client.py:1026` `voice_design`.
- iPhone: `AbstractGatewayClient/GatewayClient.swift` documents the voice library as AbstractGateway 0.16.0; check whether the iPhone's Create a voice row has the same gap (1061 shipped it) and fix it in the same item.

## Chosen route

Read the gateway's capability (the voice-library flag in discovery; if none exists, raise it to the gateway
seat as a contract gap rather than parsing versions), cache it per connection, gate the button and the iPhone
row on it; a test with a fake gateway without the flag asserts the button is disabled with the sentence.

## Acceptance criteria

- [ ] Against a gateway without the voice library the button is disabled/hidden with the sentence; with it, unchanged.
- [ ] The test is red with the gate removed.
