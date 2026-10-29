# Automations

An **automation** runs a task on a schedule on the gateway: "search the news about AI agents every
8 hours", "triage my inbox every 30 minutes", "summarise my journal every 7 days". The gateway runs
it; the Assistant lists it, creates it, answers it and tells you when it needs you. Nothing runs on
this Mac: an automation keeps running while the Assistant is closed or the Mac is asleep.

This page is the user guide. For how automations fit in the app's components and which gateway
routes they use, see [architecture.md](architecture.md#automations) and
[api.md](api.md#gateway-routes-used). For the sessions they sit next to, see
[architecture.md](architecture.md#sessions).

The managed Assistant workflow supplies baseline file, web and command tools when no explicit tool selection is provided. An explicit empty selection disables tools; gateway permissions may narrow any selection. Automations pin their workflow version: to adopt updated defaults, revise the target or create an automation using the updated workflow.

## What an automation is

- **An automation is a durable object on the gateway.** Each run of it (an *occurrence*) is a run of
  the chosen workflow with the automation's task as its prompt, in a session that belongs to the
  automation.
- **Each run is a chat turn.** The Assistant shows an automation's runs as a conversation: what
  triggered the run and the task it was given, then its answer.
- **Independent or Growing.** An Independent automation starts every run fresh. A Growing one
  shows each run the previous runs, like a continuing conversation, within a bounded history.
- **Quiet by default.** An ordinary result updates the list and never notifies you. You are
  notified when a result is marked as notable by the workflow, when a run fails after all its
  retries, and when a run waits for your answer.
- **Tools are consented once.** Nobody is in front of a scheduled run to approve a tool call, so
  you decide when you create the automation whether its tools run without asking or ask each time.

## Where automations appear

Click the chat name in the palette header. On a gateway that offers automations, the switcher has
two tabs, **Sessions | Automations** (⌘1 / ⌘2, or ← / → while the filter is empty; the last tab is
remembered). The **Automations** tab lists every automation, whichever app created it (the
Assistant, AbstractObserver or another client); archived ones are hidden until you turn on **Show
archived** in the tab's header, and **+ New automation** creates one (below). Each row shows:

- the title, and on the right when it last ran (`40 min ago`, `1 h 06 min ago`) — with
  "✋ waiting for you" when a run waits for your answer, or a red "failed" when the last run failed;
- the last result, on one line;
- the schedule in the gateway's own words, for every kind (`Every 30 minutes (UTC)`,
  `Every day at 08:00 (Europe/Paris)`), the next run
  (`next in 2 min`, `next —` when paused), the number of
  runs (`#32`), the workspace folder icon (it opens in the file manager when the gateway reports the
  folder and it is on this Mac), and at the far right the card's one control, the **Active**
  switch: on (accent track, check mark, bold label) while the automation runs on its schedule,
  off while it is paused. Clicking it pauses or resumes the automation. The switch shows the
  gateway's status and moves only when the gateway reports the new state: after a click it is busy
  until then, and if the gateway refuses it stays where it was, with the reason in its tooltip.
  An archived, ended or legacy automation's switch is unavailable, the reason after the label
  ("Active — Archived") and in its tooltip. While a run is in progress, line 2 reads "Run #37
  running", plus "· paused after this run" when paused.

The card looks like a session card. Click it (or press Enter) to open the automation, where
**Run now**, **Stop**, **Edit**, **Archive** and **Discuss** live. The times follow each refresh.

The tab's label counts what needs you (`Automations · 3 new`: unseen items plus waiting runs).
Typing in the switcher filters automations by title, cadence and last result, like chats. When
you have none yet, the tab says so and points to the clock button.

The **Automations…** entry in the menu-bar icon's menu carries the same count
(`Automations… (3 new)`) and opens the palette with the switcher.

### Automations and your sessions

The sessions an automation runs in are listed under their automation, never in the Sessions tab. The
gateway stamps every session with a kind (`chat`, `automation`, `occurrence`, `discussion`), and
the switcher lists only `chat` and `discussion` sessions; it never guesses from a session's id.
A session from a gateway that does not stamp kinds counts as a chat. When the gateway advertises
the `session_kind` filter on `/runs`, the Assistant asks it for chats and discussions only, so
automation runs never crowd your chats out of the listing. How the session list works as a whole
is described in [architecture.md](architecture.md#sessions).

## Schedule this conversation (or a new automation)

Two ways in, one window:

- the clock button in the palette header (shown once the gateway has confirmed it offers
  automations) opens **Schedule this conversation…**, prefilled with the conversation's last
  question;
- **+ New automation** in the switcher's Automations tab opens the same window empty, titled
  **New automation**, with the workflow set to **Gateway default** (or, when the gateway reports
  no default for the assistant, the workflow a turn would run); after creation the tab lists the
  new automation, selected.

The window, beside the palette:

The window carries the same content as the AbstractCode and AbstractObserver schedule dialog:

- **What**: a **Workflow** list with **Gateway default** first, then the assistant workflows the
  gateway says you can run (the list in Settings → Workflow). It starts on the conversation's
  workflow (**Gateway default** for **+ New automation**). Then the **Task** (prefilled with the
  conversation’s last question) and an optional **Title** that defaults to the task's first line
  (at most 120 characters). Both choices belong to the automation.
- **When**: **Repeat** · **Daily** · **Weekly** · **Monthly** · **Once at…** · **When an email
  arrives** (the same words as the AbstractCode and AbstractObserver dialog).
  - **Repeat**: every 5 minutes, 30 minutes, hour, 8 hours (preselected), 24 hours or 7 days, or
    **every N…** minutes, hours or days. A Repeat interval is a fixed duration in UTC ("every 24
    hours"), with an optional first-run time (`YYYY-MM-DD HH:MM`, UTC; empty means now).
  - **Daily** at a time of day; **Weekly** on the days you pick (one chip per day, Monday first;
    a picked day shows a check mark) at a time of day; **Monthly** on day 1 to 31, or **last**, at
    a time of day. A day the month does not have (31 in April) runs on that month's last day.
  - **Once at…** a date and time (`YYYY-MM-DD HH:MM`).
  - Daily, Weekly, Monthly and Once run at that wall-clock time in your account's time zone, also
    when daylight saving time changes. A line shows the zone, "in Europe/Paris (your account's
    time zone)" (its tooltip explains the rule), with **Change in preferences**, which opens
    Settings → Workflow, where the zone is set. The days, the day of the month and the time stay as
    you set them when you switch between Daily, Weekly and Monthly.
  - Repeat, Daily, Weekly and Monthly can **Stop after this many runs** and **Stop at** a date and
    time (UTC); both are optional.
  - **When an email arrives**: see [Email automations](#email-automations).
- **Context**: **Independent** (the default: each run starts fresh) or **Growing** (each run sees
  the previous runs).
- **Tools**: open the searchable grouped selector to enable or disable tools for this automation, or restore workflow defaults. Saving an empty selection disables all tools. Choose **Run without asking** (the default; the line under it reads "Tools run without asking (you approve them now by creating this automation).") or **Ask me before each tool call (the run waits for you)**. See
  [Tool consent](#tool-consent).
- **Workspaces** (visible, after Tools): the same chooser as Settings → Workspace, the gateway
  console, AbstractCode and AbstractObserver, at the run level. "Gateway: …" on top (the eligible
  workspaces, verbatim), **Use my default** (on: your account's default workspaces apply), the
  posture (**Deny everything, allow listed workspaces** / **Allow everything, refuse listed
  workspaces**), each workspace with **Read & write** / **Read-only** / **Refused** (a mode above
  the gateway's cap is disabled, with "The gateway allows this workspace read-only" as its
  tooltip) and a remove icon, **Add a workspace path** with **Choose…** (when the gateway runs on
  this Mac) and **Add**, and the effective line. Each change is checked by the gateway (`POST
  /api/gateway/workspace/effective/me`, nothing stored); a refused one shows the gateway's sentence
  with "Not saved." and the choice stays as it was. **Create automation** stores the choice in the
  definition (`target.input_data.workspace`); the gateway clamps it to the eligible workspaces at
  each run. With **Use my default** on, nothing is stored and each run uses your default at that
  time. In this narrow window the two postures are stacked and each workspace's modes sit under
  its path.
- **Mailbox**: **Email result** and **Recipients: Only me (default) /
  Me and these addresses** (see [Email automations](#email-automations)).

Every section is visible: the window has no "Advanced" part.

A line previews the schedule or says what is missing. For every schedule kind, Repeat included,
it is the gateway's own sentence ("Runs every day at 08:00 (Europe/Paris), first run Fri 9 Oct
08:00."), asked from the gateway as you edit (`POST /api/gateway/automations/schedule-preview`,
nothing is stored); only **When an email arrives** has a line of the app's own. The time-zone
line appears for Daily, Weekly, Monthly and Once, not for Repeat (a UTC interval). The Assistant
never words a schedule or works out a next run itself: every automation shows the schedule and
the next run the gateway reports. **Create automation** is enabled once the form is complete and the gateway offers
the `schedule` trigger; it creates the automation and opens it in the palette (or, from
**+ New automation**, selects it in the Automations tab). If the gateway could not be reached,
pressing **Create automation** again sends the same request, which the gateway recognises, so the
automation is never created twice; after a refusal, the next press is a new request.

## Email automations

The gateway reads your own mailbox once you connect it in the gateway console's **My email**
(Users tab). The window asks the gateway (`GET /api/gateway/me/email`) whether your account can be
used now: connected, your own switch on, and allowed by an administrator. If not, or if the gateway
could not say, the email options are disabled under **"Email isn't set up — open My email"**; the
link opens `<gateway>/console#users` in your browser. Nothing email-shaped is sent without a usable
account.

- **When an email arrives** (the trigger `email.received@1`, offered only when the gateway lists
  it): typed filters, no patterns — from these addresses, from these domains, sent to these
  addresses, subject contains, attachments (any / only with / only without). Separate entries with
  commas or new lines; a wrong entry is named. **Check for new mail every** defaults to 1 hour (an
  automation that runs a model checks once an hour by default; one that needs no model checks every
  60 s; the shortest interval is 60 s, as the window says). **At most this many emails per run**
  (default 100, up to 1000): the rest wait for the next run. Each email is read once by the
  automation; mail that arrived before it was created, or while it was paused, is not processed.
  Incoming mail is data, never instructions: the automation acts only on its task, and link-opening
  tools (`fetch_url`, `browser_probe`) always ask.
- **Email result** emails every completed run’s full result.
- **Recipients** appears when Email result is enabled: **Only me** (default) or
  **Me and these addresses**. Recipients are stored in `notify.recipients`;
  this setting does not grant email-tool permissions. The mailbox recipient policy still applies.

The wording is the shared AbstractUIC text (`automation_controls.json`, `email` section), the same
as in the web clients. **Edit** changes an email trigger's interval (the revised trigger starts
from now, so no email is read twice). You can also change **Email result** and its recipients
in the edit form.

Outside automations, the Assistant's local tool approval asks before `send_email`,
`list_emails` or `read_email` runs: these tools are not in its auto-approved set.

## Tool consent

Tool selection applies only to this automation and does not change chat preferences. The separate approval choice is sent as `policy.tool_approval`:

- **Run without asking** (`auto`): creating the automation is your approval. Its runs use the
  workflow's tools without stopping to ask, since nobody is there to answer each run.
- **Ask me before each tool call** (`ask`): every run that wants a tool waits for your approval, and you are
  notified. You approve or deny from the automation (see
  [Answering a run that waits for you](#answering-a-run-that-waits-for-you)).

Questions the workflow itself asks you always wait for your answer, whichever you choose. The
choice is kept with the automation; to change it later, archive the automation and schedule a new
one (see [Limits](#limits)).

## Reading an automation

Click a row in the Automations tab. The palette shows the automation in the chat's own surface, in
place of the conversation: its runs as the chat's exchanges and the chat's composer underneath
(see [Continue as a session](#continue-as-a-session)). The **←** button, choosing a chat or **+ New chat**
returns to the conversation; a message you were writing there is kept aside while the automation is open
and comes back.

The header is two compact rows:

- the title (cut with "…" when long; hover it for the full title), **one status chip** (Active,
  Paused, Archived, Completed, Failed, or **Running…** while a run is in progress) and a **⋯** menu;
- **one schedule chip** with what starts it ("Every 24 h", "Every day at 08:00", "When mail arrives
  in you@example.org"; hover it for the gateway's full sentence and time zone), **one next-run chip**
  ("Next in 3 h · 11:06 PM", from the gateway's next run; none for an automation that runs when
  something happens or is paused), then the **Active** switch and the icon controls (below).

What starts it is said in words: the gateway's schedule sentence (`schedule_rule_text`, shortened for
the chip), "When mail arrives in you@example.org", "When Python news has a new item" (the feed
connection's name), "When Orders is called" (the webhook connection's name) or "By hand"; the words
come from the gateway (`trigger_text`) when it serves them, else from your connections and mailboxes.

The **⋯** menu holds the details: **Workflow: basic-agent 0.0.5** (the workflow and its version),
**Workspaces…** (the gateway's summary for the stored workspace choice, or for your default, verbatim),
the context mode ("Context: Growing — each run sees the previous runs") and **Copy automation id**
(for support). A slim notice says how many runs are waiting for you; a link **Continued as a session
on Oct 27** opens the newest session this automation was continued as, when the gateway's session
list names it.

Each run reads as one exchange of the chat, oldest at the top:

- **a system line** says what started it and when, in words: "Scheduled run 1 · Oct 9 at 11:06 PM",
  "Run now · run 4 · Today at 07:12 AM", "Email received · run 3 · 2 new emails · …" (hover it for the
  full date). The runtime's bracketed trigger line in the task ("[Trigger schedule@1 · occurrence 1 ·
  fired …]") and the framed input of an email, feed or webhook run are never shown;
- **the task** is the chat's user bubble;
- **the result** is the chat's reply card, with its time (and date when not today), **copy** and the
  **speaker** that reads it aloud, as in a conversation. A result the workflow marked as notable
  carries **Notified** and its notification title. A failed run has a red card with the gateway's
  message and **Failed after 3 attempts** on its line. A run that waits for you shows **Waiting for
  you** and the controls to answer it. A running run shows **Running**. An unseen result is marked
  **New result** (or **New failure**). Files the run produced are listed by name.

Quiet runs (completed, nothing to notify) are shown dimmed. **Load older runs** at the top pages
back through the history.

Opening an automation marks the new items it displayed as seen on the gateway, so the badges clear
on every device you use; items that arrive after the view loaded stay new. Runs waiting for you
stay counted until you answer them.

## Controls

| Control | What it does |
|---|---|
| **Active** (a switch, first in the bar) | On: the automation runs on its schedule. Off: paused, scheduled runs are skipped; a run in progress finishes. Switching it back on restarts the schedule at its next time after now (it does not fire at once; times missed while paused are skipped). Unavailable, with the reason, once the automation is archived, ended or legacy, or when the gateway does not permit the change. |
| **Run now** (the play-in-a-circle icon, as in the web clients; the controls are icons, their name in the tooltip) | One run immediately, instead of waiting for the schedule. The schedule does not move: the next scheduled run keeps its time, and if that time comes while this run is still going, the scheduled run starts right after it. It does not count toward a run limit. It also works while paused, and the automation stays paused. In a Growing automation, later runs see it in their history. Disabled while a run is in progress. |
| **Stop current** (the square icon) | Stops the run in progress. |
| **Edit** (the pen icon) | Title, interval (`30m`, `8h`, `7d`; for an email trigger the check interval, at least `60s`) or, for a Daily, Weekly or Monthly schedule, its rule (the kind, the days, the day of the month and the time, with the gateway's line "in Europe/Paris (this automation's time zone)" and its preview sentence; the automation keeps its own zone and its run limits), context mode, workflow, tool selection, **Workspaces** (the same chooser as the schedule window, with the stored choice; each change checked by the gateway) and result-email recipients, inline. **Save** sends the changes as one revision; with **Use my default** the stored choice is removed. Applies from the next run; a new interval starts counting from the change, so no missed run fires. |
| **Archive** (the box icon) | Asks for confirmation in the palette. Nothing runs any more; the history is kept. |

Hovering a control shows what it does: the same text as the web clients (AbstractUIC's shared
control hints). Run now's tooltip adds the next scheduled time ("Next scheduled run: 2026-09-27
08:00 UTC.") and, for a Growing automation, that later runs see this run. A control that does not
apply is disabled, and its tooltip first gives the reason ("A run is in progress.", "Not
permitted for this automation."). The gateway decides which
controls you may use on each automation; an archived automation has none.

A legacy schedule (a scheduled run from before automations, which the gateway lists among them)
opens with every control disabled and the notice "This is an older scheduled run, kept with its own
controls. Manage it from the Observer, or recreate it as an automation." Its runs are not loaded.

After a control, the palette confirms it ("Active is off: scheduled runs are skipped until you
switch it back on.", "Saved;
applies from the next run.") and reloads the automation. When the gateway had already received
the same request, the confirmation ends with "(already received)": the first one stands and nothing
is applied twice. A request the gateway did not accept is shown as an error. If the gateway could
not be reached,
**Retry** sends the same request again with the same id, so it is never applied twice; once the
gateway has answered, trying again is a new request. An edit made while the automation changed
elsewhere is refused with "The automation changed since this view loaded. Reload it, then try
again."

## Answering a run that waits for you

A run can stop and wait for you. You get a tray notification, and the run shows what it waits for.
The gateway says which kind of answer each wait expects, and the Assistant answers by that kind,
never by reading the question's text:

| The run waits for | You see | What is sent |
|---|---|---|
| **a question** (`ask_user`) | the question, its choices as buttons, and a free-text field with **Answer** | your text as `{"response": "…"}` |
| **tool approval** (`tool_approval`, automations set to Ask me before each tool call) | the tool calls it would run, each with its arguments, and **Approve** / **Deny** | `{"approved": true}` or `{"approved": false}` |
| **an event** (`event`) | a field for the event's payload as JSON (`{"key": "value"}`) and **Send event** | `{"payload": <your JSON>}`; text that is not valid JSON is refused in place |

The answer is a `resume` command on the waiting run, the same command the palette sends when you
answer a question during a chat. A wait whose kind the gateway does not give (or gives as
something else) is shown without answer controls, with a note to answer it from AbstractObserver,
rather than answered blindly. If your answer does not reach the gateway, the palette says so and
the run keeps waiting.

## Continue as a session

Write in the composer under an open automation and press Return (or the send button): the palette asks
the gateway to open a new session seeded with the automation's history up to its **latest finished
run** (whatever its context mode), sends what you wrote in it, and switches to it. While the session is
being created the composer says **Continuing as a session…**; if the gateway refuses, your text is put
back with the reason. The session then shows **Continued as a session from “<title>” (run N).** with
**Back to the automation**.

To continue from an earlier run, open the run's **⋯** menu and choose **Discuss here**: the line above
the composer says "Your next message continues from run 3." (**Use the latest run** undoes it).

The session is an ordinary chat: it keeps the workflow's normal tools and appears among your chats with
the badge **about automation <title>** (click the badge to open the automation). The automation's files
are mounted read-only (hover the notice to see where); the session works in its own writable workspace,
and nothing is written back to the automation. The file tools refuse to write into the mounted folder;
shell commands are not sandboxed, so approve them with that in mind. Files cannot be attached to the
first message; attach them in the session.

A run in progress cannot be continued from, and the palette asks you to let a running reply finish (or
stop it) before it opens the session.

## Notifications and your event stream

On a gateway that keeps a per-person event stream (`GET /api/gateway/me/events` and its live
`/me/events/stream`), the Assistant follows it from launch: it reads what happened since it last
looked, then stays connected and reconnects on its own after a sleep or a network change, resuming
exactly where it stopped. With the stream connected:

- an automation event (a trigger fired, a run of an automation started or finished, a result
  raised or seen) refreshes the automation list within a second; a slow check every **5 minutes**
  still catches an automation created or renamed elsewhere, which sends no event;
- a run in **another conversation** that stops for your approval or your answer shows one tray
  notification ("Approval needed" or "A question for you"), unless that conversation is the one on
  screen. Its sheet opens in that conversation, as before;
- a badge beside the session control shows what waits for you elsewhere: the kit's inbox icon
  with a count. Its tooltip says what the count is ("1 conversation is waiting for you", "2 new
  results from your automations", then "Click to open it."). A click opens exactly the first
  thing it counts:
  - a run of an automation that waits for your approval opens that automation, where the run
    carries **Approve** / **Deny**;
  - a run in a chat that waits opens that chat, after asking the gateway whether the run still
    waits (it says so when it no longer does);
  - a new result opens its automation on the runs you have not seen (marked **New result**), and
    viewing them marks them seen.

  What the open view shows is not counted while it is open. With no event stream, the automation
  list's unseen counts drive the badge;
- the menu bar icon shows the amber "needs you" badge while a run elsewhere waits for you, and its
  tooltip repeats the badge's lines.

What happened while the Assistant was closed is read when it starts, but it never notifies you
for it: notifications are for what arrives while the app is open.

One notification per thing on this Mac: the gateway's tray icon is the default notifier. Before
showing one, the Assistant waits a few seconds and stays silent when the tray (or Code) on the same
Mac already showed it less than a minute ago; when it does show one, it tells the gateway
(`POST /api/gateway/me/events/notifications {channel: "assistant", device}`; the device is this Mac's
id, computed as the tray computes it). The watch is another device: it notifies on its own.

On a gateway without the event stream, the Assistant reads the automation list on two cadences
instead:

- every **60 seconds** while the palette is visible, and once each time you show the palette or
  open the switcher;
- every **5 minutes** while the palette is hidden, so that a notification reaches the tray while
  you work in other apps.

A tray notification is shown once for each:

- result the workflow marked as notable;
- run that failed after all its retries (3 attempts unless the automation sets another number);
- run waiting for you ("<title> is waiting for you", or "<title> needs your approval" for a
  tool approval).

Ordinary results never notify. Notifications are not repeated after a relaunch:
`~/.abstractassistant/automations_notified.json` remembers which ones were shown. What counts as
"seen" is kept by the gateway, per user, and moves only when you open the automation.

## When the gateway does not offer automations

The Assistant reads the gateway's capabilities (`contracts.common.automations.available`):

- **Advertised** (`true`): the Automations tab, the tray entry, the clock button and the polls
  described above.
- **Not advertised** (absent or `false`): no Automations tab, no tray entry and no clock
  button, and the polls make no automation request. A gateway that stops advertising automations
  hides them again at the next poll.
- **Capabilities could not be read**: the Automations tab shows an error line instead of
  hiding, so an unreachable gateway is never mistaken for one without automations.

The clock button and the tray entry appear only after a poll has confirmed that the gateway offers
automations, and no automation route is called before that.

## Offline and errors

- When a check fails, the switcher keeps the automations it last received and shows
  "Automations: The gateway could not be reached." (or the gateway's reason) above them. The next
  successful check replaces the line.
- Every refusal from the gateway is shown in words with the gateway's own message, for example
  "Sign in to the gateway to manage automations.", "This automation does not exist (or is not
  yours).", "A run is already in progress or queued. Wait for it to finish."
- Automations are scoped to the gateway user you are signed in as: signing in as another user shows
  that user's automations.

## Limits

- A Repeat schedule is a fixed interval in UTC. Daily, Weekly, Monthly and Once run in the
  automation's time zone, set from your account's when it is created; **Edit** does not change an
  automation's zone.
- The Assistant creates scheduled and incoming-email automations; **Run now** starts one more run.
- A maximum number of runs and an end date are set when the automation is created; **Edit** does
  not change them.
- **Edit** changes title, interval or calendar rule, context settings, workflow, available tools and result-email recipients. To change the task, revise it through the gateway API or create a new automation.

Changing workflows preserves the task, portable agent settings, selected tools and result-email
recipients. The new workflow supplies its input defaults. If additional required inputs are
missing, the form refuses the change; configure those inputs when creating a new automation
or choose a compatible workflow.

## Growing context limit

These options require AbstractGateway 0.11.3 or later.

Choose **Growing** to set **Max growing context (tokens)** when creating or editing an
automation. The default is 50,000; enter `30000` for a 30,000-token history budget.
The limit is hidden for **Independent** runs. Changing it affects subsequent occurrences;
already admitted occurrences retain their history for retries. History retains whole turns,
including the newest turn even when that turn alone exceeds the budget.

This budget limits inherited history at the start of a run. New messages, tool results,
system instructions and generated output can increase the model’s working context beyond it.
It is not a per-call context or memory limit.

The API field is `context.growing.max_tokens`, a positive integer. Existing definitions
that omit it retain the 50,000-token default.
