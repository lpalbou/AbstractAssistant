# 1217 — Apple reachability hints and automation following

> Package: AbstractAssistant
> Created: 2026-11-14
> Status: Planned — implementation prepared
> Source: framework release recovery 1209; confirmed hidden Apple bug fixes

## Current code reality

The source recovery adds a narrowly classified sleeping-host hint, preserves a followed full
automation answer when a history refresh has only an excerpt, and follows a newly indexed run
after Run now. The send uses a fresh baseline and the captured connection; cancellation or a
connection revision change prevents a later POST or navigation.

## Scope

Recover the useful Apple fixes without reviving old UI trees or uploading an App Store build.
Certificate, ATS, URL/configuration, decoding and device-offline failures keep their own error.
The hint is a possibility, not a host-sleep diagnosis. A known old result is never selected as
the new run; gateways without run indices cannot provide this follow operation.

## Validation and acceptance

- [x] Independent source review: no remaining blockers after classification and connection guards.
- [x] Standalone Swift production-helper check: full/excerpt/empty history and run-index selection.
- [ ] Shared Swift package tests, phone tests and native simulator builds.
- [ ] Final coredoc, package gates, remote-main integration and release receipts.

Follow-up limits are tracked separately in proposed item 1218.
