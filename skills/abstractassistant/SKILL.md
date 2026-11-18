---
name: abstractassistant
description: Operate AbstractAssistant through its assistant or abstractassistant CLI and gateway connection. Use to run a terminal turn, choose the intended gateway, diagnose sign-in or connection failures, or understand how desktop, web and Apple clients use gateway workflows.
license: MIT
metadata:
  package-version: "0.19.1"
---

# AbstractAssistant

Use `assistant run` for a terminal turn through AbstractGateway. Launching `assistant` with no
subcommand opens the desktop app. The gateway owns workflows, model calls, tools, workspace
policy and durable runs; the Assistant owns local preferences, its UI and local voice I/O.
Do not use private Qt or worker APIs as an integration surface.

## Install and verify

```bash
python -m pip install abstractassistant
assistant --version
assistant run --help
```

Compare the printed version with `metadata.package-version`; use the installed version's docs if
they differ. For a source installation, run `python -m pip install .` in the package checkout.
The help/version commands do not require a gateway, GUI or voice stack.

## Mental model

- A terminal turn uses the workflow chosen in the app: Gateway default when offered for
  `abstractassistant.agent.v1`, otherwise the supported built-in `abstractassistant-orchestrator`.
  A removed explicit selection blocks sending until another workflow is chosen.
- Global flags precede `run`. An explicit gateway URL wins over the saved connection, followed
  by this computer's gateway discovery and finally `http://127.0.0.1:8080`.
- A saved sign-in belongs to its gateway. `--gateway-url` can reuse the sign-in saved for that
  address; `--gateway-token` explicitly supplies a bearer token. Stop on authentication failure
  and use the documented sign-in flow rather than retrying credentials.
- Runs honor local chat/media model, reasoning, MTP and streaming overrides from preferences;
  workspaces and tool permissions come from the gateway. Tool approvals are interactive.
- The final answer is printed once on stdout. Live reply text and progress go to stderr;
  interactive tool approvals and questions also print prompts on stdout. A successful turn with
  no interactive prompts can be redirected as the final answer. `--stream on|off` overrides streaming for
  one turn; it cannot add streaming support to a gateway that does not advertise it.
- CLI failures print their cause. A gateway sign-in failure exits 2 with sign-in instructions.
  An unreachable gateway is a connection failure; an empty or failed turn is not a successful
  answer. Read the CLI result and stderr before reporting completion.

## Capability map

- Terminal execution: `assistant run --prompt TEXT [--stream on|off]`.
- Gateway selection and authentication: global `--gateway-url` and `--gateway-token`.
- Desktop palette: `assistant`; Settings chooses workflows, models, workspaces and voice.
- Entity mentions: desktop/web conversation composer, `@` picker, Gateway 0.21.0 or later.
  Names become chips and entity replies keep their authors; a message naming only entities goes
  to them alone. This skill does not claim the terminal CLI implements that graphical picker.
- Web and iPhone/Watch clients: use their documented apps; the Python CLI does not operate their
  GUI controls or publish Apple builds.

Requests may call paid models and execute tools under gateway policy. Sending creates a durable
gateway turn; local preferences, connection/session caches, downloads and audio live under
`~/.abstractassistant/`. The local gateway pointer `~/.abstractframework/gateway.json` is read
only. The CLI is not a local in-process model or runtime engine.

## Run one terminal turn

Use an explicitly chosen gateway and credentials supplied outside the conversation:

```bash
assistant --gateway-url "${GATEWAY_URL:?Set the intended gateway URL}" \
  --gateway-token "${ABSTRACTGATEWAY_AUTH_TOKEN:?Set the gateway bearer token}" \
  run --prompt "Describe the files in my permitted workspace without changing them." --stream off
```

Use the saved sign-in instead by omitting `--gateway-token`. Confirm the selected workflow and
workspace before sending a task that changes files. Answer interactive tool approvals only within
the user's authorization. Do not invent a workflow or silently select another when discovery fails.

To capture a final answer, append `> answer.txt`; inspect the exit status and stderr. An interrupted
or failed command must not be reported as an answer just because the file exists.

## Recovery

- **Needs sign-in / 401:** open the Assistant from the gateway console or sign in through Settings
  → Connection. That saved sign-in is reused by the CLI. Do not put a token in the conversation.
- **Unreachable / reconnecting:** check the explicit URL and that gateway's health and connection
  status. Do not change models to work around a transport failure.
- **Chosen workflow unavailable:** select a supported workflow in Settings → Workflow; the app
  deliberately blocks instead of guessing.
- **Streaming not sent:** the gateway did not advertise live replies; the final answer still
  follows the supported turn path. Do not infer a model failure from the streaming notice alone.
- **Another client answered an approval:** follow the gateway replay view; clients share the same
  durable run and its current wait, not independent copies of the approval.

## Go deeper

- [Getting started](https://raw.githubusercontent.com/lpalbou/AbstractAssistant/main/docs/getting-started.md): connecting, first turn, desktop mentions and shortcuts.
- [API and CLI](https://raw.githubusercontent.com/lpalbou/AbstractAssistant/main/docs/api.md): flags, precedence, workflows, routes and local files.
- [Settings](https://raw.githubusercontent.com/lpalbou/AbstractAssistant/main/docs/settings.md): model, workspace, tool and voice overrides.
- [Troubleshooting](https://raw.githubusercontent.com/lpalbou/AbstractAssistant/main/docs/troubleshooting.md): connection, authentication and runtime failures.
- [Full docs](https://raw.githubusercontent.com/lpalbou/AbstractAssistant/main/llms-full.txt): offline documentation context.
