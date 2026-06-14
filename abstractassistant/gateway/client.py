"""
Gateway HTTP client for AbstractAssistant (thin-client mode).

This mirrors the `abstractcode/web` GatewayClient and exposes the same API
surface so the tray UI can drive runs via the gateway control plane.
"""

from __future__ import annotations

from dataclasses import dataclass
from http.cookies import SimpleCookie
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
    auth_mode: str = "bearer"
    user_id: str = ""
    session_id: str = ""
    csrf_token: str = ""
    session_expires_at: str = ""
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


def _apply_optional_fields(body: Dict[str, Any], optional: Dict[str, Any]) -> None:
    for key, value in optional.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        body[key] = value


def _merge_media_options(body: Dict[str, Any], options: Optional[Dict[str, Any]], *, allowed_keys: Tuple[str, ...]) -> None:
    if not isinstance(options, dict):
        return
    for key in allowed_keys:
        if key not in options:
            continue
        value = options.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
            if not value:
                continue
        body[key] = value


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
            auth_mode=str(cfg.auth_mode or "bearer").strip() or "bearer",
            user_id=str(cfg.user_id or "").strip(),
            session_id=str(cfg.session_id or "").strip(),
            csrf_token=str(cfg.csrf_token or "").strip(),
            session_expires_at=str(cfg.session_expires_at or "").strip(),
            timeout_s=float(cfg.timeout_s),
        )

    def _url(self, path: str, query: Optional[Dict[str, Any]] = None) -> str:
        url = _join(self._cfg.base_url, path)
        if query:
            url = f"{url}?{urlencode(query)}"
        return url

    @property
    def config(self) -> GatewayClientConfig:
        return self._cfg

    def _session_auth_active(self) -> bool:
        return str(self._cfg.auth_mode or "bearer").strip() == "session" and bool(str(self._cfg.session_id or "").strip())

    def _headers(self, *, mutating: bool = False, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self._session_auth_active():
            headers["X-AbstractGateway-Session"] = str(self._cfg.session_id or "").strip()
            if mutating:
                csrf_token = str(self._cfg.csrf_token or "").strip()
                if not csrf_token:
                    raise ValueError("Gateway session auth requires csrf_token for mutating requests")
                headers["X-AbstractGateway-CSRF"] = csrf_token
        token = str(self._cfg.auth_token or "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if extra:
            headers.update(extra)
        return headers

    def _request_json(
        self,
        *,
        method: str,
        url: str,
        body: Optional[Dict[str, Any]] = None,
        timeout_s: Optional[float] = None,
        label: str,
    ) -> Dict[str, Any]:
        method_s = str(method or "GET").upper()
        return _request_json(
            method=method_s,
            url=url,
            headers=self._headers(mutating=method_s not in {"GET", "HEAD", "OPTIONS"}),
            body=body,
            timeout_s=self._cfg.timeout_s if timeout_s is None else float(timeout_s),
            label=label,
        )

    def gateway_me(self) -> Dict[str, Any]:
        return self._request_json(
            method="GET",
            url=self._url("/api/gateway/me"),
            label="gateway_me failed",
        )

    def openapi_document(self) -> Dict[str, Any]:
        return self._request_json(
            method="GET",
            url=self._url("/openapi.json"),
            label="openapi_document failed",
        )

    def session_login(
        self,
        *,
        user_id: str,
        token: str,
        remember: bool = True,
        forwarded_proto: Optional[str] = None,
    ) -> Dict[str, Any]:
        user_id_s = str(user_id or "").strip()
        token_s = str(token or "").strip()
        if not user_id_s:
            raise ValueError("session_login: user_id is required")
        if not token_s:
            raise ValueError("session_login: token is required")
        data = json.dumps({"user_id": user_id_s, "token": token_s, "remember": bool(remember)}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        proto = str(forwarded_proto or "").strip()
        if proto:
            headers["X-Forwarded-Proto"] = proto
        req = urllib.request.Request(
            self._url("/api/gateway/session/login"),
            data=data,
            method="POST",
            headers=headers,
        )
        try:
            with urllib.request.urlopen(req, timeout=self._cfg.timeout_s) as resp:
                raw = resp.read() or b""
                payload = _parse_json(_decode_bytes(raw, label="session_login"), label="session_login")
                session_id, csrf_token = self._extract_session_tokens(resp.headers)
        except urllib.error.HTTPError as e:
            body_text = _read_error(e, label="session_login failed")
            raise GatewayHttpError(
                f"session_login failed: {body_text}",
                status=int(getattr(e, "code", 0) or 0),
                retry_after_s=_retry_after_s(dict(e.headers)),
                body_text=body_text,
            )
        if not session_id or not csrf_token:
            raise RuntimeError("session_login failed: gateway did not return session cookies")
        self._cfg = GatewayClientConfig(
            base_url=self._cfg.base_url,
            auth_token="",
            auth_mode="session",
            user_id=user_id_s,
            session_id=session_id,
            csrf_token=csrf_token,
            session_expires_at=str(payload.get("session", {}).get("expires_at") or "").strip() if isinstance(payload.get("session"), dict) else "",
            timeout_s=self._cfg.timeout_s,
        )
        return payload

    def session_logout(self) -> Dict[str, Any]:
        payload = self._request_json(
            method="POST",
            url=self._url("/api/gateway/session/logout"),
            label="session_logout failed",
        )
        self._cfg = GatewayClientConfig(
            base_url=self._cfg.base_url,
            auth_token="",
            auth_mode="session",
            user_id=str(self._cfg.user_id or "").strip(),
            session_id="",
            csrf_token="",
            session_expires_at="",
            timeout_s=self._cfg.timeout_s,
        )
        return payload

    def _extract_session_tokens(self, headers: Any) -> Tuple[str, str]:
        cookie_headers: List[str] = []
        get_all = getattr(headers, "get_all", None)
        if callable(get_all):
            cookie_headers = [str(item) for item in get_all("Set-Cookie") or []]
        if not cookie_headers:
            get_list = getattr(headers, "get_list", None)
            if callable(get_list):
                cookie_headers = [str(item) for item in get_list("set-cookie") or []]
        if not cookie_headers:
            raw = headers.get("Set-Cookie") if hasattr(headers, "get") else None
            if raw:
                cookie_headers = [str(raw)]
        cookie = SimpleCookie()
        for item in cookie_headers:
            try:
                cookie.load(item)
            except Exception:
                continue
        session_id = str(cookie.get("abstractgateway_session").value if cookie.get("abstractgateway_session") else "").strip()
        csrf_token = str(cookie.get("abstractgateway_csrf").value if cookie.get("abstractgateway_csrf") else "").strip()
        return session_id, csrf_token

    def start_run(
        self,
        *,
        flow_id: Optional[str],
        input_data: Dict[str, Any],
        bundle_id: Optional[str] = None,
        bundle_version: Optional[str] = None,
        session_id: Optional[str] = None,
        registry_scope: Optional[str] = None,
    ) -> str:
        body: Dict[str, Any] = {"input_data": input_data or {}}
        if bundle_id:
            body["bundle_id"] = str(bundle_id)
        if bundle_version:
            body["bundle_version"] = str(bundle_version)
        if flow_id:
            body["flow_id"] = str(flow_id)
        if session_id:
            body["session_id"] = str(session_id)
        if registry_scope:
            body["registry_scope"] = str(registry_scope)
        out = self._request_json(
            method="POST",
            url=self._url("/api/gateway/runs/start"),
            body=body,
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
        return self._request_json(method="GET", url=self._url(f"/api/gateway/runs/{rid}"), label="get_run failed")

    def get_run_input_data(self, *, run_id: str) -> Dict[str, Any]:
        rid = str(run_id or "").strip()
        if not rid:
            raise ValueError("get_run_input_data: run_id is required")
        return self._request_json(
            method="GET",
            url=self._url(f"/api/gateway/runs/{rid}/input_data"),
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
        return self._request_json(method="GET", url=self._url("/api/gateway/runs", query=query), label="list_runs failed")

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
        return self._request_json(
            method="GET",
            url=self._url(f"/api/gateway/runs/{rid}/history_bundle", query=query),
            label="get_run_history_bundle failed",
        )

    def get_ledger(self, *, run_id: str, after: int, limit: int) -> Dict[str, Any]:
        rid = str(run_id or "").strip()
        if not rid:
            raise ValueError("get_ledger: run_id is required")
        query = {"after": int(after), "limit": int(limit)}
        return self._request_json(
            method="GET",
            url=self._url(f"/api/gateway/runs/{rid}/ledger", query=query),
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
        headers = self._headers(extra={"Accept": "text/event-stream"})
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
        return self._request_json(method="GET", url=self._url("/api/gateway/bundles"), label="list_bundles failed")

    def workflow_catalog(self, *, scope: str = "tenant_catalog") -> Dict[str, Any]:
        return self._request_json(
            method="GET",
            url=self._url("/api/gateway/workflow-catalog", query={"scope": str(scope or "tenant_catalog")}),
            label="workflow_catalog failed",
        )

    def promote_workflow_catalog_bundle(
        self,
        *,
        bundle_id: str,
        bundle_version: Optional[str] = None,
        scope: str = "tenant_catalog",
        tenant_id: Optional[str] = None,
        make_default: bool = False,
        acl: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        bundle_id_s = str(bundle_id or "").strip()
        if not bundle_id_s:
            raise ValueError("promote_workflow_catalog_bundle: bundle_id is required")
        body: Dict[str, Any] = {
            "bundle_id": bundle_id_s,
            "scope": str(scope or "tenant_catalog").strip() or "tenant_catalog",
            "make_default": bool(make_default),
        }
        if bundle_version is not None and str(bundle_version).strip():
            body["bundle_version"] = str(bundle_version).strip()
        if tenant_id is not None and str(tenant_id).strip():
            body["tenant_id"] = str(tenant_id).strip()
        if isinstance(acl, dict) and acl:
            body["acl"] = dict(acl)
        return self._request_json(
            method="POST",
            url=self._url("/api/gateway/admin/workflow-catalog/promote"),
            body=body,
            label="promote_workflow_catalog_bundle failed",
        )

    def list_visualflows(self) -> List[Dict[str, Any]]:
        payload = self._request_json(
            method="GET",
            url=self._url("/api/gateway/visualflows"),
            label="list_visualflows failed",
        )
        return payload if isinstance(payload, list) else []

    def create_visualflow(
        self,
        *,
        name: str,
        description: str = "",
        interfaces: Optional[List[str]] = None,
        nodes: Optional[List[Dict[str, Any]]] = None,
        edges: Optional[List[Dict[str, Any]]] = None,
        entry_node: Optional[str] = None,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "name": str(name or "").strip(),
            "description": str(description or "").strip(),
            "interfaces": list(interfaces or []),
            "nodes": list(nodes or []),
            "edges": list(edges or []),
            "entryNode": str(entry_node or "").strip() or None,
        }
        if not body["name"]:
            raise ValueError("create_visualflow: name is required")
        return self._request_json(
            method="POST",
            url=self._url("/api/gateway/visualflows"),
            body=body,
            label="create_visualflow failed",
        )

    def get_visualflow(self, *, flow_id: str) -> Dict[str, Any]:
        flow_id_s = str(flow_id or "").strip()
        if not flow_id_s:
            raise ValueError("get_visualflow: flow_id is required")
        return self._request_json(
            method="GET",
            url=self._url(f"/api/gateway/visualflows/{flow_id_s}"),
            label="get_visualflow failed",
        )

    def update_visualflow(
        self,
        *,
        flow_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        interfaces: Optional[List[str]] = None,
        nodes: Optional[List[Dict[str, Any]]] = None,
        edges: Optional[List[Dict[str, Any]]] = None,
        entry_node: Optional[str] = None,
    ) -> Dict[str, Any]:
        flow_id_s = str(flow_id or "").strip()
        if not flow_id_s:
            raise ValueError("update_visualflow: flow_id is required")
        body: Dict[str, Any] = {}
        if name is not None:
            body["name"] = str(name).strip()
        if description is not None:
            body["description"] = str(description).strip()
        if interfaces is not None:
            body["interfaces"] = list(interfaces or [])
        if nodes is not None:
            body["nodes"] = list(nodes or [])
        if edges is not None:
            body["edges"] = list(edges or [])
        if entry_node is not None:
            body["entryNode"] = str(entry_node).strip() or None
        return self._request_json(
            method="PUT",
            url=self._url(f"/api/gateway/visualflows/{flow_id_s}"),
            body=body,
            label="update_visualflow failed",
        )

    def publish_visualflow(
        self,
        *,
        flow_id: str,
        bundle_id: Optional[str] = None,
        bundle_version: Optional[str] = None,
        overwrite: bool = False,
        reload_gateway: bool = True,
    ) -> Dict[str, Any]:
        flow_id_s = str(flow_id or "").strip()
        if not flow_id_s:
            raise ValueError("publish_visualflow: flow_id is required")
        body: Dict[str, Any] = {
            "bundle_id": str(bundle_id or "").strip() or None,
            "bundle_version": str(bundle_version or "").strip() or None,
            "overwrite": bool(overwrite),
            "reload_gateway": bool(reload_gateway),
        }
        return self._request_json(
            method="POST",
            url=self._url(f"/api/gateway/visualflows/{flow_id_s}/publish"),
            body=body,
            label="publish_visualflow failed",
        )

    def discovery_capabilities(self) -> Dict[str, Any]:
        return self._request_json(
            method="GET",
            url=self._url("/api/gateway/discovery/capabilities"),
            label="discovery_capabilities failed",
        )

    def discovery_providers(self, *, include_models: bool = False) -> Dict[str, Any]:
        return self._request_json(
            method="GET",
            url=self._url("/api/gateway/discovery/providers", query={"include_models": "true" if include_models else "false"}),
            label="discovery_providers failed",
        )

    def discovery_provider_models(
        self,
        *,
        provider_name: str,
        capability_route: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        prov = str(provider_name or "").strip()
        if not prov:
            raise ValueError("discovery_provider_models: provider_name is required")
        query: Dict[str, Any] = {}
        if capability_route:
            query["capability_route"] = str(capability_route)
        if base_url:
            query["base_url"] = str(base_url)
        return self._request_json(
            method="GET",
            url=self._url(f"/api/gateway/discovery/providers/{prov}/models", query=query or None),
            label="discovery_provider_models failed",
        )

    def voice_voices(
        self,
        *,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        compact: bool = False,
        providers_only: bool = False,
        base_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        query: Dict[str, Any] = {}
        if provider:
            query["provider"] = str(provider)
        if model:
            query["model"] = str(model)
        if compact:
            query["compact"] = "true"
        if providers_only:
            query["providers_only"] = "true"
        if base_url:
            query["base_url"] = str(base_url)
        return self._request_json(
            method="GET",
            url=self._url("/api/gateway/voice/voices", query=query or None),
            label="voice_voices failed",
        )

    def audio_speech_models(
        self,
        *,
        provider: Optional[str] = None,
        providers_only: bool = False,
        base_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        query: Dict[str, Any] = {}
        if provider:
            query["provider"] = str(provider)
        if providers_only:
            query["providers_only"] = "true"
        if base_url:
            query["base_url"] = str(base_url)
        return self._request_json(
            method="GET",
            url=self._url("/api/gateway/audio/speech/models", query=query or None),
            label="audio_speech_models failed",
        )

    def audio_transcription_models(
        self,
        *,
        provider: Optional[str] = None,
        providers_only: bool = False,
        base_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        query: Dict[str, Any] = {}
        if provider:
            query["provider"] = str(provider)
        if providers_only:
            query["providers_only"] = "true"
        if base_url:
            query["base_url"] = str(base_url)
        return self._request_json(
            method="GET",
            url=self._url("/api/gateway/audio/transcriptions/models", query=query or None),
            label="audio_transcription_models failed",
        )

    def audio_music_providers(
        self,
        *,
        task: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        query: Dict[str, Any] = {}
        if task:
            query["task"] = str(task)
        if base_url:
            query["base_url"] = str(base_url)
        return self._request_json(
            method="GET",
            url=self._url("/api/gateway/audio/music/providers", query=query or None),
            label="audio_music_providers failed",
        )

    def audio_music_models(
        self,
        *,
        task: Optional[str] = None,
        provider: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        query: Dict[str, Any] = {}
        if task:
            query["task"] = str(task)
        if provider:
            query["provider"] = str(provider)
        if base_url:
            query["base_url"] = str(base_url)
        return self._request_json(
            method="GET",
            url=self._url("/api/gateway/audio/music/models", query=query or None),
            label="audio_music_models failed",
        )

    def vision_provider_models(
        self,
        *,
        task: Optional[str] = None,
        provider: Optional[str] = None,
        providers_only: bool = False,
        base_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        query: Dict[str, Any] = {}
        if task:
            query["task"] = str(task)
        if provider:
            query["provider"] = str(provider)
        if providers_only:
            query["providers_only"] = "true"
        if base_url:
            query["base_url"] = str(base_url)
        return self._request_json(
            method="GET",
            url=self._url("/api/gateway/vision/provider_models", query=query or None),
            label="vision_provider_models failed",
        )

    def vision_adapters(
        self,
        *,
        model: Optional[str] = None,
        task: Optional[str] = None,
        provider: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        query: Dict[str, Any] = {}
        if model:
            query["model"] = str(model)
        if task:
            query["task"] = str(task)
        if provider:
            query["provider"] = str(provider)
        if base_url:
            query["base_url"] = str(base_url)
        return self._request_json(
            method="GET",
            url=self._url("/api/gateway/vision/adapters", query=query or None),
            label="vision_adapters failed",
        )

    def vision_models(self) -> Dict[str, Any]:
        return self._request_json(method="GET", url=self._url("/api/gateway/vision/models"), label="vision_models failed")

    def discovery_model_capabilities(self, *, model_name: str) -> Dict[str, Any]:
        name = str(model_name or "").strip()
        if not name:
            raise ValueError("discovery_model_capabilities: model_name is required")
        return self._request_json(
            method="GET",
            url=self._url("/api/gateway/discovery/models/capabilities", query={"model_name": name}),
            label="discovery_model_capabilities failed",
        )

    def discovery_tools(self) -> Dict[str, Any]:
        return self._request_json(method="GET", url=self._url("/api/gateway/discovery/tools"), label="discovery_tools failed")

    def get_capability_defaults(self) -> Dict[str, Any]:
        return self._request_json(
            method="GET",
            url=self._url("/api/gateway/config/capability-defaults"),
            label="get_capability_defaults failed",
        )

    def set_capability_default(
        self,
        *,
        route_key: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        key = str(route_key or "").strip()
        if not key:
            raise ValueError("set_capability_default: route_key is required")
        parts = [part.strip() for part in key.split(".") if part.strip()]
        if len(parts) not in {2, 3}:
            raise ValueError("set_capability_default: route_key must be kind.modality or kind.modality.task")
        body = {
            "provider": str(provider or "").strip() or None,
            "model": str(model or "").strip() or None,
            "base_url": str(base_url or "").strip() or None,
            "options": dict(options or {}) if isinstance(options, dict) else {},
        }
        suffix = f"/{parts[2]}" if len(parts) == 3 else ""
        return self._request_json(
            method="PUT",
            url=self._url(f"/api/gateway/config/capability-defaults/{parts[0]}/{parts[1]}{suffix}"),
            body=body,
            label="set_capability_default failed",
        )

    def clear_capability_default(self, *, route_key: str) -> Dict[str, Any]:
        key = str(route_key or "").strip()
        if not key:
            raise ValueError("clear_capability_default: route_key is required")
        parts = [part.strip() for part in key.split(".") if part.strip()]
        if len(parts) not in {2, 3}:
            raise ValueError("clear_capability_default: route_key must be kind.modality or kind.modality.task")
        suffix = f"/{parts[2]}" if len(parts) == 3 else ""
        return self._request_json(
            method="DELETE",
            url=self._url(f"/api/gateway/config/capability-defaults/{parts[0]}/{parts[1]}{suffix}"),
            label="clear_capability_default failed",
        )

    def sandbox_generate(
        self,
        *,
        provider: str,
        model: str,
        prompt: str,
        capability: str = "output.text",
        system_prompt: Optional[str] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout_s: Optional[float] = None,
    ) -> Dict[str, Any]:
        provider_s = str(provider or "").strip()
        model_s = str(model or "").strip()
        prompt_s = str(prompt or "").strip()
        if not provider_s or not model_s:
            raise ValueError("sandbox_generate: provider and model are required")
        if not prompt_s:
            raise ValueError("sandbox_generate: prompt is required")
        body: Dict[str, Any] = {
            "capability": str(capability or "output.text").strip() or "output.text",
            "provider": provider_s,
            "model": model_s,
            "prompt": prompt_s,
        }
        if system_prompt:
            body["system_prompt"] = str(system_prompt)
        if isinstance(messages, list) and messages:
            body["messages"] = [dict(item) for item in messages if isinstance(item, dict)]
        if isinstance(attachments, list) and attachments:
            body["attachments"] = [dict(item) for item in attachments if isinstance(item, dict)]
        if temperature is not None:
            body["temperature"] = float(temperature)
        if max_tokens is not None:
            body["max_tokens"] = int(max_tokens)
        return self._request_json(
            method="POST",
            url=self._url("/api/gateway/sandbox/generate"),
            body=body,
            timeout_s=timeout_s,
            label="sandbox_generate failed",
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
        return self._request_json(
            method="POST",
            url=self._url("/api/gateway/commands"),
            body=body,
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
        return self._request_json(
            method="POST",
            url=self._url("/api/gateway/attachments/ingest"),
            body=body,
            label="attachments_ingest failed",
        )

    def attachments_upload(
        self,
        *,
        session_id: str,
        file_path: str,
        filename: Optional[str] = None,
        content_type: Optional[str] = None,
        timeout_s: Optional[float] = None,
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
        headers = self._headers(mutating=True, extra={"Content-Type": content_type_header})
        req = urllib.request.Request(self._url("/api/gateway/attachments/upload"), data=body, method="POST", headers=headers)
        timeout = self._cfg.timeout_s if timeout_s is None else float(timeout_s)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
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

    def audio_transcribe(
        self,
        *,
        run_id: str,
        audio_artifact: Dict[str, Any],
        request_id: Optional[str] = None,
        language: Optional[str] = None,
        model: Optional[str] = None,
        timeout_s: Optional[float] = None,
    ) -> Dict[str, Any]:
        rid = str(run_id or "").strip()
        if not rid:
            raise ValueError("audio_transcribe: run_id is required")
        body: Dict[str, Any] = {"audio_artifact": audio_artifact}
        if request_id:
            body["request_id"] = str(request_id)
        if language:
            body["language"] = str(language)
        if model:
            body["model"] = str(model)
        return self._request_json(
            method="POST",
            url=self._url(f"/api/gateway/runs/{rid}/audio/transcribe"),
            body=body,
            timeout_s=timeout_s,
            label="audio_transcribe failed",
        )

    def voice_tts(
        self,
        *,
        run_id: str,
        text: str,
        provider: Optional[str] = None,
        voice: Optional[str] = None,
        fmt: Optional[str] = None,
        request_id: Optional[str] = None,
        model: Optional[str] = None,
        profile: Optional[str] = None,
        timeout_s: Optional[float] = None,
    ) -> Dict[str, Any]:
        rid = str(run_id or "").strip()
        if not rid:
            raise ValueError("voice_tts: run_id is required")
        body: Dict[str, Any] = {"text": str(text or "")}
        if provider:
            body["provider"] = str(provider)
        if voice:
            body["voice"] = str(voice)
        if fmt:
            body["format"] = str(fmt)
        if request_id:
            body["request_id"] = str(request_id)
        if model:
            body["model"] = str(model)
        if profile:
            body["profile"] = str(profile)
        return self._request_json(
            method="POST",
            url=self._url(f"/api/gateway/runs/{rid}/voice/tts"),
            body=body,
            timeout_s=timeout_s,
            label="voice_tts failed",
        )

    def image_generate(
        self,
        *,
        run_id: str,
        prompt: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        image_provider: Optional[str] = None,
        image_model: Optional[str] = None,
        size: Optional[str] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        fmt: Optional[str] = None,
        negative_prompt: Optional[str] = None,
        seed: Optional[int] = None,
        steps: Optional[int] = None,
        guidance_scale: Optional[float] = None,
        guidance_2: Optional[float] = None,
        count: Optional[int] = None,
        n: Optional[int] = None,
        seeds: Optional[List[int]] = None,
        lora_adapters: Optional[List[Dict[str, Any]]] = None,
        quality: Optional[str] = None,
        style: Optional[str] = None,
        request_id: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
        options: Optional[Dict[str, Any]] = None,
        timeout_s: Optional[float] = None,
    ) -> Dict[str, Any]:
        rid = str(run_id or "").strip()
        if not rid:
            raise ValueError("image_generate: run_id is required")
        body: Dict[str, Any] = {"prompt": str(prompt or "")}
        optional: Dict[str, Any] = {
            "provider": provider,
            "model": model,
            "image_provider": image_provider,
            "image_model": image_model,
            "size": size,
            "width": width,
            "height": height,
            "negative_prompt": negative_prompt,
            "seed": seed,
            "steps": steps,
            "guidance_scale": guidance_scale,
            "guidance_2": guidance_2,
            "count": count,
            "n": n,
            "seeds": seeds,
            "lora_adapters": lora_adapters,
            "quality": quality,
            "style": style,
            "request_id": request_id,
            "extra": extra,
        }
        _apply_optional_fields(body, optional)
        _merge_media_options(
            body,
            options,
            allowed_keys=(
                "size",
                "width",
                "height",
                "format",
                "negative_prompt",
                "seed",
                "steps",
                "guidance_scale",
                "guidance_2",
                "count",
                "n",
                "seeds",
                "lora_adapters",
                "quality",
                "style",
                "extra",
            ),
        )
        if fmt is not None:
            body["format"] = str(fmt)
        return self._request_json(
            method="POST",
            url=self._url(f"/api/gateway/runs/{rid}/images/generate"),
            body=body,
            timeout_s=max(float(self._cfg.timeout_s), 180.0) if timeout_s is None else float(timeout_s),
            label="image_generate failed",
        )

    def image_edit(
        self,
        *,
        run_id: str,
        prompt: str,
        image_artifact: Dict[str, Any],
        mask_artifact: Optional[Dict[str, Any]] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        image_provider: Optional[str] = None,
        image_model: Optional[str] = None,
        strength: Optional[float] = None,
        fmt: Optional[str] = None,
        negative_prompt: Optional[str] = None,
        seed: Optional[int] = None,
        steps: Optional[int] = None,
        guidance_scale: Optional[float] = None,
        guidance_2: Optional[float] = None,
        count: Optional[int] = None,
        n: Optional[int] = None,
        seeds: Optional[List[int]] = None,
        lora_adapters: Optional[List[Dict[str, Any]]] = None,
        request_id: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
        options: Optional[Dict[str, Any]] = None,
        timeout_s: Optional[float] = None,
    ) -> Dict[str, Any]:
        rid = str(run_id or "").strip()
        if not rid:
            raise ValueError("image_edit: run_id is required")
        body: Dict[str, Any] = {
            "prompt": str(prompt or ""),
            "image_artifact": dict(image_artifact or {}),
        }
        optional: Dict[str, Any] = {
            "mask_artifact": dict(mask_artifact or {}) if isinstance(mask_artifact, dict) else None,
            "provider": provider,
            "model": model,
            "image_provider": image_provider,
            "image_model": image_model,
            "strength": strength,
            "negative_prompt": negative_prompt,
            "seed": seed,
            "steps": steps,
            "guidance_scale": guidance_scale,
            "guidance_2": guidance_2,
            "count": count,
            "n": n,
            "seeds": seeds,
            "lora_adapters": lora_adapters,
            "request_id": request_id,
            "extra": extra,
        }
        _apply_optional_fields(body, optional)
        _merge_media_options(
            body,
            options,
            allowed_keys=(
                "format",
                "strength",
                "negative_prompt",
                "seed",
                "steps",
                "guidance_scale",
                "guidance_2",
                "count",
                "n",
                "seeds",
                "lora_adapters",
                "extra",
            ),
        )
        if fmt is not None:
            body["format"] = str(fmt)
        return self._request_json(
            method="POST",
            url=self._url(f"/api/gateway/runs/{rid}/images/edit"),
            body=body,
            timeout_s=max(float(self._cfg.timeout_s), 180.0) if timeout_s is None else float(timeout_s),
            label="image_edit failed",
        )

    def image_upscale(
        self,
        *,
        run_id: str,
        image_artifact: Dict[str, Any],
        image_provider: Optional[str] = None,
        image_model: Optional[str] = None,
        resolution: Optional[str] = None,
        softness: Optional[float] = None,
        quantize: Optional[int] = None,
        vae_tiling: Optional[bool] = None,
        fmt: Optional[str] = None,
        request_id: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
        timeout_s: Optional[float] = None,
    ) -> Dict[str, Any]:
        rid = str(run_id or "").strip()
        if not rid:
            raise ValueError("image_upscale: run_id is required")
        body: Dict[str, Any] = {
            "image_artifact": dict(image_artifact or {}),
        }
        optional: Dict[str, Any] = {
            "image_provider": image_provider,
            "image_model": image_model,
            "resolution": resolution,
            "softness": softness,
            "quantize": quantize,
            "vae_tiling": vae_tiling,
            "request_id": request_id,
        }
        _apply_optional_fields(body, optional)
        _merge_media_options(
            body,
            options,
            allowed_keys=("format", "resolution", "softness", "quantize", "vae_tiling"),
        )
        if fmt is not None:
            body["format"] = str(fmt)
        return self._request_json(
            method="POST",
            url=self._url(f"/api/gateway/runs/{rid}/images/upscale"),
            body=body,
            timeout_s=max(float(self._cfg.timeout_s), 180.0) if timeout_s is None else float(timeout_s),
            label="image_upscale failed",
        )

    def video_generate(
        self,
        *,
        run_id: str,
        prompt: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        video_provider: Optional[str] = None,
        video_model: Optional[str] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        frames: Optional[int] = None,
        fps: Optional[int] = None,
        fmt: Optional[str] = None,
        negative_prompt: Optional[str] = None,
        seed: Optional[int] = None,
        steps: Optional[int] = None,
        guidance_scale: Optional[float] = None,
        guidance_2: Optional[float] = None,
        flow_shift: Optional[float] = None,
        count: Optional[int] = None,
        n: Optional[int] = None,
        seeds: Optional[List[int]] = None,
        lora_adapters: Optional[List[Dict[str, Any]]] = None,
        request_id: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
        options: Optional[Dict[str, Any]] = None,
        timeout_s: Optional[float] = None,
    ) -> Dict[str, Any]:
        rid = str(run_id or "").strip()
        if not rid:
            raise ValueError("video_generate: run_id is required")
        body: Dict[str, Any] = {"prompt": str(prompt or "")}
        optional: Dict[str, Any] = {
            "provider": provider,
            "model": model,
            "video_provider": video_provider,
            "video_model": video_model,
            "width": width,
            "height": height,
            "frames": frames,
            "fps": fps,
            "negative_prompt": negative_prompt,
            "seed": seed,
            "steps": steps,
            "guidance_scale": guidance_scale,
            "guidance_2": guidance_2,
            "flow_shift": flow_shift,
            "count": count,
            "n": n,
            "seeds": seeds,
            "lora_adapters": lora_adapters,
            "request_id": request_id,
            "extra": extra,
        }
        _apply_optional_fields(body, optional)
        _merge_media_options(
            body,
            options,
            allowed_keys=(
                "width",
                "height",
                "frames",
                "fps",
                "format",
                "negative_prompt",
                "seed",
                "steps",
                "guidance_scale",
                "guidance_2",
                "flow_shift",
                "count",
                "n",
                "seeds",
                "lora_adapters",
                "extra",
            ),
        )
        if fmt is not None:
            body["format"] = str(fmt)
        return self._request_json(
            method="POST",
            url=self._url(f"/api/gateway/runs/{rid}/videos/generate"),
            body=body,
            timeout_s=max(float(self._cfg.timeout_s), 180.0) if timeout_s is None else float(timeout_s),
            label="video_generate failed",
        )

    def video_from_image(
        self,
        *,
        run_id: str,
        prompt: str,
        image_artifact: Dict[str, Any],
        provider: Optional[str] = None,
        model: Optional[str] = None,
        video_provider: Optional[str] = None,
        video_model: Optional[str] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        frames: Optional[int] = None,
        fps: Optional[int] = None,
        fmt: Optional[str] = None,
        negative_prompt: Optional[str] = None,
        seed: Optional[int] = None,
        steps: Optional[int] = None,
        guidance_scale: Optional[float] = None,
        guidance_2: Optional[float] = None,
        flow_shift: Optional[float] = None,
        strength: Optional[float] = None,
        count: Optional[int] = None,
        n: Optional[int] = None,
        seeds: Optional[List[int]] = None,
        lora_adapters: Optional[List[Dict[str, Any]]] = None,
        request_id: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
        options: Optional[Dict[str, Any]] = None,
        timeout_s: Optional[float] = None,
    ) -> Dict[str, Any]:
        rid = str(run_id or "").strip()
        if not rid:
            raise ValueError("video_from_image: run_id is required")
        body: Dict[str, Any] = {
            "prompt": str(prompt or ""),
            "image_artifact": dict(image_artifact or {}),
        }
        optional: Dict[str, Any] = {
            "provider": provider,
            "model": model,
            "video_provider": video_provider,
            "video_model": video_model,
            "width": width,
            "height": height,
            "frames": frames,
            "fps": fps,
            "negative_prompt": negative_prompt,
            "seed": seed,
            "steps": steps,
            "guidance_scale": guidance_scale,
            "guidance_2": guidance_2,
            "flow_shift": flow_shift,
            "strength": strength,
            "count": count,
            "n": n,
            "seeds": seeds,
            "lora_adapters": lora_adapters,
            "request_id": request_id,
            "extra": extra,
        }
        _apply_optional_fields(body, optional)
        _merge_media_options(
            body,
            options,
            allowed_keys=(
                "width",
                "height",
                "frames",
                "fps",
                "format",
                "negative_prompt",
                "seed",
                "steps",
                "guidance_scale",
                "guidance_2",
                "flow_shift",
                "strength",
                "count",
                "n",
                "seeds",
                "lora_adapters",
                "extra",
            ),
        )
        if fmt is not None:
            body["format"] = str(fmt)
        return self._request_json(
            method="POST",
            url=self._url(f"/api/gateway/runs/{rid}/videos/from_image"),
            body=body,
            timeout_s=max(float(self._cfg.timeout_s), 180.0) if timeout_s is None else float(timeout_s),
            label="video_from_image failed",
        )

    def music_generate(
        self,
        *,
        run_id: str,
        prompt: str,
        task: str = "text_to_music",
        music_provider: Optional[str] = None,
        music_model: Optional[str] = None,
        fmt: str = "wav",
        request_id: Optional[str] = None,
        lyrics: Optional[str] = None,
        timeout_s: Optional[float] = None,
    ) -> Dict[str, Any]:
        rid = str(run_id or "").strip()
        if not rid:
            raise ValueError("music_generate: run_id is required")
        body: Dict[str, Any] = {
            "prompt": str(prompt or ""),
            "task": str(task or "text_to_music"),
            "format": str(fmt or "wav"),
        }
        optional: Dict[str, Any] = {
            "music_provider": music_provider,
            "music_model": music_model,
            "request_id": request_id,
            "lyrics": lyrics,
        }
        for key, value in optional.items():
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            body[key] = value
        return self._request_json(
            method="POST",
            url=self._url(f"/api/gateway/runs/{rid}/music/generate"),
            body=body,
            timeout_s=max(float(self._cfg.timeout_s), 180.0) if timeout_s is None else float(timeout_s),
            label="music_generate failed",
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
        return self._request_json(
            method="GET",
            url=self._url(f"/api/gateway/sessions/{sid}/prompt_cache/status", query=query),
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
        return self._request_json(
            method="POST",
            url=self._url(f"/api/gateway/sessions/{sid}/prompt_cache/{op}"),
            body=body,
            label=label,
        )

    def list_run_artifacts(self, *, run_id: str, limit: int = 200) -> Dict[str, Any]:
        rid = str(run_id or "").strip()
        if not rid:
            raise ValueError("list_run_artifacts: run_id is required")
        query = {"limit": max(1, int(limit))}
        return self._request_json(
            method="GET",
            url=self._url(f"/api/gateway/runs/{rid}/artifacts", query=query),
            label="list_run_artifacts failed",
        )

    def get_run_artifact_metadata(self, *, run_id: str, artifact_id: str) -> Dict[str, Any]:
        rid = str(run_id or "").strip()
        aid = str(artifact_id or "").strip()
        if not rid:
            raise ValueError("get_run_artifact_metadata: run_id is required")
        if not aid:
            raise ValueError("get_run_artifact_metadata: artifact_id is required")
        return self._request_json(
            method="GET",
            url=self._url(f"/api/gateway/runs/{rid}/artifacts/{aid}"),
            label="get_run_artifact_metadata failed",
        )

    def download_run_artifact_content(
        self,
        *,
        run_id: str,
        artifact_id: str,
        max_bytes: int = 25_000_000,
        timeout_s: Optional[float] = None,
    ) -> Tuple[bytes, str]:
        rid = str(run_id or "").strip()
        aid = str(artifact_id or "").strip()
        if not rid:
            raise ValueError("download_run_artifact_content: run_id is required")
        if not aid:
            raise ValueError("download_run_artifact_content: artifact_id is required")
        url = self._url(f"/api/gateway/runs/{rid}/artifacts/{aid}/content")
        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        timeout = self._cfg.timeout_s if timeout_s is None else float(timeout_s)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
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
