# 1044 — Installed version and supported app updates

> Package: abstractassistant
> Type: task
> Created: 2026-10-19
> Status: Completed
> Completed: 2026-10-19
> Priority: P2
> Labels: iphone, reliability

## Current code reality

Settings shows only marketing version in a footer. It has no build number or update guidance. TestFlight manages beta binary installation and its automatic-update preference.

## Scope and expected outcome

Show version/build and installation channel, provide an explicit Check for updates destination and automatic-update instructions for TestFlight/App Store; development installs use developer guidance. Never ship Apple team keys or claim to read/change TestFlight automatic-update state. Update public docs, changelog and both LLM indexes.

## Validation

Test installation-channel routing and metadata fallback; native Settings navigation and update instructions; verify links and Apple-supported update behavior. No framework version bump or public App Store release.

## ADR state

Existing thin-client architecture and ADR0002/0003 delivery boundaries apply; no new durable architecture decision.

## Completion report — 2026-10-19

Settings shows version/build, with a Version & updates destination. StoreKit-verified
transaction environment distinguishes Store/TestFlight where available; local developer
installs retain developer guidance. The explicit update button opens Apple’s update flow.
Automatic updates are configured in TestFlight/iPhone Settings, with clear instructions and
links; no fake local update-permission switch or App Store Connect key is shipped.
Native UI guidance check passes, pure model destination/fallback tests pass, and the physical
iPhone confirms itms-beta URL support. Version0.6.22/build30; CI overrides build numbers.
Coredoc updates include README, changelog, architecture, troubleshooting and both LLM indexes.
See ../evidence/1043/README.md for shared validation/screenshots. No new ADR needed. New source
must pass the existing pipeline and human approval before it becomes a TestFlight update.
Original planned path moved to completed with the same filename.
