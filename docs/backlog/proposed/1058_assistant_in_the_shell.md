# 1058 — The assistant in the shell: `assistant "find me file X"`

> Package: abstractassistant
> Type: feature
> Created: 2026-10-26
> Status: Proposed
> Completed: N/A
> Priority: P2
> Labels: cli, desktop, install

## Current code reality

The desktop install already ships a terminal entry point. `assistant run --prompt TEXT`
(`abstractassistant/cli.py:51-63`) runs ONE agentic turn through the same gateway workflow the
tray uses, in the app's active local session (`cli.py:276-291`, `llm_manager.active_session_id`),
with the same model, media and reasoning overrides from `preferences.json`, the workspaces the
gateway grants, interactive tool approvals (`cli.py:101-107`) and `ask_user` answers
(`cli.py:336`), and streaming to stderr with the final answer on stdout (`docs/api.md:112-123`).
So "find me file X", "open doc Z and check that" and "look online for Y" already work as
`assistant run --prompt "..."`, with the tools the gateway exposes to the assistant.

What is missing is the ergonomics the operator asked for on 2026-10-26: the systray is the
simpler access, the shell should be the equally simple second door.

## Scope and expected outcome

- **Bare prompt.** `assistant "find me the invoice from March"` is `assistant run --prompt ...`.
  A first positional argument that is not a known subcommand is the prompt. `assistant` alone
  in a terminal (stdin is a TTY) opens a conversation: a prompt loop in the same session, with
  the same approval and question dialogs, `Ctrl-C` stops the current run, `Ctrl-D` leaves.
  `assistant` with no TTY keeps today's behaviour (the tray), so launchers are unaffected.
- **Session control.** `--new` starts a fresh conversation; `--session <title or id>` continues
  a named one (the gateway-first session list of 0853 is the source); the default stays the
  tray's active session, so the shell and the palette are one conversation unless asked.
- **Attachments.** `--file PATH` (repeatable) uploads through the same `$artifact` path the
  tray uses (`ui/gateway_worker.py:197-220`), so a document checked from the shell shows in the
  palette's history with its thumbnail.
- **Plain output.** The final answer on stdout as Markdown by default; `--plain` strips it;
  `--json` prints the run id, the answer and the stats for scripts.
- **Same install, same sign-in.** No new package: the entry point ships with the desktop wheel
  and the Mac bundle (the bundle can expose `Contents/MacOS/assistant` or a symlink hint in
  `docs/INSTALLATION.md`), reusing `~/.abstractassistant/gateway_connection.json`.

Expected outcome: a person who installed the desktop assistant can type one line in a terminal
and get the same assistant, with the same tools, approvals and conversation, without learning
subcommands.

## Non-goals

- Not a second agent: no local tool execution, no workflow of its own; the gateway runs the
  same managed assistant workflow (ADR 0001).
- Not AbstractCode: no editor, repo or diff features; that product exists for code.
- Not voice in the terminal.

## Promotion criteria

- The operator confirms the bare-prompt and conversation shapes above (or edits them).
- The desktop host decision (ADR 0008, pending) does not move the CLI: it stays Python, it is
  a client of the gateway like the tray, and a Rust shell would ship it unchanged or call it.

## Validation ideas

- `tests/basic`: the argument parser maps a bare prompt, a subcommand and no arguments correctly
  with and without a TTY; `--file` builds the same upload request as the tray's worker.
- A walk against a hermetic gateway: one turn with a tool approval answered in the terminal,
  then the same session opened in the palette shows the turn and its attachment.

## Size and owner

M (parser and loop: S; session selection and attachments: M; docs: S). Owner: assistant seat.
