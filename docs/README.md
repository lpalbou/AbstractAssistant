# AbstractAssistant Documentation

AbstractAssistant is a macOS-first tray assistant that runs as a thin client of AbstractGateway.
Start with [getting-started.md](getting-started.md), then use the pages below as references.

## Core guides

- [INSTALLATION.md](INSTALLATION.md) — install the package, the `voice` extra, and the optional macOS app bundle
- [getting-started.md](getting-started.md) — start a gateway, launch the palette, first turn, shortcuts
- [architecture.md](architecture.md) — components, the gateway boundary, sessions on the gateway (scope, kinds, cache, offline), automations and your event stream (diagram, follower, attention model, capability gate), the run lifecycle with live replies, the console sign-in hand-over
- [api.md](api.md) — CLI entry points and flags (including the console hand-over and `run --stream`), environment variables, run input pins, live reply events, gateway routes used (sessions and automations included), local files
- [faq.md](faq.md) — recurring questions and known limits
- [troubleshooting.md](troubleshooting.md) — symptoms, causes and fixes

## Topic deep dives

- [settings.md](settings.md) — every setting, where its value comes from (gateway default vs. this app) and where it is stored, including the workflow choice, Stream replies, appearance and About
- [voice.md](voice.md) — speaking replies, dictation, and the hands-free voice conversation loop
- [automations.md](automations.md) — scheduled tasks on the gateway: the Sessions | Automations tabs, Schedule this conversation, tool consent, runs as chat pairs, controls, answering waits by kind, Discuss, notifications and your event stream (the attention line, the menu-bar badge, one notification per item on a Mac), the capability gate, offline behavior, limits
- [macos-signing.md](macos-signing.md) — signing and notarizing the macOS app bundle (`build-macos-app --sign`, `--notarize`, `--dmg`, `--local-test`): one-time Apple setup, credentials, verification and the failures you can meet

## iPhone, Apple Watch and the web

- [../phone/iphone/README.md](../phone/iphone/README.md) — AbstractAssistant for iPhone (0.16.0, carries the watch app; each device signs in on its own, the sign-in a Keychain item shared with that device's notification extension; Apple push): conversations, scoped tools, automations, notifications and tab badges from your event stream, restorable image previews and voice playback; [architecture](../phone/iphone/docs/architecture.md), [release history](../phone/iphone/CHANGELOG.md), [troubleshooting, notifications and app updates](../phone/iphone/docs/troubleshooting.md), [testing/distribution](../phone/iphone/docs/distribution.md) and [build guide](../phone/iphone/BUILD.md) (the five targets, `scripts/deploy-phone.sh`)
- [../watch/apple/README.md](../watch/apple/README.md) — AbstractAssistant for Apple Watch (0.16.0, the iPhone app's independent companion, pre-release through TestFlight): voice around the orb with the work shown live, tools and workflow per conversation, images and recordings in answers, approvals, sessions with search and archive, automations, notifications from your event stream and Apple push, your avatar on the watch face; [build guide](../watch/apple/BUILD.md) (with the `--dump-notify` readout); its pages are indexed in [../watch/apple/docs/README.md](../watch/apple/docs/README.md)
- [../web/README.md](../web/README.md) — the Assistant on the web: a scaffold on the framework's app server, run by hand against a gateway, not a release

## Design records

- [adr/README.md](adr/README.md) — architecture decision records: the gateway-native boundary, the one Apple product and project, notes inside the Apple apps, macOS signing, the web assistant, the desktop host
- [backlog/overview.md](backlog/overview.md) — planned and proposed work

## Project

- [../README.md](../README.md) — overview and quick start
- [../CHANGELOG.md](../CHANGELOG.md) — release history
- [../CONTRIBUTING.md](../CONTRIBUTING.md) — development setup and tests
- [../SECURITY.md](../SECURITY.md) — vulnerability reporting
- [../CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md) — expected behavior and how to report concerns
- [../ACKNOWLEDGMENTS.md](../ACKNOWLEDGMENTS.md) — credits and lineage
