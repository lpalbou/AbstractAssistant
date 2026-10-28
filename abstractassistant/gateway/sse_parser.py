"""
Minimal Server-Sent Events (SSE) parser for gateway ledger streaming.

Ported from the `abstractcode/web` thin-client SSE parsing approach.
"""

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class SseEvent:
    """Parsed SSE event (event name + data payload)."""

    event: str
    data: str
    # The frame's `id:` line (the replay view stream's cursor token); "" when absent.
    id: str = ""


class SseParser:
    """Incremental SSE parser that accepts text chunks."""

    def __init__(self) -> None:
        self._buffer = ""
        self._event_type = ""
        self._data_lines: List[str] = []
        self._id = ""

    def push(self, text: str) -> List[SseEvent]:
        """Push a text chunk into the parser and return any completed events."""
        if not text:
            return []
        self._buffer += text
        events: List[SseEvent] = []

        while True:
            if "\n" not in self._buffer:
                break
            line, rest = self._buffer.split("\n", 1)
            self._buffer = rest
            line = line.rstrip("\r")

            if not line:
                if self._data_lines or self._event_type:
                    event_type = self._event_type or "message"
                    data = "\n".join(self._data_lines)
                    events.append(SseEvent(event=event_type, data=data, id=self._id))
                self._event_type = ""
                self._data_lines = []
                self._id = ""
                continue

            if line.startswith(":"):
                continue  # comment line

            if line.startswith("event:"):
                self._event_type = line[len("event:") :].strip()
                continue

            if line.startswith("data:"):
                self._data_lines.append(line[len("data:") :].lstrip())
                continue

            if line.startswith("id:"):
                self._id = line[len("id:") :].strip()
                continue

            if line.startswith("retry:"):
                continue

        return events
