"""A picture the run produced renders in the answer, and every file is openable (2026-09-27).

Operator: "what's with this non clickable icon and no curve". The answer of the
Memory-monitor discussion ended with `![Memory over time](memory_curve.png)`: a
path RELATIVE to the run's workspace on the gateway host. The renderer handed Qt
a bare `<img src="memory_curve.png">`; the text browser loads no file images (by
design) and Qt drew its "missing image" glyph — a small document icon, not a
link. Now the palette resolves the reference in the run's workspace (in place on
the gateway's machine, else a copy through `GET /runs/{id}/workspace/content`),
the card renders it at the bubble's width inside a link to the file, and a
reference nothing can resolve is a labelled mention, never the glyph.

The fixture is the real run (read-only GETs against the live gateway): the
agent's verbatim answer and the verbatim `GET /runs/{id}/workspace` answer.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QPoint, Qt  # noqa: E402
from PyQt5.QtGui import QImage, QTextDocument  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from abstractassistant import app as app_module  # noqa: E402
from abstractassistant.core.file_activity import FileOperation  # noqa: E402
from abstractassistant.core.link_targets import file_href  # noqa: E402
from abstractassistant.core.workspace_images import (  # noqa: E402
    downloaded_workspace_path,
    local_workspace_image,
    workspace_relative_path,
    workspace_relative_to_root,
)
from abstractassistant.utils.markdown_renderer import MarkdownRenderer, ResolvedImage  # noqa: E402

_APP = QApplication.instance() or QApplication([])

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "gateway_runs" / "memory_curve_run.json").read_text(encoding="utf-8")
)
PNG_NAME = FIXTURE["workspace_files"][0]["path"]


def _write_png(path: Path, size=None) -> Path:
    width, height = size or FIXTURE["png_size"]
    image = QImage(int(width), int(height), QImage.Format_RGB32)
    image.fill(Qt.white)
    path.parent.mkdir(parents=True, exist_ok=True)
    assert image.save(str(path), "PNG")
    return path


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    _write_png(root / PNG_NAME)
    (root / "memory_curve.py").write_text("print('plot')\n", encoding="utf-8")
    return root


def _body(html: str) -> str:
    return html.split('<div class="markdown-content">', 1)[1]


# --------------------------------------------------------------------------- the fixture


def test_the_fixture_is_the_reported_answer() -> None:
    assert "![Memory over time](memory_curve.png)" in FIXTURE["answer"]
    assert FIXTURE["workspace"]["host"]["caller_is_this_machine"] is True
    assert PNG_NAME == "memory_curve.png"


# --------------------------------------------------------------------------- resolution (pure)


@pytest.mark.parametrize(
    "src, expected",
    [
        ("memory_curve.png", "memory_curve.png"),
        ("./plots/a.png", "plots/a.png"),
        ("plots/../a.png", "a.png"),
        ("plots%2Fa%20b.png?v=2#x", "plots/a b.png"),
        ("../outside.png", None),
        ("/abs/a.png", None),
        ("~/a.png", None),
        ("https://example.org/a.png", None),
        ("file:///tmp/a.png", None),
        ("data:image/png;base64,AAAA", None),
        ("", None),
    ],
)
def test_workspace_relative_path(src, expected) -> None:
    assert workspace_relative_path(src) == expected


def test_a_relative_reference_resolves_inside_the_workspace(workspace: Path) -> None:
    expected = os.path.realpath(workspace / PNG_NAME)
    assert local_workspace_image(PNG_NAME, str(workspace)) == expected
    # An absolute path or file URL inside the workspace is the same file.
    assert local_workspace_image(str(workspace / PNG_NAME), str(workspace)) == expected
    assert local_workspace_image(file_href(str(workspace / PNG_NAME)), str(workspace)) == expected


def test_nothing_outside_the_workspace_or_not_an_image_resolves(workspace: Path, tmp_path: Path) -> None:
    outside = _write_png(tmp_path / "outside.png", (10, 10))
    assert local_workspace_image("../outside.png", str(workspace)) is None
    assert local_workspace_image(str(outside), str(workspace)) is None
    # A symlink inside the workspace that points out of it is judged by its target.
    (workspace / "link.png").symlink_to(outside)
    assert local_workspace_image("link.png", str(workspace)) is None
    assert local_workspace_image("memory_curve.py", str(workspace)) is None  # not an image
    assert local_workspace_image("missing.png", str(workspace)) is None
    assert local_workspace_image(PNG_NAME, "") is None


def test_remote_copies_have_a_stable_readable_place(tmp_path: Path) -> None:
    root = FIXTURE["workspace"]["workspace_root"]
    assert workspace_relative_to_root(f"{root}/plots/a.png", root) == "plots/a.png"
    assert workspace_relative_to_root("/elsewhere/a.png", root) is None
    first = downloaded_workspace_path(tmp_path, run_id=FIXTURE["root_run_id"], relative_path=PNG_NAME)
    again = downloaded_workspace_path(tmp_path, run_id=FIXTURE["root_run_id"], relative_path=PNG_NAME)
    other = downloaded_workspace_path(tmp_path, run_id=FIXTURE["agent_run_id"], relative_path=PNG_NAME)
    assert first == again and first != other
    assert first.name == PNG_NAME and tmp_path in first.parents
    assert downloaded_workspace_path(tmp_path, run_id="r", relative_path="../x.png") is None


# --------------------------------------------------------------------------- renderer


def test_an_unresolved_image_is_a_label_never_qts_broken_image_glyph() -> None:
    body = _body(MarkdownRenderer().render(FIXTURE["answer"]))
    assert "<img" not in body
    assert "Memory over time (memory_curve.png)" in body


def test_web_and_local_images_become_links_and_data_images_stay_inline() -> None:
    body = _body(
        MarkdownRenderer().render(
            "![w](https://example.org/a.png) ![z](/tmp/q.png) ![d](data:image/png;base64,iVBORw0KGgo=)"
        )
    )
    assert '<a href="https://example.org/a.png">w (a.png)</a>' in body
    assert '<a class="aa-file" href="file:///tmp/q.png">z (q.png)</a>' in body
    srcs = re.findall(r'<img src="([^"]+)"', body)
    assert srcs == ["data:image/png;base64,iVBORw0KGgo="]


def test_a_resolved_image_is_a_sized_link_to_its_file() -> None:
    seen = []

    def resolver(src, alt):
        seen.append((src, alt))
        return ResolvedImage(src="aa-image://img1", href="file:///ws/memory_curve.png", width=596, height=248)

    body = _body(MarkdownRenderer().render(FIXTURE["answer"], image_resolver=resolver))
    assert seen == [("memory_curve.png", "Memory over time")]
    assert (
        '<a class="aa-image" href="file:///ws/memory_curve.png"><img src="aa-image://img1" '
        'width="596" height="248" alt="Memory over time" /></a>'
    ) in body
    # A paragraph that is only the picture is a figure (no proportional line height).
    assert '<div class="aa-figure"' in body
    # An image inside running text stays in its paragraph.
    inline = _body(MarkdownRenderer().render("see ![a](x.png) here", image_resolver=resolver))
    assert "aa-figure" not in inline and "<p>" in inline


# --------------------------------------------------------------------------- the card


def _card(message, resolve_image, width=620):
    return app_module.MessageCard(
        message=message,
        message_key="k",
        renderer=MarkdownRenderer(),
        on_open_artifact=lambda *_: None,
        bubble_width=width,
        resolve_image=resolve_image,
    )


def _message() -> dict:
    return {"role": "assistant", "content": FIXTURE["answer"], "run_id": FIXTURE["root_run_id"]}


def _image_browser(card):
    for browser in card.findChildren(app_module.AutoSizingTextBrowser):
        if browser._inline_images:
            return browser
    raise AssertionError("no text block registered an inline image")


def test_the_card_shows_the_runs_picture_inline_and_a_click_opens_the_file(workspace: Path) -> None:
    asked = []

    def resolve(src, message):
        asked.append((src, message.get("run_id")))
        return local_workspace_image(src, str(workspace))

    card = _card(_message(), resolve, width=620)
    assert asked == [("memory_curve.png", FIXTURE["root_run_id"])]
    browser = _image_browser(card)
    loaded = browser.loadResource(QTextDocument.ImageResource, app_module.QUrl("aa-image://img1"))
    assert isinstance(loaded, QImage) and not loaded.isNull()

    # Sized to the text width (bubble − 24), aspect kept, never upscaled.
    text_width = 620 - 24
    natural_w, natural_h = FIXTURE["png_size"]
    html = browser.toHtml()
    match = re.search(r'<img src="aa-image://img1"[^>]*width="(\d+)"[^>]*height="(\d+)"', html)
    assert match, html
    assert int(match.group(1)) == text_width
    assert int(match.group(2)) == round(natural_h * text_width / natural_w)

    # The picture is hit-testable as a link to the file itself.
    card.resize(640, 800)
    card.show()
    QApplication.processEvents()
    browser.refresh_height(text_width)
    layout = browser.document().documentLayout()
    block = browser.document().begin()
    image_rect = None
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            fragment = it.fragment()
            if fragment.charFormat().isImageFormat():
                image_rect = layout.blockBoundingRect(block)
            it += 1
        block = block.next()
    assert image_rect is not None
    href = browser.anchorAt(QPoint(int(image_rect.center().x()), int(image_rect.center().y())))
    assert href == file_href(os.path.realpath(workspace / PNG_NAME))
    card.hide()


def test_an_unresolvable_picture_never_leaves_a_broken_image_in_the_card() -> None:
    card = _card(_message(), lambda src, message: None)
    for browser in card.findChildren(app_module.AutoSizingTextBrowser):
        assert "<img" not in browser.toHtml()
    assert "Memory over time (memory_curve.png)" in " ".join(
        b.toPlainText() for b in card.findChildren(app_module.AutoSizingTextBrowser)
    )


def test_a_wider_bubble_lays_the_picture_out_again(workspace: Path) -> None:
    card = _card(_message(), lambda src, m: local_workspace_image(src, str(workspace)), width=400)
    card.set_bubble_width(800)
    html = _image_browser(card).toHtml()
    assert re.search(r'<img src="aa-image://img1"[^>]*width="776"', html), html


# --------------------------------------------------------------------------- the palette


class _Gateway:
    def __init__(self, workspace_answer, files=None):
        self.workspace_answer = workspace_answer
        self.files = files or {}
        self.calls = []

    def get_run_workspace(self, *, run_id):
        self.calls.append(("workspace", run_id))
        return self.workspace_answer

    def download_run_workspace_file(self, *, run_id, path):
        self.calls.append(("content", run_id, path))
        return self.files[path], "image/png"


class _Manager:
    def __init__(self, gateway):
        self._gateway = gateway

    def gateway_client(self):
        return self._gateway


class _Controller:
    def __init__(self, gateway, data_dir):
        self.llm_manager = _Manager(gateway)
        self.data_dir = data_dir


def _palette(gateway, data_dir):
    palette = app_module.AssistantPalette.__new__(app_module.AssistantPalette)
    palette.__dict__["_controller"] = _Controller(gateway, data_dir)
    # Gateway calls run inline here; the real palette runs them on a QThread.
    palette.__dict__["_start_gateway_call"] = lambda call, done: _run_inline(call, done)
    redraws = []
    palette.__dict__["refresh_history"] = lambda *a, **k: redraws.append(1)
    banners = []
    palette.__dict__["_set_banner"] = lambda text="", tone="info", key="": banners.append(text)
    return palette, redraws, banners


def _run_inline(call, done):
    try:
        result = call()
    except Exception as exc:
        done(None, str(exc))
        return
    done(result, "")


def test_on_the_gateways_machine_the_file_is_read_in_place(workspace: Path, tmp_path: Path) -> None:
    answer = dict(FIXTURE["workspace"], workspace_root=str(workspace))
    gateway = _Gateway(answer)
    palette, redraws, _ = _palette(gateway, tmp_path / "data")
    # The first render only asks where the run's files are, and redraws when told.
    assert palette._resolve_message_image(PNG_NAME, _message()) is None
    assert redraws
    path = palette._resolve_message_image(PNG_NAME, _message())
    assert path == os.path.realpath(workspace / PNG_NAME)
    # Asked once per run; the file is read in place (nothing downloaded).
    palette._resolve_message_image(PNG_NAME, _message())
    assert gateway.calls == [("workspace", FIXTURE["root_run_id"])]


def test_from_another_machine_a_copy_comes_through_the_gateway(tmp_path: Path) -> None:
    source = _write_png(tmp_path / "src" / PNG_NAME)
    answer = dict(FIXTURE["workspace"], host={"hostname": "forge.local", "caller_is_this_machine": False})
    gateway = _Gateway(answer, files={PNG_NAME: source.read_bytes()})
    palette, redraws, _ = _palette(gateway, tmp_path / "data")
    assert palette._resolve_message_image(PNG_NAME, _message()) is None  # where are the files?
    assert palette._resolve_message_image(PNG_NAME, _message()) is None  # fetching the copy
    # The copy landed and the transcript was asked to redraw; the next render finds it.
    assert gateway.calls == [
        ("workspace", FIXTURE["root_run_id"]),
        ("content", FIXTURE["root_run_id"], PNG_NAME),
    ]
    assert len(redraws) == 2
    again = palette._resolve_message_image(PNG_NAME, _message())
    assert again is not None and Path(again).read_bytes() == source.read_bytes()
    assert len(gateway.calls) == 2


def test_a_file_the_run_touched_opens_in_place_or_through_the_gateway(tmp_path: Path, monkeypatch) -> None:
    opened = []
    monkeypatch.setattr(app_module, "activate_message_link", lambda href, **_: opened.append(href) or "")
    local = _write_png(tmp_path / "here" / PNG_NAME, (4, 4))
    gateway = _Gateway(dict(FIXTURE["workspace"], host={"caller_is_this_machine": False}), files={"memory_curve.py": b"x"})
    palette, _, banners = _palette(gateway, tmp_path / "data")
    assert palette._open_run_file(_message(), str(local)) == ""
    assert opened == [file_href(str(local))]
    remote = f"{FIXTURE['workspace']['workspace_root']}/memory_curve.py"
    assert palette._open_run_file(_message(), remote) == ""
    copy = downloaded_workspace_path(tmp_path / "data" / "downloads", run_id=FIXTURE["root_run_id"], relative_path="memory_curve.py")
    assert opened[-1] == file_href(str(copy)) and copy.read_bytes() == b"x"
    assert not banners


def test_every_file_card_has_an_open_button_except_a_deleted_file(tmp_path: Path) -> None:
    clicked = []
    created = app_module.FileOperationCard(
        operation=FileOperation(action="created", path="/w/memory_curve.py", via="execute_command"),
        index=0,
        on_open=lambda path: clicked.append(path) or "",
    )
    assert created.open_button is not None
    created.open_button.click()
    assert clicked == ["/w/memory_curve.py"]
    deleted = app_module.FileOperationCard(
        operation=FileOperation(action="deleted", path="/w/old.txt", via="execute_command"),
        index=1,
        on_open=lambda path: "",
    )
    assert deleted.open_button is None
