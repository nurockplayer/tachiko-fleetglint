"""Release-gate tests (docs/architecture.md §10): the installed program, driven as a user does.

Each test owns a temporary installation (HOME and every XDG/agent directory inside a
temp dir), starts `python -m fleetglint serve --port 0`, reads the URL from its first
stdout line and talks to it with `http.client`. Polling waits are bounded and only used
here; every server is stopped in a cleanup.
"""
import http.client
import json
import os
import re
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
FIXTURES = ROOT / "tests" / "fixtures"
CANARY = "CANARY-CONTENT-8841"
SECRET = "sk-" + "a1B2c3D4e5F6g7H8i9J0k1L2"
START_TIMEOUT_S = 10
WAIT_TIMEOUT_S = 10
CONFIG = """[ingest]
poll_s = 0.1
adapter_poll_s = 0.1
"""


def stamp(**delta):
    return (datetime.now(timezone.utc) + timedelta(**delta)).astimezone().isoformat()


def local_hostname():
    return socket.gethostname().split(".")[0].lower()


def source_for(prefix):
    return f"{prefix}@{local_hostname()}"


def run_record(id, source, **extra):
    record = {"v": 1, "type": "run", "id": id, "source_id": source,
              "updated_at": stamp(), "observed_at": stamp(), "state": "running",
              "agent": "codex-cli", "started_at": stamp()}
    record.update(extra)
    return record


def job_record(id, source, **extra):
    record = {"v": 1, "type": "job", "id": id, "source_id": source,
              "updated_at": stamp(), "observed_at": stamp(), "state": "running",
              "command_summary": "sleep 5", "started_at": stamp()}
    record.update(extra)
    return record


def inbox_record(id, source, **extra):
    record = {"v": 1, "type": "inbox_item", "id": id, "source_id": source,
              "updated_at": stamp(), "state": "open", "role_id": "lead",
              "kind": "message", "created_at": stamp(),
              "subject": {"type": "external", "kind": "url",
                          "url": "https://example.com/item"}}
    record.update(extra)
    return record


def jsonl(records):
    return "".join(json.dumps(record) + "\n" for record in records).encode("utf-8")


def by_id(items):
    return {item["ref"]["id"]: item for item in items}


def _drain(stream, sink):
    try:
        for line in stream:
            sink.append(line)
    except (OSError, ValueError):
        pass
    finally:
        try:
            stream.close()
        except OSError:
            pass


class Gate:
    """One isolated Fleetglint installation under a temporary directory."""

    def __init__(self, base):
        self.base = Path(base)
        self.home = self.base / "home"
        self.state = self.base / "state"
        self.config_dir = self.base / "config"
        self.claude = self.base / "claude"
        self.codex = self.base / "codex"
        for path in (self.home, self.state, self.config_dir, self.claude, self.codex):
            path.mkdir(parents=True, exist_ok=True)
        self.config_path = self.config_dir / "fleetglint" / "config.toml"
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(CONFIG, encoding="utf-8")
        self.db_path = self.state / "fleetglint" / "fleetglint.sqlite"
        self.env = os.environ.copy()
        self.env.update({
            "HOME": str(self.home),
            "XDG_STATE_HOME": str(self.state),
            "XDG_CONFIG_HOME": str(self.config_dir),
            "CLAUDE_CONFIG_DIR": str(self.claude),
            "CODEX_HOME": str(self.codex),
            "PYTHONPATH": str(SRC),
        })
        self.proc = None
        self.port = None
        self._stdout = []
        self._stderr = []
        self._threads = []

    # -- process -----------------------------------------------------------

    def start(self):
        self._stdout = []
        self._stderr = []
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "fleetglint", "--config", str(self.config_path),
             "serve", "--port", "0"],
            cwd=str(ROOT), env=self.env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        self._threads = [threading.Thread(target=_drain, args=(self.proc.stdout, self._stdout),
                                          daemon=True),
                         threading.Thread(target=_drain, args=(self.proc.stderr, self._stderr),
                                          daemon=True)]
        for thread in self._threads:
            thread.start()
        deadline = time.monotonic() + START_TIMEOUT_S
        while time.monotonic() < deadline:
            match = re.search(r"http://127\.0\.0\.1:(\d+)/", "".join(self._stdout))
            if match:
                self.port = int(match.group(1))
                return self
            if self.proc.poll() is not None:
                self._join()
                raise AssertionError(
                    f"serve exited with {self.proc.returncode} before printing a URL: "
                    f"{self.stderr_text()}")
            time.sleep(0.02)
        self.stop()
        raise AssertionError(f"serve printed no URL within {START_TIMEOUT_S} s")

    def stop(self, sig=signal.SIGTERM):
        if self.proc is not None and self.proc.poll() is None:
            self.proc.send_signal(sig)
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)
        self._join()

    def kill(self):
        if self.proc is not None and self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait(timeout=10)
        self._join()

    def _join(self, timeout=5):
        for thread in self._threads:
            thread.join(timeout)
        self._threads = []

    def stdout_text(self):
        return "".join(self._stdout)

    def stderr_text(self):
        return "".join(self._stderr)

    # -- HTTP --------------------------------------------------------------

    def request(self, method="GET", path="/", headers=None, host=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
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

    def json(self, path):
        status, _, body = self.request("GET", path)
        if status != 200:
            raise AssertionError(f"GET {path} returned {status}: {body[:500]!r}")
        return json.loads(body)

    def snapshot(self):
        return self.json("/api/snapshot")

    def record(self, source_id, record_type, record_id):
        query = urllib.parse.urlencode({"source_id": source_id, "type": record_type,
                                        "id": record_id})
        return self.json(f"/api/record?{query}")

    def file(self, source_id, record_type, record_id, field):
        query = urllib.parse.urlencode({"source_id": source_id, "type": record_type,
                                        "id": record_id, "field": field})
        return self.json(f"/api/file?{query}")

    def quarantine(self, source_id):
        return self.json(f"/api/sources/{urllib.parse.quote(source_id, safe='')}/quarantine")

    # -- waiting -----------------------------------------------------------

    def wait(self, what, predicate, timeout=WAIT_TIMEOUT_S, interval=0.05):
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            try:
                last = predicate()
            except (OSError, http.client.HTTPException, ValueError, sqlite3.Error):
                last = None
            if last:
                return last
            time.sleep(interval)
        raise AssertionError(f"timed out waiting for {what}; last={last!r}")

    def wait_records(self, pairs, timeout=WAIT_TIMEOUT_S):
        """Wait until every (type, id) pair is in the snapshot; return the snapshot."""
        wanted = {(record_type, record_id) for record_type, record_id in pairs}
        return self.wait(
            f"records {sorted(wanted)}",
            lambda: (lambda snap: snap if wanted <= _snapshot_ids(snap) else None)(self.snapshot()),
            timeout)

    # -- database (read-only) ---------------------------------------------

    def db_rows(self, sql, params=()):
        conn = sqlite3.connect(f"{self.db_path.as_uri()}?mode=ro", uri=True, timeout=5)
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def db_value(self, sql, params=(), default=None):
        try:
            rows = self.db_rows(sql, params)
        except sqlite3.Error:
            return default
        return rows[0][0] if rows else default

    # -- CLI ---------------------------------------------------------------

    def run_cli(self, *args, input=None):
        return subprocess.run(
            [sys.executable, "-m", "fleetglint", "--config", str(self.config_path), *args],
            input=input, cwd=str(ROOT), env=self.env, capture_output=True, timeout=30)

    def emit(self, record):
        result = self.run_cli("emit", input=json.dumps(record).encode("utf-8"))
        if result.returncode != 0:
            raise AssertionError(f"emit failed ({result.returncode}): "
                                 f"{result.stderr.decode('utf-8', 'replace')}")
        return result

    def doctor(self):
        return self.run_cli("doctor")

    # -- files -------------------------------------------------------------

    def sources_root(self):
        return self.state / "fleetglint" / "sources"

    def source_path(self, source_id, *parts):
        directory = self.sources_root() / source_id
        directory.mkdir(parents=True, exist_ok=True)
        path = directory.joinpath(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def write_segment(self, source_id, seq, data):
        path = self.source_path(source_id, f"{seq:010d}.ndjson")
        path.write_bytes(data)
        return path


def _snapshot_ids(snap):
    return {(item["ref"]["type"], item["ref"]["id"])
            for group in ("runs", "jobs", "inbox", "sessions")
            for item in snap[group]}


class GateTest(unittest.TestCase):
    """One isolated installation per test; factories for extra installations."""

    def setUp(self):
        self.gate = self.new_gate()

    def new_gate(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        gate = Gate(tmp.name)
        self.addCleanup(gate.stop)
        return gate

    def assert_absent(self, needle, body, label):
        if isinstance(body, bytes):
            body = body.decode("utf-8", "replace")
        self.assertNotIn(needle, body, f"{label}: {needle!r} leaked")


class CleanEnvironmentGateTest(GateTest):
    """§10 item 1: an emitted record shows up without a restart."""

    def test_clean_environment_emit_shows_without_restart(self):
        gate = self.gate
        gate.start()
        empty = gate.snapshot()
        self.assertEqual(empty["api"], 1)
        self.assertEqual((empty["runs"], empty["jobs"], empty["inbox"], empty["sessions"]),
                         ([], [], [], []))
        self.assertEqual(empty["counts"]["attention"], 0)

        source = source_for("gate")
        gate.emit(run_record("r1", source))
        gate.emit(job_record("j1", source))
        gate.emit(inbox_record("i1", source))

        snap = gate.wait_records([("run", "r1"), ("job", "j1"), ("inbox_item", "i1")])
        self.assertEqual(by_id(snap["runs"])["r1"]["state"], "running")
        self.assertEqual(by_id(snap["jobs"])["j1"]["state"], "running")
        self.assertEqual(by_id(snap["inbox"])["i1"]["display_state"], "open")
        self.assertIn(source, {item["source_id"] for item in snap["sources"]})
        # The same process served the whole test: nothing was restarted.
        self.assertIsNone(gate.proc.poll())


class JobRelationsGateTest(GateTest):
    """§10 item 2: a detached job names its run, the run waits on it, and updates land live."""

    def test_detached_job_relations_and_terminal_update(self):
        gate = self.gate
        gate.start()
        source = source_for("gate")
        run = run_record("lead-run", source, waits_on=[{"type": "job", "id": "job-1"}])
        job = job_record("job-1", source, run={"type": "run", "id": "lead-run"})
        gate.emit(run)
        gate.emit(job)
        gate.wait_records([("run", "lead-run"), ("job", "job-1")])

        job_view = gate.record(source, "job", "job-1")
        owner = job_view["record"]["run"]
        self.assertEqual((owner["type"], owner["id"]), ("run", "lead-run"))
        self.assertTrue(owner["resolved"])
        self.assertEqual([item["id"] for item in job_view["relations"]["waited_on_by"]],
                         ["lead-run"])

        run_view = gate.record(source, "run", "lead-run")
        waits = run_view["record"]["waits_on"]
        self.assertEqual([(item["type"], item["id"]) for item in waits], [("job", "job-1")])
        self.assertTrue(waits[0]["resolved"])
        self.assertEqual([item["id"] for item in run_view["relations"]["jobs"]], ["job-1"])

        gate.emit(job_record("job-1", source, run={"type": "run", "id": "lead-run"},
                             state="done", ended_at=stamp(), exit_code=0))
        snap = gate.wait(
            "the job's terminal record",
            lambda: (lambda snap: snap if by_id(snap["jobs"]).get("job-1", {}).get("state")
                      == "done" else None)(gate.snapshot()))
        finished = by_id(snap["jobs"])["job-1"]
        self.assertEqual(finished["display_state"], "done")
        self.assertEqual(finished["exit_code"], 0)


class LivenessGateTest(GateTest):
    """§10 item 3: stale, lost and a discontinuity-driven unknown."""

    def test_stale_lost_and_discontinuity(self):
        gate = self.gate
        gate.start()
        source = source_for("gate")
        gate.emit(run_record("stale-run", source, updated_at=stamp(hours=-1),
                             observed_at=stamp(hours=-1)))
        child = subprocess.Popen([sys.executable, "-c", "pass"])
        child.wait()
        gate.emit(run_record("lost-run", source,
                             process={"host": local_hostname(), "pid": child.pid}))

        gap_source = source_for("gap")
        gate.write_segment(gap_source, 1, jsonl([run_record("gap-run", gap_source)]))

        snap = gate.wait(
            "the stale, lost and gap records",
            lambda: (lambda snap: snap if {"stale-run", "lost-run", "gap-run"}
                      <= set(by_id(snap["runs"])) else None)(gate.snapshot()))
        runs = by_id(snap["runs"])
        self.assertEqual(runs["stale-run"]["display_state"], "stale")
        self.assertEqual(runs["stale-run"]["evidence"]["kind"], "expired")
        self.assertEqual(runs["lost-run"]["display_state"], "lost")
        self.assertEqual(runs["lost-run"]["evidence"]["kind"], "process_gone")
        self.assertEqual(runs["gap-run"]["display_state"], "running")

        # A segment gap turns the source (and its records) into a discontinuity.
        gate.write_segment(gap_source, 3, jsonl([run_record("gap-run", gap_source)]))

        def broken():
            snap = gate.snapshot()
            sources = {item["source_id"]: item for item in snap["sources"]}
            if sources.get(gap_source, {}).get("status") != "discontinuity":
                return None
            if by_id(snap["runs"])["gap-run"]["display_state"] != "unknown":
                return None
            return snap

        snap = gate.wait("the gap source to become a discontinuity", broken)
        self.assertEqual(by_id(snap["runs"])["gap-run"]["display_state"], "unknown")
        self.assertEqual(by_id(snap["runs"])["gap-run"]["evidence"]["kind"], "source_problem")
        # Other sources stay usable.
        self.assertEqual(by_id(snap["runs"])["stale-run"]["display_state"], "stale")


class SafetyGateTest(GateTest):
    """§10 item 4: bad lines, symlinks, huge logs and secrets are contained."""

    def test_malformed_oversize_symlink_tail_and_secrets(self):
        gate = self.gate
        source = source_for("gate")

        after = run_record("after-big", source)
        segment = (b'{"bad": "' + SECRET.encode("ascii") + b'"\n'
                   + b"x" * (5 * 1024 * 1024) + b"\n"
                   + json.dumps(after).encode("utf-8") + b"\n")
        gate.write_segment(source, 1, segment)

        outside = gate.base / "outside.txt"
        outside.write_text("outside content\n", encoding="utf-8")
        link = gate.source_path(source, "logs", "out.log")
        link.symlink_to(outside)
        big_log = gate.source_path(source, "logs", "big.log")
        big_log.write_bytes(b"a" * (10 * 1024 * 1024 - 4) + b"END\n")
        secret_log = gate.source_path(source, "logs", "secret.log")
        secret_log.write_text(f"token {SECRET}\n", encoding="utf-8")

        gate.start()
        gate.wait_records([("run", "after-big")])
        gate.emit(job_record("symlink-job", source, log_path=str(link)))
        gate.emit(job_record("big-job", source, log_path=str(big_log)))
        gate.emit(job_record("secret-log-job", source, log_path=str(secret_log)))
        gate.emit(run_record("secret-run", source, title=f"worker {SECRET}",
                             summary=f"token {SECRET}"))
        snap = gate.wait_records([("job", "symlink-job"), ("job", "big-job"),
                                  ("job", "secret-log-job"), ("run", "secret-run")])

        reasons = {entry["reason"] for entry in gate.quarantine(source)["quarantine"]}
        self.assertIn("invalid_json", reasons)
        self.assertIn("too_large", reasons)
        self.assertIn("after-big", by_id(snap["runs"]))

        jobs = by_id(snap["jobs"])
        self.assertFalse(jobs["symlink-job"]["log"]["readable"])
        symlink_read = gate.file(source, "job", "symlink-job", "log_path")
        self.assertFalse(symlink_read["readable"])
        self.assertEqual(symlink_read["reason"], "outside_allowed_roots")

        big_read = gate.file(source, "job", "big-job", "log_path")
        self.assertTrue(big_read["readable"])
        self.assertEqual(big_read["size"], big_log.stat().st_size)
        self.assertTrue(big_read["truncated"])
        tail = big_read["text"].encode("utf-8")
        self.assertLessEqual(len(tail), 64 * 1024)
        self.assertTrue(tail.endswith(b"END\n"))

        log_read = gate.file(source, "job", "secret-log-job", "log_path")
        self.assertTrue(log_read["readable"])
        self.assertGreaterEqual(log_read["redactions"], 1)

        bodies = [
            ("snapshot", json.dumps(snap)),
            ("record secret-run", gate.request(
                "GET", "/api/record?" + urllib.parse.urlencode(
                    {"source_id": source, "type": "run", "id": "secret-run"}))[2]),
            ("record secret-log-job", gate.request(
                "GET", "/api/record?" + urllib.parse.urlencode(
                    {"source_id": source, "type": "job", "id": "secret-log-job"}))[2]),
            ("record after-big", gate.request(
                "GET", "/api/record?" + urllib.parse.urlencode(
                    {"source_id": source, "type": "run", "id": "after-big"}))[2]),
            ("file big-job", gate.request(
                "GET", "/api/file?" + urllib.parse.urlencode(
                    {"source_id": source, "type": "job", "id": "big-job",
                     "field": "log_path"}))[2]),
            ("file symlink-job", gate.request(
                "GET", "/api/file?" + urllib.parse.urlencode(
                    {"source_id": source, "type": "job", "id": "symlink-job",
                     "field": "log_path"}))[2]),
            ("file secret-log-job", gate.request(
                "GET", "/api/file?" + urllib.parse.urlencode(
                    {"source_id": source, "type": "job", "id": "secret-log-job",
                     "field": "log_path"}))[2]),
            ("quarantine", gate.request(
                "GET", "/api/sources/" + urllib.parse.quote(source, safe="")
                + "/quarantine")[2]),
            ("healthz", gate.request("GET", "/api/healthz")[2]),
        ]
        for label, body in bodies:
            self.assert_absent(SECRET, body, label)
        self.assertNotIn("outside content", symlink_read.get("text", ""))


class KillMidBatchGateTest(GateTest):
    """§10 item 5: SIGKILL mid-ingest, restart, and compare with an uninterrupted run."""

    TOTAL = 20000
    # Kill once this many of the 20,000 lines are committed: the ingest is still running
    # and the rest of the segment is left for the restarted server.
    THRESHOLD = 15000

    def payload(self, source):
        record_stamp = stamp()
        lines = []
        for index in range(self.TOTAL):
            lines.append(json.dumps({
                "v": 1, "type": "run", "id": f"kill-{index:05d}", "source_id": source,
                "updated_at": record_stamp, "observed_at": record_stamp,
                "state": "running", "agent": "codex-cli", "started_at": record_stamp}))
        return ("\n".join(lines) + "\n").encode("utf-8")

    def count(self, gate, source):
        return gate.db_value("SELECT count(*) FROM history WHERE source_id = ?", (source,),
                             default=0)

    def test_kill_during_ingest_loses_nothing(self):
        source = source_for("kill")
        data = self.payload(source)
        control = self.new_gate()
        killed = self.new_gate()
        control.write_segment(source, 1, data)
        killed.write_segment(source, 1, data)

        # The run that is not killed: the same segment, ingested in one pass.
        result = control.run_cli("ingest", "--once")
        self.assertEqual(result.returncode, 0,
                         result.stdout.decode("utf-8", "replace")
                         + result.stderr.decode("utf-8", "replace"))
        self.assertEqual(self.count(control, source), self.TOTAL)

        killed.start()
        killed.wait(
            "a partially ingested segment",
            lambda: self.THRESHOLD <= self.count(killed, source) < self.TOTAL,
            timeout=14, interval=0.1)
        killed.kill()
        killed.start()
        killed.wait("the rest of the segment after the restart",
                    lambda: self.count(killed, source) == self.TOTAL, timeout=14)
        killed.stop()

        records = "SELECT id, json FROM records WHERE source_id = ? ORDER BY id"
        history = ("SELECT id, count(*) FROM history WHERE source_id = ? "
                   "GROUP BY id ORDER BY id")
        self.assertEqual(killed.db_rows(records, (source,)),
                         control.db_rows(records, (source,)))
        self.assertEqual(killed.db_rows(history, (source,)),
                         control.db_rows(history, (source,)))
        self.assertEqual(self.count(killed, source), self.TOTAL)
        self.assertEqual(killed.db_value(
            "SELECT count(DISTINCT id) FROM history WHERE source_id = ?", (source,)),
            self.TOTAL)
        self.assertEqual(killed.db_value(
            "SELECT count(*) FROM records WHERE source_id = ?", (source,)), self.TOTAL)


class RequestSafetyGateTest(GateTest):
    """§10 item 7: methods, Host, Origin and cache headers."""

    def test_request_safety_methods_host_origin_and_cache(self):
        gate = self.gate
        gate.start()

        for method in ("POST", "PUT", "DELETE"):
            status, headers, body = gate.request(method, "/api/snapshot")
            self.assertEqual(status, 405, method)
            self.assertEqual(headers.get("allow"), "GET, HEAD")
            self.assertEqual(json.loads(body)["error"]["code"], "method_not_allowed")

        status, _, body = gate.request("GET", "/api/snapshot", host="evil.example:1234")
        self.assertEqual(status, 421)
        self.assertEqual(json.loads(body)["error"]["code"], "misdirected_request")

        status, headers, body = gate.request(
            "GET", "/api/snapshot", headers={"Origin": "http://evil.example"})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["api"], 1)
        self.assertFalse([name for name in headers if name.startswith("access-control-")])

        for path in ("/api/snapshot", "/api/healthz"):
            status, headers, _ = gate.request("GET", path)
            self.assertEqual(status, 200, path)
            self.assertEqual(headers.get("cache-control"), "no-store", path)


# -- first run (§10 readme paragraph) --------------------------------------

_CONTENT_KEYS = {"content", "text", "input", "arguments", "command", "output"}
_CLAUDE_SESSION = "11111111-1111-4111-8111-111111111111"
_CODEX_IDS = {"22222222-2222-4222-8222-222222222222",
              "33333333-3333-4333-8333-333333333333"}


def _canary(value):
    if isinstance(value, str):
        return f"{value} {CANARY}"
    return _inject(value)


def _inject(value):
    """Add the canary to every message body, tool input/output and command."""
    if isinstance(value, dict):
        return {key: _canary(item) if key in _CONTENT_KEYS else _inject(item)
                for key, item in value.items()}
    if isinstance(value, list):
        return [_inject(item) for item in value]
    return value


def _refresh(value, moment):
    """Point every timestamp in the copied shape at `moment` so the sessions are current."""
    if isinstance(value, dict):
        return {key: (moment if key == "timestamp" and isinstance(item, str)
                      else _refresh(item, moment))
                for key, item in value.items()}
    if isinstance(value, list):
        return [_refresh(item, moment) for item in value]
    return value


def copy_with_canary(source, target):
    """Copy a fixture transcript tree, canary in every content field and fresh timestamps."""
    now = datetime.now(timezone.utc)
    for path in sorted(Path(source).rglob("*.jsonl")):
        destination = Path(target) / path.relative_to(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        for index, raw in enumerate(path.read_text(encoding="utf-8").splitlines()):
            if not raw.strip():
                continue
            moment = (now - timedelta(minutes=10) + timedelta(seconds=index)).isoformat()
            record = _refresh(_inject(json.loads(raw)), moment)
            lines.append(json.dumps(record))
        destination.write_text("\n".join(lines) + "\n", encoding="utf-8")


class FirstRunGateTest(GateTest):
    """First run on a machine with only Claude Code, only Codex, and neither."""

    def check_first_run(self, gate, expected_sessions, adapter_name, session_summary):
        gate.start()
        if expected_sessions:
            snap = gate.wait(
                "the imported sessions",
                lambda: (lambda snap: snap if {item["ref"]["id"] for item in snap["sessions"]}
                          == set(expected_sessions) else None)(gate.snapshot()))
        else:
            snap = gate.snapshot()
            self.assertEqual(snap["sessions"], [])

        self.assertEqual(snap["runs"], [])
        self.assertEqual(snap["jobs"], [])
        self.assertEqual(snap["inbox"], [])
        self.assertEqual(snap["attention"], [])
        for key in ("running", "waiting", "stale_lost_unknown"):
            self.assertEqual(snap["counts"][key], 0, key)
        self.assertEqual(snap["counts"]["attention"], 0)
        for item in snap["sessions"]:
            self.assertEqual(item["state"], "unknown")
            self.assertNotIn(item["display_state"], {"running", "waiting", "done", "failed"})

        doctor = gate.doctor()
        output = doctor.stdout.decode("utf-8", "replace")
        self.assertEqual(doctor.returncode, 0,
                         output + doctor.stderr.decode("utf-8", "replace"))
        self.assertIn("no problems found", output)
        if expected_sessions:
            self.assertIn(f"adapter {adapter_name}", output)
            self.assertIn(session_summary, output)
        else:
            self.assertIn("not present", output)

        # Re-scans are idempotent: records, history and the change counter stop moving.
        time.sleep(0.5)
        before = self.counters(gate)
        time.sleep(0.5)
        after = self.counters(gate)
        self.assertEqual(before, after)

        bodies = [("snapshot", json.dumps(snap))]
        for item in snap["sessions"]:
            ref = item["ref"]
            bodies.append((f"record {ref['id']}", gate.request(
                "GET", "/api/record?" + urllib.parse.urlencode(
                    {"source_id": ref["source_id"], "type": ref["type"],
                     "id": ref["id"]}))[2]))
        if snap["sessions"]:
            bodies.append(("quarantine", gate.request(
                "GET", "/api/sources/"
                + urllib.parse.quote(snap["sessions"][0]["ref"]["source_id"], safe="")
                + "/quarantine")[2]))
        bodies.append(("healthz", gate.request("GET", "/api/healthz")[2]))
        for label, body in bodies:
            self.assert_absent(CANARY, body, label)

        gate.stop()
        for suffix in ("", "-wal", "-shm"):
            path = Path(str(gate.db_path) + suffix)
            if path.exists():
                self.assert_absent(CANARY, path.read_bytes(), f"sqlite file {path.name}")
        self.assert_absent(CANARY, gate.stdout_text(), "server stdout")
        self.assert_absent(CANARY, gate.stderr_text(), "server stderr")

    @staticmethod
    def counters(gate):
        return (gate.db_value("SELECT count(*) FROM records", default=0),
                gate.db_value("SELECT count(*) FROM history", default=0),
                gate.db_value("SELECT value FROM meta WHERE key = 'change_counter'",
                              default="0"))

    def test_first_run_with_only_claude_code(self):
        gate = self.gate
        copy_with_canary(FIXTURES / "claude_code" / "projects", gate.claude / "projects")
        main = (gate.claude / "projects" / "-Users-me-work-demo"
                / f"{_CLAUDE_SESSION}.jsonl")
        extra = {
            "type": "assistant", "sessionId": _CLAUDE_SESSION,
            "timestamp": stamp(minutes=-9), "cwd": "/Users/me/work/demo",
            "message": {"id": "msg_canary", "model": "claude-opus-5-5",
                        "usage": {"input_tokens": 1, "output_tokens": 1},
                        "content": [
                            {"type": "tool_use", "name": "Bash",
                             "input": {"command": f"echo {CANARY}"}},
                            {"type": "text", "text": f"tool output {CANARY}"},
                            {"type": "tool_result", "content": f"command output {CANARY}"},
                        ]},
        }
        with main.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(extra) + "\n")
        self.check_first_run(gate, {_CLAUDE_SESSION, "agent-deadbeef", "agent-nested"},
                             "claude-code", "session: 3")

    def test_first_run_with_only_codex(self):
        gate = self.gate
        copy_with_canary(FIXTURES / "codex", gate.codex)
        active = (gate.codex / "sessions" / "2026" / "11" / "05"
                  / "rollout-2026-11-05T10-00-00-22222222-2222-4222-8222-222222222222.jsonl")
        extra = {
            "timestamp": stamp(minutes=-9), "ordinal": 99, "type": "response_item",
            "payload": {"type": "function_call", "name": "shell",
                        "arguments": json.dumps({"command": f"echo {CANARY}"})},
        }
        with active.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(extra) + "\n")
        self.check_first_run(gate, _CODEX_IDS, "codex-cli", "session: 2")

    def test_first_run_with_neither(self):
        self.check_first_run(self.gate, set(), None, None)


if __name__ == "__main__":
    unittest.main()
