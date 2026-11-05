import gzip
import json
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from fleetglint.adapters.codex import CodexAdapter

FIXTURES = Path(__file__).parent / "fixtures" / "codex"
SESSION_ID = "22222222-2222-4222-8222-222222222222"
OPEN_ID = "33333333-3333-4333-8333-333333333333"
NOW = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)


class CodexAdapterTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "codex"
        shutil.copytree(FIXTURES, self.root)
        self.adapter = CodexAdapter(self.root, hostname="testhost")
        self.sessions = self.root / "sessions" / "2026" / "11" / "05"
        self.active = (self.sessions
                       / f"rollout-2026-11-05T10-00-00-{SESSION_ID}.jsonl")
        self.open = (self.sessions
                     / f"rollout-2026-11-05T11-00-00-{OPEN_ID}.jsonl")

    def scan(self):
        return self.adapter.scan(NOW)

    def by_id(self, result):
        return {record["id"]: record for record in result.records}

    def write_session(self, name, lines):
        path = self.sessions / name
        path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
        return path

    def test_rollout_record_fields(self):
        result = self.scan()
        self.assertEqual(result.status, "ok")
        records = self.by_id(result)
        record = records[SESSION_ID]
        self.assertEqual(record["v"], 1)
        self.assertEqual(record["type"], "session")
        self.assertEqual(record["source_id"], "codex-cli@testhost")
        self.assertEqual(record["agent"], "codex-cli")
        self.assertEqual(record["state"], "unknown")
        self.assertEqual(record["project"], "demo")
        self.assertEqual(record["provider"], "openai")
        self.assertEqual(record["started_at"], "2026-11-05T10:00:00.000Z")
        self.assertEqual(record["last_activity_at"], "2026-11-05T10:00:07.000Z")
        self.assertEqual(record["updated_at"], record["last_activity_at"])
        self.assertEqual(record["entries"], 8)
        self.assertEqual(record["model"], "gpt-6-sol")
        self.assertEqual(record["models"], ["gpt-6.1-terra", "gpt-6-sol"])
        self.assertEqual(record["effort"], "high")
        self.assertIs(record["turn_open"], False)
        self.assertEqual(record["usage"], {"basis": "measured", "input_tokens": 1000,
                                           "cached_input_tokens": 400, "output_tokens": 200})

    def test_turn_open_true(self):
        record = self.by_id(self.scan())[OPEN_ID]
        self.assertIs(record["turn_open"], True)
        self.assertEqual(record["entries"], 4)

    def test_archived_duplicate_keeps_newer_activity(self):
        records = self.by_id(self.scan())
        self.assertEqual(len(records), 2)
        record = records[SESSION_ID]
        self.assertEqual(record["last_activity_at"], "2026-11-05T10:00:07.000Z")
        self.assertEqual(record["entries"], 8)
        self.assertIn("1 duplicate rollout(s) collapsed", self.scan().detail)

    def test_required_fields_present(self):
        for record in self.scan().records:
            for key in ("v", "type", "id", "source_id", "updated_at",
                        "agent", "state", "last_activity_at"):
                self.assertIn(key, record)

    def test_secret_text_is_never_copied(self):
        dumped = json.dumps(self.scan().records)
        self.assertNotIn("SECRET-PROMPT-TEXT", dumped)

    def test_partial_last_line_waits_then_completes(self):
        lines = self.active.read_bytes().splitlines(keepends=True)
        complete, last = b"".join(lines[:-1]), lines[-1]
        self.active.write_bytes(complete + last[: len(last) // 2])
        self.assertEqual(self.by_id(self.scan())[SESSION_ID]["entries"], 7)

        with self.active.open("ab") as handle:
            handle.write(last[len(last) // 2:])
        record = self.by_id(self.scan())[SESSION_ID]
        self.assertEqual(record["entries"], 8)
        self.assertEqual(record["last_activity_at"], "2026-11-05T10:00:07.000Z")

    def test_shrunken_file_is_read_from_the_start(self):
        self.assertEqual(self.by_id(self.scan())[SESSION_ID]["entries"], 8)
        self.active.write_bytes(b"".join(self.active.read_bytes().splitlines(keepends=True)[:2]))
        record = self.by_id(self.scan())[SESSION_ID]
        self.assertEqual(record["entries"], 2)
        self.assertEqual(record["last_activity_at"], "2026-11-05T10:00:01.000Z")
        self.assertNotIn("usage", record)

    def test_unparseable_line_is_counted(self):
        with self.active.open("ab") as handle:
            handle.write(b"not json\n")
        result = self.scan()
        self.assertEqual(self.by_id(result)[SESSION_ID]["entries"], 8)
        self.assertIn("1 unparseable line(s)", result.detail)

    def test_gzip_rollout_is_read(self):
        gz_id = "44444444-4444-4444-8444-444444444444"
        lines = [
            json.dumps({"timestamp": "2026-11-05T12:00:00.000Z", "ordinal": 0,
                        "type": "session_meta",
                        "payload": {"id": gz_id, "cwd": "/Users/me/work/gz",
                                    "model_provider": "openai"}}),
            json.dumps({"timestamp": "2026-11-05T12:00:01.000Z", "ordinal": 1,
                        "type": "turn_context",
                        "payload": {"model": "gpt-6-luna", "effort": "low"}}),
        ]
        path = self.sessions / f"rollout-2026-11-05T12-00-00-{gz_id}.jsonl.gz"
        with gzip.open(path, "wb") as handle:
            handle.write(("\n".join(lines) + "\n").encode("utf-8"))
        record = self.by_id(self.scan())[gz_id]
        self.assertEqual(record["project"], "gz")
        self.assertEqual(record["model"], "gpt-6-luna")
        self.assertEqual(record["entries"], 2)

    def test_unsupported_compression_is_skipped_and_counted(self):
        bad = self.sessions / "rollout-2026-11-05T13-00-00-55555555.jsonl.zst"
        bad.write_bytes(b"not a rollout")
        result = self.scan()
        self.assertEqual(len(result.records), 2)
        self.assertIn("1 rollout file(s) skipped (unsupported compression)", result.detail)

    def test_available_false_when_missing(self):
        adapter = CodexAdapter(self.root / "missing", hostname="testhost")
        self.assertFalse(adapter.available())
        self.assertEqual(adapter.scan(NOW).status, "unavailable")


if __name__ == "__main__":
    unittest.main()
