"""Display states and local process checks (spec §8). Pure: no SQLite."""
import ctypes
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fleetglint.adapters.base import short_hostname

TERMINAL_STATES = frozenset({"done", "failed", "cancelled", "acked", "ended"})
DEFAULT_STALE_AFTER_S = 900
START_TIME_TOLERANCE_S = 2.0


@dataclass(frozen=True)
class Display:
    state: str
    evidence: str
    age_s: int | None


def is_terminal(record: dict) -> bool:
    return record.get("state") in TERMINAL_STATES


def _parse_ts(value):
    if not isinstance(value, str):
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        ts = datetime.fromisoformat(value)
    except ValueError:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def _age(record, now, field):
    """Seconds since `field`, or None when it is absent or unparseable; never negative."""
    ts = _parse_ts(record.get(field))
    if ts is None:
        return None
    return max(0, int((now - ts).total_seconds()))


def _stale_after(record, default):
    value = record.get("stale_after_s")
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return default


def _recent(record, now, field, stale_after):
    """Is `now` before `field + stale_after`? A missing timestamp is never recent."""
    ts = _parse_ts(record.get(field))
    return ts is not None and now < ts + timedelta(seconds=stale_after)


def display(record: dict, now: datetime, *, default_stale_after_s=DEFAULT_STALE_AFTER_S,
            source_ok=True, process_checker=None) -> Display:
    """The display state, evidence kind and age for one record (spec §8.1, §8.3)."""
    state = record.get("state")
    record_type = record.get("type")
    activity_field = "last_activity_at" if record_type == "session" else "observed_at"
    age = _age(record, now, activity_field)
    if is_terminal(record):
        return Display(state, "terminal", None)
    if not source_ok:
        return Display("unknown", "source_problem", age)
    if record_type == "inbox_item":
        return Display("open", "observed", age)
    if record_type == "session":
        stale_after = _stale_after(record, default_stale_after_s)
        recent = _recent(record, now, "last_activity_at", stale_after)
        return Display("recent" if recent else "idle", "activity", age)
    if state == "unknown":
        return Display("unknown", "writer_unknown", age)
    stale_after = _stale_after(record, default_stale_after_s)
    process = record.get("process")
    if process:
        checker = process_checker if process_checker is not None else ProcessChecker()
        alive = checker.check(process)
        if alive is True:
            return Display(state, "process", age)
        if alive is False:
            return Display("lost", "process_gone", age)
    if _recent(record, now, "observed_at", stale_after):
        return Display(state, "observed", age)
    return Display("stale", "expired", age)


def _alive(pid):
    """True/False from os.kill, None when the OS refuses to tell us."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return None
    return True


def _linux_start_time(pid):
    with open(f"/proc/{pid}/stat", encoding="ascii", errors="replace") as handle:
        fields = handle.read().rsplit(")", 1)[1].split()
    if len(fields) < 20:
        return None
    ticks = int(fields[19])
    with open("/proc/stat", encoding="ascii") as handle:
        for line in handle:
            if line.startswith("btime "):
                return int(line.split()[1]) + ticks / os.sysconf("SC_CLK_TCK")
    return None


class _ProcBsdInfo(ctypes.Structure):
    """struct proc_bsdinfo from <sys/proc_info.h>; we only read pbi_start_tv*. """
    _fields_ = [
        ("pbi_flags", ctypes.c_uint32),
        ("pbi_status", ctypes.c_uint32),
        ("pbi_xstatus", ctypes.c_uint32),
        ("pbi_pid", ctypes.c_uint32),
        ("pbi_ppid", ctypes.c_uint32),
        ("pbi_uid", ctypes.c_uint32),
        ("pbi_gid", ctypes.c_uint32),
        ("pbi_ruid", ctypes.c_uint32),
        ("pbi_rgid", ctypes.c_uint32),
        ("pbi_svuid", ctypes.c_uint32),
        ("pbi_svgid", ctypes.c_uint32),
        ("rfu_1", ctypes.c_uint32),
        ("pbi_comm", ctypes.c_char * 16),
        ("pbi_name", ctypes.c_char * 32),
        ("pbi_nfiles", ctypes.c_uint32),
        ("pbi_pgid", ctypes.c_uint32),
        ("pbi_pjobc", ctypes.c_uint32),
        ("e_tdev", ctypes.c_uint32),
        ("e_tpgid", ctypes.c_uint32),
        ("pbi_nice", ctypes.c_int32),
        ("pbi_start_tvsec", ctypes.c_uint64),
        ("pbi_start_tvusec", ctypes.c_uint64),
    ]


_LIBPROC = None


def _darwin_start_time(pid):
    global _LIBPROC
    if _LIBPROC is None:
        libproc = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        libproc.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64,
                                         ctypes.c_void_p, ctypes.c_int]
        libproc.proc_pidinfo.restype = ctypes.c_int
        _LIBPROC = libproc
    info = _ProcBsdInfo()
    size = ctypes.sizeof(_ProcBsdInfo)
    got = _LIBPROC.proc_pidinfo(pid, 3, 0, ctypes.byref(info), size)  # 3 = PROC_PIDTBSDINFO
    if got != size:
        return None
    return info.pbi_start_tvsec + info.pbi_start_tvusec / 1_000_000


def _process_start_time(pid):
    """Epoch seconds when the process started, or None when it cannot be read."""
    try:
        if sys.platform.startswith("linux"):
            return _linux_start_time(pid)
        if sys.platform == "darwin":
            return _darwin_start_time(pid)
    except (OSError, ValueError, IndexError, AttributeError):
        return None
    return None


class ProcessChecker:
    """Check a record's `process` against this host (spec §8.2)."""

    def __init__(self, hostname=None):
        self.hostname = (hostname or short_hostname()).lower()

    def check(self, process: dict) -> bool | None:
        if not sys.platform.startswith("linux") and sys.platform != "darwin":
            return None
        if not isinstance(process, dict):
            return None
        host = process.get("host")
        if not isinstance(host, str) or host.lower() != self.hostname:
            return None
        pid = process.get("pid")
        if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
            return False
        want = _parse_ts(process.get("start_time"))
        actual = _process_start_time(pid)
        alive = _alive(pid)
        if alive is not True:
            return alive  # False: the pid is gone; None: the OS will not tell us
        if actual is None:
            # The process exists but its start time cannot be read. Without a
            # start_time in the record that is still evidence it is alive.
            return None if want is not None else True
        if want is None:
            return True
        return abs(actual - want.timestamp()) <= START_TIME_TOLERANCE_S
