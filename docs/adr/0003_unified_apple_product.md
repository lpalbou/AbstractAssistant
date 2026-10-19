# ADR 0003 — One AbstractAssistant product for iPhone and Watch

Status: Accepted
Date: 2026-10-19

## Context

The operator wants one AbstractAssistant App Store listing containing both clients. The existing
listing identifies the Watch carrier as `ai.abstractframework.assistant`. Local iPhone development
uses `ai.abstractframework.assistant.iphone`, which has a different device sandbox. The two client
projects and Swift packages have separate ownership and both export a module named
AbstractGatewayClient. Store composition must preserve existing product identities and developer
work while providing one tested, human-approved delivery artifact.

## Decision

- Use the existing Store root `ai.abstractframework.assistant` for the real iPhone app and embed
  `ai.abstractframework.assistant.watch` as an independent companion. Generate release-only Xcode
  projects from both canonical specs; do not change local developer bundle IDs or install data.
- The generated Watch target keeps canonical sources/settings, declares the iPhone companion and
  independent operation, and omits WKWatchOnly. Both apps use the iPhone project's marketing
  version and the same CI-generated build number.
- Compile the dependency-free Watch client sources as a generated static framework module to
  avoid SwiftPM's duplicate-product conflict. Reject manifest customizations that cannot be
  preserved by that composition. Keep both original packages' tests in the release gate.
- `.github/workflows/iphone.yml` owns combined CI, archive provenance and Store upload. It watches
  both clients. `.github/workflows/watch.yml` retains standalone developer checks and directs
  releases to the combined workflow; it cannot upload a Watch-only carrier.
- Verify both bundle identities, embedded executables, platforms, version agreement and companion
  independence before accepting a candidate. Keep ADR0002's main-only manual request, full native
  suite, required human environment approval and same-build promotion to public Store release.

## Consequences

One Store record and one archive deliver both experiences. Local developer and Store iPhone apps
have separate sandboxes; Store installation needs its own gateway sign-in. The Watch does not
require a running/installed iPhone companion to use its gateway. After the iOS companion is
published on the App Store, Apple's supported migration cannot return to a watch-only listing;
public publication remains a separate human action. Changes to Watch package build semantics
require updating the composition or choosing an explicit shared-module migration.

## References

- [Distribution guide](../../phone/iphone/docs/distribution.md)
- [ADR0002](0002_iphone_release_stages.md)
- [Backlog 1042](../backlog/planned/1042_unified_iphone_and_watch_store_delivery.md)
- [Apple TN3157](https://developer.apple.com/documentation/technotes/tn3157-updating-your-watchos-project-for-swiftui-and-widgetkit)
