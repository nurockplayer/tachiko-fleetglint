"""Opt-in Claude Code hooks: install, uninstall and the record receiver (architecture §6.4)."""
import contextlib
import difflib
import fcntl
import json
import os
import shlex
import shutil
import signal
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fleetglint import config, emit, schema
from fleetglint.adapters.base import short_hostname

EVENTS = ("SessionStart", "SessionEnd", "SubagentStart", "SubagentStop")
COMMAND_SUFFIX = "hooks record claude"
MAX_PAYLOAD_BYTES = 65536
MAX_STATE_IDS = 500
BUDGET_S = 2.0


class HookError(Exception):
    pass


class _BudgetExceeded(Exception):
    pass


def run(args):
    if args.action == "record":
        return record_claude(config_path=getattr(args, "config", None))
    path = settings_path()
    config_file = config.expand(args.config) if getattr(args, "config", None) else None
    try:
        data, before, error = _load_settings(path)
    except OSError as exc:
        print(f"fleetglint hooks: cannot read {path}: {exc}", file=sys.stderr)
        return 1
    if error:
        print(f"fleetglint hooks: {error}", file=sys.stderr)
        return 1
    executable = executable_path()
    try:
        if args.action == "install":
            changed = _add_hooks(data, executable, config_file)
        else:
            changed = _remove_hooks(data, executable, config_file)
    except HookError as exc:
        print(f"fleetglint hooks: {exc}", file=sys.stderr)
        return 1
    if not changed:
        print(f"{path}: nothing to do")
        return 0
    after = _serialize(data)
    print(_diff(path, before, after), end="")
    if not getattr(args, "yes", False) and not _confirm():
        print("not applied", file=sys.stderr)
        return 1
    try:
        if _read_text(path) != before:
            print(f"fleetglint hooks: {path} changed while waiting; run again", file=sys.stderr)
            return 1
        mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
        backup = _backup(path, before, mode)
        # Claude Code has no lock to share, so check once more as late as possible.
        if _read_text(path) != before:
            print(f"fleetglint hooks: {path} changed while waiting; run again", file=sys.stderr)
            return 1
        _write_atomic(path, after, mode)
    except OSError as exc:
        print(f"fleetglint hooks: {exc}", file=sys.stderr)
        return 1
    print(f"{'installed into' if args.action == 'install' else 'removed from'} {path} "
          f"(backup: {backup})")
    return 0


# --- settings ---------------------------------------------------------------

def settings_path():
    value = os.environ.get("CLAUDE_CONFIG_DIR")
    return config.expand(value) / "settings.json" if value else config.expand("~/.claude/settings.json")


def executable_path():
    """Shell words for the fleetglint executable, or the module fallback from a source checkout."""
    found = shutil.which("fleetglint")
    if found:
        return shlex.quote(str(Path(found).resolve()))
    return f"{shlex.quote(sys.executable)} -m fleetglint"


def _command(executable, config_file=None):
    parts = [executable]
    if config_file:
        parts += ["--config", shlex.quote(str(config_file))]
    parts.append(COMMAND_SUFFIX)
    return " ".join(parts)


def _entry(executable, config_file=None):
    return {"type": "command", "command": _command(executable, config_file), "timeout": 5}


def _load_settings(path):
    """Return (data, original text, error); a missing file is `{}`."""
    if not path.exists():
        return {}, "", None
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, "", f"{path}: {exc}"
    if not isinstance(data, dict):
        return None, "", f"{path}: top level is not a JSON object"
    return data, text, None


def _check_structure(data):
    hooks = data.get("hooks")
    if hooks is None:
        return
    if not isinstance(hooks, dict):
        raise HookError("settings hooks is not a JSON object")
    for event in EVENTS:
        groups = hooks.get(event)
        if groups is not None and not isinstance(groups, list):
            raise HookError(f"settings hooks.{event} is not an array")


def _add_hooks(data, executable, config_file=None):
    _check_structure(data)
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        hooks = {}
        data["hooks"] = hooks
    command = _command(executable, config_file)
    changed = False
    for event in EVENTS:
        groups = hooks.setdefault(event, [])
        if _has_command(groups, command):
            continue
        groups.append({"matcher": "", "hooks": [_entry(executable, config_file)]})
        changed = True
    return changed


def _remove_hooks(data, executable, config_file=None):
    _check_structure(data)
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return False
    command = _command(executable, config_file)
    changed = False
    for event in EVENTS:
        groups = hooks.get(event)
        if not isinstance(groups, list):
            continue
        kept = []
        event_changed = False
        for group in groups:
            entries = group.get("hooks") if isinstance(group, dict) else None
            if not isinstance(entries, list):
                kept.append(group)
                continue
            remaining = [hook for hook in entries
                         if not (isinstance(hook, dict) and hook.get("command") == command)]
            if len(remaining) == len(entries):
                kept.append(group)
                continue
            event_changed = True
            if remaining:
                updated = dict(group)
                updated["hooks"] = remaining
                kept.append(updated)
            elif set(group) - {"matcher", "hooks"} or group.get("matcher") not in ("", None):
                updated = dict(group)
                updated["hooks"] = []
                kept.append(updated)
            # else: the container held only our entry and was created by install; drop it.
        if not event_changed:
            continue
        changed = True
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]
    if not hooks:
        data.pop("hooks", None)
    return changed


def _has_command(groups, command):
    for group in groups:
        if not isinstance(group, dict):
            continue
        entries = group.get("hooks")
        if not isinstance(entries, list):
            continue
        for hook in entries:
            if isinstance(hook, dict) and hook.get("command") == command:
                return True
    return False


def _serialize(data):
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _diff(path, before, after):
    return "".join(difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile=f"{path} (current)", tofile=f"{path} (new)"))


def _confirm():
    if not sys.stdin.isatty():
        print("stdin is not a terminal; re-run with --yes", file=sys.stderr)
        return False
    answer = input("Apply? [y/N] ").strip().lower()
    return answer in ("y", "yes")


def _read_text(path):
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _backup(path, text, mode):
    """Write a uniquely named backup that keeps the original permission bits."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    for counter in range(1000):
        suffix = f"{stamp}-{os.getpid()}" + (f"-{counter}" if counter else "")
        backup = path.with_name(f"{path.name}.fleetglint-backup-{suffix}")
        try:
            fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        except FileExistsError:
            continue
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        return backup
    raise OSError(f"could not create a backup next to {path}")


def _write_atomic(path, text, mode):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=f"{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


# --- record receiver --------------------------------------------------------

def record_claude(stream=None, now=None, config_path=None):
    """Write one session record from a hook payload; always return 0."""
    try:
        with _budget(BUDGET_S):
            _record(stream, now, config_path)
    except _BudgetExceeded:
        _log("timeout: exceeded the 2 s budget")
    except Exception as exc:  # never fail Claude, whatever happens
        _log(f"{type(exc).__name__}: {exc}")
    return 0


def _record(stream, now, config_path):
    raw = (stream if stream is not None else sys.stdin.buffer).read(MAX_PAYLOAD_BYTES + 1)
    if len(raw) > MAX_PAYLOAD_BYTES:
        _log("payload larger than 64 KiB; ignored")
        return
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _log(f"invalid JSON: {exc}")
        return
    if not isinstance(payload, dict):
        _log("payload is not a JSON object")
        return
    event = payload.get("hook_event_name")
    if event not in EVENTS:
        _log("unsupported event")
        return
    now = now or datetime.now().astimezone()
    cfg = config.load(config_path)
    root = cfg.roots[0]
    state_path = config.state_dir() / "hooks-state.json"
    with _state_lock(state_path):
        state = _load_state(state_path)
        record = _build(event, payload, now, state)
        if record is None:
            return
        errors = schema.validate(record)
        if errors:
            _log("record failed validation: " + "; ".join(errors))
            return
        emit.append_record(record, root)
        state[record["id"]] = record
        _save_state(state_path, state)


def _build(event, payload, now, state):
    stamp = now.isoformat(timespec="seconds")
    source = f"claude-hooks@{short_hostname()}"
    session_id = _text(payload.get("session_id"))
    if event in ("SessionStart", "SessionEnd"):
        if not session_id:
            return None
        record = _base(state.get(session_id), session_id, source, stamp)
        record.update(state="open" if event == "SessionStart" else "ended",
                      last_activity_at=stamp)
        record.pop("ended_at", None)
        if event == "SessionStart":
            record.setdefault("started_at", stamp)
            record["summary"] = "start: " + (_text(payload.get("source")) or "unknown")
            project = _project(payload.get("cwd"))
            if project:
                record["project"] = project
        else:
            record["ended_at"] = stamp
            record["summary"] = "end: " + (_text(payload.get("reason")) or "unknown")
        return record
    agent_id = _text(payload.get("agent_id"))
    if not agent_id or not session_id:
        # No stable subagent id in the payload: skip rather than invent one.
        return None
    record = _base(state.get(agent_id), agent_id, source, stamp)
    record.update(state="open" if event == "SubagentStart" else "ended",
                  last_activity_at=stamp,
                  parent_session={"type": "session", "id": session_id})
    record.pop("ended_at", None)
    if event == "SubagentStart":
        record["started_at"] = stamp
    else:
        record["ended_at"] = stamp
    return record


def _base(prior, record_id, source, stamp):
    """Start from the last full record so an end event keeps `started_at`."""
    record = dict(prior) if isinstance(prior, dict) else {}
    record.update({"v": 1, "type": "session", "id": record_id, "source_id": source,
                   "updated_at": stamp, "agent": "claude-code"})
    return record


def _text(value):
    return value if isinstance(value, str) and value else None


def _project(cwd):
    if not isinstance(cwd, str) or not cwd:
        return None
    return Path(cwd).name or None


def _load_state(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {key: value for key, value in data.items() if isinstance(value, dict)}


def _save_state(path, state):
    if len(state) > MAX_STATE_IDS:
        state = dict(sorted(state.items(), key=_state_age, reverse=True)[:MAX_STATE_IDS])
    _write_atomic(path, json.dumps(state, ensure_ascii=False), 0o600)


def _state_age(item):
    try:
        return datetime.fromisoformat(
            str(item[1].get("updated_at", "")).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0.0


@contextlib.contextmanager
def _state_lock(state_path):
    state_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(state_path.with_suffix(".lock"), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


@contextlib.contextmanager
def _budget(seconds):
    if not hasattr(signal, "SIGALRM"):
        yield
        return

    def handler(signum, frame):
        raise _BudgetExceeded()

    try:
        previous = signal.signal(signal.SIGALRM, handler)
    except ValueError:  # not the main thread; run without the alarm
        yield
        return
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def _log(message):
    """One line, no payload contents, best effort: hooks must never break Claude."""
    try:
        path = config.state_dir() / "hooks.log"
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        stamp = datetime.now().astimezone().isoformat(timespec="seconds")
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(f"{stamp} {message}\n")
    except OSError:
        pass
