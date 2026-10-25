# ADR Index

This directory records durable architecture decisions for AbstractAssistant.

## ADRs

- [ADR 0001](0001_gateway_native_assistant_v2.md) — Accepted — Gateway owns workflows and multimodal defaults; the assistant becomes a thin desktop shell with local UX state only.

- [ADR 0002](0002_iphone_release_stages.md) — Accepted — Credential-free iPhone CI, human-approved App Store Connect uploads, TestFlight validation and manual same-build App Store promotion.

- [ADR 0003](0003_unified_apple_product.md) — Accepted — One Store listing and archive for iPhone + independent Watch; generated Store composition and shared release ownership.

- [ADR 0004](0004_one_apple_project.md) — Accepted — One project and one product: the iPhone app is the container, the watch app its independent companion (`.watchkitapp`); shared sealed sign-in and push package; amends ADR 0003.

## Related Docs

- [../architecture.md](../architecture.md)
