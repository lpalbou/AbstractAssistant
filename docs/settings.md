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
| Workflow | Which agent workflow each new turn runs. First row: **Gateway default → name @version**, the gateway's default for `abstractassistant.agent.v1` (with its source as the gateway reports it), or **Gateway default → Built-in orchestrator** when the gateway sets none. Then every workflow in the catalog that declares the assistant interface, at its latest version. The choice applies from the next turn; a running turn keeps its workflow | this app `workflow` (`"@default"`, or the chosen bundle and flow without a version) |
| Reasoning effort | Gateway default, none, minimal, low, medium, high, extra high. The ladder comes from the gateway contract (`thinking_control.values`). Sent with every run as `_runtime.thinking`; Gateway default sends nothing. Levels the chat model's capability card does not list are greyed out | this app `reasoning_effort` |
| MTP depth | Gateway default (inherit), Off, or a depth advertised for the selected provider/model. Sent as `_runtime.speculation`; Off sends `false`, and inheritance omits the key | this app `speculation` |
| Stream replies | Gateway default, On or Off. On shows the answer while the model writes it; Off shows it when it is finished. Sent with every run as `_runtime.stream`: Off always sends `false`; On sends `true` only when the gateway offers live replies (`streaming.deltas` in its discovery) — otherwise On is listed as **On — not supported by this gateway**, nothing is sent, and a chat that runs with On saved shows one note saying so. Gateway default sends nothing, so the gateway's own streaming default decides — the list shows it, e.g. **Gateway default (Off)** | this app `stream_replies` (`gateway_default`, `on`, `off`) |
| Applies-to line | The chat model that will serve the next turn (gateway default or this app's override) and the reasoning levels that model reports, when the gateway has a capability card for it | gateway |
| Model routes | One row per route the assistant drives: chat model, voice output, voice input, image generation, image edit, image upscale, video generation, image → video, music, sound effects | this app `route_overrides` |

Each route has Provider and Model lists, plus Reasoning and MTP depth for the chat route. The first
item of every one of them is **Gateway default**. There is no mode to switch and no Apply: a
choice applies the moment it is made, and selecting `Gateway default` for the provider is how a
route goes back to following the gateway. An override needs both a provider and a model, so a
provider on its own stores nothing and the page says which half is missing.

The state line above the lists shows two facts: the gateway default (with the route it is derived
from when the gateway says so) and what this app uses. Provider, model and voice catalogs are read
from the gateway; when it cannot be reached the lists hold `Gateway default` alone, say why, and
re-fetch when you open them again — a previously saved choice stays selected and marked `(saved)`
rather than being discarded. The chat route accepts an optional provider base URL; the voice route
adds a voice picker.

Where overrides travel: the chat model rides the run input (top-level pins and `_runtime`);
voice overrides ride each speech request; image, video, music and sound overrides ride the
managed workflow's input pins. A level the model cannot honor is mapped by AbstractCore to the
nearest supported reasoning level.

### Live replies

With streaming on, the reply appears in a live bubble that grows as the model writes; the
finished answer then takes its place (the live text is never kept as a second copy). The model's
reasoning, when it shares it, goes in a collapsed **Thinking** area inside that bubble and is never
mixed into the reply. A bubble written by a sub-agent is labelled **sub-agent · step name**.
The transcript follows the text while you are at the bottom and stays put if you have scrolled up.

The live text is a preview. If the gateway had to drop the oldest part of a very long reply, the
bubble says so; the finished answer is always complete. If a step fails or is stopped, its bubble is
removed and the status line says why. Some steps cannot stream (a step that returns structured
output, a remote model server, a provider that cannot stream or cannot report token usage while
streaming); the status line says which, and that answer appears when it is finished. After a
reconnection the bubble picks up where the model is.

MTP is native multi-token prediction, not a reasoning level. Its choices come from the
gateway's execution capability card, not the model's name. The app shows whether the head is
ready or a reload is needed; an unavailable saved choice remains visible. Selecting a depth
requests that exact depth with `require_acceleration=true`: the execution host must honor it
or report an error, not silently run without MTP. This control neither downloads a head nor
changes the gateway's shared default. Leaving it on Gateway default follows the Core policy
on the execution host (fresh configurations use depth 2 only for compatible models).

## Voice

| Control | Meaning | Stored |
|---|---|---|
| Text → speech / Speech → text | The engines that speak and listen, with "gateway default" or "this app"; `Change…` opens the route in Models & reasoning | gateway / this app |
| Output device | Which speaker replies play on. A list of the devices this Mac can play to, rebuilt each time it is opened, with `System default` first; `Test` plays a tone on the selected one. AirPlay targets are not offered to apps by macOS — pick them in the Sound menu and leave this on `System default` | this app `audio_output_device` (a CoreAudio UID) |
| Speak replies automatically | Auto-speak final answers (also the speaker toggle in the header) | this app `auto_speak` |
| Voice latency | Balanced / Faster / Higher quality, applied only when the gateway advertises the TTS quality control | this app `voice_quality` |
| Send each utterance automatically | Conversation mode: send what you say as a turn; off, words land in the message box | this app `voice_auto_send` |
| Ask for short, spoken-style replies | Adds a voice-style instruction to each request while a conversation runs | this app `voice_spoken_replies` |
| Barge-in | A list: pause the mic while the assistant speaks (speakers) or keep it open so "stop" interrupts (headphones) | this app `voice_mode` (`wait` / `full`) |

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
| Width / Expanded height / Screen edge gap | Palette size; the transcript takes the remaining height. Defaults: width 650 px, height 286 px, gap 28 px. Settings accepts a width of 420–2000 px and a gap of 0–200 px; the only further limit is the screen the window is on (width up to 62% of it, gap up to a quarter of its smaller side). The gap is the space kept between the window (and Settings) and the screen edges it sits against; 0 puts it flush with the edge | this app `window_width`, `window_height`, `bottom_offset` |

Updating from a version that used the old defaults (width 500 px, gap 18 px) moves you to the new
ones once; a width or gap you had changed yourself is kept.

In-app shortcuts: Return sends, Shift+Return adds a line, Esc stops speech then hides, ⌘. stops
the run (does nothing when no run is active), ⌘N starts a new chat (refused while a run is
active), ⌘, opens Settings, ⌘⇧V starts or ends a voice conversation. In the approval sheet:
Return allows once, or activates the Deny / Decide later button when one of them has focus; ⌘D
denies; Esc decides later.

## About

Also reachable from the menu-bar icon's **About AbstractAssistant…** item.

- The application and its version, part of AbstractFramework (with the framework website), the
  author, copyright and licence, and links to the website, source, documentation, issue tracker,
  feedback form and contact address.
- The gateway stack versions the gateway reports (gateway, runtime, core, voice, vision, memory,
  contract version), the workflow the next turn runs, the workflow the last turn ran as the
  gateway resolved it, and the data folder (with Reveal in Finder).
- `Copy diagnostics` copies the same facts plus the connection (without secrets) and preferences.

## Preferences file

`~/.abstractassistant/preferences.json` holds every "this app" value above. Missing keys keep
their defaults: gateway defaults for models, reasoning and reply streaming, no workspace grant, auto-send and
spoken-style replies on, microphone paused while the assistant speaks. Each chat's `session.json`
may also carry the `workspace_root` the gateway granted to that chat.
