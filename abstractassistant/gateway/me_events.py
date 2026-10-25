"""The person's own event stream on the gateway (framework backlog 1046/1047).

Two routes, always the CALLER's own stream (no parameter names a person):

- ``GET /api/gateway/me/events?after=<seq>&limit=<n>`` — a catch-up page
  ``{stream, events[], next_after, head, more}``, events oldest first;
- ``GET /api/gateway/me/events/stream`` — Server-Sent Events: ``id: <sequence>``,
  ``event: <type>``, ``data: <CloudEvents JSON>``, ``: keep-alive`` comments.
  A reconnect sends ``Last-Event-ID: <last sequence consumed>`` and gets exactly
  what came after it.

:class:`EventFollower` is one daemon thread: catch-up pages first (history,
``live=False``), then the SSE tail (``live=True``), reconnecting with
``Last-Event-ID`` and a 1..30 s backoff after any break. It stops on a 404 (a
gateway without the stream: state ``unsupported``, callers keep their polls) or
on two 401/403 in a row (``unauthorized``). The connection is re-read from the
client factory at each reconnect; a different gateway or identity starts over
from sequence 0 (``on_reset``).
"""

from __future__ import annotations

import json
import logging
import socket
import threading
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

from .client import GatewayClient, GatewayHttpError

__all__ = [
    "ME_EVENTS_PATH",
    "ME_EVENTS_STREAM_PATH",
    "EventFollower",
    "MeEventsClient",
    "SseFrameParser",
]

logger = logging.getLogger(__name__)

ME_EVENTS_PATH = "/api/gateway/me/events"
ME_EVENTS_STREAM_PATH = "/api/gateway/me/events/stream"
PAGE_LIMIT = 1000
# The server sends a keep-alive comment every heartbeat; a socket silent for
# several of them is a dead connection, not a quiet one.
HEARTBEAT_S = 15.0
READ_TIMEOUT_S = 4 * HEARTBEAT_S


class SseFrameParser:
    """Incremental SSE parser: feed lines, get ``(id, event, data)`` per frame."""

    def __init__(self) -> None:
        self._id: Optional[str] = None
        self._event: Optional[str] = None
        self._data: List[str] = []

    def feed(self, line: str) -> Optional[Tuple[Optional[str], Optional[str], str]]:
        line = line.rstrip("\r\n")
        if line == "":
            if not self._data:
                self._id, self._event = None, None
                return None
            frame = (self._id, self._event, "\n".join(self._data))
            self._id, self._event, self._data = None, None, []
            return frame
        if line.startswith(":"):
            return None  # comment / keep-alive
        name, _, value = line.partition(":")
        value = value[1:] if value.startswith(" ") else value
        if name == "id":
            self._id = value
        elif name == "event":
            self._event = value
        elif name == "data":
            self._data.append(value)
        return None


class MeEventsClient:
    """The two read routes over one :class:`GatewayClient` (its URL, auth, timeout)."""

    def __init__(self, gateway: GatewayClient) -> None:
        self._gateway = gateway

    @property
    def identity(self) -> Tuple[str, str, str, str]:
        cfg = self._gateway.config
        return (cfg.base_url, cfg.auth_token, cfg.user_id, cfg.session_id)

    def events(self, *, after: int = 0, limit: int = PAGE_LIMIT) -> Dict[str, Any]:
        """One catch-up page (raises :class:`GatewayHttpError` with the status)."""
        url = self._gateway._url(ME_EVENTS_PATH, {"after": int(after), "limit": int(limit)})
        headers = {"Accept": "application/json"}
        headers.update(self._gateway._headers())
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self._gateway.config.timeout_s) as resp:
                raw = resp.read() or b""
        except urllib.error.HTTPError as exc:
            raise GatewayHttpError(f"me/events failed: HTTP {exc.code}", status=int(exc.code or 0)) from None
        body = json.loads(raw.decode("utf-8") or "{}")
        if not isinstance(body, dict) or not isinstance(body.get("events"), list):
            raise GatewayHttpError("me/events answered without an events list", status=200)
        return body

    def open_stream(self, *, last_event_id: int = 0, heartbeat_s: float = HEARTBEAT_S) -> Any:
        """Open the SSE tail; the resume point rides ``Last-Event-ID``."""
        url = self._gateway._url(ME_EVENTS_STREAM_PATH, {"heartbeat_s": heartbeat_s})
        headers = {"Accept": "text/event-stream"}
        headers.update(self._gateway._headers())
        if last_event_id > 0:
            headers["Last-Event-ID"] = str(int(last_event_id))
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            return urllib.request.urlopen(req, timeout=max(READ_TIMEOUT_S, 4 * float(heartbeat_s)))
        except urllib.error.HTTPError as exc:
            raise GatewayHttpError(f"me/events/stream failed: HTTP {exc.code}", status=int(exc.code or 0)) from None

    @staticmethod
    def frames(resp: Any) -> Iterator[Dict[str, Any]]:
        """Each event of an open stream (keep-alives and malformed frames skipped)."""
        parser = SseFrameParser()
        while True:
            raw = resp.readline()
            if not raw:
                return  # the server closed the stream
            frame = parser.feed(raw.decode("utf-8", "replace"))
            if frame is None:
                continue
            try:
                event = json.loads(frame[2])
            except ValueError:
                continue
            if isinstance(event, dict):
                if "sequence" not in event and frame[0] and frame[0].isdigit():
                    event["sequence"] = int(frame[0])
                yield event


class EventFollower:
    """Catch-up, then the SSE tail, reconnecting with ``Last-Event-ID``.

    ``on_event(event, live)`` runs on the follower thread for every event, in
    order, never twice. ``on_state`` gets ``connecting|live|unsupported|
    unauthorized|stopped``; ``on_reset`` runs when the connection's identity
    changed (the cursor went back to 0)."""

    def __init__(
        self,
        client_factory: Callable[[], Optional[MeEventsClient]],
        *,
        on_event: Callable[[Dict[str, Any], bool], None],
        on_state: Optional[Callable[[str], None]] = None,
        on_reset: Optional[Callable[[], None]] = None,
        max_backoff_s: float = 30.0,
        heartbeat_s: float = HEARTBEAT_S,
    ) -> None:
        self._factory = client_factory
        self._on_event = on_event
        self._on_state = on_state or (lambda _s: None)
        self._on_reset = on_reset or (lambda: None)
        self._max_backoff = float(max_backoff_s)
        self._heartbeat_s = float(heartbeat_s)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._response: Any = None
        self._identity: Optional[Tuple[str, ...]] = None
        self._auth_failures = 0
        self.cursor = 0
        self.caught_up = False
        self.state = "stopped"
        self.connections = 0

    # -------------------------------------------------------------- control

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="me-events", daemon=True)
        self._thread.start()

    def stop(self, *, join_s: float = 0.0) -> None:
        self._stop.set()
        resp = self._response
        if resp is not None:
            # A read blocked in this thread's recv is only released by shutting
            # the socket down; closing the file object alone does not.
            try:
                sock = getattr(getattr(getattr(resp, "fp", None), "raw", None), "_sock", None)
                if sock is not None:
                    sock.shutdown(socket.SHUT_RDWR)
            except Exception:  # noqa: BLE001
                pass
            try:
                resp.close()
            except Exception:  # noqa: BLE001
                pass
        thread = self._thread
        if join_s > 0 and thread is not None:
            thread.join(join_s)
        self._set_state("stopped")

    @property
    def live(self) -> bool:
        return self.state == "live"

    # ------------------------------------------------------------- internals

    def _set_state(self, state: str) -> None:
        if state == self.state:
            return
        self.state = state
        try:
            self._on_state(state)
        except Exception:  # noqa: BLE001
            logger.debug("me events: state listener failed", exc_info=True)

    def _deliver(self, event: Dict[str, Any], live: bool) -> None:
        try:
            seq = int(event.get("sequence") or 0)
        except (TypeError, ValueError):
            return
        if seq <= self.cursor:
            return  # replayed frame: never delivered twice
        self.cursor = seq
        try:
            self._on_event(event, live)
        except Exception:  # noqa: BLE001 - a UI bug must not stop the stream
            logger.debug("me events: listener failed", exc_info=True)

    def _refused(self, status: int) -> bool:
        if status in (401, 403):
            self._auth_failures += 1
            if self._auth_failures >= 2:
                self._set_state("unauthorized")
                return True
        elif status == 404:
            self._set_state("unsupported")
            return True
        return False

    def _client(self) -> Optional[MeEventsClient]:
        client = self._factory()
        if client is None:
            return None
        identity = client.identity
        if self._identity is not None and identity != self._identity:
            self.cursor = 0
            self.caught_up = False
            try:
                self._on_reset()
            except Exception:  # noqa: BLE001
                logger.debug("me events: reset listener failed", exc_info=True)
        self._identity = identity
        return client

    def catch_up(self, client: MeEventsClient) -> None:
        while not self._stop.is_set():
            page = client.events(after=self.cursor, limit=PAGE_LIMIT)
            self._auth_failures = 0
            for event in page.get("events") or []:
                if isinstance(event, dict):
                    self._deliver(event, False)
            if not page.get("more"):
                self.caught_up = True
                return

    def follow_once(self, client: MeEventsClient) -> None:
        resp = client.open_stream(last_event_id=self.cursor, heartbeat_s=self._heartbeat_s)
        self._response = resp
        self._auth_failures = 0
        self.connections += 1
        self._set_state("live")
        try:
            for event in client.frames(resp):
                if self._stop.is_set():
                    return
                self._deliver(event, True)
        finally:
            self._response = None
            try:
                resp.close()
            except Exception:  # noqa: BLE001
                pass

    def _loop(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            self._set_state("connecting")
            try:
                client = self._client()
                if client is not None:
                    if not self.caught_up:
                        self.catch_up(client)
                    if self.caught_up and not self._stop.is_set():
                        self.follow_once(client)
                        backoff = 1.0
            except GatewayHttpError as exc:
                if self._refused(int(exc.status or 0)):
                    return
            except Exception:  # noqa: BLE001 - resets, timeouts, refused connections
                logger.debug("me events: stream broke", exc_info=True)
            if self._stop.is_set():
                break
            self._stop.wait(backoff)
            backoff = min(self._max_backoff, backoff * 2)
