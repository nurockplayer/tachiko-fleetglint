"""Plans acceptance through fake executables and the loopback HTTP endpoint."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

from fleetglint import config, plans, server
from tests.test_server import FakeBackend, request, stop_server, SECURITY

REPORT = {
    "output_version": 1, "valid": True, "project": "Example", "state": "ACTIVE",
    "errors": [], "counts": {"total": 1, "PASS": 0, "STALE": 1},
    "workstreams": [{"id": "W", "counts": {"total": 1, "STALE": 1}, "criteria": [
        {"id": "C", "source_status": "PASS", "status": "STALE",
         "reason": "watched files changed", "changed_files": ["src/main.py"]}]}],
    "plan": {"project": "Example", "state": "ACTIVE", "workstreams": [
        {"id": "W", "title": "Deliverable", "outcome": "Owner can read the plan",
         "criteria": [{"id": "C", "requirement": "Observable invariant", "status": "PASS",
                       "judge": "Independent lead", "verified_sha": "abcdef1"}]}],
        "owner_decisions": [{"id": "D", "question": "Ship?", "options": ["yes", "no"],
                             "recommendation": "yes", "state": "OPEN", "deadline": "2026-12-01 JST"}]},
}


class PlansTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.file = self.root / "plan.yaml"
        self.file.write_text("plan-check owns parsing")
        self.calls = self.root / "calls"
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.env = mock.patch.dict(os.environ, {"PATH": str(self.bin) + os.pathsep + os.environ["PATH"]})
        self.env.start()
        self.addCleanup(self.env.stop)

    def fake(self, body):
        executable = self.bin / "plan-check"
        executable.write_text(f"#!{sys.executable}\nfrom pathlib import Path\nimport sys, json, os, subprocess, time\n"
                              f"with Path({str(self.calls)!r}).open('a') as f: f.write('call\\n')\n" + body)
        executable.chmod(0o755)

    def report(self, report=REPORT, code=0):
        self.fake(f"assert sys.argv[1:] == [{str(self.root)!r}, '--json']\n"
                  f"print({json.dumps(report)!r})\nsys.exit({code})\n")

    def reader(self, **kwargs):
        reader = plans.Plans([str(self.root)], **kwargs)
        self.addCleanup(reader.close)
        return reader

    def row(self, reader):
        return reader.snapshot()["plans"][0]

    def test_config_opt_in_and_types(self):
        cfg = self.root / "config.toml"
        cfg.write_text("")
        self.assertEqual(config.load(cfg).plan_paths, [])
        cfg.write_text('[plans]\npaths = ["~/repo", "/tmp/plan.yaml"]')
        self.assertEqual(config.load(cfg).plan_paths, ["~/repo", "/tmp/plan.yaml"])
        for content in ('plans = []', '[plans]\npaths = "repo"', '[plans]\npaths = [1]',
                        '[plans]\npaths = [true]', '[plans]\npaths = {}'):
            cfg.write_text(content)
            with self.subTest(content=content), self.assertRaises(config.ConfigError):
                config.load(cfg)

    def test_disabled_starts_no_process_and_api_is_empty(self):
        with mock.patch("fleetglint.plans.subprocess.Popen") as popen:
            reader = plans.Plans()
            reader.start()
            reader.refresh()
            self.assertEqual(reader.snapshot()["plans"], [])
            popen.assert_not_called()
            self.http(reader, lambda port: self.assertEqual(json.loads(request(port, path="/api/plans")[2])["plans"], []))
            popen.assert_not_called()

    def test_full_document_join_uses_reported_stale_and_redacts(self):
        report = copy.deepcopy(REPORT)
        report["plan"]["workstreams"][0]["criteria"][0]["context"] = "ghp_" + "a" * 30
        self.report(report)
        reader = self.reader()
        reader.refresh()
        row = self.row(reader)
        self.assertEqual((row["state"], row["project"], row["plan_state"]), ("ok", "Example", "ACTIVE"))
        self.assertEqual(row["counts"], REPORT["counts"])
        self.assertEqual(row["owner_decisions"][0]["question"], "Ship?")
        stream = row["workstreams"][0]
        self.assertEqual(stream["title"], "Deliverable")
        criterion = stream["criteria"][0]
        self.assertEqual(criterion["requirement"], "Observable invariant")
        self.assertEqual(criterion["status"], "STALE")
        self.assertEqual(criterion["reason"], "watched files changed")
        self.assertEqual(criterion["context"], "[redacted]")
        self.assertIsNotNone(row["file_modified_at"])
        self.assertIsNotNone(row["checked_at"])
        self.assertTrue(row["text_available"])

    def test_without_document_preserves_report(self):
        report = copy.deepcopy(REPORT)
        del report["plan"]
        self.report(report)
        reader = self.reader()
        reader.refresh()
        row = self.row(reader)
        self.assertFalse(row["text_available"])
        self.assertEqual(row["workstreams"], report["workstreams"])
        self.assertEqual(row["counts"], report["counts"])

    def test_invalid_has_errors_and_no_counts(self):
        self.report({"output_version": 1, "valid": False, "errors": ["invalid plan"], "plan": None}, 1)
        reader = self.reader()
        reader.refresh()
        self.assertEqual(self.row(reader)["state"], "invalid")
        self.assertEqual(self.row(reader)["errors"], ["invalid plan"])
        self.assertNotIn("counts", self.row(reader))

    def test_missing_executable(self):
        reader = self.reader()
        with mock.patch.dict(os.environ, {"PATH": str(self.bin)}):
            reader.refresh()
        self.assertEqual(self.row(reader)["state"], "unavailable")

    def test_non_json_oversized_and_setup_failure(self):
        for body in ("print('not json')", "print('x' * (1024 * 1024 + 1))", "sys.exit(2)",
                     "print(json.dumps({'output_version':1, 'valid':False, 'errors':['IO failed']})); sys.exit(2)"):
            with self.subTest(body=body):
                self.fake(body)
                reader = self.reader()
                reader.refresh()
                self.assertEqual(self.row(reader)["state"], "failed")
                self.assertNotIn("counts", self.row(reader))

    def test_timeout_kills_parent_and_child(self):
        pids = self.root / "pids"
        self.fake("child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
                  f"Path({str(pids)!r}).write_text(f'{{os.getpid()}} {{child.pid}}')\ntime.sleep(60)\n")
        reader = self.reader(timeout=1.5)
        reader.refresh()
        self.assertEqual(self.row(reader)["state"], "failed")
        self.assertIn("timed out", self.row(reader)["errors"][0])
        for pid in map(int, pids.read_text().split()):
            # SIGKILL delivery to an orphan is asynchronous; wait for its exit.
            deadline = time.monotonic() + 2
            while True:
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    break
                if sys.platform == "linux":
                    # Linux container init may retain a killed orphan as a zombie.
                    try:
                        state = Path(f"/proc/{pid}/stat").read_text().split()[2]
                    except FileNotFoundError:
                        break  # Process exited after the signal probe.
                    if state == "Z":
                        break
                self.assertLess(time.monotonic(), deadline, f"process {pid} still running")
                time.sleep(0.01)

    def test_cache_mtime_expiry_and_errors_expire(self):
        self.report()
        reader = self.reader()
        reader.refresh()
        reader.refresh()
        self.assertEqual(len(self.calls.read_text().splitlines()), 1)
        stamp = self.file.stat().st_mtime_ns
        os.utime(self.file, ns=(stamp + 1000000, stamp + 1000000))
        reader.refresh()
        self.assertEqual(len(self.calls.read_text().splitlines()), 2)
        reader.expiry = 0
        reader.refresh()
        self.assertEqual(len(self.calls.read_text().splitlines()), 3)
        self.fake("print('bad json')")
        reader.refresh()
        reader.expiry = 180
        reader.refresh()
        self.assertEqual(len(self.calls.read_text().splitlines()), 4)
        reader.expiry = 0
        reader.refresh()
        self.assertEqual(len(self.calls.read_text().splitlines()), 5)

    def test_head_changes_cache_key(self):
        for args in (["init", "-q"], ["-c", "user.name=Test", "-c", "user.email=test@example.org", "commit", "--allow-empty", "-qm", "one"]):
            subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True)
        self.report()
        reader = self.reader()
        reader.refresh()
        subprocess.run(["git", "-C", str(self.root), "-c", "user.name=Test", "-c", "user.email=test@example.org", "commit", "--allow-empty", "-qm", "two"], check=True, capture_output=True)
        reader.refresh()
        self.assertEqual(len(self.calls.read_text().splitlines()), 2)

    def http(self, reader, check):
        srv = server.make_server(FakeBackend(), 0, self.root)
        srv.plans = reader
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        try:
            check(srv.server_address[1])
        finally:
            stop_server(srv, thread)

    def test_api_is_immediate_while_check_runs_and_uses_http_protections(self):
        reader = self.reader()
        self.report()
        reader.refresh()
        checked = self.row(reader)["checked_at"]
        self.fake("time.sleep(60)")
        reader.expiry = 0
        entered = threading.Event()
        original = reader._check
        def check(*args):
            entered.set()
            return original(*args)
        reader._check = check
        reader.start()
        self.assertTrue(entered.wait(5))
        def assert_http(port):
            start = time.monotonic()
            status, headers, body = request(port, path="/api/plans?path=/not-configured")
            self.assertLess(time.monotonic() - start, 0.5)
            self.assertEqual(status, 200)
            row = json.loads(body)["plans"][0]
            self.assertTrue(row["refreshing"])
            self.assertEqual(row["checked_at"], checked)
            self.assertEqual(row["path"], str(self.root))
            for key, value in SECURITY.items():
                self.assertEqual(headers[key], value)
            self.assertFalse(any(k.startswith("access-control-") for k in headers))
            self.assertEqual(request(port, path="/api/plans", host="evil.test")[0], 421)
            self.assertEqual(request(port, method="POST", path="/api/plans")[0], 405)
        self.http(reader, assert_http)
