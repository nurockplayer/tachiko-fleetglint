"""`fleetglint doctor`: check paths, adapters and source health (architecture §8)."""
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from fleetglint import RECORD_FORMAT_VERSION, __version__, config, store
from fleetglint.adapters.claude_code import ClaudeCodeAdapter
from fleetglint.adapters.codex import CodexAdapter
from fleetglint.adapters.harness import HarnessAdapter

HEALTH_TIMEOUT_S = 1.0


def run(args, now=None):
    """Print the report; return 0 when nothing is wrong, 1 otherwise."""
    now = now or datetime.now().astimezone()
    path = config.expand(args.config) if args.config else config.config_path()
    try:
        cfg = config.load(path)
    except config.ConfigError as exc:
        print(f"fleetglint doctor: {exc}", file=sys.stderr)
        return 1
    problems = report(cfg, path, now)
    return 1 if problems else 0


def report(cfg, config_file, now, out=None):
    """Print every section and return the list of problems found."""
    out = out or sys.stdout
    print(f"fleetglint {__version__} (record format v{RECORD_FORMAT_VERSION}), "
          f"Python {sys.version.split()[0]}", file=out)
    print(f"config: {config_file} "
          f"({'exists' if config_file.exists() else 'defaults'})", file=out)
    problems = []
    problems += _check_paths(cfg, out)
    problems += _check_adapters(cfg, now, out)
    problems += _check_sources(cfg, out)
    _check_server(cfg, out)
    _print_privacy(cfg, out)
    print(file=out)
    if problems:
        print(f"{len(problems)} problem(s) found:", file=out)
        for problem in problems:
            print(f"  - {problem}", file=out)
    else:
        print("no problems found", file=out)
    return problems


def _check_paths(cfg, out):
    problems = []
    state = config.state_dir()
    if state.exists():
        writable = os.access(state, os.W_OK)
        print(f"state dir: {state} ({'writable' if writable else 'NOT writable'})", file=out)
        if not writable:
            problems.append(f"state dir {state} is not writable")
    else:
        print(f"state dir: {state} (not created yet; created on first write)", file=out)

    if cfg.db_path.exists():
        print(f"db: {cfg.db_path} ({_human_size(cfg.db_path.stat().st_size)})", file=out)
    else:
        print(f"db: {cfg.db_path} (not created yet: run fleetglint serve)", file=out)

    for root in cfg.roots:
        try:
            if not root.exists():
                print(f"NDJSON root: {root} (missing; created on first write)", file=out)
                continue
            count = sum(1 for entry in root.iterdir() if entry.is_dir() and not entry.name.startswith("."))
            writable = os.access(root, os.W_OK)
            print(f"NDJSON root: {root} ({count} source dir(s), "
                  f"{'writable' if writable else 'NOT writable'})", file=out)
            if not writable:
                problems.append(f"NDJSON root {root} is not writable")
        except OSError as exc:
            print(f"NDJSON root: {root} (cannot read: {exc})", file=out)
            problems.append(f"NDJSON root {root}: {exc}")
    return problems


def _adapter_specs(cfg):
    return (
        ("tachiko-harness", cfg.harness.enabled, cfg.harness.state_dir,
         HarnessAdapter(cfg.harness.state_dir)),
        ("claude-code", cfg.claude_code.enabled, cfg.claude_code.dir,
         ClaudeCodeAdapter(cfg.claude_code.dir)),
        ("codex-cli", cfg.codex.enabled, cfg.codex.dir, CodexAdapter(cfg.codex.dir)),
    )


def _check_adapters(cfg, now, out):
    problems = []
    for name, enabled, directory, adapter in _adapter_specs(cfg):
        print(f"adapter {name} (enabled: {enabled})", file=out)
        if enabled == "false":
            print("  disabled by configuration", file=out)
            continue
        try:
            available = adapter.available()
        except OSError as exc:
            print(f"  cannot check {directory}: {exc}", file=out)
            problems.append(f"adapter {name}: cannot check {directory}: {exc}")
            continue
        if not available:
            if enabled == "true":
                print(f"  NOT PRESENT {directory} (enabled = true)", file=out)
                problems.append(f"adapter {name}: enabled but {directory} is not present")
            else:
                print(f"  not present ({directory}); auto-enabled when it exists", file=out)
            continue
        started = time.perf_counter()
        try:
            result = adapter.scan(now)
        except OSError as exc:
            print(f"  scan failed: {exc}", file=out)
            problems.append(f"adapter {name}: scan failed: {exc}")
            continue
        elapsed_ms = (time.perf_counter() - started) * 1000
        if result.status != "ok":
            print(f"  unavailable: {result.detail or 'no detail'}", file=out)
            problems.append(f"adapter {name}: {result.detail or 'unavailable'}")
            continue
        print(f"  scan: {len(result.records)} record(s) in {elapsed_ms:.0f} ms", file=out)
        print(f"  {_summarise(result.records)}", file=out)
        if result.detail:
            print(f"  detail: {result.detail}", file=out)
    return problems


def _summarise(records):
    """`run: 5 (running 2, done 3); job: 1` for one scan's records."""
    by_type = {}
    for record in records:
        states = by_type.setdefault(record.get("type"), {})
        state = record.get("state")
        states[state] = states.get(state, 0) + 1
    parts = []
    for record_type in sorted(by_type, key=str):
        states = by_type[record_type]
        detail = ", ".join(f"{state} {count}" for state, count in sorted(states.items(), key=str))
        parts.append(f"{record_type}: {sum(states.values())} ({detail})")
    return "; ".join(parts) or "no records"


def _check_sources(cfg, out):
    if not cfg.db_path.exists():
        print("sources: no database yet", file=out)
        return []
    try:
        conn = store.open_db(cfg.db_path, readonly=True)
    except (sqlite3.Error, OSError) as exc:
        print(f"sources: cannot read {cfg.db_path}: {exc}", file=out)
        return [f"db {cfg.db_path}: {exc}"]
    try:
        rows = store.source_stats(conn)
    except sqlite3.Error as exc:
        print(f"sources: cannot read {cfg.db_path}: {exc}", file=out)
        return [f"db {cfg.db_path}: {exc}"]
    finally:
        conn.close()
    if not rows:
        print("sources: none ingested yet", file=out)
        return []
    print(f"sources from {cfg.db_path}:", file=out)
    problems = []
    for row in rows:
        print(f"  {row['source_id']}  {row['kind']}  {row['status']}  "
              f"{row['records']} record(s), {row['quarantine']} quarantined, "
              f"last {row['last_record_at'] or '-'}", file=out)
        if row["status"] != "ok":
            detail = f": {row['detail']}" if row["detail"] else ""
            problems.append(f"source {row['source_id']} is {row['status']}{detail}; "
                            f"fix: fleetglint source reset {row['source_id']}")
    return problems


def _check_server(cfg, out):
    url = f"http://127.0.0.1:{cfg.port}/api/healthz"
    try:
        with urllib.request.urlopen(url, timeout=HEALTH_TIMEOUT_S) as response:
            body = json.loads(response.read(1024))
    except (OSError, ValueError):
        print(f"server: not running on http://127.0.0.1:{cfg.port} (informational)", file=out)
        return
    if isinstance(body, dict) and body.get("ok") is True:
        print(f"server: running on http://127.0.0.1:{cfg.port} "
              f"(healthz ok, version {body.get('version')})", file=out)
    else:
        print(f"server: something answers on http://127.0.0.1:{cfg.port} "
              f"but it is not fleetglint", file=out)


def _print_privacy(cfg, out):
    directories = ", ".join(
        str(directory) for _, enabled, directory, _ in _adapter_specs(cfg)
        if enabled != "false") or "none"
    print(f"privacy: adapters read {directories}; only metadata (ids, times, models, counts) "
          f"is stored, never prompts, tool output or transcript paths", file=out)


def _human_size(size):
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024 or unit == "GiB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} GiB"
