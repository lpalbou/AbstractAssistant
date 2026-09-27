# Sessions and automations

An **automation** runs a task on a schedule on the gateway: "search the news about AI agents every
8 hours", "triage my inbox every 30 minutes", "summarise my journal every 7 days". The gateway runs
it; the Assistant shows it, creates it, and answers it. Nothing runs on this Mac — an automation
keeps running when the Assistant is closed.

Automations need a gateway that advertises the Automations API in its capabilities
(`contracts.common.automations.available: true`). On a gateway that does not, none of the controls
below appear — no section, no tray entry — and the Assistant never calls the automation routes.

## Where automations appear

Click the session name in the palette header. Above the sessions, the switcher lists an
**Automations** section — one row per automation, whoever created it (the Assistant, the Observer
or another client):

- the title, and a badge when something needs you: `2 NEW` (unseen results or failures) and
  `WAITING` (a run is waiting for your answer);
- the cadence, always a fixed interval in UTC ("every 8 hours (UTC)", "every 7 days (UTC) · 12 runs
  max"), its status (Active, Paused, Archived…) and its context mode;
- the next run ("next in 3 h", "paused");
- the last run's status and a line of its result.

The section header counts what is new (`AUTOMATIONS · 3 NEW`); the tray menu entry
**Automations…** carries the same count and opens the switcher.

The sessions an automation runs in are **not** listed among your chats: they live under their
automation. The gateway tells the two apart with each session's kind (`chat`, `automation`,
`occurrence`, `discussion`); the Assistant never guesses from a session's name.

## Opening an automation

Click its row. The palette replaces the conversation with the automation's runs, read as a chat:
for each run, the task it was given (with what triggered it and when) and its answer, oldest at
the top. Quiet runs are shown dimmed; a failed run is red, with the reason and the number of
attempts; a run that waits for you is highlighted. **← Chat** returns to the conversation.

Opening an automation marks the results it shows as seen (runs waiting for you stay counted until
you answer them).

The controls above the runs:

| Control | What it does |
|---|---|
| **Pause** | No scheduled run until you resume. A run in progress finishes. |
| **Resume** | Back on the schedule, from the next scheduled time (it does not fire at once). |
| **Run now** | One run immediately. Works while paused, and stays paused. Disabled while a run is in progress. |
| **Stop current** | Stops the run in progress. |
| **Edit** | Title, interval (`30m`, `8h`, `7d`) and context mode. Applies from the next run. |
| **Archive** | Asks for confirmation in the palette. Nothing runs any more; the history is kept. |

A control that does not apply is disabled, with the reason in its tooltip. If the gateway could
not be reached, **Retry** sends the same request again (the gateway recognises it, so it is never
applied twice); after the gateway answered, retrying is a new request.

## Answering a run that waits for you

A run can stop and wait for you. You get a tray notification, and the run shows what it waits for:

- **a question** ("The landlord asks whether Tuesday works. Reply now?"): its choices and a
  free-text field; your answer goes to the gateway exactly like an answer to a question from a chat;
- **approval of tool calls** (only for an automation created with "Ask each time"): the tool calls
  it would run, with **Approve** and **Deny**;
- **an event**: a free-text field.

The gateway says which of the three a run waits for, and the Assistant answers accordingly. A wait
the gateway does not describe is shown without answer controls rather than answered blindly.

## Discuss a result

**Discuss** on a finished run opens a new session seeded with the automation's runs up to that
one, sends your question, and switches to it. It is an ordinary session: it keeps the workflow's
normal tools and appears among your chats with the badge **about automation <title>** (click the
badge to open the automation). Its workspace is the automation's, **read-only**, and nothing is
written back to the automation.

## Schedule this conversation

The clock button in the palette header opens **Schedule this conversation…**:

- **What** — the conversation's workflow (the one Settings → Workflow selects) and its last
  question, editable. The title defaults to the task's first line.
- **When (UTC)** — every 5 minutes, 30 minutes, hour, 8 hours, 24 hours or 7 days, every N
  minutes/hours/days, or once at a date and time. An optional first-run time (UTC); empty means now.
  Intervals are fixed UTC durations: "every 24 hours", never "daily at 08:00 local".
- **Context** — **Independent** (the default: each run starts fresh) or **Growing** (each run
  sees the previous runs, like a continuing conversation, within a bounded history).
- **Tools** — **Tools run without asking** (the default: you approve them now by creating this
  automation, since nobody is there to approve each run) or **Ask each time** (every run that wants
  a tool waits for your approval). Questions the workflow itself asks always wait for you.

**Schedule** creates the automation and opens it.

## Notifications

The Assistant checks the automation list every 60 seconds while the palette is open, and every 5
minutes while it is hidden — that hidden check is the only request the Assistant makes in the
background, and it exists so notifications reach the tray while the palette is closed. A tray
notification is shown once for each:

- result the automation marked as notable (the workflow's output carries `notify`);
- run that failed after all its retries (3 attempts by default);
- run waiting for your answer.

Ordinary results stay quiet: they update the list, never notify. Notifications are not repeated
after a relaunch (`~/.abstractassistant/automations_notified.json` remembers them); what is
"seen" is kept by the gateway, per user.

## Limits (v1)

- Schedules are fixed intervals in UTC; there is no calendar recurrence (weekdays, time zones).
- The only triggers are the schedule and "run now".
- Changing what an automation runs (its workflow) is done in the Observer.
