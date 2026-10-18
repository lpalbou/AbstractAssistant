# 1039 — iPhone stop orb morph and contrast

> Package: abstractassistant
> Type: task
> Created: 2026-10-18
> Status: Completed
> Completed: 2026-10-18
> Priority: P1
> Labels: iphone, orb, animation, ux

Dependencies: 1038; checkpoint commit 7c5d9ec. ADR impact None — existing stop presentation only.

## Goal and current code reality

The user’s 22:50 screenshot shows a dim, shrunken stop orb and a stark white square.
AssistantOrb currently scales to 79%, halves ribbon opacity, and places the working animation
inside TimelineView. OrbContour already supports circle/squircle geometry, but the transition
needs a stable animatable presentation boundary independent of the moving audio/timeline.
Keep the same stop gesture, accessibility label and touch gating in OrbTouchSurface.

## Scope and acceptance

- [x] Commit existing iPhone work before refinement (checkpoint 7c5d9ec).
- [x] Clear, illuminated stop silhouette, recognizable stop mark and visible moving ribbons.
- [x] Continuous sphere-to-square and square-to-sphere morph, including interrupted transitions.
- [x] Preserve real voice deformation, reduced-motion behavior, tap target and safe stop gating.
- [x] Inspect native end states and intermediate frames, verify stop/cancel restoration, and
      install a normal signed iPhone build.

## Boundaries and validation

Only iPhone source/tests/docs and this local backlog. No Watch or AbstractFramework/root edits,
new APIs, server work, real agent requests or user-data mutations. Watch retains build priority.
Native render evidence plus an actual animated transition sequence and existing rapid activation
and stop/restore journeys. Verify no snapshot-only implementation and no test plugin in installed app.

## Completion report

Completed 2026-10-18. Original path `planned/1039_iphone_stop_orb_morph_and_contrast.md`;
final path `completed/1039_iphone_stop_orb_morph_and_contrast.md`.

Checkpoint committed first as `7c5d9ec`. AssistantOrb now uses a stable animatable OrbArtwork
outside TimelineView and one progress value for the shared contour, ribbon geometry, lighting,
scale and inset colored stop glyph. Working remains 96% of full size rather than 79%, keeps
its ribbons visible and gains a bright moving rim/pulsing halo. A 0.65s cubic easing morphs in
both directions; interrupting reverses the same presentation. Touch handling is unchanged.
Swift6 isolation is explicit on the value-semantic animation accessor. Audio levels continue
controlling ribbon deformation; Reduced Motion stops timeline motion and skips the transition.

Native **5/5 passed** with no runtime warnings. Parent and independent reviewer inspected source,
actual-size conversation screenshots, intermediate timed forward/reverse/interrupted frames,
restored sphere, high audio envelope and Reduced Motion. Earlier compile/test/easing iterations
are recorded in [evidence](../evidence/1039/README.md). Normal **0.6.20 (28)** signed app, no test
PlugIns, installed and launched on the iPhone. README/version/validation updated. Refinement
recorded in a separate scoped commit after the requested checkpoint.

Residual limits: snapshots sample the hosted native animation; no continuous video was reviewed.
Real audio capture/provider runs were not needed or performed for this presentation change.
No unresolved blocker, new architectural decision, follow-up or priority change. ADR impact None.
