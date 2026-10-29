# 1081 — The iPhone's New automation sheet shows whether it will ask before tools

**Status**: completed (2026-10-29, unreleased) · **Priority**: P1 · **Created**: 2026-10-29
**Cross-package**: follows 1079 (`policy.tool_approval` from the tool modes) and 1080 (the desktop editor's per-tool
Off / Ask / Auto).

## Why
A new automation inherits the Settings tool defaults unless its Tools are set ("Settings defaults"). Since 1079 it is
created "ask" when one of those tools is on Ask, and the sheet did not say so: only "Settings defaults" or "Custom"
showed beside Tools. An automation could be created "ask" by accident, and its unattended runs would then wait for an
approval (QA 2026-10-29: a run waited 7 h). The tool modes also read "Approve", while the desktop, the watch and the
kit say Off / Ask / Auto.

## What shipped
- `AssistantKit/AutomationApprovalState`: from the modes the automation is created with, `asks`, the tools on Ask
  and the sentence: "Runs without asking: no tool is on Ask." or "Asks before Send Email: a run that uses it waits for
  your approval, even while this iPhone is closed." (three names, then "and N more"). It derives exactly what
  `NewAutomation` sends as `policy.tool_approval`.
- `NewAutomationScreen`: the sheet reads the tool inventory when it opens. It then shows the sentence under Tools
  (amber with a raised hand when it asks), for the Settings defaults and for custom tools alike, before Create. The
  footer says to set a tool to Auto so its runs do not wait.
- Tool modes read the kit's words: Off / Ask / Auto (`ToolMode.label`; the Tools footer says "Ask waits for you").
  The UI tests' segmented buttons follow.
- Package tests: `AutomationApprovalStateTests` covers no Ask (sends "auto"), one Ask (named, sends "ask"), many
  (counted), the state always equal to what is sent, and the kit's words. Mutation-checked: a state that never asks
  fails.
