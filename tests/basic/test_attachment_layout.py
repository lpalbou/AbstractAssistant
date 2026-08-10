"""Layout contract for multi-attachment rendering.

Attaching several documents used to produce one full-bubble-width card per
file (a 50px thumbnail marooned in a wide empty box) and a composer tray that
silently clipped every chip past the first row. These tests pin the fixed
behaviour: images pack into a wrapped square-tile gallery, and chip rows wrap
instead of disappearing.
"""

from __future__ import annotations

import os

import pytest
from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QImage
from PyQt5.QtWidgets import QApplication, QPushButton, QWidget

import abstractassistant.app as app_module
from abstractassistant.app import (
    ArtifactPreviewCard,
    FlowContainer,
    FlowLayout,
    MediaGallery,
    MessageCard,
    _attachment_tray_height,
    _ATTACHMENT_TRAY_MAX_ROWS,
)


_QAPP: QApplication | None = None


def _app() -> QApplication:
    # Held module-global: a QApplication with no live Python reference is
    # garbage collected and the next QWidget construction aborts the process.
    global _QAPP
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _QAPP = QApplication.instance() or QApplication([])
    return _QAPP


def _write_image(tmp_path, name: str, width: int, height: int) -> str:
    image = QImage(width, height, QImage.Format_RGB32)
    image.fill(0x336699)
    path = tmp_path / name
    assert image.save(str(path), "PNG")
    return str(path)


@pytest.mark.basic
def test_flow_layout_wraps_instead_of_overflowing() -> None:
    _app()
    host = FlowContainer(h_spacing=6, v_spacing=6)
    for _ in range(6):
        button = QPushButton("chip")
        button.setFixedSize(100, 30)
        host.flow().addWidget(button)

    # 3 x 100px chips (+2 gaps) = 312px fit in 320; the other 3 wrap below.
    assert host.flow().rows_for_width(320) == 2
    assert host.flow().rows_for_width(140) == 6
    assert host.flow().rows_for_width(1200) == 1
    # A wrapped layout reports the taller height so the parent reserves room.
    assert host.flow().heightForWidth(320) > host.flow().heightForWidth(1200)
    host.deleteLater()


@pytest.mark.basic
def test_media_gallery_packs_tiles_into_columns() -> None:
    _app()
    # Four attachments at a typical bubble width share rows instead of each
    # taking a full-width row of their own.
    assert MediaGallery._columns_for(4, 520) == 4
    assert MediaGallery._columns_for(4, 300) == 2
    assert MediaGallery._columns_for(1, 520) == 1

    # Rows are balanced, never ragged: no row may be shorter than the previous
    # one by more than the count allows (a 3 + 1 tail is the bug being pinned).
    for count in range(1, 17):
        for width in (200, 320, 520, 900):
            columns = MediaGallery._columns_for(count, width)
            rows = -(-count // columns)
            balanced = -(-count // rows)
            assert columns == balanced, (count, width, columns)

    # Tiles never exceed the width they were given.
    for count in (1, 2, 3, 4, 5, 9, 12):
        for width in (200, 320, 520, 900):
            columns = MediaGallery._columns_for(count, width)
            tile = MediaGallery._tile_size(count, width)
            assert tile > 0
            assert columns * tile + (columns - 1) * MediaGallery._SPACING <= width + 1

    # A lone image gets a real preview, not a 50px stamp.
    assert MediaGallery._tile_size(1, 520) >= 200
    # Many images shrink so the gallery stays compact.
    assert MediaGallery._tile_size(12, 520) < MediaGallery._tile_size(2, 520)


@pytest.mark.basic
def test_media_gallery_regrids_on_width_change() -> None:
    app = _app()
    gallery = MediaGallery(available_width=520)
    cards = []
    for _ in range(4):
        card = QWidget()
        card.set_tile_size = lambda size, c=card: setattr(c, "_tile", size)  # type: ignore[attr-defined]
        cards.append(card)
        gallery.add_card(card)
    app.processEvents()

    grid = gallery.layout()
    positions = {grid.getItemPosition(i)[:2] for i in range(grid.count())}
    assert positions == {(0, 0), (0, 1), (0, 2), (0, 3)}
    assert 4 * gallery.tile_size() + 3 * MediaGallery._SPACING <= 520

    gallery.set_available_width(280)
    app.processEvents()
    grid = gallery.layout()
    positions = {grid.getItemPosition(i)[:2] for i in range(grid.count())}
    assert positions == {(0, 0), (0, 1), (1, 0), (1, 1)}
    # Fewer columns may mean *larger* tiles; what must hold is that the row
    # still fits the narrower bubble.
    assert 2 * gallery.tile_size() + MediaGallery._SPACING <= 280
    # The cards were told to re-scale.
    assert all(getattr(card, "_tile", 0) == gallery.tile_size() for card in cards)
    gallery.deleteLater()


@pytest.mark.basic
def test_artifact_preview_card_tiles_to_a_square(tmp_path) -> None:
    app = _app()
    path = _write_image(tmp_path, "wide.png", 800, 200)
    card = ArtifactPreviewCard(
        artifact={"filename": "wide.png", "modality": "image"},
        resolve_path=lambda: __import__("pathlib").Path(path),
        tile_size=120,
    )
    # The async resolver emits into the GUI thread; pump until it lands.
    for _ in range(200):
        app.processEvents()
        if card._image_button is not None:
            break
    assert card._image_button is not None

    assert card.objectName() == "mediaPreviewTile"
    # Square tile keeps the grid aligned...
    assert card._image_button.size() == QSize(120, 120)
    # ...while the icon keeps the source 4:1 aspect ratio.
    icon = card._image_button.iconSize()
    assert icon.width() == 120
    assert icon.height() == 30

    card.set_tile_size(90)
    app.processEvents()
    assert card._image_button.size() == QSize(90, 90)
    assert card._image_button.iconSize().width() == 90
    card.deleteLater()


@pytest.mark.basic
def test_artifact_preview_card_without_tile_keeps_inline_thumbnail(tmp_path) -> None:
    app = _app()
    path = _write_image(tmp_path, "tall.png", 200, 800)
    card = ArtifactPreviewCard(
        artifact={"filename": "tall.png", "modality": "image"},
        resolve_path=lambda: __import__("pathlib").Path(path),
    )
    for _ in range(200):
        app.processEvents()
        if card._image_button is not None:
            break
    assert card._image_button is not None
    assert card.objectName() == "mediaPreviewCard"
    assert card._image_button.height() == app_module._IMAGE_PREVIEW_HEIGHT
    card.deleteLater()


@pytest.mark.basic
def test_message_card_groups_images_into_one_gallery(tmp_path) -> None:
    app = _app()
    paths = [_write_image(tmp_path, f"page{i}.png", 600, 800) for i in range(4)]
    message = {
        "role": "user",
        "content": "here are the 4 illustrations of the novel",
        "metadata": {
            "attachments": [
                {"local_path": path, "filename": f"page{i}.png", "modality": "image"}
                for i, path in enumerate(paths)
            ]
        },
    }

    built: list[int] = []

    def _build(artifact, _message, *, tile_size=0):
        built.append(tile_size)
        return ArtifactPreviewCard(
            artifact=artifact,
            resolve_path=lambda p=artifact["local_path"]: __import__("pathlib").Path(p),
            tile_size=tile_size,
        )

    card = MessageCard(
        message=message,
        message_key="user-gallery",
        renderer=app_module.MarkdownRenderer(theme="friendly_grayscale"),
        on_open_artifact=lambda *_a, **_k: None,
        build_media_preview=_build,
        bubble_width=520,
    )
    card.show()
    app.processEvents()

    galleries = card.findChildren(MediaGallery)
    assert len(galleries) == 1, "four images must share one gallery, not four rows"
    assert galleries[0].card_count() == 4
    # Every image preview was asked for a tile, and they all agree.
    assert len(built) == 4 and len(set(built)) == 1 and built[0] > 0

    grid = galleries[0].layout()
    rows = {grid.getItemPosition(i)[0] for i in range(grid.count())}
    assert rows == {0}, "at 520px the four tiles fit on one row"

    # Resizing the transcript re-grids the gallery rather than clipping it.
    card.set_bubble_width(300)
    app.processEvents()
    grid = galleries[0].layout()
    rows = {grid.getItemPosition(i)[0] for i in range(grid.count())}
    assert rows == {0, 1}
    card.close()


@pytest.mark.basic
def test_message_card_keeps_players_full_width_and_wraps_chips(tmp_path) -> None:
    app = _app()
    message = {
        "role": "assistant",
        "content": "audio + images",
        "metadata": {
            "attachments": [
                {"local_path": str(tmp_path / "a.wav"), "modality": "audio"},
                {
                    "local_path": _write_image(tmp_path, "i.png", 300, 300),
                    "modality": "image",
                },
            ]
        },
    }

    seen: list[int] = []

    def _build(artifact, _message, *, tile_size=0):
        seen.append(tile_size)
        widget = QWidget()
        widget.set_tile_size = lambda _s: None  # type: ignore[attr-defined]
        return widget

    card = MessageCard(
        message=message,
        message_key="mixed",
        renderer=app_module.MarkdownRenderer(theme="friendly_grayscale"),
        on_open_artifact=lambda *_a, **_k: None,
        build_media_preview=_build,
        bubble_width=520,
    )
    card.show()
    app.processEvents()

    # The audio player is asked for tile_size=0 (full-width row); the image
    # gets a real tile.
    assert 0 in seen and any(value > 0 for value in seen)
    galleries = card.findChildren(MediaGallery)
    assert len(galleries) == 1 and galleries[0].card_count() == 1
    card.close()


@pytest.mark.basic
def test_message_card_fallback_chips_wrap(tmp_path) -> None:
    app = _app()
    message = {
        "role": "assistant",
        "content": "many files",
        "metadata": {
            "attachments": [
                {"local_path": str(tmp_path / f"doc{i}.pdf"), "filename": f"doc{i}.pdf"}
                for i in range(8)
            ]
        },
    }
    card = MessageCard(
        message=message,
        message_key="chips",
        renderer=app_module.MarkdownRenderer(theme="friendly_grayscale"),
        on_open_artifact=lambda *_a, **_k: None,
        build_media_preview=lambda *_a, **_k: None,
        bubble_width=320,
    )
    card.show()
    app.processEvents()

    trays = [
        widget
        for widget in card.findChildren(FlowContainer)
        if widget.objectName() == "artifactChipTray"
    ]
    assert len(trays) == 1, "chips share one wrapping tray, not one row each"
    assert trays[0].flow().count() == 8
    assert trays[0].flow().rows_for_width(320) > 1
    card.close()


@pytest.mark.basic
def test_attachment_tray_height_grows_then_caps() -> None:
    one = _attachment_tray_height(1)
    two = _attachment_tray_height(2)
    assert two > one
    # Beyond the cap the tray scrolls instead of eating the window.
    capped = _attachment_tray_height(_ATTACHMENT_TRAY_MAX_ROWS)
    assert _attachment_tray_height(_ATTACHMENT_TRAY_MAX_ROWS + 5) == capped


@pytest.mark.basic
def test_message_card_keeps_unpreviewable_documents_visible(tmp_path) -> None:
    """A message mixing images with PDFs must show BOTH: the old fallback only
    fired when nothing previewed, so the documents disappeared silently."""
    app = _app()
    message = {
        "role": "user",
        "content": "two pictures and three reports",
        "metadata": {
            "attachments": [
                {
                    "local_path": _write_image(tmp_path, "shot1.png", 400, 400),
                    "modality": "image",
                },
                {
                    "local_path": _write_image(tmp_path, "shot2.png", 400, 400),
                    "modality": "image",
                },
                {"local_path": str(tmp_path / "q1.pdf"), "filename": "q1.pdf"},
                {"local_path": str(tmp_path / "q2.pdf"), "filename": "q2.pdf"},
                {"local_path": str(tmp_path / "q3.xlsx"), "filename": "q3.xlsx"},
            ]
        },
    }

    def _build(artifact, _message, *, tile_size=0):
        # Mirrors the real builder: only image/audio/video get a preview.
        if app_module._artifact_media_kind(artifact) != "image":
            return None
        return ArtifactPreviewCard(
            artifact=artifact,
            resolve_path=lambda p=artifact["local_path"]: __import__("pathlib").Path(p),
            tile_size=tile_size,
        )

    card = MessageCard(
        message=message,
        message_key="mixed-docs",
        renderer=app_module.MarkdownRenderer(theme="friendly_grayscale"),
        on_open_artifact=lambda *_a, **_k: None,
        build_media_preview=_build,
        bubble_width=520,
    )
    card.show()
    app.processEvents()

    galleries = card.findChildren(MediaGallery)
    assert len(galleries) == 1 and galleries[0].card_count() == 2
    trays = [
        widget
        for widget in card.findChildren(FlowContainer)
        if widget.objectName() == "artifactChipTray"
    ]
    assert len(trays) == 1, "the three documents must still be reachable"
    assert trays[0].flow().count() == 3
    card.close()


@pytest.mark.basic
def test_composer_tray_wraps_many_chips_and_grows(tmp_path) -> None:
    """Many attachments must stay visible: the tray wraps and the composer
    grows to fit, up to the row cap, instead of clipping chips off the edge."""
    app = _app()
    from PyQt5.QtWidgets import QFrame, QScrollArea

    palette = app_module.AssistantPalette.__new__(app_module.AssistantPalette)

    host = FlowContainer(h_spacing=6, v_spacing=6)
    tray = QScrollArea()
    tray.setWidgetResizable(True)
    tray.setWidget(host)
    tray.setFixedWidth(320)
    composer = QFrame()

    palette.attachments_host = host
    palette.attachments_layout = host.flow()
    palette.attachments_tray = tray
    palette.composer_card = composer
    palette._composer_drop_active = False
    palette._attachments = [str(tmp_path / f"doc{i}.pdf") for i in range(10)]
    palette._reflow_shell = lambda: None
    palette._remove_attachment = lambda _path: None

    app_module.AssistantPalette._render_attachments(palette)
    app.processEvents()

    chips = [
        widget
        for widget in host.findChildren(app_module.AttachmentIconChip)
    ]
    assert len(chips) == 10, "every attachment gets a chip"
    # 10 x 36px chips cannot fit one 320px row; they wrap.
    rows = host.flow().rows_for_width(320)
    assert rows > 1
    one_row = _attachment_tray_height(1)
    assert tray.height() > one_row
    assert composer.height() == app_module._COMPOSER_BASE_HEIGHT + tray.height()
    # Past the cap the tray scrolls rather than swallowing the window.
    assert tray.height() <= _attachment_tray_height(_ATTACHMENT_TRAY_MAX_ROWS)
    assert tray.verticalScrollBarPolicy() != Qt.ScrollBarAlwaysOff

    # Clearing collapses the composer back to its bare height.
    palette._attachments = []
    app_module.AssistantPalette._render_attachments(palette)
    app.processEvents()
    assert composer.height() == app_module._COMPOSER_BASE_HEIGHT
    assert not tray.isVisible()


@pytest.mark.basic
def test_flow_layout_take_at_releases_items() -> None:
    _app()
    layout = FlowLayout(h_spacing=4, v_spacing=4)
    buttons = [QPushButton(f"b{i}") for i in range(3)]
    for button in buttons:
        layout.addWidget(button)
    assert layout.count() == 3
    while layout.count():
        item = layout.takeAt(0)
        assert item is not None
    assert layout.count() == 0
    assert layout.itemAt(0) is None
    assert layout.takeAt(0) is None
