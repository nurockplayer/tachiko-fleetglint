import argparse
import contextlib
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fleetglint import demo, liveness, schema
from fleetglint.adapters.base import short_hostname

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 6, 12, 0, tzinfo=JST)


class DemoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.root = self.dir / "sources"
        self.path = self.root / demo.SOURCE_ID

    def run_demo(self, clear=False, now=NOW):
        config_file = self.dir / "config.toml"
        config_file.write_text(f'[server]\nport = 1\n[ingest]\nroots = ["{self.root}"]\n')
        args = argparse.Namespace(config=str(config_file), clear=clear)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = demo.run(args, now=now)
        return code, out.getvalue()

    def records(self):
        found = []
        for segment in sorted(self.path.glob("*.ndjson")):
            for line in segment.read_text(encoding="utf-8").splitlines():
                found.append(json.loads(line))
        return found

    def latest(self, records):
        return {(record["type"], record["id"]): record for record in records}

    def test_writes_a_valid_labelled_sample(self):
        code, text = self.run_demo()
        self.assertEqual(code, 0)
        self.assertTrue(self.path.is_dir())
        self.assertIn("remove with fleetglint demo --clear", text)

        records = self.records()
        self.assertGreater(len(records), 0)
        for record in records:
            self.assertEqual(schema.validate(record), [], record["id"])
            self.assertEqual(record["source_id"], demo.SOURCE_ID)
            self.assertTrue(record["title"].startswith("[demo] "), record["id"])

        latest = self.latest(records)
        lead = latest[("run", "demo-lead-1")]
        self.assertEqual(lead["state"], "done")
        self.assertEqual(latest[("run", "demo-lead-2")]["resume_of"]["id"], "demo-lead-1")
        self.assertEqual(latest[("run", "demo-worker-1")]["parent_run"]["id"], "demo-lead-1")
        self.assertEqual(latest[("job", "demo-job-1")]["run"]["id"], "demo-lead-1")
        inbox = latest[("inbox_item", "demo-inbox-1")]
        self.assertEqual((inbox["state"], inbox["action_required"]), ("open", True))
        self.assertEqual(inbox["subject"]["id"], "demo-job-1")

        projects = {record["project"] for record in records if "project" in record}
        self.assertEqual(projects, set(demo.PROJECTS))
        pairs = {(record["agent"], record["model"]) for record in records if "model" in record}
        self.assertEqual(len(pairs), 4)

        stale = latest[("run", "demo-stale-1")]
        self.assertEqual(stale["stale_after_s"], 900)
        self.assertEqual(stale["observed_at"], (NOW - timedelta(hours=2)).isoformat())
        self.assertEqual(liveness.display(stale, NOW).state, "stale")

        lost = latest[("run", "demo-lost-1")]
        self.assertEqual(lost["process"]["host"], short_hostname())
        with self.assertRaises(ProcessLookupError):
            os.kill(lost["process"]["pid"], 0)
        self.assertEqual(liveness.display(lost, NOW).state, "lost")

        self.assertEqual(latest[("run", "demo-unknown-1")]["state"], "unknown")
        self.assertEqual(latest[("run", "demo-failed-1")]["state"], "failed")

        recent = latest[("session", "demo-session-1")]
        idle = latest[("session", "demo-session-2")]
        self.assertEqual(liveness.display(recent, NOW).state, "recent")
        self.assertEqual(liveness.display(idle, NOW).state, "idle")

    def test_clear_removes_only_the_demo_source(self):
        self.assertEqual(self.run_demo()[0], 0)
        other = self.root / "someone@host"
        other.mkdir()
        code, text = self.run_demo(clear=True)
        self.assertEqual(code, 0)
        self.assertFalse(self.path.exists())
        self.assertTrue(other.exists())
        self.assertIn("disappear from the board on the next ingest pass", text)
        self.assertIn("fleetglint ingest --once", text)

    def test_clear_refuses_a_symlink(self):
        self.root.mkdir(parents=True)
        target = self.dir / "elsewhere"
        target.mkdir()
        self.path.symlink_to(target, target_is_directory=True)
        code, _ = self.run_demo(clear=True)
        self.assertEqual(code, 1)
        self.assertTrue(self.path.is_symlink())
        self.assertTrue(target.is_dir())

    def test_rerun_appends_new_versions_to_the_same_segment(self):
        self.assertEqual(self.run_demo()[0], 0)
        first = self.records()
        later = NOW + timedelta(minutes=5)
        self.assertEqual(self.run_demo(now=later)[0], 0)
        records = self.records()

        segments = sorted(self.path.glob("*.ndjson"))
        self.assertEqual(len(segments), 1)
        self.assertEqual(len(records), 2 * len(first))
        self.assertEqual([record["id"] for record in records[:len(first)]],
                         [record["id"] for record in records[len(first):]])
        for record in records:
            self.assertEqual(schema.validate(record), [], record["id"])
        latest = self.latest(records)
        self.assertEqual(latest[("run", "demo-lead-2")]["updated_at"],
                         (later - timedelta(minutes=2)).isoformat())


if __name__ == "__main__":
    unittest.main()
