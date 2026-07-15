"""Helpers for Gateway-backed generated media artifacts."""

from __future__ import annotations

import hashlib
import re


_SAFE_RUN_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
_SESSION_MEMORY_RUN_PREFIX = "session_memory_"


def session_memory_run_id(session_id: str) -> str:
    """Mirror Gateway's stable session-memory run id for direct media artifacts."""

    sid = str(session_id or "").strip()
    if not sid:
        raise ValueError("session_id is required")
    if _SAFE_RUN_ID_PATTERN.match(sid):
        rid = f"{_SESSION_MEMORY_RUN_PREFIX}{sid}"
        if _SAFE_RUN_ID_PATTERN.match(rid):
            return rid
    digest = hashlib.sha256(sid.encode("utf-8")).hexdigest()[:32]
    return f"{_SESSION_MEMORY_RUN_PREFIX}sha_{digest}"
