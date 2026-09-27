# Automations

An **automation** runs a task on a schedule on the gateway: "search the news about AI agents every
8 hours", "triage my inbox every 30 minutes", "summarise my journal every 7 days". The gateway runs
it; the Assistant lists it, creates it, answers it and tells you when it needs you. Nothing runs on
this Mac: an automation keeps running while the Assistant is closed or the Mac is asleep.

This page is the user guide. For how automations fit in the app's components and which gateway
routes they use, see [architecture.md](architecture.md#automations) and
[api.md](api.md#gateway-routes-used). For the sessions they sit next to, see
[architecture.md](architecture.md#sessions).

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

Click the chat name in the palette header. On a gateway that offers automations, the switcher lists
an **Automations** section above your chats: one row per automation you own, whichever app created
it (the Assistant, AbstractObserver or another client). Each row shows:

- the title, and a badge when something needs you: `2 NEW` (unseen results or failures) and
  `WAITING` (a run waits for your answer);
- the cadence, its status and its context mode, for example
  `every 8 hours (UTC) · Active · independent` or `every 7 days (UTC) · 12 runs max · Paused · growing`;
- when it runs next (`next in 3 h`, `next in 12 min`, `next: now`, `paused`, `running`);
- the last run's number, status and the first line of its result (`#12 completed: …`), or
  `waiting for you: <question>`.

The section header counts what needs you (`AUTOMATIONS · 3 NEW`: unseen items plus waiting runs).
Typing in the switcher filters automations by title, cadence and last result, like chats. When
you have none yet, the section says so and points to the clock button.

The **Automations…** entry in the menu-bar icon's menu carries the same count
(`Automations… (3 new)`) and opens the palette with the switcher.

### Automations and your sessions

The sessions an automation runs in are listed under their automation, never among your chats. The
gateway stamps every session with a kind (`chat`, `automation`, `occurrence`, `discussion`), and
the switcher lists only `chat` and `discussion` sessions; it never guesses from a session's id.
A session from a gateway that does not stamp kinds counts as a chat. When the gateway advertises
the `session_kind` filter on `/runs`, the Assistant asks it for chats and discussions only, so
automation runs never crowd your chats out of the listing. How the session list works as a whole
is described in [architecture.md](architecture.md#sessions).

## Schedule this conversation

The clock button in the palette header (shown once the gateway has confirmed it offers automations)
opens **Schedule this conversation…**, a window beside the
palette:

- **What**: the conversation's workflow (the one Settings → Models → Workflow selects, shown as
  "Workflow: …") and a task prefilled with the conversation's last question, which you can edit.
  The title is optional and defaults to the task's first line (at most 120 characters).
- **When (UTC)**: every 5 minutes, 30 minutes, hour, 8 hours (preselected), 24 hours or 7 days;
  **every N…** minutes, hours or days; or **once at…** a date and time. For an interval, an
  optional first-run time (`YYYY-MM-DD HH:MM`, UTC); empty means the first run is due now.
  Intervals are fixed durations in UTC: "every 24 hours", never "daily at 08:00 local time".
- **Context**: **Independent** (the default: each run starts fresh) or **Growing** (each run sees
  the previous runs).
- **Tools**: **Tools run without asking** (the default) or **Ask each time**. See
  [Tool consent](#tool-consent).

A line under the form previews the schedule ("every 8 hours (UTC), first run now") or says what is
missing. **Schedule** is enabled once the form is complete and the gateway offers the `schedule`
trigger; it creates the automation and opens it in the palette. If the gateway could not be
reached, pressing **Schedule** again sends the same request, which the gateway recognises, so the
automation is never created twice; after a refusal, the next press is a new request.

## Tool consent

The **Tools** choice is sent as the automation's `policy.tool_approval`:

- **Tools run without asking** (`auto`): creating the automation is your approval. Its runs use the
  workflow's tools without stopping to ask, since nobody is there to answer each run.
- **Ask each time** (`ask`): every run that wants a tool waits for your approval, and you are
  notified. You approve or deny from the automation (see
  [Answering a run that waits for you](#answering-a-run-that-waits-for-you)).

Questions the workflow itself asks you always wait for your answer, whichever you choose. The
choice is kept with the automation; to change it later, archive the automation and schedule a new
one (see [Limits](#limits)).

## Reading an automation

Click a row in the Automations section. The palette shows the automation in place of the
conversation, and **← Chat** returns to it.

The header gives the title and one line with the cadence, status, next run, context mode and run
count. Below it, a highlighted block lists what is new ("New · #12 Price above threshold",
"Failed · #9") and how many runs are waiting for you.

Each run reads as a pair of chat turns, oldest at the top, newest in view:

- **the trigger turn**: the run's number, the gateway's summary of what fired it and when
  (`#7 · schedule: every 30 minutes (UTC), tick 5 · fired 2026-09-27 06:30 UTC`), then the task
  the run was given;
- **the answer turn**: the run's status and finish time, then its answer. A result the workflow
  marked as notable carries its notification title and a **Notified** badge. A failed run is red,
  with the gateway's reason and the number of attempts ("Failed after 3 attempts"). A run that
  waits for you is highlighted with **Waiting for you** and the controls to answer it. A running
  run shows **Running**. Files the run produced are listed by name.

Quiet runs (completed, nothing to notify) are shown dimmed. **Load older runs** at the top pages
back through the history.

Opening an automation marks the new items it displayed as seen on the gateway, so the badges clear
on every device you use; items that arrive after the view loaded stay new. Runs waiting for you
stay counted until you answer them.

## Controls

| Control | What it does |
|---|---|
| **Pause** | No scheduled run until you resume. A run in progress finishes. |
| **Resume** | Back on the schedule from the next scheduled time; it does not fire at once. |
| **Run now** | One run immediately. It also works while paused, and the automation stays paused. Disabled while a run is in progress. |
| **Stop current** | Stops the run in progress. |
| **Edit** | Title, interval (`30m`, `8h`, `7d`) and context mode, inline. Applies from the next run; a new interval starts counting from the change, so no missed run fires. |
| **Archive** | Asks for confirmation in the palette. Nothing runs any more; the history is kept. |

A control that does not apply is disabled, with the reason in its tooltip ("Already paused.",
"An occurrence is in progress.", "Not permitted for this automation."). The gateway decides which
controls you may use on each automation; an archived automation has none.

A legacy schedule (a scheduled run from before automations, which the gateway lists among them)
opens with every control disabled and the notice "This is an older scheduled run, kept with its own
controls. Manage it from the Observer, or recreate it as an automation." Its runs are not loaded.

After a control, the palette confirms it ("Paused: no scheduled run until you resume.", "Saved;
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
| **tool approval** (`tool_approval`, automations set to Ask each time) | the tool calls it would run, each with its arguments, and **Approve** / **Deny** | `{"approved": true}` or `{"approved": false}` |
| **an event** (`event`) | a field for the event's payload as JSON (`{"key": "value"}`) and **Send event** | `{"payload": <your JSON>}`; text that is not valid JSON is refused in place |

The answer is a `resume` command on the waiting run, the same command the palette sends when you
answer a question during a chat. A wait whose kind the gateway does not give (or gives as
something else) is shown without answer controls, with a note to answer it from AbstractObserver,
rather than answered blindly. If your answer does not reach the gateway, the palette says so and
the run keeps waiting.

## Discuss a result

**Discuss** on a finished run opens a field ("What do you want to discuss about this result?");
**Start** asks the gateway to open a new session seeded with the automation's whole history up to
that run (whatever its context mode), sends your question in it, and switches the palette to it. It
is an ordinary chat: it keeps the workflow's normal tools and appears among your chats with the badge
**about automation <title>** (click the badge to open the automation). The automation's files are
mounted read-only (the notice after Discuss says where); the discussion works in its own writable
workspace, and nothing is written back to the automation. The file tools refuse to write into the
mounted folder; shell commands are not sandboxed, so approve them with that in mind.

Discuss is disabled on a run in progress, and the palette asks you to let a running reply finish
(or stop it) before it opens a discussion.

## Notifications and the two polls

The Assistant reads the automation list from the gateway on two cadences:

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

- **Advertised** (`true`): the Automations section, the tray entry, the clock button and the polls
  described above.
- **Not advertised** (absent or `false`): no Automations section, no tray entry and no clock
  button, and the polls make no automation request. A gateway that stops advertising automations
  hides them again at the next poll.
- **Capabilities could not be read**: the Automations section shows an error line instead of
  hiding, so an unreachable gateway is never mistaken for one without automations.

The clock button and the tray entry appear only after a poll has confirmed that the gateway offers
automations, and no automation route is called before that.

## Offline and errors

- When a check fails, the switcher keeps the automations it last received and shows
  "Automations: The gateway could not be reached." (or the gateway's reason) above them. The next
  successful check replaces the line.
- Every refusal from the gateway is shown in words with the gateway's own message, for example
  "Sign in to the gateway to manage automations.", "This automation does not exist (or is not
  yours).", "An occurrence is already running or queued. Wait for it to finish."
- Automations are scoped to the gateway user you are signed in as: signing in as another user shows
  that user's automations.

## Limits

- Schedules are fixed intervals in UTC, or one run at a given time. There is no calendar recurrence
  (weekdays, local time zones).
- The only triggers the Assistant creates are the schedule and **Run now**.
- The Schedule window does not set a maximum number of runs or an end date; an automation created
  elsewhere with one shows it in its cadence.
- **Edit** changes an automation's title, interval and context mode only. The workflow and task
  it runs (its target) and its tool-approval policy change only through the gateway's
  `PATCH /api/gateway/automations/{id}` route; no app's edit form changes them. From the apps,
  archive the automation and schedule a new one.
