# Settings Reference

The Settings window (⌘, or the gear button) has seven pages. Each control below says where its
value comes from and where it is stored:

- **gateway** — read from the gateway and shown as-is; the assistant never writes it
- **this app** — stored in `~/.abstractassistant/preferences.json` on this Mac and sent with each
  request; the gateway's shared configuration is never changed
- **connection** — stored in `~/.abstractassistant/gateway_connection.json`

Gateway defaults apply whenever an override is empty. See [architecture.md](architecture.md) for
the boundary and [faq.md](faq.md) for common questions.

## Connection

| Control | Meaning | Stored |
|---|---|---|
| Status | Who you are on the gateway (user, tenant, roles, auth mode, routing) and the gateway version, probed off the GUI thread | gateway |
| Gateway URL | Where runs, tools and speech execute | connection `base_url` |
| Sign-in mode | Bearer token (shared, local or operator-run gateways) or Gateway session (one user, personal token exchanged for a session) | connection `auth_mode` |
| Bearer token / Gateway user / Gateway user token | Credentials for the chosen mode; the eye button reveals the bearer token | connection |
| Keep the gateway session after this app closes | Session mode only | connection `remember_session` |

`Connect` saves and reconnects. `Sign out` clears the local sign-in state (and logs a gateway
session out).

## Models & reasoning

| Control | Meaning | Stored |
|---|---|---|
| Reasoning effort | Gateway default, none, minimal, low, medium, high, extra high. The ladder comes from the gateway contract (`thinking_control.values`). Sent with every run as `_runtime.thinking`; Gateway default sends nothing. Levels the chat model's capability card does not list are greyed out | this app `reasoning_effort` |
| Applies-to line | The chat model that will serve the next turn (gateway default or this app's override) and the reasoning levels that model reports, when the gateway has a capability card for it | gateway |
| Model routes | One row per route the assistant drives: chat model, voice output, voice input, image generation, image edit, image upscale, video generation, image → video, music, sound effects | this app `route_overrides` |

For each route the state line shows two facts: the gateway default (with the route it is derived
from when the gateway says so) and what this app uses. `Use gateway default` stores nothing;
`Override for this app` requires both a provider and a model. Provider, model and voice catalogs
are read from the gateway. The chat route accepts an optional provider base URL; the voice route
adds a voice picker. `Reset to gateway` drops the override.

Where overrides travel: the chat model rides the run input (top-level pins and `_runtime`);
voice overrides ride each speech request; image, video, music and sound overrides ride the
managed workflow's input pins. A level the model cannot honor is mapped by AbstractCore to the
nearest supported level.

## Voice

| Control | Meaning | Stored |
|---|---|---|
| Text → speech / Speech → text | The engines that speak and listen, with "gateway default" or "this app"; `Change…` opens the route in Models & reasoning | gateway / this app |
| Output device | The Mac's current default output and volume; playback follows the system output | read locally |
| Speak replies automatically | Auto-speak final answers (also the speaker toggle in the header) | this app `auto_speak` |
| Voice latency | Balanced / Faster / Higher quality, applied only when the gateway advertises the TTS quality control | this app `voice_quality` |
| Send each utterance automatically | Conversation mode: send what you say as a turn; off, words land in the message box | this app `voice_auto_send` |
| Ask for short, spoken-style replies | Adds a voice-style instruction to each request while a conversation runs | this app `voice_spoken_replies` |
| Barge-in | Pause the mic while the assistant speaks (speakers) or keep it open so "stop" interrupts (headphones) | this app `voice_mode` (`wait` / `full`) |

See [voice.md](voice.md) for how the conversation loop behaves.

## Workspace

| Control | Meaning | Stored |
|---|---|---|
| Gateway policy | Your effective posture, whether client scope grants are allowed, gateway-allowed and blocked paths, the access modes offered, mounts and launch-folder trust | gateway (`/workspace/policy`, `/workspace/policy/self`) |
| Workspace root | The folder the run's file tools work in. Empty means the gateway picks a folder for the first run of a chat and the assistant reuses it for later turns of that chat. The `Choose…` picker appears only when the gateway runs on this Mac; for a remote gateway, type the path as it exists on the gateway's host | this app `workspace_root` |
| Access mode | Server-managed (send nothing) or one of the modes the gateway offers: workspace only, workspace + allowed folders, any absolute path except ignored ones | this app `workspace_access_mode` |
| Allowed folders | Extra folders the tools may reach in "workspace + allowed folders" mode. Absolute paths (or `~`) only; adding one switches the access mode when needed | this app `workspace_allowed_paths` |

The gateway resolves these paths on its own host and clamps them to its policy. When the policy
forbids client scope grants, Save refuses entries outside the gateway-allowed paths and names
them. A grant the gateway still rejects makes the run start fail; the palette then shows
"Not sent" with the gateway's reason and puts your message back in the composer.

## Tools & permissions

| Control | Meaning | Stored |
|---|---|---|
| Tool mode note | The gateway's tool execution mode (approval, local, passthrough, delegated) | gateway |
| Per-tool Off / Auto / Ask | Off never offers the tool to the model; Auto pre-approves it on this Mac, even where the gateway would ask; Ask prompts every time. The gateway's own default is marked in the tooltip. Save stores only the tools that differ from the gateway default | this app `tool_preferences` |
| Risk chip and sentence | The gateway's risk tier (reads only, makes changes, reaches outside, destructive) and capability facts (writes, can delete, sends messages, reaches remote services, captures the environment) | gateway |
| Disabled on gateway | Tools the gateway has turned off; they are never offered to a run | gateway |
| All auto / All ask | Set every available tool of a toolset at once. All auto leaves outreach and destructive tools on Ask; set those to Auto one by one | this app |
| Use gateway defaults | Restore each tool to the gateway's approval default (press Save to keep) | this app |

Off and Ask narrow what the gateway allows; Auto pre-approves on this Mac. Tools you never
configured follow the gateway's approval default. "Always allow … on this Mac" in the approval
sheet is offered for the observe and act tiers only. "Allow all enabled tools in this chat" is
always offered, and it reaches exactly as far as the batch you granted it on: granted on a
read-only batch it keeps asking for outreach and destructive calls, granted on a destructive
batch (the item then says so) it covers everything this page has not switched off, for that chat.

## Window & shortcuts

| Control | Meaning | Stored |
|---|---|---|
| Enable the global summon shortcut / Shortcut | Global hotkey (default `cmd+shift+space`), subject to macOS Accessibility permission | this app `hotkey_enabled`, `hotkey_sequence` |
| Popover width / Expanded height / Screen edge gap | Palette size, honored up to the screen; the transcript takes the remaining height | this app `window_width`, `window_height`, `bottom_offset` |

In-app shortcuts: Return sends, Shift+Return adds a line, Esc stops speech then hides, ⌘. stops
the run (does nothing when no run is active), ⌘N starts a new chat (refused while a run is
active), ⌘, opens Settings, ⌘⇧V starts or ends a voice conversation. In the approval sheet:
Return allows once, or activates the Deny / Decide later button when one of them has focus; ⌘D
denies; Esc decides later.

## About

Package version, the gateway stack versions the gateway reports (gateway, runtime, core, voice,
vision, memory, contract version), the resolved workflow, the data folder (with Reveal in Finder)
and `Copy diagnostics` (versions, connection without secrets, workflow, preferences).

## Preferences file

`~/.abstractassistant/preferences.json` holds every "this app" value above. Missing keys keep
their defaults: gateway defaults for models and reasoning, no workspace grant, auto-send and
spoken-style replies on, microphone paused while the assistant speaks. Each chat's `session.json`
may also carry the `workspace_root` the gateway granted to that chat.
