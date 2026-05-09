"""
Gateway HTTP client for AbstractAssistant (thin-client mode).

This mirrors the `abstractcode/web` GatewayClient and exposes the same API
surface so the tray UI can drive runs via the gateway control plane.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import mimetypes
import os
import socket
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlencode
import urllib.error
import urllib.request
import urllib.response
import warnings

from .sse_parser import SseParser
from .types import LedgerStreamEvent


@dataclass(frozen=True)
class GatewayClientConfig:
    """Configuration for gateway HTTP client."""

    base_url: str
    auth_token: str = ""
    timeout_s: float = 30.0


class GatewayHttpError(RuntimeError):
    """HTTP error returned by the gateway."""

    def __init__(self, message: str, *, status: int, retry_after_s: Optional[float] = None, body_text: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.retry_after_s = retry_after_s
        self.body_text = body_text


class GatewayStreamIdle(RuntimeError):
    """SSE ledger stream idle timeout (client reconnect)."""


def _join(base_url: str, path: str) -> str:
    base = str(base_url or "").strip().rstrip("/")
    if not base:
        raise ValueError("Gateway base_url is required")
    p = str(path or "").strip()
    if not p.startswith("/"):
        p = "/" + p
    return f"{base}{p}"


def _auth_headers(token: str | None) -> Dict[str, str]:
    t = str(token or "").strip()
    return {"Authorization": f"Bearer {t}"} if t else {}


def _retry_after_s(headers: Dict[str, str]) -> Optional[float]:
    lowered = {str(k).lower(): str(v) for k, v in headers.items()}
    ra = lowered.get("retry-after")
    if not ra:
        return None
    try:
        n = float(ra)
    except Exception:
        return None
    return n if n > 0 else None


def _decode_bytes(raw: bytes, *, label: str) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        warnings.warn(f"#FALLBACK: {label} response was not utf-8; decoding with replacement")
        return raw.decode("utf-8", errors="replace")


def _parse_json(text: str, *, label: str) -> Dict[str, Any]:
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except Exception:
        warnings.warn(f"#FALLBACK: {label} response was not JSON; returning empty object")
        return {}


def _read_error(resp: urllib.response.addinfourl, *, label: str) -> str:
    try:
        raw = resp.read() or b""
    except Exception:
        return label
    text = _decode_bytes(raw, label=label).strip()
    if not text:
        return label
    if text.startswith("{") or text.startswith("["):
        parsed = _parse_json(text, label=label)
        if isinstance(parsed, dict):
            detail = parsed.get("detail") or parsed.get("error") or parsed.get("message")
            if isinstance(detail, str) and detail.strip():
                return detail.strip()
            return json.dumps(parsed)
    return text


def _request_json(
    *,
    method: str,
    url: str,
    headers: Dict[str, str],
    body: Optional[Dict[str, Any]] = None,
    timeout_s: float,
    label: str,
) -> Dict[str, Any]:
    data = None
    h = dict(headers)
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method.upper(), headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read() or b""
            text = _decode_bytes(raw, label=label)
            if not text.strip():
                return {}
            return _parse_json(text, label=label)
    except urllib.error.HTTPError as e:
        body_text = _read_error(e, label=label)
        raise GatewayHttpError(f"{label}: {body_text}", status=int(getattr(e, "code", 0) or 0), retry_after_s=_retry_after_s(dict(e.headers)), body_text=body_text)


def _encode_multipart(
    *,
    fields: Dict[str, str],
    files: List[Tuple[str, str, str, bytes]],
) -> Tuple[bytes, str]:
    boundary = f"----abstractassistant-{os.urandom(12).hex()}"
    lines: List[bytes] = []
    for k, v in fields.items():
        lines.append(f"--{boundary}".encode("utf-8"))
        lines.append(f'Content-Disposition: form-data; name="{k}"'.encode("utf-8"))
        lines.append(b"")
        lines.append(str(v).encode("utf-8"))
    for field, filename, content_type, data in files:
        lines.append(f"--{boundary}".encode("utf-8"))
        lines.append(
            f'Content-Disposition: form-data; name="{field}"; filename="{filename}"'.encode("utf-8")
        )
        lines.append(f"Content-Type: {content_type}".encode("utf-8"))
        lines.append(b"")
        lines.append(data)
    lines.append(f"--{boundary}--".encode("utf-8"))
    lines.append(b"")
    body = b"\r\n".join(lines)
    content_type_header = f"multipart/form-data; boundary={boundary}"
    return body, content_type_header


class GatewayClient:
    """HTTP client wrapper for the gateway control plane."""

    def __init__(self, cfg: GatewayClientConfig) -> None:
        self._cfg = GatewayClientConfig(
            base_url=str(cfg.base_url or "").strip(),
            auth_token=str(cfg.auth_token or "").strip(),
            timeout_s=float(cfg.timeout_s),
        )

    def _url(self, path: str, query: Optional[Dict[str, Any]] = None) -> str:
        url = _join(self._cfg.base_url, path)
        if query:
            url = f"{url}?{urlencode(query)}"
        return url

    def start_run(
        self,
        *,
        flow_id: Optional[str],
        input_data: Dict[str, Any],
        bundle_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> str:
        body: Dict[str, Any] = {"input_data": input_data or {}}
        if bundle_id:
            body["bundle_id"] = str(bundle_id)
        if flow_id:
            body["flow_id"] = str(flow_id)
        if session_id:
            body["session_id"] = str(session_id)
        out = _request_json(
            method="POST",
            url=self._url("/api/gateway/runs/start"),
            headers=_auth_headers(self._cfg.auth_token),
            body=body,
            timeout_s=self._cfg.timeout_s,
            label="start_run failed",
        )
        run_id = out.get("run_id")
        if not isinstance(run_id, str) or not run_id.strip():
            raise RuntimeError("start_run: missing run_id")
        return run_id.strip()

    def get_run(self, run_id: str) -> Dict[str, Any]:
        rid = str(run_id or "").strip()
        if not rid:
            raise ValueError("get_run: run_id is required")
        return _request_json(
            method="GET",
            url=self._url(f"/api/gateway/runs/{rid}"),
            headers=_auth_headers(self._cfg.auth_token),
            timeout_s=self._cfg.timeout_s,
            label="get_run failed",
        )

    def get_run_input_data(self, *, run_id: str) -> Dict[str, Any]:
        rid = str(run_id or "").strip()
        if not rid:
            raise ValueError("get_run_input_data: run_id is required")
        return _request_json(
            method="GET",
            url=self._url(f"/api/gateway/runs/{rid}/input_data"),
            headers=_auth_headers(self._cfg.auth_token),
            timeout_s=self._cfg.timeout_s,
            label="get_run_input_data failed",
        )

    def list_runs(self, *, limit: int = 50, status: str = "", session_id: str = "", root_only: bool = False) -> Dict[str, Any]:
        query: Dict[str, Any] = {"limit": max(1, int(limit))}
        if status:
            query["status"] = status
        if session_id:
            query["session_id"] = session_id
        if root_only:
            query["root_only"] = "true"
        return _request_json(
            method="GET",
            url=self._url("/api/gateway/runs", query=query),
            headers=_auth_headers(self._cfg.auth_token),
            timeout_s=self._cfg.timeout_s,
            label="list_runs failed",
        )

    def get_run_history_bundle(
        self,
        *,
        run_id: str,
        include_subruns: bool = True,
        include_session: bool = True,
        session_turn_limit: int = 50,
        ledger_mode: str = "tail",
        ledger_max_items: int = 2000,
    ) -> Dict[str, Any]:
        rid = str(run_id or "").strip()
        if not rid:
            raise ValueError("get_run_history_bundle: run_id is required")
        query: Dict[str, Any] = {
            "include_subruns": "true" if include_subruns else "false",
            "include_session": "true" if include_session else "false",
        }
        if session_turn_limit:
            query["session_turn_limit"] = max(1, int(session_turn_limit))
        if ledger_mode:
            query["ledger_mode"] = str(ledger_mode)
        if ledger_max_items:
            query["ledger_max_items"] = max(1, int(ledger_max_items))
        return _request_json(
            method="GET",
            url=self._url(f"/api/gateway/runs/{rid}/history_bundle", query=query),
            headers=_auth_headers(self._cfg.auth_token),
            timeout_s=self._cfg.timeout_s,
            label="get_run_history_bundle failed",
        )

    def get_ledger(self, *, run_id: str, after: int, limit: int) -> Dict[str, Any]:
        rid = str(run_id or "").strip()
        if not rid:
            raise ValueError("get_ledger: run_id is required")
        query = {"after": int(after), "limit": int(limit)}
        return _request_json(
            method="GET",
            url=self._url(f"/api/gateway/runs/{rid}/ledger", query=query),
            headers=_auth_headers(self._cfg.auth_token),
            timeout_s=self._cfg.timeout_s,
            label="get_ledger failed",
        )

    def stream_ledger(
        self,
        *,
        run_id: str,
        after: int,
        on_step: Callable[[LedgerStreamEvent], Optional[bool]],
        stop_signal: Optional[Any] = None,
        timeout_s: Optional[float] = None,
        max_idle_s: Optional[float] = None,
    ) -> None:
        rid = str(run_id or "").strip()
        if not rid:
            raise ValueError("stream_ledger: run_id is required")
        url = self._url(f"/api/gateway/runs/{rid}/ledger/stream", query={"after": int(after)})
        headers = {"Accept": "text/event-stream", **_auth_headers(self._cfg.auth_token)}
        req = urllib.request.Request(url, headers=headers, method="GET")
        timeout = self._cfg.timeout_s if timeout_s is None else float(timeout_s)
        last_step_at = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                parser = SseParser()
                for raw in resp:
                    if stop_signal is not None and bool(getattr(stop_signal, "is_set", lambda: False)()):
                        return
                    text = _decode_bytes(raw, label="stream_ledger")
                    for ev in parser.push(text):
                        if ev.event != "step" or not ev.data:
                            continue
                        try:
                            parsed = json.loads(ev.data)
                        except Exception:
                            warnings.warn("#FALLBACK: stream_ledger event data was not JSON; dropping")
                            continue
                        if isinstance(parsed, dict) and isinstance(parsed.get("cursor"), int) and parsed.get("record"):
                            last_step_at = time.monotonic()
                            keep_going = on_step(parsed)  # type: ignore[arg-type]
                            if keep_going is False:
                                return
                    if max_idle_s is not None and (time.monotonic() - last_step_at) >= max_idle_s:
                        raise GatewayStreamIdle(f"stream_ledger idle for {max_idle_s:.0f}s")
        except socket.timeout:
            raise GatewayStreamIdle("stream_ledger socket timeout")
        except urllib.error.HTTPError as e:
            body_text = _read_error(e, label="stream_ledger failed")
            raise GatewayHttpError(
                f"stream_ledger failed: {body_text}",
                status=int(getattr(e, "code", 0) or 0),
                retry_after_s=_retry_after_s(dict(e.headers)),
                body_text=body_text,
            )
        except urllib.error.URLError as e:
            if isinstance(getattr(e, "reason", None), socket.timeout):
                raise GatewayStreamIdle("stream_ledger socket timeout")
            raise

    def list_bundles(self) -> Dict[str, Any]:
        return _request_json(
            method="GET",
            url=self._url("/api/gateway/bundles"),
            headers=_auth_headers(self._cfg.auth_token),
            timeout_s=self._cfg.timeout_s,
            label="list_bundles failed",
        )

    def discovery_capabilities(self) -> Dict[str, Any]:
        return _request_json(
            method="GET",
            url=self._url("/api/gateway/discovery/capabilities"),
            headers=_auth_headers(self._cfg.auth_token),
            timeout_s=self._cfg.timeout_s,
            label="discovery_capabilities failed",
        )

    def discovery_providers(self, *, include_models: bool = False) -> Dict[str, Any]:
        return _request_json(
            method="GET",
            url=self._url("/api/gateway/discovery/providers", query={"include_models": "true" if include_models else "false"}),
            headers=_auth_headers(self._cfg.auth_token),
            timeout_s=self._cfg.timeout_s,
            label="discovery_providers failed",
        )

    def discovery_provider_models(self, *, provider_name: str) -> Dict[str, Any]:
        prov = str(provider_name or "").strip()
        if not prov:
            raise ValueError("discovery_provider_models: provider_name is required")
        return _request_json(
            method="GET",
            url=self._url(f"/api/gateway/discovery/providers/{prov}/models"),
            headers=_auth_headers(self._cfg.auth_token),
            timeout_s=self._cfg.timeout_s,
            label="discovery_provider_models failed",
        )

    def discovery_model_capabilities(self, *, model_name: str) -> Dict[str, Any]:
        name = str(model_name or "").strip()
        if not name:
            raise ValueError("discovery_model_capabilities: model_name is required")
        return _request_json(
            method="GET",
            url=self._url("/api/gateway/discovery/models/capabilities", query={"model_name": name}),
            headers=_auth_headers(self._cfg.auth_token),
            timeout_s=self._cfg.timeout_s,
            label="discovery_model_capabilities failed",
        )

    def discovery_tools(self) -> Dict[str, Any]:
        return _request_json(
            method="GET",
            url=self._url("/api/gateway/discovery/tools"),
            headers=_auth_headers(self._cfg.auth_token),
            timeout_s=self._cfg.timeout_s,
            label="discovery_tools failed",
        )

    def submit_command(self, *, command: Dict[str, Any]) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "command_id": str(command.get("command_id") or "").strip(),
            "run_id": str(command.get("run_id") or "").strip(),
            "type": str(command.get("type") or "").strip(),
            "payload": command.get("payload") if isinstance(command.get("payload"), dict) else {},
        }
        if not body["command_id"] or not body["run_id"] or not body["type"]:
            raise ValueError("submit_command: command_id, run_id, and type are required")
        for k in ("ts", "client_id"):
            v = command.get(k)
            if isinstance(v, str) and v.strip():
                body[k] = v.strip()
        return _request_json(
            method="POST",
            url=self._url("/api/gateway/commands"),
            headers=_auth_headers(self._cfg.auth_token),
            body=body,
            timeout_s=self._cfg.timeout_s,
            label="submit_command failed",
        )

    def attachments_ingest(self, *, session_id: str, path: str, scope: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        sid = str(session_id or "").strip()
        p = str(path or "").strip()
        if not sid:
            raise ValueError("attachments_ingest: session_id is required")
        if not p:
            raise ValueError("attachments_ingest: path is required")
        body: Dict[str, Any] = {"session_id": sid, "path": p}
        if scope and isinstance(scope, dict):
            body.update({k: v for k, v in scope.items() if isinstance(v, str) and v.strip()})
        return _request_json(
            method="POST",
            url=self._url("/api/gateway/attachments/ingest"),
            headers=_auth_headers(self._cfg.auth_token),
            body=body,
            timeout_s=self._cfg.timeout_s,
            label="attachments_ingest failed",
        )

    def attachments_upload(
        self,
        *,
        session_id: str,
        file_path: str,
        filename: Optional[str] = None,
        content_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        sid = str(session_id or "").strip()
        if not sid:
            raise ValueError("attachments_upload: session_id is required")
        p = str(file_path or "").strip()
        if not p:
            raise ValueError("attachments_upload: file_path is required")
        with open(p, "rb") as f:
            data = f.read()
        name = filename or os.path.basename(p) or "upload.bin"
        ctype = content_type or mimetypes.guess_type(name)[0] or "application/octet-stream"
        if not content_type:
            warnings.warn("#FALLBACK: attachments_upload content_type missing; using application/octet-stream")
        body, content_type_header = _encode_multipart(
            fields={"session_id": sid},
            files=[("file", name, ctype, data)],
        )
        headers = {"Content-Type": content_type_header, **_auth_headers(self._cfg.auth_token)}
        req = urllib.request.Request(self._url("/api/gateway/attachments/upload"), data=body, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self._cfg.timeout_s) as resp:
                raw = resp.read() or b""
                text = _decode_bytes(raw, label="attachments_upload")
                return _parse_json(text, label="attachments_upload")
        except urllib.error.HTTPError as e:
            body_text = _read_error(e, label="attachments_upload failed")
            raise GatewayHttpError(
                f"attachments_upload failed: {body_text}",
                status=int(getattr(e, "code", 0) or 0),
                retry_after_s=_retry_after_s(dict(e.headers)),
                body_text=body_text,
            )

    def audio_transcribe(self, *, run_id: str, audio_artifact: Dict[str, Any], request_id: Optional[str] = None, language: Optional[str] = None) -> Dict[str, Any]:
        rid = str(run_id or "").strip()
        if not rid:
            raise ValueError("audio_transcribe: run_id is required")
        body: Dict[str, Any] = {"audio_artifact": audio_artifact}
        if request_id:
            body["request_id"] = str(request_id)
        if language:
            body["language"] = str(language)
        return _request_json(
            method="POST",
            url=self._url(f"/api/gateway/runs/{rid}/audio/transcribe"),
            headers=_auth_headers(self._cfg.auth_token),
            body=body,
            timeout_s=self._cfg.timeout_s,
            label="audio_transcribe failed",
        )

    def voice_tts(self, *, run_id: str, text: str, voice: Optional[str] = None, fmt: Optional[str] = None, request_id: Optional[str] = None) -> Dict[str, Any]:
        rid = str(run_id or "").strip()
        if not rid:
            raise ValueError("voice_tts: run_id is required")
        body: Dict[str, Any] = {"text": str(text or "")}
        if voice:
            body["voice"] = str(voice)
        if fmt:
            body["format"] = str(fmt)
        if request_id:
            body["request_id"] = str(request_id)
        return _request_json(
            method="POST",
            url=self._url(f"/api/gateway/runs/{rid}/voice/tts"),
            headers=_auth_headers(self._cfg.auth_token),
            body=body,
            timeout_s=self._cfg.timeout_s,
            label="voice_tts failed",
        )

    def image_generate(
        self,
        *,
        run_id: str,
        prompt: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        size: Optional[str] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        fmt: str = "png",
        negative_prompt: Optional[str] = None,
        seed: Optional[int] = None,
        steps: Optional[int] = None,
        guidance_scale: Optional[float] = None,
        quality: Optional[str] = None,
        style: Optional[str] = None,
        request_id: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        rid = str(run_id or "").strip()
        if not rid:
            raise ValueError("image_generate: run_id is required")
        body: Dict[str, Any] = {"prompt": str(prompt or ""), "format": str(fmt or "png")}
        optional: Dict[str, Any] = {
            "provider": provider,
            "model": model,
            "size": size,
            "width": width,
            "height": height,
            "negative_prompt": negative_prompt,
            "seed": seed,
            "steps": steps,
            "guidance_scale": guidance_scale,
            "quality": quality,
            "style": style,
            "request_id": request_id,
            "extra": extra,
        }
        for key, value in optional.items():
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            body[key] = value
        return _request_json(
            method="POST",
            url=self._url(f"/api/gateway/runs/{rid}/images/generate"),
            headers=_auth_headers(self._cfg.auth_token),
            body=body,
            timeout_s=self._cfg.timeout_s,
            label="image_generate failed",
        )

    def session_prompt_cache_status(
        self,
        *,
        session_id: str,
        provider: str,
        model: str,
        bundle_id: Optional[str] = None,
        bundle_version: Optional[str] = None,
        flow_id: Optional[str] = None,
        template_id: Optional[str] = None,
        version: int = 1,
    ) -> Dict[str, Any]:
        sid = str(session_id or "").strip()
        if not sid:
            raise ValueError("session_prompt_cache_status: session_id is required")
        query: Dict[str, Any] = {
            "provider": str(provider or "").strip(),
            "model": str(model or "").strip(),
            "version": int(version or 1),
        }
        if not query["provider"] or not query["model"]:
            raise ValueError("session_prompt_cache_status: provider and model are required")
        for key, value in {
            "bundle_id": bundle_id,
            "bundle_version": bundle_version,
            "flow_id": flow_id,
            "template_id": template_id,
        }.items():
            if isinstance(value, str) and value.strip():
                query[key] = value.strip()
        return _request_json(
            method="GET",
            url=self._url(f"/api/gateway/sessions/{sid}/prompt_cache/status", query=query),
            headers=_auth_headers(self._cfg.auth_token),
            timeout_s=self._cfg.timeout_s,
            label="session_prompt_cache_status failed",
        )

    def session_prompt_cache_prepare(
        self,
        *,
        session_id: str,
        provider: str,
        model: str,
        bundle_id: Optional[str] = None,
        bundle_version: Optional[str] = None,
        flow_id: Optional[str] = None,
        template_id: Optional[str] = None,
        modules: Optional[List[Dict[str, Any]]] = None,
        system_prompt: Optional[str] = None,
        workflow_instructions: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        pinned_attachments: Optional[List[Dict[str, Any]]] = None,
        make_default: bool = False,
        ttl_s: Optional[float] = None,
        version: int = 1,
    ) -> Dict[str, Any]:
        body = self._session_prompt_cache_body(
            provider=provider,
            model=model,
            bundle_id=bundle_id,
            bundle_version=bundle_version,
            flow_id=flow_id,
            template_id=template_id,
            modules=modules,
            system_prompt=system_prompt,
            workflow_instructions=workflow_instructions,
            tools=tools,
            pinned_attachments=pinned_attachments,
            make_default=make_default,
            ttl_s=ttl_s,
            version=version,
        )
        return self._session_prompt_cache_post(
            session_id=session_id,
            operation="prepare",
            body=body,
            label="session_prompt_cache_prepare failed",
        )

    def session_prompt_cache_clear(
        self,
        *,
        session_id: str,
        provider: str,
        model: str,
        bundle_id: Optional[str] = None,
        bundle_version: Optional[str] = None,
        flow_id: Optional[str] = None,
        template_id: Optional[str] = None,
        version: int = 1,
    ) -> Dict[str, Any]:
        body = self._session_prompt_cache_body(
            provider=provider,
            model=model,
            bundle_id=bundle_id,
            bundle_version=bundle_version,
            flow_id=flow_id,
            template_id=template_id,
            version=version,
        )
        return self._session_prompt_cache_post(
            session_id=session_id,
            operation="clear",
            body=body,
            label="session_prompt_cache_clear failed",
        )

    def session_prompt_cache_rebuild(
        self,
        *,
        session_id: str,
        provider: str,
        model: str,
        bundle_id: Optional[str] = None,
        bundle_version: Optional[str] = None,
        flow_id: Optional[str] = None,
        template_id: Optional[str] = None,
        modules: Optional[List[Dict[str, Any]]] = None,
        system_prompt: Optional[str] = None,
        workflow_instructions: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        pinned_attachments: Optional[List[Dict[str, Any]]] = None,
        make_default: bool = False,
        ttl_s: Optional[float] = None,
        version: int = 1,
    ) -> Dict[str, Any]:
        body = self._session_prompt_cache_body(
            provider=provider,
            model=model,
            bundle_id=bundle_id,
            bundle_version=bundle_version,
            flow_id=flow_id,
            template_id=template_id,
            modules=modules,
            system_prompt=system_prompt,
            workflow_instructions=workflow_instructions,
            tools=tools,
            pinned_attachments=pinned_attachments,
            make_default=make_default,
            ttl_s=ttl_s,
            version=version,
        )
        return self._session_prompt_cache_post(
            session_id=session_id,
            operation="rebuild",
            body=body,
            label="session_prompt_cache_rebuild failed",
        )

    def _session_prompt_cache_body(
        self,
        *,
        provider: str,
        model: str,
        bundle_id: Optional[str] = None,
        bundle_version: Optional[str] = None,
        flow_id: Optional[str] = None,
        template_id: Optional[str] = None,
        modules: Optional[List[Dict[str, Any]]] = None,
        system_prompt: Optional[str] = None,
        workflow_instructions: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        pinned_attachments: Optional[List[Dict[str, Any]]] = None,
        make_default: bool = False,
        ttl_s: Optional[float] = None,
        version: int = 1,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "provider": str(provider or "").strip(),
            "model": str(model or "").strip(),
            "version": int(version or 1),
        }
        if not body["provider"] or not body["model"]:
            raise ValueError("session prompt-cache: provider and model are required")
        optional: Dict[str, Any] = {
            "bundle_id": bundle_id,
            "bundle_version": bundle_version,
            "flow_id": flow_id,
            "template_id": template_id,
            "modules": modules,
            "system_prompt": system_prompt,
            "workflow_instructions": workflow_instructions,
            "tools": tools,
            "pinned_attachments": pinned_attachments,
            "make_default": bool(make_default),
            "ttl_s": ttl_s,
        }
        for key, value in optional.items():
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            if isinstance(value, list) and not value:
                continue
            if key == "make_default" and value is False:
                continue
            body[key] = value
        return body

    def _session_prompt_cache_post(
        self,
        *,
        session_id: str,
        operation: str,
        body: Dict[str, Any],
        label: str,
    ) -> Dict[str, Any]:
        sid = str(session_id or "").strip()
        op = str(operation or "").strip()
        if not sid:
            raise ValueError(f"{label}: session_id is required")
        if op not in {"prepare", "clear", "rebuild"}:
            raise ValueError(f"{label}: invalid operation")
        return _request_json(
            method="POST",
            url=self._url(f"/api/gateway/sessions/{sid}/prompt_cache/{op}"),
            headers=_auth_headers(self._cfg.auth_token),
            body=body,
            timeout_s=self._cfg.timeout_s,
            label=label,
        )

    def list_run_artifacts(self, *, run_id: str, limit: int = 200) -> Dict[str, Any]:
        rid = str(run_id or "").strip()
        if not rid:
            raise ValueError("list_run_artifacts: run_id is required")
        query = {"limit": max(1, int(limit))}
        return _request_json(
            method="GET",
            url=self._url(f"/api/gateway/runs/{rid}/artifacts", query=query),
            headers=_auth_headers(self._cfg.auth_token),
            timeout_s=self._cfg.timeout_s,
            label="list_run_artifacts failed",
        )

    def get_run_artifact_metadata(self, *, run_id: str, artifact_id: str) -> Dict[str, Any]:
        rid = str(run_id or "").strip()
        aid = str(artifact_id or "").strip()
        if not rid:
            raise ValueError("get_run_artifact_metadata: run_id is required")
        if not aid:
            raise ValueError("get_run_artifact_metadata: artifact_id is required")
        return _request_json(
            method="GET",
            url=self._url(f"/api/gateway/runs/{rid}/artifacts/{aid}"),
            headers=_auth_headers(self._cfg.auth_token),
            timeout_s=self._cfg.timeout_s,
            label="get_run_artifact_metadata failed",
        )

    def download_run_artifact_content(
        self,
        *,
        run_id: str,
        artifact_id: str,
        max_bytes: int = 25_000_000,
    ) -> Tuple[bytes, str]:
        rid = str(run_id or "").strip()
        aid = str(artifact_id or "").strip()
        if not rid:
            raise ValueError("download_run_artifact_content: run_id is required")
        if not aid:
            raise ValueError("download_run_artifact_content: artifact_id is required")
        url = self._url(f"/api/gateway/runs/{rid}/artifacts/{aid}/content")
        req = urllib.request.Request(url, headers=_auth_headers(self._cfg.auth_token), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self._cfg.timeout_s) as resp:
                raw = resp.read() or b""
                if int(max_bytes) > 0 and len(raw) > int(max_bytes):
                    raise RuntimeError(f"Artifact too large ({len(raw)} bytes > {int(max_bytes)} bytes)")
                content_type = str(resp.headers.get("content-type") or "").strip() or "application/octet-stream"
                return raw, content_type
        except urllib.error.HTTPError as e:
            body_text = _read_error(e, label="download_run_artifact_content failed")
            raise GatewayHttpError(
                f"download_run_artifact_content failed: {body_text}",
                status=int(getattr(e, "code", 0) or 0),
                retry_after_s=_retry_after_s(dict(e.headers)),
                body_text=body_text,
            )
