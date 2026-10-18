# 1040 — restored inline image previews

## Diagnosis and change

The screenshot’s generated image remained available from the gateway and could open full screen.
The inline row owned a cancellable SwiftUI task. Cancelling that task cancelled the network
transfer; a replacement consumer returned nil while the old transfer was still marked loading.
URLError.cancelled then appeared in the message, with no remaining task to decode its thumbnail.

MessageMediaController now owns one transfer per artifact. Row consumers share it and their
cancellation cannot cancel the transfer. Images enter the thumbnail cache before the transfer
returns, including full-screen-only requests. Conversation/account reset still cancels owned
work and rejects late cache/presentation results. Missing disposable files refetch; failures have
an explicit retry. Cache bounds and existing audio/reference behavior are retained.

## Validation and evidence

`native-summary.json`: **7 passed, 0 failed, no runtime warnings** on iPhone 17 Pro/iOS 26.5 simulator.
Native bundle: `phone/iphone/build/UITests-1792360128388865000.xcresult` (ignored build artifact).

Six MessageMediaTests cover:
- Cancel original row, join replacement thumbnail and full-screen consumers, complete delayed
  HTTP transport: one request, zero transport cancellations, ready thumbnail/preview, no error.
- Switch account/session during transport; cancel old request, preserve new same-artifact loading,
  and prevent stale preview presentation/cache writes.
- HTTP 503 failure then retry, direct-open thumbnail decoding and a purged temporary file refetch.
- Existing six-file cache cap and account cleanup, independent audio playback/pause/reset,
  and reuse of original gateway artifact identity without a copied upload.

PhoneUITests/testRestoredImageSurvivesColdRelaunchPreviewAndTabChanges launches twice, restores
history, waits for the inline image, opens/closes native preview, switches Inbox→Assistant and
asserts the image stays ready with no cancelled error. `cold-launch-1.png` and `cold-launch-2.png`
were inspected: image visible inline after both journeys. Hermetic transport and demo images only;
no real generation, uploads or user-conversation mutations.

The initial test compilation exposed a Swift6 actor-isolation issue in its async polling helper;
that helper is now MainActor-isolated. Pre-fix native execution was not completed while Watch
builds held priority. Final regression checks ran against the fix. Earlier native attempts yielded
to Watch activity; the final run and signed build passed under the strict priority guard.

Normal signed **0.6.21 (29)** installed on the physical iPhone: `normal-app.json`, `install.json`.
Installed app has no hosted-test plugins. Automatic launch was denied because the phone is locked
(`launch.json`, SBMainWorkspace Locked); user can reopen Assistant after unlocking. Physical
verification covers installation; behavior was checked with native simulator and delayed HTTP.
No Watch, AbstractFramework/root, server or package changes. The implementation was initially left uncommitted for review. The requested 2026-10-19
commit/push pass includes the fix, coredoc updates and this evidence; see `publication-checks.json`.

## Reproduce

```sh
python3 phone/iphone/scripts/build.py --ui-test 2332651D-D41D-4048-8121-3A6EA800D768 \
  --only-testing AbstractAssistantPhoneTests/MessageMediaTests \
  --only-testing AbstractAssistantPhoneUITests/PhoneUITests/testRestoredImageSurvivesColdRelaunchPreviewAndTabChanges
python3 phone/iphone/scripts/build.py --device 33A1ED53-E782-53EB-8858-F2BDA5811593 --team K3R4D6HP2A
```
