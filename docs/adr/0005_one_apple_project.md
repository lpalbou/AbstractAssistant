# ADR 0005 — One project for the AbstractAssistant iPhone and Watch apps

Status: Accepted
Date: 2026-10-25
Amends: [ADR 0003](0003_unified_apple_product.md) (the generated Store composition and the bundle ids)

## Context

ADR 0003 kept two developer projects and generated a release-only composition for the Store. The
operator decided on 2026-10-25 that the iPhone app and the watch app are ONE product named
AbstractAssistant: the iPhone app is the container, the watch app its companion ("Watch App for iOS
App"), one sign-in shared between them, one push mirrored to the wrist by Apple (framework backlog
1049). Apple mirrors an iPhone alert to the watch and de-duplicates by `apns-collapse-id` only for a
watch app and its own iOS app, so the family must be real, not composed at release.

## Decision

- One XcodeGen spec, `phone/iphone/project.yml` (`AbstractAssistant.xcodeproj`). The iPhone project
  absorbs the watch targets; the watch sources stay in `watch/apple` (least churn: no file moves, the
  iPhone's scripts, CI and archive name keep working; the watch scripts point at the new project).
- Bundle ids: iOS app `ai.abstractframework.assistant`; watch `ai.abstractframework.assistant.watchkitapp`;
  complication `….watchkitapp.orbclock`; notification service extensions
  `ai.abstractframework.assistant.notifications` and `….watchkitapp.notifications`. The developer
  builds use the Store ids; `….assistant.iphone` and `….assistant.watch` are retired.
- The watch app declares `WKCompanionAppBundleIdentifier` and `WKRunsIndependentlyOfCompanionApp`
  (it signs in and runs without the iPhone); `WKWatchOnly` and the empty container target are gone.
- The watch's gateway client compiles in the project as a static framework (module
  `AbstractGatewayClient`); the iPhone's AssistantKit package exports a module of the same name and
  SwiftPM refuses two packages with one target name in one graph. Both packages keep their own tests.
- A new package, `phone/iphone/Packages/AssistantPush`, is shared by both apps and both extensions:
  the sign-in in a protected file in the app group `group.ai.abstractframework.assistant` (no OS
  keychain; plain JSON under the device's Data Protection, excluded from backups: backlog 1053, 2026-10-26;
  it was sealed with a key file beside it until then), the
  push registration, the iPhone-to-watch sign-in handoff and how a push is rendered.
- One version for the family (`MARKETING_VERSION` 0.16.0, one build number).

## Consequences

- The apps carry explicit entitlements (`aps-environment`, time-sensitive notifications, the app
  group), so ADR 0003's unsigned-candidate CI step refuses by design: a Store candidate now needs an
  archive-signing configuration.
- The gateway's packaged push topics must list the new ids (`ai.abstractframework.assistant`,
  `ai.abstractframework.assistant.watchkitapp`); until then registrations are refused (422).
- Installs of the retired ids keep their own sandbox: people sign in once in the new app.

## References

- [BUILD](../../phone/iphone/BUILD.md), [watch BUILD](../../watch/apple/BUILD.md)
- Framework backlog 1049 (Apple push), `abstractgateway/docs/push.md`
