import json
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from fleetglint.adapters.claude_code import ClaudeCodeAdapter

FIXTURES = Path(__file__).parent / "fixtures" / "claude_code" / "projects"
SESSION_ID = "11111111-1111-4111-8111-111111111111"
NOW = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)


class ClaudeCodeAdapterTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "projects"
        shutil.copytree(FIXTURES, self.root)
        self.adapter = ClaudeCodeAdapter(self.root, hostname="testhost")
        self.main = self.root / "-Users-me-work-demo" / f"{SESSION_ID}.jsonl"
        self.sub = (self.root / "-Users-me-work-demo" / SESSION_ID
                    / "subagents" / "agent-deadbeef.jsonl")

    def scan(self):
        return self.adapter.scan(NOW)

    def by_id(self, result):
        return {record["id"]: record for record in result.records}

    def test_main_and_subagent_records(self):
        result = self.scan()
        self.assertEqual(result.status, "ok")
        records = self.by_id(result)
        self.assertEqual(set(records), {SESSION_ID, "agent-deadbeef", "agent-nested"})

        main = records[SESSION_ID]
        self.assertEqual(main["v"], 1)
        self.assertEqual(main["type"], "session")
        self.assertEqual(main["source_id"], "claude-code@testhost")
        self.assertEqual(main["agent"], "claude-code")
        self.assertEqual(main["state"], "unknown")
        self.assertEqual(main["project"], "demo")
        self.assertEqual(main["title"], "Demo session")
        self.assertEqual(main["started_at"], "2026-11-05T10:00:00.000Z")
        self.assertEqual(main["last_activity_at"], "2026-11-05T10:00:10.000Z")
        self.assertEqual(main["updated_at"], main["last_activity_at"])
        self.assertEqual(main["entries"], 6)
        self.assertEqual(main["model"], "claude-opus-5-5")
        self.assertEqual(main["models"], ["claude-opus-5-5"])
        self.assertEqual(main["usage"], {"basis": "measured", "input_tokens": 1110,
                                         "cached_input_tokens": 100, "output_tokens": 5})
        self.assertNotIn("turn_open", main)

        sub = records["agent-deadbeef"]
        self.assertEqual(sub["parent_session"], {"type": "session", "id": SESSION_ID})
        self.assertEqual(sub["model"], "claude-haiku-5-5")
        self.assertEqual(sub["entries"], 2)
        self.assertEqual(sub["usage"], {"basis": "measured", "input_tokens": 60,
                                        "cached_input_tokens": 20, "output_tokens": 40})

    def test_nested_subagent_transcript_is_found(self):
        nested = self.by_id(self.scan())["agent-nested"]
        self.assertEqual(nested["parent_session"], {"type": "session", "id": SESSION_ID})
        self.assertEqual(nested["model"], "claude-sonnet-5-5")
        self.assertEqual(nested["entries"], 2)

    def test_usage_keeps_the_last_entry_for_a_message_id(self):
        later = json.dumps({
            "type": "assistant", "sessionId": SESSION_ID,
            "timestamp": "2026-11-05T10:00:11.000Z", "cwd": "/Users/me/work/demo",
            "message": {"id": "msg_1", "model": "claude-opus-5-5",
                        "usage": {"input_tokens": 10, "cache_read_input_tokens": 100,
                                  "cache_creation_input_tokens": 1000, "output_tokens": 500}},
        })
        with self.main.open("a") as handle:
            handle.write(later + "\n")
        main = self.by_id(self.scan())[SESSION_ID]
        self.assertEqual(main["usage"]["output_tokens"], 500)
        self.assertEqual(main["usage"]["input_tokens"], 1110)

    def test_worktree_cwd_uses_repo_name(self):
        path = self.main
        path.write_text(path.read_text().replace("/Users/me/work/demo", "/Users/me/work/demo/.claude/worktrees/feature"))
        self.assertEqual(self.by_id(self.scan())[SESSION_ID]["project"], "demo")

    def test_required_fields_present(self):
        for record in self.scan().records:
            for key in ("v", "type", "id", "source_id", "updated_at",
                        "agent", "state", "last_activity_at"):
                self.assertIn(key, record)

    def test_secret_text_is_never_copied(self):
        dumped = json.dumps(self.scan().records)
        self.assertNotIn("SECRET-PROMPT-TEXT", dumped)

    def test_partial_last_line_waits_then_completes(self):
        lines = self.main.read_bytes().splitlines(keepends=True)
        complete, last = b"".join(lines[:-1]), lines[-1]
        self.main.write_bytes(complete + last[: len(last) // 2])
        self.assertEqual(self.by_id(self.scan())[SESSION_ID]["entries"], 5)

        with self.main.open("ab") as handle:
            handle.write(last[len(last) // 2:])
        main = self.by_id(self.scan())[SESSION_ID]
        self.assertEqual(main["entries"], 6)
        self.assertEqual(main["last_activity_at"], "2026-11-05T10:00:10.000Z")

    def test_shrunken_file_is_read_from_the_start(self):
        self.assertEqual(self.by_id(self.scan())[SESSION_ID]["entries"], 6)
        self.main.write_bytes(b"".join(self.main.read_bytes().splitlines(keepends=True)[:2]))
        main = self.by_id(self.scan())[SESSION_ID]
        self.assertEqual(main["entries"], 2)
        self.assertEqual(main["last_activity_at"], "2026-11-05T10:00:05.000Z")
        self.assertEqual(main["usage"]["output_tokens"], 5)

    def test_unparseable_line_is_counted_on_every_scan(self):
        with self.main.open("ab") as handle:
            handle.write(b"not json\n")
        for _ in range(2):
            result = self.scan()
            self.assertEqual(self.by_id(result)[SESSION_ID]["entries"], 6)
            self.assertIn("1 unparseable line(s)", result.detail)

    def test_unchanged_rescan_does_not_double_count(self):
        self.scan()
        main = self.by_id(self.scan())[SESSION_ID]
        self.assertEqual(main["entries"], 6)
        self.assertEqual(main["usage"]["input_tokens"], 1110)

    def test_available_false_when_missing(self):
        adapter = ClaudeCodeAdapter(self.root / "missing", hostname="testhost")
        self.assertFalse(adapter.available())
        self.assertEqual(adapter.scan(NOW).status, "unavailable")


if __name__ == "__main__":
    unittest.main()
