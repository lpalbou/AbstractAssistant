"""Automations v1 client — one method per gateway route (contract F).

Mirrors the kit's `createAutomationsClient` (`@abstractframework/ui-kit`,
`src/automations/client.ts`): the same ten calls, the same full paths under
``/api/gateway/``, the same error rule. It rides the existing
:class:`~abstractassistant.gateway.client.GatewayClient` for the base URL, the
auth headers (bearer or session + CSRF) and the timeout.

- No polling inside and no timers: callers poll FULL pages themselves; v1 has
  no change cursor, so ``changed_since`` is never sent.
- Every non-2xx answer must carry the automation error envelope
  ``{"detail": {"reason_code", "message", "field"?, "command_id"?}}`` and is
  raised as :class:`AutomationApiError` whose ``reason_code`` is
  ``detail.reason_code``. A non-2xx without that envelope, or a 2xx body that is
  not a JSON object, raises ``invalid_response`` — never a silent success. A
  gateway that cannot be reached raises ``unreachable`` (status 0).
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
import uuid
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import quote

from .client import GatewayClient

__all__ = [
    "AUTOMATIONS_PATH",
    "MY_EMAIL_PATH",
    "TRIGGER_SOURCES_PATH",
    "AUTOMATION_COMMAND_TYPES",
    "AutomationApiError",
    "AutomationsClient",
    "parse_api_error",
]

AUTOMATIONS_PATH = "/api/gateway/automations"
TRIGGER_SOURCES_PATH = "/api/gateway/trigger-sources"
# The signed-in user's own email account (framework backlog 0992; never a secret).
MY_EMAIL_PATH = "/api/gateway/me/email"

# The `automation.*` command types of contract F (`command_types.py` on the
# gateway). `automation.revise` is normally sent through PATCH (`revise`).
AUTOMATION_COMMAND_TYPES = (
    "automation.revise",
    "automation.pause",
    "automation.resume",
    "automation.run_now",
    "automation.stop_current",
    "automation.archive",
)

# Guard for `list_all`: a gateway handing back the same cursor forever must not
# spin a poll thread.
_MAX_PAGES = 200


class AutomationApiError(RuntimeError):
    """A refused or unreadable automation call (contract F error envelope)."""

    def __init__(
        self,
        *,
        status: int,
        reason_code: str,
        message: str,
        field: Optional[str] = None,
        command_id: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.status = int(status)
        self.reason_code = str(reason_code)
        self.message = str(message)
        self.field = field
        self.command_id = command_id

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"AutomationApiError({self.status}, {self.reason_code!r}, {self.message!r})"


def parse_api_error(status: int, body: Any) -> AutomationApiError:
    """The contract envelope yields its ``reason_code``; any other shape is
    ``invalid_response`` (status kept)."""
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, dict):
        code = detail.get("reason_code")
        message = detail.get("message")
        if isinstance(code, str) and code and isinstance(message, str):
            field = detail.get("field")
            command_id = detail.get("command_id")
            return AutomationApiError(
                status=status,
                reason_code=code,
                message=message,
                field=field if isinstance(field, str) else None,
                command_id=command_id if isinstance(command_id, str) else None,
            )
    return AutomationApiError(
        status=status,
        reason_code="invalid_response",
        message=f"The gateway answered HTTP {status} without an automation error envelope.",
    )


def _query(params: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in params.items() if v is not None and v != ""}


class AutomationsClient:
    """The ten contract-F calls over one :class:`GatewayClient`."""

    def __init__(self, gateway: GatewayClient, *, new_id: Optional[Callable[[], str]] = None) -> None:
        self._gateway = gateway
        self._new_id = new_id or (lambda: uuid.uuid4().hex)

    # ----------------------------------------------------------- transport

    def _call(
        self,
        method: str,
        path: str,
        *,
        query: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        method = method.upper()
        gateway = self._gateway
        url = gateway._url(path, _query(query or {}))
        headers = {"Accept": "application/json"}
        headers.update(gateway._headers(mutating=method not in {"GET", "HEAD", "OPTIONS"}))
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=gateway.config.timeout_s) as resp:
                status = int(getattr(resp, "status", 200) or 200)
                raw = resp.read() or b""
        except urllib.error.HTTPError as exc:
            status = int(getattr(exc, "code", 0) or 0)
            try:
                raw = exc.read() or b""
            except Exception:
                raw = b""
            raise parse_api_error(status, _loads(raw)) from None
        except (urllib.error.URLError, socket.timeout, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            raise AutomationApiError(
                status=0,
                reason_code="unreachable",
                message=f"The gateway could not be reached ({type(exc).__name__}: {reason}).",
            ) from None
        parsed = _loads(raw)
        if not isinstance(parsed, dict):
            raise AutomationApiError(
                status=status,
                reason_code="invalid_response",
                message=f"The gateway answered {method} {path} with a body that is not a JSON object.",
            )
        return parsed

    @staticmethod
    def _one(automation_id: str) -> str:
        aid = str(automation_id or "").strip()
        if not aid:
            raise ValueError("automation_id is required")
        return f"{AUTOMATIONS_PATH}/{quote(aid, safe='')}"

    # --------------------------------------------------------------- calls

    def list(self, *, status: Optional[str] = None, cursor: Optional[str] = None, limit: Optional[int] = None) -> Dict[str, Any]:
        """``GET /automations`` — one ``Page<AutomationSummary>``."""
        return self._call("GET", AUTOMATIONS_PATH, query={"status": status, "cursor": cursor, "limit": limit})

    def list_all(self, *, status: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Every summary, following ``next_cursor`` (v1 clients poll full pages)."""
        items: List[Dict[str, Any]] = []
        cursor: Optional[str] = None
        seen: set = set()
        for _ in range(_MAX_PAGES):
            page = self.list(status=status, cursor=cursor, limit=limit)
            batch = page.get("items")
            if not isinstance(batch, list):
                raise AutomationApiError(
                    status=200, reason_code="invalid_response", message="The automation list has no items array."
                )
            items.extend(item for item in batch if isinstance(item, dict))
            nxt = page.get("next_cursor")
            if not isinstance(nxt, str) or not nxt or nxt in seen:
                return items
            seen.add(nxt)
            cursor = nxt
        return items

    def get(self, automation_id: str) -> Dict[str, Any]:
        """``GET /automations/{id}`` → ``{definition, active_revision, summary}``."""
        return self._call("GET", self._one(automation_id))

    def create(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """``POST /automations`` → ``{automation_id, revision, summary}``."""
        if not isinstance(body, dict) or not str(body.get("request_id") or "").strip():
            raise ValueError("create: body.request_id is required")
        return self._call("POST", AUTOMATIONS_PATH, body=body)

    def revise(
        self,
        automation_id: str,
        *,
        changes: Dict[str, Any],
        expected_revision: Optional[int] = None,
        command_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """``PATCH /automations/{id}`` → ``CommandReceipt``."""
        body: Dict[str, Any] = {"command_id": command_id or self._new_id()}
        if expected_revision is not None:
            body["expected_revision"] = int(expected_revision)
        body["changes"] = dict(changes or {})
        return self._call("PATCH", self._one(automation_id), body=body)

    def command(
        self,
        automation_id: str,
        type_: str,
        *,
        payload: Optional[Dict[str, Any]] = None,
        command_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """``POST /automations/{id}/commands`` → ``CommandReceipt``."""
        if type_ not in AUTOMATION_COMMAND_TYPES:
            raise ValueError(f"command: unknown automation command type {type_!r}")
        body: Dict[str, Any] = {"command_id": command_id or self._new_id(), "type": type_}
        if payload is not None:
            body["payload"] = dict(payload)
        return self._call("POST", f"{self._one(automation_id)}/commands", body=body)

    def occurrences(self, automation_id: str, *, cursor: Optional[str] = None, limit: Optional[int] = None) -> Dict[str, Any]:
        """``GET /automations/{id}/occurrences`` → ``Page<OccurrenceRow>`` (newest first)."""
        return self._call("GET", f"{self._one(automation_id)}/occurrences", query={"cursor": cursor, "limit": limit})

    def discuss(
        self,
        automation_id: str,
        *,
        occurrence_index: int,
        prompt: str,
        request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """``POST /automations/{id}/discuss`` → ``{session_id, run_id, session_kind}``."""
        body = {
            "request_id": request_id or self._new_id(),
            "occurrence_index": int(occurrence_index),
            "prompt": str(prompt),
        }
        return self._call("POST", f"{self._one(automation_id)}/discuss", body=body)

    def seen(self, automation_id: str, attention_cursor: str) -> Dict[str, Any]:
        """``POST /automations/{id}/seen`` → ``{attention_cursor}`` (the max kept)."""
        cursor = str(attention_cursor or "").strip()
        if not cursor:
            raise ValueError("seen: attention_cursor is required")
        return self._call("POST", f"{self._one(automation_id)}/seen", body={"attention_cursor": cursor})

    def attention(self, automation_id: str, *, cursor: Optional[str] = None, limit: Optional[int] = None) -> Dict[str, Any]:
        """``GET /automations/{id}/attention`` → ``Page<AttentionItem>`` (unseen, oldest first)."""
        return self._call("GET", f"{self._one(automation_id)}/attention", query={"cursor": cursor, "limit": limit})

    def trigger_sources(self) -> Dict[str, Any]:
        """``GET /trigger-sources`` → ``{items: [TriggerSource + {available, …}]}``."""
        return self._call("GET", TRIGGER_SOURCES_PATH)

    def my_email(self) -> Dict[str, Any]:
        """``GET /me/email`` → the user's own account status (``configured``,
        ``effective_enabled``, ``address``, …; never a secret). Decides whether
        the Schedule sheet offers the email options."""
        return self._call("GET", MY_EMAIL_PATH)

    def console_url(self, tab: str = "users") -> str:
        """The gateway console's tab (My email lives in the Users tab)."""
        return f"{self._gateway._url('/console')}#{tab}"


def _loads(raw: bytes) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None
