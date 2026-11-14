"""A fake gateway side for the desktop `@` mention UI (no network, no real worker).

``MentionController`` is the smoke tests' stub controller with a transcript, a `GET /entities`
answer and a worker factory; ``FakeMentionWorker`` speaks the worker API of
abstractassistant/core/mentions.py ("The worker API": `set_mentions`, `mention_asked`,
`mention_answered`, `mention_skipped`, `mentions_done`) and is driven by the test, step by step.
Used by test_mentions_desktop_ui.py and the screenshot harness.
"""

from __future__ import annotations

import os
import runpy
from pathlib import Path
from typing import Any, Dict, List, Optional

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYSTRAY_BACKEND", "dummy")

from PyQt5.QtCore import QObject, pyqtSignal

from abstractassistant.core.mentions import (
    Mention,
    MentionAnswer,
    MentionDelivery,
    MentionsSummary,
    mention_answer_metadata,
)

SMOKE = runpy.run_path(str(Path(__file__).with_name("test_palette_smoke.py")))

ENTITIES = {
    "entities": [
        {"slug": "castor", "name": "Castor", "identity": {"avatar": {"style": "halo", "color": "#c084fc"}}, "state": {"state": "awake", "mode": "visiting"}},
        {"slug": "pollux", "name": "Pollux", "identity": {"avatar": {"style": "watch-nebula", "color": "#34d399"}}, "state": {"state": "resting"}},
        {"slug": "aletheia", "name": "Aletheia", "identity": {"avatar": {"style": None, "color": "#f59e0b"}}, "state": {}},
    ]
}


class FakeGateway:
    def __init__(self) -> None:
        self.entity_reads = 0

    def list_entities(self) -> Dict[str, Any]:
        self.entity_reads += 1
        return ENTITIES


class FakeMentionWorker(QObject):
    """The palette's worker, minus the gateway: the test emits what the real one would."""

    event_emitted = pyqtSignal(object)
    error_occurred = pyqtSignal(str)
    warning_occurred = pyqtSignal(str)
    finished = pyqtSignal()
    mention_asked = pyqtSignal(object)
    mention_answered = pyqtSignal(object, object)
    mention_skipped = pyqtSignal(object, str)
    mentions_done = pyqtSignal(object)

    def __init__(self, controller: "MentionController", kwargs: Dict[str, Any]) -> None:
        super().__init__()
        self.controller = controller
        self.kwargs = kwargs
        self.mentions: tuple = ()
        self.resend = None
        self.running = False
        self.interrupted = False

    def set_mentions(self, mentions, *, resend=None) -> None:
        for chip in mentions:
            assert isinstance(chip, Mention), chip
        self.mentions = tuple(mentions)
        self.resend = resend

    def start(self) -> None:
        self.running = True

    def isRunning(self) -> bool:  # noqa: N802 - QThread naming
        return self.running

    def requestInterruption(self) -> None:  # noqa: N802
        self.interrupted = True

    def status(self, status: str) -> None:
        self.event_emitted.emit({"type": "status", "status": status})

    def entity(self, slug: str) -> Mention:
        return next(m for m in self.mentions if m.id == slug)

    # -- what the real worker does, one step at a time -------------------------------------

    def not_addressed(self, turn_id: str = "turn-1") -> None:
        self.event_emitted.emit({"type": "agent_not_addressed", "turn_id": turn_id})
        self.event_emitted.emit({"type": "status", "status": "thinking"})

    def ask(self, slug: str) -> None:
        self.mention_asked.emit(self.entity(slug))

    def answer(self, slug: str, reply: str, *, run_id: str = "") -> MentionAnswer:
        mention = self.entity(slug)
        look = next((e["identity"]["avatar"] for e in ENTITIES["entities"] if e["slug"] == slug), None)
        answer = MentionAnswer(
            run_id=run_id or f"run-{slug}",
            reply=reply,
            mention_index=mention.index,
            author={"kind": "entity", "name": mention.name, "entity_id": f"ent-{slug}", "identity_ref": f"entity:{slug}#1", "avatar": look},
        )
        # The worker appends the answer row (with its author) BEFORE it signals.
        self.controller.append_message("assistant", reply, metadata=mention_answer_metadata(answer, mention))
        self.mention_answered.emit(mention, answer)
        return answer

    def skip(self, slug: str, sentence: str) -> None:
        self.mention_skipped.emit(self.entity(slug), sentence)

    def done(self, *, text: str, agent_addressed: bool = False, notes=(), stopped: Optional[str] = None, unsent=()) -> MentionsSummary:
        outcome = MentionDelivery(message="msg-1", notes=list(notes), stopped=stopped, unsent=list(unsent))
        summary = MentionsSummary.of(outcome, session_id=self.controller.active_session_id, text=text, turn_id="turn-1", agent_addressed=agent_addressed)
        self.mentions_done.emit(summary)
        return summary

    def finish(self) -> None:
        self.event_emitted.emit({"type": "status", "status": "completed"})
        self.running = False
        self.finished.emit()


class MentionController(SMOKE["_Controller"]):
    """The smoke controller with a transcript, the entity list and the fake worker."""

    def __init__(self) -> None:
        super().__init__()
        self.gateway = FakeGateway()
        self.messages: List[Dict[str, Any]] = []
        self.workers: List[FakeMentionWorker] = []
        self._ids = 0
        # The chat's previous agent run (an entities-only message starts none) and every run
        # command the palette sends, recorded.
        self.previous_run = ""
        self.commands: List[tuple] = []

    def session_messages(self) -> list:
        return list(self.messages)

    def append_message(self, role: str, content: str, metadata=None) -> str:
        self._ids += 1
        row: Dict[str, Any] = {"role": role, "content": content, "ts": "2026-11-11T10:00:00+00:00", "message_id": f"m{self._ids}"}
        if metadata:
            row["metadata"] = dict(metadata)
        self.messages.append(row)
        return row["message_id"]

    def append_user_message(self, content: str, metadata=None) -> str:
        return self.append_message("user", content, metadata)

    def build_chat_worker(self, **kwargs):
        self.built.append(dict(kwargs))
        worker = FakeMentionWorker(self, kwargs)
        self.workers.append(worker)
        return worker

    def latest_image_artifact(self):
        return None

    def last_run_id(self) -> str:
        return self.previous_run

    def inject_guidance(self, run_id: str, text: str) -> bool:
        self.commands.append(("steer", run_id, text))
        return True

    def cancel_run(self, run_id: str) -> bool:
        self.commands.append(("cancel", run_id))
        return True

    def pause_run(self, run_id: str) -> bool:
        self.commands.append(("pause", run_id))
        return True

    def resume_run(self, run_id: str) -> bool:
        self.commands.append(("resume", run_id))
        return True

    def build_attach_worker(self, run_id: str):
        worker = FakeMentionWorker(self, {"attach": run_id})
        self.workers.append(worker)
        return worker
