"""HTTP transport for `fleetglint serve` (docs/architecture.md §4, spec §9)."""
import http.server
import importlib.resources
import json
import math
import sys
import threading
import traceback
import urllib.parse
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Protocol

from fleetglint import __version__

MAX_REQUEST_LINE = 2048
API_CONTENT_TYPE = "application/json; charset=utf-8"
RECORD_TYPES = ("run", "job", "inbox_item")
FILE_FIELDS = ("log_path", "result_path", "link")

SECURITY_HEADERS = (
    ("Cache-Control", "no-store"),
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
    ("X-Frame-Options", "DENY"),
    ("Content-Security-Policy",
     "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'"),
)

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".woff2": "font/woff2",
    ".webmanifest": "application/manifest+json",
    ".json": API_CONTENT_TYPE,
    ".ico": "image/x-icon",
}

ERROR_CODES = {
    400: "bad_request",
    404: "not_found",
    405: "method_not_allowed",
    414: "uri_too_long",
    421: "misdirected_request",
    500: "internal_error",
    501: "not_implemented",
}

NOT_BUILT_HTML = b"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<title>Fleetglint</title>
<body>
<h1>Fleetglint</h1>
<p>The web UI is not built in this checkout.</p>
<p>Build it with <code>pnpm -C ui install &amp;&amp; pnpm -C ui build</code>, then reload this page.</p>
<p>The API already works: <a href="/api/snapshot">/api/snapshot</a>.</p>
</body>
</html>
"""

_ERROR = object()


class Backend(Protocol):
    """Read model the server talks to; `query.py` implements it (architecture §4)."""

    def change_counter(self) -> int: ...

    def snapshot(self, now: datetime) -> dict: ...

    def record(self, now: datetime, source_id: str, type: str, id: str) -> dict | None: ...

    def file(self, now: datetime, source_id: str, type: str, id: str,
             field: str, index: int | None) -> dict | None: ...

    def quarantine(self, source_id: str) -> list[dict] | None: ...


def _default_clock() -> datetime:
    return datetime.now().astimezone()


def default_web_dir() -> Path:
    return Path(str(importlib.resources.files("fleetglint"))) / "web"


def weak_etag(counter: int, now: datetime) -> str:
    """`W/"<change_counter>-<floor(now/5)>"` (architecture §4.5)."""
    return f'W/"{counter}-{math.floor(now.timestamp() / 5)}"'


def etag_matches(header, etag: str) -> bool:
    """Whether an If-None-Match header matches `etag` (weak comparison)."""
    if not header:
        return False
    opaque = etag[2:] if etag.startswith("W/") else etag
    for part in header.split(","):
        part = part.strip()
        if part == "*":
            return True
        if part.startswith("W/"):
            part = part[2:]
        if part == opaque:
            return True
    return False


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = f"Fleetglint/{__version__}"
    sys_version = ""

    def log_message(self, format, *args):
        """No access log: the UI polls every few seconds."""

    def __getattr__(self, name):
        # Any method other than GET/HEAD gets 405, including ones with no do_ handler.
        if name.startswith("do_"):
            return self._method_not_allowed
        raise AttributeError(name)

    def do_GET(self):
        self._dispatch()

    def do_HEAD(self):
        self._dispatch()

    # ---- responses -------------------------------------------------------

    def _respond(self, status, body: bytes, content_type: str, etag=None, close=False, extra=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if etag:
            self.send_header("ETag", etag)
        for name, value in (extra or {}).items():
            self.send_header(name, value)
        for name, value in SECURITY_HEADERS:
            self.send_header(name, value)
        if close:
            self.send_header("Connection", "close")
            self.close_connection = True
        self.end_headers()
        if self.command != "HEAD" and body:
            self.wfile.write(body)

    def _json(self, status: int, data):
        try:
            body = json.dumps(data).encode("utf-8")
        except (TypeError, ValueError):
            traceback.print_exc()
            self._error(500, "internal_error", "internal server error")
            return
        self._respond(status, body, API_CONTENT_TYPE)

    def _error(self, status: int, code: str, message: str, extra=None):
        body = json.dumps({"api": 1, "error": {"code": code, "message": message}}).encode("utf-8")
        self._respond(status, body, API_CONTENT_TYPE, close=True, extra=extra)

    def _not_modified(self, etag: str):
        self.send_response(304)
        self.send_header("ETag", etag)
        for name, value in SECURITY_HEADERS:
            self.send_header(name, value)
        self.end_headers()

    def send_error(self, code, message=None, explain=None):
        """Keep stdlib-generated errors (bad request line, …) in the API's error shape."""
        self.requestline = getattr(self, "requestline", "")
        text = message or "request failed"
        self._error(code, ERROR_CODES.get(code, "error"), text)

    def _method_not_allowed(self):
        self._error(405, "method_not_allowed", "only GET and HEAD are allowed",
                    extra={"Allow": "GET, HEAD"})

    # ---- request handling ------------------------------------------------

    def parse_request(self):
        if len(self.raw_requestline) > MAX_REQUEST_LINE:
            self.requestline = ""
            self.command = ""
            self.request_version = ""
            self._error(414, "uri_too_long", "request line too long")
            return False
        return super().parse_request()

    def _dispatch(self):
        # No request body is ever read; a request that carries one cannot be
        # followed by another on the same connection.
        if self.headers.get("Content-Length", "0") not in ("", "0") or self.headers.get("Transfer-Encoding"):
            self.close_connection = True
        if not self._host_ok():
            self._error(421, "misdirected_request", "unexpected Host header")
            return
        parts = urllib.parse.urlsplit(self.path)
        if len(parts.query) > MAX_REQUEST_LINE:
            self._error(414, "uri_too_long", "query string too long")
            return
        if parts.path == "/api" or parts.path.startswith("/api/"):
            self._api(parts)
        else:
            self._static(parts.path)

    def _host_ok(self) -> bool:
        port = self.server.server_address[1]
        host = self.headers.get("Host")
        return host in (f"127.0.0.1:{port}", f"localhost:{port}")

    def _api(self, parts):
        query = urllib.parse.parse_qs(parts.query, keep_blank_values=True)
        path = parts.path
        if path == "/api/healthz":
            self._json(200, {"ok": True, "version": __version__})
        elif path == "/api/snapshot":
            self._snapshot()
        elif path == "/api/record":
            self._record(query)
        elif path == "/api/file":
            self._file(query)
        elif path.startswith("/api/sources/") and path.endswith("/quarantine") and path.count("/") == 4:
            self._quarantine(urllib.parse.unquote(path.split("/")[3]))
        else:
            self._error(404, "not_found", "unknown endpoint")

    # ---- API routes ------------------------------------------------------

    def _guard(self, fn, *args):
        """Run a backend call; log a bug and answer 500 without leaking details."""
        try:
            return fn(*args)
        except Exception:
            traceback.print_exc()
            self._error(500, "internal_error", "internal server error")
            return _ERROR

    def _snapshot(self):
        now = self.server.clock()
        counter = self._guard(self.server.backend.change_counter)
        if counter is _ERROR:
            return
        etag = weak_etag(counter, now)
        if etag_matches(self.headers.get("If-None-Match"), etag):
            self._not_modified(etag)
            return
        data = self._guard(self.server.backend.snapshot, now)
        if data is _ERROR:
            return
        body = self._dump(data)
        if body is None:
            return
        self._respond(200, body, API_CONTENT_TYPE, etag=etag)

    def _record(self, query):
        params = self._require(query, ("source_id", "type", "id"))
        if params is None:
            return
        if params["type"] not in RECORD_TYPES:
            self._error(400, "bad_request", "type must be run, job or inbox_item")
            return
        now = self.server.clock()
        counter = self._guard(self.server.backend.change_counter)
        if counter is _ERROR:
            return
        etag = weak_etag(counter, now)
        if etag_matches(self.headers.get("If-None-Match"), etag):
            self._not_modified(etag)
            return
        data = self._guard(self.server.backend.record, now, params["source_id"],
                           params["type"], params["id"])
        if data is _ERROR:
            return
        if data is None:
            self._error(404, "not_found", "unknown record")
            return
        body = self._dump(data)
        if body is None:
            return
        self._respond(200, body, API_CONTENT_TYPE, etag=etag)

    def _file(self, query):
        params = self._require(query, ("source_id", "type", "id", "field"))
        if params is None:
            return
        if params["type"] not in RECORD_TYPES:
            self._error(400, "bad_request", "type must be run, job or inbox_item")
            return
        if params["field"] not in FILE_FIELDS:
            self._error(400, "bad_request", "field must be log_path, result_path or link")
            return
        index = None
        if "index" in query:
            raw = query["index"][0]
            if not raw.isdigit():
                self._error(400, "bad_request", "index must be a non-negative integer")
                return
            index = int(raw)
        data = self._guard(self.server.backend.file, self.server.clock(), params["source_id"],
                           params["type"], params["id"], params["field"], index)
        if data is _ERROR:
            return
        if data is None:
            self._error(404, "not_found", "unknown record")
            return
        self._json(200, data)

    def _quarantine(self, source_id):
        if "/" in source_id:
            self._error(404, "not_found", "unknown source")
            return
        lines = self._guard(self.server.backend.quarantine, source_id)
        if lines is _ERROR:
            return
        if lines is None:
            self._error(404, "not_found", "unknown source")
            return
        self._json(200, {"api": 1, "source_id": source_id, "quarantine": lines})

    def _require(self, query, names):
        values = {}
        for name in names:
            found = query.get(name)
            if not found or not found[0]:
                self._error(400, "bad_request", f"missing query parameter: {name}")
                return None
            values[name] = found[0]
        return values

    def _dump(self, data):
        try:
            return json.dumps(data).encode("utf-8")
        except (TypeError, ValueError):
            traceback.print_exc()
            self._error(500, "internal_error", "internal server error")
            return None

    # ---- static files ----------------------------------------------------

    def _static(self, raw_path):
        root = self.server.web_root
        try:
            decoded = urllib.parse.unquote(raw_path)
        except ValueError:
            decoded = ""
        target = None
        if decoded and "\x00" not in decoded:
            try:
                target = (root / decoded.lstrip("/")).resolve()
            except (OSError, RuntimeError):
                target = None
        if target is not None and target.is_file() and target.is_relative_to(root):
            self._send_file(target)
            return
        index = root / "index.html"
        if index.is_file():
            self._send_file(index)
        else:
            self._respond(200, NOT_BUILT_HTML, "text/html; charset=utf-8")

    def _send_file(self, path: Path):
        try:
            data = path.read_bytes()
        except OSError:
            self._error(404, "not_found", "not found")
            return
        self._respond(200, data, CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream"))


def make_server(backend: Backend, port: int, web_dir: Path | None = None, clock=None) -> http.server.ThreadingHTTPServer:
    """Bind 127.0.0.1:`port` (0 = ephemeral) and return the server; call serve_forever()."""
    root = Path(web_dir).resolve() if web_dir is not None else default_web_dir()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.backend = backend
    server.web_root = root
    server.clock = clock or _default_clock
    return server


def run(args) -> int:
    """`fleetglint serve`: the ingest thread plus the HTTP server (docs/architecture.md §8)."""
    from fleetglint import config, ingest, query

    try:
        cfg = config.load(getattr(args, "config", None))
    except config.ConfigError as exc:
        print(f"fleetglint serve: {exc}", file=sys.stderr)
        return 3
    port = cfg.port if getattr(args, "port", None) is None else args.port

    # query.py and ingest.py land in parallel PRs; the lead wires these two calls
    # once they merge.
    backend = query.backend(cfg)
    try:
        server = make_server(backend, port)
    except OSError as exc:
        print(f"fleetglint serve: cannot listen on 127.0.0.1:{port}: {exc}", file=sys.stderr)
        return 3
    threading.Thread(target=ingest.serve, args=(cfg,), daemon=True).start()

    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"Fleetglint on {url} (read-only)", flush=True)
    if getattr(args, "open", False):
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
