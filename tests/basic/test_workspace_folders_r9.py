"""Round 9 FINAL wording (R9.3 / R10.4): Settings → Workspace = the gateway's
workspace model with the same rows and words as the console and AbstractCode
(ui-kit WorkspaceChooser): the posture ("Deny everything, allow listed
workspaces" / "Allow everything, refuse listed workspaces"), the shared
workspace (Read & write), the Allowed / Refused workspaces each with Read &
write / Read-only / Refused (lower, never raise), Everything else + the add
row only under the second posture, the gateway's effective line verbatim; a
friendly Gateway policy card; one PUT /workspace/policy/me per change; the
gateway's refusal sentence with "Not saved."; no local policy logic."""

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

T = wf.WORKSPACE_CHOOSER_TEXT
SHARED = "/srv/gw/workspaces"
P = "/data/project"
AR = "/archive"
SEC = "/secrets"
X = "/elsewhere"
LINE_A = "Deny everything, allow listed workspaces · Shared workspace (rw) · /data/project (rw) · /archive (ro)"


def _posture_b(state):
    state["gateway"].update(posture="any_except_denied", folders=[{"path": SEC, "mode": "deny"}, {"path": AR, "mode": "ro"}])
    state["effective"].update(
        posture="any_except_denied",
        default_mode="rw",
        folders=[{"path": SHARED, "mode": "rw", "source": "shared"}, {"path": SEC, "mode": "deny", "source": "gateway"}, {"path": AR, "mode": "ro", "source": "gateway"}],
        summary="Allow everything, refuse listed workspaces (rw) · Shared workspace (rw) · /secrets (refused) · /archive (ro)",
    )
    return state


def _ctl(b: bool = False):
    ctl = _Controller()
    ctl.workspace_state = copy.deepcopy(_Controller.workspace_state)
    if b:
        _posture_b(ctl.workspace_state)
    ctl.workspace_puts = []
    ctl.workspace_refuse = ""
    return ctl


def _page(ctl):
    dlg, _ = _dialog(ctl)
    dlg.show_section("workspace")
    page = dlg.page_workspace
    page.refresh()
    return dlg, page


def _notes(page, kind):
    return [w.text() for w in page.rows_host.findChildren(type(page.load_note)) if w.property("workspace") == kind]


@pytest.mark.basic
def test_posture_a_rows_modes_line_and_no_add_row() -> None:
    dlg, page = _page(_ctl())
    assert page.folders_card.title_label.text() == T["title"] == "Workspaces"
    assert page.posture_badge.text() == T["postureAllowedOnly"]
    assert page.shared_label.text() == SHARED
    assert list(page.row_widgets) == [P, AR]
    assert page.mode_buttons[P]["rw"].isChecked() and not page.mode_buttons[P]["rw"].property("unavailable")
    # /archive is read-only for the admin: the account cannot raise it.
    assert page.mode_buttons[AR]["ro"].isChecked()
    assert page.mode_buttons[AR]["rw"].property("unavailable") is True
    assert page.mode_buttons[AR]["rw"].toolTip() == T["accessCeiling"]
    assert page.effective_label.text() == LINE_A.replace("&", "&amp;")
    assert page.add_field is None and page.admin_only_note.text() == T["adminOnlyAdds"]
    assert "everything-else" not in page.row_widgets
    dlg.close()


@pytest.mark.basic
def test_one_put_per_choice_raise_is_impossible_and_refusal_is_verbatim() -> None:
    ctl = _ctl()
    dlg, page = _page(ctl)
    page.mode_buttons[P]["ro"].click()
    assert ctl.workspace_puts == [{"folders": [{"path": P, "mode": "ro"}]}]
    assert page.mode_buttons[P]["ro"].isChecked()
    page.mode_buttons[AR]["rw"].click()  # above the admin's mode: nothing is sent
    assert len(ctl.workspace_puts) == 1
    ctl.workspace_refuse = f"{AR} cannot be refused while an automation needs it."
    page.mode_buttons[AR]["deny"].click()
    assert ctl.workspace_puts[-1] == {"folders": [{"path": P, "mode": "ro"}, {"path": AR, "mode": "deny"}]}
    assert page.mode_buttons[AR]["ro"].isChecked()  # refused: the row keeps its mode
    assert _notes(page, "refusal") == [f"{AR} cannot be refused while an automation needs it. Not saved."]
    dlg.close()


@pytest.mark.basic
def test_posture_b_everything_else_add_row_refused_rows() -> None:
    ctl = _ctl(b=True)
    dlg, page = _page(ctl)
    assert page.posture_badge.text() == T["postureAnyExceptDenied"]
    assert list(page.row_widgets)[:2] == [AR, SEC]  # allowed first, then refused
    assert SEC not in page.mode_buttons  # the admin's refused row is fixed
    assert page.mode_buttons["everything-else"]["rw"].isChecked()
    page.mode_buttons["everything-else"]["ro"].click()
    assert ctl.workspace_puts[-1] == {"default_mode": "ro"}
    assert page.admin_only_note is None and page.add_field is not None
    assert page.add_field.placeholderText() == T["addPlaceholder"] == "Add a workspace path"
    QTest.keyClicks(page.add_field, "/tmp/scratch")
    QTest.keyClick(page.add_field, Qt.Key_Escape)
    assert page.add_field.text() == ""
    page.add_field.setText(X)
    QTest.keyClick(page.add_field, Qt.Key_Return)
    assert ctl.workspace_puts[-1] == {"folders": [{"path": X, "mode": "deny"}]}
    assert X in page.row_widgets and page.row_widgets[X].property("workspace") == "account-row"
    page._remove_row(X)
    assert ctl.workspace_puts[-1] == {"folders": []}
    dlg.close()


@pytest.mark.basic
def test_gateway_policy_card_is_friendly() -> None:
    dlg, page = _page(_ctl(b=True))
    texts = [w.text() for w in page.policy_host.findChildren(type(page.posture_badge))]
    assert T["postureAnyExceptDenied"] in texts
    assert f"archive · {T['accessRead']}" in texts and "secrets" in texts
    assert not any(":" in t and "policy" in t.lower() for t in texts)  # no key: value dump
    dlg.close()


@pytest.mark.basic
def test_bodies_never_raise_and_never_invent() -> None:
    state = wf.parse_state({"ok": True, **copy.deepcopy(_Controller.workspace_state)})
    view = wf.account_view(state)
    row_ar = next(r for r in view.rows if r.path == AR)
    assert row_ar.choices == ("ro", "deny")
    assert wf.mode_body(state, row_ar, "rw") == {"folders": []}  # rw is never stored
    assert wf.mode_body(state, row_ar, "deny") == {"folders": [{"path": AR, "mode": "deny"}]}
    assert wf.default_mode_body("rw") == {"default_mode": None}


@pytest.mark.basic
def test_pre_round9_answer_fails_loudly() -> None:
    for bad in ({"ok": True, "policy": {"mode": "whitelist"}}, {**copy.deepcopy(_Controller.workspace_state), "effective": {"shared_workspace": SHARED}}):
        with pytest.raises(wf.WorkspaceAnswerError):
            wf.parse_state(bad)


@pytest.mark.basic
def test_controller_reads_and_writes_me_and_runs_send_no_folder_list() -> None:
    import threading

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
    ctl._cache_lock = threading.RLock()
    ctl._cache_epoch = 0
    ctl._cache_ttl_s = 30.0
    ctl._workspace_policy_cache = None
    ctl._workspace_policy_cache_at = 0.0
    ctl.gateway = _GW()
    out = ctl.workspace_policy()
    assert out["error"] == "" and out["state"]["effective"]["shared_workspace"] == SHARED
    ctl._workspace_policy_cache = None
    ctl.put_workspace_folders({"folders": [{"path": AR, "mode": "deny"}]})
    assert calls == [("GET", "me"), ("PUT", "me", {"folders": [{"path": AR, "mode": "deny"}]})]
    scope = AssistantPreferences(workspace_root="/srv/gw/workspaces/x").run_scope()
    assert "workspace_access_mode" not in scope and "workspace_allowed_paths" not in scope


@pytest.mark.basic
def test_wording_is_the_kit_table_and_says_workspaces() -> None:
    """X3: any drift from ui-kit WORKSPACE_CHOOSER_TEXT is a failure (the cross-repo
    diff runs in the round-9 gate: untracked/round4/r9/w3/check_wording.py)."""
    assert T["postureAllowedOnly"] == "Deny everything, allow listed workspaces"
    assert T["postureAnyExceptDenied"] == "Allow everything, refuse listed workspaces"
    assert T["allowedTitle"] == "Allowed workspaces" and T["deniedTitle"] == "Refused workspaces"
    assert T["accessRead"] == "Read-only" and T["accessReadWrite"] == "Read & write" and T["accessDenied"] == "Refused"
    assert not any("folder" in v.lower() for v in T.values())
    page_src = Path(wf.__file__).with_name("pages.py").read_text(encoding="utf-8")
    ws = page_src[page_src.index("class WorkspacePage"):page_src.index("def _html_escape")]
    visible = [s for s in __import__("re").findall(r'"([^"\n{]*)"', ws) if " " in s]
    assert not [s for s in visible if "folder" in s.lower()], [s for s in visible if "folder" in s.lower()]
