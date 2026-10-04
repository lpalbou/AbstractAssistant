"""A fake of the gateway's round-11 workspace levels for headless tests.

Answers in the shapes of "R11 WORKSPACE API — FINAL" (COORD): account and
session GET/PUT answer ``{ok, policy, gateway, effective[, account_default],
can_edit}``; a refusal is a GatewayHttpError whose body is the gateway's
``{"detail": {"reason": "workspace_refused", "message", "path"}}``. The fake
implements just enough of the gateway's rules to drive the UI: eligible set =
the gateway rows (posture allowed_only), caps = those rows' modes, and the
summary format "<posture>[ (<default>)] · <path> (ro|rw|refused) · …".
"""

from __future__ import annotations

import copy
import json
from typing import Any, Dict, List, Optional

POSTURE_LABEL = {
    "allowed_only": "Deny everything, allow listed workspaces",
    "any_except_denied": "Allow everything, refuse listed workspaces",
}
_RANK = {"deny": 0, "ro": 1, "rw": 2}


def summary(level: Dict[str, Any]) -> str:
    head = POSTURE_LABEL[level["posture"]]
    if level["posture"] == "any_except_denied":
        head += f" ({level['default_mode']})"
    parts = [head] + [f"{r['path']} ({'refused' if r['mode'] == 'deny' else r['mode']})" for r in level["folders"]]
    return " · ".join(parts)


class FakeWorkspaceGateway:
    def __init__(self, *, session_id: str = "session-1") -> None:
        self.session_id = session_id
        self.gateway = {
            "posture": "allowed_only",
            "default_mode": "rw",
            "folders": [{"path": "/data/project", "mode": "rw"}, {"path": "/archive", "mode": "ro"}],
        }
        self.account: Optional[Dict[str, Any]] = None  # None = follow the gateway policy
        self.sessions: Dict[str, Optional[Dict[str, Any]]] = {}
        self.puts: List[tuple] = []
        self.refuse: str = ""
        self.can_edit = True
        self.fetches = 0

    # ---------------------------------------------------------------- rules
    def cap(self, path: str) -> Optional[str]:
        best = None
        for row in self.gateway["folders"]:
            if path == row["path"] or path.startswith(row["path"].rstrip("/") + "/"):
                if best is None or len(row["path"]) > len(best["path"]):
                    best = row
        return best["mode"] if best else None

    def _effective(self, level: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "posture": level["posture"],
            "default_mode": level["default_mode"],
            "folders": [dict(r, cap=self.cap(r["path"]) or "deny", source=level.get("_source", "gateway")) for r in level["folders"]],
            "summary": summary(level),
            "gateway_summary": summary(self.gateway),
        }

    def _account_level(self) -> Dict[str, Any]:
        if self.account is None:
            return dict(copy.deepcopy(self.gateway), _source="gateway")
        return dict(copy.deepcopy(self.account), _source="account")

    def _session_level(self, sid: str) -> Dict[str, Any]:
        stored = self.sessions.get(sid)
        if stored is None:
            return self._account_level()
        return dict(copy.deepcopy(stored), _source="session")

    def _validate(self, body: Dict[str, Any]) -> Dict[str, Any]:
        from abstractassistant.gateway.client import GatewayHttpError

        def refuse(message: str, path: Optional[str] = None):
            text = json.dumps({"detail": {"reason": "workspace_refused", "message": message, "path": path}})
            raise GatewayHttpError(f"workspaces not saved: {text}", status=400, body_text=text)

        if self.refuse:
            refuse(self.refuse)
        level = {
            "posture": body.get("posture", self.gateway["posture"]),
            "default_mode": body.get("default_mode", self.gateway["default_mode"]),
            "folders": [dict(path=r["path"], mode=r["mode"]) for r in body.get("folders", [])],
        }
        for row in level["folders"]:
            if row["mode"] == "deny":
                continue
            cap = self.cap(row["path"])
            if cap is None or cap == "deny":
                refuse(f"{row['path']} is outside the workspaces this gateway allows.", row["path"])
            if _RANK[row["mode"]] > _RANK[cap]:
                refuse(f"The gateway allows {row['path']} read-only.", row["path"])
        return level

    # ------------------------------------------------------------ answers
    def answer(self, which: str, sid: str = "") -> Dict[str, Any]:
        gateway = dict(copy.deepcopy(self.gateway), summary=summary(self.gateway))
        if which == "account":
            level = self._account_level()
            policy = {"account": "default:me", "configured": self.account is not None}
            policy.update({k: v for k, v in level.items() if not k.startswith("_")})
            if self.account is None:
                policy["folders"] = []  # display base: the gateway's posture, no rows
            return {"ok": True, "policy": policy, "gateway": gateway, "effective": self._effective(level), "can_edit": self.can_edit}
        level = self._session_level(sid)
        policy = {"session_id": sid, "account": "default:me", "configured": self.sessions.get(sid) is not None}
        policy.update({k: v for k, v in level.items() if not k.startswith("_")})
        if self.sessions.get(sid) is None:
            policy["folders"] = []
        return {
            "ok": True,
            "policy": policy,
            "gateway": gateway,
            "account_default": self._effective(self._account_level()),
            "effective": self._effective(level),
        }

    # ------------------------------------------------ controller surface
    def workspace_policy(self) -> Dict[str, Any]:
        from abstractassistant.ui.settings.workspace_chooser import parse_answer

        self.fetches += 1
        return {
            "account": {"state": parse_answer(self.answer("account")), "error": ""},
            "session": {"session_id": self.session_id, "state": parse_answer(self.answer("session", self.session_id)), "error": ""},
        }

    def put_workspace_policy(self, level: str, body: Dict[str, Any], session_id: str = "") -> Dict[str, Any]:
        from abstractassistant.ui.settings.workspace_chooser import parse_answer

        self.puts.append((level, session_id, copy.deepcopy(body)))
        configured = body.get("configured") is not False
        stored = self._validate(body) if configured else None
        if level == "account":
            self.account = stored
            return parse_answer(self.answer("account"))
        self.sessions[session_id] = stored
        return parse_answer(self.answer("session", session_id))
