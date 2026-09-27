"""The session list is the gateway's root runs folded by `session_id`.

Fixtures: `fixtures/gateway_runs/` holds the shared SHAPE of the gateway's
answers — `runs_page.json` is a `GET /api/gateway/runs?limit=N&root_only=true
&include_ledger_len=false` page (envelope `items/count/offset/has_more`,
`abstractgateway/routes/gateway.py` `list_runs`), `input_data.json` and
`history_bundles.json` the per-run answers for the same runs. AbstractCode
keeps its fold cases inline (`tui/src/runner.rs` tests of `fold_session_rows`,
`web/src/workspace/catalog.test.ts`) and abstractuic vendors no session-row
fixture, so the cases here mirror AbstractCode's rather than copy a file.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from abstractassistant.core.gateway_sessions import (
    SESSION_LIST_LIMIT,
    GatewaySession,
    fold_session_rows,
    prompt_from_input_data,
)
from abstractassistant.gateway.client import GatewayClient, GatewayClientConfig

FIXTURES = Path(__file__).parent / "fixtures" / "gateway_runs"


def _page() -> dict:
    return json.loads((FIXTURES / "runs_page.json").read_text(encoding="utf-8"))


def _by_id(rows):
    return {row.session_id: row for row in rows}


@pytest.mark.basic
def test_the_session_list_query_is_pinned() -> None:
    """The gateway 400s an unknown query parameter, so a renamed or added one
    empties the list instead of degrading it. Same query as AbstractCode
    (`tui/src/gateway/mod.rs` session_listing_path)."""
    assert GatewayClient.session_listing_path(SESSION_LIST_LIMIT) == (
        "/api/gateway/runs?limit=5000&root_only=true&include_ledger_len=false"
    )
    # The same N as AbstractCode's session board (ui/modals.rs SESSION_LIST_LIMIT).
    assert SESSION_LIST_LIMIT == 5000
    # With a gateway that advertises the session_kind filter (contract F).
    assert GatewayClient.session_listing_path(SESSION_LIST_LIMIT, session_kind_filter=True) == (
        "/api/gateway/runs?limit=5000&root_only=true&include_ledger_len=false&session_kind=chat,discussion"
    )


@pytest.mark.basic
def test_list_session_runs_sends_exactly_the_pinned_url(monkeypatch) -> None:
    import abstractassistant.gateway.client as client_module

    seen = {}

    def _fake_request_json(**kwargs):
        seen.update(kwargs)
        return {"items": [], "has_more": False}

    monkeypatch.setattr(client_module, "_request_json", _fake_request_json)
    client = GatewayClient(GatewayClientConfig(base_url="http://127.0.0.1:9/", auth_token="t"))
    client.list_session_runs(limit=SESSION_LIST_LIMIT, timeout_s=3.0)
    assert seen["method"] == "GET"
    assert seen["url"] == "http://127.0.0.1:9/api/gateway/runs?limit=5000&root_only=true&include_ledger_len=false"
    assert seen["timeout_s"] == 3.0


@pytest.mark.basic
def test_fold_one_row_per_session_newest_first_by_updated_at() -> None:
    rows, truncated = fold_session_rows(_page())
    assert truncated is False
    # Newest first by `updated_at` (the gateway's paging field): a session
    # created in August but touched later sorts first.
    assert [r.session_id for r in rows] == ["sess_hot", "sess_alpha", "sess_cold", "sess_beta", "sess_unknown"]
    # No row for a run without a session, or without a run id.
    assert "sess_no_run_id" not in _by_id(rows)


@pytest.mark.basic
def test_fold_turns_are_root_runs_and_first_last_runs_come_from_created_at() -> None:
    rows = _by_id(fold_session_rows(_page())[0])
    alpha = rows["sess_alpha"]
    # The child agent run of run_alpha_3 is not a turn.
    assert alpha.turns == 3
    assert alpha.first_run_id == "run_alpha_1"   # its prompt names the session
    assert alpha.latest_run_id == "run_alpha_3"  # its bundle carries every turn
    assert alpha.updated_at == "2026-09-26T08:05:00+00:00"
    assert alpha.created_at == "2026-09-20T09:00:00+00:00"
    assert rows["sess_beta"].turns == 2
    assert rows["sess_beta"].first_run_id == "run_beta_1"
    assert rows["sess_beta"].latest_run_id == "run_beta_2"


@pytest.mark.basic
def test_fold_state_is_the_liveliest_run_and_unknown_is_never_done() -> None:
    rows = _by_id(fold_session_rows(_page())[0])
    # A waiting run outranks a newer completed one: recency is not liveliness.
    assert rows["sess_alpha"].state == "waiting"
    # Running (older) outranks failed (newer).
    assert rows["sess_beta"].state == "running"
    assert rows["sess_cold"].state == "done"
    # An unreported status is not a verdict; with no updated_at the row
    # still orders by created_at.
    assert rows["sess_unknown"].state == "unknown"
    assert rows["sess_unknown"].updated_at == "2026-09-23T09:00:00+00:00"


@pytest.mark.basic
def test_fold_unknown_status_loses_to_any_real_one() -> None:
    rows, _ = fold_session_rows(
        {
            "items": [
                {"run_id": "a", "session_id": "S", "status": "queued", "updated_at": "2026-08-28T10:00:00Z"},
                {"run_id": "b", "session_id": "S", "status": "waiting", "updated_at": "2026-08-28T09:00:00Z"},
            ],
            "has_more": False,
        }
    )
    assert rows[0].state == "waiting"


@pytest.mark.basic
def test_fold_a_page_without_an_explicit_has_more_false_is_truncated() -> None:
    page = _page()
    page["has_more"] = True
    assert fold_session_rows(page)[1] is True
    page.pop("has_more")
    assert fold_session_rows(page)[1] is True, "absent has_more cannot prove completeness"


@pytest.mark.basic
def test_rows_round_trip_through_the_cache_format() -> None:
    for row in fold_session_rows(_page())[0]:
        assert GatewaySession.from_dict(row.to_dict()) == row


@pytest.mark.basic
def test_opening_prompt_reads_input_data_prompt_or_a_bare_prompt() -> None:
    answers = json.loads((FIXTURES / "input_data.json").read_text(encoding="utf-8"))
    assert prompt_from_input_data(answers["run_alpha_1"]) == "Plan the Q3 launch checklist"
    assert prompt_from_input_data(answers["run_hot_1"]) == "Refactor the router module"
    assert prompt_from_input_data(answers["run_unknown_1"]) == ""
    assert prompt_from_input_data({"input_data": {"context": {"task": "from the task"}}}) == "from the task"
