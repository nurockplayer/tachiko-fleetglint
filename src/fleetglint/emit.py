"""`fleetglint emit`: validate one record from stdin and append it (docs/spec.md §6.3)."""
import contextlib
import fcntl
import json
import os
import re
import sys
from pathlib import Path

from fleetglint import config, schema

MAX_RECORD_BYTES = 65536
SEGMENT_LIMIT = 16 * 1024 * 1024
SEGMENT = re.compile(r"^(\d{10})\.ndjson$")
SEGMENT_GZ = re.compile(r"^(\d{10})\.ndjson\.gz$")


def append_record(record, root):
    """Append one validated record to its source's current segment; return the segment path."""
    line = json.dumps(record, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n"
    directory = Path(root) / record["source_id"]
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    data = line.encode("utf-8")
    if len(data) > MAX_RECORD_BYTES:
        raise ValueError(f"record line is larger than {MAX_RECORD_BYTES} bytes")
    remaining = memoryview(data)
    with _locked(directory / ".lock"):
        segment = _current_segment(directory)
        if segment.exists() and segment.stat().st_size >= SEGMENT_LIMIT:
            segment = _next_segment(directory)
        fd = os.open(segment, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            while remaining:
                written = os.write(fd, remaining)
                if written <= 0:
                    raise OSError("short write")
                remaining = remaining[written:]
        finally:
            os.close(fd)
    return segment


def run(args):
    record, problem = _read_record()
    if problem:
        print(f"fleetglint emit: {problem}", file=sys.stderr)
        return 1
    if args.source_id:
        if "source_id" not in record:
            record["source_id"] = args.source_id
        elif record["source_id"] != args.source_id:
            print(f"fleetglint emit: source_id {record['source_id']!r} does not match "
                  f"{args.source_id!r}", file=sys.stderr)
            return 1
    errors = schema.validate(record)
    if errors:
        for message in errors:
            print(f"fleetglint emit: {message}", file=sys.stderr)
        return 1
    try:
        root = config.expand(args.root) if args.root else config.load(args.config).roots[0]
        append_record(record, root)
    except ValueError as exc:
        print(f"fleetglint emit: {exc}", file=sys.stderr)
        return 1
    except (OSError, config.ConfigError) as exc:
        print(f"fleetglint emit: {exc}", file=sys.stderr)
        return 3
    return 0


def _read_record():
    data = sys.stdin.buffer.read(MAX_RECORD_BYTES + 1)
    if len(data) > MAX_RECORD_BYTES:
        return None, f"record is larger than {MAX_RECORD_BYTES} bytes"
    try:
        record = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, f"invalid JSON: {exc}"
    if not isinstance(record, dict):
        return None, "record must be a JSON object"
    return record, None


@contextlib.contextmanager
def _locked(path):
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def _seqs(directory):
    plain, gz = [], []
    for entry in directory.iterdir():
        match = SEGMENT.match(entry.name)
        if match:
            plain.append(int(match.group(1)))
            continue
        match = SEGMENT_GZ.match(entry.name)
        if match:
            gz.append(int(match.group(1)))
    return plain, gz


def _next_segment(directory):
    plain, gz = _seqs(directory)
    seq = max(plain + gz, default=0) + 1
    return directory / f"{seq:010d}.ndjson"


def _current_segment(directory):
    """The highest seq if it is still plain; a compressed or missing highest seq means start the next one."""
    plain, gz = _seqs(directory)
    if plain and max(plain) > max(gz, default=0):
        return directory / f"{max(plain):010d}.ndjson"
    return _next_segment(directory)
