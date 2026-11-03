"""Avatars ship with every install (operator ruling): AbstractAvatar is a base dependency, and the
old `avatar` extra stays as an alias so `abstractassistant[avatar]` still resolves."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _project() -> dict:
    if sys.version_info >= (3, 11):
        import tomllib
    else:  # pragma: no cover
        import tomli as tomllib
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)["project"]


@pytest.mark.basic
def test_abstractavatar_is_a_base_dependency_with_the_gaze_catalog_floor() -> None:
    project = _project()
    avatar = [dep for dep in project["dependencies"] if re.match(r"abstractavatar\b", dep)]
    assert avatar == ["abstractavatar>=0.1.1"], "the avatar must be in every install, at 0.1.1 or later"
    assert project["optional-dependencies"]["avatar"] == [], "the avatar extra is a back-compat alias"
