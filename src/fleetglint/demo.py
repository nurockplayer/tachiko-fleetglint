"""`fleetglint demo`: write a labelled sample source `demo@fleetglint` (architecture §8.1)."""
import os
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

from fleetglint import config, emit, schema
from fleetglint.adapters.base import short_hostname

SOURCE_ID = "demo@fleetglint"
PROJECTS = ("eddington-1919", "gteki", "fleetglint")
LEAD_SESSION = "5b1e0c8e-2d7a-4c55-9a11-0f6e2b9d4c01"
WORKER_SESSION = "3c90f0b2-3a04-4c2e-9060-3e3cf5507ce5"


def run(args, now=None):
    """Append the sample source (same ids, fresh versions) or remove it with `--clear`."""
    now = now or datetime.now().astimezone()
    try:
        cfg = config.load(args.config)
    except config.ConfigError as exc:
        print(f"fleetglint demo: {exc}", file=sys.stderr)
        return 1
    root = cfg.roots[0]
    if args.clear:
        return _clear(root)
    try:
        records = build(now)
        for record in records:
            errors = schema.validate(record)
            assert not errors, f"{record['type']} {record['id']}: {errors}"
            emit.append_record(record, root)
    except (OSError, ValueError) as exc:
        print(f"fleetglint demo: {exc}", file=sys.stderr)
        return 3
    print(f"wrote {len(records)} record(s) to {Path(root) / SOURCE_ID} "
          f"(source {SOURCE_ID})")
    for record in records:
        print(f"  {record['type']:8} {record['id']}: {record.get('state')}")
    print("remove with fleetglint demo --clear")
    return 0


def build(now):
    """Every record the demo writes, in write order."""
    return _chain(now) + _extras(now)


def _chain(now):
    """The lead -> worker -> detached job -> inbox -> resumed lead sample chain."""
    lead_started = now - timedelta(minutes=20)
    started = now - timedelta(minutes=6)
    done = now - timedelta(minutes=3)
    handoff = now - timedelta(minutes=4)
    resumed = now - timedelta(minutes=2)
    lead = {
        "project": PROJECTS[0],
        "agent": "claude-code",
        "model": "claude-opus-5-5",
        "provider": "anthropic",
        "effort": "high",
        "role_id": "demo-lead",
        "session_id": LEAD_SESSION,
        "title": "[demo] demo-lead session",
    }
    worker = {
        "project": PROJECTS[0],
        "agent": "claude-code",
        "model": "deepseek-flash",
        "provider": "deepseek",
        "role_id": "demo-lead",
        "parent_run": {"type": "run", "id": "demo-lead-1"},
        "session_id": WORKER_SESSION,
        "title": "[demo] store-blink: fix the blinking store badge",
    }
    job = {
        "project": PROJECTS[0],
        "kind": "wait",
        "command_summary": "lead-wait run store-blink -- ds-exec demo-worker-1",
        "run": {"type": "run", "id": "demo-lead-1"},
        "title": "[demo] wait for the worker",
    }
    return [
        _record("run", "demo-lead-1", started, lead, state="running",
                started_at=_stamp(lead_started), stale_after_s=1800),
        _record("run", "demo-worker-1", started, worker, state="running",
                started_at=_stamp(started)),
        _record("job", "demo-job-1", started, job, state="running",
                started_at=_stamp(started)),
        _record("run", "demo-lead-1", handoff, lead, state="done",
                started_at=_stamp(lead_started), ended_at=_stamp(handoff),
                summary="Handed off store-blink; session cleared at HANDOFF-OK."),
        _record("run", "demo-worker-1", done, worker, state="done",
                started_at=_stamp(started), ended_at=_stamp(done), exit_code=0,
                links=[{"label": "PR", "url": "https://example.com/fleetglint-demo/pull/1"}]),
        _record("job", "demo-job-1", done, job, state="done",
                started_at=_stamp(started), ended_at=_stamp(done), exit_code=0),
        _record("inbox_item", "demo-inbox-1", done,
                {"project": PROJECTS[0], "role_id": "demo-lead", "kind": "job_finished",
                 "subject": {"type": "job", "id": "demo-job-1"}, "outcome": "done",
                 "action_required": True, "created_at": _stamp(done),
                 "detail": "demo-worker-1 finished (exit 0); review the PR.",
                 "title": "[demo] worker finished"},
                state="open"),
        _record("run", "demo-lead-2", resumed, lead, state="waiting",
                started_at=_stamp(resumed), resume_of={"type": "run", "id": "demo-lead-1"},
                title="[demo] demo-lead session (after /clear)",
                waits_on=[{"type": "external", "kind": "github_pr",
                           "key": "example/fleetglint-demo#1",
                           "url": "https://example.com/fleetglint-demo/pull/1"}]),
    ]


def _extras(now):
    """Stale, lost, unknown, failed, recent/idle sessions and the other projects."""
    stale_at = now - timedelta(hours=2)
    lost_at = now - timedelta(minutes=10)
    failed_at = now - timedelta(minutes=110)
    recent_session = now - timedelta(minutes=5)
    idle_session = now - timedelta(hours=6)
    return [
        _record("run", "demo-stale-1", stale_at,
                {"project": PROJECTS[1], "state": "running", "agent": "codex-cli",
                 "model": "gpt-6.1-terra", "provider": "openai", "effort": "medium",
                 "role_id": "gteki-lead", "started_at": _stamp(stale_at),
                 "observed_at": _stamp(stale_at), "stale_after_s": 900,
                 "title": "[demo] gteki store refactor"}),
        _record("run", "demo-lost-1", lost_at,
                {"project": PROJECTS[2], "state": "running", "agent": "claude-code",
                 "model": "claude-opus-5-5", "provider": "anthropic",
                 "role_id": "fleetglint-lead", "started_at": _stamp(lost_at),
                 "observed_at": _stamp(lost_at), "stale_after_s": 900,
                 "process": {"host": short_hostname(), "pid": _dead_pid()},
                 "title": "[demo] a worker whose process is gone"}),
        _record("run", "demo-unknown-1", now - timedelta(minutes=30),
                {"project": PROJECTS[1], "state": "unknown", "agent": "codex-cli",
                 "model": "gpt-6.1-terra", "provider": "openai",
                 "started_at": _stamp(now - timedelta(minutes=45)),
                 "title": "[demo] an importer that lost track"}),
        _record("run", "demo-failed-1", failed_at,
                {"project": PROJECTS[2], "state": "failed", "agent": "claude-code",
                 "model": "claude-haiku-5-5", "provider": "anthropic",
                 "started_at": _stamp(failed_at), "ended_at": _stamp(failed_at + timedelta(minutes=10)),
                 "exit_code": 2, "title": "[demo] flaky checkout smoke test"}),
        _record("session", "demo-session-1", recent_session,
                {"project": PROJECTS[2], "state": "open", "agent": "claude-code",
                 "model": "claude-opus-5-5", "models": ["claude-opus-5-5"],
                 "started_at": _stamp(now - timedelta(minutes=90)),
                 "last_activity_at": _stamp(recent_session), "entries": 120,
                 "title": "[demo] fleetglint-lead history"}),
        _record("session", "demo-session-2", idle_session,
                {"project": PROJECTS[1], "state": "unknown", "agent": "codex-cli",
                 "model": "gpt-6.1-terra", "models": ["gpt-6.1-terra"],
                 "provider": "openai", "effort": "medium",
                 "started_at": _stamp(now - timedelta(hours=7)),
                 "last_activity_at": _stamp(idle_session), "entries": 300,
                 "title": "[demo] gteki codex history"}),
    ]


def _record(record_type, record_id, updated, fields, **extra):
    record = {"v": 1, "type": record_type, "id": record_id,
              "source_id": SOURCE_ID, "updated_at": _stamp(updated)}
    record.update(fields)
    record.update(extra)
    return record


def _stamp(moment):
    return moment.isoformat(timespec="seconds")


def _dead_pid():
    """A pid on this host that `os.kill(pid, 0)` says does not exist."""
    for pid in range(999_999, 999_899, -1):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return pid
        except OSError:
            continue
    return 999_999


def _clear(root, out=None):
    """Delete `<root>/demo@fleetglint`; return 0, or 1 when it is a symlink."""
    out = out or sys.stdout
    path = Path(root) / SOURCE_ID
    if path.is_symlink():
        print(f"fleetglint demo: refusing to remove {path}: it is a symlink", file=sys.stderr)
        return 1
    if not path.exists():
        print(f"no demo source at {path}")
        return 0
    shutil.rmtree(path)
    print(f"removed {path}")
    print("the demo rows disappear from the board on the next ingest pass "
          "(fleetglint serve polls, or run fleetglint ingest --once)")
    return 0
