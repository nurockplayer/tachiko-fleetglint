"""Codex CLI rollout importer (docs/architecture.md §6.3). Metadata only."""
import gzip
import json
import os
import stat
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .base import ScanResult, short_hostname

_CHUNK = 1 << 20
_MAX_SESSIONS = 5000
_MAX_MODELS = 16
_TURN_EVENTS = ("task_started", "task_complete", "turn_aborted")


def _timestamp(value):
    """Parse a timestamp for ordering, keeping the writer's string in records."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _count(value):
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0


def _project(cwd):
    name = Path(cwd).name if cwd else ""
    return name or None


def _consume_stream(stream, on_line):
    """Feed complete lines to `on_line`; return the number of bytes consumed."""
    pending = b""
    consumed = 0
    while True:
        chunk = stream.read(_CHUNK)
        if not chunk:
            return consumed
        parts = (pending + chunk).split(b"\n")
        pending = parts.pop()
        for raw in parts:
            on_line(raw)
            consumed += len(raw) + 1


@dataclass
class _Agg:
    """Everything a record needs, accumulated one line at a time."""

    entries: int = 0
    started: str | None = None
    last: str | None = None
    last_dt: datetime | None = None
    session_id: str | None = None
    cwd: str | None = None
    provider: str | None = None
    model: str | None = None
    effort: str | None = None
    models: list[str] = field(default_factory=list)
    turn_last: str | None = None
    usage: dict | None = None

    def add(self, obj):
        self.entries += 1
        ts = _timestamp(obj.get("timestamp"))
        if ts is not None and (self.last_dt is None or ts > self.last_dt):
            self.last_dt, self.last = ts, obj["timestamp"]
        kind = obj.get("type")
        payload = obj.get("payload")
        if not isinstance(payload, dict):
            return
        if kind == "session_meta":
            self._add_meta(obj, payload)
        elif kind == "turn_context":
            self._add_turn_context(payload)
        elif kind == "event_msg":
            self._add_event(payload)

    def _add_meta(self, obj, payload):
        if self.session_id is not None:
            return
        session_id = payload.get("id")
        if not isinstance(session_id, str):
            return
        self.session_id = session_id
        cwd = payload.get("cwd")
        if isinstance(cwd, str):
            self.cwd = cwd
        provider = payload.get("model_provider")
        if isinstance(provider, str):
            self.provider = provider
        ts = obj.get("timestamp")
        if isinstance(ts, str):
            self.started = ts

    def _add_turn_context(self, payload):
        model = payload.get("model")
        if isinstance(model, str):
            self.model = model
            if model not in self.models and len(self.models) < _MAX_MODELS:
                self.models.append(model)
        effort = payload.get("effort")
        if isinstance(effort, str):
            self.effort = effort

    def _add_event(self, payload):
        kind = payload.get("type")
        if kind in _TURN_EVENTS:
            self.turn_last = kind
        if kind != "token_count":
            return
        info = payload.get("info")
        total = info.get("total_token_usage") if isinstance(info, dict) else None
        if isinstance(total, dict):
            self.usage = {
                "basis": "measured",
                "input_tokens": _count(total.get("input_tokens")),
                "cached_input_tokens": _count(total.get("cached_input_tokens")),
                "output_tokens": _count(total.get("output_tokens")),
            }


@dataclass
class _FileState:
    inode: int
    size: int = 0
    mtime_ns: int = 0
    offset: int = 0
    errors: int = 0
    agg: _Agg = field(default_factory=_Agg)


class CodexAdapter:
    def __init__(self, codex_home: Path, hostname=None):
        self.codex_home = Path(codex_home)
        self.hostname = hostname or short_hostname()
        self.source_id = f"codex-cli@{self.hostname}"
        self.allowed_roots = []
        self._files: dict[Path, _FileState] = {}

    def available(self) -> bool:
        return (self.codex_home / "sessions").is_dir() or (self.codex_home / "archived_sessions").is_dir()

    def scan(self, now: datetime) -> ScanResult:
        if not self.available():
            return ScanResult("unavailable", "sessions directory not found", [])
        unreadable = 0
        unsupported = 0
        without_meta = 0
        found = []
        states = {}
        for path in self._candidates():
            if not _is_rollout(path):
                unsupported += 1
                continue
            try:
                st = os.stat(path, follow_symlinks=False)
            except OSError:
                unreadable += 1
                continue
            compressed = path.name.endswith(".gz")
            prev = self._files.get(path)
            unchanged = (prev is not None and prev.inode == st.st_ino
                         and prev.size == st.st_size and prev.mtime_ns == st.st_mtime_ns)
            if unchanged:
                state = prev
            else:
                fresh = (prev is None or prev.inode != st.st_ino or compressed
                         or st.st_size < prev.offset)
                state = _FileState(inode=st.st_ino) if fresh else prev
                try:
                    state.errors += self._read_file(path, state, compressed)
                except (OSError, EOFError):
                    unreadable += 1
                    continue
                state.size = st.st_size
                state.mtime_ns = st.st_mtime_ns
            states[path] = state
            agg = state.agg
            if agg.session_id is None or agg.last is None:
                without_meta += 1
                continue
            found.append((agg.last_dt, st.st_mtime_ns, self._record(agg)))
        self._files = states
        unparseable = sum(state.errors for state in states.values())
        records, duplicates = _newest_per_session(found)
        records.sort(key=lambda item: item[0], reverse=True)
        cut = max(0, len(records) - _MAX_SESSIONS)
        result = [record for _, record in records[:_MAX_SESSIONS]]
        detail = _detail(unparseable, unreadable, unsupported, without_meta, duplicates, cut)
        return ScanResult("ok", detail, result)

    def _candidates(self):
        for root in (self.codex_home / "sessions", self.codex_home / "archived_sessions"):
            if not root.is_dir():
                continue
            for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
                dirnames[:] = [name for name in dirnames
                               if not os.path.islink(os.path.join(dirpath, name))]
                for name in filenames:
                    if not name.startswith("rollout-"):
                        continue
                    path = Path(dirpath) / name
                    try:
                        mode = os.stat(path, follow_symlinks=False).st_mode
                    except OSError:
                        continue
                    if stat.S_ISREG(mode):
                        yield path

    def _read_file(self, path, state, compressed):
        """Read new complete lines into `state`; return the unparseable count."""
        errors = 0

        def handle(raw):
            nonlocal errors
            try:
                obj = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                errors += 1
                return
            if isinstance(obj, dict):
                state.agg.add(obj)
            else:
                errors += 1

        if compressed:
            with gzip.open(path, "rb") as stream:
                _consume_stream(stream, handle)
        else:
            with open(path, "rb") as stream:
                stream.seek(state.offset)
                state.offset += _consume_stream(stream, handle)
        return errors

    def _record(self, agg):
        record = {
            "v": 1,
            "type": "session",
            "id": agg.session_id,
            "source_id": self.source_id,
            "updated_at": agg.last,
            "agent": "codex-cli",
            "state": "unknown",
            "last_activity_at": agg.last,
            "entries": agg.entries,
        }
        if agg.started is not None:
            record["started_at"] = agg.started
        project = _project(agg.cwd)
        if project:
            record["project"] = project
        if agg.provider:
            record["provider"] = agg.provider
        if agg.model:
            record["model"] = agg.model
        if agg.models:
            record["models"] = list(agg.models)
        if agg.effort:
            record["effort"] = agg.effort
        if agg.turn_last is not None:
            record["turn_open"] = agg.turn_last == "task_started"
        if agg.usage is not None:
            record["usage"] = dict(agg.usage)
        return record


def _is_rollout(path):
    return path.name.endswith(".jsonl") or path.name.endswith(".jsonl.gz")


def _newest_per_session(found):
    """Collapse the same session id from both directories, keeping the newest activity."""
    best = {}
    for last_dt, mtime_ns, record in found:
        key = record["id"]
        current = best.get(key)
        if current is None or (last_dt, mtime_ns) > (current[0], current[1]):
            best[key] = (last_dt, mtime_ns, record)
    return [(mtime_ns, record) for _, mtime_ns, record in best.values()], len(found) - len(best)


def _detail(unparseable, unreadable, unsupported, without_meta, duplicates, cut):
    parts = []
    if unparseable:
        parts.append(f"{unparseable} unparseable line(s)")
    if unreadable:
        parts.append(f"{unreadable} unreadable file(s)")
    if unsupported:
        parts.append(f"{unsupported} rollout file(s) skipped (unsupported compression)")
    if without_meta:
        parts.append(f"{without_meta} rollout(s) without session_meta")
    if duplicates:
        parts.append(f"{duplicates} duplicate rollout(s) collapsed")
    if cut:
        parts.append(f"{cut} session(s) beyond the {_MAX_SESSIONS} cap")
    return "; ".join(parts) or None
