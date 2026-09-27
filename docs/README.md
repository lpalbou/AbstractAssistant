# AbstractAssistant Documentation

AbstractAssistant is a macOS-first tray assistant that runs as a thin client of AbstractGateway.
Start with [getting-started.md](getting-started.md), then use the pages below as references.

## Core guides

- [INSTALLATION.md](INSTALLATION.md) — install the package, the `voice` extra, and the optional macOS app bundle
- [getting-started.md](getting-started.md) — start a gateway, launch the palette, first turn, shortcuts
- [architecture.md](architecture.md) — components, the gateway boundary, sessions on the gateway (scope, kinds, cache, offline), automations (diagram, polling, capability gate), the run lifecycle with live replies, the console sign-in hand-over
- [api.md](api.md) — CLI entry points and flags (including the console hand-over and `run --stream`), environment variables, run input pins, live reply events, gateway routes used (sessions and automations included), local files
- [faq.md](faq.md) — recurring questions and known limits
- [troubleshooting.md](troubleshooting.md) — symptoms, causes and fixes

## Topic deep dives

- [settings.md](settings.md) — every setting, where its value comes from (gateway default vs. this app) and where it is stored, including the workflow choice, Stream replies, appearance and About
- [voice.md](voice.md) — speaking replies, dictation, and the hands-free voice conversation loop
- [automations.md](automations.md) — scheduled tasks on the gateway: the Sessions | Automations tabs, Schedule this conversation, tool consent, runs as chat pairs, controls, answering waits by kind, Discuss, notifications and the two polls, the capability gate, offline behavior, limits

## Design records

- [adr/README.md](adr/README.md) — architecture decision records (the gateway-native boundary)
- [backlog/overview.md](backlog/overview.md) — planned and proposed work

## Project

- [../README.md](../README.md) — overview and quick start
- [../CHANGELOG.md](../CHANGELOG.md) — release history
- [../CONTRIBUTING.md](../CONTRIBUTING.md) — development setup and tests
- [../SECURITY.md](../SECURITY.md) — vulnerability reporting
- [../CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md) — expected behavior and how to report concerns
- [../ACKNOWLEDGMENTS.md](../ACKNOWLEDGMENTS.md) — credits and lineage
