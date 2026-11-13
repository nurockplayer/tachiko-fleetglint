"""SQLite read model: connection, migrations and the SQL used by the rest of Fleetglint (architecture §5)."""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

SCHEMA_VERSION = 1

RECORD_TYPES = ("run", "job", "inbox_item", "session", "decision")

_MIGRATION_1 = (
    """CREATE TABLE sources (
        source_id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        root TEXT,
        status TEXT NOT NULL DEFAULT 'ok',
        detail TEXT,
        discontinuity_at TEXT,
        last_scan_at TEXT,
        last_record_at TEXT
    )""",
    """CREATE TABLE segments (
        source_id TEXT NOT NULL,
        seq INTEGER NOT NULL,
        length INTEGER,
        fingerprint TEXT,
        inode INTEGER,
        closed INTEGER NOT NULL,
        compressed INTEGER NOT NULL DEFAULT 0,
        file_size INTEGER,
        file_mtime REAL,
        PRIMARY KEY (source_id, seq)
    )""",
    """CREATE TABLE checkpoints (
        source_id TEXT PRIMARY KEY,
        seq INTEGER NOT NULL,
        byte_offset INTEGER NOT NULL
    )""",
    """CREATE TABLE records (
        source_id TEXT NOT NULL,
        type TEXT NOT NULL,
        id TEXT NOT NULL,
        seq INTEGER NOT NULL,
        byte_offset INTEGER NOT NULL,
        state TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        updated_ts REAL NOT NULL,
        observed_ts REAL NOT NULL,
        stale_after_s INTEGER,
        role_id TEXT,
        project TEXT,
        json TEXT NOT NULL,
        blocks_retention INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (source_id, type, id)
    )""",
    """CREATE TABLE history (
        source_id TEXT NOT NULL,
        seq INTEGER NOT NULL,
        byte_offset INTEGER NOT NULL,
        type TEXT NOT NULL,
        id TEXT NOT NULL,
        state TEXT,
        updated_at TEXT,
        updated_ts REAL,
        json TEXT,
        ingested_ts REAL,
        PRIMARY KEY (source_id, seq, byte_offset)
    )""",
    """CREATE TABLE refs (
        from_source TEXT NOT NULL,
        from_type TEXT NOT NULL,
        from_id TEXT NOT NULL,
        rel TEXT NOT NULL,
        to_type TEXT,
        to_source TEXT,
        to_id TEXT,
        ext_kind TEXT,
        ext_key TEXT,
        ext_url TEXT
    )""",
    """CREATE TABLE quarantine (
        qid INTEGER PRIMARY KEY,
        source_id TEXT,
        seq INTEGER,
        byte_offset INTEGER,
        reason TEXT,
        detail TEXT,
        excerpt TEXT,
        at TEXT
    )""",
    """CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)""",
    "CREATE INDEX records_type_state ON records(type, state)",
    "CREATE INDEX records_updated_ts ON records(updated_ts)",
    "CREATE INDEX refs_to ON refs(to_source, to_type, to_id)",
    "CREATE INDEX refs_from ON refs(from_source, from_type, from_id)",
    "CREATE INDEX history_identity ON history(source_id, type, id, seq, byte_offset)",
)

MIGRATIONS = (_MIGRATION_1,)


def open_db(path, readonly=False):
    """Open the read model, creating and migrating it when writable (architecture §5)."""
    path = Path(path)
    if readonly:
        conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True,
                               isolation_level=None, check_same_thread=False)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
    else:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        migrate(conn)
    conn.row_factory = sqlite3.Row
    return conn


def migrate(conn):
    """Apply forward-only migrations keyed by PRAGMA user_version."""
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version > len(MIGRATIONS):
        raise RuntimeError(f"database schema v{version} is newer than this Fleetglint supports")
    for number, statements in enumerate(MIGRATIONS[version:], start=version + 1):
        conn.execute("BEGIN IMMEDIATE")
        try:
            for statement in statements:
                conn.execute(statement)
            conn.execute(f"PRAGMA user_version = {number}")
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise


# --- timestamps -------------------------------------------------------------

def parse_timestamp(text):
    """Parse an RFC 3339 timestamp with an explicit offset into an aware datetime (spec §2)."""
    if not isinstance(text, str):
        raise ValueError("timestamp is not a string")
    value = text[:-1] + "+00:00" if text.endswith("Z") else text
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp has no offset: {text!r}")
    return parsed


def epoch(text):
    return parse_timestamp(text).timestamp()


def canonical_json(record):
    """Stable serialisation used for storage and change comparison."""
    return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


# --- meta -------------------------------------------------------------------

def get_meta(conn, key, default=None):
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(conn, key, value):
    conn.execute("INSERT INTO meta(key, value) VALUES (?, ?) "
                 "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, str(value)))


def bump_change_counter(conn):
    """Increment meta.change_counter inside the caller's transaction (architecture §5)."""
    value = int(get_meta(conn, "change_counter", "0")) + 1
    set_meta(conn, "change_counter", value)
    return value


def get_change_counter(conn):
    return int(get_meta(conn, "change_counter", "0"))


# --- sources, segments, checkpoints ----------------------------------------

def get_source(conn, source_id):
    return conn.execute("SELECT * FROM sources WHERE source_id = ?", (source_id,)).fetchone()


def ensure_source(conn, source_id, kind, root):
    row = get_source(conn, source_id)
    if row is None:
        conn.execute("INSERT INTO sources(source_id, kind, root) VALUES (?, ?, ?)",
                     (source_id, kind, root))
    elif row["kind"] != kind or row["root"] != root:
        conn.execute("UPDATE sources SET kind = ?, root = ? WHERE source_id = ?",
                     (kind, root, source_id))


_SOURCE_FIELDS = {"kind", "root", "status", "detail", "discontinuity_at", "last_scan_at", "last_record_at"}


def update_source(conn, source_id, **fields):
    unknown = set(fields) - _SOURCE_FIELDS
    if unknown:
        raise ValueError(f"unknown source fields: {sorted(unknown)}")
    if not fields:
        return
    assignments = ", ".join(f"{name} = ?" for name in fields)
    conn.execute(f"UPDATE sources SET {assignments} WHERE source_id = ?",
                 (*fields.values(), source_id))


def refresh_last_record(conn, source_id):
    row = conn.execute(
        "SELECT updated_at FROM records WHERE source_id = ? "
        "ORDER BY updated_ts DESC, seq DESC, byte_offset DESC LIMIT 1", (source_id,)).fetchone()
    value = row["updated_at"] if row else None
    conn.execute("UPDATE sources SET last_record_at = ? WHERE source_id = ?", (value, source_id))
    return value


def source_stats(conn):
    """One row per source: kind, status, record and quarantine counts (for `status`)."""
    return conn.execute(
        "SELECT s.source_id, s.kind, s.status, s.detail, s.last_record_at, "
        " (SELECT count(*) FROM records r WHERE r.source_id = s.source_id) AS records, "
        " (SELECT count(*) FROM quarantine q WHERE q.source_id = s.source_id) AS quarantine "
        "FROM sources s ORDER BY s.source_id").fetchall()


def delete_source_rows(conn, source_id):
    """Remove everything stored for one source (source reset, architecture §5.1)."""
    conn.execute("DELETE FROM refs WHERE from_source = ?", (source_id,))
    conn.execute("DELETE FROM history WHERE source_id = ?", (source_id,))
    conn.execute("DELETE FROM records WHERE source_id = ?", (source_id,))
    conn.execute("DELETE FROM quarantine WHERE source_id = ?", (source_id,))
    conn.execute("DELETE FROM segments WHERE source_id = ?", (source_id,))
    conn.execute("DELETE FROM checkpoints WHERE source_id = ?", (source_id,))
    conn.execute("DELETE FROM sources WHERE source_id = ?", (source_id,))


def get_segment(conn, source_id, seq):
    return conn.execute("SELECT * FROM segments WHERE source_id = ? AND seq = ?",
                        (source_id, seq)).fetchone()


def segments_for(conn, source_id):
    return conn.execute("SELECT * FROM segments WHERE source_id = ? ORDER BY seq",
                        (source_id,)).fetchall()


def put_segment(conn, source_id, seq, *, length, fingerprint, inode, closed, compressed,
                file_size=None, file_mtime=None):
    conn.execute(
        "INSERT INTO segments(source_id, seq, length, fingerprint, inode, closed, compressed,"
        " file_size, file_mtime) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(source_id, seq) DO UPDATE SET length = excluded.length,"
        " fingerprint = excluded.fingerprint, inode = excluded.inode, closed = excluded.closed,"
        " compressed = excluded.compressed, file_size = excluded.file_size,"
        " file_mtime = excluded.file_mtime",
        (source_id, seq, length, fingerprint, inode, int(closed), int(compressed),
         file_size, file_mtime))


def delete_segment(conn, source_id, seq):
    conn.execute("DELETE FROM segments WHERE source_id = ? AND seq = ?", (source_id, seq))


def get_checkpoint(conn, source_id):
    return conn.execute("SELECT * FROM checkpoints WHERE source_id = ?", (source_id,)).fetchone()


def set_checkpoint(conn, source_id, seq, byte_offset):
    conn.execute("INSERT INTO checkpoints(source_id, seq, byte_offset) VALUES (?, ?, ?) "
                 "ON CONFLICT(source_id) DO UPDATE SET seq = excluded.seq,"
                 " byte_offset = excluded.byte_offset", (source_id, seq, byte_offset))


# --- records, history, refs -------------------------------------------------

def get_latest(conn, source_id, type, id):
    return conn.execute("SELECT * FROM records WHERE source_id = ? AND type = ? AND id = ?",
                        (source_id, type, id)).fetchone()


def iter_latest(conn, types=()):
    """Rows of the latest version of every record, optionally limited to some record types."""
    if isinstance(types, str):
        types = (types,)
    types = tuple(types or ())
    query = "SELECT * FROM records"
    params = ()
    if types:
        query += " WHERE type IN (%s)" % ", ".join("?" for _ in types)
        params = types
    query += " ORDER BY updated_ts, source_id, type, id"
    return conn.execute(query, params)


def _record_columns(record):
    updated_at = record["updated_at"]
    updated_ts = epoch(updated_at)
    if record["type"] == "decision":
        observed_text = record["decided_at"]
    elif record["type"] == "session":
        observed_text = record.get("last_activity_at") or updated_at
    else:
        observed_text = record.get("observed_at") or updated_at
    return {
        "state": "done" if record["type"] == "decision" else record["state"],
        "updated_at": updated_at,
        "updated_ts": updated_ts,
        "observed_ts": epoch(observed_text),
        "stale_after_s": record.get("stale_after_s"),
        "role_id": record.get("role_id"),
        "project": record.get("project"),
        "json": canonical_json(record),
    }


def put_latest(conn, record, seq, byte_offset):
    """Store the latest version; an older (seq, byte_offset) never replaces a newer one."""
    source_id, type, id = record["source_id"], record["type"], record["id"]
    existing = conn.execute("SELECT seq, byte_offset FROM records "
                            "WHERE source_id = ? AND type = ? AND id = ?",
                            (source_id, type, id)).fetchone()
    if existing is not None and (existing["seq"], existing["byte_offset"]) > (seq, byte_offset):
        return False
    columns = _record_columns(record)
    conn.execute(
        "INSERT INTO records(source_id, type, id, seq, byte_offset, state, updated_at, updated_ts,"
        " observed_ts, stale_after_s, role_id, project, json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(source_id, type, id) DO UPDATE SET seq = excluded.seq,"
        " byte_offset = excluded.byte_offset, state = excluded.state,"
        " updated_at = excluded.updated_at, updated_ts = excluded.updated_ts,"
        " observed_ts = excluded.observed_ts, stale_after_s = excluded.stale_after_s,"
        " role_id = excluded.role_id, project = excluded.project, json = excluded.json",
        (source_id, type, id, seq, byte_offset, columns["state"], columns["updated_at"],
         columns["updated_ts"], columns["observed_ts"], columns["stale_after_s"],
         columns["role_id"], columns["project"], columns["json"]))
    return True


def insert_history(conn, record, seq, byte_offset, ingested_ts):
    """Append one version; a replay of an already ingested position is a no-op."""
    columns = _record_columns(record)
    cursor = conn.execute(
        "INSERT OR IGNORE INTO history(source_id, seq, byte_offset, type, id, state, updated_at,"
        " updated_ts, json, ingested_ts) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (record["source_id"], seq, byte_offset, record["type"], record["id"], columns["state"],
         columns["updated_at"], columns["updated_ts"], columns["json"], ingested_ts))
    return cursor.rowcount == 1


def refs_for(record):
    """The refs rows derived from one record (architecture §5)."""
    rows = []
    source_id = record["source_id"]

    def add(rel, ref):
        if not isinstance(ref, dict):
            return
        if ref.get("type") == "external":
            rows.append((source_id, record["type"], record["id"], rel, None, None, None,
                         ref.get("kind"), ref.get("key"), ref.get("url")))
        else:
            rows.append((source_id, record["type"], record["id"], rel, ref.get("type"),
                         ref.get("source_id") or source_id, ref.get("id"), None, None, None))

    add("parent_run", record.get("parent_run"))
    add("resume_of", record.get("resume_of"))
    for ref in record.get("waits_on") or ():
        add("waits_on", ref)
    if record["type"] == "job":
        add("job_run", record.get("run"))
    elif record["type"] == "inbox_item":
        add("subject", record.get("subject"))
    elif record["type"] == "session":
        add("parent_session", record.get("parent_session"))
    return rows


def replace_refs(conn, record):
    conn.execute("DELETE FROM refs WHERE from_source = ? AND from_type = ? AND from_id = ?",
                 (record["source_id"], record["type"], record["id"]))
    rows = refs_for(record)
    if rows:
        conn.executemany("INSERT INTO refs(from_source, from_type, from_id, rel, to_type,"
                         " to_source, to_id, ext_kind, ext_key, ext_url) "
                         "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)


def delete_record(conn, source_id, type, id):
    conn.execute("DELETE FROM refs WHERE from_source = ? AND from_type = ? AND from_id = ?",
                 (source_id, type, id))
    conn.execute("DELETE FROM history WHERE source_id = ? AND type = ? AND id = ?",
                 (source_id, type, id))
    conn.execute("DELETE FROM records WHERE source_id = ? AND type = ? AND id = ?",
                 (source_id, type, id))


# --- quarantine -------------------------------------------------------------

QUARANTINE_LIMIT = 1000


def add_quarantine(conn, source_id, seq, byte_offset, reason, detail, excerpt, at):
    conn.execute("INSERT INTO quarantine(source_id, seq, byte_offset, reason, detail, excerpt, at)"
                 " VALUES (?, ?, ?, ?, ?, ?, ?)",
                 (source_id, seq, byte_offset, reason, detail, excerpt, at))
    conn.execute("DELETE FROM quarantine WHERE qid NOT IN "
                 "(SELECT qid FROM quarantine ORDER BY qid DESC LIMIT ?)", (QUARANTINE_LIMIT,))


def quarantine_for(conn, source_id, limit=100):
    return conn.execute("SELECT * FROM quarantine WHERE source_id = ? ORDER BY qid DESC LIMIT ?",
                        (source_id, limit)).fetchall()
