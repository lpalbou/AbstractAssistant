"""core.tool_presenter: headline promotion, secrets, flattening, batch tier,
and parity with the summary helpers app.py used to keep private."""

from __future__ import annotations

import json

import pytest

from abstractassistant.core.tool_presenter import (
    SECRET_MASK,
    ToolCallSummary,
    batch_tier,
    clip_lines,
    collapse_home,
    mask_secrets,
    present_call,
    tool_call_arguments,
    tool_call_reason,
    tool_call_summary,
    tool_call_value_summary,
    tool_calls_text,
    toolset_glyph,
)


EXECUTE = {
    "name": "execute_command",
    "toolset": "system",
    "available": True,
    "approval_default": "ask",
    "risk_tier": "destroy",
    "risk_rank": 4,
    "mutating": True,
    "destructive_capable": True,
    "parameters": {
        "command": {"type": "string", "description": "Shell command to run"},
        "timeout": {"type": "integer", "default": 300, "description": "Seconds before the command is killed"},
    },
}
READ_FILE = {"name": "read_file", "toolset": "files", "available": True, "approval_default": "auto", "risk_tier": "observe", "risk_rank": 1}
WRITE_FILE = {"name": "write_file", "toolset": "files", "available": True, "approval_default": "ask", "risk_tier": "act", "risk_rank": 2, "mutating": True}
FETCH_URL = {"name": "fetch_url", "toolset": "web", "available": True, "approval_default": "ask", "risk_tier": "act", "risk_rank": 2, "remote_write_capable": True}
CAMERA_OPEN = {"name": "camera_open", "toolset": "camera", "available": True, "risk_tier": "outreach", "risk_rank": 3, "mutating": True, "remote_write_capable": True, "captures_environment": True}
SEND_EMAIL = {"name": "send_email", "toolset": "comms.email", "available": False, "approval_default": "ask", "risk_tier": "outreach", "risk_rank": 3, "comms_send": True, "remote_write_capable": True}


# --------------------------------------------------------------------------- #
# Headline promotion
# --------------------------------------------------------------------------- #


@pytest.mark.basic
def test_command_is_promoted_with_shell_prompt_and_rest_stays_secondary() -> None:
    p = present_call(
        {"name": "execute_command", "arguments": {"command": "rm -rf build && make", "timeout": 300, "capture_output": True}},
        EXECUTE,
    )
    assert p.headline == "$ rm -rf build && make"
    assert p.headline_kind == "command"
    assert p.headline_key == "command"
    keys = [key for key, _value, _tip in p.params]
    assert "command" not in keys
    assert ("timeout", "300", "Seconds before the command is killed") in p.params
    assert ("capture_output", "true", "") in p.params


@pytest.mark.basic
def test_cmd_alias_is_promoted_for_command_tools() -> None:
    p = present_call({"name": "run_command", "arguments": {"cmd": "npm test"}})
    assert p.headline == "$ npm test"
    assert p.headline_kind == "command"


@pytest.mark.basic
def test_path_is_promoted_with_home_collapsed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", "/Users/tester")
    p = present_call({"name": "read_file", "arguments": {"file_path": "/Users/tester/proj/a.py", "start_line": 1}}, READ_FILE)
    assert p.headline == "~/proj/a.py"
    assert p.headline_kind == "path"
    assert p.headline_key == "file_path"
    assert ("start_line", "1", "") in p.params
    # A path under someone else's home is not touched.
    assert collapse_home("/Users/other/proj/a.py") == "/Users/other/proj/a.py"
    assert collapse_home("/Users/tester") == "~"


@pytest.mark.basic
def test_url_is_promoted_as_is() -> None:
    p = present_call({"name": "fetch_url", "arguments": {"url": "https://example.com/x?y=1", "max_chars": 4000}}, FETCH_URL)
    assert p.headline == "https://example.com/x?y=1"
    assert p.headline_kind == "url"
    assert ("max_chars", "4000", "") in p.params


@pytest.mark.basic
def test_query_is_promoted_quoted_for_search_tools() -> None:
    p = present_call({"name": "web_search", "arguments": {"query": "Genentech roles", "num_results": 5}})
    assert p.headline == "“Genentech roles”"
    assert p.headline_kind == "query"
    files = present_call({"name": "search_files", "arguments": {"directory_path": ".", "pattern": "TODO"}})
    assert files.headline == "“TODO”"
    assert files.headline_key == "pattern"
    assert ("directory_path", ".", "") in files.params
    listing = present_call({"name": "list_files", "arguments": {"directory_path": "docs", "pattern": "*.md"}})
    assert listing.headline_kind == "path"
    assert listing.headline == "docs"


@pytest.mark.basic
def test_no_headline_when_nothing_promotable() -> None:
    p = present_call({"name": "camera_status", "arguments": {"verbose": True}})
    assert p.headline == "" and p.headline_kind == "" and p.headline_key == ""
    assert p.params == [("verbose", "true", "")]


# --------------------------------------------------------------------------- #
# Secrets
# --------------------------------------------------------------------------- #


@pytest.mark.basic
def test_mask_secrets_deep_copies_and_masks_by_key() -> None:
    payload = {
        "url": "https://api",
        "headers": {"Authorization": "Bearer abc", "Accept": "json"},
        "API-Key": "k1",
        "nested": [{"password": "p", "keep": 1}],
        "passwd": "x",
        "cookie": "c=1",
        "token_id": "t",
    }
    masked = mask_secrets(payload)
    assert masked["headers"]["Authorization"] == SECRET_MASK
    assert masked["headers"]["Accept"] == "json"
    assert masked["API-Key"] == SECRET_MASK
    assert masked["nested"][0]["password"] == SECRET_MASK
    assert masked["nested"][0]["keep"] == 1
    assert masked["passwd"] == SECRET_MASK
    assert masked["cookie"] == SECRET_MASK
    assert masked["token_id"] == SECRET_MASK
    # Original untouched.
    assert payload["headers"]["Authorization"] == "Bearer abc"


@pytest.mark.basic
def test_present_call_masks_secrets_in_params_tooltips_and_raw_json() -> None:
    long_secret = "s" * 200
    p = present_call(
        {
            "name": "fetch_url",
            "arguments": {"url": "https://api", "headers": {"Authorization": "Bearer abc"}, "api_key": long_secret},
        },
        FETCH_URL,
    )
    assert p.secrets_masked is True
    assert ("headers.Authorization", SECRET_MASK, "") in p.params
    assert ("api_key", SECRET_MASK, "") in p.params
    flat = json.dumps(p.params)
    assert "Bearer abc" not in flat and long_secret not in flat
    assert "Bearer abc" not in p.raw_json and long_secret not in p.raw_json
    assert SECRET_MASK in p.raw_json
    assert json.loads(p.raw_json)["name"] == "fetch_url"

    clean = present_call({"name": "read_file", "arguments": {"file_path": "a.py"}}, READ_FILE)
    assert clean.secrets_masked is False


# --------------------------------------------------------------------------- #
# Flatten / lists / scalars / content
# --------------------------------------------------------------------------- #


@pytest.mark.basic
def test_objects_flatten_one_level_and_deeper_is_summarised() -> None:
    p = present_call({"name": "camera_open", "arguments": {"options": {"fps": 30, "deep": {"a": 1, "b": 2}, "tags": ["x"]}, "empty": {}}})
    assert ("options.fps", "30", "") in p.params
    assert ("options.deep", "{…} 2 keys", "") in p.params
    assert ("options.tags", "[1 item] x", "") in p.params
    assert ("empty", "{} empty", "") in p.params


@pytest.mark.basic
def test_lists_show_count_and_up_to_three_scalars() -> None:
    four = present_call({"name": "skim_folders", "arguments": {"paths": ["a", "b", "c", "d"]}})
    assert four.params == [("paths", "[4 items] a, b, c, …", "")]
    one = present_call({"name": "skim_folders", "arguments": {"paths": ["docs"]}})
    assert one.params == [("paths", "[1 item] docs", "")]
    mixed = present_call({"name": "x", "arguments": {"items": [{"k": 1}, [1], None]}})
    assert mixed.params == [("items", "[3 items] {…}, […], none", "")]
    empty = present_call({"name": "x", "arguments": {"items": []}})
    assert empty.params == [("items", "[0 items]", "")]


@pytest.mark.basic
def test_scalars_render_booleans_none_and_cut_long_strings_with_tooltip() -> None:
    long_text = "word " * 40  # 200 chars, no newline, < 240 → inline but cut
    long_text = long_text.strip()
    p = present_call({"name": "x", "arguments": {"flag": False, "nothing": None, "n": 2.5, "s": long_text}})
    assert ("flag", "false", "") in p.params
    assert ("nothing", "none", "") in p.params
    assert ("n", "2.5", "") in p.params
    key, display, tooltip = [row for row in p.params if row[0] == "s"][0]
    assert display.endswith("…") and len(display) == 120
    assert tooltip == long_text
    assert p.content_blocks == []


@pytest.mark.basic
def test_content_keys_and_multiline_strings_become_preview_blocks() -> None:
    body = "\n".join(f"line {i}" for i in range(1, 121))
    p = present_call({"name": "write_file", "arguments": {"file_path": "/tmp/x.txt", "content": body}}, WRITE_FILE)
    assert [key for key, _v, _t in p.params] == []
    assert len(p.content_blocks) == 1
    key, summary, preview = p.content_blocks[0]
    assert key == "content"
    assert summary == f"{len(body):,} chars · 120 lines"
    lines = preview.splitlines()
    assert lines[:40] == [f"line {i}" for i in range(1, 41)]
    assert lines[40] == "… (+80 more lines)"

    # Any other key with a newline or > 240 chars is demoted too.
    multi = present_call({"name": "x", "arguments": {"note": "a\nb"}})
    assert multi.content_blocks[0][:2] == ("note", "3 chars · 2 lines")
    huge = present_call({"name": "x", "arguments": {"blob": "z" * 300}})
    assert huge.content_blocks[0][:2] == ("blob", "300 chars · 1 line")
    assert huge.params == []


@pytest.mark.basic
def test_non_dict_arguments_are_one_honest_row() -> None:
    p = present_call({"name": "x", "arguments": "just text"})
    assert p.params == [("arguments", "just text", "")]
    assert p.headline == ""
    assert json.loads(p.raw_json)["arguments"] == "just text"
    multi = present_call({"name": "x", "arguments": "a\nb\nc"})
    assert multi.params == [] and multi.content_blocks[0][0] == "arguments"


@pytest.mark.basic
def test_schema_description_lands_in_tooltip() -> None:
    p = present_call({"name": "execute_command", "arguments": {"command": "ls", "timeout": 5}}, EXECUTE)
    assert ("timeout", "5", "Seconds before the command is killed") in p.params


@pytest.mark.basic
def test_clip_lines_reports_hidden_count() -> None:
    text = "\n".join(str(i) for i in range(12))
    clipped = clip_lines(text, 8)
    assert clipped.splitlines()[:8] == [str(i) for i in range(8)]
    assert clipped.splitlines()[-1] == "… (+4 lines)"
    assert clip_lines("one\ntwo", 8) == "one\ntwo"


# --------------------------------------------------------------------------- #
# Risk facts, availability, results
# --------------------------------------------------------------------------- #


@pytest.mark.basic
def test_risk_flags_come_from_gateway_facts_only() -> None:
    execute = present_call({"name": "execute_command", "arguments": {"command": "ls"}}, EXECUTE)
    assert execute.risk["label"] == "Destructive" and execute.risk["tone"] == "destroy" and execute.risk["rank"] == 4
    assert ("can delete", "destroy") in execute.flags
    assert ("writes", "act") not in execute.flags  # implied by "can delete"
    camera = present_call({"name": "camera_open", "arguments": {}}, CAMERA_OPEN)
    assert camera.flags == [("writes", "act"), ("sends data", "outreach"), ("camera/mic", "outreach")]
    email = present_call({"name": "send_email", "arguments": {"to": "a@b"}}, SEND_EMAIL)
    assert ("messages people", "outreach") in email.flags
    assert email.available is False
    plain = present_call({"name": "read_file", "arguments": {"file_path": "a"}}, READ_FILE)
    assert plain.flags == [] and plain.available is True and plain.unknown is False
    assert plain.approval_default == "auto"


@pytest.mark.basic
def test_unknown_tool_fails_closed() -> None:
    p = present_call({"name": "brand_new_tool", "arguments": {"x": 1}})
    assert p.unknown is True
    assert p.available is True
    assert p.risk["label"] == "Unknown risk"
    assert p.risk["tone"] == "unknown"
    assert p.risk["rank"] == 0
    assert p.flags == []


@pytest.mark.basic
def test_result_fields_success_error_and_bounded_output() -> None:
    p = present_call({"name": "edit_file", "arguments": {"file_path": "b.py"}, "success": False, "error": "pattern not found", "output": "x" * 5000})
    assert p.success is False
    assert p.error == "pattern not found"
    assert len(p.output_preview) == 1200 and p.output_preview.endswith("…")
    ok = present_call({"name": "x", "arguments": {}, "success": True, "result": {"rows": 3}})
    assert ok.success is True and ok.error == ""
    assert json.loads(ok.output_preview) == {"rows": 3}
    none = present_call({"name": "x", "arguments": {}})
    assert none.success is None and none.output_preview == ""


@pytest.mark.basic
def test_toolset_glyph_prefers_gateway_toolset_then_name_family() -> None:
    assert toolset_glyph("execute_command", EXECUTE) == "terminal"
    assert toolset_glyph("fetch_url", FETCH_URL) == "globe"
    assert toolset_glyph("read_file", READ_FILE) == "folder"
    assert toolset_glyph("send_email", SEND_EMAIL) == "mail"
    assert toolset_glyph("camera_open", CAMERA_OPEN) == "camera"
    assert toolset_glyph("shell_exec", None) == "terminal"
    assert toolset_glyph("web_search", None) == "globe"
    assert toolset_glyph("write_file", None) == "folder"
    assert toolset_glyph("camera_capture_photo", None) == "camera"
    assert toolset_glyph("send_whatsapp_message", None) == "mail"
    assert toolset_glyph("mystery", None) == "spark"


# --------------------------------------------------------------------------- #
# Batch tier
# --------------------------------------------------------------------------- #


@pytest.mark.basic
def test_batch_tier_is_the_loudest_known_tier() -> None:
    risks = {"read_file": READ_FILE, "write_file": WRITE_FILE, "execute_command": EXECUTE}
    calls = [{"name": "read_file", "arguments": {}}, {"name": "write_file", "arguments": {}}]
    tier = batch_tier(calls, risks)
    assert tier == {"label": "Makes changes", "tone": "act", "rank": 2, "unknown": False}
    loud = batch_tier(calls + [{"name": "execute_command", "arguments": {}}], risks)
    assert loud["label"] == "Destructive" and loud["rank"] == 4 and loud["unknown"] is False


@pytest.mark.basic
def test_batch_tier_unknown_tool_fails_closed_but_keeps_a_louder_known_label() -> None:
    risks = {"read_file": READ_FILE, "execute_command": EXECUTE}
    only_unknown = batch_tier([{"name": "mystery", "arguments": {}}], risks)
    assert only_unknown == {"label": "Unknown risk", "tone": "unknown", "rank": 0, "unknown": True}
    with_observe = batch_tier([{"name": "mystery", "arguments": {}}, {"name": "read_file", "arguments": {}}], risks)
    assert with_observe["label"] == "Unknown risk" and with_observe["unknown"] is True
    # Quieter known tiers (observe / act / outreach) never dress an unlisted tool up as safe.
    with_act = batch_tier([{"name": "mystery", "arguments": {}}, {"name": "write_file", "arguments": {}}], {**risks, "write_file": WRITE_FILE})
    assert with_act["label"] == "Unknown risk" and with_act["unknown"] is True
    with_destroy = batch_tier([{"name": "mystery", "arguments": {}}, {"name": "execute_command", "arguments": {}}], risks)
    assert with_destroy["label"] == "Destructive" and with_destroy["tone"] == "destroy"
    assert with_destroy["rank"] == 4 and with_destroy["unknown"] is True
    assert batch_tier([], risks)["unknown"] is True
    assert batch_tier([{"name": "read_file"}], None)["unknown"] is True


# --------------------------------------------------------------------------- #
# Summary helpers: parity with the palette tests app.py relies on
# --------------------------------------------------------------------------- #


@pytest.mark.basic
def test_tool_call_summary_humanizes_large_write_file_payload() -> None:
    content = "<!DOCTYPE html>\n<html><body>Hello</body></html>" * 40
    summary = tool_call_summary({"name": "write_file", "arguments": {"filepath": "/tmp/fantasy-comic.html", "content": content}})
    assert isinstance(summary, ToolCallSummary)
    assert summary.name == "write_file"
    assert summary.reason == "Create or replace `/tmp/fantasy-comic.html`."
    assert summary.parameters == [
        ("filepath", "/tmp/fantasy-comic.html"),
        ("content", f"HTML content, {len(content):,} chars"),
    ]
    assert summary.raw_text.startswith("write_file\n{")
    assert '"filepath": "/tmp/fantasy-comic.html"' in summary.raw_text


@pytest.mark.basic
def test_tool_call_summary_parses_json_argument_text() -> None:
    summary = tool_call_summary({"name": "execute_command", "arguments": '{"cmd":"npm test","timeout":120}'})
    assert summary.name == "execute_command"
    assert summary.reason == "Run `npm test`."
    assert ("cmd", "npm test") in summary.parameters
    assert ("timeout", "120") in summary.parameters


@pytest.mark.basic
def test_summary_helper_edge_cases_match_the_legacy_strings() -> None:
    assert tool_calls_text([]) == "No tool details were provided by the workflow."
    assert tool_calls_text("nope") == "No tool details were provided by the workflow."
    assert tool_calls_text([{"name": "x", "arguments": {}}]) == "x"
    assert tool_calls_text([{"name": "x", "arguments": "raw"}]) == "x\nraw"
    assert tool_call_arguments('{"a": 1}') == {"a": 1}
    assert tool_call_arguments("[1]") == {}
    assert tool_call_arguments("{bad") == {}
    assert tool_call_value_summary("x", None) == "none"
    assert tool_call_value_summary("x", True) == "true"
    assert tool_call_value_summary("x", {"a": 1}) == "object with 1 entry"
    assert tool_call_value_summary("x", [1, 2]) == "list with 2 items"
    assert tool_call_value_summary("x", "   ") == "empty"
    assert tool_call_value_summary("body", "hi") == "text content, 2 chars"
    assert tool_call_value_summary("x", "y" * 100) == "y" * 93 + "..."
    assert tool_call_reason("web_search", {"query": "q"}) == "Search the web for `q`."
    assert tool_call_reason("apply_patch", {}) == "Apply a patch to one or more local files."
    assert tool_call_reason("list_things", {}) == "Inspect available resources."
    assert tool_call_reason("", {}) == "Call `<unknown>` with the parameters below."
    unstructured = tool_call_summary("garbage")
    assert unstructured.name == "<unknown>" and unstructured.raw_text == "garbage"
    scalar = tool_call_summary({"name": "x", "arguments": "plain"})
    assert scalar.parameters == [("arguments", "plain")]
