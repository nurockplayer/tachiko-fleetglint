import os
import sqlite3
import stat
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from fleetglint import store

UPDATED = "2026-11-05T10:00:00+09:00"


def run_record(source_id="s@host", id="r1", state="running", updated_at=UPDATED, **extra):
    record = {"v": 1, "type": "run", "id": id, "source_id": source_id,
              "updated_at": updated_at, "state": state, "agent": "codex-cli"}
    record.update(extra)
    return record


class OpenDbTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_creates_parent_schema_and_pragmas(self):
        path = self.dir / "nested" / "fleetglint.sqlite"
        conn = store.open_db(path)
        self.addCleanup(conn.close)
        self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
        self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        self.assertEqual(conn.execute("PRAGMA synchronous").fetchone()[0], 1)
        self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], store.SCHEMA_VERSION)
        self.assertIsInstance(conn.execute("SELECT 1").fetchone(), sqlite3.Row)
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'")}
        self.assertTrue({"sources", "segments", "checkpoints", "records", "history", "refs",
                         "quarantine", "meta"} <= tables)
        indexes = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'")}
        self.assertTrue({"records_type_state", "records_updated_ts", "refs_to", "refs_from",
                         "history_identity"} <= indexes)

    def test_read_only_connection_refuses_writes(self):
        path = self.dir / "db.sqlite"
        store.open_db(path).close()
        conn = store.open_db(path, readonly=True)
        self.addCleanup(conn.close)
        with self.assertRaises(sqlite3.OperationalError):
            conn.execute("INSERT INTO meta(key, value) VALUES ('x', '1')")

    def test_newer_schema_is_refused(self):
        path = self.dir / "db.sqlite"
        conn = store.open_db(path)
        conn.execute(f"PRAGMA user_version = {store.SCHEMA_VERSION + 1}")
        conn.close()
        with self.assertRaises(RuntimeError):
            store.open_db(path)


class HelpersTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.conn = store.open_db(Path(self.tmp.name) / "db.sqlite")
        self.addCleanup(self.conn.close)

    def test_meta_and_change_counter(self):
        self.assertIsNone(store.get_meta(self.conn, "missing"))
        self.assertEqual(store.get_meta(self.conn, "missing", "fallback"), "fallback")
        store.set_meta(self.conn, "key", "value")
        self.assertEqual(store.get_meta(self.conn, "key"), "value")
        self.assertEqual(store.get_change_counter(self.conn), 0)
        self.assertEqual(store.bump_change_counter(self.conn), 1)
        self.assertEqual(store.bump_change_counter(self.conn), 2)
        self.assertEqual(store.get_change_counter(self.conn), 2)

    def test_latest_record_never_goes_backwards(self):
        record = run_record()
        self.assertTrue(store.put_latest(self.conn, record, 2, 100))
        older = run_record(state="queued")
        self.assertFalse(store.put_latest(self.conn, older, 1, 999))
        self.assertEqual(store.get_latest(self.conn, "s@host", "run", "r1")["state"], "running")
        newer = run_record(state="done")
        self.assertTrue(store.put_latest(self.conn, newer, 3, 0))
        self.assertEqual(store.get_latest(self.conn, "s@host", "run", "r1")["state"], "done")

    def test_history_replay_is_a_noop(self):
        record = run_record()
        self.assertTrue(store.insert_history(self.conn, record, 1, 50, 1.0))
        self.assertFalse(store.insert_history(self.conn, record, 1, 50, 2.0))
        rows = self.conn.execute("SELECT * FROM history").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ingested_ts"], 1.0)

    def test_iter_latest_filters_types(self):
        store.put_latest(self.conn, run_record(id="r1"), 1, 1)
        store.put_latest(self.conn, {"v": 1, "type": "job", "id": "j1", "source_id": "s@host",
                                     "updated_at": UPDATED, "state": "running",
                                     "command_summary": "test"}, 1, 2)
        self.assertEqual([row["id"] for row in store.iter_latest(self.conn)], ["j1", "r1"])
        self.assertEqual([row["id"] for row in store.iter_latest(self.conn, types=("run",))], ["r1"])
        self.assertEqual([row["id"] for row in store.iter_latest(self.conn, types="job")], ["j1"])

    def test_observed_ts(self):
        store.put_latest(self.conn, run_record(observed_at="2026-11-05T11:00:00+09:00"), 1, 1)
        row = store.get_latest(self.conn, "s@host", "run", "r1")
        self.assertEqual(row["observed_ts"], store.epoch("2026-11-05T11:00:00+09:00"))
        self.assertEqual(row["updated_ts"], store.epoch(UPDATED))

        store.put_latest(self.conn, run_record(id="r2"), 1, 2)
        row = store.get_latest(self.conn, "s@host", "run", "r2")
        self.assertEqual(row["observed_ts"], store.epoch(UPDATED))

        session = {"v": 1, "type": "session", "id": "s1", "source_id": "s@host",
                   "updated_at": UPDATED, "state": "unknown", "agent": "claude-code",
                   "last_activity_at": "2026-11-05T12:00:00+09:00"}
        store.put_latest(self.conn, session, 1, 3)
        row = store.get_latest(self.conn, "s@host", "session", "s1")
        self.assertEqual(row["observed_ts"], store.epoch("2026-11-05T12:00:00+09:00"))

    def test_parse_timestamp_requires_offset(self):
        self.assertEqual(store.parse_timestamp("2026-11-05T10:00:00Z"),
                         datetime(2026, 11, 5, 10, 0, tzinfo=timezone.utc))
        with self.assertRaises(ValueError):
            store.parse_timestamp("2026-11-05T10:00:00")

    def test_refs_for_all_relations(self):
        run = run_record(
            parent_run={"type": "run", "id": "lead"},
            resume_of={"type": "run", "id": "old", "source_id": "other@host"},
            waits_on=[{"type": "external", "kind": "github_pr", "key": "a/b#1"},
                      {"type": "job", "id": "j1"}])
        refs = {(row[3], row[4], row[5], row[6], row[7]): row for row in store.refs_for(run)}
        self.assertEqual(refs[("parent_run", "run", "s@host", "lead", None)],
                         ("s@host", "run", "r1", "parent_run", "run", "s@host", "lead",
                          None, None, None))
        self.assertIn(("resume_of", "run", "other@host", "old", None), refs)
        self.assertIn(("waits_on", None, None, None, "github_pr"), refs)
        self.assertIn(("waits_on", "job", "s@host", "j1", None), refs)

        job = {"v": 1, "type": "job", "id": "j1", "source_id": "s@host",
               "updated_at": UPDATED, "state": "running", "command_summary": "test",
               "run": {"type": "run", "id": "r1"}}
        self.assertEqual([row[3] for row in store.refs_for(job)], ["job_run"])

        inbox = {"v": 1, "type": "inbox_item", "id": "i1", "source_id": "s@host",
                 "updated_at": UPDATED, "state": "open", "role_id": "lead", "kind": "x",
                 "subject": {"type": "external", "kind": "ci_run", "url": "https://x"},
                 "created_at": UPDATED}
        subject = store.refs_for(inbox)[0]
        self.assertEqual((subject[3], subject[7], subject[9]), ("subject", "ci_run", "https://x"))

        session = {"v": 1, "type": "session", "id": "s1", "source_id": "s@host",
                   "updated_at": UPDATED, "state": "unknown", "agent": "codex-cli",
                   "last_activity_at": UPDATED,
                   "parent_session": {"type": "session", "id": "parent"}}
        self.assertEqual(store.refs_for(session)[0][3:7],
                         ("parent_session", "session", "s@host", "parent"))

    def test_replace_refs_rewrites(self):
        record = run_record(parent_run={"type": "run", "id": "lead"})
        store.replace_refs(self.conn, record)
        self.assertEqual(self.conn.execute("SELECT count(*) FROM refs").fetchone()[0], 1)
        record["parent_run"] = {"type": "run", "id": "other"}
        store.replace_refs(self.conn, record)
        rows = self.conn.execute("SELECT * FROM refs").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["to_id"], "other")

    def test_quarantine_is_bounded_and_keeps_excerpt(self):
        for index in range(store.QUARANTINE_LIMIT + 5):
            store.add_quarantine(self.conn, "s@host", 1, index, "invalid_json", "bad",
                                 f"line {index}", UPDATED)
        rows = store.quarantine_for(self.conn, "s@host", limit=store.QUARANTINE_LIMIT + 10)
        self.assertEqual(len(rows), store.QUARANTINE_LIMIT)
        self.assertEqual(rows[0]["excerpt"], f"line {store.QUARANTINE_LIMIT + 4}")
        self.assertEqual(rows[-1]["qid"], 6)

    def test_source_stats(self):
        record = run_record()
        store.put_latest(self.conn, record, 1, 1)
        store.ensure_source(self.conn, "s@host", "ndjson", "/tmp/root")
        store.add_quarantine(self.conn, "s@host", 1, 1, "schema", "bad", "x", UPDATED)
        [row] = store.source_stats(self.conn)
        self.assertEqual((row["source_id"], row["kind"], row["status"], row["records"],
                          row["quarantine"]), ("s@host", "ndjson", "ok", 1, 1))


if __name__ == "__main__":
    unittest.main()
