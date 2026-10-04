"""Round 9 (R9.3): Settings → Workspace = the gateway's folder model, the same
rows and words as the console and AbstractCode (ui-kit WorkspaceChooser):
shared workspace always on, admin-allowed folders as switches (off until
turned on), "My folders" only while the admin allows any folder, the
gateway's one-line summary; one PUT /workspace/policy/me per change; the
gateway's refusal sentence shown with "Not saved."; no local policy logic."""

from __future__ import annotations

import copy
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest

from abstractassistant.preferences import AssistantPreferences
from abstractassistant.ui.settings import workspace_folders as wf

from test_settings_pages import _Controller, _dialog  # noqa: E402 (tests/basic is on sys.path)

SHARED = "/srv/gw/workspaces"
A = "/data/projects"
B = "/data/notes"
OWN = "/home/me/thesis"
DENIED = "/etc/secrets"


def _ctl(**effective):
    ctl = _Controller()
    ctl.workspace_state = copy.deepcopy(_Controller.workspace_state)
    ctl.workspace_state["effective"].update(effective)
    ctl.workspace_puts = []
    ctl.workspace_refuse = ""
    return ctl


def _page(ctl):
    dlg, _ = _dialog(ctl)
    dlg.show_section("workspace")
    page = dlg.page_workspace
    page.refresh()
    return dlg, page


@pytest.mark.basic
def test_rows_shared_always_on_switches_only_for_admin_allowed_folders() -> None:
    dlg, page = _page(_ctl())
    T = wf.WORKSPACE_CHOOSER_TEXT
    assert page.folders_card.title_label.text() == T["title"]
    assert page.shared_label is not None and page.shared_label.text() == SHARED
    assert list(page.extra_switches) == [A, B]
    assert page.extra_switches[A].isChecked() is True
    assert page.extra_switches[B].isChecked() is False
    assert SHARED not in page.extra_switches and DENIED not in page.extra_switches
    assert page.effective_label.text() == f"<b>{T['effectivePrefix']}</b> Shared workspace + 1 folder. Never: 1 folder."
    assert page.own_field is None and page.own_note is not None and page.own_note.text() == T["ownHidden"]
    assert not hasattr(page, "workspace_mode_combo")
    dlg.close()


@pytest.mark.basic
def test_a_switch_is_one_put_and_a_refusal_shows_the_gateway_sentence() -> None:
    ctl = _ctl()
    dlg, page = _page(ctl)
    page.extra_switches[B].click()
    assert ctl.workspace_puts == [{"enabled_folders": [A, B]}]
    assert page.extra_switches[B].isChecked() is True
    ctl.workspace_refuse = f"Folder {B} is no longer allowed on this gateway."
    page.extra_switches[A].click()
    assert ctl.workspace_puts[-1] == {"enabled_folders": [B]}
    # Refused: the row keeps its previous state and says why, verbatim.
    assert page.extra_switches[A].isChecked() is True
    notes = [w.text() for w in page.rows_host.findChildren(type(page.load_note)) if w.property("workspace") == "refusal"]
    assert notes == [f"Folder {B} is no longer allowed on this gateway. Not saved."]
    dlg.close()


@pytest.mark.basic
def test_my_folders_only_when_any_folder_is_allowed_add_return_escape_remove() -> None:
    ctl = _ctl(own_folders_allowed=True)
    dlg, page = _page(ctl)
    assert page.own_note is None and page.own_field is not None
    page.own_field.setFocus()
    QTest.keyClicks(page.own_field, "/tmp/scratch")
    QTest.keyClick(page.own_field, Qt.Key_Escape)
    assert page.own_field.text() == "" and ctl.workspace_puts == []
    page.own_field.setText(OWN)
    QTest.keyClick(page.own_field, Qt.Key_Return)
    assert ctl.workspace_puts == [{"own_folders": [OWN]}]
    assert OWN in page.own_rows and page.own_field.text() == ""
    page._remove_own(OWN)
    assert ctl.workspace_puts[-1] == {"own_folders": []}
    assert OWN not in page.own_rows
    ctl.workspace_refuse = f"Folder {DENIED} is never allowed."
    page.own_field.setText(DENIED)
    page._add_own()
    assert page.own_field.text() == DENIED  # kept unsaved with the sentence
    notes = [w.text() for w in page.rows_host.findChildren(type(page.load_note)) if w.property("workspace") == "refusal"]
    assert notes == [f"Folder {DENIED} is never allowed. Not saved."]
    dlg.close()


@pytest.mark.basic
def test_a_listed_folder_the_gateway_marks_never_allowed_is_not_switchable() -> None:
    ctl = _ctl(available_folders=[{"path": A, "enabled": False, "never_allowed": True}, {"path": B, "enabled": False}])
    dlg, page = _page(ctl)
    assert page.extra_switches[A].unavailable_reason == wf.WORKSPACE_CHOOSER_TEXT["neverAllowed"]
    page.extra_switches[A].click()
    assert ctl.workspace_puts == []
    assert page.extra_switches[B].unavailable_reason == ""
    dlg.close()


@pytest.mark.basic
def test_inactive_own_folders_sentence() -> None:
    ctl = _ctl(own_folders_allowed=False, own_folders_inactive=True)
    ctl.workspace_state["policy"]["own_folders"] = [OWN]
    dlg, page = _page(ctl)
    assert page.own_note.text() == wf.WORKSPACE_CHOOSER_TEXT["ownInactive"]
    assert OWN not in page.own_rows
    dlg.close()


@pytest.mark.basic
def test_a_folder_the_admin_did_not_allow_never_reaches_a_put_body() -> None:
    state = wf.parse_state({"ok": True, **copy.deepcopy(_Controller.workspace_state)})
    view = wf.account_view(state)
    assert wf.extra_body(view, DENIED, True) == {"enabled_folders": [A]}
    assert wf.extra_body(view, B, True) == {"enabled_folders": [A, B]}


@pytest.mark.basic
def test_pre_round9_answer_fails_loudly() -> None:
    with pytest.raises(wf.WorkspaceAnswerError):
        wf.parse_state({"ok": True, "policy": {"mode": "whitelist"}})


@pytest.mark.basic
def test_controller_reads_and_writes_me_and_runs_send_no_folder_list() -> None:
    from abstractassistant.controller import AssistantController

    calls = []

    class _GW:
        def workspace_account_policy(self, account="me"):
            calls.append(("GET", account))
            return {"ok": True, **copy.deepcopy(_Controller.workspace_state)}

        def put_workspace_account_policy(self, body, account="me"):
            calls.append(("PUT", account, body))
            return {"ok": True, **copy.deepcopy(_Controller.workspace_state)}

    ctl = AssistantController.__new__(AssistantController)
    import threading

    ctl._cache_lock = threading.RLock()
    ctl._cache_epoch = 0
    ctl._cache_ttl_s = 30.0
    ctl._workspace_policy_cache = None
    ctl._workspace_policy_cache_at = 0.0
    ctl.gateway = _GW()
    out = ctl.workspace_policy()
    assert out["error"] == "" and out["state"]["effective"]["shared_workspace"] == SHARED
    ctl._workspace_policy_cache = None
    ctl.put_workspace_folders({"enabled_folders": [A]})
    assert calls == [("GET", "me"), ("PUT", "me", {"enabled_folders": [A]})]
    scope = AssistantPreferences(workspace_root="/srv/gw/workspaces/x").run_scope()
    assert "workspace_access_mode" not in scope and "workspace_allowed_paths" not in scope
    legacy = AssistantPreferences.from_dict({"workspace_access_mode": "all_except_ignored", "workspace_allowed_paths": ["/x"]})
    assert "workspace_access_mode" not in legacy.to_dict() and "workspace_allowed_paths" not in legacy.to_dict()


@pytest.mark.basic
def test_wording_is_the_kit_table() -> None:
    """The exact strings (X3): any drift from ui-kit WORKSPACE_CHOOSER_TEXT is a failure.
    The cross-repo diff runs in the round-9 gate (untracked/round4/r9/w3/check_wording.py)."""
    T = wf.WORKSPACE_CHOOSER_TEXT
    assert T["title"] == "Workspace folders"
    assert T["sharedLabel"] == "Shared workspace" and T["sharedState"] == "Always on"
    assert T["allowedTitle"] == "Allowed folders" and T["ownTitle"] == "My folders"
    assert T["ownHidden"] == "My folders appear when the gateway admin allows any folder."
    assert T["effectivePrefix"] == "Agents may use:" and T["notSaved"] == "Not saved."
    src = Path(wf.__file__).read_text(encoding="utf-8")
    assert "available_folders" in src and "never_allowed" not in src.split("WORKSPACE_CHOOSER_TEXT")[2]
