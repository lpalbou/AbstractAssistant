#!/usr/bin/env python3
"""Generate `llms-full.txt` from the most useful repo files.

Why:
- `llms.txt` is an index of canonical docs/code entrypoints for LLMs/agents.
- `llms-full.txt` is the "single-file context bundle" version, suitable for offline use
  or for pasting into a model context window.

This script intentionally avoids huge UI files (for example `abstractassistant/ui/qt_bubble.py`).
"""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]

INCLUDED_FILES: list[str] = [
    "llms.txt",
    "README.md",
    "docs/README.md",
    "docs/INSTALLATION.md",
    "docs/getting-started.md",
    "docs/api.md",
    "docs/architecture.md",
    "docs/faq.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "ACKNOWLEDGMENTS.md",
    "LICENSE",
    "CHANGELOG.md",
    "pyproject.toml",
    "abstractassistant/cli.py",
    "abstractassistant/config.py",
    "abstractassistant/app.py",
    "abstractassistant/create_app_bundle.py",
    "abstractassistant/core/agent_host.py",
    "abstractassistant/core/tool_policy.py",
    "abstractassistant/core/session_index.py",
    "abstractassistant/core/session_store.py",
    "abstractassistant/core/llm_manager.py",
    "docs/devnotes/README.md",
    "scripts/update_llms_full.py",
    "tests/basic/test_tool_policy.py",
    "tests/basic/test_session_index.py",
    "tests/basic/test_session_store.py",
    "tests/basic/test_transcript_summary.py",
    "tests/integration/test_agent_host_tool_wait_resume.py",
    "tests/integration/test_agent_host_restart_resume.py",
    "tests/integration/test_agent_host_allowed_tools_allowlist.py",
]


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    out_path = ROOT / "llms-full.txt"

    missing: list[str] = []
    for rel in INCLUDED_FILES:
        if not (ROOT / rel).exists():
            missing.append(rel)
    if missing:
        print("Missing required files:", file=sys.stderr)
        for rel in missing:
            print(f"- {rel}", file=sys.stderr)
        return 2

    header = (
        "# AbstractAssistant — llms-full.txt\n\n"
        "This file is intended for LLMs/agents. It concatenates the most useful docs and core backend code from the\n"
        "repository into a single, plain-text bundle.\n\n"
        "Regenerate:\n"
        "  python scripts/update_llms_full.py\n\n"
        "Included files (in order):\n"
        + "\n".join(f"- {p}" for p in INCLUDED_FILES)
        + "\n\n"
    )

    parts: list[str] = [header]
    for rel in INCLUDED_FILES:
        p = ROOT / rel
        content = _read_text(p).rstrip("\n")
        parts.append(f"--- {rel} ---\n")
        parts.append(content + "\n\n")

    out_path.write_text("".join(parts), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
