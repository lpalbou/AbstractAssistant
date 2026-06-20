"""Lightweight Mermaid flowchart rendering helpers.

This module intentionally supports a narrow Mermaid subset that covers the most
common assistant outputs: `flowchart` / `graph` diagrams with node/edge lines.
Unsupported Mermaid dialects fall back to raw code rendering upstream.
"""

from __future__ import annotations

import base64
import html
import math
import os
import re
import textwrap
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional

try:
    from PyQt5.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
    from PyQt5.QtGui import (
        QBrush,
        QColor,
        QFont,
        QFontMetrics,
        QGuiApplication,
        QImage,
        QLinearGradient,
        QPainter,
        QPainterPath,
        QPen,
        QPolygonF,
    )
    from PyQt5.QtSvg import QSvgRenderer
    from PyQt5.QtWidgets import QApplication
except Exception:  # pragma: no cover - import safety on minimal environments
    QBuffer = None  # type: ignore[assignment]
    QByteArray = None  # type: ignore[assignment]
    QIODevice = None  # type: ignore[assignment]
    QPointF = None  # type: ignore[assignment]
    QRectF = None  # type: ignore[assignment]
    Qt = None  # type: ignore[assignment]
    QBrush = None  # type: ignore[assignment]
    QColor = None  # type: ignore[assignment]
    QFont = None  # type: ignore[assignment]
    QFontMetrics = None  # type: ignore[assignment]
    QGuiApplication = None  # type: ignore[assignment]
    QImage = None  # type: ignore[assignment]
    QLinearGradient = None  # type: ignore[assignment]
    QPainter = None  # type: ignore[assignment]
    QPainterPath = None  # type: ignore[assignment]
    QPen = None  # type: ignore[assignment]
    QPolygonF = None  # type: ignore[assignment]
    QSvgRenderer = None  # type: ignore[assignment]
    QApplication = None  # type: ignore[assignment]


_QT_MERMAID_APP = None
_MERMAID_NODE_TEXT_MAX_WIDTH = 200


_HEADER_RE = re.compile(r"^(?:flowchart|graph)\s*(?P<direction>TB|TD|BT|LR|RL)?\s*$", flags=re.I)
_NODE_ID_RE = re.compile(r"[A-Za-z0-9_.:/-]+")
_ESCAPED_LINEBREAK_BETWEEN_TOKENS_RE = re.compile(r"(?<=[>|)\]}])\\n(?=\s*[\[\(\{A-Za-z0-9_.:/-])")


@dataclass
class MermaidNode:
    node_id: str
    label: str
    shape: str
    order: int
    width: float = 0.0
    height: float = 0.0
    center_x: float = 0.0
    center_y: float = 0.0


@dataclass
class MermaidEdge:
    source: str
    target: str
    style: str
    label: str = ""


@dataclass
class MermaidLayout:
    direction: str
    horizontal: bool
    total_width: float
    total_height: float
    nodes: Dict[str, MermaidNode]
    ordered_nodes: List[MermaidNode]
    edges: List[MermaidEdge]


def mermaid_block_to_data_uri(source: str) -> Optional[str]:
    layout = _build_flowchart_layout(source)
    if layout is None:
        return None
    return _layout_to_png_data_uri(layout)


def mermaid_flowchart_to_svg(source: str) -> Optional[str]:
    layout = _build_flowchart_layout(source)
    if layout is None:
        return None
    total_width = layout.total_width
    total_height = layout.total_height
    horizontal = layout.horizontal
    nodes = layout.nodes
    edges = layout.edges
    ordered_nodes = layout.ordered_nodes
    svg_parts: List[str] = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{int(total_width)}" height="{int(total_height)}" '
            f'viewBox="0 0 {int(total_width)} {int(total_height)}">'
        ),
        "<defs>",
        (
            '<marker id="arrow" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="7" markerHeight="7" '
            'orient="auto-start-reverse">'
            '<path d="M 0 0 L 10 5 L 0 10 z" fill="#8fd7ff"/>'
            "</marker>"
        ),
        (
            '<linearGradient id="panel" x1="0%" x2="100%" y1="0%" y2="100%">'
            '<stop offset="0%" stop-color="#151b24"/>'
            '<stop offset="100%" stop-color="#10161f"/>'
            "</linearGradient>"
        ),
        "</defs>",
        (
            f'<rect x="0.5" y="0.5" width="{max(1, int(total_width) - 1)}" height="{max(1, int(total_height) - 1)}" '
            'rx="16" fill="url(#panel)" stroke="rgba(255,255,255,0.08)"/>'
        ),
    ]

    for edge in edges:
        source_node = nodes.get(edge.source)
        target_node = nodes.get(edge.target)
        if source_node is None or target_node is None:
            continue
        svg_parts.append(_render_edge_svg(edge=edge, source=source_node, target=target_node, horizontal=horizontal))

    for node in ordered_nodes:
        svg_parts.append(_render_node_svg(node))

    svg_parts.append("</svg>")
    return "".join(svg_parts)


def _build_flowchart_layout(source: str) -> Optional[MermaidLayout]:
    diagram = _parse_flowchart(source)
    if diagram is None:
        return None
    if QFontMetrics is not None:
        _ensure_qt_gui_application()
    direction = str(diagram["direction"])
    nodes: Dict[str, MermaidNode] = dict(diagram["nodes"])
    edges: List[MermaidEdge] = list(diagram["edges"])
    ordered_nodes = sorted(nodes.values(), key=lambda item: item.order)
    if not ordered_nodes:
        return None

    for node in ordered_nodes:
        font = _node_text_font()
        metrics = QFontMetrics(font) if (font is not None and QFontMetrics is not None) else None
        lines = _wrap_label_lines(node.label, metrics=metrics, max_width=_MERMAID_NODE_TEXT_MAX_WIDTH)
        if metrics is not None:
            text_width = max((metrics.horizontalAdvance(line) for line in lines), default=72)
            line_height = max(metrics.lineSpacing(), 18)
            node.width = max(118.0, float(text_width + 44))
            node.height = max(56.0, float(len(lines) * line_height + 24))
        else:
            longest = max((len(line) for line in lines), default=8)
            node.width = max(118.0, 28.0 + float(longest * 7.2))
            node.height = max(56.0, 22.0 + float(len(lines) * 20.0))

    horizontal = direction in {"LR", "RL"}
    reversed_primary = direction in {"RL", "BT"}
    display_layer_map = _compute_layer_map(ordered_nodes=ordered_nodes, edges=edges, reversed_primary=reversed_primary)
    layer_groups: Dict[int, List[MermaidNode]] = defaultdict(list)
    for node in ordered_nodes:
        layer_groups[display_layer_map[node.node_id]].append(node)
    layer_keys = sorted(layer_groups.keys())
    max_cross_count = max((len(items) for items in layer_groups.values()), default=1)
    max_node_width = max((node.width for node in ordered_nodes), default=120.0)
    max_node_height = max((node.height for node in ordered_nodes), default=56.0)
    slot_primary = (max_node_width + 86.0) if horizontal else (max_node_height + 84.0)
    slot_cross = (max_node_height + 58.0) if horizontal else (max_node_width + 64.0)
    margin_x = 44.0
    margin_y = 40.0

    if horizontal:
        total_width = margin_x * 2.0 + float(len(layer_keys) - 1) * slot_primary + max_node_width
        total_height = margin_y * 2.0 + float(max_cross_count - 1) * slot_cross + max_node_height
        for layer in layer_keys:
            items = sorted(layer_groups[layer], key=lambda item: item.order)
            layer_offset = float(max_cross_count - len(items)) * slot_cross / 2.0
            for idx, node in enumerate(items):
                node.center_x = margin_x + layer * slot_primary + (max_node_width / 2.0)
                node.center_y = margin_y + layer_offset + idx * slot_cross + (max_node_height / 2.0)
    else:
        total_width = margin_x * 2.0 + float(max_cross_count - 1) * slot_cross + max_node_width
        total_height = margin_y * 2.0 + float(len(layer_keys) - 1) * slot_primary + max_node_height
        for layer in layer_keys:
            items = sorted(layer_groups[layer], key=lambda item: item.order)
            layer_offset = float(max_cross_count - len(items)) * slot_cross / 2.0
            for idx, node in enumerate(items):
                node.center_x = margin_x + layer_offset + idx * slot_cross + (max_node_width / 2.0)
                node.center_y = margin_y + layer * slot_primary + (max_node_height / 2.0)

    return MermaidLayout(
        direction=direction,
        horizontal=horizontal,
        total_width=total_width,
        total_height=total_height,
        nodes=nodes,
        ordered_nodes=ordered_nodes,
        edges=edges,
    )


def _parse_flowchart(source: str) -> Optional[Dict[str, object]]:
    normalized = str(source or "").replace("\r\n", "\n").replace("\r", "\n")
    raw_lines = [line.rstrip() for line in normalized.splitlines()]
    lines = [line for line in raw_lines if line.strip()]
    if not lines:
        return None

    header_match = _HEADER_RE.match(lines[0].strip())
    if not header_match:
        return None
    direction = str(header_match.group("direction") or "TD").upper()

    nodes: Dict[str, MermaidNode] = {}
    edges: List[MermaidEdge] = []
    order_counter = 0
    anonymous_counter = 0
    body_lines = lines[1:]
    if not body_lines:
        return None

    def ensure_node(node_id: str, *, label: str, shape: str) -> MermaidNode:
        nonlocal order_counter
        existing = nodes.get(node_id)
        label_text = _normalize_label(label or node_id)
        if existing is None:
            existing = MermaidNode(node_id=node_id, label=label_text, shape=shape, order=order_counter)
            nodes[node_id] = existing
            order_counter += 1
            return existing
        if (existing.label == existing.node_id and label_text != node_id) or (label_text and len(label_text) > len(existing.label)):
            existing.label = label_text
        if existing.shape == "rect" and shape != "rect":
            existing.shape = shape
        return existing

    def next_anonymous_node_id() -> str:
        nonlocal anonymous_counter
        anonymous_counter += 1
        return f"__mermaid_anon_{anonymous_counter}"

    for raw_line in _merge_wrapped_flowchart_lines(body_lines):
        line = _strip_comment(_sanitize_mermaid_line(raw_line)).strip()
        if not line:
            continue
        if line.startswith(("classDef ", "class ", "style ", "linkStyle ", "click ", "%%")):
            continue
        if line.startswith("subgraph ") or line == "end":
            return None
        parsed = _parse_statement(
            line,
            ensure_node=ensure_node,
            edges=edges,
            anonymous_node_id=next_anonymous_node_id,
        )
        if not parsed:
            return None

    return {"direction": direction, "nodes": nodes, "edges": edges}


def _parse_statement(
    line: str,
    *,
    ensure_node,
    edges: List[MermaidEdge],
    anonymous_node_id,
) -> bool:
    pos = 0
    current = _parse_node_spec(line, pos, anonymous_node_id=anonymous_node_id)
    if current is None:
        return False
    current_id, current_label, current_shape, pos = current
    ensure_node(current_id, label=current_label, shape=current_shape)
    parsed_edge = False

    while True:
        pos = _skip_ws(line, pos)
        if pos >= len(line):
            return True
        arrow = _parse_arrow(line, pos)
        if arrow is None:
            return False if parsed_edge else pos >= len(line)
        arrow_style, arrow_label, pos = arrow
        nxt = _parse_node_spec(line, pos, anonymous_node_id=anonymous_node_id)
        if nxt is None:
            return False
        target_id, target_label, target_shape, pos = nxt
        ensure_node(target_id, label=target_label, shape=target_shape)
        edges.append(MermaidEdge(source=current_id, target=target_id, style=arrow_style, label=arrow_label))
        current_id = target_id
        parsed_edge = True


def _parse_node_spec(line: str, pos: int, *, anonymous_node_id=None) -> Optional[tuple[str, str, str, int]]:
    pos = _skip_ws(line, pos)
    node_match = _NODE_ID_RE.match(line, pos)
    if node_match is None:
        if anonymous_node_id is None:
            return None
        shape_spec = _parse_shape_spec(line, pos)
        if shape_spec is None:
            return None
        label, shape, next_pos = shape_spec
        return anonymous_node_id(), label, shape, next_pos

    node_id = node_match.group(0)
    pos = node_match.end()
    label = node_id
    shape = "rect"
    shape_spec = _parse_shape_spec(line, pos)
    if shape_spec is not None:
        label, shape, pos = shape_spec
    return node_id, label, shape, pos


def _parse_shape_spec(line: str, pos: int) -> Optional[tuple[str, str, int]]:
    for open_token, close_token, mapped_shape in (
        ("([", "])", "stadium"),
        ("((", "))", "circle"),
        ("{{", "}}", "hex"),
        ("[", "]", "rect"),
        ("(", ")", "round"),
        ("{", "}", "diamond"),
    ):
        if line.startswith(open_token, pos):
            close_index = line.find(close_token, pos + len(open_token))
            if close_index < 0:
                return None
            label = line[pos + len(open_token):close_index]
            return label, mapped_shape, close_index + len(close_token)
    return None


def _parse_arrow(line: str, pos: int) -> Optional[tuple[str, str, int]]:
    pos = _skip_ws(line, pos)
    for token in ("-.->", "-->", "==>", "---", "--", "=="):
        if line.startswith(token, pos):
            next_pos = pos + len(token)
            label = ""
            next_pos = _skip_ws(line, next_pos)
            if next_pos < len(line) and line[next_pos] == "|":
                close_index = line.find("|", next_pos + 1)
                if close_index < 0:
                    return None
                label = line[next_pos + 1:close_index].strip()
                next_pos = _skip_ws(line, close_index + 1)
            return token, label, next_pos
    return None


def _compute_layer_map(
    *,
    ordered_nodes: List[MermaidNode],
    edges: List[MermaidEdge],
    reversed_primary: bool,
) -> Dict[str, int]:
    order_index = {node.node_id: idx for idx, node in enumerate(ordered_nodes)}
    layers: Dict[str, int] = {node.node_id: 0 for node in ordered_nodes}
    outgoing: Dict[str, List[str]] = defaultdict(list)
    for edge in edges:
        outgoing[edge.source].append(edge.target)

    for node in ordered_nodes:
        current_layer = layers[node.node_id]
        for target in outgoing.get(node.node_id, []):
            if order_index.get(target, -1) <= order_index.get(node.node_id, -1):
                continue
            layers[target] = max(layers.get(target, 0), current_layer + 1)

    if not reversed_primary:
        return layers

    max_layer = max(layers.values(), default=0)
    return {node_id: max_layer - layer for node_id, layer in layers.items()}


def _render_edge_svg(*, edge: MermaidEdge, source: MermaidNode, target: MermaidNode, horizontal: bool) -> str:
    start_x, start_y, end_x, end_y = _edge_points(source=source, target=target)
    stroke_width = "2.4" if "=" in edge.style else "1.8"
    dash = ' stroke-dasharray="6 5"' if "." in edge.style else ""
    marker = ' marker-end="url(#arrow)"' if ">" in edge.style else ""
    stroke = "#8fd7ff"

    if horizontal and target.center_x <= source.center_x:
        ctrl_y = min(source.center_y, target.center_y) - 68.0
        path = (
            f'M {start_x:.1f} {start_y:.1f} '
            f'C {start_x - 34.0:.1f} {ctrl_y:.1f} {end_x + 34.0:.1f} {ctrl_y:.1f} {end_x:.1f} {end_y:.1f}'
        )
        return f'<path d="{path}" fill="none" stroke="{stroke}" stroke-width="{stroke_width}"{dash}{marker}/>'
    if (not horizontal) and target.center_y <= source.center_y:
        ctrl_x = min(source.center_x, target.center_x) - 94.0
        path = (
            f'M {start_x:.1f} {start_y:.1f} '
            f'C {ctrl_x:.1f} {start_y - 28.0:.1f} {ctrl_x:.1f} {end_y + 28.0:.1f} {end_x:.1f} {end_y:.1f}'
        )
        return f'<path d="{path}" fill="none" stroke="{stroke}" stroke-width="{stroke_width}"{dash}{marker}/>'
    return (
        f'<line x1="{start_x:.1f}" y1="{start_y:.1f}" x2="{end_x:.1f}" y2="{end_y:.1f}" '
        f'stroke="{stroke}" stroke-width="{stroke_width}"{dash}{marker}/>'
    )


def _render_node_svg(node: MermaidNode) -> str:
    x = node.center_x - (node.width / 2.0)
    y = node.center_y - (node.height / 2.0)
    body = ""
    if node.shape == "circle":
        body = (
            f'<ellipse cx="{node.center_x:.1f}" cy="{node.center_y:.1f}" rx="{node.width / 2.0:.1f}" '
            f'ry="{node.height / 2.0:.1f}" fill="#1b2330" stroke="#66c8ff" stroke-width="1.8"/>'
        )
    elif node.shape == "diamond":
        mid_x = node.center_x
        mid_y = node.center_y
        points = [
            f"{mid_x:.1f},{y:.1f}",
            f"{x + node.width:.1f},{mid_y:.1f}",
            f"{mid_x:.1f},{y + node.height:.1f}",
            f"{x:.1f},{mid_y:.1f}",
        ]
        body = f'<polygon points="{" ".join(points)}" fill="#1b2330" stroke="#66c8ff" stroke-width="1.8"/>'
    elif node.shape == "hex":
        inset = min(18.0, node.width * 0.16)
        points = [
            f"{x + inset:.1f},{y:.1f}",
            f"{x + node.width - inset:.1f},{y:.1f}",
            f"{x + node.width:.1f},{node.center_y:.1f}",
            f"{x + node.width - inset:.1f},{y + node.height:.1f}",
            f"{x + inset:.1f},{y + node.height:.1f}",
            f"{x:.1f},{node.center_y:.1f}",
        ]
        body = f'<polygon points="{" ".join(points)}" fill="#1b2330" stroke="#66c8ff" stroke-width="1.8"/>'
    else:
        radius = (node.height / 2.0) if node.shape == "stadium" else (18 if node.shape == "round" else 12)
        body = (
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{node.width:.1f}" height="{node.height:.1f}" '
            f'rx="{radius}" ry="{radius}" fill="#1b2330" stroke="#66c8ff" stroke-width="1.8"/>'
        )

    lines = _wrap_label_lines(node.label)
    text_spans: List[str] = []
    start_y = node.center_y - ((len(lines) - 1) * 9.0)
    for idx, line in enumerate(lines):
        y_pos = start_y + idx * 18.0
        safe_line = html.escape(line)
        text_spans.append(
            f'<tspan x="{node.center_x:.1f}" y="{y_pos:.1f}">{safe_line}</tspan>'
        )
    text = (
        f'<text text-anchor="middle" font-family="Helvetica Neue, Helvetica, Arial" font-size="14" '
        f'font-weight="600" fill="#edf6ff">{"".join(text_spans)}</text>'
    )
    return body + text


def _edge_points(*, source: MermaidNode, target: MermaidNode) -> tuple[float, float, float, float]:
    dx = target.center_x - source.center_x
    dy = target.center_y - source.center_y
    if abs(dx) >= abs(dy):
        sx = source.center_x + ((source.width / 2.0) if dx >= 0 else -(source.width / 2.0))
        sy = source.center_y
        tx = target.center_x - ((target.width / 2.0) if dx >= 0 else -(target.width / 2.0))
        ty = target.center_y
        return sx, sy, tx, ty
    sx = source.center_x
    sy = source.center_y + ((source.height / 2.0) if dy >= 0 else -(source.height / 2.0))
    tx = target.center_x
    ty = target.center_y - ((target.height / 2.0) if dy >= 0 else -(target.height / 2.0))
    return sx, sy, tx, ty


def _wrap_label_lines(text: str, *, metrics=None, max_width: int = _MERMAID_NODE_TEXT_MAX_WIDTH) -> List[str]:
    raw_lines = [part.strip() for part in _normalize_label(text).split("\n")] or [""]
    wrapped: List[str] = []
    for line in raw_lines:
        if metrics is not None:
            words = [piece for piece in line.split(" ") if piece]
            if not words:
                wrapped.append("")
                continue
            current = words[0]
            for word in words[1:]:
                candidate = f"{current} {word}".strip()
                if metrics.horizontalAdvance(candidate) <= max_width:
                    current = candidate
                    continue
                wrapped.append(current)
                current = word
            wrapped.append(current)
            continue
        pieces = textwrap.wrap(line, width=20, break_long_words=False, break_on_hyphens=False)
        wrapped.extend(pieces or [""])
    return wrapped or [""]


def _normalize_label(text: str) -> str:
    normalized = html.unescape(str(text or ""))
    normalized = normalized.replace("\\n", "\n")
    normalized = normalized.replace("<br/>", "\n").replace("<br />", "\n").replace("<br>", "\n")
    return normalized.strip() or "Node"


def _strip_comment(line: str) -> str:
    idx = line.find("%%")
    if idx < 0:
        return line
    return line[:idx]


def _skip_ws(text: str, pos: int) -> int:
    while pos < len(text) and text[pos].isspace():
        pos += 1
    return pos


def _sanitize_mermaid_line(line: str) -> str:
    return _ESCAPED_LINEBREAK_BETWEEN_TOKENS_RE.sub(" ", str(line or ""))


def _merge_wrapped_flowchart_lines(lines: List[str]) -> List[str]:
    merged: List[str] = []
    carry = ""
    carry_kind = ""
    for raw_line in lines:
        line = str(raw_line or "").rstrip()
        if not line.strip():
            continue
        if carry:
            separator = "\n" if carry_kind == "label" else " "
            candidate = f"{carry}{separator}{line.lstrip()}".strip()
        else:
            candidate = line.strip()
        continuation_kind = _line_needs_continuation(candidate)
        if continuation_kind:
            carry = candidate
            carry_kind = continuation_kind
            continue
        merged.append(candidate)
        carry = ""
        carry_kind = ""
    if carry:
        merged.append(carry)
    return merged


def _line_needs_continuation(line: str) -> str:
    stripped = _sanitize_mermaid_line(str(line or "")).rstrip()
    if not stripped:
        return ""
    if _open_shape_balance(stripped) > 0:
        return "label"
    if stripped.endswith("|"):
        return "token"
    if any(stripped.endswith(token) for token in ("-.->", "-->", "==>", "---", "--", "==")):
        return "token"
    return ""


def _open_shape_balance(text: str) -> int:
    balance = 0
    for char in str(text or ""):
        if char in "([{":
            balance += 1
        elif char in ")]}":
            balance -= 1
    return balance


def _svg_to_png_data_uri(svg: str) -> Optional[str]:
    if (
        not svg
        or QSvgRenderer is None
        or QByteArray is None
        or QImage is None
        or QPainter is None
        or QBuffer is None
        or QIODevice is None
    ):
        return None

    _ensure_qt_gui_application()
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    if not renderer.isValid():
        return None

    default_size = renderer.defaultSize()
    width = max(160, int(default_size.width()) if default_size.width() > 0 else 640)
    height = max(120, int(default_size.height()) if default_size.height() > 0 else 360)
    scale = 2
    image = QImage(width * scale, height * scale, QImage.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        painter.scale(scale, scale)
        renderer.render(painter)
    finally:
        painter.end()

    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    try:
        if not image.save(buffer, "PNG"):
            return None
        encoded = bytes(buffer.data().toBase64()).decode("ascii")
    finally:
        buffer.close()
    return f"data:image/png;base64,{encoded}"


def _layout_to_png_data_uri(layout: MermaidLayout) -> Optional[str]:
    if (
        QImage is None
        or QPainter is None
        or QBuffer is None
        or QIODevice is None
        or QColor is None
        or QPen is None
        or QBrush is None
        or QLinearGradient is None
        or QPainterPath is None
        or Qt is None
    ):
        return None

    _ensure_qt_gui_application()
    width = max(160, int(math.ceil(layout.total_width)))
    height = max(120, int(math.ceil(layout.total_height)))
    scale = 2
    image = QImage(width * scale, height * scale, QImage.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.scale(scale, scale)

        panel_path = QPainterPath()
        panel_path.addRoundedRect(0.5, 0.5, float(width - 1), float(height - 1), 16.0, 16.0)
        panel_gradient = QLinearGradient(0.0, 0.0, float(width), float(height))
        panel_gradient.setColorAt(0.0, QColor("#151b24"))
        panel_gradient.setColorAt(1.0, QColor("#10161f"))
        painter.fillPath(panel_path, QBrush(panel_gradient))
        painter.setPen(QPen(QColor(255, 255, 255, 20), 1.0))
        painter.drawPath(panel_path)

        for edge in layout.edges:
            source_node = layout.nodes.get(edge.source)
            target_node = layout.nodes.get(edge.target)
            if source_node is None or target_node is None:
                continue
            _draw_edge(painter, edge=edge, source=source_node, target=target_node, horizontal=layout.horizontal)

        for node in layout.ordered_nodes:
            _draw_node(painter, node)
    finally:
        painter.end()

    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    try:
        if not image.save(buffer, "PNG"):
            return None
        encoded = bytes(buffer.data().toBase64()).decode("ascii")
    finally:
        buffer.close()
    return f"data:image/png;base64,{encoded}"


def _draw_edge(painter: QPainter, *, edge: MermaidEdge, source: MermaidNode, target: MermaidNode, horizontal: bool) -> None:
    if QPen is None or QColor is None or QPainterPath is None or Qt is None:
        return
    start_x, start_y, end_x, end_y = _edge_points(source=source, target=target)
    stroke_width = 2.4 if "=" in edge.style else 1.8
    pen = QPen(QColor("#8fd7ff"), stroke_width)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    if "." in edge.style:
        pen.setDashPattern([6.0, 5.0])
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)

    arrow_direction = QPointF(end_x - start_x, end_y - start_y) if QPointF is not None else None
    if horizontal and target.center_x <= source.center_x:
        ctrl_y = min(source.center_y, target.center_y) - 68.0
        path = QPainterPath(QPointF(start_x, start_y))
        ctrl1 = QPointF(start_x - 34.0, ctrl_y)
        ctrl2 = QPointF(end_x + 34.0, ctrl_y)
        path.cubicTo(ctrl1, ctrl2, QPointF(end_x, end_y))
        painter.drawPath(path)
        arrow_direction = QPointF(end_x - ctrl2.x(), end_y - ctrl2.y())
    elif (not horizontal) and target.center_y <= source.center_y:
        ctrl_x = min(source.center_x, target.center_x) - 94.0
        path = QPainterPath(QPointF(start_x, start_y))
        ctrl1 = QPointF(ctrl_x, start_y - 28.0)
        ctrl2 = QPointF(ctrl_x, end_y + 28.0)
        path.cubicTo(ctrl1, ctrl2, QPointF(end_x, end_y))
        painter.drawPath(path)
        arrow_direction = QPointF(end_x - ctrl2.x(), end_y - ctrl2.y())
    else:
        painter.drawLine(QPointF(start_x, start_y), QPointF(end_x, end_y))

    if ">" in edge.style and arrow_direction is not None:
        _draw_arrowhead(painter, QPointF(end_x, end_y), arrow_direction)


def _draw_arrowhead(painter: QPainter, tip: QPointF, direction: QPointF) -> None:
    if QPolygonF is None or QColor is None:
        return
    length = math.hypot(direction.x(), direction.y())
    if length <= 0.001:
        return
    dx = direction.x() / length
    dy = direction.y() / length
    size = 9.0
    width = 5.5
    base_x = tip.x() - dx * size
    base_y = tip.y() - dy * size
    left = QPointF(base_x - dy * width, base_y + dx * width)
    right = QPointF(base_x + dy * width, base_y - dx * width)
    painter.save()
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#8fd7ff"))
    painter.drawPolygon(QPolygonF([tip, left, right]))
    painter.restore()


def _draw_node(painter: QPainter, node: MermaidNode) -> None:
    if QPen is None or QColor is None or QBrush is None or QFont is None or Qt is None:
        return
    x = node.center_x - (node.width / 2.0)
    y = node.center_y - (node.height / 2.0)
    painter.save()
    painter.setPen(QPen(QColor("#66c8ff"), 1.8))
    painter.setBrush(QBrush(QColor("#1b2330")))

    if node.shape == "circle":
        painter.drawEllipse(QRectF(x, y, node.width, node.height))
    elif node.shape == "diamond":
        painter.drawPolygon(
            QPolygonF(
                [
                    QPointF(node.center_x, y),
                    QPointF(x + node.width, node.center_y),
                    QPointF(node.center_x, y + node.height),
                    QPointF(x, node.center_y),
                ]
            )
        )
    elif node.shape == "hex":
        inset = min(18.0, node.width * 0.16)
        painter.drawPolygon(
            QPolygonF(
                [
                    QPointF(x + inset, y),
                    QPointF(x + node.width - inset, y),
                    QPointF(x + node.width, node.center_y),
                    QPointF(x + node.width - inset, y + node.height),
                    QPointF(x + inset, y + node.height),
                    QPointF(x, node.center_y),
                ]
            )
        )
    else:
        radius = (node.height / 2.0) if node.shape == "stadium" else (18.0 if node.shape == "round" else 12.0)
        painter.drawRoundedRect(QRectF(x, y, node.width, node.height), radius, radius)

    font = _node_text_font()
    if font is None:
        painter.restore()
        return
    painter.setFont(font)
    painter.setPen(QPen(QColor("#edf6ff"), 1.0))
    text_rect = QRectF(
        x + 14.0,
        y + 8.0,
        max(1.0, node.width - 28.0),
        max(1.0, node.height - 16.0),
    )
    painter.drawText(
        text_rect,
        int(Qt.AlignCenter | Qt.TextWordWrap),
        node.label,
    )
    painter.restore()


def _node_text_font() -> Optional[QFont]:
    if QFont is None:
        return None
    font = QFont()
    font.setPointSize(13)
    font.setBold(True)
    return font


def _ensure_qt_gui_application() -> None:
    global _QT_MERMAID_APP
    if QGuiApplication is None:
        return
    existing = QGuiApplication.instance()
    if existing is not None:
        return
    if _QT_MERMAID_APP is not None:
        return
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app_cls = QApplication if QApplication is not None else QGuiApplication
    _QT_MERMAID_APP = app_cls(["abstractassistant-mermaid", "-platform", "offscreen"])
