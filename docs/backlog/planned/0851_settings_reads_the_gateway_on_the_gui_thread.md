# 0851 — Settings reads the gateway on the GUI thread, and freezes for minutes when it is away

**Status**: planned · **Priority**: high · **Created**: 2026-09-18
**Package**: abstractassistant · **Found by**: the adversarial pass on the 2026-09-18
settings-simplification wave (the operator's "greyed out on the subway" report)

## Why

Opening Settings blocks the Qt event loop on synchronous HTTP. `GatewayClient` uses
`urllib.request.urlopen` with `timeout_s = 30.0` (`gateway/client.py:40`), and the settings
surfaces call it straight from the GUI thread: `controller.route_map` (:517),
`controller.provider_choices` (:598), `controller.model_choices` (:601),
`workspace_policy`, `tool_inventory`, `model_capabilities`. Nothing about the window is
painted, and nothing else in the app runs, until every one of them returns.

Measured by the adversarial pass against a black-hole host (`10.255.255.1:8080`), one
`RouteOverrideEditor.refresh()`:

```
refresh() BLOCKED THE GUI THREAD FOR 61.12 s   (7 round trips)
```

61 s only because macOS abandons an unroutable subnet early (7–11 s per call). A host that
is **routable but silent** — a gateway that has stopped answering, which is the case this
app actually hits — burns the full 30 s each: **~210 s frozen**, per open. And
`SettingsDialog.__init__` refreshes all seven pages, so the true first-open cost is higher
than the Models page alone.

## What the 2026-09-18 wave already did

Two of the seven calls were the Models page paying for the same thing twice, and both are
fixed here, with `test_opening_settings_costs_two_gateway_reads_not_seven` pinning it
(mutation-checked on both halves):

- `refresh()` called `_load_selected_route` explicitly after `setCurrentRow`, on a comment
  that claimed row 0 would not re-emit `currentRowChanged`. It does — `clear()` had already
  moved the current row to `-1` — so **every catalog fetch on the page was paid twice**.
- The reasoning caption asked `controller.effective_chat_route()`, which re-reads the
  capability defaults and does **not** cache a failure, so an unreachable gateway made it a
  fresh 30 s request every time the caption was rendered (4 of the 7 calls). The editor
  already holds both facts it needs; it now answers locally.

**7 round trips → 2, on every open and reopen.** That is a 3.5× cut, not a fix: two
synchronous 30 s calls still freeze the app for a minute.

## In scope

- Move the catalog and policy reads off the GUI thread, the way `ConnectionPage` already
  does it (`refresh_status_async` + a `_status_ready` signal): show the page immediately
  with "Loading…" in the lists, fill them when the answer lands, and keep "Gateway default"
  selectable throughout (it needs no gateway, and that is what the operator could not reach).
- Give the settings reads a short timeout of their own (2–5 s). A settings list is not worth
  30 s, and the 30 s default exists for run submission.
- Consider caching a successful catalog per `(route_key, provider, base_url)` for the
  window's lifetime, so switching between the ten routes is not ten round trips. Note the
  freshness cost: a provider started after the app (LM Studio, Ollama) would not appear until
  the list is reopened — the retry-on-empty already added in `_CatalogCombo` covers the empty
  case but not the grew-since case.

## Acceptance

Opening Settings against a silent gateway paints within one frame, never blocks the event
loop for more than the chosen timeout, and still lets the user pick "Gateway default" and
any previously saved override while the gateway is unreachable.

## Evidence

- `ui/settings/route_editor.py` (the 2 remaining reads), `gateway/client.py:40` (the 30 s
  timeout), `controller.py:517,598,601` (no threading), `ui/settings/dialog.py:197`
  (constructor refreshes all seven pages), `app.py:8832-8841` (the window is cached and
  `refresh()`ed on every reopen).
- `tests/basic/test_settings_routes.py::test_opening_settings_costs_two_gateway_reads_not_seven`
  and `::test_nothing_is_disabled_when_the_gateway_cannot_be_reached`.
