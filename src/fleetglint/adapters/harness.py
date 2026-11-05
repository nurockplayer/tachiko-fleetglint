"""tachiko-harness adapter (docs/architecture.md §6.1).

Read-only over the harness state directory: worker-ledger runs and running
entries, job-run jobs, lead-wait markers and lead-inbox events.
"""
import hashlib
import json
import os
import re
import signal
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fleetglint.adapters.base import ScanResult, short_hostname

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
_SECRET = re.compile(r"(?i)token|secret|password|passwd|api[_-]?key|bearer|"
                     r"sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9]{8,}|eyJ[A-Za-z0-9_.-]{16,}")
_TOKEN = re.compile(r"^[A-Za-z0-9+/_=-]{24,}$")


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


def _ledger_stamp(moment):
    """The `%F %H:%M %Z` form worker-ledger writes for a start epoch."""
    return moment.strftime("%Y-%m-%d %H:%M JST")


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
    return "=" in argument or _SECRET.search(argument) is not None or _TOKEN.match(argument) is not None


def _command_summary(argv):
    """First word (basename) plus at most two arguments, secret-looking ones dropped."""
    if not argv:
        return None
    head = os.path.basename(argv[0]) or argv[0]
    parts = [head]
    for argument in argv[1:3]:
        if not _looks_secret(argument):
            parts.append(argument[:40])
    return _clip(" ".join(parts), 200) or None


class _Stats:
    """Counts of rows a scan skipped, for ScanResult.detail."""

    def __init__(self):
        self.malformed = 0
        self.unreadable = 0

    def detail(self):
        parts = []
        if self.malformed:
            parts.append(f"{self.malformed} malformed row(s) skipped")
        if self.unreadable:
            parts.append(f"{self.unreadable} unreadable file(s) skipped")
        return "; ".join(parts) or None


class HarnessAdapter:
    """Adapter over tachiko-harness state (architecture §6.1)."""

    def __init__(self, cfg_harness_state_dir: Path, hostname: str | None = None):
        self.state_dir = Path(cfg_harness_state_dir)
        self.hostname = hostname or short_hostname()
        self.source_id = f"tachiko-harness@{self.hostname}"
        self.allowed_roots = [self.state_dir / name for name in ROOTS
                              if (self.state_dir / name).is_dir()]
        # id -> (last running record, tool, ledger start stamp), to tell a vanished run apart
        self._live: dict[str, tuple[dict, str, str]] = {}

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
        records = self._scan_runs(ledger_text, now, stats)
        jobs, jobs_by_id = self._scan_jobs(now, stats)
        self._link_waits(jobs_by_id, stats)
        records.extend(jobs)
        records.extend(self._scan_inbox(set(jobs_by_id), stats))
        return ScanResult("ok", stats.detail(), records)

    def _base(self, record_type, record_id, updated_at):
        return {"v": 1, "type": record_type, "id": record_id,
                "source_id": self.source_id, "updated_at": updated_at}

    # -- worker-ledger ----------------------------------------------------

    def _scan_runs(self, ledger_text, now, stats):
        records = []
        finished = set()
        for row in ledger_text.splitlines():
            if not row.strip() or row.startswith("started\t"):
                continue
            built = self._ledger_record(row, stats)
            if built is None:
                continue
            record, join_key = built
            finished.add(join_key)
            records.append(record)

        current = {}
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
                built = self._running_record(path, now, stats)
                if built is None:
                    continue
                record, join_key = built
                current[record["id"]] = (record, *join_key)
                records.append(record)

        for record_id, (previous, tool, started) in self._live.items():
            if record_id in current or (tool, started) in finished:
                continue
            record = {key: value for key, value in previous.items()
                      if key not in ("observed_at", "process", "stale_after_s")}
            record["state"] = "unknown"
            record["updated_at"] = _iso(now)
            record["summary"] = "the running entry disappeared and worker-ledger has no finished row for it"
            records.append(record)
        self._live = current
        return records

    def _ledger_record(self, row, stats):
        fields = row.split("\t")
        if len(fields) < 10:
            stats.malformed += 1
            return None
        started_text, ended_text, tool, project, worker, model, _pane, exit_text, _advice, log = fields[:10]
        note = fields[10] if len(fields) > 10 else ""
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
        record = self._base("run", f"{tool}.ledger.{digest}", _iso(ended))
        record.update({"state": state, "agent": _clip(agent, 64), "started_at": _iso(started)})
        if state in TERMINAL_STATES:
            record["ended_at"] = _iso(ended)
        if exit_code is not None:
            record["exit_code"] = exit_code
        self._add_run_details(record, project, worker, model, provider, log)
        if note.strip():
            record["summary"] = _clip(note.strip(), 2000)
        return record, (tool, started_text)

    def _running_record(self, path, now, stats):
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
        record_id = f"{tool}.{pid}" + (f".{key}" if key else "") + f".{int(fields[3])}"
        record = self._base("run", record_id, _iso(started))
        record.update({
            "state": "running",
            "agent": _clip(agent, 64),
            "started_at": _iso(started),
            "stale_after_s": 3600,
            "process": {"host": self.hostname, "pid": pid, "start_time": _iso(started)},
            "observed_at": _iso(now),
        })
        self._add_run_details(record, fields[4], fields[5], fields[6], provider, fields[9])
        return record, (tool, _ledger_stamp(started))

    def _add_run_details(self, record, project, worker, model, provider, log):
        if _clean(project):
            record["project"] = _clip(project, 200)
        if _clean(worker):
            record["title"] = _clip(worker, 200)
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
        root = self.state_dir / "job-run"
        if not root.is_dir():
            return [], by_id
        try:
            entries = sorted(root.iterdir())
        except OSError:
            stats.unreadable += 1
            return [], by_id
        for directory in entries:
            if not directory.is_dir() or directory.name.startswith("."):
                continue
            record = self._job_record(directory, now, stats)
            if record is not None:
                by_id[record["id"]] = record
        return list(by_id.values()), by_id

    def _job_record(self, directory, now, stats):
        job_id = directory.name
        if _ID.match(job_id) is None:
            stats.malformed += 1
            return None
        try:
            argv = [line for line in _text(directory / "cmd").splitlines() if line.strip()]
        except OSError:
            stats.malformed += 1
            return None
        summary = _command_summary(argv)
        if summary is None:
            stats.malformed += 1
            return None
        result_path = directory / "result.json"
        if result_path.is_file():
            return self._job_from_result(directory, result_path, summary, stats)
        return self._running_job(directory, summary, now, stats)

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
        record.update({"state": "running", "command_summary": summary, "started_at": _iso(updated)})
        if pid is not None:
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
            record["kind"] = "wait"
            record["role_id"] = roles.pop()

    # -- lead-inbox -------------------------------------------------------

    def _scan_inbox(self, job_ids, stats):
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
                record = self._inbox_record(role, line, job_ids, stats)
                if record is not None:
                    records.append(record)
        return records

    def _inbox_record(self, role, line, job_ids, stats):
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
