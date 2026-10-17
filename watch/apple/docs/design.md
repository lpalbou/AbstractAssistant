# Design: AbstractAssistant for Apple Watch

Target device: Apple Watch Series 11, 46 mm (416 × 496 px) and 42 mm; watchOS 26. Dark palette
from abstractframework.ai (ground `#0a0a12`, cards `#15151f`, hairlines `#2a2a3a`, indigo, cyan,
green, amber, red as light). System font (SF, rounded) in the app; the mockups use Inter.

Mockups: `../design/screens/`. Prototype: `../design/prototype.html`.

## Principles

1. **One glance, one tap.** Every screen answers one question and offers at most three actions.
2. **Nothing consequential without a tap.** Raising the wrist, scrolling or a notification never
   approves anything. Double Tap is allowed only for approvals whose tool reads and does not
   change anything, and it is off by default for everything else.
3. **The run waits; the watch does not.** The watch shows the wait and leaves. The gateway keeps
   the state. Lowering the wrist never loses anything.
4. **Same session as the Mac.** "Continue on Mac" and "Discuss" open nothing on the watch; they
   mean the session is already there.
5. **Honest status.** Every screen says where the work runs ("on your Mac · local model") and how
   fresh the data is ("40 s ago").

## Screens

| # | Screen | Purpose | Actions |
|---|---|---|---|
| 01 | Sign in | First launch, after Sign out, or when the gateway ends the session: the AbstractFramework mark breathing in its glow, "User or email", the gateway (default gateway.abstractframework.ai, changeable). A user name asks for its token (checked with `GET /me`, which must name that user). A registered email gets an 8-digit code by email (`POST /session/recovery/request`, sent from the account's own mailbox, 10 minutes, single use), redeemed for a 30-day gateway session (`/session/recovery/redeem`, `remember: true`). | Continue · Sign in · Send a new code · Back |
| 02 | Home | The glance: how many runs wait for you (amber tile), Ask, Runs, Automations, last event. | Open waiting · Ask · Runs · Automations |
| 03 | Approval | One tool approval: tool name, risk pills, the command, run and workflow, how long it has waited, where else it is shown. | Allow once · Deny · Later · hold Allow for "allow all in this run" (0.2) |
| 04 | Approval done | Confirmation with the next step of the run and how many still wait. | back |
| 16 | Question | An `ask_user` wait: the question and its choices, or dictate an answer. | choice · dictate |
| 05 | Ask | The orb, alone: tap it and speak. Who answers (Assistant or an entity) one tap away; a small keyboard button opens the watch's text input. | tap the orb · keyboard · change responder |
| 06 | Listening | The orb becomes a cloud of 640 tiny points of light (after Apple's particle animations: pairing, Mindfulness) that flows over a sphere and gathers into a spiral disc and back, swelling, roughening and brightening with the voice it hears. Tap the orb, or stop speaking for 3 s, to send (nothing heard in 5 s: it stops). | tap the orb · Cancel |
| 07 | Thinking | The orb orbits; the step in words; what you said. You can lower your wrist: the answer comes back as a notification. | Cancel |
| 08 | Answer | The orb speaks the answer (it swells with the voice); the answer in markdown below. Tap the orb to pause the voice, tap again to resume exactly where it stopped; hold the orb (or the microphone button shown while paused) to reply. | tap: pause/resume · hold: reply · keyboard · New · Cancel (stops the voice) |
| 09 | Runs | Root runs with state (waiting, running, done, failed) and age. | open |
| 10 | Run detail | The last ledger records of a run, Cancel, Discuss. | Cancel · Discuss |
| 11 | Automations | Schedules with last result; Run now for a favourite. | Run now · open |
| 12 | Automation result | The last occurrence's answer. | Discuss on Mac · Mark read |
| 13 | Notification | Long-look notification for an approval with Allow once / Deny / Open (0.2, push). | Allow once · Deny · Open |
| 14 | Smart Stack | Rectangular widget "2 waiting for you", second widget with the last automation, corner complication with the count. | tap opens the first wait |
| 15 | Settings | Gateway, network, voice mode, haptics, Double Tap policy, sign out. | |

## Flows

### An approval arrives
1. A run reaches a `tool_approval` wait on the gateway.
2. The watch learns it (0.1: next poll, at most 15 s in the foreground; 0.2: push).
3. Haptic `.notification`; the Home tile turns amber; the complication count increments.
4. Approval screen. The person reads the tool, the risk pills and the command.
5. Allow once: haptic `.success`, `POST /commands` with `resume {approved: true}`, confirmation
   screen with the run's next step. Deny: `{approved: false}`. Later: nothing is sent, the wait
   stays, the tile stays amber.
6. The run continues on the gateway; the desktop assistant shows the same approval as answered.

### Ask by voice
1. Tap the orb: the microphone records 16 kHz mono WAV (`AVAudioRecorder`, metered). The first
   half second sets the room's noise floor; speech is 12 dB above it. A click haptic marks the
   moment it first hears you.
2. Send: a second tap on the orb, or 3 s without speech once you have spoken. Nothing heard in
   5 s ends the listening without sending. The WAV is uploaded as a session attachment
   (`POST /attachments/upload`) and transcribed by the gateway (`POST /runs/{session owner}/audio/transcribe`).
3. `POST /runs/start` with the default agent interface and `use_session_history` (an entity:
   `chat/{id}/turn`). The run's ledger stream is also handed to a background URLSession, which
   watchOS keeps open with the app suspended and which wakes the app when the gateway closes it.
4. The orb thinks; the step line names the latest ledger effect in words. A wait on a person on
   the run or on the agent's child run opens the approval or question; answering it returns to
   the orb, which follows the run again. "Allow all in this session" (on an approval opened from
   Ask) trusts the Ask session: later approvals of the current run are answered by the watch, and
   new runs carry `_runtime.tool_policy {auto_approve_max_risk_rank: 4, require_approval_tools:
   <the outreach tools>}`, so sends to someone else still ask. "tools allowed" shows beside who
   answers; New starts an untrusted session. Risk tiers come from `GET /discovery/tools`.
5. The answer: a notification haptic, the orb reads it aloud (`POST /runs/{id}/voice/tts/stream`,
   Settings → Speak answers), the markdown below. If the app is not on screen, the answer is
   posted as a notification (title: who answered, subtitle: what you said, body: the answer);
   opening it, or its Listen action, opens the answer and the orb speaks it.

### An automation reports
1. The automation's occurrence completes; `attention.unseen_count` increases.
2. Haptic only when the occurrence asked something, needs an approval, or failed. A plain
   completion is silent and appears on Home as the last event.
3. Automation result screen; Mark read calls `POST /automations/{id}/seen`; Discuss creates the
   discussion session on the gateway and tells the person it is open on the Mac.

## The orb

One mark stands for the assistant everywhere: the app icon, the Ask tile on Home, the hero of
the Ask screen and each row of the responder picker. Its motion is the state: it breathes when
a mass of pixel-size points that swirls continuously, in every state and at every size (after
Apple's particle pictures: the Watch pairing cloud, the dotted heart). About 2,400 points on the
Ask orb, in strands of 24 that trail one behind the other, turning around an axis leaning toward
you, the inside faster than the outside: the trails bend into the arms of a vortex. Dense near the
surface, sparse inside, a few strays outside: defined by its density, undefined at its edge.
Positions are a function of time, so the motion is continuous. Five brightness levels, drawn as one
filled path each, additive on black Idle, the light
breathes; listening, the light faces you and every syllable becomes a ring of larger, brighter dots
travelling outward, then the outer ring dims around the circle as the 3 s countdown to sending
(`design/anim/orb-listening.gif`, recorded with a real voice); it orbits three dots while thinking; while speaking it swells,
glows and rings with the measured loudness of the voice it plays. It is drawn with SwiftUI shapes
and a Canvas at any size, so a tile and a hero are the same view. The microphone is open only
while the dots are on screen: it starts with a tap and ends with a tap, 3 s of silence after you
speak, 5 s with nothing heard, or Cancel.

## Outreach approvals

A `send_*` tool (email, messages) is an outreach: the gateway always asks before a send to
anyone but you. The card shows the recipient and the subject, "View draft" opens the full body
verbatim from the tool arguments, and the primary action reads "Send it". Double Tap is off for
sends, as for destructive calls. The pill "sends to someone else" is derived from the tool name
until the wait payload carries the gateway's own tier (backlog 0015).

## Interaction rules

- **Haptics.** `.notification` for a new wait, `.success` after allow or send, `.failure` for a
  failed run or a denied token. Never more than one haptic per event.
- **Double Tap.** `handGestureShortcut(.primaryAction)` on Allow once, only when the approval is
  for a tool whose declared facts are read-only. The Settings screen shows the policy. 0.1 cannot
  know the tier from the wait payload, so 0.1 enables Double Tap for nothing; 0.2 reads the tier
  from the payload.
- **Long press on Allow** reveals "Allow all in this run" (0.2, needs gateway support). It is
  never the default action.
- **Wrist raise** refreshes the current screen; it never acts.
- **Offline.** The last known state stays visible with its age; actions are disabled with the
  reason ("gateway unreachable since 2 min").
- **Token rejected (401).** The app stops polling, shows "signed out by the gateway" and the
  pairing screen. It never retries in a loop: the gateway locks out an address after repeated
  failures.
- **Text size.** Titles 20–22 pt, body 14–16 pt, mono for tool names and commands at 12–14 pt.
  Two-line maximum for commands; the full command is on the run detail screen.

## Content rules

- Tool names and commands are shown verbatim, never paraphrased.
- Risk pills repeat the gateway's words (`Destructive`, `can delete`) when the payload carries
  them; otherwise the card shows the tool facts the app can derive, or nothing.
- Every answer screen says which run it came from and how long it took.
- The word "approve" is never used for a question; a question is answered.

## Approval states

An answer goes through visible states: *sending* (button disabled), *applied* (confirmation screen,
the run's next step), *rejected* (back to the list), *already handled* (the wait was answered on
another device: the card closes with that sentence and nothing is sent). An HTTP acceptance is never
shown as applied before the run has resumed. For destructive approvals, 0.2 adds the local owner
check (`deviceOwnerAuthenticationWithWristDetection`) before sending; it is a local gate, not an
identity proof to the gateway.

## Adopted from the cross-review (2026-10-16)

A second product spec reviewed the same idea with a wider lens. Adopted here: the approval state
machine above and stale-wait protection; minimal push payloads with a fetch before rendering;
never persisting the admin token on a watch; an entity and workflow picker on the Ask screen
(backlog 0021); a one-call inbox projection (0022); on-demand location (0023); and meeting
capture as the later flagship (0020), with "Record" and "Briefing" as the two home actions that
appear when those ship. Kept as research beyond this track: lived-context memory with evidence
grades, person and place views, proactive situational prompts.

## Accessibility

VoiceOver labels on every control, Dynamic Type for body text, high contrast by construction (all
text ≥ 4.5:1 on the ground), haptics mirrored by a visible change, no colour-only state (every
state has a word).
