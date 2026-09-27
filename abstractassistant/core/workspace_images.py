"""Images an answer names by a path in its run's workspace.

An agent that draws a chart writes ``memory_curve.png`` into the run's
workspace and answers ``![Memory over time](memory_curve.png)``. The reference
is RELATIVE to that workspace — a folder on the gateway host — so the chat
renderer, which knows neither the folder nor the host, used to hand Qt a bare
``<img src="memory_curve.png">``. Qt cannot load it (and the text browser loads
no file images at all, by design: `AutoSizingTextBrowser.loadResource`), so it
drew its built-in "missing image" glyph: a small document icon that is not a
link. That was the "non clickable icon and no curve" defect (2026-09-27).

This module decides, Qt-free, what an image reference names:

- ``workspace_relative_path`` — the workspace-relative path of a reference, or
  None for anything that is not one (a URL, ``data:``, a path that climbs out
  of the workspace with ``..``).
- ``local_workspace_image`` — the absolute local file for a reference when the
  workspace folder is on this machine, the file exists INSIDE it (symlinks
  resolved, so a link cannot point the renderer elsewhere) and its name is an
  image kind.
- ``downloaded_workspace_path`` — where a copy fetched through the gateway's
  workspace file route (``GET /runs/{id}/workspace/content``) is kept when the
  workspace is on another machine (images to show, files to open).

The renderer asks a resolver (built by the palette from these) for each image;
nothing here reads the network or blocks on a path the model chose: a
workspace root is only ever stat'ed when it is under a local, user-owned root
(`link_targets.is_safe_to_stat`).
"""

from __future__ import annotations

import hashlib
import os
import posixpath
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlparse

from .link_targets import is_safe_to_stat, local_path_from_href, path_kind

__all__ = [
    "downloaded_workspace_path",
    "local_workspace_image",
    "workspace_relative_path",
    "workspace_relative_to_root",
]

_MAX_REF_CHARS = 1024


def workspace_relative_path(src: str) -> Optional[str]:
    """``plots/a.png`` for ``./plots/a.png`` or ``plots%2Fa.png``; None otherwise.

    Only a scheme-less, non-absolute reference can name a workspace file. The
    query and fragment are dropped (a model sometimes cache-busts with ``?v=2``);
    ``..`` may not climb above the workspace folder.
    """
    text = str(src or "").strip()
    if not text or len(text) > _MAX_REF_CHARS:
        return None
    parsed = urlparse(text)
    if parsed.scheme or parsed.netloc or text.startswith(("/", "~", "#", "\\")):
        return None
    raw_path = unquote(parsed.path or "")
    if not raw_path or "\x00" in raw_path or "\\" in raw_path:
        return None
    parts: list[str] = []
    for part in raw_path.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            if not parts:
                return None
            parts.pop()
            continue
        parts.append(part)
    if not parts:
        return None
    return posixpath.join(*parts)


def _inside(root: str, candidate: str) -> bool:
    return candidate == root or candidate.startswith(root.rstrip(os.sep) + os.sep)


def local_workspace_image(src: str, workspace_root: str) -> Optional[str]:
    """The local file an image reference names inside ``workspace_root``, or None.

    ``src`` may be workspace-relative, or an absolute path / ``file:`` URL that
    lies inside the workspace. Everything is resolved through symlinks before
    the inside-the-workspace check, and only image kinds (by name) qualify.
    """
    root_text = str(workspace_root or "").strip()
    if not root_text or not os.path.isabs(root_text) or not is_safe_to_stat(root_text):
        return None
    text = str(src or "").strip()
    relative = workspace_relative_path(text)
    if relative is not None:
        candidate = os.path.join(root_text, *relative.split("/"))
    else:
        local = local_path_from_href(text) if text.lower().startswith("file:") else None
        if local is None and text.startswith("/"):
            local = os.path.normpath(text)
        if local is None:
            return None
        candidate = local
    if path_kind(candidate) != "image":
        return None
    try:
        real_root = os.path.realpath(root_text)
        real = os.path.realpath(candidate)
        if not _inside(real_root, real) or not os.path.isfile(real):
            return None
    except (OSError, ValueError):
        return None
    return real


def workspace_relative_to_root(path: str, workspace_root: str) -> Optional[str]:
    """``plots/a.png`` for ``<root>/plots/a.png`` (lexically; no stat), else None."""
    root = os.path.normpath(str(workspace_root or "").strip())
    target = os.path.normpath(str(path or "").strip())
    if not os.path.isabs(root) or not os.path.isabs(target) or not _inside(root, target) or target == root:
        return None
    return workspace_relative_path(os.path.relpath(target, root).replace(os.sep, "/"))


def downloaded_workspace_path(cache_dir: Path, *, run_id: str, relative_path: str) -> Optional[Path]:
    """Where the gateway copy of a remote workspace file is kept.

    One folder per (run, file), hashed so a run id never becomes a path, with
    the file's own name last so the OS opener and "Show in Finder" show what
    it is.
    """
    rel = workspace_relative_path(relative_path)
    rid = str(run_id or "").strip()
    if rel is None or not rid:
        return None
    digest = hashlib.sha256(f"{rid}\n{rel}".encode("utf-8")).hexdigest()[:16]
    return Path(cache_dir) / "workspace-files" / digest / posixpath.basename(rel)
