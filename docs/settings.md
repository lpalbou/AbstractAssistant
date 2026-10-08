# Settings Reference

The Settings window (⌘, or the gear button) has eight pages: Connection, Models, Workflow, Voice,
Workspace, Tools, Appearance and About. Each control below says where its
value comes from and where it is stored:

- **gateway** — read from the gateway and shown as-is; the assistant never writes it
- **this app** — stored in `~/.abstractassistant/preferences.json` on this Mac and sent with each
  request; the gateway's shared configuration is never changed
- **connection** — stored in `~/.abstractassistant/gateway_connection.json`
- **your account** — stored by the gateway for the signed-in account and shared with every device
  and app of that account (`GET`/`PUT /api/gateway/accounts/me/preferences`)

Gateway defaults apply whenever an override is empty. See [architecture.md](architecture.md) for
the boundary and [faq.md](faq.md) for common questions.

On/off settings are switches labelled by the feature, the same control as the other
AbstractFramework apps: on shows an accent track with a check mark and a bold label, off is plain.
A switch that is a saved setting applies the moment you flip it, and the line at the bottom of the
page names the new state ("Replies are spoken automatically."); if the save fails, the switch
flips back and the line says so. No page has a Save button: switches, lists and fields apply as
they change (a field when you press Return or leave it), and a change that cannot be stored or
that the gateway refuses says "Not saved." with the reason. The Connection page keeps its labelled
actions (**Connect**, **Sign out**, **Reload status**).

## Connection

| Control | Meaning | Stored |
|---|---|---|
| Status | Who you are on the gateway (user, tenant, roles, auth mode, routing) and the gateway version, probed off the GUI thread | gateway |
| Gateway URL | Where runs, tools and speech execute | connection `base_url` |
| Sign-in mode | Bearer token (shared, local or operator-run gateways) or Gateway session (one user, personal token exchanged for a session) | connection `auth_mode` |
| Bearer token / Gateway user / Gateway user token | Credentials for the chosen mode; the eye button reveals the bearer token | connection |

Sessions belong to the gateway: the Assistant never decides how long a sign-in or a conversation
session is kept (0.12.1 removed the "Keep the session after this app closes" switch).

`Connect` saves and reconnects. `Sign out` clears the local sign-in state (and logs a gateway
session out).

## Models & reasoning

| Control | Meaning | Stored |
|---|---|---|
| Reasoning effort | Gateway default, none, minimal, low, medium, high, extra high. The ladder comes from the gateway contract (`thinking_control.values`). Sent with every run as `_runtime.thinking`; Gateway default sends nothing. Levels the chat model's capability card does not list are greyed out | this app `reasoning_effort` |
| MTP depth | The shared route picker's MTP choice, with the same words as AbstractCode and the gateway console: **Gateway default** (with the gateway's own depth, e.g. **Gateway default (depth 2)**), **Off**, or **Depth N** for each depth the gateway advertises for the selected provider/model. Configurable when the gateway reports the model MTP-capable; for a model it reports without MTP the list is shown disabled with the gateway's sentence (a saved depth stays changeable, marked **(saved; not available)**). Sent as `_runtime.speculation` (`{mode: "native_mtp", num_draft_tokens, require_acceleration: true}`); Off sends `false`, and inheritance omits the key | this app `speculation` |
| Stream replies | A switch, on by default: on shows the answer while the model writes it; off shows it when it is finished. Streaming is this app's choice, so every run says so explicitly as `_runtime.stream` — `true` when the switch is on and the gateway offers live replies (`streaming.deltas` in its discovery, read from the cached answer, never fetched per turn), `false` otherwise. There is no "Gateway default": the gateway's own **Streamed replies** setting (Workflows → Settings in the console) applies only to clients that do not say. When the switch is on but the gateway says it has no live replies, the line under it says so and a chat shows one note | this app `stream_replies` (`on`, `off`; an older `gateway_default` loads as on) |
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
re-fetch when you open them again — a saved choice stays selected and marked `(saved)`
rather than being discarded. The chat route has an optional **Provider base URL** row (a plain row,
no "Advanced" disclosure); the voice route adds a voice picker.

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
removed and the status line says why; if the model call had to be run again, the status line says
**Reply restarted** and the new attempt gets its own bubble. Some steps cannot stream (a step that returns structured
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

## Workflow

The page right after Models. It sets the workflow the Assistant runs for each new turn; a turn
already running keeps its workflow. The choice applies the moment you pick it (there is no Save);
if it cannot be stored, the line at the bottom of the page says "Not saved." followed by the reason
(the gateway's sentence when the gateway refuses the workflow).

| Control | Meaning | Stored |
|---|---|---|
| Runs | Which agent workflow each new turn runs. First row: **Gateway default (name)**, the gateway's default for `abstractassistant.agent.v1` in the gateway's own words (the console and AbstractCode show the same), with the line underneath naming where the gateway says the setting comes from; **Gateway default (Built-in orchestrator @version) — gateway reports: reason** when the gateway sets none; **Gateway default (unavailable)**, with the reason, when neither exists. Then every workflow in the catalog that declares the assistant interface, as **name @version — bundle**, the app's own as **Built-in orchestrator @version**; a chosen workflow always runs its latest version. The built-in orchestrator shows no number until the app has published a real version of it (the first is 0.0.1): its row reads **Built-in orchestrator**, and where it appears under another name, **name (built-in)** — the gateway's placeholder 0.0.0 is never shown. The choice applies from the next turn; a running turn keeps its workflow. If a chosen workflow leaves the catalog, sending is blocked with a message naming it until you pick another one | your account `default_workflow` for `abstractassistant.agent.v1` (`null` = Gateway default, or `bundle:flow` without a version); this app `workflow` on a gateway older than 0.13.1 |
| Open in AbstractFlow | Icon button beside the list, shown only when the gateway serves AbstractFlow at `/apps/flow/` (the `flow` row of `GET /api/gateway/apps` is installed and mounted). It opens the selected workflow in AbstractFlow in your browser, already signed in, through `POST /api/gateway/apps/flow/open` with AbstractFlow's deep link `/?bundle=<id>&version=<version>&flow=<flow>`. **Gateway default** opens the workflow the gateway reports as its default (or the built-in orchestrator when it reports none); a chosen workflow opens at its latest version. When AbstractFlow is installed but not running, the tooltip says so and the gateway's refusal is shown | gateway |

The list is the same one the automation window offers: the assistant workflows the gateway says
you can run (`GET /api/gateway/bundles?executable_for=abstractassistant.agent.v1`).

The choice belongs to your account on the gateway (0.13.1 and later): the console's Accounts →
Preferences, AbstractCode and your other Macs see the same one, and a change says "Saved for your
account — applies from the next turn, in every app." A workflow chosen on this Mac before is moved
there once: the first time the Assistant reads your account's preferences, it uploads that choice
if your account has none yet (a choice already made elsewhere wins), then removes `workflow` from
`preferences.json`. A gateway older than 0.13.1 has no account preferences: the choice stays in
`preferences.json` and a change says "Saved on this device — applies from the next turn."

**Time zone** (gateways with account time zones): where your Daily, Weekly, Monthly and one-time
automations run. A searchable list of the time zones the gateway offers (type to filter); the
first row, **Gateway default (Europe/Paris)**, follows the gateway's own zone. The label and the
line under it are the gateway's. A choice applies at once ("Saved.", or "Not saved." and the
gateway's sentence) and belongs to your account (`PUT /api/gateway/accounts/me/preferences`
`{"time_zone": "<zone>" | null}`), shared with the console's Accounts → Preferences and AbstractCode.
New automations take this zone; an existing automation keeps the zone it was created with. On a
gateway that does not serve the time zone, the row stays with its list disabled and says "This
gateway did not serve a time zone (needs gateway ≥ the round-16 build)."

## Voice

| Control | Meaning | Stored |
|---|---|---|
| Output device | Which speaker replies play on. A list of the devices this Mac can play to, rebuilt each time it is opened, with `System default` first; `Test` plays a tone on the selected one. AirPlay targets are not offered to apps by macOS — pick them in the Sound menu and leave this on `System default` | this app `audio_output_device` (a CoreAudio UID) |
| Speak replies automatically | Switch: auto-speak final answers (also the speaker toggle in the header); applies at once | this app `auto_speak` |
| Voice latency | Balanced / Faster / Higher quality, applied only when the gateway advertises the TTS quality control | this app `voice_quality` |
| Send what you say automatically | Switch, conversation mode: send what you say as a turn; off, words land in the message box; applies at once | this app `voice_auto_send` |
| Ask for short, spoken-style replies | Switch: adds a voice-style instruction to each request while a conversation runs; applies at once | this app `voice_spoken_replies` |
| Barge-in | A list: pause the mic while the assistant speaks (speakers) or keep it open so "stop" interrupts (headphones) | this app `voice_mode` (`wait` / `full`) |

The speech engines are not on this page: they are chosen in one place, Models → Voice output
(TTS) / Voice input (STT). See [voice.md](voice.md) for how the conversation loop behaves.

## Workspace

Two sections with the same words and rows as the gateway console, AbstractCode, AbstractFlow and
AbstractObserver (the ui-kit WorkspaceChooser). The gateway admin defines the **eligible**
workspaces and the most each one allows; you choose among them. Each section shows, from the top:

- **Gateway: …** — the admin's ceiling, verbatim (`gateway_summary`).
- A state switch — **Follow the gateway policy** (account) or **Use my default** (this chat). On,
  the section shows what applies, read-only; switching it off starts your own list from exactly
  that, and switching it back on sends `{configured: false}`.
- **Workspaces agents may use**: **Deny everything, allow listed workspaces** or **Allow
  everything, refuse listed workspaces**.
- One row per workspace: the path, **Read & write** / **Read-only** / **Refused**, and a remove
  icon (tooltip **Remove**). A mode above the gateway's cap for that workspace is disabled with the
  tooltip **The gateway allows this workspace read-only** (or **The gateway refuses this
  workspace**). Under the second posture, **Everything else** sets the mode of the workspaces not
  listed.
- **Add a workspace path** with **Choose…** (a directory picker, shown when the gateway runs on this
  Mac) and **Add**. A new row starts Read-only under "Deny everything, allow listed workspaces" and
  Refused under "Allow everything, refuse listed workspaces".
- The effective line, verbatim from the gateway, e.g. "Deny everything, allow listed workspaces ·
  /Users/me/Pictures (rw) · /Users/me/Documents (ro)".

| Section | Meaning | Stored |
|---|---|---|
| My default workspaces | Your account's subset, used by every chat that does not choose its own. Each change is one `PUT /api/gateway/workspace/policy/me` with the whole list | gateway (your account) |
| This chat | The open conversation's own subset, starting from your default. Each change is one `PUT /api/gateway/sessions/{id}/workspaces`; the gateway keeps it on the session, so every app that opens this conversation sees the same choice, and applies it when a run starts | gateway (the session) |

A change applies at once; a refused one shows the gateway's sentence followed by "Not saved." under
the section, and the rows stay as the gateway holds them. The gateway decides everything: this app
checks no path, computes no cap and keeps no workspace list of its own. There is no shared
workspace and no "Run workspace": each run's private workspace (in the gateway's data folder) is
automatic and always read & write — the section **This chat** says so — and the app only reuses the
one the gateway gave this chat's first run. An old `workspace_root` saved in `preferences.json` by
earlier versions is ignored.

## Tools & permissions

| Control | Meaning | Stored |
|---|---|---|
| Tool mode note | The gateway's tool execution mode (approval, local, passthrough, delegated) | gateway |
| Categories | One collapsible panel per category the gateway reports for its tools (the `toolset` of each tool in `GET /api/gateway/discovery/tools`: camera, comms, files, web, …), sorted by name: the name, the number of tools, then **All auto** / **All ask**. Every panel starts collapsed, including those holding a choice that differs from the gateway default; a panel you open or close stays that way | gateway |
| Per-tool Off / Auto / Ask | Off never offers the tool to the model; Auto pre-approves it on this Mac, even where the gateway would ask; Ask prompts every time. The gateway's own default is marked in the tooltip. A choice applies at once; only the tools that differ from the gateway default are stored, and a failed save puts the row back with "Not saved." | this app `tool_preferences` |
| Risk chip and sentence | The gateway's risk tier (reads only, makes changes, reaches outside, destructive) and capability facts (writes, can delete, sends messages, reaches remote services, captures the environment) | gateway |
| Disabled on gateway | Tools the gateway has turned off; they are never offered to a run | gateway |
| Command sandbox | On the tools that start processes (`execute_command`, `shell_exec`, `local_helper_start`, `execute_python`): the gateway's state, verbatim — **Sandboxed to this run's workspaces**, or its refused / unsandboxed state — with the gateway's explanation in the tooltip (`sandboxed` / `sandbox` of each tool and `command_sandbox.sentence` in `GET /api/gateway/discovery/tools`). The app never decides it | gateway |
| All auto / All ask | Pressed-state controls in each panel header: **All auto** is pressed when every tool it may reach is on Auto, **All ask** when every tool of the panel is on Ask, neither when they are mixed; pressing one sets the panel's tools and applies at once. All auto leaves outreach and destructive tools on Ask; set those to Auto one by one. With a filter, only the tools shown are changed | this app |
| Filter tools | Searches every category (names and descriptions); panels with a match open, the others step aside, and the count reads **2 of 8** | — |
| Use gateway defaults | Restore each tool to the gateway's approval default (applies at once) | this app |

Off and Ask narrow what the gateway allows; Auto pre-approves on this Mac. Tools you never
configured follow the gateway's approval default. "Always allow … on this Mac" in the approval
sheet is offered for the observe and act tiers only. "Allow all enabled tools in this chat" is
always offered, and it reaches exactly as far as the batch you granted it on: granted on a
read-only batch it keeps asking for outreach and destructive calls, granted on a destructive
batch (the item then says so) it covers everything this page has not switched off, for that chat.

## Appearance & window

Listed as **Appearance** in the sidebar.

| Control | Meaning | Stored |
|---|---|---|
| Theme | The colour palettes shared with the other AbstractFramework apps; applies to every window of this app at once | this app `ui_theme` |
| Text size / Line spacing / Paragraph gap / Bullet gap | How replies are set in the transcript: text size 10–22 px (default 13), line spacing 1.0–2.2 × (default 1.2), paragraph gap 0–28 px and bullet gap 0–16 px (default 3 each). Applies immediately | this app `text_size`, `line_spacing`, `paragraph_spacing`, `bullet_spacing` |
| Summon / Key combination | Global hotkey (default `cmd+shift+space`), subject to macOS Accessibility permission. The **Summon the assistant from anywhere** switch applies at once; the key combination applies when you press Return or leave the field | this app `hotkey_enabled`, `hotkey_sequence` |
| Accessibility | macOS only: the permission the shortcut needs, as **Granted** / **Not granted**. **Configure** asks macOS for it (the system prompt, when macOS still offers it) and opens System Settings → Privacy & Security → Accessibility; the state is checked again when you come back to the app or reopen the page, and the shortcut starts as soon as it is granted | macOS |
| Width / Expanded height / Screen edge gap | Apply as they change. Palette size; the transcript takes the remaining height. Defaults: width 650 px, height 286 px, gap 12 px. Settings accepts a width of 420–2000 px and a gap of 0–200 px; the only further limit is the screen the window is on (width up to 62% of it, gap up to a quarter of its smaller side). The gap is the space kept between the window (and Settings) and the screen edges it sits against; 0 puts it flush with the edge | this app `window_width`, `window_height`, `bottom_offset` |

Migration note: preferences saved with the 0.5.0 defaults (width 500 px, gap 18 px) and without
the `layout_version: 2` marker are moved to 650 px and 12 px once; any other saved width or gap,
including a gap of 0, is kept.

In-app shortcuts: Return sends, Shift+Return adds a line, Esc stops speech then hides, ⌘. stops
the run (does nothing when no run is active), ⌘N starts a new chat (refused while a run is
active), ⌘, opens Settings, ⌘⇧V starts or ends a voice conversation. In the approval sheet:
Return allows once, or activates the Deny / Decide later button when one of them has focus; ⌘D
denies; Esc decides later.

## About

Also reachable from the menu-bar icon's **About AbstractAssistant…** item.

- The application and its version, part of AbstractFramework (with the framework website), the
  author, copyright and licence, and links to the website, source, documentation, issue tracker,
  feedback form and contact address. These rows come from the AbstractFramework identity shipped
  with AbstractCore, so they read the same as in every other AbstractFramework app. The version is
  the one `assistant --version` prints.
- **Gateway**: the AbstractGateway version, the AbstractFramework version installed on the gateway
  host (or "not installed on the gateway host"), and each gateway package version, as the gateway
  reports them; a single "Gateway: unavailable (reason)" row when they cannot be read.
- **Workflow**: the workflow the next turn runs, as **Gateway default → name @version (bundle)**,
  **Built-in orchestrator @version (bundle:flow)** or **name @version (bundle:flow)**; **Last turn
  ran**: the workflow the gateway resolved for the last run start, as **name @version
  (bundle:flow) — the gateway default | chosen by this app**. Both follow the workflow row's
  rule for the built-in orchestrator: no number (or **(built-in)**) until it has a real published
  version. **Data folder** (with Reveal in Finder).
- `Copy diagnostics` copies the same facts plus the connection (without secrets) and preferences.

## Preferences file

`~/.abstractassistant/preferences.json` holds every "this app" value above. Missing keys keep
their defaults: gateway defaults for models and reasoning, Stream replies on, auto-send and
spoken-style replies on, microphone paused while the assistant speaks. Workspaces are not in this
file (they live in the gateway). Each session's cached `session.json` may also carry the
`workspace_root` (the private workspace) the gateway gave that session.
