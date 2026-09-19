"""Links in an answer: found, rendered as links, and safe to click (2026-09-17).

Operator report: an answer ended "The video is saved at: `/Users/…/clip.mp4`" and the
path was a dead grey code span. Two halves, tested separately:

DETECTION — a local path or URL becomes a real link, including when it is wrapped in
backticks (how models habitually write paths), but never inside a fenced block, never
inside an existing link, and never for prose that merely contains a slash.

POLICY — the text is written by a MODEL and may echo a web page, so a link is untrusted
input. `QTextBrowser.setOpenExternalLinks(True)` handed every href to the OS, and for
`file:` links "open" can mean RUN: an `.app`, a `.command`, a share on another host.
Clicks now go through `activate_message_link`: inert kinds open, everything else is
revealed in Finder, other hosts are refused, and symlinks are judged by their target.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List

import pytest

from abstractassistant.core import link_targets as lt
from abstractassistant.utils.markdown_renderer import render_markdown

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _links(markdown: str) -> List[tuple[str, str]]:
    body = render_markdown(markdown).split('<div class="markdown-content">', 1)[1]
    return [(href, re.sub(r"<[^>]+>", "", label)) for href, label in re.findall(r'<a [^>]*href="([^"]+)"[^>]*>(.*?)</a>', body)]


# --------------------------------------------------------------------------- detection

CLIP = "/Users/albou/Pictures/macbook_pro_camera/capture_20260917_213045_0001.mp4"


def test_the_reported_answer_gets_a_clickable_path() -> None:
    links = _links(f"The video is saved at:\n`{CLIP}`")
    assert links == [(f"file://{CLIP}", CLIP)]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Saved to /tmp/report.pdf.", ["/tmp/report.pdf"]),                      # sentence period
        ("(see /Users/a/notes/todo.md)", ["/Users/a/notes/todo.md"]),           # closing bracket
        ("in ~/Documents/plan.md, then", ["~/Documents/plan.md"]),              # home-relative
        ("/Users/a/x.png and /Users/a/y.png", ["/Users/a/x.png", "/Users/a/y.png"]),
        ("either/or, 1/2 of it, on 2026/09/17", []),                            # prose slashes
        ("the regex /foo/g and a // comment", []),
        ("just / or /usr alone", []),                                           # a root is a mention
        ("C:\\Users\\a\\x.txt", []),
        ("https://host.example/Users/a/x.png", []),                             # belongs to the URL
    ],
)
def test_paths_in_running_prose(text: str, expected: List[str]) -> None:
    assert [span.path for span in lt.find_path_spans(text)] == expected


def test_a_url_keeps_its_path_and_a_named_link_is_left_alone() -> None:
    links = _links("Docs: https://host.example/Users/guide. And [here](https://x.example/Users/z).")
    assert links == [
        ("https://host.example/Users/guide", "https://host.example/Users/guide"),
        ("https://x.example/Users/z", "here"),
    ]


def test_inline_code_links_only_when_the_whole_span_is_the_target() -> None:
    assert _links("Run `ls /Users/albou/docs` first") == []          # a command, not a path
    assert _links("Open `https://abstractframework.ai`") == [("https://abstractframework.ai", "https://abstractframework.ai")]
    assert _links("`/usr/bin/env python`") == []                      # spaced, and does not exist


def test_a_spaced_path_in_backticks_links_only_if_it_exists(tmp_path: Path) -> None:
    real = tmp_path / "My Notes" / "plan final.md"
    real.parent.mkdir()
    real.write_text("x")
    assert lt.is_safe_to_stat(str(real)), "pytest tmp dirs must count as local for this test to mean anything"
    assert [label for _href, label in _links(f"`{real}`")] == [str(real)]
    assert _links(f"`{real}.missing and more`") == []


def test_fenced_code_is_never_rewritten() -> None:
    markdown = "```bash\ncat /Users/albou/secret.txt\ncurl https://example.com/x\n```"
    assert _links(markdown) == []


def test_the_label_is_the_path_as_written_so_a_selection_copies_a_real_path() -> None:
    (href, label), = _links("see ~/Documents/plan.md")
    assert label == "~/Documents/plan.md"
    assert href == "file://" + str(Path.home() / "Documents/plan.md")


def test_hrefs_are_percent_encoded_and_round_trip() -> None:
    path = "/Users/albou/Mes Vidéos/été #1.mp4"
    href = lt.file_href(path)
    assert " " not in href and "#" not in href
    assert lt.local_path_from_href(href) == path


# --------------------------------------------------------------------------- policy


@pytest.mark.parametrize("name", ["clip.mp4", "shot.PNG", "memo.pdf", "notes.md", "data.csv", "song.m4a"])
def test_inert_kinds_open(name: str) -> None:
    assert lt.click_action(f"/Users/a/{name}") == "open"


@pytest.mark.parametrize(
    "name",
    [
        "Calculator.app", "install.command", "run.sh", "setup.pkg", "disk.dmg", "flow.workflow",
        "script.scpt", "link.webloc", "share.inetloc", "page.html", "drawing.svg", "tool", "archive.zip",
        "Terminal.terminal", "evil.jar", "macro.docm",
    ],
)
def test_everything_else_is_only_revealed(name: str) -> None:
    assert lt.click_action(f"/Users/a/{name}") == "reveal"


@pytest.mark.parametrize(
    "href",
    ["file://evil.example/share/x.mp4", "file://10.0.0.5/c$/x.pdf", "smb://evil.example/share", "https://ok.example"],
)
def test_only_this_machine_is_a_local_path(href: str) -> None:
    assert lt.local_path_from_href(href) is None


def test_dot_dot_is_collapsed_before_anything_judges_the_path() -> None:
    assert lt.local_path_from_href("file:///Users/a/Movies/../../../Applications/Calculator.app") == "/Applications/Calculator.app"
    assert lt.click_action("/Users/a/Movies/../../../Applications/Calculator.app") == "reveal"


def test_render_time_never_touches_a_path_that_could_be_a_network_mount() -> None:
    for risky in ("/Volumes/Share/x.mp4", "/net/host/x.mp4", "/home/other/x.mp4", "/mnt/nas/x.mp4", "/Network/x.mp4"):
        assert lt.is_safe_to_stat(risky) is False
        assert lt.exists_locally(risky) is False
    assert lt.is_safe_to_stat(str(Path.home() / "x.mp4")) is True


def test_only_existing_inert_files_earn_a_chip(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"0")
    script = tmp_path / "run.command"
    script.write_text("#!/bin/sh")
    folder = tmp_path / "album.mp4"  # a directory wearing a media extension
    folder.mkdir()
    text = f"Saved `{clip}` and `{script}`, folder `{folder}`, missing `{tmp_path}/gone.mp4`.\n```\n{clip}\n```"
    assert lt.mentioned_local_files(text) == [os.path.realpath(clip)]


def test_a_media_named_symlink_to_something_else_earns_no_chip(tmp_path: Path) -> None:
    target = tmp_path / "payload.command"
    target.write_text("#!/bin/sh")
    disguised = tmp_path / "holiday.mp4"
    disguised.symlink_to(target)
    assert lt.mentioned_local_files(f"`{disguised}`") == []


# --------------------------------------------------------------------------- the click


@pytest.fixture()
def acts(monkeypatch):
    import abstractassistant.app as app

    seen: List[tuple[str, str]] = []
    monkeypatch.setattr(app.QDesktopServices, "openUrl", lambda url: seen.append(("open", url.toString())) or True)
    monkeypatch.setattr(app, "_reveal_in_file_manager", lambda path: seen.append(("reveal", path)) or True)
    # Text kinds open through `open -t`: never let a test spawn a real editor.
    monkeypatch.setattr(app.subprocess, "Popen", lambda argv, *a, **k: seen.append(("editor", list(argv)[-1])))
    return app, seen


def test_clicking_a_video_opens_it_and_clicking_an_app_only_reveals_it(acts, tmp_path: Path) -> None:
    app, seen = acts
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"0")
    bundle = tmp_path / "Thing.app"
    bundle.mkdir()
    script = tmp_path / "go.command"
    script.write_text("#!/bin/sh")

    assert app.activate_message_link(lt.file_href(str(clip))) == ""
    assert app.activate_message_link(lt.file_href(str(bundle))) == ""
    assert app.activate_message_link(lt.file_href(str(script))) == ""
    assert [kind for kind, _ in seen] == ["open", "reveal", "reveal"]


def test_a_symlink_is_judged_by_what_it_points_at(acts, tmp_path: Path) -> None:
    app, seen = acts
    bundle = tmp_path / "Thing.app"
    bundle.mkdir()
    disguised = tmp_path / "holiday.mp4"
    disguised.symlink_to(bundle)
    assert app.activate_message_link(lt.file_href(str(disguised))) == ""
    assert seen == [("reveal", os.path.realpath(bundle))]


def test_plain_folders_open_and_force_reveal_wins(acts, tmp_path: Path) -> None:
    app, seen = acts
    folder = tmp_path / "exports"
    folder.mkdir()
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"0")
    app.activate_message_link(lt.file_href(str(folder)))
    app.activate_message_link(lt.file_href(str(clip)), force_reveal=True)
    assert [kind for kind, _ in seen] == ["open", "reveal"]


def test_refusals_say_why_and_touch_nothing(acts, tmp_path: Path) -> None:
    app, seen = acts
    assert "another computer" in app.activate_message_link("file://evil.example/share/x.mp4")
    assert "Not found" in app.activate_message_link(lt.file_href(str(tmp_path / "gone.mp4")))
    assert "not opened" in app.activate_message_link("x-apple-helpbasic://anything")
    assert "not opened" in app.activate_message_link("javascript:alert(1)")
    assert seen == []


def test_action_buttons_share_the_inline_links_policy(acts, tmp_path: Path) -> None:
    app, seen = acts
    script = tmp_path / "go.command"
    script.write_text("#!/bin/sh")
    assert app._open_external_href(lt.file_href(str(script))) is True
    assert seen == [("reveal", os.path.realpath(script))]


def test_the_message_browser_never_lets_qt_open_a_link_by_itself(acts, tmp_path: Path) -> None:
    app, seen = acts
    from PyQt5.QtCore import QUrl
    from PyQt5.QtWidgets import QApplication

    _qapp = QApplication.instance() or QApplication([])
    browser = app.AutoSizingTextBrowser()
    assert browser.openLinks() is False and browser.openExternalLinks() is False

    script = tmp_path / "go.command"
    script.write_text("#!/bin/sh")
    browser.anchorClicked.emit(QUrl(lt.file_href(str(script))))
    assert seen == [("reveal", os.path.realpath(script))]


# --------------------------------------------------------------------------- adversarial round
#
# Found by the adversarial pass on the first implementation (70-case corpus, 54/70):
# the principle is LONGEST EXISTING PATH, ELSE THE CAUTIOUS TOKEN, ELSE NOTHING — a
# confident link to a truncated stump is worse than no link.


@pytest.fixture()
def tree(tmp_path: Path) -> Path:
    (tmp_path / "My Documents").mkdir()
    (tmp_path / "My Documents" / "report final (v2).pdf").write_bytes(b"0")
    (tmp_path / "weird,name.txt").write_text("x")
    (tmp_path / "it's here.txt").write_text("x")
    (tmp_path / "文档").mkdir()
    (tmp_path / "文档" / "报告.pdf").write_bytes(b"0")
    for name in ("a.txt", "b.txt", "notes.md", "clip.mp4"):
        (tmp_path / name).write_bytes(b"0")
    assert lt.is_safe_to_stat(str(tmp_path))
    return tmp_path


def _paths(text: str) -> List[str]:
    return [span.path for span in lt.find_path_spans(text)]


def test_a_spaced_path_in_prose_links_whole_or_not_at_all(tree: Path) -> None:
    whole = f"{tree}/My Documents/report final (v2).pdf"
    assert _paths(f"I wrote {whole} for you.") == [whole]
    # The longer name is gone: "{tree}/My" is a STUMP of "My Documents", not a target.
    assert _paths(f"I wrote {tree}/My Documents/missing file.pdf for you.") in ([], [f"{tree}/My Documents"])
    assert f"{tree}/My" not in _paths(f"I wrote {tree}/My Documents/missing file.pdf for you.")


def test_quotes_and_escaped_spaces_delimit_explicitly(tree: Path) -> None:
    whole = f"{tree}/My Documents/report final (v2).pdf"
    assert _paths(f'Saved as "{whole}".') == [whole]
    assert _paths(f"cd {tree}/My\\ Documents") == [f"{tree}/My Documents"]


def test_names_with_a_comma_or_apostrophe_win_when_they_exist(tree: Path) -> None:
    assert _paths(f"see {tree}/weird,name.txt, ok") == [f"{tree}/weird,name.txt"]
    assert _paths(f"see {tree}/it's here.txt now") == [f"{tree}/it's here.txt"]


def test_separators_that_are_not_spaces(tree: Path) -> None:
    a, b = f"{tree}/a.txt", f"{tree}/b.txt"
    assert _paths(f"{a},{b}") == [a, b]
    assert _paths(f"{a}—done") == [a]
    assert _paths(f"{a}→{b}") == [a, b]
    assert _paths(f"报告在{tree}/文档/报告.pdf。") == [f"{tree}/文档/报告.pdf"]
    assert _paths(f"Is it {a}?") == [a]


def test_compiler_style_line_suffix_links_the_file_not_the_suffix(tree: Path) -> None:
    text = f"Error at {tree}/notes.md:42:7: unexpected token"
    (span,) = lt.find_path_spans(text)
    assert span.path == f"{tree}/notes.md"
    assert text[span.start : span.end] == f"{tree}/notes.md"
    assert lt.path_from_code_span(f"{tree}/notes.md:42") == f"{tree}/notes.md"


@pytest.mark.parametrize(
    "text",
    [
        "PATH=/usr/local/bin:/usr/bin:/bin",          # one link over a list is wrong
        "scp build@ci:/Users/ci/out/app.zip .",       # another machine
        "C:/Users/albou/file.txt",                    # Windows
        "${HOME}/tmp/out.txt and $TMPDIR/tmp/run.json",  # template tails
        "Delete /Users/a/build/*.txt",                # glob
        "rm /tmp/cache/file?.bin",
    ],
)
def test_things_that_look_like_paths_and_are_not(text: str) -> None:
    assert _paths(text) == []


def test_markdown_eating_glob_stars_does_not_leave_a_linked_stump(tree: Path) -> None:
    assert _links(f"Delete {tree}/*.txt and /tmp/build-*/out") == []
    assert [label for _h, label in _links(f"**{tree}/a.txt** is bold")] == [f"{tree}/a.txt"]


def test_bare_file_urls_link_only_for_this_machine(tree: Path) -> None:
    assert [span.path for span in lt.find_file_url_spans(f"Open file://{tree}/clip.mp4 to view.")] == [f"{tree}/clip.mp4"]
    assert lt.find_file_url_spans("Open file://evil.example/share/clip.mp4 now") == []


def test_names_that_display_as_something_else_are_never_links() -> None:
    assert _paths("/Users/a/invoice\u202efdp.exe") == []   # RLO: shows as "invoiceexe.pdf"
    assert lt.path_from_code_span("/Users/a/x\u2066y.pdf") is None


def test_detection_is_linear_in_hostile_input() -> None:
    import time

    hostile = "/Users/x/y" + ")" * 80_000
    started = time.perf_counter()
    render_markdown(hostile)
    render_markdown("see https://example.com/a" + ")" * 80_000)
    assert time.perf_counter() - started < 1.0, "a quadratic strip loop froze the GUI thread for seconds"


def test_a_path_longer_than_path_max_is_not_linked_as_a_stump() -> None:
    long_path = "/Users/albou/" + "/".join(f"segment_{i:03d}" for i in range(120)) + "/file.txt"
    assert len(long_path) > 1024
    assert _paths(f"see {long_path} ok") == []


def test_source_files_open_in_an_editor_never_their_default_app(acts, tmp_path: Path, monkeypatch) -> None:
    """With python.org's Python Launcher installed, "opening" a .py RUNS it."""
    app, seen = acts
    launched: List[List[str]] = []
    monkeypatch.setattr(app.sys, "platform", "darwin")
    monkeypatch.setattr(app.subprocess, "Popen", lambda argv, *a, **k: launched.append(list(argv)))
    script = tmp_path / "tool.py"
    script.write_text("print('hi')")
    assert app.activate_message_link(lt.file_href(str(script))) == ""
    assert launched == [["/usr/bin/open", "-t", os.path.realpath(script)]]
    assert seen == []


def test_a_scheme_less_markdown_href_is_a_local_path(acts, tmp_path: Path) -> None:
    app, seen = acts
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"0")
    assert app.activate_message_link(str(clip)) == ""
    assert [kind for kind, _ in seen] == ["open"]


def test_the_message_browser_loads_nothing_but_inline_data_images(acts) -> None:
    app, _seen = acts
    from PyQt5.QtCore import QUrl
    from PyQt5.QtGui import QTextDocument
    from PyQt5.QtWidgets import QApplication

    _qapp = QApplication.instance() or QApplication([])
    browser = app.AutoSizingTextBrowser()
    for blocked in ("file:///etc/hosts", "/etc/hosts", "https://example.com/x.png", "smb://host/x.png"):
        assert browser.loadResource(QTextDocument.ImageResource, QUrl(blocked)) is None


def test_the_hover_tooltip_cannot_be_made_to_render_markup() -> None:
    import abstractassistant.app as app

    text = app._tooltip_html(lt.describe_link("file:///Users/a/<img src=x>.pdf").split("\n"))
    assert "<img" not in text and "&lt;img" in text


def test_a_persisted_tool_call_keeps_its_identity() -> None:
    from abstractassistant.gateway.run_stats import compact_tool_call_for_ui

    kept = compact_tool_call_for_ui(
        {"name": "camera_open", "arguments": {}, "call_id": "0", "runtime_call_id": "rtcall_abc_1"}
    )
    assert kept["call_id"] == "0" and kept["call_uid"] == "rtcall_abc_1"


def test_a_fence_holding_only_a_path_is_the_deliverable_not_code(tree: Path) -> None:
    """Seen live in the session this ask came from: the model answered "where is it?"
    with the path alone in a fenced block — the one place a link could never appear."""
    clip = f"{tree}/clip.mp4"
    markdown = f"It's a local file path, not a URL:\n\n```\n{clip}\n```\n\nYou can open it in QuickTime."
    assert [label for _h, label in _links(markdown)] == [clip]
    assert lt.mentioned_local_files(markdown) == [os.path.realpath(clip)]
    # A lone URL in a fence is NOT unfenced: no evidence it is ever the deliverable, and
    # "fenced URLs are not rewritten" is the renderer's long-standing contract.
    assert _links("```\nhttps://example.com/docs\n```") == []


def test_a_fence_holding_anything_else_stays_code(tree: Path) -> None:
    clip = f"{tree}/clip.mp4"
    for body in (f"open {clip}", f"{clip}\n{clip}", f"cat {clip} | wc -l"):
        markdown = f"```bash\n{body}\n```"
        assert _links(markdown) == []
        assert lt.mentioned_local_files(markdown) == []
        assert lt.unfence_lone_targets(markdown) == markdown


def test_a_nul_byte_in_a_file_link_is_refused_not_a_crash(acts) -> None:
    """`%00` unquotes to a real NUL; os.path then raises ValueError, not OSError. That
    escaped the anchorClicked slot and ABORTED the app (SIGABRT) — adversarial find."""
    app, seen = acts
    assert lt.local_path_from_href("file:///tmp/a%00b.mp4") is None
    assert app.activate_message_link("file:///tmp/a%00b.mp4") != ""
    assert seen == []


def test_the_click_slot_never_raises(acts, monkeypatch) -> None:
    app, _seen = acts
    from PyQt5.QtCore import QUrl
    from PyQt5.QtWidgets import QApplication

    _qapp = QApplication.instance() or QApplication([])
    monkeypatch.setattr(app, "activate_message_link", lambda *a, **k: (_ for _ in ()).throw(ValueError("boom")))
    monkeypatch.setattr(app.QToolTip, "showText", lambda *a, **k: None)
    app.AutoSizingTextBrowser()._on_anchor_clicked(QUrl("file:///tmp/x.mp4"))  # must not raise


def test_render_time_stats_never_follow_a_symlink_out_of_the_safe_roots(tmp_path: Path) -> None:
    """`is_safe_to_stat` is lexical: ~/link -> /Volumes/share passed it and `exists()`
    then walked onto the mount. A symlinked component is left to click time."""
    real = tmp_path / "real"
    real.mkdir()
    (real / "clip.mp4").write_bytes(b"0")
    (tmp_path / "link").symlink_to(real)
    assert lt.exists_locally(str(real / "clip.mp4")) is True
    assert lt.exists_locally(str(tmp_path / "link" / "clip.mp4")) is False
    assert lt.mentioned_local_files(f"`{tmp_path}/link/clip.mp4`") == []
