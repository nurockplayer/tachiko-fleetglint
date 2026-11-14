"""Builds the API JSON from the SQLite read model (docs/architecture.md §4).

Every call opens its own read-only connection and closes it (architecture §5): the
HTTP threads never share the ingest thread's connection.
"""
import json
import sqlite3
import time
from pathlib import Path

from fleetglint import __version__, files, liveness, redact, store
from fleetglint.adapters.base import short_hostname

LIST_LIMIT = 500
HISTORY_LIMIT = 50
QUARANTINE_LIMIT = 100
SHORT_TEXT = 300
ATTENTION_TEXT = 200
PROCESS_CACHE_S = 2.0
TERMINAL_STATES = frozenset({"done", "failed", "cancelled"})
BOARD_LIST_LIMIT = 200
BOARD_EXCEPTION_LIMIT = 50
BOARD_RECENT_LIMIT = 20
BOARD_SESSIONS_LIMIT = 30
BOARD_INBOX_ITEMS = 5

_SOURCES_SQL = (
    "SELECT s.source_id, s.kind, s.status, s.detail, s.last_scan_at, s.last_record_at,"
    " (SELECT count(*) FROM records r WHERE r.source_id = s.source_id) AS records,"
    " (SELECT count(*) FROM quarantine q WHERE q.source_id = s.source_id) AS quarantine"
    " FROM sources s ORDER BY s.source_id")


_LOOKUP_KEYS = frozenset({"id", "source_id"})


def _text(value, limit=None):
    """A redacted string (spec §9), optionally cut to `limit` characters."""
    if not isinstance(value, str):
        return value
    redacted = redact.redact(value)[0]
    return redacted[:limit] if limit is not None else redacted


def _redact_json(value):
    """The raw view: every string in the JSON tree is redacted (spec §9)."""
    if isinstance(value, str):
        return redact.redact(value)[0]
    if isinstance(value, list):
        return [_redact_json(item) for item in value]
    if isinstance(value, dict):
        return {key: _redact_json(item) for key, item in value.items()}
    return value


def _redact_response(value):
    """Every string leaving the API is redacted (spec §9), except the ids clients look records up by."""
    if isinstance(value, str):
        return redact.redact(value)[0]
    if isinstance(value, list):
        return [_redact_response(item) for item in value]
    if isinstance(value, dict):
        return {key: item if key in _LOOKUP_KEYS and isinstance(item, str)
                else _redact_response(item)
                for key, item in value.items()}
    return value


def _age_text(seconds):
    if seconds is None:
        return ""
    if seconds < 3600:
        return f"{max(1, seconds // 60)}m "
    if seconds < 86400:
        return f"{seconds // 3600}h "
    return f"{seconds // 86400}d "


def _included(row, window_start):
    """Non-terminal records, and terminal or acked ones inside the window (architecture §4.1)."""
    if row["type"] == "inbox_item":
        return row["state"] == "open" or row["updated_ts"] >= window_start
    return row["state"] not in TERMINAL_STATES or row["updated_ts"] >= window_start


def _countable_work(row):
    """A non-terminal run or job past the list limit still feeds counts and attention."""
    return row["state"] not in TERMINAL_STATES


def _countable_inbox(row):
    """An open inbox item past the list limit still needs attention."""
    return row["state"] == "open"


class _CachedProcessChecker:
    """A `ProcessChecker` whose answers live for a couple of seconds (one board, one check per pid)."""

    def __init__(self, checker, ttl=PROCESS_CACHE_S, clock=time.monotonic):
        self._checker = checker
        self._ttl = ttl
        self._clock = clock
        self._seen = {}

    def check(self, process):
        key = json.dumps(process, sort_keys=True, default=str)
        now = self._clock()
        cached = self._seen.get(key)
        if cached is not None and now - cached[0] < self._ttl:
            return cached[1]
        result = self._checker.check(process)
        self._seen[key] = (now, result)
        return result


class _View:
    """One read of the store: summaries, display states and extended refs (architecture §4.1, §4.2)."""

    def __init__(self, conn, now, *, default_stale_after_s, process_checker,
                 allowed_roots, list_limit):
        self.conn = conn
        self.now = now
        self.default_stale_after_s = default_stale_after_s
        self.process_checker = process_checker
        self.allowed_roots = allowed_roots
        self.list_limit = list_limit
        self.statuses = {row["source_id"]: row["status"]
                         for row in conn.execute("SELECT source_id, status FROM sources")}
        self._records = {}
        self._latest = {}

    # -- lookups -----------------------------------------------------------

    def record(self, row):
        key = (row["source_id"], row["type"], row["id"])
        value = self._records.get(key)
        if value is None:
            value = json.loads(row["json"])
            self._records[key] = value
        return value

    def latest(self, source_id, type, id):
        key = (source_id, type, id)
        if key not in self._latest:
            self._latest[key] = store.get_latest(self.conn, source_id, type, id)
        return self._latest[key]

    def source_ok(self, source_id):
        return self.statuses.get(source_id, "ok") == "ok"

    def display(self, record, source_id):
        return liveness.display(
            record, self.now,
            default_stale_after_s=self.default_stale_after_s,
            source_ok=self.source_ok(source_id),
            process_checker=self.process_checker)

    # -- refs --------------------------------------------------------------

    def extended_identity(self, type, source_id, id):
        """A record ref with `resolved` and, when resolved, `display_state` and `title`."""
        out = {"type": type, "id": id, "source_id": source_id}
        row = self.latest(source_id, type, id)
        out["resolved"] = row is not None
        if row is not None:
            record = self.record(row)
            out["display_state"] = self.display(record, source_id).state
            out["title"] = _text(record.get("title"))
        return out

    def extended(self, ref, default_source):
        """A record ref extended, or an external ref passed through (architecture §4.1)."""
        if not isinstance(ref, dict):
            return None
        if ref.get("type") == "external":
            out = {"type": "external"}
            for key in ("kind", "key", "url"):
                if key in ref:
                    out[key] = ref[key]
            return out
        if not isinstance(ref.get("type"), str) or not isinstance(ref.get("id"), str):
            return None
        return self.extended_identity(ref["type"], ref.get("source_id") or default_source, ref["id"])

    def ref(self, record_ref):
        return self.extended_identity(record_ref["type"], record_ref["source_id"], record_ref["id"])

    # -- summaries ---------------------------------------------------------

    def file_ref(self, path):
        if not isinstance(path, str):
            return None
        return {"path": path, "readable": files.is_readable(path, self.allowed_roots)}

    def links(self, record):
        links = []
        for link in record.get("links") or ():
            if not isinstance(link, dict):
                continue
            entry = {"label": _text(link.get("label"))}
            if isinstance(link.get("url"), str):
                entry["url"] = link["url"]
            elif isinstance(link.get("path"), str):
                entry["path"] = link["path"]
                entry["readable"] = files.is_readable(link["path"], self.allowed_roots)
            links.append(entry)
        return links

    def summary(self, row):
        record = self.record(row)
        source_id = row["source_id"]
        display = self.display(record, source_id)
        summary = {
            "ref": {"type": row["type"], "id": row["id"], "source_id": source_id},
            "state": row["state"],
            "display_state": display.state,
            "evidence": {"kind": display.evidence, "age_s": display.age_s, "detail": None},
            "updated_at": row["updated_at"],
            # Sessions observe activity through `last_activity_at` (spec §2, §8.3).
            "observed_at": record.get("observed_at") or (
                record.get("last_activity_at") if row["type"] == "session" else None
            ) or row["updated_at"],
            "project": record.get("project"),
            "title": _text(record.get("title")),
            "links": self.links(record),
        }
        summary.update(_FIELDS[row["type"]](self, record, row, source_id))
        if row["type"] == "run" and "worker" in record:
            summary["worker"] = _text(record["worker"])
        return summary

    # -- per-type summary fields ------------------------------------------

    def _run_fields(self, record, row, source_id):
        return {
            "agent": record.get("agent"),
            "model": record.get("model"),
            "provider": record.get("provider"),
            "effort": record.get("effort"),
            "role_id": record.get("role_id"),
            "session_id": record.get("session_id"),
            "started_at": record.get("started_at"),
            "ended_at": record.get("ended_at"),
            "exit_code": record.get("exit_code"),
            "summary": _text(record.get("summary"), SHORT_TEXT),
            "parent_run": self.extended(record.get("parent_run"), source_id),
            "resume_of": self.extended(record.get("resume_of"), source_id),
            "waits_on": [ref for ref in (self.extended(item, source_id)
                                         for item in record.get("waits_on") or ()) if ref],
        }

    def _job_fields(self, record, row, source_id):
        return {
            "kind": record.get("kind"),
            "command_summary": _text(record.get("command_summary")),
            "run": self.extended(record.get("run"), source_id),
            "role_id": record.get("role_id"),
            "started_at": record.get("started_at"),
            "ended_at": record.get("ended_at"),
            "exit_code": record.get("exit_code"),
            "signal": record.get("signal"),
            "summary": _text(record.get("summary"), SHORT_TEXT),
            "log": self.file_ref(record.get("log_path")),
            "result": self.file_ref(record.get("result_path")),
        }

    def _inbox_fields(self, record, row, source_id):
        return {
            "role_id": record.get("role_id"),
            "kind": record.get("kind"),
            "subject": self.extended(record.get("subject"), source_id),
            "outcome": _text(record.get("outcome")),
            "action_required": bool(record.get("action_required", False)),
            "created_at": record.get("created_at"),
            "acked_at": record.get("acked_at"),
            "detail": _text(record.get("detail"), SHORT_TEXT),
            "blocks_retention": bool(row["blocks_retention"]),
        }

    def _session_fields(self, record, row, source_id):
        models = record.get("models")
        usage = record.get("usage")
        return {
            "agent": record.get("agent"),
            "model": record.get("model"),
            "models": list(models) if isinstance(models, list) else [],
            "provider": record.get("provider"),
            "effort": record.get("effort"),
            "role_id": record.get("role_id"),
            "started_at": record.get("started_at"),
            "last_activity_at": record.get("last_activity_at"),
            "ended_at": record.get("ended_at"),
            "turn_open": record.get("turn_open"),
            "entries": record.get("entries"),
            "parent_session": self.extended(record.get("parent_session"), source_id),
            "usage": _redact_json(usage) if isinstance(usage, dict) else None,
        }


_FIELDS = {
    "run": _View._run_fields,
    "job": _View._job_fields,
    "inbox_item": _View._inbox_fields,
    "session": _View._session_fields,
    "decision": lambda view, record, row, source_id: {"role_id": record.get("role_id"), "text": _text(record.get("text")), "decided_at": record.get("decided_at")},
}


class QueryBackend:
    """The server's read model (architecture §4)."""

    def __init__(self, cfg, *, process_checker=None, adapters=()):
        self.cfg = cfg
        self.list_limit = LIST_LIMIT
        checker = liveness.ProcessChecker() if process_checker is None else process_checker
        self.process_checker = _CachedProcessChecker(checker)
        self.allowed_roots = [Path(path) for path in cfg.allowed_roots]
        self.allowed_roots.extend(Path(root) for root in cfg.roots)
        for adapter in adapters:
            self.allowed_roots.extend(Path(root) for root in getattr(adapter, "allowed_roots", ()))

    # -- connections -------------------------------------------------------

    def _open(self):
        path = Path(self.cfg.db_path)
        if not path.exists():
            return None
        try:
            return store.open_db(path, readonly=True)
        except sqlite3.OperationalError:
            return None

    def _view(self, conn, now):
        return _View(conn, now,
                     default_stale_after_s=self.cfg.default_stale_after_s,
                     process_checker=self.process_checker,
                     allowed_roots=self.allowed_roots,
                     list_limit=self.list_limit)

    def _server(self):
        return {"version": __version__, "host": short_hostname(), "read_only": True}

    # -- endpoints ---------------------------------------------------------

    def change_counter(self):
        conn = self._open()
        if conn is None:
            return 0
        try:
            return store.get_change_counter(conn)
        finally:
            conn.close()

    def snapshot(self, now):
        conn = self._open()
        if conn is None:
            return self._empty_snapshot(now)
        try:
            return _redact_response(self._snapshot(conn, now))
        finally:
            conn.close()

    def _empty_snapshot(self, now):
        return {
            "api": 1,
            "generated_at": now.isoformat(),
            "server": self._server(),
            "window_hours": self.cfg.window_hours,
            "sources": [],
            "counts": {"running": 0, "waiting": 0, "attention": 0,
                       "stale_lost_unknown": 0, "sessions_recent": 0},
            "runs": [],
            "jobs": [],
            "inbox": [],
            "sessions": [],
            "attention": [],
            "truncated": {"runs": False, "jobs": False, "inbox": False, "sessions": False},
            "demo": False,
        }

    def _snapshot(self, conn, now):
        view = self._view(conn, now)
        window_start = now.timestamp() - self.cfg.window_hours * 3600
        rows = {"run": [], "job": [], "inbox_item": [], "session": []}
        for row in store.iter_latest(conn):
            if row["type"] == "decision":
                continue
            if row["type"] == "session":
                if row["observed_ts"] >= window_start:
                    rows["session"].append(row)
            elif _included(row, window_start):
                rows[row["type"]].append(row)

        runs, runs_cut, open_runs = self._summaries(view, rows["run"], "updated_ts",
                                                    _countable_work)
        jobs, jobs_cut, open_jobs = self._summaries(view, rows["job"], "updated_ts",
                                                    _countable_work)
        inbox, inbox_cut, open_inbox = self._summaries(view, rows["inbox_item"], "updated_ts",
                                                       _countable_inbox)
        sessions, sessions_cut, _ = self._summaries(view, rows["session"], "observed_ts")
        sources = self._sources(conn)
        # Attention and counts see every included row; only the display lists are cut.
        work = runs + jobs + open_runs + open_jobs
        attention = _attention(view, work, inbox + open_inbox, sources, window_start)
        sessions_recent = sum(1 for item in sessions if item["display_state"] == "recent")
        sessions_recent += self._recent_sessions_beyond(view, rows["session"])
        return {
            "api": 1,
            "generated_at": now.isoformat(),
            "server": self._server(),
            "window_hours": self.cfg.window_hours,
            "sources": sources,
            "counts": {
                "running": sum(1 for item in work if item["display_state"] == "running"),
                "waiting": sum(1 for item in work if item["display_state"] == "waiting"),
                "attention": len(attention),
                "stale_lost_unknown": sum(1 for item in work
                                          if item["display_state"] in ("stale", "lost", "unknown")
                                          and not _beyond_window(item, window_start)),
                "sessions_recent": sessions_recent,
            },
            "runs": runs,
            "jobs": jobs,
            "inbox": inbox,
            "sessions": sessions,
            "attention": attention[:view.list_limit],
            "truncated": {"runs": runs_cut, "jobs": jobs_cut,
                          "inbox": inbox_cut, "sessions": sessions_cut},
            "demo": any(item["ref"]["source_id"].startswith("demo@")
                        for item in runs + jobs + inbox + sessions),
        }

    # -- board -------------------------------------------------------------

    def board(self, now):
        conn = self._open()
        if conn is None:
            return self._empty_board(now)
        try:
            return _redact_response(self._board(conn, now))
        finally:
            conn.close()

    def _empty_board(self, now):
        return {
            "api": 1,
            "generated_at": now.isoformat(),
            "server": self._server(),
            "window_hours": self.cfg.window_hours,
            "inbox_old_after_s": self.cfg.inbox_old_after_s,
            "demo": False,
            "sources": [],
            "capabilities": {"execution": False, "requests": False},
            "counts": {"needs_you": 0, "queued": 0, "waiting": 0, "running": 0, "lead_inbox_open": 0,
                       "lead_inbox_old": 0, "process_gone": 0, "out_of_date": 0,
                       "unverified_recent": 0, "failed_recent": 0, "older_unverified": 0,
                       "sessions_recent": 0},
            "needs_you": [],
            "projects": [],
            "lead_inbox": [],
            "queued": [],
            "waiting": [],
            "running": [],
            "exceptions": {"process_gone": [], "out_of_date": [], "unverified_recent": []},
            "recent": [],
            "sessions": [],
            "sessions_total": 0,
            "truncated": {"queued": False, "waiting": False, "running": False, "exceptions": False,
                          "recent": False, "lead_inbox": False},
        }

    def _board(self, conn, now):
        return _board_data(self._view(conn, now), self.cfg, now, self._server())

    def _summaries(self, view, rows, order_field, beyond=None):
        """The newest `list_limit` summaries and, for counting, those of `beyond` rows."""
        rows.sort(key=lambda row: (row[order_field], row["seq"], row["byte_offset"],
                                   row["source_id"], row["type"], row["id"]), reverse=True)
        limit = view.list_limit
        shown = [view.summary(row) for row in rows[:limit]]
        extra = [view.summary(row) for row in rows[limit:] if beyond is not None and beyond(row)]
        return shown, len(rows) > limit, extra

    def _recent_sessions_beyond(self, view, rows):
        """Recent sessions past the list limit still count (architecture §4.1)."""
        return sum(1 for row in rows[view.list_limit:]
                   if view.display(view.record(row), row["source_id"]).state == "recent")

    def _sources(self, conn):
        return _source_entries(conn)

    def record(self, now, source_id, type, id):
        conn = self._open()
        if conn is None:
            return None
        try:
            row = store.get_latest(conn, source_id, type, id)
            if row is None:
                return None
            view = self._view(conn, now)
            record = view.record(row)
            usage = record.get("usage")
            return _redact_response({
                "api": 1,
                "generated_at": now.isoformat(),
                "record": view.summary(row),
                "full": _redact_json(record),
                "relations": _relations(view, row, record),
                "history": self._history(conn, row),
                "usage": _redact_json(usage) if isinstance(usage, dict) else None,
            })
        finally:
            conn.close()

    def _history(self, conn, row):
        return [{
            "seq": entry["seq"],
            "byte_offset": entry["byte_offset"],
            "updated_at": entry["updated_at"],
            "state": entry["state"],
        } for entry in conn.execute(
            "SELECT seq, byte_offset, updated_at, state FROM history"
            " WHERE source_id = ? AND type = ? AND id = ?"
            " ORDER BY seq DESC, byte_offset DESC LIMIT ?",
            (row["source_id"], row["type"], row["id"], HISTORY_LIMIT))]

    def file(self, now, source_id, type, id, field, index):
        conn = self._open()
        if conn is None:
            return None
        try:
            row = store.get_latest(conn, source_id, type, id)
            if row is None:
                return None
            record = json.loads(row["json"])
        finally:
            conn.close()
        path = _file_path(record, field, index)
        if path is None:
            return {"api": 1, "readable": False, "reason": "no_path"}
        result = files.read_tail(path, self.allowed_roots,
                                 self.cfg.max_tail_kib * 1024, redact=redact.redact)
        return _redact_response({"api": 1, **result})

    def quarantine(self, source_id):
        conn = self._open()
        if conn is None:
            return None
        try:
            if store.get_source(conn, source_id) is None:
                return None
            return [{
                "position": f"{row['seq']:010d}:{row['byte_offset']}",
                "reason": _text(row["reason"]),
                "excerpt": _text(row["excerpt"]),
            } for row in store.quarantine_for(conn, source_id, QUARANTINE_LIMIT)]
        finally:
            conn.close()


def _source_entries(conn):
    return [{
        "source_id": row["source_id"],
        "kind": row["kind"],
        "status": row["status"],
        "detail": _text(row["detail"]) if row["status"] != "ok" else None,
        "last_scan_at": row["last_scan_at"],
        "last_record_at": row["last_record_at"],
        "quarantine_count": row["quarantine"],
        "records": row["records"],
    } for row in conn.execute(_SOURCES_SQL)]


def _file_path(record, field, index):
    """The path the field names, from the record itself; the client never sends one (architecture §4.3)."""
    if field in ("log_path", "result_path"):
        path = record.get(field)
        return path if isinstance(path, str) else None
    if field == "link" and isinstance(index, int):
        links = record.get("links")
        if isinstance(links, list) and 0 <= index < len(links) and isinstance(links[index], dict):
            path = links[index].get("path")
            return path if isinstance(path, str) else None
    return None


def _relations(view, row, record):
    source_id, type, id = row["source_id"], row["type"], row["id"]

    def pointing(rel):
        rows = view.conn.execute(
            "SELECT DISTINCT from_source, from_type, from_id FROM refs"
            " WHERE rel = ? AND to_source = ? AND to_type = ? AND to_id = ?"
            " ORDER BY from_source, from_type, from_id", (rel, source_id, type, id))
        return [view.extended_identity(item["from_type"], item["from_source"], item["from_id"])
                for item in rows]

    if type == "run":
        parent = view.extended(record.get("parent_run"), source_id)
        resume_of = view.extended(record.get("resume_of"), source_id)
        children = pointing("parent_run")
        resumed_by = pointing("resume_of")
        jobs = pointing("job_run")
    else:
        parent = resume_of = None
        children, resumed_by, jobs = [], [], []
    return {
        "parent": parent,
        "resume_of": resume_of,
        "children": children,
        "resumed_by": resumed_by,
        "jobs": jobs,
        "inbox": pointing("subject"),
        "waited_on_by": pointing("waits_on"),
    }


def _attention(view, work, inbox, sources, window_start):
    """Needs attention, in the brief's order (architecture §4.1)."""
    entries = []

    def add(reason, who, subject, source_id, text):
        entries.append({"reason": reason, "who": who, "subject": subject,
                        "source_id": source_id, "text": _clip(text)})

    open_items = [item for item in inbox if item["state"] == "open"]
    for item in open_items:
        if item["action_required"]:
            add("action_required", item["role_id"], item["subject"],
                item["ref"]["source_id"], _inbox_text(item))
    for item in open_items:
        if not item["action_required"]:
            add("inbox", item["role_id"], item["subject"],
                item["ref"]["source_id"], _inbox_text(item))
    for reason in ("lost", "stale", "unknown"):
        for item in work:
            if item["display_state"] == reason and not _beyond_window(item, window_start):
                add(reason, _who(view, item), view.ref(item["ref"]), item["ref"]["source_id"],
                    _work_text(item))
    for source in sources:
        if source["status"] != "ok":
            add("source", None, None, source["source_id"],
                f"{source['status']}: {source['detail'] or 'no detail'}")
    return entries


def _epoch(value):
    """Seconds since the epoch for an RFC 3339 string, or None."""
    if not isinstance(value, str):
        return None
    try:
        return store.epoch(value)
    except ValueError:
        return None


def _age_s(value, now):
    """Whole seconds since `value`, or None when it is absent or unreadable."""
    ts = _epoch(value)
    return None if ts is None else max(0, int(now.timestamp() - ts))


def _beyond_window(item, window_start):
    """Whether a summary's `updated_at` is before the window start (`older`, architecture §4.1b)."""
    ts = _epoch(item.get("updated_at"))
    return ts is not None and ts < window_start


def _row_order(row):
    return (row["seq"], row["byte_offset"], row["source_id"], row["type"], row["id"])


def _newest(pair):
    row = pair[0]
    return (row["updated_ts"],) + _row_order(row)


def _inbox_order(pair):
    row, item = pair
    ts = _epoch(item["created_at"])
    return (ts is not None, ts or 0.0) + _row_order(row)


def _started_order(pair):
    row, item = pair
    ts = _epoch(item["started_at"])
    return (ts is not None, ts or 0.0) + _row_order(row)


def _role_order(role):
    oldest = role["oldest_age_s"]
    return (-role["action_required"], -(oldest if oldest is not None else -1),
            role["role_id"] or "")


def _work_item(view, row, section_reason, now):
    item = view.summary(row)
    item["started_age_s"] = _age_s(view.record(row).get("started_at"), now)
    item["section_reason"] = section_reason
    return item


def _inbox_item(view, row, now):
    item = view.summary(row)
    item["age_s"] = _age_s(view.record(row).get("created_at"), now)
    return item


def _covered_by_run(row, record, live_runs):
    """Rule 5: a `wait-worker` job is plumbing when a listed run of the same role started no earlier."""
    started = _epoch(record.get("started_at"))
    role_id = row["role_id"]
    if started is None or role_id is None:
        return False
    return any(role == role_id and run_started is not None and run_started >= started
               for role, run_started in live_runs)


def _board_excluded(row, window_start):
    """A run or job the board never lists: terminal or unknown and older than the window."""
    if row["type"] not in ("run", "job"):
        return row["type"] == "inbox_item" and row["state"] != "open"
    return row["updated_ts"] < window_start and (
        row["state"] == "unknown" or row["state"] in TERMINAL_STATES)


def _board_demo(rows, window_start):
    return any(row["source_id"].startswith("demo@")
               and not _board_excluded(row, window_start)
               for row in rows["run"] + rows["job"] + rows["inbox_item"] + rows["session"])


def _board_sessions(view, rows):
    """The newest sessions in the window and how many of them are recent (rule 10)."""
    rows = sorted(rows, key=lambda row: (row["observed_ts"],) + _row_order(row), reverse=True)
    recent = sum(1 for row in rows
                 if view.display(view.record(row), row["source_id"]).state == "recent")
    return [view.summary(row) for row in rows[:BOARD_SESSIONS_LIMIT]], recent


def _board_inbox(view, rows, cfg, now, viewer_roles, counts):
    """Rules 1 and 2: needs_you items and open inbox items grouped by role."""
    needs_you, groups = [], {}
    for row in rows:
        if row["state"] != "open":
            continue
        item = _inbox_item(view, row, now)
        if item["action_required"] and item["role_id"] in viewer_roles:
            if item["age_s"] is not None and item["age_s"] <= cfg.needs_you_hours * 3600:
                needs_you.append((row, item))
            continue
        groups.setdefault(item["role_id"], []).append((row, item))
    needs_you.sort(key=_inbox_order, reverse=True)
    counts["needs_you"] = len(needs_you)

    roles = []
    for role_id, pairs in groups.items():
        pairs.sort(key=_inbox_order, reverse=True)
        ages = [item["age_s"] for _, item in pairs if item["age_s"] is not None]
        old = sum(1 for _, item in pairs
                  if item["age_s"] is not None and item["age_s"] > cfg.inbox_old_after_s)
        roles.append({
            "role_id": role_id,
            "open": len(pairs),
            "old": old,
            "oldest_age_s": max(ages) if ages else None,
            "action_required": sum(1 for _, item in pairs if item["action_required"]),
            "items": [item for _, item in pairs[:BOARD_INBOX_ITEMS]],
        })
        counts["lead_inbox_open"] += len(pairs)
        counts["lead_inbox_old"] += old
    roles.sort(key=_role_order)
    return [item for _, item in needs_you], roles


def _board_work(view, rows, now, window_start, counts):
    """Rules 3-9: one place per run or job, in this order."""
    queued, waiting, running, recent = [], [], [], []
    exceptions = {"process_gone": [], "out_of_date": [], "unverified_recent": []}
    live_runs = []  # (role_id, started_ts) of runs in display running or waiting

    def place(row, dstate, older, kind=None):
        if dstate == "queued":
            queued.append((row, _work_item(view, row, None, now)))
        elif dstate == "waiting":
            waiting.append((row, _work_item(view, row, "waits_on", now)))
        elif dstate == "running":
            if row["type"] == "job" and kind == "wait":
                waiting.append((row, _work_item(view, row, "lead_wait", now)))
            elif row["type"] == "job" and kind == "wait-worker":
                if not _covered_by_run(row, view.record(row), live_runs):
                    waiting.append((row, _work_item(view, row, "lead_wait", now)))
            else:
                running.append((row, _work_item(view, row, None, now)))
        elif dstate in ("lost", "stale"):
            if older:
                counts["older_unverified"] += 1
            else:
                key = "process_gone" if dstate == "lost" else "out_of_date"
                exceptions[key].append((row, _work_item(view, row, None, now)))
        elif dstate == "unknown":
            if older:
                counts["older_unverified"] += 1
            else:
                exceptions["unverified_recent"].append((row, _work_item(view, row, None, now)))
        elif dstate in TERMINAL_STATES:
            if row["type"] == "job" and kind == "wait-worker":
                return
            recent.append((row, _work_item(view, row, None, now)))
            if dstate == "failed":
                counts["failed_recent"] += 1

    for row in rows["run"]:
        older = row["updated_ts"] < window_start
        if older and row["state"] == "unknown":
            counts["older_unverified"] += 1
            continue
        if older and row["state"] in TERMINAL_STATES:
            continue
        record = view.record(row)
        dstate = view.display(record, row["source_id"]).state
        if dstate in ("running", "waiting"):
            live_runs.append((row["role_id"], _epoch(record.get("started_at"))))
        place(row, dstate, older)

    for row in rows["job"]:
        older = row["updated_ts"] < window_start
        if older and row["state"] == "unknown":
            counts["older_unverified"] += 1
            continue
        if older and row["state"] in TERMINAL_STATES:
            continue
        record = view.record(row)
        place(row, view.display(record, row["source_id"]).state, older, record.get("kind"))

    queued.sort(key=_newest, reverse=True)
    waiting.sort(key=_newest, reverse=True)
    running.sort(key=_started_order, reverse=True)
    for items in exceptions.values():
        items.sort(key=_newest, reverse=True)
    recent.sort(key=_newest, reverse=True)
    return ([item for _, item in queued],
            [item for _, item in waiting], [item for _, item in running],
            {key: [item for _, item in items] for key, items in exceptions.items()},
            [item for _, item in recent])


def _board_projects(view, rows, needs_you, now, window_start, cfg):
    groups = {}
    def project(record):
        return record.get("project")

    def line_key(record):
        if record["type"] == "run":
            if record.get("role_id") and record.get("title"):
                return (project(record), "run", record["role_id"], record.get("agent"), record["title"])
            return None
        if record.get("kind") == "github-actions":
            return (project(record), "gha", record.get("command_summary"))
        if record.get("cwd"):
            return (project(record), "job", record["cwd"], record.get("role_id"), record.get("kind"),
                    record.get("title"), record.get("command_summary"))
        if record.get("role_id") and record.get("title"):
            return (project(record), "job", record["role_id"], record.get("kind"), record["title"])
        return None

    done_lines = {}
    for row in rows["run"] + rows["job"]:
        if row["updated_ts"] < window_start:
            continue
        record = view.record(row)
        if view.display(record, row["source_id"]).state == "done":
            key = line_key(record)
            if key is not None:
                done_lines[key] = max(done_lines.get(key, row["updated_ts"]), row["updated_ts"])

    def group(name):
        return groups.setdefault(name, {"project": name, "needs_you": [], "in_progress": [],
            "decisions": [], "recent": {"done": [], "failed": []},
            "lead_inbox_open": 0, "sessions_recent": 0, "last_activity_at": None})

    # Include live work and open inbox even if last updated before the window.
    for kind, entries in rows.items():
        for row in entries:
            if kind == "decision":
                included = row["observed_ts"] >= now.timestamp() - 7 * 86400
            elif kind == "session":
                included = row["observed_ts"] >= window_start
            elif kind == "inbox_item":
                included = row["state"] == "open" or row["updated_ts"] >= window_start
            else:
                included = not _board_excluded(row, window_start)
            if not included:
                continue
            record = view.record(row)
            name = project(record)
            g = group(name)
            activity = record.get("decided_at") if kind == "decision" else (record.get("last_activity_at") if kind == "session" else record["updated_at"])
            if g["last_activity_at"] is None or _epoch(activity) > _epoch(g["last_activity_at"]):
                g["last_activity_at"] = activity
            if kind == "decision":
                g["decisions"].append({"ref": {"type": kind, "id": row["id"], "source_id": row["source_id"]},
                    "project": name, "role_id": record["role_id"], "text": _text(record["text"]),
                    "decided_at": record["decided_at"], "links": view.links(record)})
            elif kind == "session":
                g["sessions_recent"] += view.display(record, row["source_id"]).state == "recent"
            elif kind == "inbox_item":
                if row["state"] == "open" and not (record.get("action_required") and record.get("role_id") in cfg.viewer_roles):
                    g["lead_inbox_open"] += 1
            else:
                state = view.display(record, row["source_id"]).state
                key = line_key(record)
                if (state in ("stale", "lost", "failed", "unknown")
                        and row["updated_ts"] >= window_start
                        and (key is None or done_lines.get(key, row["updated_ts"]) <= row["updated_ts"])):
                    reason = (record.get("summary") or (f"exit {record['exit_code']}" if record.get("exit_code") is not None else "failed")) if state == "failed" else "unverified" if state == "unknown" else state
                    g["needs_you"].append(_work_item(view, row, reason, now))
                if (state in ("done", "failed") and row["updated_ts"] >= window_start
                        and not (record.get("kind") == "github-actions" and record["id"].endswith(".poll"))):
                    g["recent"][state].append(_work_item(view, row, None, now))
    for item in needs_you:
        ref = item["ref"]
        row = view.latest(ref["source_id"], ref["type"], ref["id"])
        group(project(view.record(row)))["needs_you"].append(item)

    live_runs = []
    for row in rows["run"]:
        if _board_excluded(row, window_start):
            continue
        record = view.record(row)
        if view.display(record, row["source_id"]).state in ("running", "waiting", "queued"):
            item = _work_item(view, row, None, now)
            item["jobs"] = []
            group(project(record))["in_progress"].append(item)
            live_runs.append((row, record, item))
    for row in rows["job"]:
        if _board_excluded(row, window_start):
            continue
        record = view.record(row)
        if view.display(record, row["source_id"]).state != "running":
            continue
        job_ref = (row["source_id"], row["id"])
        attached = False
        for run_row, run_record, item in live_runs:
            run_ref = record.get("run") or {}
            match = (run_ref.get("type") == "run" and run_ref.get("id") == run_row["id"] and (run_ref.get("source_id") or row["source_id"]) == run_row["source_id"])
            match |= any(ref.get("type") == "job" and (ref.get("source_id") or run_row["source_id"], ref.get("id")) == job_ref for ref in run_record.get("waits_on", []))
            if match:
                item["jobs"].append(_work_item(view, row, None, now))
                attached = True
        if not attached:
            group(project(record))["in_progress"].append(_work_item(view, row, None, now))

    for g in groups.values():
        g["needs_you_total"] = len(g["needs_you"])
        g["decisions"].sort(key=lambda x: _epoch(x["decided_at"]), reverse=True)
        for items in g["recent"].values():
            items.sort(key=lambda x: _epoch(x["updated_at"]), reverse=True)
        g["truncated"] = {"needs_you": len(g["needs_you"]) > BOARD_LIST_LIMIT,
            "in_progress": len(g["in_progress"]) > BOARD_LIST_LIMIT,
            "decisions": len(g["decisions"]) > 10,
            "recent": {key: len(items) > 10 for key, items in g["recent"].items()}}
        g["needs_you"] = g["needs_you"][:BOARD_LIST_LIMIT]
        g["in_progress"] = g["in_progress"][:BOARD_LIST_LIMIT]
        g["decisions"] = g["decisions"][:10]
        g["recent"] = {key: items[:10] for key, items in g["recent"].items()}
    return sorted(groups.values(), key=lambda g: (not bool(g["needs_you"]), g["project"] is None and not g["needs_you"], -(_epoch(g["last_activity_at"]) or 0), g["project"] or ""))


def _board_data(view, cfg, now, server):
    window_start = now.timestamp() - cfg.window_hours * 3600
    rows = {"run": [], "job": [], "inbox_item": [], "session": [], "decision": []}
    for row in store.iter_latest(view.conn):
        if row["type"] == "session":
            if row["observed_ts"] >= window_start:
                rows["session"].append(row)
        else:
            rows[row["type"]].append(row)

    counts = {"needs_you": 0, "queued": 0, "waiting": 0, "running": 0, "lead_inbox_open": 0,
              "lead_inbox_old": 0, "process_gone": 0, "out_of_date": 0,
              "unverified_recent": 0, "failed_recent": 0, "older_unverified": 0,
              "sessions_recent": 0}
    needs_you, lead_inbox = _board_inbox(view, rows["inbox_item"], cfg, now,
                                         set(cfg.viewer_roles), counts)
    queued, waiting, running, exceptions, recent = _board_work(view, rows, now, window_start,
                                                               counts)
    sessions, counts["sessions_recent"] = _board_sessions(view, rows["session"])
    counts["queued"] = len(queued)
    counts["waiting"] = len(waiting)
    counts["running"] = len(running)
    counts["process_gone"] = len(exceptions["process_gone"])
    counts["out_of_date"] = len(exceptions["out_of_date"])
    counts["unverified_recent"] = len(exceptions["unverified_recent"])

    return {
        "api": 1,
        "generated_at": now.isoformat(),
        "server": server,
        "window_hours": cfg.window_hours,
        "inbox_old_after_s": cfg.inbox_old_after_s,
        "demo": _board_demo(rows, window_start),
        "sources": _source_entries(view.conn),
        "capabilities": {"execution": bool(rows["run"] or rows["job"]),
                         "requests": bool(rows["inbox_item"])},
        "counts": counts,
        "needs_you": needs_you[:BOARD_LIST_LIMIT],
        "projects": _board_projects(view, rows, needs_you, now, window_start, cfg),
        "lead_inbox": lead_inbox[:BOARD_LIST_LIMIT],
        "queued": queued[:BOARD_LIST_LIMIT],
        "waiting": waiting[:BOARD_LIST_LIMIT],
        "running": running[:BOARD_LIST_LIMIT],
        "exceptions": {key: items[:BOARD_EXCEPTION_LIMIT]
                       for key, items in exceptions.items()},
        "recent": recent[:BOARD_RECENT_LIMIT],
        "sessions": sessions,
        "sessions_total": len(rows["session"]),
        "truncated": {
            "queued": len(queued) > BOARD_LIST_LIMIT,
            "waiting": len(waiting) > BOARD_LIST_LIMIT,
            "running": len(running) > BOARD_LIST_LIMIT,
            "exceptions": any(len(items) > BOARD_EXCEPTION_LIMIT
                              for items in exceptions.values()),
            "recent": len(recent) > BOARD_RECENT_LIMIT,
            "lead_inbox": len(lead_inbox) > BOARD_LIST_LIMIT
                          or any(role["open"] > BOARD_INBOX_ITEMS for role in lead_inbox),
        },
    }


def _clip(text, limit=ATTENTION_TEXT):
    return text[:limit] if isinstance(text, str) else text


def _inbox_text(item):
    parts = [item["kind"] or "inbox_item"]
    if item["outcome"]:
        parts.append(item["outcome"])
    line = " · ".join(parts)
    return f"{line} — {item['detail']}" if item["detail"] else line


def _work_text(item):
    ref, state = item["ref"], item["display_state"]
    prefix = f"{ref['type']} {ref['id']} {state}"
    if state == "lost":
        return f"{prefix} — process gone, no terminal record"
    if state == "stale":
        return f"{prefix} {_age_text(item['evidence']['age_s'])}— no evidence"
    return f"{prefix} — no usable evidence"


def _who(view, item):
    """A run/job's own role, else the owning run's role (architecture §4.1)."""
    if item.get("role_id"):
        return item["role_id"]
    if item["ref"]["type"] == "job" and item.get("run") and item["run"].get("resolved"):
        row = view.latest(item["run"]["source_id"], "run", item["run"]["id"])
        if row is not None:
            return view.record(row).get("role_id")
    return None


def backend(cfg):
    """The backend `fleetglint serve` hands to the HTTP server."""
    from fleetglint import ingest

    return QueryBackend(cfg, adapters=ingest.default_adapters(cfg))
