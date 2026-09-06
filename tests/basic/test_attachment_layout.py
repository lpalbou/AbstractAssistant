"""Layout contract for multi-attachment rendering.

Attaching several documents used to produce one full-bubble-width card per
file (a 50px thumbnail marooned in a wide empty box) and a composer tray that
silently clipped every chip past the first row. These tests pin the fixed
behaviour: images pack into a wrapped square-tile gallery, and chip rows wrap
instead of disappearing.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QImage, QPixmap
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
    """Media the ASSISTANT produced is the answer: it keeps the real gallery.

    (Files the user attached take the compact-chip path instead — see
    ``test_user_attachments_render_as_compact_chips``.)
    """
    app = _app()
    paths = [_write_image(tmp_path, f"page{i}.png", 600, 800) for i in range(4)]
    message = {
        "role": "assistant",
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

    def _build(artifact, _message, *, tile_size=0, compact=False):
        # A builder that can only preview images: the documents must still
        # reach the bubble through the fallback tray.
        if app_module._artifact_media_kind(artifact) != "image":
            return None
        return ArtifactPreviewCard(
            artifact=artifact,
            resolve_path=lambda p=artifact["local_path"]: __import__("pathlib").Path(p),
            tile_size=tile_size,
            compact=compact,
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

    strips = [
        widget
        for widget in card.findChildren(FlowContainer)
        if widget.objectName() == "attachmentChipStrip"
    ]
    assert len(strips) == 1 and strips[0].flow().count() == 2
    trays = [
        widget
        for widget in card.findChildren(FlowContainer)
        if widget.objectName() == "artifactChipTray"
    ]
    assert len(trays) == 1, "the three documents must still be reachable"
    assert trays[0].flow().count() == 3
    card.close()


@pytest.mark.basic
def test_rounded_thumbnail_keeps_aspect_and_stays_small() -> None:
    _app()
    height = app_module._ATTACHMENT_THUMB_HEIGHT
    max_width = app_module._ATTACHMENT_THUMB_MAX_WIDTH
    for width, source_height, expected in (
        # A 16:9 screenshot keeps its shape...
        (2560, 1440, QSize(int(height * 16 / 9), height)),
        # ...a tall image is bounded by the height, not stretched...
        (400, 1600, QSize(max(1, height // 4), height)),
        # ...and a panorama is clamped by the width instead.
        (4000, 500, QSize(max_width, max(1, round(max_width * 500 / 4000)))),
    ):
        image = QImage(width, source_height, QImage.Format_RGB32)
        image.fill(0x336699)
        thumb = app_module._rounded_thumbnail(
            QPixmap.fromImage(image), height=height, max_width=max_width
        )
        # Rendered at 2x for retina, so the LOGICAL size is what layout sees.
        assert thumb.devicePixelRatio() == 2.0
        logical = QSize(thumb.width() // 2, thumb.height() // 2)
        assert abs(logical.width() - expected.width()) <= 1
        assert abs(logical.height() - expected.height()) <= 1
        assert logical.height() <= height and logical.width() <= max_width


@pytest.mark.basic
def test_compact_card_shows_the_picture_not_a_glyph(tmp_path) -> None:
    """The operator's complaint: a small attachment must still BE the image."""
    app = _app()
    path = _write_image(tmp_path, "Screenshot 2026-09-06 at 12.43.58 PM.png", 2560, 1440)
    chip = ArtifactPreviewCard(
        artifact={"local_path": path, "filename": Path(path).name, "modality": "image"},
        resolve_path=lambda: Path(path),
        compact=True,
    )
    chip.show()
    for _ in range(200):
        app.processEvents()
        if chip._source_pixmap is not None:
            break

    assert chip.is_compact()
    # The pill placeholder gave way to the picture, which carries its own frame.
    assert chip.objectName() == "mediaPreviewThumb"
    assert chip._thumb_label is not None
    assert chip._thumb_label.objectName() == "mediaPreviewChipImage"
    thumb = chip._thumb_label.pixmap()
    assert thumb is not None and not thumb.isNull()
    logical_height = thumb.height() // 2
    logical_width = thumb.width() // 2
    # Small — but a real 16:9 thumbnail, not a 260px tile and not a 20px stamp.
    assert logical_height == app_module._ATTACHMENT_THUMB_HEIGHT
    assert logical_width == pytest.approx(logical_height * 16 / 9, abs=2)
    # The picture is the source image, not the type glyph: its middle pixel
    # carries the fill colour we wrote to disk.
    middle = thumb.toImage().pixelColor(thumb.width() // 2, thumb.height() // 2)
    assert (middle.red(), middle.green(), middle.blue()) == (0x33, 0x66, 0x99)
    # A tile resize request from a gallery cannot re-inflate a compact card.
    chip.set_tile_size(260)
    assert chip._thumb_label.pixmap().height() // 2 == app_module._ATTACHMENT_THUMB_HEIGHT
    assert "2560x1440" in chip.toolTip()
    chip.deleteLater()


@pytest.mark.basic
def test_compact_card_keeps_the_name_pill_when_there_is_no_picture(tmp_path) -> None:
    """A PDF — or an image whose file is gone — still reads as an attachment."""
    app = _app()
    missing = tmp_path / "Screenshot gone.png"
    for artifact, resolver in (
        (
            {"local_path": str(tmp_path / "q1.pdf"), "filename": "q1.pdf"},
            lambda: Path(tmp_path / "q1.pdf"),
        ),
        (
            {"local_path": str(missing), "filename": missing.name, "modality": "image"},
            lambda: Path(missing),
        ),
    ):
        card = ArtifactPreviewCard(
            artifact=artifact, resolve_path=resolver, compact=True
        )
        for _ in range(200):
            app.processEvents()
            if card._local_path is not None:
                break
        assert card.objectName() == "mediaPreviewChip"
        names = [
            widget
            for widget in card.findChildren(app_module.QLabel)
            if widget.objectName() == "mediaPreviewChipName"
        ]
        assert names and artifact["filename"][:6] in names[0].text()
        card.deleteLater()


@pytest.mark.basic
def test_compact_chip_click_opens_the_image_preview(tmp_path) -> None:
    app = _app()
    path = _write_image(tmp_path, "shot.png", 900, 300)
    chip = ArtifactPreviewCard(
        artifact={"local_path": path, "filename": "shot.png", "modality": "image"},
        resolve_path=lambda: Path(path),
        compact=True,
    )
    for _ in range(200):
        app.processEvents()
        if chip._source_pixmap is not None:
            break

    opened: list = []
    # Click the THUMBNAIL label, not the frame: the whole card must be the
    # button, so the press has to propagate from the child up to the card.
    from PyQt5.QtTest import QTest

    chip.show()
    app.processEvents()
    QTest.mouseClick(chip._thumb_label, Qt.LeftButton)
    app.processEvents()
    dialog = chip._preview_dialog
    assert isinstance(dialog, app_module.ImagePreviewDialog)
    # Modeless: the transcript stays usable behind the preview.
    assert not dialog.isModal()
    assert "shot.png" in dialog.windowTitle()
    dialog.close()

    # A non-image chip has no in-app preview: it hands the file to the OS.
    doc = ArtifactPreviewCard(
        artifact={"local_path": str(tmp_path / "report.pdf"), "filename": "report.pdf"},
        resolve_path=lambda: Path(tmp_path / "report.pdf"),
        compact=True,
    )
    for _ in range(200):
        app.processEvents()
        if doc._local_path is not None:
            break
    doc._open_external = lambda: opened.append("external")  # type: ignore[method-assign]
    doc._activate_compact()
    assert opened == ["external"]
    assert doc._preview_dialog is None
    chip.deleteLater()
    doc.deleteLater()


@pytest.mark.basic
def test_missing_attachment_reports_the_real_reason(tmp_path) -> None:
    """A deleted attachment must not be reported as "artifact_id is required"."""
    from abstractassistant.controller import AssistantController

    controller = AssistantController.__new__(AssistantController)
    gone = tmp_path / "Screenshot 2026-09-06 at 12.43.58 PM.png"
    with pytest.raises(FileNotFoundError) as excinfo:
        AssistantController.download_artifact(
            controller,
            run_id="",
            artifact={"local_path": str(gone), "filename": gone.name},
        )
    assert "no longer on disk" in str(excinfo.value)
    assert gone.name in str(excinfo.value)

    # A gateway artifact with no id is still the old programming error.
    with pytest.raises(ValueError):
        AssistantController.download_artifact(
            controller, run_id="run_1", artifact={"filename": "x.png"}
        )


@pytest.mark.basic
def test_image_preview_dialog_fits_the_screen_without_upscaling() -> None:
    _app()
    dialog_cls = app_module.ImagePreviewDialog
    # A small image is shown at its own size...
    assert dialog_cls.fit_size(QSize(320, 200)) == QSize(320, 200)
    # ...a huge one is bounded, keeping its aspect ratio.
    fitted = dialog_cls.fit_size(QSize(8000, 4000))
    assert fitted.width() < 8000 and fitted.height() < 4000
    assert abs(fitted.width() / fitted.height() - 2.0) < 0.02


@pytest.mark.basic
def test_user_attachments_render_as_compact_chips(tmp_path) -> None:
    """Operator ask 2026-09-06: an attached screenshot must cost one line."""
    app = _app()
    path = _write_image(tmp_path, "screenshot.png", 2560, 1440)
    message = {
        "role": "user",
        "content": "i get this with my current apple account, what do you recommend?",
        "metadata": {
            "attachments": [
                {"local_path": path, "filename": "screenshot.png", "modality": "image"}
            ]
        },
    }

    seen: list[bool] = []

    def _build(artifact, _message, *, tile_size=0, compact=False):
        seen.append(compact)
        return ArtifactPreviewCard(
            artifact=artifact,
            resolve_path=lambda p=artifact["local_path"]: Path(p),
            tile_size=tile_size,
            compact=compact,
        )

    card = MessageCard(
        message=message,
        message_key="user-attachment",
        renderer=app_module.MarkdownRenderer(theme="friendly_grayscale"),
        on_open_artifact=lambda *_a, **_k: None,
        build_media_preview=_build,
        bubble_width=520,
    )
    card.show()
    app.processEvents()

    assert seen == [True], "user attachments are built compact"
    assert not card.findChildren(MediaGallery), "no gallery tile for an input file"
    strips = [
        widget
        for widget in card.findChildren(FlowContainer)
        if widget.objectName() == "attachmentChipStrip"
    ]
    assert len(strips) == 1 and strips[0].flow().count() == 1
    chips = [
        widget
        for widget in card.findChildren(ArtifactPreviewCard)
        if widget.is_compact()
    ]
    assert len(chips) == 1
    # The PICTURE reached the bubble. Without this the test passes when every
    # thumbnail silently degrades to the icon pill — the exact regression the
    # operator reported ("it removed ALL thumbnails").
    assert chips[0]._source_pixmap is not None
    assert chips[0].objectName() == "mediaPreviewThumb"
    row_height = strips[0].flow().heightForWidth(496)
    assert row_height == app_module._ATTACHMENT_THUMB_HEIGHT
    # ...and it is a small thumbnail, not a 260px block.
    assert row_height < MediaGallery._base_tile_size(1)
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
