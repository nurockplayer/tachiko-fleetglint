"""tachiko-harness adapter (docs/architecture.md §6.1).

Read-only over the harness state directory: worker-ledger runs and running
entries, job-run jobs, lead-wait markers and lead-inbox events.
"""
import hashlib
import json
import os
import re
import shlex
import signal
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fleetglint.adapters.base import ScanResult, short_hostname
from fleetglint.projects import project_from_path

JST = timezone(timedelta(hours=9))
ROOTS = ("cx-exec", "ds-exec", "agy-exec", "job-run", "lead-wait")
TERMINAL_STATES = ("done", "failed", "cancelled")
# lead-wait's finish() states that ask the role to act, not only take note.
ACTION_OUTCOMES = frozenset({"failed", "blocked", "needs_decision", "changes", "checks-timeout"})

ZONES = {"JST": "+09:00", "UTC": "+00:00", "Z": "+00:00"}
_HARNESS_TIME = re.compile(
    r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})(?::(\d{2}))? ([A-Za-z]{2,5}|[+-]\d{2}:?\d{2})$")
_RFC3339 = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")
_EPOCH = re.compile(r"^\d+$")
_ID = re.compile(r"^[^\s\x00-\x1f\x7f]{1,200}$")
_ROLE = re.compile(r"^[a-z0-9-]+$")
_RUNNING_NAME = re.compile(r"^(?P<tool>[a-z]+)\.(?P<pid>\d+)(?:\.(?P<key>[A-Za-z0-9_-]+))?$")
_BUNDLE = re.compile(r"review/([A-Za-z0-9._-]+)/([A-Za-z0-9._-]+)/pr(\d+)-")
# The wrappers write these two lines to the run's log while a job runs; no other
# line is evidence of a wait.
_WAIT_START = re.compile(r"^\S+: waiting on job (\S+) \(cap ")
_WAIT_DONE = re.compile(r"^\S+: job (\S+) finished")
_WORKER_WRAPPERS = frozenset({"ds-exec", "cx-exec", "agy-exec"})
_SECRET = re.compile(r"(?i)token|secret|password|passwd|api[_-]?key|bearer|"
                     r"sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9]{8,}|eyJ[A-Za-z0-9_.-]{16,}")
_TOKEN = re.compile(r"^[A-Za-z0-9+/_=-]{24,}$")
# Options whose next argument is a credential (`curl -u alice:hunter2`).
_CREDENTIAL_OPTIONS = frozenset({"-u", "--user", "-p", "--password", "--pass", "--token",
                                 "--api-key", "--apikey", "--auth", "--authorization"})
_BARE_PAIR = re.compile(r"^[^\s/:]+:[^\s/]+$")
# `scheme://user[:pass]@host…` keeps the scheme and host; anything else shaped `user:pass@`
# is dropped whole (it names a credential and nothing worth showing).
_URL_USERINFO = re.compile(r"^(?P<scheme>[A-Za-z][A-Za-z0-9+.-]*://)(?P<authority>[^/?#]*)@")
_USERINFO_REF = re.compile(r"[^/\s]+:[^/\s]+@")


def _text(path):
    return Path(path).read_text(encoding="utf-8", errors="replace")


def _clip(value, limit):
    return value[:limit] if len(value) > limit else value


def _clean(value):
    """A worker-ledger column that may hold "-" for absent."""
    return value if value and value != "-" else None


def _iso(moment):
    return moment.isoformat(timespec="seconds")


def _parse_harness_time(text):
    """Parse `2026-11-05 06:10 JST`; a time without a known zone gives None."""
    match = _HARNESS_TIME.match(text.strip())
    if match is None:
        return None
    date, clock, seconds, zone = match.groups()
    offset = ZONES.get(zone.upper())
    if offset is None:
        if re.fullmatch(r"[+-]\d{2}:?\d{2}", zone):
            offset = zone if ":" in zone else f"{zone[:3]}:{zone[3:]}"
        else:
            return None
    try:
        return datetime.fromisoformat(f"{date}T{clock}:{seconds or '00'}{offset}")
    except ValueError:
        return None


def _parse_rfc3339(text):
    if not isinstance(text, str) or _RFC3339.match(text) is None:
        return None
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else None


def _parse_lstart(text):
    """`ps -o lstart=` output as worker-ledger and job-run store it, in UTC."""
    try:
        moment = datetime.strptime(" ".join(text.split()), "%a %b %d %H:%M:%S %Y")
    except ValueError:
        return None
    return moment.replace(tzinfo=timezone.utc).astimezone(JST)


def _from_epoch(epoch):
    try:
        return datetime.fromtimestamp(epoch, JST)
    except (OverflowError, OSError, ValueError):
        return None


def _mtime(path):
    try:
        return datetime.fromtimestamp(Path(path).stat().st_mtime, JST)
    except OSError:
        return None


def _log_tail(path, limit=8192):
    """The last `limit` bytes of a regular file; a directory, a symlink or any read
    error gives None. The first line of a cut tail is dropped: it is not a whole line."""
    try:
        info = os.lstat(path)
    except (OSError, TypeError):
        return None
    if not stat.S_ISREG(info.st_mode):
        return None
    try:
        with open(path, "rb") as handle:
            if info.st_size > limit:
                handle.seek(info.st_size - limit)
                data = handle.read(limit)
                data = data.split(b"\n", 1)[1] if b"\n" in data else b""
            else:
                data = handle.read(limit)
    except OSError:
        return None
    return data.decode("utf-8", "replace")


def _wait_from_log(path):
    """The job a wrapper says it is waiting on, from the newest matching log line.

    Only the wrapper's own two lines count; a newer `finished` line means running."""
    text = _log_tail(path)
    if text is None:
        return None
    for line in reversed(text.splitlines()):
        match = _WAIT_START.match(line)
        if match is not None:
            job_id = match.group(1)
            return job_id if _ID.match(job_id) else None
        if _WAIT_DONE.match(line) is not None:
            return None
    return None


def _run_identity(tool, log):
    """The running entry and its finished row both state the run's log path, which is unique
    per run (`<worker>-<timestamp>.log`), so hashing it keeps one identity across a restart."""
    if log and log.startswith("/") and len(log) <= 4096:
        return f"{tool}.{hashlib.sha1(log.encode('utf-8', 'replace')).hexdigest()[:12]}"
    return None


def _agent_for(tool):
    """(agent, provider) for a worker-ledger tool prefix."""
    if tool == "cx":
        return "codex-cli", None
    if tool == "ds":
        return "claude-code", "deepseek"
    if tool == "agy":
        return "antigravity", None
    if tool in ("haiku", "sub"):
        return "claude-code", None
    return tool, None


def _signal_name(value):
    if isinstance(value, str):
        return value[:32] or None
    if isinstance(value, int) and not isinstance(value, bool):
        try:
            return signal.Signals(value).name
        except ValueError:
            return f"SIG{value}"
    return None


def _link(label, path):
    if path and path.startswith("/") and len(path) <= 4096:
        return {"label": label, "path": path}
    return None


def _looks_secret(argument):
    return (argument in _CREDENTIAL_OPTIONS or "=" in argument
            or _SECRET.search(argument) is not None or _TOKEN.match(argument) is not None
            or _BARE_PAIR.match(argument) is not None)


def _scrub_url(argument):
    """A URL with userinfo keeps `scheme://host/path`; the query and fragment go, since a
    query often carries a token."""
    match = _URL_USERINFO.match(argument)
    if match is None:
        return None
    rest = argument[match.end():]
    for separator in ("?", "#"):
        rest = rest.split(separator, 1)[0]
    return match.group("scheme") + rest


def _command_summary(argv):
    """First word (basename) plus at most two arguments, credential-looking ones dropped."""
    while argv and re.match(r"[A-Za-z_][A-Za-z0-9_]*=", argv[0]):
        argv = argv[1:]  # leading VAR=value assignments, which often carry tokens
    if not argv:
        return None
    head = os.path.basename(argv[0]) or argv[0]
    parts = [head]
    drop_next = False
    user_next = False
    for argument in argv[1:3]:
        if user_next:
            user_next = False
            parts.append("[redacted]")  # the username can be a token too
            continue
        if argument in ("-u", "--user"):
            parts.append(argument)
            user_next = True
            continue
        header = re.match(r"(?i)^(authorization|proxy-authorization)\s*:", argument)
        if header:
            parts.append(header.group(0) + " [redacted]")
            continue
        if drop_next:
            drop_next = False
            continue
        scrubbed = _scrub_url(argument)
        if scrubbed is None and _USERINFO_REF.search(argument):
            continue
        if scrubbed is not None:
            argument = scrubbed
        if _looks_secret(argument):
            drop_next = argument in _CREDENTIAL_OPTIONS
            continue
        parts.append(argument[:40])
    return _clip(" ".join(parts), 200) or None


def _strip_env(argv):
    """`env A=B cmd …` names the command that actually runs, not `env`."""
    argv = list(argv)
    if argv and os.path.basename(argv[0]) == "env":
        argv = argv[1:]
        while argv and "=" in argv[0] and not argv[0].startswith("-"):
            argv = argv[1:]
    return argv


def _worker_name(argv):
    """The worker named by a wrapper's first positional argument, skipping its options
    (`--resume <id>`, `-m <x>`, `--effort <x>`, `--search`, any other flag)."""
    options_with_value = {"--resume", "-m", "--effort"}
    index = 1
    while index < len(argv):
        argument = argv[index]
        if argument.startswith("-"):
            index += 2 if argument in options_with_value else 1
            continue
        return os.path.basename(argument) or argument
    return None


def _lead_wait(argv):
    """Parse `lead-wait --inner --role R --job J pr N …` or `… run L -- cmd …`.

    Returns role, op, the PR number or label, and the wrapped argv; None when the
    shape does not match, so the marker fallback applies."""
    if not argv or os.path.basename(argv[0]) != "lead-wait":
        return None
    role = None
    job_id = None
    inner = False
    index = 1
    while index < len(argv):
        argument = argv[index]
        if argument == "--inner":
            inner = True
            index += 1
        elif argument == "--role" and index + 1 < len(argv):
            role = argv[index + 1]
            index += 2
        elif argument == "--job" and index + 1 < len(argv):
            job_id = argv[index + 1]
            index += 2
        elif argument.startswith("-"):
            index += 1
        else:
            break
    if not inner or role is None or job_id is None or index >= len(argv):
        return None
    op, rest = argv[index], argv[index + 1:]
    if op == "pr":
        if not rest or not rest[0].isdigit():
            return None
        return {"role": role, "op": "pr", "value": rest[0], "wrapped": []}
    if op == "run":
        if "--" not in rest:
            return None
        split = rest.index("--")
        label = " ".join(rest[:split]).strip()
        wrapped = _strip_env(rest[split + 1:])
        if not label or not wrapped:
            return None
        return {"role": role, "op": "run", "value": label, "wrapped": wrapped}
    return None


def _lead_wait_summary(wait):
    if wait["op"] == "pr":
        return _clip(f"review PR #{wait['value']}", 200)
    return _command_summary(wait["wrapped"])


def _job_project(directory):
    try:
        return project_from_path(_text(Path(directory) / "cwd").strip())
    except OSError:
        return None


class _Stats:
    """Counts of rows a scan skipped, for ScanResult.detail."""

    def __init__(self):
        self.malformed = 0
        self.unreadable = 0
        self.ci_errors = 0
        self.orb_no_log = False

    def detail(self):
        parts = []
        if self.malformed:
            parts.append(f"{self.malformed} malformed row(s) skipped")
        if self.unreadable:
            parts.append(f"{self.unreadable} unreadable file(s) skipped")
        if self.ci_errors:
            parts.append(f"ci-watch errors={self.ci_errors}")
        if self.orb_no_log:
            parts.append("orb-test: no finish log")
        return "; ".join(parts) or None


class HarnessAdapter:
    """Adapter over tachiko-harness state (architecture §6.1)."""

    def __init__(self, cfg_harness_state_dir: Path, hostname: str | None = None):
        self.state_dir = Path(cfg_harness_state_dir)
        self.hostname = hostname or short_hostname()
        self.source_id = f"tachiko-harness@{self.hostname}"
        self.allowed_roots = [self.state_dir / name for name in ROOTS
                              if (self.state_dir / name).is_dir()]

    def available(self):
        return (self.state_dir / "worker-ledger" / "runs.tsv").exists()

    def scan(self, now: datetime) -> ScanResult:
        ledger = self.state_dir / "worker-ledger" / "runs.tsv"
        if not ledger.exists():
            return ScanResult("unavailable", f"{ledger} not found")
        stats = _Stats()
        try:
            ledger_text = _text(ledger)
        except OSError as exc:
            return ScanResult("unavailable", f"cannot read {ledger}: {exc}")
        decisions, aliases = self._scan_decisions(stats)
        records = self._scan_runs(ledger_text, now, stats, aliases)
        jobs, jobs_by_id, workers = self._scan_jobs(now, stats)
        self._link_waits(jobs_by_id, stats)
        self._link_runs_to_jobs(records, jobs_by_id)
        self._link_run_roles(records, jobs_by_id, workers)
        records.extend(jobs)
        records.extend(self._scan_ci(stats))
        records.extend(self._scan_orb_test(now, stats))
        known = {r["project"] for r in records if r.get("project")}
        records.extend(self._scan_inbox(set(jobs_by_id), stats, aliases, known))
        records.extend(self._scan_owner_notify(stats, aliases, known))
        records.extend(decisions)
        return ScanResult("ok", stats.detail(), records)

    def _base(self, record_type, record_id, updated_at):
        return {"v": 1, "type": record_type, "id": record_id,
                "source_id": self.source_id, "updated_at": updated_at}

    def _scan_ci(self, stats):
        path = self.state_dir / "ci-watch" / "runs.tsv"
        if not path.exists():
            return []
        try:
            lines = _text(path).splitlines()
        except OSError:
            stats.unreadable += 1
            return []
        records = []
        polls = {}
        for line in lines[1:]:
            fields = line.split("\t")
            if len(fields) != 12:
                stats.malformed += 1
                continue
            polled, repo, run_id, workflow, branch, event, status, conclusion, created, updated, url, _ = fields
            poll_id = f"gha.{repo.replace('/', '.')}.poll"
            poll_time = _parse_rfc3339(polled)
            if repo.count("/") == 1 and all(repo.split("/")) and _ID.match(poll_id) and poll_time:
                previous = polls.get(repo)
                if previous is None or poll_time >= previous[0]:
                    polls[repo] = (poll_time, status == "error")
            if status == "error":
                stats.ci_errors += 1
                continue
            if run_id == "-":
                continue
            times = [_parse_rfc3339(t) for t in (polled, created, updated)]
            record_id = f"gha.{repo.replace('/', '.')}.{run_id}"
            if (not run_id.isdigit() or repo.count("/") != 1 or not all(repo.split("/"))
                    or not _ID.match(record_id) or not all(times)
                    or not url.startswith(("http://", "https://")) or len(url) > 2000):
                stats.malformed += 1
                continue
            state = "unknown"
            if status in ("queued", "waiting", "pending", "requested"):
                state = "queued"
            elif status == "in_progress":
                state = "running"
            elif status == "completed":
                if conclusion in ("success", "neutral", "skipped"):
                    state = "done"
                elif conclusion in ("failure", "timed_out", "startup_failure"):
                    state = "failed"
                elif conclusion == "cancelled":
                    state = "cancelled"
            record = self._base("job", record_id, _iso(times[2]))
            record.update(kind="github-actions", project=_clip(repo.split("/")[1], 200),
                          command_summary=_clip(f"{workflow} · {branch} · {event}", 200),
                          state=state, started_at=_iso(times[1]),
                          links=[{"label": "GitHub run", "url": url}])
            if state in TERMINAL_STATES:
                record["ended_at"] = _iso(times[2])
            else:
                record.update(observed_at=_iso(times[0]), stale_after_s=1800)
            if state == "failed":
                record["summary"] = conclusion
            records.append(record)
        for repo, (polled, failed) in polls.items():
            timestamp = _iso(polled)
            record = self._base("job", f"gha.{repo.replace('/', '.')}.poll", timestamp)
            record.update(kind="github-actions", project=_clip(repo.split("/")[1], 200),
                          command_summary="ci-watch poll", started_at=timestamp,
                          state="unknown" if failed else "done",
                          summary="ci-watch could not read this repo's runs" if failed else "ci-watch polled this repo")
            if failed:
                record["observed_at"] = timestamp
            else:
                record["ended_at"] = timestamp
            records.append(record)
        return records

    def _scan_orb_test(self, now, stats):
        root = self.state_dir / "orb-test"
        if not root.is_dir():
            return []
        finish = root / "runs.tsv"
        if not finish.exists():
            stats.orb_no_log = True
            return []
        try:
            lines = _text(finish).splitlines()
        except OSError:
            stats.unreadable += 1
            return []
        records = {}

        def build(pid, pstart, project, label):
            started = _parse_lstart(pstart)
            if not pid.isdigit() or int(pid) < 1 or started is None or not _clean(project) or not _clean(label):
                return None
            record_id = f"orb-test.{int(pid)}.{int(started.timestamp())}"
            record = self._base("job", record_id, _iso(now))
            # orb-test writes '<prefix> :: <command>'; only the prefix is meant to be read.
            label = label.split(" :: ", 1)[0]
            try:
                argv = shlex.split(label)
            except ValueError:
                argv = label.split()
            record.update(kind="orb-test", project=_clip(project, 200),
                          command_summary=_command_summary(argv) or "orb-test", started_at=_iso(started))
            return record

        # Later sources override earlier ones: active beats holder and queue.
        for name in ("queue", "waiting", "holder", "active"):
            directory = root / name
            try:
                paths = ([root / "heavy.holder"] if name == "holder" and (root / "heavy.holder").is_file()
                         else sorted(directory.iterdir()) if directory.is_dir() else [])
            except OSError:
                stats.unreadable += 1
                continue
            for path in paths:
                if path.name.startswith(".") or path.name.endswith(".why") or not path.is_file():
                    continue
                try:
                    fields = _text(path).rstrip("\n").split("\t")
                    if name in ("queue", "holder"):
                        if len(fields) != 8 or not fields[0].isdigit() or not fields[2].isdigit():
                            raise ValueError
                        ticket, pid, _, project, _, _, label, pstart = fields
                        if name == "queue" and path.name != f"{int(ticket):06d}.{pid}":
                            raise ValueError
                    else:
                        if len(fields) != (5 if name == "active" else 6):
                            raise ValueError
                        project, pid, pstart, memory, label = fields[:5]
                        if path.name != pid or not memory.isdigit() or (name == "waiting" and not fields[5].isdigit()):
                            raise ValueError
                    record = build(pid, pstart, project, label)
                    if record is None:
                        raise ValueError
                    record.update(state="running" if name in ("active", "holder") else "queued",
                                  observed_at=_iso(now), stale_after_s=600,
                                  process={"host": self.hostname, "pid": int(pid), "start_time": record["started_at"]})
                    if name == "holder":
                        record["summary"] = "heavy lock held, starting"
                    elif name == "waiting":
                        record["summary"] = "waiting for memory"
                    elif name == "queue":
                        why = path.with_name(path.name + ".why")
                        record["summary"] = _clip(_text(why).strip(), 2000) if why.is_file() else f"queued #{int(ticket)}"
                    records[record["id"]] = record
                except OSError:
                    stats.unreadable += 1
                except ValueError:
                    stats.malformed += 1
        for line in lines:
            fields = line.split("\t")
            if len(fields) != 6:
                stats.malformed += 1
                continue
            ended_text, pid, pstart, project, label, exit_text = fields
            ended = _from_epoch(int(ended_text)) if ended_text.isdigit() else None
            record = build(pid, pstart, project, label)
            if ended is None or record is None or (exit_text != "-" and not re.fullmatch(r"-?\d+", exit_text)):
                stats.malformed += 1
                continue
            if ended < now - timedelta(hours=24) or ended > now:
                continue
            record.update(updated_at=_iso(ended), ended_at=_iso(ended))
            if exit_text == "-":
                record.update(state="cancelled", summary="ended; exit status not recorded")
            else:
                code = int(exit_text)
                record.update(state="done" if code == 0 else "failed", exit_code=code)
            records[record["id"]] = record
        return list(records.values())

    # -- worker-ledger ----------------------------------------------------

    def _scan_runs(self, ledger_text, now, stats, aliases):
        records = []
        seen = set()
        header = ledger_text.splitlines()[0].split("\t") if ledger_text.splitlines() else []
        title_index = header.index("title") if "title" in header else None
        for row in ledger_text.splitlines():
            if not row.strip() or row.startswith("started\t"):
                continue
            record = self._ledger_record(row, stats, aliases, title_index)
            if record is None or record["id"] in seen:
                continue
            seen.add(record["id"])
            records.append(record)
        running_dir = self.state_dir / "worker-ledger" / "running"
        if running_dir.is_dir():
            try:
                entries = sorted(running_dir.iterdir())
            except OSError:
                stats.unreadable += 1
                entries = []
            for path in entries:
                if path.name.startswith(".") or not path.is_file():
                    continue
                record = self._running_record(path, now, stats, aliases)
                if record is None or record["id"] in seen:
                    continue
                seen.add(record["id"])
                records.append(record)
        return records

    def _ledger_record(self, row, stats, aliases, title_index=None):
        fields = row.split("\t")
        if len(fields) < 10:
            stats.malformed += 1
            return None
        started_text, ended_text, tool, project, worker, model, _pane, exit_text, _advice, log = fields[:10]
        note = fields[10] if len(fields) > 10 and title_index != 10 else ""
        title = fields[title_index] if title_index is not None and title_index < len(fields) else ""
        started = _parse_harness_time(started_text)
        ended = _parse_harness_time(ended_text)
        agent, provider = _agent_for(tool)
        if not agent or started is None or ended is None:
            stats.malformed += 1
            return None
        exit_code = None
        if _EPOCH.match(exit_text):
            exit_code = int(exit_text)
            state = "done" if exit_code == 0 else "failed"
        else:
            # worker-ledger writes "lost" when it pruned a dead pid: it cannot tell the outcome.
            state = "unknown"
        digest = hashlib.sha1(row.encode("utf-8", "replace")).hexdigest()[:12]
        record_id = _run_identity(tool, log) or f"{tool}.ledger.{digest}"
        record = self._base("run", record_id, _iso(ended))
        record.update({"state": state, "agent": _clip(agent, 64), "started_at": _iso(started)})
        if state in TERMINAL_STATES:
            record["ended_at"] = _iso(ended)
        if exit_code is not None:
            record["exit_code"] = exit_code
        self._add_run_details(record, project, worker, model, provider, log, aliases, title)
        if note.strip():
            record["summary"] = _clip(note.strip(), 2000)
        return record

    def _running_record(self, path, now, stats, aliases):
        match = _RUNNING_NAME.match(path.name)
        if match is None:
            stats.malformed += 1
            return None
        tool, key = match.group("tool"), match.group("key")
        pid = int(match.group("pid"))
        try:
            fields = _text(path).rstrip("\n").split("\t")
        except OSError:
            stats.unreadable += 1
            return None
        if (len(fields) < 10 or fields[0] != tool or not _EPOCH.match(fields[1])
                or int(fields[1]) != pid or not _EPOCH.match(fields[3])):
            stats.malformed += 1
            return None
        started = _from_epoch(int(fields[3]))
        agent, provider = _agent_for(tool)
        if started is None or not agent:
            stats.malformed += 1
            return None
        record_id = (_run_identity(tool, fields[9])
                     or f"{tool}.{pid}" + (f".{key}" if key else "") + f".{int(fields[3])}")
        record = self._base("run", record_id, _iso(started))
        record.update({
            "state": "running",
            "agent": _clip(agent, 64),
            "started_at": _iso(started),
            "stale_after_s": 21600 if key else 3600,
            "observed_at": _iso(started if key else now),
        })
        # A keyed subagent marker uses its parent session's pid, not its own.
        if not key:
            process = {"host": self.hostname, "pid": pid}
            lstart = _parse_lstart(fields[2])
            if lstart is not None:
                process["start_time"] = _iso(lstart)
            record["process"] = process
        waiting_on = _wait_from_log(fields[9])
        if waiting_on is not None:
            record["state"] = "waiting"
            record["waits_on"] = [{"type": "job", "id": waiting_on}]
        self._add_run_details(record, fields[4], fields[5], fields[6], provider, fields[9], aliases,
                              fields[11] if len(fields) > 11 else "")
        return record

    def _add_run_details(self, record, project, worker, model, provider, log, aliases, title=""):
        if _clean(project):
            record["project"] = _clip(aliases.get(project, project), 200)
        if _clean(worker):
            record["title"] = _clip(worker, 200)
        if _clean(title):
            record["title"] = _clip(title, 200)
            if _clean(worker):
                record["worker"] = _clip(worker, 200)
        if provider:
            record["provider"] = _clip(provider, 64)
        if _clean(model):
            record["model"] = _clip(model, 128)
        link = _link("worker log", log)
        if link is not None:
            record["links"] = [link]

    # -- job-run ----------------------------------------------------------

    def _scan_jobs(self, now, stats):
        by_id = {}
        workers = {}
        root = self.state_dir / "job-run"
        if not root.is_dir():
            return [], by_id, workers
        try:
            entries = sorted(root.iterdir())
        except OSError:
            stats.unreadable += 1
            return [], by_id, workers
        for directory in entries:
            if not directory.is_dir() or directory.name.startswith("."):
                continue
            built = self._job_record(directory, now, stats)
            if built is None:
                continue
            record, worker = built
            by_id[record["id"]] = record
            if worker:
                workers[record["id"]] = worker
        return list(by_id.values()), by_id, workers

    def _job_record(self, directory, now, stats):
        """The job record and, for a wait-worker job, the worker it runs (not a field)."""
        job_id = directory.name
        if _ID.match(job_id) is None:
            stats.malformed += 1
            return None
        try:
            argv = [line for line in _text(directory / "cmd").splitlines() if line.strip()]
        except OSError:
            stats.malformed += 1
            return None
        wait = _lead_wait(argv)
        summary = _lead_wait_summary(wait) if wait is not None else _command_summary(argv)
        if summary is None:
            stats.malformed += 1
            return None
        result_path = directory / "result.json"
        if result_path.is_file():
            record = self._job_from_result(directory, result_path, summary, stats)
        else:
            record = self._running_job(directory, summary, now, stats)
        if record is None:
            return None
        project = _job_project(directory)
        if project is not None:
            record["project"] = project
        try:
            cwd = _text(directory / "cwd").strip()
            if os.path.isabs(cwd):
                record["cwd"] = _clip(cwd, 4096)
        except OSError:
            pass
        return record, self._apply_lead_wait(record, wait) if wait is not None else None

    def _apply_lead_wait(self, record, wait):
        """Kind, role, title and summary of a `lead-wait` job; returns its worker name."""
        if _ROLE.match(wait["role"]):
            record["role_id"] = wait["role"]
        if wait["op"] == "pr":
            record["kind"] = "wait"
            record["title"] = _clip(f"PR #{wait['value']} review", 200)
            return None
        record["title"] = _clip(wait["value"], 200)
        if os.path.basename(wait["wrapped"][0]) not in _WORKER_WRAPPERS:
            record["kind"] = "wait"
            return None
        record["kind"] = "wait-worker"
        return _worker_name(wait["wrapped"])

    def _job_pid(self, directory):
        """(pid, start time) from the job's pid file, either may be None."""
        try:
            fields = _text(directory / "pid").rstrip("\n").split("\t")
        except OSError:
            return None, None
        pid = int(fields[0]) if fields and fields[0].isdigit() else None
        started = _parse_lstart(fields[1]) if len(fields) > 1 else None
        return pid, started

    def _job_from_result(self, directory, result_path, summary, stats):
        try:
            data = json.loads(_text(result_path))
        except (OSError, ValueError):
            data = None
        if not isinstance(data, dict):
            stats.malformed += 1
            updated = _mtime(result_path) or _mtime(directory / "pid")
            if updated is None:
                return None
            _pid, started = self._job_pid(directory)
            record = self._base("job", directory.name, _iso(updated))
            record.update({"state": "unknown", "command_summary": summary,
                           "result_path": str(result_path)})
            if started is not None:
                record["started_at"] = _iso(started)
            return record

        status = data.get("status")
        state = "done" if status == "ok" else "failed" if status == "failed" else "unknown"
        started = _parse_rfc3339(data.get("started"))
        ended = _parse_rfc3339(data.get("ended"))
        if state in TERMINAL_STATES and (started is None or ended is None):
            stats.malformed += 1
            return None
        updated = ended or started or _mtime(result_path)
        if updated is None:
            stats.malformed += 1
            return None
        record = self._base("job", directory.name, _iso(updated))
        record.update({"state": state, "command_summary": summary, "result_path": str(result_path)})
        if started is not None:
            record["started_at"] = _iso(started)
        if ended is not None:
            record["ended_at"] = _iso(ended)
        exit_code = data.get("exit_code")
        if isinstance(exit_code, int) and not isinstance(exit_code, bool):
            record["exit_code"] = exit_code
        signal_name = _signal_name(data.get("signal"))
        if signal_name is not None:
            record["signal"] = signal_name
        log = data.get("log")
        if not (isinstance(log, str) and log.startswith("/") and len(log) <= 4096):
            log = str(directory / "log") if (directory / "log").is_file() else None
        if log is not None:
            record["log_path"] = log
        return record

    def _running_job(self, directory, summary, now, stats):
        pid, started = self._job_pid(directory)
        updated = started or _mtime(directory / "pid") or _mtime(directory / "cmd")
        if updated is None:
            stats.malformed += 1
            return None
        record = self._base("job", directory.name, _iso(updated))
        if pid is None:
            # A cmd alone is not evidence that anything is running.
            record.update({"state": "unknown", "command_summary": summary,
                           "summary": "no pid recorded"})
            if started is not None:
                record["started_at"] = _iso(started)
        else:
            record.update({"state": "running", "command_summary": summary,
                           "started_at": _iso(updated)})
            process = {"host": self.hostname, "pid": pid}
            if started is not None:
                process["start_time"] = _iso(started)
            record["process"] = process
            record["observed_at"] = _iso(now)
        if (directory / "log").is_file():
            record["log_path"] = str(directory / "log")
        return record

    def _link_waits(self, jobs_by_id, stats):
        markers = {}
        root = self.state_dir / "lead-wait"
        if not root.is_dir():
            return
        try:
            roles = sorted(root.iterdir())
        except OSError:
            stats.unreadable += 1
            return
        for role_dir in roles:
            if not role_dir.is_dir() or role_dir.name.startswith("."):
                continue
            if _ROLE.match(role_dir.name) is None:
                stats.malformed += 1
                continue
            try:
                entries = sorted(role_dir.iterdir())
            except OSError:
                stats.unreadable += 1
                continue
            for path in entries:
                if path.name.startswith(".") or not path.is_file():
                    continue
                try:
                    fields = _text(path).strip().split("\t")
                except OSError:
                    stats.unreadable += 1
                    continue
                if len(fields) < 3:
                    stats.malformed += 1
                markers.setdefault(path.name, set()).add(role_dir.name)
        for job_id, roles in markers.items():
            record = jobs_by_id.get(job_id)
            if record is None:
                continue
            if len(roles) != 1:
                stats.malformed += 1
                continue
            # The job's own cmd is stronger evidence than the marker; this is the fallback.
            if "kind" not in record:
                record["kind"] = "wait"
            if "role_id" not in record:
                record["role_id"] = roles.pop()

    def _link_runs_to_jobs(self, records, jobs_by_id):
        """A run waiting on a job points at it; the job names the run that owns it."""
        for record in records:
            if record.get("type") != "run":
                continue
            for ref in record.get("waits_on") or []:
                if ref.get("type") != "job":
                    continue
                job = jobs_by_id.get(ref.get("id"))
                if job is not None:
                    job["run"] = {"type": "run", "id": record["id"]}

    def _link_run_roles(self, records, jobs_by_id, workers):
        """A run's role comes from the wait-worker job that launched it, when the job's
        worker name and its time window both fit. Titles alone are never enough."""
        for record in records:
            title = record.get("worker") or record.get("title")
            started = _parse_rfc3339(record.get("started_at", ""))
            if (record.get("type") != "run" or "role_id" in record
                    or not title or started is None):
                continue
            roles = set()
            for job_id, worker in workers.items():
                if worker != title:
                    continue
                job = jobs_by_id[job_id]
                if job.get("kind") != "wait-worker":
                    continue
                job_started = _parse_rfc3339(job.get("started_at", ""))
                if job_started is None or job_started - timedelta(seconds=60) > started:
                    continue
                job_ended = _parse_rfc3339(job.get("ended_at", ""))
                if job_ended is not None and started > job_ended:
                    continue
                roles.add(job.get("role_id"))
            if len(roles) == 1 and None not in roles:
                record["role_id"] = roles.pop()

    # Harness roles conventionally use <project>-<function>; only this adapter infers projects.
    @staticmethod
    def _role_project(role):
        return role.rsplit("-", 1)[0] if "-" in role else None

    def _role_project_for(self, role, aliases, known):
        prefix = self._role_project(role)
        while prefix is not None:
            if prefix in aliases:
                return aliases[prefix]
            if prefix in known:
                return prefix
            prefix = self._role_project(prefix)
        prefix = self._role_project(role)
        return aliases.get(prefix, prefix)

    # -- lead-inbox -------------------------------------------------------

    def _scan_inbox(self, job_ids, stats, aliases, known):
        records = []
        root = self.state_dir / "lead-inbox"
        if not root.is_dir():
            return records
        try:
            paths = sorted(root.glob("*.tsv"))
        except OSError:
            stats.unreadable += 1
            return records
        for path in paths:
            role = path.stem
            if _ROLE.match(role) is None:
                stats.malformed += 1
                continue
            try:
                text = _text(path)
            except OSError:
                stats.unreadable += 1
                continue
            for number, line in enumerate(text.splitlines(), start=1):
                if not line.strip() or (number == 1 and line.startswith("id\t")):
                    continue
                record = self._inbox_record(role, line, job_ids, stats, aliases, known)
                if record is not None:
                    records.append(record)
        return records

    def _inbox_record(self, role, line, job_ids, stats, aliases, known):
        fields = line.split("\t", 6)
        if len(fields) < 6:
            stats.malformed += 1
            return None
        item_id, when, kind, ref, outcome, detail = fields[:6]
        acked_text = fields[6] if len(fields) > 6 else ""
        created = _parse_harness_time(when)
        if (created is None or _ID.match(item_id) is None
                or not kind.strip() or len(kind) > 64):
            stats.malformed += 1
            return None
        acked = None
        if acked_text.strip():
            acked = _parse_harness_time(acked_text)
            if acked is None:
                stats.malformed += 1
                return None
        record = self._base("inbox_item", item_id, _iso(acked or created))
        record.update({
            "role_id": role,
            "state": "acked" if acked is not None else "open",
            "kind": kind.strip(),
            "subject": self._subject(kind.strip(), ref, detail, job_ids),
            "created_at": _iso(created),
        })
        if "-" in role:
            record["project"] = self._role_project_for(role, aliases, known)
        if acked is not None:
            record["acked_at"] = _iso(acked)
        outcome = outcome.strip()
        if outcome:
            record["outcome"] = _clip(outcome, 80)
        if outcome in ACTION_OUTCOMES:
            record["action_required"] = True
        if detail.strip():
            record["detail"] = _clip(detail.strip(), 4000)
        return record

    def _subject(self, kind, ref, detail, job_ids):
        if kind == "pr":
            external = self._github_pr(ref, detail)
            if external is not None:
                return external
        elif kind == "run":
            job_id = self._job_for_label(ref, job_ids)
            if job_id is not None:
                return {"type": "job", "id": job_id}
        return {"type": "external", "kind": "harness_ref", "key": _clip(f"{kind}:{ref}", 200)}

    def _github_pr(self, ref, detail):
        match = re.fullmatch(r"#(\d+)", ref.strip())
        if match is None:
            return None
        found = {entry for entry in _BUNDLE.findall(detail) if entry[2] == match.group(1)}
        if len(found) != 1:
            return None
        owner, repo, number = found.pop()
        return {"type": "external", "kind": "github_pr",
                "key": f"{owner}/{repo}#{number}",
                "url": f"https://github.com/{owner}/{repo}/pull/{number}"}

    def _job_for_label(self, label, job_ids):
        slug = re.sub(r"-+", "-", re.sub(r"[^a-z0-9-]+", "-", label.lower())).strip("-")
        if not slug:
            return None
        prefix = f"lw-{slug}-"
        candidates = [job_id for job_id in job_ids if job_id.startswith(prefix)]
        return candidates[0] if len(candidates) == 1 else None

    # -- owner-notify -----------------------------------------------------

    def _scan_owner_notify(self, stats, aliases, known):
        """One open item per key of owner-notify's log; the log has no acknowledged state."""
        path = self.state_dir / "owner-notify" / "log.tsv"
        if not path.exists():
            return []
        try:
            text = _text(path)
        except OSError:
            stats.unreadable += 1
            return []
        chosen = {}
        for number, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            fields = line.split("\t", 4)
            if len(fields) < 5:
                stats.malformed += 1
                continue
            when, key, role, status, message = fields
            moment = _parse_harness_time(when)
            if moment is None or _ID.match(key) is None:
                stats.malformed += 1
                continue
            status = status.strip()
            # owner-notify logs an absent --key as "-": each such row is its own notification,
            # even when two rows read the same. The log is append-only, so the line number holds.
            if key == "-":
                key = f"line.{number}"
            # Reserve line. and key: for unkeyed rows and escaped explicit keys.
            elif key.startswith(("line.", "key:")):
                key = f"key:{key}"
                if _ID.match(f"owner-notify.{key}") is None:
                    stats.malformed += 1
                    continue
            # A key's newest sent/failed row wins; a skipped-only key keeps its newest skip.
            priority = 0 if status in ("sent", "failed") else 1 if status == "skipped" else None
            if priority is None:
                continue
            current = chosen.get(key)
            if (current is None or priority < current[0]
                    or (priority == current[0] and moment >= current[1])):
                chosen[key] = (priority, moment, role, status, message)
        records = []
        for key, (_, moment, role, status, message) in chosen.items():
            record = self._base("inbox_item", f"owner-notify.{key}", _iso(moment))
            record.update({
                "role_id": "owner",
                "state": "open",
                "kind": "owner-notify",
                "action_required": True,
                "subject": {"type": "external", "kind": "harness_ref",
                            "key": _clip(f"from:{role.strip()}", 200)},
                "created_at": _iso(moment),
                "outcome": _clip(status, 80),
                "detail": _clip(message.strip(), 4000),
            })
            if "-" in role.strip():
                record["project"] = self._role_project_for(role.strip(), aliases, known)
            records.append(record)
        return records

    def _scan_decisions(self, stats):
        path = self.state_dir / "lead-decision" / "log.tsv"
        if not path.exists():
            return [], {}
        try:
            text = _text(path)
        except OSError:
            stats.unreadable += 1
            return [], {}
        records = []
        aliases = {}
        ambiguous = set()
        for line in text.splitlines():
            fields = line.split("\t")
            if len(fields) < 7 or not _parse_harness_time(fields[0]) or not _clean(fields[1]):
                continue
            role, project, repo = fields[1:4]
            if not _clean(repo):
                continue
            name = os.path.basename(repo.rstrip("/"))
            for key in {_clean(project), self._role_project(role)} - {None, ""}:
                if key in aliases and aliases[key] != name:
                    ambiguous.add(key)
                aliases[key] = name
        for key in ambiguous:
            aliases.pop(key, None)
        for number, line in enumerate(text.splitlines(), 1):
            if not line.strip() or (number == 1 and line.startswith("time\t")):
                continue
            fields = line.split("\t")
            if len(fields) < 7:
                stats.malformed += 1
                continue
            when, role, project, repo, ref, url, decision_text = fields[:7]
            moment = _parse_harness_time(when)
            if moment is None or not _clean(role):
                stats.malformed += 1
                continue
            record = self._base("decision", f"decision.{number}", _iso(moment))
            record.update(role_id=_clip(role.strip(), 200), text=_clip(decision_text, 1000), decided_at=_iso(moment))
            key = _clean(project) or self._role_project(role)
            project = os.path.basename(repo.rstrip("/")) if _clean(repo) else aliases.get(key, key)
            if project:
                record["project"] = _clip(project, 200)
            links = []
            if url.startswith(("http://", "https://")):
                links.append({"label": "decision", "url": url[:2000]})
            if ref.isdigit() and _clean(repo):
                links.append({"label": "issue", "url": f"https://github.com/{repo}/issues/{ref}"})
            if links:
                record["links"] = links
            records.append(record)
        return records, aliases
