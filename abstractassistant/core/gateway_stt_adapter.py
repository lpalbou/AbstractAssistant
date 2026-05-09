"""
Gateway-backed STT adapter for AbstractAssistant.

Implements the AbstractVoice STTAdapter interface, sending audio to the
gateway /audio/transcribe endpoint instead of running a local whisper model.
This allows the VoiceRecognizer (mic capture + VAD) to run locally while
the heavy transcription happens on the gateway.
"""

from __future__ import annotations

import io
import tempfile
import uuid
import wave
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from abstractvoice.adapters.base import STTAdapter


class GatewaySTTAdapter(STTAdapter):
    """STT adapter that delegates transcription to AbstractGateway."""

    def __init__(
        self,
        *,
        gateway_client_fn: Callable,
        session_id_fn: Callable,
        run_id_fn: Callable,
        content_type_fn: Optional[Callable[[], str]] = None,
        max_upload_bytes_fn: Optional[Callable[[], int]] = None,
    ) -> None:
        self._gateway_client_fn = gateway_client_fn
        self._session_id_fn = session_id_fn
        self._run_id_fn = run_id_fn
        self._content_type_fn = content_type_fn
        self._max_upload_bytes_fn = max_upload_bytes_fn

    def transcribe(self, audio_path: str, language: Optional[str] = None, **kwargs) -> str:
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()
        return self.transcribe_from_bytes(audio_bytes, language=language)

    def transcribe_from_bytes(self, audio_bytes: bytes, language: Optional[str] = None, **kwargs) -> str:
        gw = self._gateway_client_fn()
        run_id = str(self._run_id_fn() or "").strip()
        sid = str(self._session_id_fn() or "").strip()
        if not run_id or not gw:
            return ""

        content_type = "audio/wav"
        if callable(self._content_type_fn):
            try:
                content_type = str(self._content_type_fn() or "").strip()
            except Exception:
                content_type = ""
        if not content_type:
            return ""

        max_upload_bytes = 0
        if callable(self._max_upload_bytes_fn):
            try:
                max_upload_bytes = int(self._max_upload_bytes_fn() or 0)
            except Exception:
                max_upload_bytes = 0
        if max_upload_bytes > 0 and len(audio_bytes) > max_upload_bytes:
            raise RuntimeError(f"Gateway STT audio exceeds upload limit ({len(audio_bytes)} > {max_upload_bytes} bytes)")

        old_timeout = None
        try:
            cfg = getattr(gw, "_cfg", None)
            if cfg is not None:
                old_timeout = float(getattr(cfg, "timeout_s", 0) or 0)
                if old_timeout and old_timeout < 120.0:
                    object.__setattr__(cfg, "timeout_s", 120.0)
        except Exception:
            old_timeout = None

        tmp = None
        try:
            tmp = Path(tempfile.mktemp(suffix=".wav", prefix="gw_stt_"))
            tmp.write_bytes(audio_bytes)
            attachment = gw.attachments_upload(
                session_id=sid,
                file_path=str(tmp),
                filename=tmp.name,
                content_type=content_type,
            )
            audio_ref = attachment
            if isinstance(attachment, dict) and isinstance(attachment.get("attachment"), dict):
                audio_ref = attachment["attachment"]
            if not isinstance(audio_ref, dict) or not str(audio_ref.get("$artifact") or "").strip():
                raise RuntimeError("Gateway STT: upload returned no artifact ref")
            res = gw.audio_transcribe(
                run_id=run_id,
                audio_artifact=audio_ref,
                request_id=str(uuid.uuid4()),
                language=str(language) if isinstance(language, str) and language.strip() else None,
            )
            return str(res.get("text") or "").strip() if isinstance(res, dict) else ""
        finally:
            try:
                if tmp is not None and tmp.exists():
                    tmp.unlink()
            except Exception:
                pass
            try:
                cfg = getattr(gw, "_cfg", None)
                if cfg is not None and old_timeout is not None:
                    object.__setattr__(cfg, "timeout_s", old_timeout)
            except Exception:
                pass

    def transcribe_from_array(self, audio_array: np.ndarray, sample_rate: int,
                              language: Optional[str] = None, **kwargs) -> str:
        buf = io.BytesIO()
        pcm = (audio_array * 32768.0).clip(-32768, 32767).astype(np.int16)
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm.tobytes())
        return self.transcribe_from_bytes(buf.getvalue(), language=language)

    def set_language(self, language: str) -> bool:
        return True

    def get_supported_languages(self) -> list[str]:
        return []

    def is_available(self) -> bool:
        try:
            gw = self._gateway_client_fn()
            return gw is not None
        except Exception:
            return False
