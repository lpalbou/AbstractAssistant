# 1048 — Voice message review setting

Package256/256 passes. Preference regression covers absent-key upgrades, explicit opt-in,
re-instantiation/persistence and account isolation. Native16/16 passes, zero failures/skips:
11 existing voice-controller lifecycle/playback checks plus5 UI flows covering default review,
manual corrections before Send, existing typed draft preservation, explicit automatic sending,
touch-down cancellation, keyboard/suggestion cancellation and existing voice settings.

review-default.png, editable-transcription.png and automatic-enabled.png are exported native
screenshots; visually inspected. Tests use deterministic local microphone/HTTP/demo fixtures,
with no live model/automation execution. Standard transcription still uses the Gateway; review
gates the Assistant run, not the earlier transcription request.

Normal development build0.6.22(32) was installed and launched on the physical iPhone for user validation. These changes
remain uncommitted and unpushed. No Framework modifications or Store deployment.
