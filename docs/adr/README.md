# ADR Index

This directory records durable architecture decisions for AbstractAssistant.

## ADRs

- [ADR 0001](0001_gateway_native_assistant_v2.md) — Accepted — Gateway owns workflows and multimodal defaults; the assistant becomes a thin desktop shell with local UX state only.

- [ADR 0002](0002_iphone_release_stages.md) — Accepted — Credential-free iPhone CI, human-approved App Store Connect uploads, TestFlight validation and manual same-build App Store promotion.

- [ADR 0003](0003_unified_apple_product.md) — Accepted — One Store listing and archive for iPhone + independent Watch; generated Store composition and shared release ownership.

- [ADR 0004](0004_notes_inside_the_assistant_abstractnote_stays_a_service.md) — Accepted — Notes are captured and recalled in the assistant's Apple apps; AbstractNote stays a gateway service and web app; the Notes surface is gated by one status probe; nothing is copied between the two repositories again.

- [ADR 0005](0005_one_apple_project.md) — Accepted — One project and one product: the iPhone app is the container, the watch app its independent companion (`.watchkitapp`); the sign-in a Keychain item shared through the app group, and one push package (`AssistantPush`); amends ADR 0003.

- [ADR 0006](0006_macos_signing_and_distribution.md) — Proposed — The macOS app joins the Apple family as `ai.abstractframework.assistant.mac`, ships by Developer ID + notarization (not the Mac App Store), signing off by default and layered on a cross-platform app.

- [ADR 0007](0007_web_assistant.md) — Proposed — The Assistant on the web: a gateway app built from `web/`, one component library and tokens for every host behind one host interface, separate layouts; the same managed workflow, presence check only.

- [ADR 0008](0008_desktop_host.md) — Proposed — The desktop host stays PyQt5 for this cycle, polished toward the iPhone look (1056 + orb/tokens port); a Rust/Tauri shell is a gated one-week spike (0003) with measured exit criteria; the bundle id is kept whatever the host.

## Related Docs

- [../architecture.md](../architecture.md)
