import contextlib
import gzip
import io
import json
import os
import sqlite3
import tempfile
import unittest
from unittest import mock
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fleetglint import cli, config, ingest, store
from fleetglint.adapters.base import ScanResult

BASE = datetime(2026, 11, 6, 3, 0, tzinfo=timezone.utc)
RECORD_TYPES = {"run", "job", "inbox_item", "session"}


def stamp(**delta):
    return (BASE + timedelta(**delta)).isoformat()


def run(id="r1", state="running", source_id="s@host", updated_at=None, **extra):
    record = {"v": 1, "type": "run", "id": id, "source_id": source_id,
              "updated_at": updated_at or stamp(), "state": state, "agent": "codex-cli"}
    record.update(extra)
    return record


def job(id="j1", state="running", source_id="s@host", updated_at=None, **extra):
    record = {"v": 1, "type": "job", "id": id, "source_id": source_id,
              "updated_at": updated_at or stamp(), "state": state,
              "command_summary": "orb-test"}
    record.update(extra)
    return record


def inbox(id="i1", state="open", source_id="s@host", updated_at=None, subject=None, **extra):
    record = {"v": 1, "type": "inbox_item", "id": id, "source_id": source_id,
              "updated_at": updated_at or stamp(), "state": state, "role_id": "lead",
              "kind": "run_finished", "created_at": updated_at or stamp(),
              "subject": subject or {"type": "run", "id": "r1"}}
    record.update(extra)
    return record


def session(id="s1", state="unknown", source_id="s@host", updated_at=None, **extra):
    record = {"v": 1, "type": "session", "id": id, "source_id": source_id,
              "updated_at": updated_at or stamp(), "state": state, "agent": "claude-code",
              "last_activity_at": updated_at or stamp()}
    record.update(extra)
    return record


def fake_validator(raw, expected_source_id):
    """The contract's validator shape, without depending on schema.py."""
    if isinstance(raw, (bytes, bytearray)):
        try:
            record = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None, "invalid_json", "not JSON"
    else:
        record = raw
    if not isinstance(record, dict):
        return None, "schema", "not an object"
    if record.get("v") != 1:
        return None, "unsupported_version", "v must be 1"
    if record.get("type") not in RECORD_TYPES:
        return None, "unsupported_type", "unknown type"
    if record.get("source_id") != expected_source_id:
        return None, "source_mismatch", "source_id does not match the source"
    for key in ("id", "updated_at", "state"):
        if key not in record:
            return None, "schema", f"missing {key}"
    try:
        store.parse_timestamp(record["updated_at"])
    except ValueError:
        return None, "schema", "invalid updated_at"
    return record, None, None


class Clock:
    def __init__(self, value=BASE):
        self.value = value

    def __call__(self):
        return self.value

    def advance(self, **delta):
        self.value += timedelta(**delta)


class FakeAdapter:
    def __init__(self, source_id="tool@host", records=(), status="ok", detail=None,
                 available=True):
        self.source_id = source_id
        self.allowed_roots = []
        self.records = list(records)
        self.status = status
        self.detail = detail
        self.available_flag = available

    def available(self):
        return self.available_flag

    def scan(self, now):
        return ScanResult(self.status, self.detail, list(self.records))


class IngestTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.root = self.dir / "sources"
        self.root.mkdir()
        cfg = config.Config()
        cfg.roots = [self.root]
        cfg.db_path = self.dir / "db.sqlite"
        self.cfg = cfg
        self.clock = Clock()
        self.conn = store.open_db(cfg.db_path)
        self.addCleanup(self.conn.close)
        self.ing = ingest.Ingestor(self.conn, cfg, validator=fake_validator, clock=self.clock)

    # --- helpers ----------------------------------------------------------

    def source_dir(self, source_id="s@host"):
        path = self.root / source_id
        path.mkdir(exist_ok=True)
        return path

    def write_segment(self, records, seq=1, source_id="s@host", gz=False):
        directory = self.source_dir(source_id)
        name = f"{seq:010d}.ndjson" + (".gz" if gz else "")
        data = "".join(json.dumps(record) + "\n" for record in records)
        path = directory / name
        if gz:
            path.write_bytes(gzip.compress(data.encode("utf-8")))
        else:
            path.write_text(data, encoding="utf-8")
        return path

    def segment_path(self, seq=1, source_id="s@host", gz=False):
        name = f"{seq:010d}.ndjson" + (".gz" if gz else "")
        return self.source_dir(source_id) / name

    def history_count(self):
        return self.conn.execute("SELECT count(*) FROM history").fetchone()[0]

    def status(self, source_id="s@host"):
        row = store.get_source(self.conn, source_id)
        return row["status"] if row else None

    # --- NDJSON -----------------------------------------------------------

    def test_ingests_segments_and_builds_read_model(self):
        first, second = run(state="running"), run(state="done", updated_at=stamp(minutes=5))
        self.write_segment([first, inbox()], seq=1)
        self.write_segment([second], seq=2)
        self.ing.scan_roots()

        latest = store.get_latest(self.conn, "s@host", "run", "r1")
        self.assertEqual(latest["state"], "done")
        self.assertEqual((latest["seq"], latest["byte_offset"]), (2, self.segment_path(2).stat().st_size))
        self.assertEqual(self.history_count(), 3)
        self.assertEqual(store.get_latest(self.conn, "s@host", "inbox_item", "i1")["state"], "open")
        checkpoint = store.get_checkpoint(self.conn, "s@host")
        self.assertEqual((checkpoint["seq"], checkpoint["byte_offset"]),
                         (2, self.segment_path(2).stat().st_size))
        source = store.get_source(self.conn, "s@host")
        self.assertEqual((source["kind"], source["status"], source["root"]),
                         ("ndjson", "ok", str(self.root)))
        self.assertEqual(source["last_record_at"], stamp(minutes=5))
        refs = self.conn.execute("SELECT * FROM refs ORDER BY rel").fetchall()
        self.assertEqual([(row["rel"], row["to_type"], row["to_id"]) for row in refs],
                         [("subject", "run", "r1")])

        self.ing.scan_roots()
        self.assertEqual(self.history_count(), 3)

    def test_incomplete_trailing_line_waits(self):
        first = run(state="running")
        second = run(id="r2", updated_at=stamp(minutes=1))
        complete = json.dumps(first) + "\n"
        self.segment_path().write_text(complete + json.dumps(second)[:12], encoding="utf-8")
        self.ing.scan_roots()
        self.assertIsNotNone(store.get_latest(self.conn, "s@host", "run", "r1"))
        self.assertIsNone(store.get_latest(self.conn, "s@host", "run", "r2"))
        self.assertEqual(store.get_checkpoint(self.conn, "s@host")["byte_offset"], len(complete))

        with open(self.segment_path(), "a", encoding="utf-8") as handle:
            handle.write(json.dumps(second)[12:] + "\n")
        self.ing.scan_roots()
        self.assertIsNotNone(store.get_latest(self.conn, "s@host", "run", "r2"))

    def test_unterminated_line_in_a_closed_segment_is_quarantined_once(self):
        first = run(state="running")
        second = run(id="r2", state="running", updated_at=stamp(minutes=1))
        partial = json.dumps(run(id="r3", state="running", updated_at=stamp(minutes=2)))[:17]
        self.segment_path(1).write_text(json.dumps(first) + "\n" + partial, encoding="utf-8")
        self.write_segment([second], seq=2)
        self.ing.scan_roots()

        self.assertIsNotNone(store.get_latest(self.conn, "s@host", "run", "r1"))
        self.assertIsNotNone(store.get_latest(self.conn, "s@host", "run", "r2"))
        self.assertIsNone(store.get_latest(self.conn, "s@host", "run", "r3"))
        rows = store.quarantine_for(self.conn, "s@host")
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["seq"], rows[0]["reason"], rows[0]["detail"]),
                         (1, "invalid_json", "unterminated line in a closed segment"))
        self.assertTrue(rows[0]["excerpt"])
        self.assertEqual(store.get_checkpoint(self.conn, "s@host")["seq"], 2)

        self.ing.scan_roots()
        self.assertEqual(len(store.quarantine_for(self.conn, "s@host")), 1)
        self.assertEqual(self.history_count(), 2)

    def test_all_segments_missing_is_a_discontinuity(self):
        self.write_segment([run()], seq=1)
        self.ing.scan_roots()
        self.segment_path(1).unlink()
        self.ing.scan_roots()
        self.assertEqual(self.status(), "discontinuity")
        self.assertIn("all segments are missing",
                      store.get_source(self.conn, "s@host")["detail"])

    def test_all_segments_missing_after_retention_is_not_a_discontinuity(self):
        self.write_segment([run(state="done")], seq=1)
        self.write_segment([run(id="r2", state="done", updated_at=stamp(minutes=1))], seq=2)
        self.ing.scan_roots()
        # Simulate a retention pass that recorded deleting the checkpointed segment too.
        store.set_meta(self.conn, "retention_deleted:s@host", "2")
        self.segment_path(1).unlink()
        self.segment_path(2).unlink()
        self.ing.scan_roots()
        self.assertEqual(self.status(), "ok")

    def test_crash_rolls_back_the_open_batch_without_loss_or_duplicates(self):
        self.assertEqual(self.ing.MAX_BATCH_LINES, 1000)
        self.assertEqual(self.ing.MAX_BATCH_BYTES, 4 * 1024 * 1024)
        records = [run(id=f"r{index}", updated_at=stamp(minutes=index)) for index in range(5)]
        self.write_segment(records)
        self.ing.max_batch_lines = 2

        calls = {"count": 0}

        def crash(record, seq, offset):
            calls["count"] += 1
            if calls["count"] == 3:
                raise RuntimeError("simulated crash")

        self.ing.line_hook = crash
        with self.assertRaises(RuntimeError):
            self.ing.scan_roots()
        self.assertEqual(self.history_count(), 2)
        self.assertEqual(store.get_checkpoint(self.conn, "s@host")["byte_offset"],
                         len((json.dumps(records[0]) + "\n" + json.dumps(records[1]) + "\n").encode()))

        self.ing.line_hook = None
        self.ing.scan_roots()
        self.assertEqual(self.history_count(), 5)
        self.assertIsNotNone(store.get_latest(self.conn, "s@host", "run", "r4"))
        self.ing.scan_roots()
        self.assertEqual(self.history_count(), 5)

    def test_truncation_is_a_discontinuity_and_reset_recovers(self):
        records = [run(id="r1"), run(id="r2", updated_at=stamp(minutes=1))]
        path = self.write_segment(records)
        self.ing.scan_roots()
        first_line = (json.dumps(records[0]) + "\n").encode()
        path.write_bytes(first_line + b'{"v": 1')
        self.ing.scan_roots()
        self.assertEqual(self.status(), "discontinuity")
        self.assertIn("truncated", store.get_source(self.conn, "s@host")["detail"])

        self.ing.reset_source("s@host")
        self.assertEqual(self.status(), "ok")
        self.assertIsNotNone(store.get_latest(self.conn, "s@host", "run", "r1"))
        self.assertIsNone(store.get_latest(self.conn, "s@host", "run", "r2"))
        self.assertEqual(store.get_source(self.conn, "s@host")["detail"], None)

    def test_replaced_prefix_is_a_discontinuity(self):
        first = json.dumps(run(id="r1"))
        second = json.dumps(run(id="r2", updated_at=stamp(minutes=1)))
        width = max(len(first), len(second))
        path = self.segment_path()
        path.write_text(first.ljust(width) + "\n", encoding="utf-8")
        self.ing.scan_roots()
        self.assertEqual(self.status(), "ok")
        path.write_text(second.ljust(width) + "\n", encoding="utf-8")
        self.ing.scan_roots()
        self.assertEqual(self.status(), "discontinuity")
        self.assertIn("replaced", store.get_source(self.conn, "s@host")["detail"])

    def test_replaced_inode_is_a_discontinuity(self):
        path = self.write_segment([run(id="r1")])
        self.ing.scan_roots()
        replacement = self.dir / "replacement.ndjson"
        replacement.write_bytes(path.read_bytes())
        os.replace(replacement, path)
        self.ing.scan_roots()
        self.assertEqual(self.status(), "discontinuity")
        self.assertIn("inode", store.get_source(self.conn, "s@host")["detail"])

    def test_changed_closed_segment_is_a_discontinuity(self):
        self.write_segment([run(id="r1")], seq=1)
        self.write_segment([run(id="r2", updated_at=stamp(minutes=1))], seq=2)
        self.ing.scan_roots()
        with open(self.segment_path(1), "a", encoding="utf-8") as handle:
            handle.write(json.dumps(run(id="r3")) + "\n")
        self.ing.scan_roots()
        self.assertEqual(self.status(), "discontinuity")
        self.assertIn("changed", store.get_source(self.conn, "s@host")["detail"])

    def test_lower_segment_appearing_is_a_discontinuity(self):
        self.write_segment([run(id="r2")], seq=2)
        self.ing.scan_roots()
        self.assertEqual(self.status(), "ok")
        self.write_segment([run(id="r1")], seq=1)
        self.ing.scan_roots()
        self.assertEqual(self.status(), "discontinuity")
        self.assertIn("appeared", store.get_source(self.conn, "s@host")["detail"])

    def test_gap_before_ingestion_is_a_discontinuity(self):
        self.write_segment([run(id="r1")], seq=1)
        self.write_segment([run(id="r3")], seq=3)
        self.ing.scan_roots()
        self.assertEqual(self.status(), "discontinuity")
        self.assertIn("missing", store.get_source(self.conn, "s@host")["detail"])

    def test_compression_is_not_a_discontinuity(self):
        self.write_segment([run(id="r1")], seq=1)
        self.write_segment([run(id="r2", updated_at=stamp(minutes=1))], seq=2)
        self.ing.scan_roots()
        plain = self.segment_path(1)
        gz = self.segment_path(1, gz=True)
        gz.write_bytes(gzip.compress(plain.read_bytes()))
        plain.unlink()
        self.ing.scan_roots()
        self.assertEqual(self.status(), "ok")
        self.assertEqual(self.history_count(), 2)
        self.assertEqual(store.get_segment(self.conn, "s@host", 1)["compressed"], 1)

    def test_segments_missing_below_the_lowest_are_retention(self):
        self.write_segment([run(id="r2")], seq=2)
        self.write_segment([run(id="r3", updated_at=stamp(minutes=1))], seq=3)
        self.ing.scan_roots()
        self.assertEqual(self.status(), "ok")
        self.assertIsNotNone(store.get_latest(self.conn, "s@host", "run", "r2"))

    def test_symlinked_sources_and_segments_are_skipped(self):
        outside = self.dir / "outside"
        outside.mkdir()
        (outside / "0000000001.ndjson").write_text(json.dumps(run(source_id="link@host")) + "\n")
        os.symlink(outside, self.root / "link@host")
        (self.root / "Bad Name").mkdir()

        directory = self.source_dir()
        self.write_segment([run(id="r1")], seq=1)
        external = self.dir / "external.ndjson"
        external.write_text(json.dumps(run(id="r2")) + "\n")
        os.symlink(external, directory / "0000000002.ndjson")
        self.ing.scan_roots()

        link = store.get_source(self.conn, "link@host")
        self.assertIn("symlink", link["detail"])
        self.assertEqual(self.conn.execute(
            "SELECT count(*) FROM records WHERE source_id = 'link@host'").fetchone()[0], 0)
        self.assertIsNone(store.get_source(self.conn, "Bad Name"))
        self.assertIn("symlink", store.get_source(self.conn, "s@host")["detail"])
        self.assertEqual(self.status(), "ok")
        self.assertEqual(self.history_count(), 1)

    def test_invalid_lines_are_quarantined_and_do_not_stop_the_batch(self):
        bad = [b"not json", json.dumps({"v": 2, "type": "run", "id": "r9",
                                        "source_id": "s@host", "updated_at": stamp(),
                                        "state": "running"}).encode(),
               json.dumps(run(source_id="other@host")).encode()]
        directory = self.source_dir()
        with open(directory / "0000000001.ndjson", "wb") as handle:
            for line in bad:
                handle.write(line + b"\n")
            handle.write(json.dumps(run(id="r1")).encode() + b"\n")
        self.ing.scan_roots()
        rows = store.quarantine_for(self.conn, "s@host")
        self.assertEqual({row["reason"] for row in rows},
                         {"invalid_json", "unsupported_version", "source_mismatch"})
        self.assertIsNotNone(store.get_latest(self.conn, "s@host", "run", "r1"))

    def test_session_observed_ts_uses_last_activity(self):
        activity = stamp(minutes=7)
        self.write_segment([session(updated_at=stamp(), last_activity_at=activity)])
        self.ing.scan_roots()
        row = store.get_latest(self.conn, "s@host", "session", "s1")
        self.assertEqual(row["observed_ts"], store.epoch(activity))

    # --- adapters ---------------------------------------------------------

    def adapter_ingestor(self, adapter):
        return ingest.Ingestor(self.conn, self.cfg, validator=fake_validator,
                               adapters=(adapter,), clock=self.clock)

    def test_adapter_records_are_upserted_only_when_changed(self):
        adapter = FakeAdapter(records=[run(source_id="tool@host")])
        ingestor = self.adapter_ingestor(adapter)
        ingestor.scan_adapters()

        row = store.get_latest(self.conn, "tool@host", "run", "r1")
        self.assertEqual((row["seq"], row["byte_offset"]), (0, 1))
        self.assertEqual(self.history_count(), 1)
        self.assertEqual(store.get_source(self.conn, "tool@host")["kind"], "adapter")
        self.assertEqual(store.get_checkpoint(self.conn, "tool@host")["byte_offset"], 1)

        refreshed = dict(run(source_id="tool@host"), observed_at=stamp(minutes=5))
        adapter.records = [refreshed]
        ingestor.scan_adapters()
        self.assertEqual(self.history_count(), 1)
        row = store.get_latest(self.conn, "tool@host", "run", "r1")
        self.assertEqual(json.loads(row["json"])["observed_at"], stamp(minutes=5))
        self.assertEqual(row["observed_ts"], store.epoch(stamp(minutes=5)))

        adapter.records = [run(state="done", source_id="tool@host")]
        ingestor.scan_adapters()
        self.assertEqual(self.history_count(), 2)
        self.assertEqual(store.get_latest(self.conn, "tool@host", "run", "r1")["state"], "done")
        self.assertEqual(store.get_checkpoint(self.conn, "tool@host")["byte_offset"], 3)

    def test_adapter_invalid_record_is_quarantined(self):
        bad = {"v": 1, "type": "run", "id": "bad", "source_id": "tool@host",
               "updated_at": stamp()}
        adapter = FakeAdapter(records=[bad, run(source_id="tool@host")])
        self.adapter_ingestor(adapter).scan_adapters()
        rows = store.quarantine_for(self.conn, "tool@host")
        self.assertEqual([row["reason"] for row in rows], ["schema"])
        self.assertIsNotNone(store.get_latest(self.conn, "tool@host", "run", "r1"))

    def test_unavailable_adapter_keeps_records(self):
        adapter = FakeAdapter(records=[run(source_id="tool@host")])
        ingestor = self.adapter_ingestor(adapter)
        ingestor.scan_adapters()
        adapter.available_flag = False
        ingestor.scan_adapters()
        source = store.get_source(self.conn, "tool@host")
        self.assertEqual(source["status"], "unavailable")
        self.assertIsNotNone(store.get_latest(self.conn, "tool@host", "run", "r1"))

        unseen = FakeAdapter(source_id="absent@host", available=False)
        self.adapter_ingestor(unseen).scan_adapters()
        self.assertIsNone(store.get_source(self.conn, "absent@host"))

    def test_adapter_scan_status_unavailable_keeps_records(self):
        adapter = FakeAdapter(records=[run(source_id="tool@host")])
        ingestor = self.adapter_ingestor(adapter)
        ingestor.scan_adapters()
        adapter.status = "unavailable"
        adapter.detail = "state directory vanished"
        ingestor.scan_adapters()
        source = store.get_source(self.conn, "tool@host")
        self.assertEqual((source["status"], source["detail"]),
                         ("unavailable", "state directory vanished"))
        self.assertIsNotNone(store.get_latest(self.conn, "tool@host", "run", "r1"))

        adapter.status = "ok"
        ingestor.scan_adapters()
        self.assertEqual(store.get_source(self.conn, "tool@host")["status"], "ok")

    # --- retention --------------------------------------------------------

    def make_old(self, path, days=40):
        when = (BASE - timedelta(days=days)).timestamp()
        os.utime(path, (when, when))

    def retain(self):
        self.ing.apply_retention()

    def test_retention_deletes_old_closed_segment_with_terminal_records(self):
        self.write_segment([run(state="done")], seq=1)
        self.write_segment([run(id="r2", state="running", updated_at=stamp(minutes=1))], seq=2)
        self.write_segment([run(id="r3", state="done", updated_at=stamp(minutes=2))], seq=3)
        self.ing.scan_roots()
        self.make_old(self.segment_path(1))
        self.make_old(self.segment_path(2))
        self.retain()
        self.assertFalse(self.segment_path(1).exists())
        self.assertTrue(self.segment_path(2).exists())
        self.assertTrue(self.segment_path(3).exists())
        self.assertIsNone(store.get_segment(self.conn, "s@host", 1))

        self.ing.scan_roots()
        self.assertEqual(self.status(), "ok")

    def test_retention_failure_before_commit_deletes_no_file(self):
        self.write_segment([run(state="done")], seq=1)
        self.write_segment([run(id="r2", state="done", updated_at=stamp(minutes=1))], seq=2)
        self.ing.scan_roots()
        self.make_old(self.segment_path(1))
        with mock.patch.object(store, "set_meta", side_effect=sqlite3.OperationalError("boom")):
            with self.assertRaises(sqlite3.OperationalError):
                self.retain()
        self.assertTrue(self.segment_path(1).exists())
        self.assertIsNotNone(store.get_segment(self.conn, "s@host", 1))

    def test_crash_after_commit_leaves_a_retired_file_that_is_skipped_then_removed(self):
        self.write_segment([run(state="done")], seq=1)
        self.write_segment([run(id="r2", state="done", updated_at=stamp(minutes=1))], seq=2)
        self.ing.scan_roots()
        self.make_old(self.segment_path(1))
        with mock.patch.object(Path, "unlink", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.retain()
        self.assertTrue(self.segment_path(1).exists())
        self.assertIsNone(store.get_segment(self.conn, "s@host", 1))
        self.ing.scan_roots()
        self.assertEqual(self.status(), "ok")
        self.retain()
        self.assertFalse(self.segment_path(1).exists())

    def test_retention_keeps_segment_with_non_terminal_record(self):
        self.write_segment([run(id="r1")], seq=1)
        self.write_segment([run(id="r2", updated_at=stamp(minutes=1))], seq=2)
        self.ing.scan_roots()
        self.make_old(self.segment_path(1))
        self.retain()
        self.assertTrue(self.segment_path(1).exists())

    def test_retention_deletes_abandoned_non_terminal_record(self):
        self.write_segment([run(updated_at=stamp(days=-100))], seq=1)
        self.write_segment([run(id="r2", updated_at=stamp(minutes=1))], seq=2)
        self.ing.scan_roots()
        self.make_old(self.segment_path(1))
        self.retain()
        self.assertFalse(self.segment_path(1).exists())

    def test_retention_flags_open_inbox_item(self):
        self.write_segment([run(state="done")], seq=1)
        self.write_segment([inbox(updated_at=stamp(days=-200))], seq=2)
        self.write_segment([run(id="r3", state="done", updated_at=stamp(minutes=2))], seq=3)
        self.ing.scan_roots()
        self.make_old(self.segment_path(1))
        self.make_old(self.segment_path(2))
        self.retain()
        self.assertFalse(self.segment_path(1).exists())
        self.assertTrue(self.segment_path(2).exists())
        self.assertEqual(store.get_latest(self.conn, "s@host", "inbox_item", "i1")["blocks_retention"], 1)

    def test_retention_treats_open_and_unknown_sessions_as_non_terminal(self):
        self.write_segment([session(state="unknown", updated_at=stamp())], seq=1)
        self.write_segment([run(id="r2", updated_at=stamp(minutes=1))], seq=2)
        self.ing.scan_roots()
        self.make_old(self.segment_path(1))
        self.retain()
        self.assertTrue(self.segment_path(1).exists())

    def test_retention_deletes_ended_session_and_acked_inbox_segments(self):
        self.write_segment([session(id="s1", state="ended", updated_at=stamp(days=-100))], seq=1)
        self.write_segment([inbox(state="acked", updated_at=stamp(days=-100),
                                  acked_at=stamp(days=-100))], seq=2)
        self.write_segment([run(id="r3", updated_at=stamp(minutes=2))], seq=3)
        self.ing.scan_roots()
        self.make_old(self.segment_path(1))
        self.make_old(self.segment_path(2))
        self.retain()
        self.assertFalse(self.segment_path(1).exists())
        self.assertFalse(self.segment_path(2).exists())
        self.assertTrue(self.segment_path(3).exists())

    def test_retention_deletes_oldest_first(self):
        self.write_segment([run(id="r1")], seq=1)
        self.write_segment([run(id="r2", state="done", updated_at=stamp(minutes=1))], seq=2)
        self.ing.scan_roots()
        self.make_old(self.segment_path(1))
        self.make_old(self.segment_path(2))
        self.retain()
        self.assertTrue(self.segment_path(1).exists())
        self.assertTrue(self.segment_path(2).exists())

    def test_history_retention_drops_old_history_and_terminal_records(self):
        self.write_segment([run(state="done")])
        self.ing.scan_roots()
        self.assertEqual(self.history_count(), 1)
        self.clock.advance(days=40)
        self.retain()
        self.assertEqual(self.history_count(), 0)
        self.assertIsNone(store.get_latest(self.conn, "s@host", "run", "r1"))

    def test_history_retention_keeps_non_terminal_latest_record(self):
        self.write_segment([run(state="running")])
        self.ing.scan_roots()
        self.clock.advance(days=40)
        self.retain()
        self.assertEqual(self.history_count(), 0)
        self.assertIsNotNone(store.get_latest(self.conn, "s@host", "run", "r1"))

    def test_retention_does_not_follow_a_symlinked_source_dir(self):
        self.write_segment([run(state="done")], seq=1)
        self.write_segment([run(id="r2", state="done", updated_at=stamp(minutes=1))], seq=2)
        self.ing.scan_roots()
        self.make_old(self.segment_path(1))
        outside = self.dir / "outside"
        outside.mkdir()
        moved = outside / "s@host"
        os.rename(self.source_dir(), moved)
        os.symlink(moved, self.root / "s@host")
        self.retain()
        self.assertTrue((moved / "0000000001.ndjson").exists())
        self.assertIsNotNone(store.get_segment(self.conn, "s@host", 1))

    def test_retention_refuses_a_segment_replaced_after_ingestion(self):
        real_a = self.dir / "root-a"
        real_a.mkdir()
        self.root.rmdir()
        os.symlink(real_a, self.root)
        self.write_segment([run(state="done")], seq=1)
        self.write_segment([run(id="r2", state="done", updated_at=stamp(minutes=1))], seq=2)
        self.ing.scan_roots()
        self.make_old(self.segment_path(1))

        real_b = self.dir / "root-b"
        (real_b / "s@host").mkdir(parents=True)
        replacement = real_b / "s@host" / "0000000001.ndjson"
        replacement.write_text(json.dumps(run(id="r1", state="running")) + "\n")
        os.unlink(self.root)
        os.symlink(real_b, self.root)

        self.retain()
        self.assertTrue(replacement.exists())
        self.assertIsNotNone(store.get_segment(self.conn, "s@host", 1))
        self.assertEqual(self.status(), "discontinuity")
        self.assertIn("segment 0000000001 changed before retention",
                      store.get_source(self.conn, "s@host")["detail"])

    def test_retention_does_not_delete_a_symlinked_segment_target(self):
        self.write_segment([run(state="done")], seq=1)
        self.write_segment([run(id="r2", state="done", updated_at=stamp(minutes=1))], seq=2)
        self.ing.scan_roots()
        self.make_old(self.segment_path(1))
        outside = self.dir / "outside.ndjson"
        outside.write_bytes(self.segment_path(1).read_bytes())
        self.segment_path(1).unlink()
        os.symlink(outside, self.segment_path(1))
        self.retain()
        self.assertTrue(outside.exists())

    # --- rebuild and CLI --------------------------------------------------

    def test_rebuild_replays_retained_segments(self):
        self.write_segment([run(id="r1")], seq=1)
        self.write_segment([run(id="r2", updated_at=stamp(minutes=1))], seq=2)
        self.ing.scan_roots()
        self.conn.close()
        with mock.patch.object(ingest, "_classify_line", fake_validator):
            ingest.rebuild(self.cfg)
        conn = store.open_db(self.cfg.db_path)
        self.addCleanup(conn.close)
        self.assertEqual(conn.execute("SELECT count(*) FROM records").fetchone()[0], 2)
        self.assertEqual(conn.execute("SELECT count(*) FROM history").fetchone()[0], 2)
        self.assertEqual(store.get_checkpoint(conn, "s@host")["seq"], 2)

    def write_config(self):
        path = self.dir / "config.toml"
        path.write_text(f'[ingest]\nroots = ["{self.root}"]\ndb_path = "{self.cfg.db_path}"\n')
        return path

    def run_cli(self, *args):
        parsed = cli.build_parser().parse_args(["--config", str(self.write_config()), *args])
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(ingest, "_classify_line", fake_validator), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ingest.run(parsed)
        return code, out.getvalue(), err.getvalue()

    def test_cli_once_status_reset_rebuild(self):
        self.write_segment([run(id="r1")])
        code, out, err = self.run_cli("ingest", "--once")
        self.assertEqual(code, 0)
        self.assertIn("ingest:", out)

        code, out, err = self.run_cli("status")
        self.assertEqual(code, 0)
        self.assertIn("s@host", out)
        self.assertIn("db:", out)

        self.segment_path().write_bytes(b'{"v": 1')
        self.run_cli("ingest", "--once")
        self.assertEqual(self.status(), "discontinuity")
        code, out, err = self.run_cli("source", "reset", "s@host")
        self.assertEqual(code, 0)
        self.assertEqual(self.status(), "ok")

        self.conn.close()
        code, out, err = self.run_cli("rebuild")
        self.assertEqual(code, 0)
        self.assertTrue(self.cfg.db_path.exists())

    def test_service_lock_blocks_rebuild_reset_and_once(self):
        self.write_segment([run(id="r1")])
        self.ing.scan_roots()
        before = self.cfg.db_path.read_bytes()
        with ingest.hold_service_lock(self.cfg):
            for command in (("rebuild",), ("ingest", "--once"),
                            ("source", "reset", "s@host")):
                code, out, err = self.run_cli(*command)
                self.assertEqual(code, 3, command)
                self.assertIn("fleetglint is running", err)
                self.assertNotIn("Traceback", err)
                self.assertTrue(self.cfg.db_path.exists())
                self.assertEqual(self.cfg.db_path.read_bytes(), before)
        self.assertEqual(self.status(), "ok")
        self.assertIsNotNone(store.get_latest(self.conn, "s@host", "run", "r1"))

    def test_cli_reports_validator_import_error(self):
        self.write_segment([run()])
        parsed = cli.build_parser().parse_args(
            ["--config", str(self.write_config()), "ingest", "--once"])

        def unavailable(raw, expected_source_id):
            raise ImportError("cannot import name 'classify_line'")

        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(ingest, "_classify_line", unavailable), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ingest.run(parsed)
        self.assertEqual(code, 3)
        self.assertIn("validator", err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())


if __name__ == "__main__":
    unittest.main()
