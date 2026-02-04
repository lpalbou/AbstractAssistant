"""Tool approval policy helpers for AbstractAssistant."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Set


_DEFAULT_SAFE_AUTO_APPROVE: Set[str] = {
    # Read-only filesystem
    "list_files",
    "skim_folders",
    "analyze_code",
    "read_file",
    "skim_files",
    "search_files",
    # Network read-only
    "web_search",
    "fetch_url",
}

_DEFAULT_REQUIRE_APPROVAL: Set[str] = {
    # Side effects
    "write_file",
    "edit_file",
    "execute_command",
    # Agent-only side effects
    "execute_python",
    "self_improve",
}


@dataclass(frozen=True)
class ToolApprovalPolicy:
    """Decide whether a batch of tool calls should require user approval."""

    auto_approve_tools: Set[str] = field(default_factory=lambda: set(_DEFAULT_SAFE_AUTO_APPROVE))
    require_approval_tools: Set[str] = field(default_factory=lambda: set(_DEFAULT_REQUIRE_APPROVAL))

    def requires_approval(self, tool_calls: Sequence[Dict[str, object]]) -> bool:
        """Return True if any tool call in the batch requires explicit approval."""
        for tc in tool_calls or []:
            name = str((tc or {}).get("name") or "").strip()
            if not name:
                return True
            if name in self.require_approval_tools:
                return True
            if name not in self.auto_approve_tools:
                return True
        return False

    def describe(self) -> Dict[str, List[str]]:
        return {
            "auto_approve_tools": sorted(self.auto_approve_tools),
            "require_approval_tools": sorted(self.require_approval_tools),
        }

