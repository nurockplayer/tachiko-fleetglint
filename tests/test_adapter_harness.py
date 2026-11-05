import hashlib
import re
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from fleetglint.adapters import harness

FIXTURES = Path(__file__).parent / "fixtures" / "harness" / "state"
JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 5, 12, 0, tzinfo=JST)
LATER = datetime(2026, 11, 5, 12, 1, tzinfo=JST)

TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")
ID = re.compile(r"^[^\s\x00-\x1f\x7f]{1,200}$")
SOURCE = re.compile(r"^(?!.*\n)[a-z0-9][a-z0-9._-]*(@[a-z0-9][a-z0-9._-]*)?$")
RUN_STATES = {"queued", "running", "waiting", "done", "failed", "cancelled", "unknown"}
JOB_STATES = {"queued", "running", "done", "failed", "cancelled", "unknown"}
TERMINAL = {"done", "failed", "cancelled"}


def check(record):
    """Minimal v1 field check until fleetglint.schema lands (see the PR body)."""
    problems = []

    def ok(condition, message):
        if not condition:
            problems.append(message)

    ok(record.get("v") == 1, "v")
    ok(record.get("type") in {"run", "job", "inbox_item", "session"}, "type")
    ok(bool(ID.match(str(record.get("id", "")))), "id")
    ok(bool(SOURCE.match(str(record.get("source_id", "")))), "source_id")
    ok(bool(TS.match(str(record.get("updated_at", "")))), "updated_at")
    if "observed_at" in record:
        ok(bool(TS.match(record["observed_at"])), "observed_at")
    if "stale_after_s" in record:
        ok(isinstance(record["stale_after_s"], int) and record["stale_after_s"] >= 1, "stale_after_s")
    if "project" in record:
        ok(1 <= len(record["project"]) <= 200, "project")
    if "title" in record:
        ok(len(record["title"]) <= 200, "title")
    for link in record.get("links", []):
        ok(len(link.get("label", "")) <= 80, "link label")
        ok(("url" in link) != ("path" in link), "link has exactly one of url/path")
        if "path" in link:
            ok(link["path"].startswith("/"), "link path absolute")
        if "url" in link:
            ok(link["url"].startswith(("http://", "https://")), "link url")

    record_type = record.get("type")
    if record_type == "run":
        ok(record.get("state") in RUN_STATES, "run state")
        ok(isinstance(record.get("agent"), str) and 1 <= len(record["agent"]) <= 64, "run agent")
        if record.get("state") in {"running", "waiting"} | TERMINAL:
            ok(bool(TS.match(str(record.get("started_at", "")))), "run started_at")
        if record.get("state") in TERMINAL:
            ok(bool(TS.match(str(record.get("ended_at", "")))), "run ended_at")
        if "process" in record:
            ok(record["process"].get("host") and isinstance(record["process"].get("pid"), int), "process")
    elif record_type == "job":
        ok(record.get("state") in JOB_STATES, "job state")
        ok(isinstance(record.get("command_summary"), str)
           and 1 <= len(record["command_summary"]) <= 200, "command_summary")
        if record.get("state") in {"running"} | TERMINAL:
            ok(bool(TS.match(str(record.get("started_at", "")))), "job started_at")
        if record.get("state") in TERMINAL:
            ok(bool(TS.match(str(record.get("ended_at", "")))), "job ended_at")
        if "signal" in record and record["signal"] is not None:
            ok(isinstance(record["signal"], str) and len(record["signal"]) <= 32, "signal")
    elif record_type == "inbox_item":
        ok(isinstance(record.get("role_id"), str) and record["role_id"], "role_id")
        ok(record.get("state") in {"open", "acked"}, "inbox state")
        ok(isinstance(record.get("kind"), str) and 1 <= len(record["kind"]) <= 64, "kind")
        ok(bool(TS.match(str(record.get("created_at", "")))), "created_at")
        subject = record.get("subject") or {}
        if subject.get("type") == "external":
            ok(bool(subject.get("kind")) and bool(subject.get("key") or subject.get("url")), "external subject")
        else:
            ok(bool(subject.get("type")) and bool(subject.get("id")), "subject")
        if record.get("state") == "acked":
            ok(bool(TS.match(str(record.get("acked_at", "")))), "acked_at")
    for touched in ("created_at", "started_at", "ended_at", "acked_at", "observed_at"):
        if touched in record:
            try:
                datetime.fromisoformat(record[touched].replace("Z", "+00:00"))
            except ValueError:
                problems.append(f"{touched} not a real time")
    return problems


def by_id(records):
    return {record["id"]: record for record in records}


class HarnessAdapterTest(unittest.TestCase):
    def setUp(self):
        self.adapter = harness.HarnessAdapter(FIXTURES, hostname="fixture-host")
        self.result = self.adapter.scan(NOW)

    def test_identity_and_allowed_roots(self):
        self.assertEqual(self.adapter.source_id, "tachiko-harness@fixture-host")
        self.assertEqual(self.adapter.allowed_roots,
                         [FIXTURES / "job-run", FIXTURES / "lead-wait"])
        with mock.patch.object(harness, "short_hostname", return_value="fake-host"):
            self.assertEqual(harness.HarnessAdapter(FIXTURES).source_id,
                             "tachiko-harness@fake-host")

    def test_unavailable_without_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter = harness.HarnessAdapter(Path(tmp), hostname="h")
            self.assertFalse(adapter.available())
            result = adapter.scan(NOW)
        self.assertEqual(result.status, "unavailable")
        self.assertEqual(result.records, [])
        self.assertIn("not found", result.detail)

    def test_unreadable_ledger_is_unavailable(self):
        with mock.patch.object(harness, "_text", side_effect=PermissionError(13, "denied")):
            result = self.adapter.scan(NOW)
        self.assertEqual(result.status, "unavailable")
        self.assertIn("cannot read", result.detail)

    def test_finished_ledger_rows(self):
        records = by_id(self.result.records)
        row = next(line for line in (FIXTURES / "worker-ledger/runs.tsv").read_text().splitlines()
                   if line.startswith("2026-11-05 04:00 JST"))
        digest = hashlib.sha1(row.encode()).hexdigest()[:12]
        record = records[f"cx.ledger.{digest}"]
        self.assertEqual(record["state"], "done")
        self.assertEqual(record["agent"], "codex-cli")
        self.assertEqual(record["exit_code"], 0)
        self.assertEqual(record["project"], "alpha")
        self.assertEqual(record["title"], "terra-a")
        self.assertEqual(record["model"], "gpt-6.1-terra")
        self.assertEqual(record["summary"], "handed off")
        self.assertEqual(record["started_at"], "2026-11-05T04:00:00+09:00")
        self.assertEqual(record["ended_at"], "2026-11-05T04:30:00+09:00")
        self.assertEqual(record["links"],
                         [{"label": "worker log",
                           "path": "/Users/example/.local/state/cx-exec/terra-a.log"}])

        failed = next(r for r in self.result.records if r.get("title") == "flash-b")
        self.assertEqual(failed["state"], "failed")
        self.assertEqual(failed["exit_code"], 3)
        self.assertEqual(failed["agent"], "claude-code")
        self.assertEqual(failed["provider"], "deepseek")

        lost = next(r for r in self.result.records if r.get("title") == "agy-c")
        self.assertEqual(lost["state"], "unknown")
        self.assertEqual(lost["agent"], "antigravity")
        self.assertNotIn("model", lost)
        self.assertNotIn("ended_at", lost)
        self.assertNotIn("exit_code", lost)
        self.assertNotIn("links", lost)

        old_format = next(r for r in self.result.records if r.get("title") == "haiku-d")
        self.assertEqual(old_format["state"], "done")
        self.assertEqual(old_format["agent"], "claude-code")
        self.assertNotIn("summary", old_format)

    def test_malformed_rows_are_counted(self):
        self.assertEqual(self.result.detail, "7 malformed row(s) skipped")
        titles = {record.get("title") for record in self.result.records}
        self.assertNotIn("terra-b", titles)

    def test_running_entries(self):
        records = by_id(self.result.records)
        record = records["cx.4001.1793847600"]
        self.assertEqual(record["state"], "running")
        self.assertEqual(record["agent"], "codex-cli")
        self.assertEqual(record["started_at"], "2026-11-05T12:00:00+09:00")
        self.assertEqual(record["stale_after_s"], 3600)
        self.assertEqual(record["observed_at"], "2026-11-05T12:00:00+09:00")
        self.assertEqual(record["process"], {"host": "fixture-host", "pid": 4001,
                                             "start_time": "2026-11-05T12:00:00+09:00"})
        self.assertEqual(record["title"], "terra-live")
        self.assertEqual(record["links"][0]["path"],
                         "/Users/example/.local/state/cx-exec/terra-live.log")

        keyed = records["ds.4002.toolu_synthetickey.1793844000"]
        self.assertEqual(keyed["state"], "running")
        self.assertEqual(keyed["provider"], "deepseek")
        self.assertEqual(keyed["process"]["pid"], 4002)

    def test_vanished_running_entry_becomes_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            shutil.copytree(FIXTURES, state)
            adapter = harness.HarnessAdapter(state, hostname="fixture-host")
            adapter.scan(NOW)
            (state / "worker-ledger/running/cx.4001").unlink()
            second = adapter.scan(LATER)
            record = by_id(second.records)["cx.4001.1793847600"]
            self.assertEqual(record["state"], "unknown")
            self.assertNotEqual(record["state"], "done")
            self.assertNotIn("process", record)
            self.assertNotIn("observed_at", record)
            self.assertEqual(record["updated_at"], "2026-11-05T12:01:00+09:00")
            third = adapter.scan(LATER)
            self.assertNotIn("cx.4001.1793847600", by_id(third.records))

    def test_vanished_entry_with_finished_row_is_not_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            shutil.copytree(FIXTURES, state)
            adapter = harness.HarnessAdapter(state, hostname="fixture-host")
            adapter.scan(NOW)
            (state / "worker-ledger/running/cx.4001").unlink()
            with open(state / "worker-ledger/runs.tsv", "a") as file:
                file.write("2026-11-05 12:00 JST\t2026-11-05 12:02 JST\tcx\talpha\tterra-live\t"
                           "gpt-6.1-terra\tpane:9\t0\t-\t"
                           "/Users/example/.local/state/cx-exec/terra-live.log\t\n")
            second = adapter.scan(LATER)
            records = by_id(second.records)
            self.assertNotIn("cx.4001.1793847600", records)
            finished = [r for r in second.records
                        if r.get("title") == "terra-live" and r["state"] == "done"]
            self.assertEqual(len(finished), 1)

    def test_pid_reuse_gives_new_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            shutil.copytree(FIXTURES, state)
            adapter = harness.HarnessAdapter(state, hostname="fixture-host")
            adapter.scan(NOW)
            (state / "worker-ledger/running/cx.4001").write_text(
                "cx\t4001\tThu Nov  5 03:01:00 2026\t1793847660\talpha\tterra-reused\t"
                "gpt-6.1-terra\tpane:9\t/Users/example/Developer/alpha\t"
                "/Users/example/.local/state/cx-exec/terra-reused.log\troutine/cx\n")
            records = by_id(adapter.scan(LATER).records)
            self.assertEqual(records["cx.4001.1793847660"]["state"], "running")
            self.assertEqual(records["cx.4001.1793847600"]["state"], "unknown")

    def test_jobs(self):
        records = by_id(self.result.records)
        build = records["build-20261105-090000-777"]
        self.assertEqual(build["state"], "done")
        self.assertEqual(build["exit_code"], 0)
        self.assertEqual(build["command_summary"], "make test")
        self.assertEqual(build["started_at"], "2026-11-05T09:00:00+09:00")
        self.assertEqual(build["ended_at"], "2026-11-05T09:10:00+09:00")
        self.assertEqual(build["result_path"],
                         str(FIXTURES / "job-run/build-20261105-090000-777/result.json"))
        self.assertEqual(build["log_path"],
                         "/Users/example/.local/state/job-run/build-20261105-090000-777/log")
        self.assertNotIn("process", build)

        killed = records["kill-20261105-080000-555"]
        self.assertEqual(killed["state"], "failed")
        self.assertEqual(killed["exit_code"], 143)
        self.assertEqual(killed["signal"], "SIGTERM")

        corrupt = records["corrupt-20261105-070000-333"]
        self.assertEqual(corrupt["state"], "unknown")
        self.assertEqual(corrupt["command_summary"], "true")
        self.assertIn("started_at", corrupt)
        self.assertNotIn("no-cmd-20261105-060000-111", records)

    def test_running_job_and_wait_marker(self):
        job = by_id(self.result.records)["lw-alpha-20261105-101500"]
        self.assertEqual(job["state"], "running")
        self.assertEqual(job["kind"], "wait")
        self.assertEqual(job["role_id"], "lead-alpha")
        self.assertEqual(job["command_summary"], "bash run-tests")
        self.assertEqual(job["started_at"], "2026-11-05T10:15:00+09:00")
        self.assertEqual(job["observed_at"], "2026-11-05T12:00:00+09:00")
        self.assertEqual(job["process"], {"host": "fixture-host", "pid": 5001,
                                          "start_time": "2026-11-05T10:15:00+09:00"})

    def test_inbox_items(self):
        records = by_id(self.result.records)
        self.assertEqual(len([r for r in self.result.records if r["type"] == "inbox_item"]), 4)

        job_item = records["ev-20261105-101600-aaaa"]
        self.assertEqual(job_item["role_id"], "lead-alpha")
        self.assertEqual(job_item["state"], "open")
        self.assertEqual(job_item["outcome"], "failed")
        self.assertTrue(job_item["action_required"])
        self.assertEqual(job_item["subject"],
                         {"type": "job", "id": "lw-alpha-20261105-101500"})
        self.assertEqual(job_item["created_at"], "2026-11-05T10:16:00+09:00")
        self.assertEqual(job_item["updated_at"], "2026-11-05T10:16:00+09:00")

        pr_item = records["ev-20261105-101700-bbbb"]
        self.assertEqual(pr_item["state"], "acked")
        self.assertEqual(pr_item["acked_at"], "2026-11-05T10:20:00+09:00")
        self.assertEqual(pr_item["updated_at"], "2026-11-05T10:20:00+09:00")
        self.assertEqual(pr_item["subject"], {
            "type": "external", "kind": "github_pr",
            "key": "nurockplayer/example#42",
            "url": "https://github.com/nurockplayer/example/pull/42"})
        self.assertNotIn("action_required", pr_item)

        unknown_pr = records["ev-20261105-101800-cccc"]
        self.assertEqual(unknown_pr["subject"], {
            "type": "external", "kind": "harness_ref", "key": "pr:#7"})
        self.assertTrue(unknown_pr["action_required"])

        unknown_run = records["ev-20261105-101900-eeee"]
        self.assertEqual(unknown_run["subject"], {
            "type": "external", "kind": "harness_ref", "key": "run:missing-label"})
        self.assertNotIn("action_required", unknown_run)

        self.assertNotIn("ev-20261105-101850-dddd", records)
        self.assertNotIn("ev-20261105-102000-ffff", records)

    def test_every_record_passes_minimal_schema(self):
        for record in self.result.records:
            with self.subTest(record=record["id"]):
                self.assertEqual(check(record), [])

    def test_rescan_is_identical(self):
        again = self.adapter.scan(NOW)
        self.assertEqual(again.detail, self.result.detail)
        self.assertEqual(again.records, self.result.records)

    def test_missing_optional_dirs_give_no_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            (state / "worker-ledger").mkdir()
            (state / "worker-ledger/runs.tsv").write_text(
                "started\tended\ttool\tproject\tworker\tmodel\tlead_pane\texit\tadvice\tlog\n")
            adapter = harness.HarnessAdapter(state, hostname="h")
            result = adapter.scan(NOW)
        self.assertEqual((result.status, result.detail, result.records), ("ok", None, []))


if __name__ == "__main__":
    unittest.main()
