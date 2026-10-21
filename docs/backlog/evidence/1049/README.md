# 1049 — Speech and approval orb states

Package260/260 passes (179 AssistantKit,81 GatewayClient), including the additional1050
workflow regressions. Native22/22 passes with no failures, skips or runtime warnings:
5 rendering/Stop checks,12 voice lifecycle/playback checks and5 UI flows (including1050’s
non-Assistant creation flow). native-summary.json retains the Xcode result summary.

Verified delayed STT cancellation with no late draft, successful review after retry, delayed
TTS cancellation without microphone activation, successful playback after retry, and gaps
between streamed chunks returning to preparation before cancellation. A scoped child approval
opens Approve, Deny and Approve all from Guard rather than stopping the run.

Screenshots were exported from native tests and inspected at68 and136 points. guard-hand.png,
geodesic.png and stop-to-guard.png show endpoints and sampled geometry. guard-conversation.png,
tts-wait.png and stt-wait.png show production controls and action captions. Moving-frame and
Reduced Motion comparisons pass; existing native Stop midflight reversal remains green.
No continuous animation video or physical microphone sensitivity measurement was performed.

Debug/demo/ui-test fixtures delay synthetic speech only; no real microphone, model calls or
automation triggers are needed. Native builds yielded to independent Watch compilation;
interrupted attempts were not counted as completed application tests. Final1050 automation
regression3/3 also passes (see../1050/native-summary.json).

Normal development-signed0.6.22(33) was signature-verified, installed and launched on the
physical iPhone for user validation. development-install.json records the delivery outcome.
No Git commit/push, Store upload or Framework/Watch source modification for this item.
