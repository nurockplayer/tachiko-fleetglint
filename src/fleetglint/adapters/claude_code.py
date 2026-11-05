"""Claude Code transcript importer (docs/architecture.md §6.2). Metadata only."""
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


def _is_placeholder(model):
    return model.startswith("<") and model.endswith(">")


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
    started_dt: datetime | None = None
    last: str | None = None
    last_dt: datetime | None = None
    cwd: str | None = None
    title: str | None = None
    model: str | None = None
    models: list[str] = field(default_factory=list)
    message_ids: set[str] = field(default_factory=set)
    input_tokens: int = 0
    cached_tokens: int = 0
    cache_creation_tokens: int = 0
    output_tokens: int = 0
    usage_seen: bool = False
    session_ids: set[str] = field(default_factory=set)

    def add(self, obj):
        self.entries += 1
        ts = _timestamp(obj.get("timestamp"))
        if ts is not None:
            if self.started_dt is None or ts < self.started_dt:
                self.started_dt, self.started = ts, obj["timestamp"]
            if self.last_dt is None or ts > self.last_dt:
                self.last_dt, self.last = ts, obj["timestamp"]
        cwd = obj.get("cwd")
        if isinstance(cwd, str):
            self.cwd = cwd
        session_id = obj.get("sessionId")
        if isinstance(session_id, str):
            self.session_ids.add(session_id)
        if obj.get("type") == "ai-title":
            title = obj.get("aiTitle")
            if isinstance(title, str):
                self.title = title
        if obj.get("type") == "assistant":
            self._add_assistant(obj.get("message"))

    def _add_assistant(self, message):
        if not isinstance(message, dict):
            return
        model = message.get("model")
        if isinstance(model, str) and not _is_placeholder(model):
            self.model = model
            if model not in self.models and len(self.models) < _MAX_MODELS:
                self.models.append(model)
        usage = message.get("usage")
        if not isinstance(usage, dict):
            return
        message_id = message.get("id")
        if isinstance(message_id, str):
            if message_id in self.message_ids:
                return
            self.message_ids.add(message_id)
        self.usage_seen = True
        self.input_tokens += _count(usage.get("input_tokens"))
        self.cached_tokens += _count(usage.get("cache_read_input_tokens"))
        self.cache_creation_tokens += _count(usage.get("cache_creation_input_tokens"))
        self.output_tokens += _count(usage.get("output_tokens"))


@dataclass
class _FileState:
    inode: int
    size: int = 0
    mtime_ns: int = 0
    offset: int = 0
    agg: _Agg = field(default_factory=_Agg)


def _scandir(path):
    try:
        with os.scandir(path) as entries:
            return list(entries)
    except OSError:
        return []


def _is_dir(path):
    try:
        return stat.S_ISDIR(os.stat(path, follow_symlinks=False).st_mode)
    except OSError:
        return False


class ClaudeCodeAdapter:
    def __init__(self, projects_dir: Path, hostname=None):
        self.projects_dir = Path(projects_dir)
        self.hostname = hostname or short_hostname()
        self.source_id = f"claude-code@{self.hostname}"
        self.allowed_roots = []
        self._files: dict[Path, _FileState] = {}

    def available(self) -> bool:
        return self.projects_dir.is_dir()

    def scan(self, now: datetime) -> ScanResult:
        if not self.available():
            return ScanResult("unavailable", "projects directory not found", [])
        unreadable = 0
        unparseable = 0
        without_time = 0
        mismatches = 0
        found = []
        states = {}
        for path, parent in self._candidates():
            try:
                st = os.stat(path, follow_symlinks=False)
            except OSError:
                unreadable += 1
                continue
            prev = self._files.get(path)
            unchanged = (prev is not None and prev.inode == st.st_ino
                         and prev.size == st.st_size and prev.mtime_ns == st.st_mtime_ns)
            if unchanged:
                state = prev
            else:
                fresh = prev is None or prev.inode != st.st_ino or st.st_size < prev.offset
                state = _FileState(inode=st.st_ino) if fresh else prev
                try:
                    unparseable += self._read_file(path, state)
                except OSError:
                    unreadable += 1
                    continue
                state.size = st.st_size
                state.mtime_ns = st.st_mtime_ns
            states[path] = state
            agg = state.agg
            if agg.last is None:
                without_time += 1
                continue
            stem = path.stem
            if parent is None and agg.session_ids and any(s != stem for s in agg.session_ids):
                mismatches += 1
            found.append((st.st_mtime_ns, self._record(agg, stem, parent)))
        self._files = states
        found.sort(key=lambda item: item[0], reverse=True)
        cut = max(0, len(found) - _MAX_SESSIONS)
        records = [record for _, record in found[:_MAX_SESSIONS]]
        return ScanResult("ok", _detail(unparseable, unreadable, without_time, mismatches, cut), records)

    def _candidates(self):
        for project in _scandir(self.projects_dir):
            if not project.is_dir(follow_symlinks=False):
                continue
            for entry in _scandir(project.path):
                if entry.is_file(follow_symlinks=False) and entry.name.endswith(".jsonl"):
                    yield Path(entry.path), None
                elif entry.is_dir(follow_symlinks=False):
                    subagents = Path(entry.path) / "subagents"
                    if not _is_dir(subagents):
                        continue
                    for agent in _scandir(subagents):
                        if (agent.is_file(follow_symlinks=False)
                                and agent.name.startswith("agent-")
                                and agent.name.endswith(".jsonl")):
                            yield Path(agent.path), entry.name

    def _read_file(self, path, state):
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

        with open(path, "rb") as stream:
            stream.seek(state.offset)
            state.offset += _consume_stream(stream, handle)
        return errors

    def _record(self, agg, stem, parent):
        record = {
            "v": 1,
            "type": "session",
            "id": stem,
            "source_id": self.source_id,
            "updated_at": agg.last,
            "agent": "claude-code",
            "state": "unknown",
            "last_activity_at": agg.last,
            "entries": agg.entries,
        }
        if agg.started is not None:
            record["started_at"] = agg.started
        project = _project(agg.cwd)
        if project:
            record["project"] = project
        if agg.title:
            record["title"] = agg.title[:200]
        if agg.model:
            record["model"] = agg.model
        if agg.models:
            record["models"] = list(agg.models)
        if agg.usage_seen:
            record["usage"] = {
                "basis": "measured",
                "input_tokens": agg.input_tokens + agg.cached_tokens + agg.cache_creation_tokens,
                "cached_input_tokens": agg.cached_tokens,
                "output_tokens": agg.output_tokens,
            }
        if parent is not None:
            record["parent_session"] = {"type": "session", "id": parent}
        return record


def _detail(unparseable, unreadable, without_time, mismatches, cut):
    parts = []
    if unparseable:
        parts.append(f"{unparseable} unparseable line(s)")
    if unreadable:
        parts.append(f"{unreadable} unreadable file(s)")
    if without_time:
        parts.append(f"{without_time} transcript(s) without timestamps")
    if mismatches:
        parts.append(f"{mismatches} file(s) whose sessionId differs from the file name")
    if cut:
        parts.append(f"{cut} session(s) beyond the {_MAX_SESSIONS} cap")
    return "; ".join(parts) or None
