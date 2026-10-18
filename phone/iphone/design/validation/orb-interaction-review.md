# Orb interaction review — 0.6.1 (9)

The conversation contains one progress row. The floating orb becomes a rounded square
with a stationary Stop glyph during an Assistant/entity turn; surrounding ribbons keep
moving. Tapping it requests cancellation, and normal voice interaction returns after
confirmation. The keyboard editor still expands and hides the orb while editing.

Microphone and playback energy deform the ribbons' curvature, spacing, angle and stroke.
A soft compression knee retains differences between loud syllables. Silence detection
continues to use independent raw microphone power and three observed quiet seconds.
Reduce Motion freezes geometry/rotation while preserving the distinct Stop shape and
level-driven light.

## Evidence

- 80 package tests pass: 52 phone state/feature cases and 28 inherited client/model cases.
  Cancellation checks cover delayed IDs, repeated Stop, late entity opens/policy/turn
  replies, lease conflicts, unknown-start recovery and stopping a subsequent turn.
- 19 native tests pass (15 hosted and four UI) with zero runtime warnings, on the final
  source: `build/UITests-1792290198428358000.xcresult`. The full native run was interrupted
  when another Xcode build started; the phone guard yielded priority. The completed
  targeted run covers conversation/navigation, the only active answer's playback controls,
  local voice cancel/automatic send, and the working-square/stop/restoration interaction.
- Actual AVAudioPlayer WAV playback produced an interior energy range of 0.4437–0.8648
  (delta 0.4211); see [sampled trace](wav-playback-energy.csv). Hosted tests also verify
  microphone-envelope response, local cancellation with zero HTTP calls and one upload/
  transcription after three measured quiet seconds.
- Native render comparisons: [quiet](../screenshots/orb-quiet.png),
  [loud](../screenshots/orb-loud.png), [square detail](../screenshots/orb-stop-detail.png).
  The parent and independent UX reviewer inspected the actual renders.
  Final interaction screenshots: [working](../screenshots/orb-working.png) and
  [restored after Stop](../screenshots/orb-restored.png).

## Review boundaries

Two adversarial agents reviewed behavior and usability. The technical reviewer implemented
an isolated cancellation change and package tests; the parent and other reviewer inspected
that implementation. Rendered UI tests use the phone simulator and controlled demo data.
The signed 0.6.1 (9) build passed strict code-signature verification and installed on the
physical iPhone; CoreDevice reports version 0.6.1, build 9. Microphone sensitivity and the
feel of live audio on that device still require hands-on confirmation.

Entity cancellation may wait for the gateway's writer lease to yield; the app keeps
Stopping visible and retries closure. Older entity APIs can dismiss an eventual reply but
cannot interrupt work already sent, which the app reports explicitly. Root cancellation
uses the existing gateway command and waits for terminal state. No gateway or Watch code
changes are required for this phone refinement.
