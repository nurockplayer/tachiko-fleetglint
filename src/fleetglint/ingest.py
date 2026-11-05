"""NDJSON segment and adapter ingestion into the SQLite read model (spec §7, architecture §5.1, §6)."""
import gzip
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

from fleetglint import config, store

_SOURCE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*(@[a-z0-9][a-z0-9._-]*)?$")
_SEGMENT_RE = re.compile(r"^(\d{10})\.ndjson(\.gz)?$")
_EXCERPT_BYTES = 1024


class _Discontinuity(Exception):
    """The source cannot be read continuously any more (spec §7.4)."""


def _default_clock():
    return datetime.now().astimezone()


class Ingestor:
    MAX_BATCH_LINES = 1000
    MAX_BATCH_BYTES = 4 * 1024 * 1024

    def __init__(self, conn, cfg, *, validator=None, adapters=(), clock=None):
        self.conn = conn
        self.cfg = cfg
        self.validator = validator
        self.adapters = tuple(adapters)
        self.clock = clock or _default_clock
        self.max_batch_lines = self.MAX_BATCH_LINES
        self.max_batch_bytes = self.MAX_BATCH_BYTES
        # Test seam: called after every line inside its transaction; raising rolls the batch back.
        self.line_hook = None

    # --- time -------------------------------------------------------------

    def _now(self):
        return self.clock()

    def _now_text(self):
        return self._now().isoformat()

    def _now_ts(self):
        return self._now().timestamp()

    # --- NDJSON roots -----------------------------------------------------

    def scan_roots(self):
        """Ingest every source directory under every configured root (spec §7.1–§7.4)."""
        for root in self.cfg.roots:
            root = Path(root)
            try:
                entries = sorted(root.iterdir(), key=lambda entry: entry.name)
            except FileNotFoundError:
                continue
            except NotADirectoryError:
                continue
            for entry in entries:
                if not _valid_source_id(entry.name):
                    continue  # a directory whose name is not a source id is ignored
                if entry.is_symlink():
                    self._touch_source(entry.name, "ndjson", str(root),
                                       detail="ignored symlinked source directory")
                    continue
                if not entry.is_dir():
                    continue
                self._scan_source(entry, root)

    def _scan_source(self, directory, root):
        source_id = directory.name
        conn = self.conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            store.ensure_source(conn, source_id, "ndjson", str(root))
            store.bump_change_counter(conn)
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise

        row = store.get_source(conn, source_id)
        if row["status"] == "discontinuity":
            self._touch_scan(source_id)
            return

        segments, skipped = _list_segments(directory)
        detail = "ignored symlinked segment(s): " + ", ".join(skipped) if skipped else None
        try:
            self._ingest_source(source_id, segments)
        except _Discontinuity as exc:
            self._set_discontinuity(source_id, str(exc))
            return
        self._touch_source(source_id, "ndjson", str(root), detail)

    def _ingest_source(self, source_id, segments):
        seqs = sorted(segments)
        if not seqs:
            return
        for lower, higher in zip(seqs, seqs[1:]):
            if higher != lower + 1:
                raise _Discontinuity(
                    f"missing: segment {lower + 1:010d} is missing between "
                    f"{lower:010d} and {higher:010d}")

        checkpoint = store.get_checkpoint(self.conn, source_id)
        if checkpoint is not None:
            if checkpoint["seq"] not in segments:
                raise _Discontinuity(
                    f"missing: current segment {checkpoint['seq']:010d} is gone")
            for seq in seqs:
                if seq >= checkpoint["seq"]:
                    break
                row = store.get_segment(self.conn, source_id, seq)
                if row is None:
                    raise _Discontinuity(
                        f"appeared: segment {seq:010d} appeared below checkpoint "
                        f"{checkpoint['seq']:010d}")
                path, compressed = segments[seq]
                self._verify_closed(source_id, seq, path, compressed, row)
            start = seqs.index(checkpoint["seq"])
        else:
            start = 0

        for index in range(start, len(seqs)):
            seq = seqs[index]
            path, compressed = segments[seq]
            offset = checkpoint["byte_offset"] if checkpoint is not None and seq == checkpoint["seq"] else 0
            self._process_segment(source_id, seq, path, compressed, offset,
                                  has_higher=index + 1 < len(seqs))

    def _verify_closed(self, source_id, seq, path, compressed, row):
        """Compare a fully ingested segment with what was stored (compression is not a change)."""
        try:
            stat = os.stat(path)
        except OSError:
            raise _Discontinuity(f"missing: segment {seq:010d} disappeared") from None
        if (row["closed"] and row["compressed"] == int(compressed)
                and row["inode"] == stat.st_ino and row["file_size"] == stat.st_size
                and row["file_mtime"] == stat.st_mtime):
            return
        fingerprint, length = _fingerprint(path, compressed)
        if row["length"] != length or row["fingerprint"] != fingerprint:
            raise _Discontinuity(f"changed: segment {seq:010d} content changed")
        conn = self.conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            store.put_segment(conn, source_id, seq, length=length, fingerprint=fingerprint,
                              inode=stat.st_ino, closed=1, compressed=int(compressed),
                              file_size=stat.st_size, file_mtime=stat.st_mtime)
            store.bump_change_counter(conn)
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise

    def _process_segment(self, source_id, seq, path, compressed, offset, *, has_higher):
        try:
            stat = os.stat(path)
        except OSError:
            raise _Discontinuity(f"missing: segment {seq:010d} disappeared") from None
        row = store.get_segment(self.conn, source_id, seq)
        prefix = None
        if not compressed:
            if offset and stat.st_size < offset:
                raise _Discontinuity(
                    f"truncated: segment {seq:010d} is {stat.st_size} bytes, checkpoint is {offset}")
            known = min(4096, stat.st_size)
            prefix = _prefix_fingerprint(path, known)
            if row is not None and not row["closed"]:
                if row["inode"] != stat.st_ino:
                    raise _Discontinuity(f"replaced: segment {seq:010d} inode changed")
                # Compare only the bytes the previous scan saw; appending must not look like a change.
                earlier = _prefix_fingerprint(path, min(4096, row["file_size"] or 0))
                if row["fingerprint"] != earlier:
                    raise _Discontinuity(f"replaced: segment {seq:010d} prefix changed")
        elif row is not None and row["closed"]:
            self._verify_closed(source_id, seq, path, True, row)

        self._ingest_lines(source_id, seq, path, compressed, offset, stat, prefix)

        conn = self.conn
        if has_higher:
            fingerprint, length = _fingerprint(path, compressed)
            stat = os.stat(path)
            conn.execute("BEGIN IMMEDIATE")
            try:
                store.put_segment(conn, source_id, seq, length=length, fingerprint=fingerprint,
                                  inode=stat.st_ino, closed=1, compressed=int(compressed),
                                  file_size=stat.st_size, file_mtime=stat.st_mtime)
                store.set_checkpoint(conn, source_id, seq + 1, 0)
                store.bump_change_counter(conn)
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
        elif compressed:
            fingerprint, length = _fingerprint(path, True)
            conn.execute("BEGIN IMMEDIATE")
            try:
                store.put_segment(conn, source_id, seq, length=length, fingerprint=fingerprint,
                                  inode=stat.st_ino, closed=1, compressed=1,
                                  file_size=stat.st_size, file_mtime=stat.st_mtime)
                store.set_checkpoint(conn, source_id, seq, length)
                store.bump_change_counter(conn)
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise

    def _ingest_lines(self, source_id, seq, path, compressed, offset, stat, prefix):
        batch = []
        batch_bytes = 0
        position = offset
        for raw, end in _iter_lines(path, compressed, offset):
            if batch and (len(batch) >= self.max_batch_lines
                          or batch_bytes + len(raw) + 1 > self.max_batch_bytes):
                self._commit_batch(source_id, seq, batch, batch[-1][1], stat, prefix, compressed)
                batch, batch_bytes = [], 0
            batch.append((raw, end))
            batch_bytes += len(raw) + 1
            position = end
            if len(batch) >= self.max_batch_lines or batch_bytes >= self.max_batch_bytes:
                self._commit_batch(source_id, seq, batch, position, stat, prefix, compressed)
                batch, batch_bytes = [], 0
        if batch:
            self._commit_batch(source_id, seq, batch, position, stat, prefix, compressed)
        else:
            self._commit_batch(source_id, seq, (), position, stat, prefix, compressed)

    def _commit_batch(self, source_id, seq, batch, position, stat, prefix, compressed):
        conn = self.conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            for raw, end in batch:
                self._handle_line(source_id, raw, seq, end)
            store.set_checkpoint(conn, source_id, seq, position)
            store.put_segment(conn, source_id, seq, length=stat.st_size, fingerprint=prefix,
                              inode=stat.st_ino, closed=0, compressed=int(compressed),
                              file_size=stat.st_size, file_mtime=stat.st_mtime)
            store.bump_change_counter(conn)
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise

    def _handle_line(self, source_id, raw, seq, byte_offset):
        record, reason, detail = self._validate(raw, source_id)
        if record is not None and record.get("source_id") != source_id:
            record, reason, detail = None, "source_mismatch", \
                "record source_id differs from the source directory"
        if record is not None:
            conn = self.conn
            conn.execute("SAVEPOINT line")
            try:
                store.insert_history(conn, record, seq, byte_offset, self._now_ts())
                store.put_latest(conn, record, seq, byte_offset)
                store.replace_refs(conn, record)
            except (KeyError, TypeError, ValueError) as exc:
                conn.execute("ROLLBACK TO line")
                conn.execute("RELEASE line")
                record, reason, detail = None, "schema", str(exc)
            else:
                conn.execute("RELEASE line")
        if record is None:
            store.add_quarantine(self.conn, source_id, seq, byte_offset, reason or "schema",
                                 detail, _excerpt(raw), self._now_text())
        if self.line_hook is not None:
            self.line_hook(record, seq, byte_offset)

    def _validate(self, raw, source_id):
        if self.validator is not None:
            return self.validator(raw, source_id)
        if isinstance(raw, dict):
            return _validate_record(raw, source_id)
        return _classify_line(raw, source_id)

    # --- adapters ---------------------------------------------------------

    def scan_adapters(self):
        """Run every adapter once (architecture §6)."""
        for adapter in self.adapters:
            source_id = adapter.source_id
            existing = store.get_source(self.conn, source_id)
            try:
                available = adapter.available()
            except OSError:
                available = False
            if not available:
                if existing is not None:
                    self._set_adapter_state(source_id, "unavailable", "adapter input is not present")
                continue
            now = self._now()
            result = adapter.scan(now)
            if result.status == "unavailable":
                self._set_adapter_state(source_id, "unavailable", result.detail or "adapter unavailable")
                continue
            self._apply_adapter_scan(adapter, result, now)

    def _set_adapter_state(self, source_id, status, detail):
        conn = self.conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            store.ensure_source(conn, source_id, "adapter", None)
            store.update_source(conn, source_id, status=status, detail=detail,
                                last_scan_at=self._now_text())
            store.bump_change_counter(conn)
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise

    def _apply_adapter_scan(self, adapter, result, now):
        source_id = adapter.source_id
        conn = self.conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            store.ensure_source(conn, source_id, "adapter", None)
            checkpoint = store.get_checkpoint(conn, source_id)
            position = checkpoint["byte_offset"] if checkpoint else 0
            ingested_ts = now.timestamp()
            for record in result.records:
                position += 1
                self._apply_adapter_record(source_id, record, position, ingested_ts)
            store.set_checkpoint(conn, source_id, 0, position)
            store.update_source(conn, source_id, status="ok", detail=None,
                                last_scan_at=now.isoformat())
            store.refresh_last_record(conn, source_id)
            store.bump_change_counter(conn)
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise

    def _apply_adapter_record(self, source_id, original, position, ingested_ts):
        record, reason, detail = self._validate(original, source_id)
        if record is not None and record.get("source_id") != source_id:
            record, reason, detail = None, "source_mismatch", \
                "record source_id differs from the adapter source"
        conn = self.conn
        if record is None:
            store.add_quarantine(conn, source_id, 0, position, reason or "schema", detail,
                                 _json_excerpt(original), self._now_text())
            return
        conn.execute("SAVEPOINT record")
        try:
            stored = store.get_latest(conn, source_id, record["type"], record["id"])
            if stored is None:
                changed = True
            else:
                previous = json.loads(stored["json"])
                if previous == record:
                    changed = False
                elif _without_observed(previous) == _without_observed(record):
                    store.put_latest(conn, record, 0, position)
                    changed = False
                else:
                    changed = True
            if changed:
                store.insert_history(conn, record, 0, position, ingested_ts)
                store.put_latest(conn, record, 0, position)
                store.replace_refs(conn, record)
        except (KeyError, TypeError, ValueError) as exc:
            conn.execute("ROLLBACK TO record")
            conn.execute("RELEASE record")
            store.add_quarantine(conn, source_id, 0, position, "schema", str(exc),
                                 _json_excerpt(original), self._now_text())
            return
        conn.execute("RELEASE record")

    # --- source state -----------------------------------------------------

    def _touch_scan(self, source_id):
        conn = self.conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            store.update_source(conn, source_id, last_scan_at=self._now_text())
            store.bump_change_counter(conn)
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise

    def _touch_source(self, source_id, kind, root, detail=None):
        conn = self.conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            store.ensure_source(conn, source_id, kind, root)
            row = store.get_source(conn, source_id)
            fields = {"last_scan_at": self._now_text()}
            if row["status"] == "ok":
                fields["detail"] = detail
            store.update_source(conn, source_id, **fields)
            store.refresh_last_record(conn, source_id)
            store.bump_change_counter(conn)
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise

    def _set_discontinuity(self, source_id, detail):
        conn = self.conn
        now = self._now_text()
        conn.execute("BEGIN IMMEDIATE")
        try:
            store.update_source(conn, source_id, status="discontinuity", detail=detail,
                                discontinuity_at=now, last_scan_at=now)
            store.bump_change_counter(conn)
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise

    # --- maintenance ------------------------------------------------------

    def reset_source(self, source_id):
        """Clear a discontinuity: drop the source's rows and ingest its remaining segments again."""
        conn = self.conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            store.delete_source_rows(conn, source_id)
            store.bump_change_counter(conn)
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        self.scan_roots()
        if any(getattr(adapter, "source_id", None) == source_id for adapter in self.adapters):
            self.scan_adapters()

    def apply_retention(self):
        """Delete old segments and history under the spec §7.5 conditions."""
        conn = self.conn
        now_ts = self._now_ts()
        segment_cutoff = now_ts - self.cfg.segment_days * 86400
        abandon_cutoff = now_ts - self.cfg.abandon_days * 86400
        history_cutoff = now_ts - self.cfg.history_days * 86400
        changed = False
        conn.execute("BEGIN IMMEDIATE")
        try:
            cursor = conn.execute("UPDATE records SET blocks_retention = 0 WHERE blocks_retention != 0")
            changed = cursor.rowcount > 0
            sources = conn.execute(
                "SELECT * FROM sources WHERE kind = 'ndjson' AND root IS NOT NULL").fetchall()
            for source in sources:
                deleted, blockers = self._retain_segments(source, segment_cutoff, abandon_cutoff)
                changed = changed or deleted
                if blockers:
                    changed = self._flag_blockers(blockers) or changed
            cursor = conn.execute(
                "DELETE FROM history WHERE ingested_ts IS NOT NULL AND ingested_ts < ?",
                (history_cutoff,))
            changed = changed or cursor.rowcount > 0
            for row in conn.execute("SELECT * FROM records WHERE updated_ts < ?",
                                    (history_cutoff,)).fetchall():
                if _terminal(row):
                    store.delete_record(conn, row["source_id"], row["type"], row["id"])
                    changed = True
            if changed:
                store.bump_change_counter(conn)
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise

    def _retain_segments(self, source, segment_cutoff, abandon_cutoff):
        conn = self.conn
        source_id = source["source_id"]
        checkpoint = store.get_checkpoint(conn, source_id)
        if checkpoint is None:
            return False, []
        directory = Path(source["root"]) / source_id
        changed = False
        for row in store.segments_for(conn, source_id):
            seq = row["seq"]
            if not row["closed"] or seq >= checkpoint["seq"]:
                break
            paths = _segment_paths(directory, seq)
            if not paths:
                store.delete_segment(conn, source_id, seq)
                changed = True
                continue
            try:
                mtime = min(os.stat(path).st_mtime for path in paths)
            except OSError:
                continue
            if mtime >= segment_cutoff:
                break
            blockers = [record for record in conn.execute(
                "SELECT source_id, type, id, state, updated_ts FROM records "
                "WHERE source_id = ? AND seq = ?", (source_id, seq))
                if _blocks_retention(record, abandon_cutoff)]
            if blockers:
                return changed, blockers
            for path in paths:
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
            store.delete_segment(conn, source_id, seq)
            changed = True
        return changed, []

    def _flag_blockers(self, blockers):
        conn = self.conn
        flagged = False
        for record in blockers:
            if record["type"] == "inbox_item" and record["state"] == "open":
                cursor = conn.execute(
                    "UPDATE records SET blocks_retention = 1 "
                    "WHERE source_id = ? AND type = ? AND id = ?",
                    (record["source_id"], record["type"], record["id"]))
                flagged = flagged or cursor.rowcount > 0
        return flagged


# --- files ----------------------------------------------------------------

def _valid_source_id(name):
    return len(name) <= 128 and _SOURCE_ID_RE.match(name) is not None


def _list_segments(directory):
    """Map seq -> (path, compressed); symlinked segments are not followed."""
    segments = {}
    skipped = []
    for entry in sorted(directory.iterdir(), key=lambda item: item.name):
        match = _SEGMENT_RE.match(entry.name)
        if not match:
            continue
        seq = int(match.group(1))
        if seq < 1:
            continue
        if entry.is_symlink():
            skipped.append(entry.name)
            continue
        compressed = bool(match.group(2))
        if seq not in segments or (segments[seq][1] and not compressed):
            segments[seq] = (entry, compressed)
    return segments, skipped


def _segment_paths(directory, seq):
    paths = []
    for name in (f"{seq:010d}.ndjson", f"{seq:010d}.ndjson.gz"):
        path = directory / name
        try:
            if path.is_symlink() or not path.is_file():
                continue
        except OSError:
            continue
        paths.append(path)
    return paths


def _iter_lines(path, compressed, offset):
    """Yield (line bytes without newline, offset just past it) from offset onwards."""
    if compressed:
        if offset:
            with gzip.open(path, "rb") as handle:
                data = handle.read()
            if offset > len(data):
                raise _Discontinuity(f"truncated: segment {path.name} is shorter than checkpoint {offset}")
            yield from _split_lines(data[offset:], offset)
            return
        opener = gzip.open
    else:
        opener = open
    with opener(path, "rb") as handle:
        if not compressed:
            handle.seek(offset)
        position = offset
        buffer = b""
        while True:
            chunk = handle.read(256 * 1024)
            if not chunk:
                break
            buffer += chunk
            start = 0
            while True:
                newline = buffer.find(b"\n", start)
                if newline < 0:
                    break
                position += newline - start + 1
                yield buffer[start:newline], position
                start = newline + 1
            buffer = buffer[start:]


def _split_lines(data, base):
    position = base
    start = 0
    while (newline := data.find(b"\n", start)) >= 0:
        position += newline - start + 1
        yield data[start:newline], position
        start = newline + 1


def _prefix_fingerprint(path, length):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read(length)).hexdigest()


def _fingerprint(path, compressed):
    digest = hashlib.sha256()
    length = 0
    opener = gzip.open if compressed else open
    with opener(path, "rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            length += len(chunk)
    return digest.hexdigest(), length


def _excerpt(raw):
    return raw[:_EXCERPT_BYTES].decode("utf-8", "replace")


def _json_excerpt(value):
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        text = repr(value)
    return text[:_EXCERPT_BYTES]


def _without_observed(record):
    return {key: value for key, value in record.items() if key != "observed_at"}


def _blocks_retention(record, abandon_cutoff):
    """Does this latest record keep its segment from being deleted (spec §7.5)?"""
    if record["type"] == "inbox_item":
        return record["state"] == "open"
    if _terminal(record):
        return False
    return record["updated_ts"] >= abandon_cutoff


def _terminal(record):
    if record["type"] == "inbox_item":
        return record["state"] == "acked"
    if record["type"] == "session":
        return record["state"] == "ended"
    return record["state"] in ("done", "failed", "cancelled")


# --- default validators (schema.py is written separately) -----------------

def _classify_line(raw, expected_source_id):
    from fleetglint.schema import classify_line
    return classify_line(raw, expected_source_id)


def _validate_record(record, expected_source_id):
    from fleetglint.schema import validate
    errors = validate(record)
    if record.get("source_id") != expected_source_id:
        return None, "source_mismatch", "record source_id differs from the adapter source"
    if errors:
        return None, "schema", "; ".join(str(error) for error in errors)
    return record, None, None


# --- command entry point --------------------------------------------------

def default_adapters(cfg):
    """Adapters available in this version (their modules are added by later work)."""
    return ()


def rebuild(cfg, adapters=()):
    """Delete the database and ingest everything retained again."""
    for suffix in ("", "-wal", "-shm"):
        Path(str(cfg.db_path) + suffix).unlink(missing_ok=True)
    conn = store.open_db(cfg.db_path)
    try:
        ingestor = Ingestor(conn, cfg, adapters=adapters)
        ingestor.scan_roots()
        ingestor.scan_adapters()
    finally:
        conn.close()


def run(args):
    try:
        cfg = config.load(getattr(args, "config", None))
        if args.command == "ingest":
            return _run_ingest(cfg, once=args.once)
        if args.command == "status":
            return _run_status(cfg)
        if args.command == "source":
            return _run_source(cfg, args.source_id)
        if args.command == "rebuild":
            rebuild(cfg, default_adapters(cfg))
            print(f"rebuilt {cfg.db_path}")
            return 0
        print(f"fleetglint: unknown command {args.command}", file=sys.stderr)
        return 2
    except (config.ConfigError, OSError, sqlite3.Error) as exc:
        print(f"fleetglint: {exc}", file=sys.stderr)
        return 3


def _run_ingest(cfg, once):
    conn = store.open_db(cfg.db_path)
    try:
        ingestor = Ingestor(conn, cfg, adapters=default_adapters(cfg))
        if once:
            ingestor.scan_roots()
            ingestor.scan_adapters()
            ingestor.apply_retention()
            _print_summary(conn)
            return 0
        return _loop(ingestor, cfg)
    finally:
        conn.close()


def _loop(ingestor, cfg):
    ingestor.apply_retention()
    next_roots = next_adapters = next_retention = 0.0
    try:
        while True:
            now = time.monotonic()
            if now >= next_roots:
                ingestor.scan_roots()
                next_roots = now + cfg.poll_s
            if now >= next_adapters:
                ingestor.scan_adapters()
                next_adapters = now + cfg.adapter_poll_s
            if now >= next_retention:
                ingestor.apply_retention()
                next_retention = now + 3600
            wake = min(next_roots, next_adapters, next_retention) - time.monotonic()
            time.sleep(max(0.0, min(1.0, wake)))
    except KeyboardInterrupt:
        return 0


def _print_summary(conn):
    sources = conn.execute("SELECT count(*) FROM sources").fetchone()[0]
    records = conn.execute("SELECT count(*) FROM records").fetchone()[0]
    quarantine = conn.execute("SELECT count(*) FROM quarantine").fetchone()[0]
    print(f"ingest: {records} records from {sources} sources, {quarantine} quarantined")


def _run_status(cfg):
    if not Path(cfg.db_path).exists():
        print(f"no database at {cfg.db_path}")
        return 0
    conn = store.open_db(cfg.db_path, readonly=True)
    try:
        print(f"{'source':32} {'kind':8} {'status':12} {'records':>7} {'quarantine':>10}  last record")
        for row in store.source_stats(conn):
            print(f"{row['source_id']:32} {row['kind']:8} {row['status']:12} "
                  f"{row['records']:>7} {row['quarantine']:>10}  {row['last_record_at'] or '-'}")
        print(f"db: {cfg.db_path} ({_human_size(Path(cfg.db_path).stat().st_size)})")
        return 0
    finally:
        conn.close()


def _run_source(cfg, source_id):
    conn = store.open_db(cfg.db_path)
    try:
        Ingestor(conn, cfg, adapters=default_adapters(cfg)).reset_source(source_id)
        print(f"source {source_id}: reset and re-ingested")
        return 0
    finally:
        conn.close()


def _human_size(size):
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024 or unit == "GiB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} GiB"
