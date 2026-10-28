"""Write src/lib/__fixtures__/tool_policy_parity.json FROM the desktop's controller.

The web's tool lists are the kit's plan (ui-kit `planRunTools`, backlog 0033);
src/lib/tool_plan.test.ts checks it against these cases (tools and the auto / ask split).

Each case is a `GET /discovery/tools` answer and what the desktop sends for it
with no local per-tool settings and no chat trust grant:
`allowed_tools_for_run()` and `tool_policy_for_run()` (abstractassistant/controller.py).
Every tool in these cases carries the gateway's `approval_default` (the web
asks for a tool without one; the desktop then uses its local lists — not a
parity case). Re-run after changing either side; needs the package's
dependencies (the controller imports them):

    PYTHONPATH=. python -P web/scripts/gen_tool_policy_parity.py   # from the repository root
"""

import json
import pathlib

from abstractassistant.controller import AssistantController
from abstractassistant.preferences import AssistantPreferences

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIXTURE = json.loads((ROOT / "tests/basic/fixtures/discovery_tools_command_sandbox.json").read_text(encoding="utf-8"))

CASES = [
    ("desktop fixture discovery_tools_command_sandbox.json", FIXTURE),
    ("toolset order, duplicates, disabled", {"items": [
        {"name": "web_search", "toolset": "web", "approval_default": "auto"},
        {"name": "fetch_url", "toolset": "web", "approval_default": "auto"},
        {"name": "send_email", "toolset": "email", "approval_default": "ask"},
        {"name": "fetch_url", "toolset": "web", "approval_default": "ask"},
        {"name": "delete_file", "toolset": "files", "approval_default": "ask", "enabled": False},
        {"name": "", "toolset": "x", "approval_default": "auto"},
    ]}),
]


class _Gateway:
    def __init__(self, payload):
        self.payload = payload

    def discovery_tools(self):
        return self.payload


def desktop_lists(payload):
    c = AssistantController.__new__(AssistantController)
    c.gateway = _Gateway(payload)
    c.preferences = AssistantPreferences()
    inventory = c._compute_tool_inventory()
    c.tool_inventory = lambda: inventory
    c.session_trust_rank = lambda: 0
    return {"allowed_tools": c.allowed_tools_for_run(), "tool_policy": c.tool_policy_for_run()}


out = [{"name": name, "discovery": payload, "expected": desktop_lists(payload)} for name, payload in CASES]
target = ROOT / "web" / "src" / "lib" / "__fixtures__" / "tool_policy_parity.json"
target.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(f"wrote {len(out)} cases to {target}")
