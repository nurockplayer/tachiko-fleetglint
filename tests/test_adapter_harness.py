import hashlib
import re
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from fleetglint.adapters import harness
from fleetglint import liveness

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


def run_id(tool, log):
    """The id both the running entry and the finished row derive from the run's log path."""
    return f"{tool}.{hashlib.sha1(log.encode()).hexdigest()[:12]}"


TERRA_LIVE = "/Users/example/.local/state/cx-exec/terra-live.log"
TERRA_LIVE_ID = run_id("cx", TERRA_LIVE)
LEDGER_HEADER = "started\tended\ttool\tproject\tworker\tmodel\tlead_pane\texit\tadvice\tlog\n"


def make_state(tmp):
    """A state dir with only an empty worker-ledger, for one ad-hoc fixture per test."""
    state = Path(tmp) / "state"
    (state / "worker-ledger").mkdir(parents=True)
    (state / "worker-ledger" / "runs.tsv").write_text(LEDGER_HEADER)
    return state


def write_running(state, pid, log, tool="ds", worker="flash-live",
                  lstart="Thu Nov  5 03:00:00 2026", epoch="1793847600",
                  model="deepseek-flash"):
    running = state / "worker-ledger" / "running"
    running.mkdir(parents=True, exist_ok=True)
    (running / f"{tool}.{pid}").write_text(
        f"{tool}\t{pid}\t{lstart}\t{epoch}\talpha\t{worker}\t{model}\tpane:1\t"
        f"/Users/example/Developer/alpha\t{log}\troutine/{tool}\n")


def write_job(state, job_id, argv, pid=None, result=None):
    directory = state / "job-run" / job_id
    directory.mkdir(parents=True)
    (directory / "cmd").write_text("\n".join(argv) + "\n")
    if pid is not None:
        (directory / "pid").write_text(pid + "\n")
    if result is not None:
        (directory / "result.json").write_text(result)
    return directory


def wait_worker_cmd(role, worker):
    return ["/Users/example/bin/lead-wait", "--inner", "--role", role,
            "--job", "lw-role", "run", worker, "--",
            "/Users/example/bin/ds-exec", worker, "brief.md"]


def lead_wait_cmd(role, op, value, wrapped=()):
    return ["/Users/example/bin/lead-wait", "--inner", "--role", role,
            "--job", "lw-job", op, value, "--", *wrapped]


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
        record = records[run_id("cx", "/Users/example/.local/state/cx-exec/terra-a.log")]
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
        record = records[TERRA_LIVE_ID]
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

        keyed = records[run_id("ds", "/Users/example/.local/state/ds-exec/flash-sub.log")]
        self.assertEqual(keyed["state"], "running")
        self.assertEqual(keyed["provider"], "deepseek")
        self.assertNotIn("process", keyed)

    def test_keyed_running_marker_expires_from_start_time(self):
        for age, expected in ((timedelta(minutes=10), "running"),
                              (timedelta(days=2), "stale")):
            with self.subTest(age=age), tempfile.TemporaryDirectory() as tmp:
                state = make_state(tmp)
                started = NOW - age
                write_running(state, 4100, "-", tool="sonnet", epoch=str(int(started.timestamp())))
                running = state / "worker-ledger" / "running"
                (running / "sonnet.4100").rename(running / "sonnet.4100.toolu_01GQ")
                record = harness.HarnessAdapter(state, hostname="h").scan(NOW).records[0]
                self.assertNotIn("process", record)
                self.assertEqual(record["observed_at"], record["started_at"])
                self.assertEqual(record["stale_after_s"], 21600)
                self.assertEqual(liveness.display(record, NOW).state, expected)

    def test_vanished_running_entry_is_left_to_the_liveness_layer(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            shutil.copytree(FIXTURES, state)
            adapter = harness.HarnessAdapter(state, hostname="fixture-host")
            first = by_id(adapter.scan(NOW).records)
            (state / "worker-ledger/running/cx.4001").unlink()
            second = by_id(adapter.scan(LATER).records)
            # No finished row states the outcome and the liveness layer turns a gone pid into
            # lost by itself, so the adapter emits nothing new and the last record stays.
            self.assertNotIn(TERRA_LIVE_ID, second)
            self.assertEqual(first[TERRA_LIVE_ID]["state"], "running")
            self.assertEqual(adapter.scan(LATER).detail, "7 malformed row(s) skipped")

    def test_log_path_identity_survives_a_restart(self):
        row = ("2026-11-05 12:00 JST\t2026-11-05 12:02 JST\tcx\talpha\tterra-live\t"
               f"gpt-6.1-terra\tpane:9\t0\t-\t{TERRA_LIVE}\tfinished\n")
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            shutil.copytree(FIXTURES, state)
            first = by_id(harness.HarnessAdapter(state, hostname="fixture-host").scan(NOW).records)
            self.assertEqual(first[TERRA_LIVE_ID]["state"], "running")

            (state / "worker-ledger/running/cx.4001").unlink()
            with open(state / "worker-ledger/runs.tsv", "a") as file:
                file.write(row)
            # A fresh adapter: nothing in memory carries the identity, the log path does.
            restarted = harness.HarnessAdapter(state, hostname="fixture-host")
            records = by_id(restarted.scan(LATER).records)
            finished = records[TERRA_LIVE_ID]
            self.assertEqual(finished["state"], "done")
            self.assertEqual(finished["ended_at"], "2026-11-05T12:02:00+09:00")
            self.assertEqual(finished["exit_code"], 0)
            self.assertEqual(finished["summary"], "finished")
            self.assertNotIn("process", finished)
            self.assertEqual(finished["links"],
                             [{"label": "worker log", "path": TERRA_LIVE}])
            self.assertEqual([record for record in records.values()
                              if record.get("title") == "terra-live"], [finished])

    def test_entry_without_a_log_path_falls_back_to_pid_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            shutil.copytree(FIXTURES, state)
            (state / "worker-ledger/running/cx.4001").write_text(
                "cx\t4001\tThu Nov  5 03:00:00 2026\t1793847600\talpha\tterra-nolog\t"
                "gpt-6.1-terra\tpane:9\t/Users/example/Developer/alpha\t-\troutine/cx\n")
            adapter = harness.HarnessAdapter(state, hostname="fixture-host")
            records = by_id(adapter.scan(NOW).records)
        record = records["cx.4001.1793847600"]
        self.assertEqual(record["state"], "running")
        self.assertNotIn("links", record)

    def test_pid_reuse_gives_new_identity(self):
        reused = "/Users/example/.local/state/cx-exec/terra-reused.log"
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            shutil.copytree(FIXTURES, state)
            adapter = harness.HarnessAdapter(state, hostname="fixture-host")
            adapter.scan(NOW)
            (state / "worker-ledger/running/cx.4001").write_text(
                "cx\t4001\tThu Nov  5 03:01:00 2026\t1793847660\talpha\tterra-reused\t"
                "gpt-6.1-terra\tpane:9\t/Users/example/Developer/alpha\t"
                f"{reused}\troutine/cx\n")
            records = by_id(adapter.scan(LATER).records)
            new_id = run_id("cx", reused)
            self.assertNotEqual(new_id, TERRA_LIVE_ID)
            self.assertEqual(records[new_id]["state"], "running")
            self.assertEqual(records[new_id]["process"]["pid"], 4001)
            self.assertNotIn(TERRA_LIVE_ID, records)

    def test_process_start_time_is_lstart_not_the_ledger_epoch(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = make_state(tmp)
            log = state / "terra-start.log"
            # 1793847600 is 2026-11-05 12:00 JST; the process started 7 s before the row.
            write_running(state, 4001, log, tool="cx", worker="terra-start",
                          lstart="Thu Nov  5 02:59:53 2026", model="gpt-6.1-terra")
            record = by_id(harness.HarnessAdapter(state, hostname="h").scan(NOW).records)[
                run_id("cx", str(log))]
        self.assertEqual(record["process"]["start_time"], "2026-11-05T11:59:53+09:00")
        self.assertEqual(record["started_at"], "2026-11-05T12:00:00+09:00")

    def test_unparsed_lstart_leaves_start_time_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = make_state(tmp)
            log = state / "flash-nodate.log"
            write_running(state, 4004, log, lstart="not a date")
            record = by_id(harness.HarnessAdapter(state, hostname="h").scan(NOW).records)[
                run_id("ds", str(log))]
        self.assertEqual(record["state"], "running")
        self.assertEqual(record["process"]["pid"], 4004)
        self.assertNotIn("start_time", record["process"])

    def test_waiting_state_from_the_wrapper_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = make_state(tmp)
            log = state / "flash-live.log"
            log.write_text("ds-exec: model says hello\n"
                           "ds-exec: waiting on job job-20261105-120000-abcd (cap 4 h)\n")
            write_running(state, 4100, log)
            write_job(state, "job-20261105-120000-abcd", ["sleep", "30"],
                      pid="5001\tThu Nov  5 02:00:00 2026")
            records = by_id(harness.HarnessAdapter(state, hostname="h").scan(NOW).records)
        record = records[run_id("ds", str(log))]
        self.assertEqual(record["state"], "waiting")
        self.assertEqual(record["waits_on"],
                         [{"type": "job", "id": "job-20261105-120000-abcd"}])
        self.assertEqual(records["job-20261105-120000-abcd"]["run"],
                         {"type": "run", "id": run_id("ds", str(log))})

    def test_newest_finished_line_means_running(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = make_state(tmp)
            log = state / "flash-done.log"
            log.write_text("ds-exec: waiting on job job-1 (cap 4 h)\n"
                           "ds-exec: job job-1 finished; exit 0\n")
            write_running(state, 4101, log)
            record = by_id(harness.HarnessAdapter(state, hostname="h").scan(NOW).records)[
                run_id("ds", str(log))]
        self.assertEqual(record["state"], "running")
        self.assertNotIn("waits_on", record)

    def test_log_that_is_not_a_regular_file_gives_no_wait(self):
        for kind in ("missing", "directory", "symlink"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                state = make_state(tmp)
                log = state / "flash-nolog.log"
                if kind == "directory":
                    log.mkdir()
                elif kind == "symlink":
                    (state / "target.log").write_text(
                        "ds-exec: waiting on job job-1 (cap 4 h)\n")
                    log.symlink_to(state / "target.log")
                write_running(state, 4102, log)
                record = by_id(harness.HarnessAdapter(state, hostname="h").scan(NOW).records)[
                    run_id("ds", str(log))]
                self.assertEqual(record["state"], "running")
                self.assertNotIn("waits_on", record)

    def test_project_comes_from_the_git_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app" / ".git" / "worktrees" / "feature").mkdir(parents=True)
            (root / "app" / "ui").mkdir()
            (root / "elsewhere" / "feature" / "src").mkdir(parents=True)
            (root / "elsewhere" / "feature" / ".git").write_text(
                f"gitdir: {root}/app/.git/worktrees/feature\n")
            (root / "bare.git" / "worktrees" / "topic").mkdir(parents=True)
            (root / "elsewhere" / "topic").mkdir()
            (root / "elsewhere" / "topic" / ".git").write_text(
                f"gitdir: {root}/bare.git/worktrees/topic\n")
            self.assertEqual(harness._project_from_path(str(root / "app" / "ui")), "app")
            self.assertEqual(
                harness._project_from_path(str(root / "elsewhere" / "feature" / "src")), "app")
            self.assertEqual(harness._project_from_path(str(root / "elsewhere" / "topic")), "bare")
        self.assertEqual(harness._project_from_path("/gone/repo/.claude/worktrees/x"), "repo")
        self.assertEqual(harness._project_from_path("/gone/plain"), "plain")

    def test_git_repo_name_with_nested_worktrees_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            worktree = root / "linked"
            worktree.mkdir()
            (worktree / ".git").write_text(
                f"gitdir: {root}/worktrees/app/.git/worktrees/feature\n")
            self.assertEqual(harness._project_from_path(str(worktree)), "app")

    def test_jobs(self):
        records = by_id(self.result.records)
        build = records["build-20261105-090000-777"]
        self.assertEqual(build["state"], "done")
        self.assertEqual(build["exit_code"], 0)
        self.assertEqual(build["command_summary"], "make test")
        self.assertEqual(build["project"], "alpha")
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

        curl = records["curl-20261105-050000-222"]
        self.assertEqual(curl["command_summary"], "curl")
        self.assertNotIn("hunter2", str(self.result.records))

        fetch = records["fetch-20261105-040000-444"]
        self.assertEqual(fetch["command_summary"], "curl https://example.test/status")
        for secret in ("alice", "hunter2", "synthetictokenvalue"):
            self.assertNotIn(secret, str(self.result.records))

    def test_job_without_a_pid_is_unknown(self):
        record = by_id(self.result.records)["nopid-20261105-030000-000"]
        self.assertEqual(record["state"], "unknown")
        self.assertEqual(record["summary"], "no pid recorded")
        self.assertEqual(record["command_summary"], "sleep 30")
        self.assertNotIn("process", record)
        self.assertNotIn("observed_at", record)
        self.assertNotIn("started_at", record)

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

    def test_lead_wait_pr_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = make_state(tmp)
            write_job(state, "lw-review-20261105-110000",
                      ["/Users/example/bin/lead-wait", "--inner", "--role", "lead-alpha",
                       "--job", "lw-review-20261105-110000", "pr", "42", "--scope", "notes.md"],
                      pid="5100\tThu Nov  5 02:00:00 2026")
            # The marker fallback must not overwrite what the job's own cmd says.
            marker = state / "lead-wait" / "lead-beta" / "lw-review-20261105-110000"
            marker.parent.mkdir(parents=True)
            marker.write_text("pr\t42\t2026-11-05 11:00 JST\n")
            record = by_id(harness.HarnessAdapter(state, hostname="h").scan(NOW).records)[
                "lw-review-20261105-110000"]
        self.assertEqual(record["kind"], "wait")
        self.assertEqual(record["role_id"], "lead-alpha")
        self.assertEqual(record["title"], "PR #42 review")
        self.assertEqual(record["command_summary"], "review PR #42")

    def test_lead_wait_run_job_names_the_worker(self):
        wrapped = ["/Users/example/bin/env", "FOO=bar", "BAZ=1",
                   "/Users/example/bin/ds-exec", "--effort", "high", "ds-fg-13", "brief.md"]
        with tempfile.TemporaryDirectory() as tmp:
            state = make_state(tmp)
            write_job(state, "lw-alpha-20261105-110000",
                      lead_wait_cmd("lead-alpha", "run", "alpha-task", wrapped),
                      pid="5101\tThu Nov  5 02:00:00 2026")
            record = by_id(harness.HarnessAdapter(state, hostname="h").scan(NOW).records)[
                "lw-alpha-20261105-110000"]
        self.assertEqual(record["kind"], "wait-worker")
        self.assertEqual(record["role_id"], "lead-alpha")
        self.assertEqual(record["title"], "alpha-task")
        self.assertEqual(record["command_summary"], "ds-exec --effort high")

    def test_lead_wait_run_job_without_a_wrapper_is_a_plain_wait(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = make_state(tmp)
            write_job(state, "lw-tests-20261105-110000",
                      lead_wait_cmd("Lead-Alpha", "run", "tests",
                                    ["bash", "run-tests", "--verbose"]),
                      pid="5102\tThu Nov  5 02:00:00 2026")
            record = by_id(harness.HarnessAdapter(state, hostname="h").scan(NOW).records)[
                "lw-tests-20261105-110000"]
        self.assertEqual(record["kind"], "wait")
        self.assertEqual(record["title"], "tests")
        self.assertEqual(record["command_summary"], "bash run-tests --verbose")
        self.assertNotIn("role_id", record)

    def test_job_project_comes_from_cwd(self):
        cases = {
            "/Users/example/Developer/alpha": "alpha",
            "/Users/example/Developer/tachiko-fleetglint/.claude/worktrees/ds-fg-13":
                "tachiko-fleetglint",
        }
        for cwd, expected in cases.items():
            with self.subTest(cwd=cwd), tempfile.TemporaryDirectory() as tmp:
                state = make_state(tmp)
                directory = write_job(state, "job-20261105-120000", ["make", "test"],
                                      pid="5200\tThu Nov  5 02:00:00 2026")
                (directory / "cwd").write_text(cwd + "\n")
                record = by_id(harness.HarnessAdapter(state, hostname="h").scan(NOW).records)[
                    "job-20261105-120000"]
            self.assertEqual(record["project"], expected)

    def test_job_without_a_readable_cwd_has_no_project(self):
        for kind in ("absent", "directory"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                state = make_state(tmp)
                directory = write_job(state, "job-20261105-120100", ["make", "test"],
                                      pid="5201\tThu Nov  5 02:00:00 2026")
                if kind == "directory":
                    (directory / "cwd").mkdir()
                record = by_id(harness.HarnessAdapter(state, hostname="h").scan(NOW).records)[
                    "job-20261105-120100"]
            self.assertNotIn("project", record)

    def test_run_role_from_the_wait_worker_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = make_state(tmp)
            log = state / "ds-fg-13.log"
            write_running(state, 4200, log, worker="ds-fg-13")
            write_job(state, "lw-role-1", wait_worker_cmd("lead-alpha", "ds-fg-13"),
                      pid="5300\tThu Nov  5 02:59:00 2026")
            record = by_id(harness.HarnessAdapter(state, hostname="h").scan(NOW).records)[
                run_id("ds", str(log))]
        self.assertEqual(record["role_id"], "lead-alpha")
        self.assertNotIn("worker", record)

    def test_two_wait_worker_roles_disagree_gives_no_role(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = make_state(tmp)
            log = state / "ds-fg-14.log"
            write_running(state, 4201, log, worker="ds-fg-14")
            write_job(state, "lw-role-2", wait_worker_cmd("lead-alpha", "ds-fg-14"),
                      pid="5301\tThu Nov  5 02:59:00 2026")
            write_job(state, "lw-role-3", wait_worker_cmd("lead-beta", "ds-fg-14"),
                      pid="5302\tThu Nov  5 02:59:30 2026")
            record = by_id(harness.HarnessAdapter(state, hostname="h").scan(NOW).records)[
                run_id("ds", str(log))]
        self.assertNotIn("role_id", record)

    def test_wait_worker_that_ended_before_the_run_gives_no_role(self):
        result = ('{"status": "ok", "exit_code": 0, '
                  '"started": "2026-11-05T10:00:00+09:00", '
                  '"ended": "2026-11-05T10:30:00+09:00"}')
        with tempfile.TemporaryDirectory() as tmp:
            state = make_state(tmp)
            log = state / "ds-fg-15.log"
            write_running(state, 4202, log, worker="ds-fg-15")
            write_job(state, "lw-role-4", wait_worker_cmd("lead-alpha", "ds-fg-15"),
                      result=result)
            record = by_id(harness.HarnessAdapter(state, hostname="h").scan(NOW).records)[
                run_id("ds", str(log))]
        self.assertNotIn("role_id", record)

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

    def test_owner_notify_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = make_state(tmp)
            (state / "owner-notify").mkdir()
            (state / "owner-notify" / "log.tsv").write_text(
                "2026-11-07 07:08 JST\tkey-a\tlead-alpha\tskipped\tnot yet\n"
                "2026-11-07 07:09 JST\tkey-a\tlead-alpha\tsent\tsent to owner\n"
                "2026-11-07 07:10 JST\tkey-a\tlead-alpha\tskipped\ttoo soon\n"
                "2026-11-07 07:11 JST\tkey-b\tlead-beta\tskipped\tno owner\n"
                "2026-11-07 07:12 JST\tkey-c\tlead-gamma\tinfo\tignored\n"
                "not a row\n")
            result = harness.HarnessAdapter(state, hostname="h").scan(NOW)
        records = by_id(result.records)
        self.assertEqual(sorted(records), ["owner-notify.key-a", "owner-notify.key-b"])
        sent = records["owner-notify.key-a"]
        self.assertEqual(sent["role_id"], "owner")
        self.assertEqual(sent["state"], "open")
        self.assertEqual(sent["kind"], "owner-notify")
        self.assertTrue(sent["action_required"])
        self.assertEqual(sent["created_at"], "2026-11-07T07:09:00+09:00")
        self.assertEqual(sent["updated_at"], "2026-11-07T07:09:00+09:00")
        self.assertEqual(sent["outcome"], "sent")
        self.assertEqual(sent["detail"], "sent to owner")
        self.assertEqual(sent["subject"],
                         {"type": "external", "kind": "harness_ref",
                          "key": "from:lead-alpha"})
        self.assertEqual(records["owner-notify.key-b"]["outcome"], "skipped")
        self.assertEqual(result.detail, "1 malformed row(s) skipped")

    def test_owner_notify_rows_without_a_key_stay_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = make_state(tmp)
            (state / "owner-notify").mkdir()
            (state / "owner-notify" / "log.tsv").write_text(
                "2026-11-07 07:08 JST\t-\tlead-alpha\tsent\tfirst\n"
                "2026-11-07 07:09 JST\t-\tlead-beta\tsent\tsecond\n"
                "2026-11-07 07:09 JST\t-\tlead-beta\tsent\tsecond\n")
            result = harness.HarnessAdapter(state, hostname="h").scan(NOW)
        items = [r for r in result.records if r.get("kind") == "owner-notify"]
        self.assertEqual(sorted(r["detail"] for r in items), ["first", "second", "second"])
        self.assertEqual(len({r["id"] for r in items}), 3)

    def test_owner_notify_without_a_log_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = make_state(tmp)
            result = harness.HarnessAdapter(state, hostname="h").scan(NOW)
        self.assertEqual(result.records, [])
        self.assertIsNone(result.detail)

    def test_owner_notify_reserved_keys_and_length(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = make_state(tmp)
            (state / "owner-notify").mkdir()
            (state / "owner-notify" / "log.tsv").write_text(
                "2026-11-07 07:08 JST\t-\tlead\tsent\tunkeyed\n"
                "2026-11-07 07:09 JST\tline.1\tlead\tsent\texplicit\n"
                "2026-11-07 07:10 JST\tkey:x\tlead\tsent\tescaped\n"
                f"2026-11-07 07:11 JST\tline.{'x' * 180}\tlead\tsent\ttoo long\n")
            result = harness.HarnessAdapter(state, hostname="h").scan(NOW)
        self.assertEqual(set(by_id(result.records)), {
            "owner-notify.line.1", "owner-notify.key:line.1", "owner-notify.key:key:x"})
        self.assertEqual(result.detail, "1 malformed row(s) skipped")

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
