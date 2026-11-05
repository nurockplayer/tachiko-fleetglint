"""Tests for `fleetglint serve`: the HTTP server plus the ingest thread (architecture §8)."""
import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from fleetglint import config, emit, ingest, server


def real_stamp():
    """A wall-clock timestamp, so display states are current for the server's own clock."""
    return datetime.now(timezone.utc).astimezone().isoformat()


def job(id, state, **extra):
    record = {"v": 1, "type": "job", "id": id, "source_id": "work@mbp",
              "updated_at": real_stamp(), "state": state, "command_summary": "sleep 5"}
    record.update(extra)
    return record


class ServeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.root = self.dir / "sources"
        self.root.mkdir()
        cfg = config.Config()
        cfg.roots = [self.root]
        cfg.db_path = self.dir / "db.sqlite"
        cfg.poll_s = 0.05
        cfg.adapter_poll_s = 0.05
        for adapter in (cfg.harness, cfg.claude_code, cfg.codex):
            adapter.enabled = "false"
        self.cfg = cfg

    def start(self):
        http_server, ingest_thread, stop_event = server.start(self.cfg, 0)
        serving = threading.Thread(target=http_server.serve_forever, daemon=True)
        serving.start()
        self.addCleanup(self.stop, http_server, serving, ingest_thread, stop_event)
        self.port = http_server.server_address[1]
        return http_server, ingest_thread, stop_event

    def stop(self, http_server, serving, ingest_thread, stop_event):
        stop_event.set()
        if serving.is_alive():
            http_server.shutdown()
            serving.join(5)
        ingest_thread.join(5)
        http_server.server_close()

    def get(self, path):
        url = f"http://127.0.0.1:{self.port}{path}"
        with urllib.request.urlopen(url, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    def poll(self, path, predicate, timeout=5.0):
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            try:
                last = self.get(path)
            except (urllib.error.URLError, ConnectionError, OSError):
                last = None
            if last is not None and predicate(last):
                return last
            time.sleep(0.05)
        self.fail(f"{path} did not reach the expected state within {timeout}s; last={last}")

    def test_serve_ingests_new_records_until_stopped(self):
        _, ingest_thread, stop_event = self.start()
        self.assertTrue(ingest_thread.is_alive())

        # The server is up before any record exists: a valid, empty board.
        empty = self.poll("/api/snapshot", lambda snap: snap["api"] == 1)
        self.assertEqual(empty["jobs"], [])
        self.assertEqual(empty["counts"]["attention"], 0)

        emit.append_record(job("live-1", "running"), self.root)
        snap = self.poll("/api/snapshot", lambda snap: any(
            item["ref"]["id"] == "live-1" for item in snap["jobs"]))
        item = {item["ref"]["id"]: item for item in snap["jobs"]}["live-1"]
        self.assertEqual(item["state"], "running")
        self.assertEqual(item["display_state"], "running")
        self.assertEqual(item["evidence"]["kind"], "observed")

        # A terminal update shows up without a restart.
        emit.append_record(job("live-1", "done", exit_code=0), self.root)
        snap = self.poll("/api/snapshot", lambda snap: any(
            item["ref"]["id"] == "live-1" and item["state"] == "done"
            for item in snap["jobs"]))
        item = {item["ref"]["id"]: item for item in snap["jobs"]}["live-1"]
        self.assertEqual(item["display_state"], "done")
        self.assertEqual(item["evidence"], {"kind": "terminal", "age_s": None,
                                            "detail": None})
        self.assertEqual(item["exit_code"], 0)

        record = self.get("/api/record?source_id=work%40mbp&type=job&id=live-1")
        self.assertEqual(record["record"]["state"], "done")
        self.assertEqual(record["full"]["id"], "live-1")

        stop_event.set()
        ingest_thread.join(5)
        self.assertFalse(ingest_thread.is_alive())

    def test_start_refuses_when_the_service_lock_is_held(self):
        with ingest.hold_service_lock(self.cfg):
            with self.assertRaises(ingest.ServiceLockBusy):
                server.start(self.cfg, 0)


if __name__ == "__main__":
    unittest.main()
