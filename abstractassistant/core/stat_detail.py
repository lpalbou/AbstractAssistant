"""Structured detail for the message footer's stat chips (Qt-free).

The desktop mirror of AbstractUIC panel-chat ``stat_detail.tsx``: a chip's
detail is DATA — a titled card ("Tokens · 7,586 total") with sections
("Usage · 3 model calls": Input / Output / Total; "Prompt cache"), optional
notes and a footnote ("From the run ledger; summed across this turn and its
child runs.") — built here and rendered by one widget
(`ui.stat_detail.StatDetailPopup`) for every chip. It replaces the plain grey
multi-line tooltips the chips carried.

Honesty rule, as the kit's: a value the ledger did not report reads
"not reported" — never 0, which would be a claim.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

NOT_REPORTED = "not reported"
LEDGER_FOOTNOTE = "From the run ledger; summed across this turn and its child runs."


@dataclass(frozen=True)
class StatRow:
    label: str
    value: str
    hint: str = ""


@dataclass(frozen=True)
class StatSection:
    heading: str
    rows: Tuple[StatRow, ...] = ()
    note: str = ""


@dataclass(frozen=True)
class StatDetail:
    kind: str  # tokens | time | tools | files | model | cache
    title: str
    headline: str
    sections: Tuple[StatSection, ...] = ()
    footer: Tuple[str, ...] = field(default_factory=tuple)


def _n(value: Optional[int]) -> str:
    return NOT_REPORTED if value is None else f"{int(value):,}"


def _plural(count: int, one: str, many: str = "") -> str:
    return f"{count:,} {one if count == 1 else (many or one + 's')}"


def _short_model(model: str) -> str:
    clean = str(model or "").split("#")[0].rstrip("/")
    return clean[clean.rfind("/") + 1:] or str(model or "")


def ledger_footer(provider: str = "", model: str = "") -> Tuple[str, ...]:
    lines: List[str] = []
    if model or provider:
        lines.append(" · ".join(part for part in (_short_model(model) if model else "", provider) if part))
    lines.append(LEDGER_FOOTNOTE)
    return tuple(lines)


def _cache_section(cache: Optional[Dict[str, Any]], llm_calls: Optional[int]) -> Optional[StatSection]:
    if isinstance(cache, dict) and cache.get("measured_calls"):
        cached = int(cache.get("cached_tokens") or 0)
        new = int(cache.get("new_tokens") or 0)
        measured = int(cache.get("measured_calls") or 0)
        share = f" ({cached / (cached + new):.0%})" if cached + new else ""
        rows = [StatRow("Reused from cache", f"{cached:,}{share}"), StatRow("Newly processed", f"{new:,}")]
        if llm_calls is not None and measured != llm_calls:
            rows.append(StatRow("Measured on", f"{measured} of {llm_calls} calls"))
        return StatSection(
            "Prompt cache",
            tuple(rows),
            note="Newly processed includes uncached history and tool results, not only your new message.",
        )
    if llm_calls is None or llm_calls > 0:
        return StatSection("Prompt cache", (StatRow("Cache reuse", NOT_REPORTED),))
    return None


def tokens_detail(
    usage: Dict[str, int],
    *,
    llm_calls: Optional[int],
    cache: Optional[Dict[str, Any]] = None,
    split_known: bool = True,
    provider: str = "",
    model: str = "",
) -> StatDetail:
    """The Tokens card: "Usage · N model calls" (Input / Output / Total) and
    "Prompt cache" (reuse, or "not reported" — never assumed zero)."""
    total = usage.get("total_tokens")
    rows = (
        StatRow("Input", _n(usage.get("input_tokens") if split_known else None)),
        StatRow("Output", _n(usage.get("output_tokens") if split_known else None)),
        StatRow("Total", _n(total)),
    )
    heading = f"Usage · {_plural(int(llm_calls), 'model call')}" if llm_calls else "Usage"
    note = ""
    if not split_known:
        note = "This provider did not report the input/output split."
    elif llm_calls and llm_calls > 1:
        note = "Each call re-sends the conversation, so the input total counts the context once per call."
    sections: List[StatSection] = [StatSection(heading, rows, note=note)]
    cache_section = _cache_section(cache, llm_calls)
    if cache_section is not None:
        sections.append(cache_section)
    return StatDetail(
        kind="tokens",
        title="Tokens",
        headline=NOT_REPORTED if total is None else f"{int(total):,} total",
        sections=tuple(sections),
        footer=ledger_footer(provider, model),
    )


def cache_detail(cache: Dict[str, Any], *, llm_calls: Optional[int], headline: str, provider: str = "", model: str = "") -> StatDetail:
    section = _cache_section(cache, llm_calls)
    return StatDetail(
        kind="cache",
        title="Prompt cache",
        headline=headline,
        sections=(section,) if section is not None else (),
        footer=ledger_footer(provider, model),
    )


def time_detail(duration_ms: Optional[float], *, label: str, provider: str = "", model: str = "") -> StatDetail:
    return StatDetail(
        kind="time",
        title="Time",
        headline=f"{label} wall clock" if label else NOT_REPORTED,
        sections=(StatSection("Turn", (StatRow("Wall clock", label or NOT_REPORTED),)),),
        footer=ledger_footer(provider, model),
    )


def tools_detail(
    count: int,
    calls: Sequence[Tuple[str, str, bool]],
    *,
    clickable: bool,
    max_rows: int = 12,
) -> StatDetail:
    """``calls``: (tool name, reason in words, failed) per executed call."""
    if count <= 0:
        return StatDetail(
            kind="tools",
            title="Tools",
            headline="none",
            sections=(StatSection("Outcome", (StatRow("Tools called", "none"),)),),
            footer=(LEDGER_FOOTNOTE,),
        )
    failed = sum(1 for _name, _reason, bad in calls if bad)
    sections: List[StatSection] = [
        StatSection("Outcome", (StatRow("Succeeded", f"{max(0, count - failed):,}"), StatRow("Failed", f"{failed:,}")))
    ]
    if calls:
        rows = [StatRow(name, reason, "failed" if bad else "") for name, reason, bad in calls[:max_rows]]
        more = len(calls) - len(rows)
        sections.append(StatSection("Calls", tuple(rows), note=f"… and {more} more" if more > 0 else ""))
    else:
        sections.append(StatSection("Calls", note="Details are not attached to this message; click to load them from the run ledger."))
    footer = [LEDGER_FOOTNOTE]
    if clickable:
        footer.append("Click for the full list.")
    return StatDetail(
        kind="tools",
        title="Tools",
        headline=f"{_plural(count, 'call')}{f' · {failed} failed' if failed else ''}",
        sections=tuple(sections),
        footer=tuple(footer),
    )


def files_detail(changes: Sequence[Tuple[str, str]], *, distinct: int, clickable: bool, max_rows: int = 12) -> StatDetail:
    """``changes``: (action in words, file label) per operation."""
    if not changes:
        return StatDetail(
            kind="files",
            title="Files",
            headline="none",
            sections=(StatSection("Changes", (StatRow("Files changed", "none"),), note="No files were created, modified, moved or deleted."),),
            footer=(LEDGER_FOOTNOTE,),
        )
    rows = [StatRow(action, label) for action, label in changes[:max_rows]]
    more = len(changes) - len(rows)
    footer = [LEDGER_FOOTNOTE]
    if clickable:
        footer.append("Click for the full list.")
    return StatDetail(
        kind="files",
        title="Files",
        headline=_plural(distinct, "file"),
        sections=(StatSection("Changes", tuple(rows), note=f"… and {more} more" if more > 0 else ""),),
        footer=tuple(footer),
    )


def model_detail(provider: str, model: str) -> StatDetail:
    rows = []
    if model:
        rows.append(StatRow("Model", model))
    if provider:
        rows.append(StatRow("Provider", provider))
    return StatDetail(
        kind="model",
        title="Model",
        headline=_short_model(model) if model else provider,
        sections=(StatSection("Used for this answer", tuple(rows)),),
        footer=(),
    )


def stat_detail_text(detail: StatDetail) -> str:
    """Plain text (copy, accessibility, tests): the card read top to bottom."""
    lines = [f"{detail.title} · {detail.headline}"]
    for section in detail.sections:
        lines.extend(["", section.heading])
        for row in section.rows:
            lines.append(f"  {row.label}: {row.value}{f' ({row.hint})' if row.hint else ''}")
        if section.note:
            lines.append(f"  {section.note}")
    if detail.footer:
        lines.extend(["", *detail.footer])
    return "\n".join(lines)


__all__ = [
    "LEDGER_FOOTNOTE",
    "NOT_REPORTED",
    "StatDetail",
    "StatRow",
    "StatSection",
    "cache_detail",
    "files_detail",
    "ledger_footer",
    "model_detail",
    "stat_detail_text",
    "time_detail",
    "tokens_detail",
    "tools_detail",
]
