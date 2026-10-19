# 1042 — Unified iPhone and Watch App Store delivery

> Package: abstractassistant
> Type: task
> Created: 2026-10-19
> Status: Planned
> Completed: N/A
> Priority: P1
> Labels: iphone, watch, release, app-store

## Context and current code reality

The operator confirmed that iPhone and Watch are one AbstractAssistant product and should use
the existing App Store Connect listing. The currently published Watch carrier uses bundle ID
`ai.abstractframework.assistant`; its embedded watchOS app uses
`ai.abstractframework.assistant.watch`. watch/apple/project.yml defines a watch-only carrier
and WKWatchOnly=true. phone/iphone/project.yml defines a separate iPhone application with bundle
ID `ai.abstractframework.assistant.iphone`. The iPhone candidate verifier pins that separate ID.
The two Actions workflows archive/upload independently with different version sources.

Real iPhone release run 39190954901 passed contracts, package/native tests, archive creation and
artifact verification. After operator approval, Apple rejected export with exit70: no App Store
Connect record for ai.abstractframework.assistant.iphone. Existing AbstractAssistant TestFlight
0.2.0 build110 shown by the operator belongs to the Watch carrier. Creating another iOS record
would preserve the wrong product boundary; simply renaming the iPhone display name cannot fix it.

## Goal and expected outcome

Distribute the iPhone app and independently functioning Watch app through the existing
AbstractAssistant App Store Connect record. One approved, tested archive contains both device
apps and uses the existing carrier identity rather than creating another store listing.

## Scope

- Retain store root ai.abstractframework.assistant and watch identity root.watch.
- Replace the empty store carrier with the real iPhone app and embed the Watch app in its archive.
- Configure WKCompanionAppBundleIdentifier, remove the watch-only declaration for combined
  delivery, and retain independent Watch operation.
- Use matching marketing/build versions in both embedded applications.
- Preserve local developer install/data implications explicitly: changing the installed iPhone
  bundle identifier creates a different sandbox; plan migration or keep local debug identity
  separate from Store packaging.
- Unify approved Store upload ownership so a later Watch-only workflow cannot overwrite or
  attempt to regress the combined product. Preserve existing required human approval and
  same-build TestFlight-to-Store promotion boundaries.
- Validate archive identity/embedding/versions, both clients' relevant tests, signing and actual
  Apple processing. Avoid collecting or committing private keys.

## Non-goals and ownership

No framework/server changes or feature redesign. Do not include another agent's uncommitted Watch
source changes in an iPhone commit. Coordinate shared release/project changes before modifying
Watch-owned files; local Watch builds retain priority. No automatic App Review/public release.
Do not create a second App Store Connect record merely to make the old pipeline pass.

## ADR state

ADR0002's credential-free testing, human approval, provenance verification and staged promotion
remain applicable. Its separate-store-identity assumption needs an explicit amendment or successor
before implementing combined packaging. Apple TN3157 states that after publishing an iOS companion
on the App Store, rollback to a watch-only app is unavailable. Keep the public publication decision
behind the existing human release boundary.

## Validation

1. Generate/review the combined Xcode build graph without overwriting local Watch work.
2. Run meaningful iPhone and Watch checks; build an actual generic iOS Release archive.
3. Inspect both application executables, store/companion identifiers, supported platforms,
   independence declaration, matching versions and absence of test bundles.
4. Exercise failure cases for missing or mismatched Watch content and candidate provenance.
5. Verify human gate and Apple acceptance/processing; report TestFlight visibility separately
   from public App Store publication.
6. Update distribution docs, ADRs, build guides and public documentation indexes together.

## References

- [1041: CI and first release attempt](../completed/1041_iphone_ci_and_gated_apple_delivery.md)
- [First release failure](../evidence/1041/first-release-outcome.json)
- [ADR0002](../../adr/0002_iphone_release_stages.md)
- [Apple TN3157: adding an iOS companion to a watch-only app](https://developer.apple.com/documentation/technotes/tn3157-updating-your-watchos-project-for-swiftui-and-widgetkit)
