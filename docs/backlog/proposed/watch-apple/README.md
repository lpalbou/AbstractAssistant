# Track: Apple Watch client (watch-apple)

Design and delivery of AbstractAssistant for Apple Watch, a standalone watchOS 26 thin client of
AbstractGateway. The proposal, the UX design, the client architecture, the screen mockups and
the animated prototype live in [`watch/apple/`](../../../../watch/apple/README.md). This track
holds the work items; the gateway-side items are filed here with their owning package stated
and should be mirrored into the gateway backlog when they are taken up.

| ID | Item | Owning package | Priority |
|---|---|---|---|
| [0012](0012_apple_watch_client_mvp.md) | Apple Watch client MVP: waiting for you, ask, runs, automations | abstractassistant | P1 |
| [0013](0013_device_pairing_and_per_device_tokens.md) | Device pairing by short code and per-device revocable tokens | abstractgateway | P1 |
| [0014](0014_push_notification_bridge.md) | Push notification bridge for waits and failures (APNs) | abstractgateway, abstractassistant | P1 |
| [0015](0015_wait_payload_risk_tier_and_approve_all.md) | Wait payload carries the risk tier; allow all in this run | abstractruntime, abstractgateway | P2 |
| [0016](0016_voice_on_the_wrist.md) | Voice on the wrist: record, transcribe on the gateway, speak the answer | abstractassistant, abstractgateway | P2 |
| [0017](0017_complications_smart_stack_and_app_intents.md) | Complications, Smart Stack widget and App Intents | abstractassistant | P2 |
| [0018](0018_watch_packaging_and_ci.md) | Packaging and CI for watch/apple | abstractassistant | P2 |
| [0019](0019_iphone_companion_and_wearos_parity.md) | iPhone companion and Wear OS parity study | abstractassistant | P3 |
| [0020](0020_meeting_capture_on_the_wrist.md) | Meeting capture on the wrist: chunked resumable upload, finalize, meeting workflow | abstractgateway, abstractassistant, abstractflow | P2 |
| [0021](0021_entity_and_agent_picker.md) | Entity and agent picker: talk to a named entity or a chosen workflow (picker + chat path built in 0012; card line and visits remain) | abstractassistant | P2 |
| [0022](0022_inbox_projection_endpoint.md) | Inbox projection: one feed of waits, results, failures and entity questions | abstractgateway | P2 |
| [0023](0023_on_demand_location_context.md) | On-demand location context attached to a question | abstractassistant | P3 |

Items 0020–0023 and the amendments to 0012–0014 (stale-approval protection, queued → applied
states, wrist/passcode check for destructive approvals, minimal push payloads) come from the
cross-review of a second product spec on 2026-10-16 (`AbstractAssistant_Apple_Watch_Product_Spec_2026-10-16.md`,
kept outside the repository). Its broader thesis, lived-context memory with evidence,
person/place views and proactive prompts, stays a research direction beyond this track.

Order: 0012 first (it needs nothing new from the gateway), then 0013 and 0014 together (they
turn the watch from a polling client into a notified one), then 0015–0017, with 0018 alongside
0012. Research notes that informed the track: `untracked/watch/research/` in the framework
checkout (assistant brief, gateway API brief, toolchain check).
