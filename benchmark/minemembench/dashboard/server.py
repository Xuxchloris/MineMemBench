"""Minimal loopback HTTP/SSE server for read-only benchmark observability."""

from __future__ import annotations

import json
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .compare import build_same_seed_comparison
from .index import ResultIndex
from .replay import build_replay

_STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}
_STATIC_ROOT = Path(__file__).with_name("static")
_SENSITIVE_KEYS = {
    "authorization",
    "api_key",
    "apikey",
    "password",
    "secret",
    "cookie",
    "set_cookie",
    "access_token",
    "refresh_token",
    "headers",
    "environment",
    "environ",
}


def sanitize(value: Any) -> Any:
    """Redact secret-shaped nested fields without hiding token metrics."""

    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for raw_key, child in value.items():
            key = str(raw_key)
            normalized = key.lower().replace("-", "_")
            if normalized in _SENSITIVE_KEYS or normalized.endswith("_api_key"):
                safe[key] = "[REDACTED]"
            else:
                safe[key] = sanitize(child)
        return safe
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize(item) for item in value]
    return value


class DashboardHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        index: ResultIndex,
        *,
        poll_interval: float = 1.0,
    ) -> None:
        self.index = index
        self.poll_interval = max(0.1, poll_interval)
        super().__init__(server_address, DashboardRequestHandler)


class DashboardRequestHandler(BaseHTTPRequestHandler):
    server: DashboardHTTPServer
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:
        # Keep the benchmark console quiet; producer logs are independent.
        return

    def _security_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
            "base-uri 'none'; frame-ancestors 'none'",
        )

    def _bytes(
        self,
        payload: bytes,
        *,
        status: HTTPStatus = HTTPStatus.OK,
        content_type: str,
    ) -> None:
        self.send_response(status)
        self._security_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, value: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        payload = json.dumps(
            sanitize(value), ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        self._bytes(payload, status=status, content_type="application/json; charset=utf-8")

    def _error(self, status: HTTPStatus, category: str) -> None:
        self._json({"error": category, "status": int(status)}, status=status)

    def _serve_static(self, path: str) -> bool:
        spec = _STATIC.get(path)
        if spec is None:
            return False
        filename, content_type = spec
        try:
            payload = (_STATIC_ROOT / filename).read_bytes()
        except OSError:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "static_unavailable")
            return True
        self._bytes(payload, content_type=content_type)
        return True

    def _events(self) -> None:
        self.send_response(HTTPStatus.OK)
        self._security_headers()
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        last_revision: str | None = None
        keepalive_at = time.monotonic()
        try:
            while True:
                snapshot = self.server.index.refresh()
                if snapshot.revision != last_revision:
                    payload = json.dumps(
                        {
                            "revision": snapshot.revision,
                            "partial_file_count": snapshot.partial_file_count,
                            "invalid_file_count": snapshot.invalid_file_count,
                        },
                        separators=(",", ":"),
                    )
                    self.wfile.write(f"event: revision\ndata: {payload}\n\n".encode())
                    self.wfile.flush()
                    last_revision = snapshot.revision
                    keepalive_at = time.monotonic()
                elif time.monotonic() - keepalive_at >= 15:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    keepalive_at = time.monotonic()
                time.sleep(self.server.poll_interval)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        parsed = urlparse(self.path)
        try:
            if self._serve_static(parsed.path):
                return
            if parsed.path == "/api/events":
                self._events()
                return
            if parsed.path == "/api/health":
                snapshot = self.server.index.refresh()
                self._json(
                    {
                        "status": "ok",
                        "revision": snapshot.revision,
                        "partial_file_count": snapshot.partial_file_count,
                        "invalid_file_count": snapshot.invalid_file_count,
                    }
                )
                return
            if parsed.path == "/api/snapshot":
                snapshot = self.server.index.refresh()
                self._json(snapshot.model_dump(mode="json"))
                return
            if parsed.path.startswith("/api/runs/"):
                self.server.index.refresh()
                run_id = parsed.path.removeprefix("/api/runs/")
                result = self.server.index.get_run(run_id)
                if result is None:
                    self._error(HTTPStatus.NOT_FOUND, "run_not_found")
                    return
                self._json(
                    {"run_id": run_id, "result": result.model_dump(mode="json")}
                )
                return
            if parsed.path.startswith("/api/replay/"):
                self.server.index.refresh()
                run_id = parsed.path.removeprefix("/api/replay/")
                result = self.server.index.get_run(run_id)
                if result is None:
                    self._error(HTTPStatus.NOT_FOUND, "run_not_found")
                    return
                replay = build_replay(result)
                self._json(replay.model_dump(mode="json"))
                return
            if parsed.path == "/api/compare":
                self.server.index.refresh()
                anchor = parse_qs(parsed.query).get("anchor", [None])[0]
                if anchor is None:
                    self._error(HTTPStatus.BAD_REQUEST, "anchor_required")
                    return
                campaign_id = self.server.index.get_campaign_id(anchor)
                comparison = build_same_seed_comparison(
                    self.server.index.iter_runs(
                        campaign_id=campaign_id, accepted_only=True
                    ),
                    anchor_run_id=anchor,
                )
                if comparison is None:
                    self._error(HTTPStatus.NOT_FOUND, "run_not_found")
                    return
                self._json(comparison.model_dump(mode="json"))
                return
            self._error(HTTPStatus.NOT_FOUND, "not_found")
        except Exception:  # noqa: BLE001 - sanitized service boundary
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error")

    def _method_not_allowed(self) -> None:
        self._error(HTTPStatus.METHOD_NOT_ALLOWED, "method_not_allowed")

    do_POST = _method_not_allowed
    do_PUT = _method_not_allowed
    do_PATCH = _method_not_allowed
    do_DELETE = _method_not_allowed


def create_server(
    results_dir: str | Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    poll_interval: float = 1.0,
) -> DashboardHTTPServer:
    """Construct the server without starting a thread or writing files."""

    index = ResultIndex(results_dir)
    index.refresh()
    return DashboardHTTPServer(
        (host, port), index, poll_interval=poll_interval
    )
