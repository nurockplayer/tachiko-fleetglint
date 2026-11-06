"""Tests for the HTTP transport (`fleetglint server`), docs/architecture.md §4."""
import argparse
import contextlib
import http.client
import io
import json
import math
import os
import pathlib
import signal
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.parse
from datetime import datetime, timedelta, timezone
from unittest import mock

from fleetglint import __version__, server

NOW = datetime(2026, 11, 6, 3, 40, 20, tzinfo=timezone(timedelta(hours=9)))
WINDOW = math.floor(NOW.timestamp() / 5)

SECURITY = {
    "cache-control": "no-store",
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "x-frame-options": "DENY",
    "content-security-policy": ("default-src 'self'; img-src 'self' data:; "
                                "style-src 'self' 'unsafe-inline'; frame-ancestors 'none'"),
}

INDEX_HTML = b"<!doctype html><title>Fake UI</title><p>SPA INDEX</p>"
STATIC_FILES = {
    "app.js": ("console.log(1)", "text/javascript"),
    "style.css": ("body{}", "text/css"),
    "logo.svg": ("<svg/>", "image/svg+xml"),
    "pic.png": ("\x89PNG", "image/png"),
    "font.woff2": ("woff2", "font/woff2"),
    "site.webmanifest": ('{"name":"Fleetglint"}', "application/manifest+json"),
}


class FakeBackend:
    def __init__(self):
        self.counter = 7
        self.fail = None
        self.calls = []
        self.records = {
            ("src@host", "run", "cx.1"): {
                "api": 1, "record": {"ref": {"type": "run", "id": "cx.1", "source_id": "src@host"}},
                "full": {}, "relations": {}, "history": [], "usage": None,
            }
        }
        self.files = {
            ("src@host", "job", "j1", "log_path", None): {
                "api": 1, "readable": True, "path": "/tmp/x.log", "size": 3,
                "truncated": False, "text": "hi\n", "redactions": 0,
            }
        }
        self.quarantined = {"src@host": [{"position": 3, "reason": "bad_json", "excerpt": "{"}]}

    def _maybe_fail(self, name):
        if self.fail == name:
            raise RuntimeError("backend exploded: very secret path /Users/x")

    def change_counter(self):
        self._maybe_fail("change_counter")
        return self.counter

    def snapshot(self, now):
        self._maybe_fail("snapshot")
        return {"api": 1, "generated_at": now.isoformat(), "sources": [], "fake": True}

    def board(self, now):
        self._maybe_fail("board")
        return {"api": 1, "generated_at": now.isoformat(), "fake_board": True}

    def record(self, now, source_id, type, id):
        self._maybe_fail("record")
        self.calls.append((source_id, type, id))
        return self.records.get((source_id, type, id))

    def file(self, now, source_id, type, id, field, index):
        self._maybe_fail("file")
        self.calls.append((source_id, type, id, field, index))
        return self.files.get((source_id, type, id, field, index))

    def quarantine(self, source_id):
        self._maybe_fail("quarantine")
        self.calls.append((source_id,))
        return self.quarantined.get(source_id)


def start_server(web_dir, backend=None):
    backend = backend or FakeBackend()
    srv = server.make_server(backend, 0, web_dir, clock=lambda: NOW)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    return srv, thread


def stop_server(srv, thread):
    srv.shutdown()
    srv.server_close()
    thread.join(timeout=5)


def request(port, method="GET", path="/", headers=None, host=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        if host is None:
            conn.request(method, path, headers=headers or {})
        else:
            conn.putrequest(method, path, skip_host=True)
            if host is not False:
                conn.putheader("Host", host)
            for name, value in (headers or {}).items():
                conn.putheader(name, value)
            conn.endheaders()
        response = conn.getresponse()
        body = response.read()
        return response.status, {k.lower(): v for k, v in response.getheaders()}, body
    finally:
        conn.close()


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = pathlib.Path(cls.tmp.name)
        cls.web = cls.root / "web"
        cls.web.mkdir()
        (cls.web / "index.html").write_bytes(INDEX_HTML)
        for name, (content, _) in STATIC_FILES.items():
            (cls.web / name).write_text(content)
        (cls.web / "assets").mkdir()
        (cls.web / "assets" / "index-abc.js").write_text("asset")
        cls.secret = cls.root / "secret.txt"
        cls.secret.write_text("TOP SECRET")
        (cls.web / "link.txt").symlink_to(cls.secret)
        cls.srv, cls.thread = start_server(cls.web)
        cls.port = cls.srv.server_address[1]

    @classmethod
    def tearDownClass(cls):
        stop_server(cls.srv, cls.thread)
        cls.tmp.cleanup()

    def setUp(self):
        self.backend = FakeBackend()
        self.srv.backend = self.backend

    def get(self, path, headers=None, method="GET"):
        return request(self.port, method, path, headers)

    def assert_security(self, headers):
        for name, value in SECURITY.items():
            self.assertEqual(headers.get(name), value, name)
        self.assertFalse([name for name in headers if name.startswith("access-control-")])

    def assert_error(self, status, headers, body, code):
        self.assertTrue(headers["content-type"].startswith("application/json"))
        data = json.loads(body)
        self.assertEqual(data["api"], 1)
        self.assertEqual(data["error"]["code"], code)
        self.assertIsInstance(data["error"]["message"], str)
        self.assert_security(headers)

    # ---- snapshot --------------------------------------------------------

    def test_snapshot_returns_json_and_weak_etag(self):
        status, headers, body = self.get("/api/snapshot")
        self.assertEqual(status, 200)
        self.assertTrue(headers["content-type"].startswith("application/json; charset=utf-8"))
        self.assertEqual(json.loads(body)["fake"], True)
        self.assertEqual(headers["etag"], f'W/"7-{WINDOW}"')
        self.assertEqual(headers["content-length"], str(len(body)))
        self.assert_security(headers)

    def test_snapshot_if_none_match_gives_304_without_body(self):
        _, headers, _ = self.get("/api/snapshot")
        for sent in (headers["etag"], headers["etag"][2:], "*", f' {headers["etag"]} , "x"'):
            status, headers304, body = self.get("/api/snapshot", {"If-None-Match": sent})
            self.assertEqual(status, 304, sent)
            self.assertEqual(body, b"")
            self.assertEqual(headers304["etag"], headers["etag"])
            self.assert_security(headers304)

    def test_snapshot_changed_counter_misses_etag(self):
        self.backend.counter = 8
        status, _, _ = self.get("/api/snapshot", {"If-None-Match": f'W/"7-{WINDOW}"'})
        self.assertEqual(status, 200)

    # ---- board -----------------------------------------------------------

    def test_board_returns_json_and_weak_etag(self):
        status, headers, body = self.get("/api/board")
        self.assertEqual(status, 200)
        self.assertTrue(headers["content-type"].startswith("application/json; charset=utf-8"))
        self.assertEqual(json.loads(body)["fake_board"], True)
        self.assertEqual(headers["etag"], f'W/"7-{WINDOW}"')
        self.assertEqual(headers["content-length"], str(len(body)))
        self.assert_security(headers)

    def test_board_if_none_match_gives_304(self):
        _, headers, _ = self.get("/api/board")
        status, headers304, body = self.get("/api/board", {"If-None-Match": headers["etag"]})
        self.assertEqual(status, 304)
        self.assertEqual(body, b"")
        self.assertEqual(headers304["etag"], headers["etag"])
        self.assert_security(headers304)

    # ---- record ----------------------------------------------------------

    def test_record_passes_params_and_returns_json(self):
        url = "/api/record?" + urllib.parse.urlencode(
            {"source_id": "src@host", "type": "run", "id": "cx.1"})
        status, headers, body = self.get(url)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["full"], {})
        self.assertEqual(headers["etag"], f'W/"7-{WINDOW}"')
        self.assertEqual(self.backend.calls, [("src@host", "run", "cx.1")])
        self.assert_security(headers)

    def test_record_304(self):
        url = "/api/record?source_id=src%40host&type=run&id=cx.1"
        status, headers, _ = self.get(url, {"If-None-Match": f'W/"7-{WINDOW}"'})
        self.assertEqual(status, 304)
        self.assert_security(headers)
        self.assertEqual(self.backend.calls, [("src@host", "run", "cx.1")])

    def test_record_unknown_is_404(self):
        status, headers, body = self.get("/api/record?source_id=src&type=run&id=nope")
        self.assertEqual(status, 404)
        self.assert_error(status, headers, body, "not_found")

    def test_record_unknown_wins_over_if_none_match(self):
        status, headers, body = self.get("/api/record?source_id=src&type=run&id=nope",
                                         {"If-None-Match": "*"})
        self.assertEqual(status, 404)
        self.assert_error(status, headers, body, "not_found")

    def test_record_requires_params(self):
        for url in ("/api/record", "/api/record?source_id=src&type=run",
                    "/api/record?source_id=&type=run&id=x",
                    "/api/record?source_id=src&type=session&id=x"):
            status, headers, body = self.get(url)
            self.assertEqual(status, 400, url)
            self.assert_error(status, headers, body, "bad_request")

    # ---- file ------------------------------------------------------------

    def test_file_returns_backend_payload(self):
        url = "/api/file?source_id=src@host&type=job&id=j1&field=log_path"
        status, headers, body = self.get(url)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["text"], "hi\n")
        self.assertEqual(self.backend.calls, [("src@host", "job", "j1", "log_path", None)])
        self.assert_security(headers)

    def test_file_index(self):
        url = "/api/file?source_id=src@host&type=job&id=j1&field=link&index=2"
        status, _, _ = self.get(url)
        self.assertEqual(status, 404)  # record known, this link is not
        self.assertEqual(self.backend.calls, [("src@host", "job", "j1", "link", 2)])

    def test_file_bad_params(self):
        for url in ("/api/file?source_id=src&type=job&id=j1",
                    "/api/file?source_id=src&type=job&id=j1&field=nope",
                    "/api/file?source_id=src&type=session&id=j1&field=log_path",
                    "/api/file?source_id=src&type=job&id=j1&field=log_path&index=x",
                    "/api/file?source_id=src&type=job&id=j1&field=log_path&index=-1"):
            status, headers, body = self.get(url)
            self.assertEqual(status, 400, url)
            self.assert_error(status, headers, body, "bad_request")

    def test_file_unknown_record_is_404(self):
        status, headers, body = self.get("/api/file?source_id=x&type=job&id=j&field=log_path")
        self.assertEqual(status, 404)
        self.assert_error(status, headers, body, "not_found")

    def test_file_non_ascii_index_is_400(self):
        url = "/api/file?source_id=src&type=job&id=j1&field=link&index=%C2%B2"
        status, headers, body = self.get(url)
        self.assertEqual(status, 400)
        self.assert_error(status, headers, body, "bad_request")
        self.assertEqual(self.backend.calls, [])

    # ---- quarantine ------------------------------------------------------

    def test_quarantine_percent_decoded(self):
        status, headers, body = self.get("/api/sources/src%40host/quarantine")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["api"], 1)
        self.assertEqual(data["source_id"], "src@host")
        self.assertEqual(data["quarantine"][0]["reason"], "bad_json")
        self.assertEqual(self.backend.calls, [("src@host",)])
        self.assert_security(headers)

    def test_quarantine_unknown_source_is_404(self):
        status, headers, body = self.get("/api/sources/nope/quarantine")
        self.assertEqual(status, 404)
        self.assert_error(status, headers, body, "not_found")

    def test_quarantine_encoded_slash_is_not_a_source(self):
        status, headers, body = self.get("/api/sources/a%2Fb/quarantine")
        self.assertEqual(status, 404)
        self.assert_error(status, headers, body, "not_found")

    # ---- healthz and unknown endpoints -----------------------------------

    def test_healthz(self):
        status, headers, body = self.get("/api/healthz")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"ok": True, "version": __version__})
        self.assert_security(headers)

    def test_unknown_api_path_is_404_json(self):
        for path in ("/api", "/api/", "/api/nope", "/api/sources/x", "/api/sources/x/quarantine/"):
            status, headers, body = self.get(path)
            self.assertEqual(status, 404, path)
            self.assert_error(status, headers, body, "not_found")

    # ---- methods, Host, sizes -------------------------------------------

    def test_other_methods_are_405_with_allow(self):
        for method in ("POST", "PUT", "PATCH", "DELETE", "OPTIONS", "BREW"):
            status, headers, body = request(self.port, method, "/api/snapshot")
            self.assertEqual(status, 405, method)
            self.assertEqual(headers["allow"], "GET, HEAD")
            self.assert_error(status, headers, body, "method_not_allowed")

    def test_head_matches_get_without_body(self):
        for path in ("/api/snapshot", "/api/healthz", "/api/nope", "/style.css"):
            get_status, get_headers, get_body = self.get(path)
            head_status, head_headers, head_body = self.get(path, method="HEAD")
            self.assertEqual(head_status, get_status, path)
            self.assertEqual(head_body, b"", path)
            for name in ("content-type", "content-length", "etag", "cache-control",
                         "content-security-policy"):
                self.assertEqual(head_headers.get(name), get_headers.get(name), (path, name))

    def test_host_header_must_match_loopback_port(self):
        status, headers, body = self.get("/api/healthz", {"Host": "evil.example"})
        self.assertEqual(status, 421)
        self.assert_error(status, headers, body, "misdirected_request")
        for host in (f"127.0.0.1:{self.port + 1}", "127.0.0.1", f"localhost:{self.port + 1}",
                     "evil.example:80"):
            status, _, _ = self.get("/api/healthz", {"Host": host})
            self.assertEqual(status, 421, host)
        for host in (f"127.0.0.1:{self.port}", f"localhost:{self.port}"):
            status, _, _ = request(self.port, "GET", "/api/healthz", host=host)
            self.assertEqual(status, 200, host)

    def test_missing_host_is_421(self):
        status, headers, body = request(self.port, "GET", "/api/snapshot", host=False)
        self.assertEqual(status, 421)
        self.assert_error(status, headers, body, "misdirected_request")

    def test_long_request_line_is_414(self):
        status, headers, body = self.get("/" + "a" * 2100)
        self.assertEqual(status, 414)
        self.assert_error(status, headers, body, "uri_too_long")

    def test_long_query_is_414(self):
        status, headers, body = self.get("/api/record?source_id=" + "a" * 2100)
        self.assertEqual(status, 414)
        self.assert_error(status, headers, body, "uri_too_long")

    def test_query_at_the_limit_is_accepted(self):
        path = "/api/record?source_id=" + "a" * 1700
        status, _, _ = self.get(path)
        self.assertEqual(status, 400)  # params valid enough: type/id missing

    # ---- backend failures ------------------------------------------------

    def test_backend_exception_is_500_without_details(self):
        self.backend.fail = "snapshot"
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            status, headers, body = self.get("/api/snapshot")
        self.assertEqual(status, 500)
        self.assert_error(status, headers, body, "internal_error")
        self.assertNotIn("secret", body.decode())
        self.assertNotIn("backend exploded", body.decode())
        self.assertIn("backend exploded", err.getvalue())

    def test_backend_failure_in_record_is_500(self):
        self.backend.fail = "record"
        with contextlib.redirect_stderr(io.StringIO()):
            status, headers, body = self.get("/api/record?source_id=s&type=run&id=x")
        self.assertEqual(status, 500)
        self.assert_error(status, headers, body, "internal_error")

    # ---- security headers and CORS --------------------------------------

    def test_no_cors_headers_even_with_origin(self):
        status, headers, body = self.get("/api/snapshot", {"Origin": "http://evil.example"})
        self.assertEqual(status, 200)
        self.assert_security(headers)
        self.assertNotIn("access-control-allow-origin", headers)

    # ---- static files ----------------------------------------------------

    def test_index_is_served_at_root(self):
        status, headers, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertTrue(headers["content-type"].startswith("text/html"))
        self.assertEqual(body, INDEX_HTML)
        self.assert_security(headers)

    def test_static_content_types(self):
        for name, (content, content_type) in STATIC_FILES.items():
            status, headers, body = self.get("/" + name)
            self.assertEqual(status, 200, name)
            self.assertTrue(headers["content-type"].startswith(content_type), (name, headers["content-type"]))
            self.assertEqual(body.decode(), content, name)

    def test_hashed_asset_is_served(self):
        status, headers, body = self.get("/assets/index-abc.js")
        self.assertEqual(status, 200)
        self.assertTrue(headers["content-type"].startswith("text/javascript"))
        self.assertEqual(body, b"asset")

    def test_spa_fallback_to_index(self):
        for path in ("/attention", "/run/cx.1", "/run/a/b/c"):
            status, headers, body = self.get(path)
            self.assertEqual(status, 200, path)
            self.assertEqual(body, INDEX_HTML, path)
            self.assertTrue(headers["content-type"].startswith("text/html"), path)

    def test_path_traversal_never_leaves_web_dir(self):
        for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/assets/../../secret.txt",
                     "/..%2fsecret.txt", "/link.txt"):
            status, _, body = self.get(path)
            self.assertEqual(status, 200, path)
            self.assertNotIn(b"TOP SECRET", body, path)
            self.assertEqual(body, INDEX_HTML, path)

    def test_symlinked_index_outside_web_dir_is_not_served(self):
        web = self.root / "symlink-web"
        web.mkdir(exist_ok=True)
        (web / "index.html").symlink_to(self.secret)
        srv, thread = start_server(web)
        try:
            status, _, body = request(srv.server_address[1], "GET", "/")
            self.assertEqual(status, 200)
            self.assertNotIn(b"TOP SECRET", body)
            self.assertEqual(body, server.NOT_BUILT_HTML)
        finally:
            stop_server(srv, thread)

    def test_not_built_page_when_no_index(self):
        empty = self.root / "empty-web"
        empty.mkdir(exist_ok=True)
        srv, thread = start_server(empty)
        try:
            port = srv.server_address[1]
            for path in ("/", "/attention"):
                status, headers, body = request(port, "GET", path)
                self.assertEqual(status, 200, path)
                self.assertTrue(headers["content-type"].startswith("text/html"))
                self.assertIn(b"pnpm -C ui install", body)
                self.assertIn(b"pnpm -C ui build", body)
                self.assertIn(b"/api/snapshot", body)
            status, _, body = request(port, "GET", "/api/healthz")
            self.assertEqual(status, 200)
        finally:
            stop_server(srv, thread)


class RunTest(unittest.TestCase):
    def test_sigterm_stops_serve_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {**os.environ, "PYTHONPATH": "src", "XDG_STATE_HOME": str(pathlib.Path(tmp) / "state"),
                   "XDG_CONFIG_HOME": str(pathlib.Path(tmp) / "config")}
            process = subprocess.Popen(
                [sys.executable, "-m", "fleetglint", "serve", "--port", "0"],
                env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                self.assertIn("read-only", process.stdout.readline())
                process.send_signal(signal.SIGTERM)
                _, err = process.communicate(timeout=15)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()
        self.assertEqual(process.returncode, 0, err)
        self.assertNotIn("Traceback", err)

    def test_service_lock_held_exits_3_without_traceback(self):
        from fleetglint import config, ingest
        with tempfile.TemporaryDirectory() as tmp:
            config_path = pathlib.Path(tmp) / "config.toml"
            db_path = pathlib.Path(tmp) / "db.sqlite"
            config_path.write_text(f'[ingest]\ndb_path = "{db_path}"\n')
            args = argparse.Namespace(config=str(config_path), port=0, open=False)
            err, out = io.StringIO(), io.StringIO()
            with ingest.hold_service_lock(config.load(config_path)):
                with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
                    code = server.run(args)
        self.assertEqual(code, 3)
        self.assertIn("is running", err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())


class MakeServerTest(unittest.TestCase):
    def test_binding_does_not_resolve_the_host_name(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch("socket.getfqdn", side_effect=AssertionError("getfqdn called")):
            srv, thread = start_server(pathlib.Path(tmp))
            try:
                self.assertEqual(srv.server_name, "127.0.0.1")
                self.assertEqual(srv.server_port, srv.server_address[1])
            finally:
                stop_server(srv, thread)

    def test_binds_loopback_only_and_reports_port(self):
        with tempfile.TemporaryDirectory() as tmp:
            srv, thread = start_server(pathlib.Path(tmp))
            try:
                self.assertEqual(srv.server_address[0], "127.0.0.1")
                self.assertGreater(srv.server_address[1], 0)
            finally:
                stop_server(srv, thread)

    def test_port_in_use_raises_oserror(self):
        with tempfile.TemporaryDirectory() as tmp:
            srv, thread = start_server(pathlib.Path(tmp))
            try:
                with self.assertRaises(OSError):
                    server.make_server(FakeBackend(), srv.server_address[1], pathlib.Path(tmp))
            finally:
                stop_server(srv, thread)


if __name__ == "__main__":
    unittest.main()
