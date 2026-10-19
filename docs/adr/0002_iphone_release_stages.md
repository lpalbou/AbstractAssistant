# ADR 0002 — iPhone testing and Apple distribution stages

Status: Accepted
Date: 2026-10-19

## Context

Local iPhone development has its own bundle identifier. Store delivery combines iPhone and Watch
under the existing listing as defined in [ADR0003](0003_unified_apple_product.md). CI must test changes
without Apple credentials, while App Store Connect uploads need an explicit human decision.
The repository already protects Apple signing credentials with the `app-store` environment.
A separate staging app would need another bundle ID, app record and independent local data.
The client already lets each account choose its gateway, so a second binary is not required
for beta testing.

## Decision

1. PR, main and manual CI run without Apple credentials. Tests and an unsigned Release archive
   identify a specific source commit, marketing version, CI build number and archive digest.
2. Upload is opt-in through a manual workflow dispatch on main. Full native tests must pass.
   The existing protected `app-store` environment requires a human reviewer before the upload
   job can access its credentials. The job validates and signs the tested archive without rebuilding.
3. App Store Connect receives a normal distribution build for TestFlight. The upload does not
   submit App Review, enable public distribution or use the non-promotable Internal Only mode.
4. After beta validation, an operator selects that same processed build in App Store Connect,
   completes store metadata and review requirements, chooses manual release, submits for review,
   and separately releases the approved version. No second upload or rebuild is required.
5. No default production gateway is embedded. Local developer installs, disposable CI testing,
   TestFlight delivery and public App Store publication remain distinct stages.

## Consequences

A push cannot upload or publish an app. TestFlight and App Store share one bundle and candidate,
so production receives the tested binary. Apple processing, app metadata, review and final public
release remain visible human responsibilities. The upload environment is shared with Watch;
this decision does not change its protections or credentials. A separately installable staging
app can be added later if separate device data or app records become necessary.

## References

- [iPhone build guide](../../phone/iphone/BUILD.md)
- [GitHub deployment reviews](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/review-deployments)
- [Apple beta distribution](https://developer.apple.com/tutorials/develop-in-swift/test-your-beta-app)
- [Apple upload builds](https://developer.apple.com/help/app-store-connect/manage-builds/upload-builds)
