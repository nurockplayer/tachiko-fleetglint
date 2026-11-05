"""NDJSON segment and adapter ingestion into the SQLite read model (spec §7, architecture §5.1, §6)."""
import fcntl
import gzip
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import traceback
import zlib
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from fleetglint import config, store
from fleetglint.demo import SOURCE_ID as DEMO_SOURCE_ID

_SOURCE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*(@[a-z0-9][a-z0-9._-]*)?$")
_SEGMENT_RE = re.compile(r"^(\d{10})\.ndjson(\.gz)?$")
_EXCERPT_BYTES = 1024

SERVICE_LOCK_BUSY = ("fleetglint is running (stop it first: brew services stop fleetglint, "
                     "or Ctrl-C the serve process)")


class ServiceLockBusy(Exception):
    """Another Fleetglint process holds the service lock."""


def acquire_service_lock(cfg, blocking=True):
    """Take <db_path>.lock exclusively and return the open handle; the caller closes it."""
    path = Path(str(cfg.db_path) + ".lock")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    handle = open(path, "a")
    flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
    try:
        fcntl.flock(handle, flags)
    except BlockingIOError:
        handle.close()
        raise ServiceLockBusy(SERVICE_LOCK_BUSY) from None
    return handle


def release_service_lock(handle):
    """Unlock and close a handle from `acquire_service_lock`."""
    try:
        fcntl.flock(handle, fcntl.LOCK_UN)
    finally:
        handle.close()


@contextmanager
def hold_service_lock(cfg, blocking=True):
    """Hold <db_path>.lock exclusively; serve/ingest keep it for their lifetime (architecture §5)."""
    handle = acquire_service_lock(cfg, blocking)
    try:
        yield
    finally:
        release_service_lock(handle)


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
                # The root itself vanished: its sources can no longer be read continuously.
                self._mark_missing_sources(root, set())
                continue
            except NotADirectoryError:
                continue
            present = {entry.name for entry in entries}
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
            self._mark_missing_sources(root, present)

    def _mark_missing_sources(self, root, present):
        """A previously ingested source directory that vanished is a discontinuity (spec §7.4)."""
        sources = self.conn.execute(
            "SELECT * FROM sources WHERE kind = 'ndjson' AND root IS NOT NULL").fetchall()
        for source in sources:
            source_id = source["source_id"]
            if source_id in present or Path(source["root"]) != root:
                continue
            if source_id == DEMO_SOURCE_ID:
                self._forget_source(source_id)  # `fleetglint demo --clear` empties the board
                continue
            if source["status"] == "discontinuity":
                continue
            checkpoint = store.get_checkpoint(self.conn, source_id)
            if not store.segments_for(self.conn, source_id) and (
                    checkpoint is None
                    or self._retention_explains(source_id, checkpoint["seq"])):
                continue
            self._set_discontinuity(source_id, "source directory is missing")

    def _forget_source(self, source_id):
        """Drop everything stored for a source, including its retention markers."""
        conn = self.conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            store.delete_source_rows(conn, source_id)
            conn.execute("DELETE FROM meta WHERE key = ?", (self._retention_marker_key(source_id),))
            conn.execute("DELETE FROM meta WHERE key GLOB ?", (f"retired:{source_id}:*",))
            store.bump_change_counter(conn)
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise

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
        # Files retention retired in the database but did not unlink yet (crash after COMMIT).
        segments = {seq: value for seq, value in segments.items()
                    if self._retired(source_id, seq) is None}
        seqs = sorted(segments)
        if not seqs:
            checkpoint = store.get_checkpoint(self.conn, source_id)
            if checkpoint is not None and not self._retention_explains(source_id, checkpoint["seq"]):
                raise _Discontinuity(
                    f"missing: all segments are missing (checkpoint segment "
                    f"{checkpoint['seq']:010d})")
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

    @staticmethod
    def _retention_marker_key(source_id):
        return f"retention_deleted:{source_id}"

    def _retention_explains(self, source_id, checkpoint_seq):
        """Did retention record deleting every segment up to this checkpoint (spec §7.5)?"""
        value = store.get_meta(self.conn, self._retention_marker_key(source_id))
        if value is None:
            return False
        try:
            return checkpoint_seq <= int(value)
        except ValueError:
            return False

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

        position = self._ingest_lines(source_id, seq, path, compressed, offset, stat, prefix)

        conn = self.conn
        if has_higher:
            fingerprint, length = _fingerprint(path, compressed)
            stat = os.stat(path)
            trailing = _trailing_bytes(path, compressed, position)
            conn.execute("BEGIN IMMEDIATE")
            try:
                store.put_segment(conn, source_id, seq, length=length, fingerprint=fingerprint,
                                  inode=stat.st_ino, closed=1, compressed=int(compressed),
                                  file_size=stat.st_size, file_mtime=stat.st_mtime)
                store.set_checkpoint(conn, source_id, seq + 1, 0)
                if trailing:
                    store.add_quarantine(
                        conn, source_id, seq, position, "invalid_json",
                        "unterminated line in a closed segment", _excerpt(trailing),
                        self._now_text())
                store.bump_change_counter(conn)
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
        elif compressed:
            fingerprint, length = _fingerprint(path, True)
            trailing = _trailing_bytes(path, True, position)
            conn.execute("BEGIN IMMEDIATE")
            try:
                store.put_segment(conn, source_id, seq, length=length, fingerprint=fingerprint,
                                  inode=stat.st_ino, closed=1, compressed=1,
                                  file_size=stat.st_size, file_mtime=stat.st_mtime)
                store.set_checkpoint(conn, source_id, seq, length)
                if trailing:
                    store.add_quarantine(
                        conn, source_id, seq, position, "invalid_json",
                        "unterminated line in a closed segment", _excerpt(trailing),
                        self._now_text())
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
        return position

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
            existing = store.get_source(conn, source_id)
            store.ensure_source(conn, source_id, "adapter", None)
            changed = existing is None
            checkpoint = store.get_checkpoint(conn, source_id)
            position = checkpoint["byte_offset"] if checkpoint else 0
            ingested_ts = now.timestamp()
            for record in result.records:
                position += 1
                changed = self._apply_adapter_record(source_id, record, position,
                                                     ingested_ts) or changed
            store.set_checkpoint(conn, source_id, 0, position)
            if existing is None or existing["status"] != "ok" or existing["detail"] is not None:
                changed = True
            store.update_source(conn, source_id, status="ok", detail=None,
                                last_scan_at=now.isoformat())
            store.refresh_last_record(conn, source_id)
            # A scan that changed nothing (the usual re-scan) must not move the
            # change counter, or the board's ETag never settles (architecture §10).
            if changed:
                store.bump_change_counter(conn)
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise

    def _apply_adapter_record(self, source_id, original, position, ingested_ts):
        """Upsert one adapter record; return whether anything visible changed."""
        record, reason, detail = self._validate(original, source_id)
        if record is not None and record.get("source_id") != source_id:
            record, reason, detail = None, "source_mismatch", \
                "record source_id differs from the adapter source"
        conn = self.conn
        if record is None:
            store.add_quarantine(conn, source_id, 0, position, reason or "schema", detail,
                                 _json_excerpt(original), self._now_text())
            return True
        conn.execute("SAVEPOINT record")
        try:
            stored = store.get_latest(conn, source_id, record["type"], record["id"])
            if stored is None:
                changed = True
            else:
                previous = json.loads(stored["json"])
                if previous == record:
                    conn.execute("RELEASE record")
                    return False
                if _without_observed(previous) == _without_observed(record):
                    store.put_latest(conn, record, 0, position)
                    conn.execute("RELEASE record")
                    return True
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
            return True
        conn.execute("RELEASE record")
        return True

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
        self._forget_source(source_id)
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
        allowed_roots = {Path(root).resolve() for root in self.cfg.roots}
        self._unlink_retired_leftovers(allowed_roots)
        changed = False
        # Files are unlinked only after COMMIT: a failure before it must not lose data
        # whose metadata is rolled back. A crash after COMMIT leaves retired files that
        # the scanner skips and the next pass removes.
        self._pending_unlink = []
        conn.execute("BEGIN IMMEDIATE")
        try:
            cursor = conn.execute("UPDATE records SET blocks_retention = 0 WHERE blocks_retention != 0")
            changed = cursor.rowcount > 0
            sources = conn.execute(
                "SELECT * FROM sources WHERE kind = 'ndjson' AND root IS NOT NULL").fetchall()
            for source in sources:
                deleted, blockers = self._retain_segments(source, segment_cutoff, abandon_cutoff,
                                                          allowed_roots)
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
            self._pending_unlink = []
            raise
        self._unlink_retired(self._pending_unlink)
        self._pending_unlink = []

    @staticmethod
    def _retired_key(source_id, seq):
        return f"retired:{source_id}:{seq}"

    def _unlink_retired(self, retired):
        """Unlink retired files that still match what was ingested, then forget them."""
        done = []
        for source_id, seq, paths, length, fingerprint in retired:
            for path in paths:
                try:
                    current, current_length = _fingerprint(path, path.name.endswith(".gz"))
                except FileNotFoundError:
                    continue
                except (OSError, EOFError, zlib.error):
                    break
                if (current_length, current) != (length, fingerprint):
                    break  # replaced since it was retired: never delete someone else's file
                path.unlink(missing_ok=True)
            else:
                done.append(self._retired_key(source_id, seq))
        if done:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                self.conn.executemany("DELETE FROM meta WHERE key = ?", [(key,) for key in done])
                self.conn.execute("COMMIT")
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise

    def _retired(self, source_id, seq):
        """(length, fingerprint) recorded when retention retired this segment, or None."""
        value = store.get_meta(self.conn, self._retired_key(source_id, seq))
        if value is None:
            return None
        try:
            data = json.loads(value)
            return data["length"], data["fingerprint"]
        except (ValueError, KeyError, TypeError):
            return None

    def _unlink_retired_leftovers(self, allowed_roots):
        """Finish deletions a crash interrupted after COMMIT (verified against the recorded content)."""
        retired = []
        for source in self.conn.execute(
                "SELECT * FROM sources WHERE kind = 'ndjson' AND root IS NOT NULL").fetchall():
            directory = self._retention_dir(source, allowed_roots)
            if directory is None:
                continue
            try:
                segments, _ = _list_segments(directory)
            except OSError:
                continue
            for seq, (path, _compressed) in segments.items():
                recorded = self._retired(source["source_id"], seq)
                if recorded is not None:
                    retired.append((source["source_id"], seq, [path], *recorded))
        self._unlink_retired(retired)

    def _retain_segments(self, source, segment_cutoff, abandon_cutoff, allowed_roots):
        conn = self.conn
        source_id = source["source_id"]
        if source["status"] != "ok":
            return False, []  # never delete data for a source that needs attention
        checkpoint = store.get_checkpoint(conn, source_id)
        if checkpoint is None:
            return False, []
        directory = self._retention_dir(source, allowed_roots)
        if directory is None:
            return False, []  # a symlinked or foreign source directory is never followed
        changed = False
        for row in store.segments_for(conn, source_id):
            seq = row["seq"]
            if not row["closed"] or seq >= checkpoint["seq"]:
                break
            paths = self._verified_segment_paths(directory, row)
            if paths is None:
                # The file on disk is no longer the one that was ingested: keep everything.
                store.update_source(conn, source_id, status="discontinuity",
                                    detail=f"segment {seq:010d} changed before retention",
                                    discontinuity_at=self._now_text())
                return True, []
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
            self._pending_unlink.append((source_id, seq, paths, row["length"], row["fingerprint"]))
            store.set_meta(conn, self._retired_key(source_id, seq),
                           json.dumps({"length": row["length"], "fingerprint": row["fingerprint"]}))
            store.delete_segment(conn, source_id, seq)
            store.set_meta(conn, self._retention_marker_key(source_id), seq)
            changed = True
        return changed, []

    def _verified_segment_paths(self, directory, row):
        """Same-seq files whose content equals what was ingested, or None if any differs."""
        if row["length"] is None or row["fingerprint"] is None:
            return None
        paths = _segment_paths(directory, row["seq"])
        if not paths:
            return None
        verified = []
        for path in paths:
            try:
                fingerprint, length = _fingerprint(path, path.name.endswith(".gz"))
            except (OSError, EOFError, zlib.error):
                return None
            if length != row["length"] or fingerprint != row["fingerprint"]:
                return None
            verified.append(path)
        return verified

    def _retention_dir(self, source, allowed_roots):
        """The resolved source directory, only when it is a real dir directly under a root."""
        root = Path(source["root"])
        try:
            resolved_root = root.resolve()
            if resolved_root not in allowed_roots:
                return None
            candidate = root / source["source_id"]
            if candidate.is_symlink():
                return None
            resolved = candidate.resolve()
        except OSError:
            return None
        if resolved.parent != resolved_root:
            return None
        return resolved

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
    """Real files named for this seq directly inside a resolved source directory."""
    paths = []
    for name in (f"{seq:010d}.ndjson", f"{seq:010d}.ndjson.gz"):
        path = directory / name
        try:
            if path.is_symlink() or not path.is_file():
                continue
            if path.resolve().parent != directory:
                continue
        except OSError:
            continue
        paths.append(path)
    return paths


def _iter_lines(path, compressed, offset):
    """Yield (line bytes without newline, offset just past it) from offset onwards.

    An overlong line is kept only as its first MAX_LINE_BYTES + 1 bytes; the rest is
    skipped up to its LF, so the buffer stays bounded and the checkpoint still moves
    past the whole line (spec §7.3).
    """
    from fleetglint.schema import MAX_LINE_BYTES

    limit = MAX_LINE_BYTES + 1
    opener = gzip.open if compressed else open
    with opener(path, "rb") as handle:
        if compressed and offset:
            # Decompress forward instead of reading the whole member; one byte back
            # tells an offset at EOF from one past a truncated member.
            handle.seek(offset - 1)
            if not handle.read(1):
                raise _Discontinuity(
                    f"truncated: segment {path.name} is shorter than checkpoint {offset}")
        else:
            handle.seek(offset)
        position = offset
        buffer = bytearray()
        discarding = False
        while True:
            chunk = handle.read(256 * 1024)
            if not chunk:
                break
            start = 0
            while True:
                newline = chunk.find(b"\n", start)
                if newline < 0:
                    if not discarding:
                        _append_prefix(buffer, chunk[start:], limit)
                        discarding = len(buffer) >= limit
                    position += len(chunk) - start
                    break
                position += newline - start + 1
                if not discarding:
                    _append_prefix(buffer, chunk[start:newline], limit)
                yield bytes(buffer), position
                buffer.clear()
                discarding = False
                start = newline + 1


def _append_prefix(buffer, chunk, limit):
    """Append at most what fits in `limit`, so an overlong line never grows the buffer."""
    room = limit - len(buffer)
    if room > 0:
        buffer += chunk[:room]


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


def _trailing_bytes(path, compressed, position):
    """The first bytes after the last complete line, or b'' when the segment ends on a newline."""
    if compressed:
        skip = position
        with gzip.open(path, "rb") as handle:
            while skip > 0:
                chunk = handle.read(min(skip, 256 * 1024))
                if not chunk:
                    return b""
                skip -= len(chunk)
            return handle.read(_EXCERPT_BYTES)
    try:
        if os.stat(path).st_size <= position:
            return b""
        with open(path, "rb") as handle:
            handle.seek(position)
            return handle.read(_EXCERPT_BYTES)
    except OSError:
        return b""


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
    """The enabled adapters for this configuration (architecture §6, §7)."""
    from fleetglint.adapters.claude_code import ClaudeCodeAdapter
    from fleetglint.adapters.codex import CodexAdapter
    from fleetglint.adapters.harness import HarnessAdapter

    candidates = (
        (cfg.harness.enabled, lambda: HarnessAdapter(cfg.harness.state_dir)),
        (cfg.claude_code.enabled, lambda: ClaudeCodeAdapter(cfg.claude_code.dir)),
        (cfg.codex.enabled, lambda: CodexAdapter(cfg.codex.dir)),
    )
    adapters = []
    for enabled, build in candidates:
        if enabled == "false":
            continue
        adapter = build()
        if enabled == "true":
            adapters.append(adapter)
            continue
        try:
            available = adapter.available()
        except OSError:
            available = False
        if available:
            adapters.append(adapter)
    return tuple(adapters)


def rebuild(cfg, adapters=()):
    """Delete the database and ingest everything retained again."""
    with hold_service_lock(cfg, blocking=False):
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
    except ServiceLockBusy as exc:
        print(str(exc), file=sys.stderr)
        return 3
    except ImportError as exc:
        print(f"fleetglint: record validator unavailable ({exc}); "
              "fleetglint.schema is missing or incomplete", file=sys.stderr)
        return 3
    except (config.ConfigError, OSError, sqlite3.Error) as exc:
        print(f"fleetglint: {exc}", file=sys.stderr)
        return 3


def _run_ingest(cfg, once):
    if once:
        with hold_service_lock(cfg, blocking=False):
            return _ingest_once(cfg)
    with hold_service_lock(cfg):
        return _ingest_loop(cfg)


def serve(cfg, stop_event, lock=None):
    """The long-running ingest loop of `fleetglint serve` (architecture §8).

    With `lock`, take ownership of a handle from `acquire_service_lock` and close it
    when the loop ends; this leaves no gap between the server's check and the thread.
    """
    if lock is None:
        lock = acquire_service_lock(cfg)
    try:
        conn = store.open_db(cfg.db_path)
        try:
            ingestor = Ingestor(conn, cfg, adapters=default_adapters(cfg))
            return _loop(ingestor, cfg, stop_event)
        finally:
            conn.close()
    finally:
        release_service_lock(lock)


def _ingest_once(cfg):
    conn = store.open_db(cfg.db_path)
    try:
        ingestor = Ingestor(conn, cfg, adapters=default_adapters(cfg))
        ingestor.scan_roots()
        ingestor.scan_adapters()
        ingestor.apply_retention()
        _print_summary(conn)
        return 0
    finally:
        conn.close()


def _ingest_loop(cfg):
    conn = store.open_db(cfg.db_path)
    try:
        ingestor = Ingestor(conn, cfg, adapters=default_adapters(cfg))
        return _loop(ingestor, cfg)
    finally:
        conn.close()


def _loop(ingestor, cfg, stop_event=None):
    """Scan roots and adapters on their intervals, retain hourly, stop on Ctrl-C or `stop_event`."""
    # Scan first, then retain: retention verifies files against what the scan ingested.
    next_roots = next_adapters = next_retention = 0.0
    try:
        while stop_event is None or not stop_event.is_set():
            now = time.monotonic()
            if now >= next_roots:
                _pass(ingestor.scan_roots)
                next_roots = now + cfg.poll_s
            if now >= next_adapters:
                _pass(ingestor.scan_adapters)
                next_adapters = now + cfg.adapter_poll_s
            if now >= next_retention:
                _pass(ingestor.apply_retention)
                next_retention = now + 3600
            wake = min(next_roots, next_adapters, next_retention) - time.monotonic()
            wake = max(0.0, min(1.0, wake))
            if stop_event is None:
                time.sleep(wake)
            else:
                stop_event.wait(wake)
    except KeyboardInterrupt:
        return 0
    return 0


def _pass(step):
    """One scan or retention pass; a failure is reported and the loop carries on (architecture §5.1)."""
    try:
        step()
    except Exception:  # noqa: BLE001 - the loop must survive one bad pass
        traceback.print_exc()


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
    with hold_service_lock(cfg, blocking=False):
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
