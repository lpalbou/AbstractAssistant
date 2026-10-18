# 1039 — stop orb evidence

Checkpoint requested before refinement: `7c5d9ec` (includes completed iPhone item 1038).
Refinement changes only iPhone presentation, render tests, version/docs and package-local backlog.

## Result

Normal **0.6.20 (28)** signed app installed/launched on the physical iPhone. See `normal-app.json`,
`install.json`, `launch.json`. No hosted-test plugins in the installed app.

**Five native tests passed**, zero failures/runtime warnings: `native-summary.json`.
Native test bundle: `phone/iphone/build/UITests-1792357335365726000.xcresult` (ignored build artifact).
`OrbRenderingTests` checks rapid accessibility stop gating, real rendered voice/stop contours,
hosted animated forward/reverse/interrupted transitions and restored endpoint pixel similarity,
plus Reduced Motion artwork. `PhoneUITests/testWorkingOrbIsTheOnlyStopAndReturnsAfterCancellation`
checks the actual composer stop, cancellation and return to the microphone-ready state.

## Visual evidence

- `conversation-working.png`, `conversation-stopped.png`: actual demo conversation UI.
- `sphere.png`, `morph-entering.png`, `stop.png`, `morph-returning.png`,
  `morph-interrupted.png`, `sphere-restored.png`: real UIHosting window snapshots while the
  same AssistantOrb changes working state, shown at 68pt and 136pt. Snapshot time includes
  draw/attachment overhead; these are sampled animation frames, not a continuous recording.
- `voice-envelope.png`: high real-input-level rendering; test varies supplied levels 0.2/0.85/0.1.
- `reduced-motion.png`: static artwork with reduced motion enabled at the artwork boundary.
- `review.md`: independent source/frame review; parent inspected all final images too.

Initial compile checks caught Swift6 Animatable main-actor conformance and a read-only accessibility
environment key in the test. Conformance now exposes only its value-semantic progress accessor
as nonisolated; reduced-motion artwork is tested directly. Initial native run passed 4/5; PNG-byte
endpoint equality failed despite visually matching images. Replaced it with normalized sRGB
pixel difference (<0.5/255 mean) to accommodate GPU gradient rasterization. First spring settled
its shape too quickly in inspected frames; final easing is a 0.65s cubic timing curve.

## Reproduce

```sh
python3 phone/iphone/scripts/build.py --ui-test 2332651D-D41D-4048-8121-3A6EA800D768 \
  --only-testing AbstractAssistantPhoneTests/OrbRenderingTests \
  --only-testing AbstractAssistantPhoneUITests/PhoneUITests/testWorkingOrbIsTheOnlyStopAndReturnsAfterCancellation
python3 phone/iphone/scripts/build.py --device 33A1ED53-E782-53EB-8858-F2BDA5811593 --team K3R4D6HP2A
```

One low-priority iPhone build at a time, isolated DerivedData. Verification permitted only the
already-idle Watch test PID 37754, with CPU/compilation/memory-pressure guard retained. No Watch
process/product/index changes, backend/framework writes, real agent requests or user data mutations.
Physical verification here is install/launch; interactive behavior was checked on the simulator.
