"""Create a voice through the gateway's voice library (AbstractGateway 0.16.0).

Two ways, one dialog:

- **From a description**: ``POST /voice/design`` (Qwen3-TTS renders a reference from the words and
  stores it as a voice);
- **From a recording**: ``POST /voice/clones`` with an audio file.

With user accounts on, the voice is the person's own (their voice store on the gateway); on a
gateway with one shared store, only an administrator may create voices and the gateway's 403
sentence is shown. The call runs off the Qt thread; the dialog closes with the new voice's id and
engine so the route editor can select it. Cancel cancels: a result that arrives after it is dropped.

A recording's language is detected by the gateway unless chosen (no ``language`` sent); a
description keeps one (design needs it). When the route's selected provider is a cloning engine,
the recording is cloned with it (``provider``); otherwise the gateway's default cloning engine.
"""
from __future__ import annotations

import threading
from typing import Any, Dict, Optional

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

# Engines that clone a voice from a recording (AbstractVoice); another selected provider is not sent.
CLONING_ENGINES = ("qwen3-tts", "omnivoice", "f5_tts", "chroma", "audiodit")

DETECT_LANGUAGE = "Detect from the recording"

LANGUAGES = [
    ("en", "English"), ("fr", "French"), ("de", "German"), ("es", "Spanish"), ("it", "Italian"),
    ("pt", "Portuguese"), ("ru", "Russian"), ("zh", "Chinese"), ("ja", "Japanese"), ("ko", "Korean"),
]


def _language_combo(default: str = "en", *, detect: bool = False) -> QComboBox:
    combo = QComboBox()
    if detect:
        combo.addItem(DETECT_LANGUAGE, "")
    for code, label in LANGUAGES:
        combo.addItem(label, code)
    idx = combo.findData(default)
    combo.setCurrentIndex(idx if idx >= 0 else 0)
    return combo


class CreateVoiceDialog(QDialog):
    """Ask for a description or a recording, create the voice on the gateway, report the result."""

    _finished = pyqtSignal(object)  # {"ok": True, "voice_id", "name", "engine"} | {"ok": False, "error"}

    def __init__(
        self, controller: Any, parent: Optional[QWidget] = None, *, language: str = "en", provider: str = ""
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        selected = str(provider or "").strip().lower()
        self._clone_provider = selected if selected in CLONING_ENGINES else ""
        self._cancelled = False
        self.result_voice: Dict[str, Any] = {}
        self.setWindowTitle("Create a voice")
        self.setModal(True)

        root = QVBoxLayout(self)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs)

        design = QWidget()
        design_form = QFormLayout(design)
        self.description = QPlainTextEdit()
        self.description.setPlaceholderText("A calm, warm adult female voice with a slight British accent, speaking slowly.")
        self.description.setFixedHeight(88)
        design_form.addRow("Describe the voice", self.description)
        self.design_name = QLineEdit()
        self.design_name.setPlaceholderText("Calm narrator")
        design_form.addRow("Name", self.design_name)
        self.design_language = _language_combo(language)
        design_form.addRow("Language", self.design_language)
        self.tabs.addTab(design, "From a description")

        recording = QWidget()
        recording_form = QFormLayout(recording)
        file_row = QHBoxLayout()
        self.file_path = QLineEdit()
        self.file_path.setPlaceholderText("A WAV, FLAC or OGG recording of 5 to 20 seconds")
        browse = QPushButton("Choose…")
        browse.clicked.connect(self._choose_file)
        file_row.addWidget(self.file_path, 1)
        file_row.addWidget(browse)
        recording_form.addRow("Recording", file_row)
        self.transcript = QLineEdit()
        self.transcript.setPlaceholderText("Optional: what the recording says")
        recording_form.addRow("Transcript", self.transcript)
        self.clone_name = QLineEdit()
        self.clone_name.setPlaceholderText("My voice")
        recording_form.addRow("Name", self.clone_name)
        self.clone_language = _language_combo("", detect=True)
        recording_form.addRow("Language", self.clone_language)
        self.tabs.addTab(recording, "From a recording")

        self.note = QLabel("")
        self.note.setWordWrap(True)
        root.addWidget(self.note)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        self.create_button = QPushButton("Create voice")
        self.create_button.setDefault(True)
        self.create_button.clicked.connect(self._create)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.create_button)
        root.addLayout(buttons)
        self._finished.connect(self._on_finished)

    def _choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose a recording", "", "Audio (*.wav *.flac *.ogg *.mp3 *.m4a)")
        if path:
            self.file_path.setText(path)

    def request(self) -> Dict[str, Any]:
        """What the current tab asks for (also used by tests)."""
        if self.tabs.currentIndex() == 0:
            return {
                "mode": "design",
                "description": self.description.toPlainText().strip(),
                "name": self.design_name.text().strip() or None,
                "language": self.design_language.currentData(),
            }
        return {
            "mode": "clone",
            "file_path": self.file_path.text().strip(),
            "reference_text": self.transcript.text().strip() or None,
            "name": self.clone_name.text().strip() or None,
            "language": self.clone_language.currentData() or None,
        }

    def _create(self) -> None:
        req = self.request()
        if req["mode"] == "design" and not req["description"]:
            self.note.setText("Describe the voice first.")
            return
        if req["mode"] == "clone" and not req["file_path"]:
            self.note.setText("Choose a recording first.")
            return
        self.create_button.setEnabled(False)
        self.note.setText(
            "Creating the voice from your description… this takes a few seconds to a minute."
            if req["mode"] == "design"
            else "Cloning the voice from your recording…"
        )

        def work() -> None:
            try:
                if req["mode"] == "design":
                    out = self._controller.design_voice(description=req["description"], name=req["name"], language=req["language"])
                else:
                    kwargs: Dict[str, Any] = {
                        "file_path": req["file_path"],
                        "name": req["name"],
                        "language": req["language"],
                        "reference_text": req["reference_text"],
                    }
                    if self._clone_provider:
                        kwargs["provider"] = self._clone_provider
                    out = self._controller.clone_voice(**kwargs)
                result = {"ok": True, **dict(out or {})}
                if not result.get("voice_id"):
                    result = {"ok": False, "error": "the gateway answered without a voice id"}
            except Exception as exc:  # the gateway's sentence (403 shared store, 501 engine missing, …)
                result = {"ok": False, "error": str(exc)}
            try:
                self._finished.emit(result)
            except RuntimeError:
                pass  # dialog closed while the call was in flight

        threading.Thread(target=work, name="assistant-create-voice", daemon=True).start()

    def reject(self) -> None:
        # Cancel cancels: the call may still answer, but nothing is accepted after this.
        self._cancelled = True
        super().reject()

    def _on_finished(self, result: Dict[str, Any]) -> None:
        if self._cancelled:
            return
        self.create_button.setEnabled(True)
        if not result.get("ok"):
            self.note.setText(f"The voice was not created: {str(result.get('error') or 'unknown error').rstrip('.')}.")
            return
        self.result_voice = {
            "voice_id": str(result.get("voice_id")),
            "name": str(result.get("name") or result.get("voice_id")),
            "engine": str(result.get("engine") or ("qwen3-tts" if self.tabs.currentIndex() == 0 else "")),
        }
        self.accept()
