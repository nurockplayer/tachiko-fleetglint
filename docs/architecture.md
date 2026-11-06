# Fleetglint architecture (v0.1)

Status: draft (2026-11-06). This is the implementation contract for v0.1.
The record format itself is [spec.md](spec.md); the UI's meaning is
[design/brief.md](design/brief.md). Where this file and the spec disagree,
the spec wins and this file is fixed.

## 1. Shape

```
writers / emitters ──► NDJSON segments ─┐
tachiko-harness files ──► adapter ──────┤
Claude Code transcripts ─► adapter ─────┤
Codex rollouts ──► adapter ─────────────┼─► ingest ──► SQLite read model ──► query ──► HTTP API ──► web UI
                                        ┘     (one writer thread)              (GET only, 127.0.0.1)
```

One process, `fleetglint serve`: an HTTP server plus one background ingest
thread. Nothing else runs; there is no daemon besides this one, no network
access beyond the loopback listener, no child process started because of a
record.

## 2. Runtime and packaging

- Python **≥ 3.11**, **standard library only** at runtime (`sqlite3`,
  `http.server`, `tomllib`, `json`, `ctypes`). No third-party runtime
  dependency, so Homebrew and pipx installs have nothing to resolve.
- `pyproject.toml` with the `setuptools` build backend, src layout:
  `src/fleetglint/`. Console script `fleetglint = fleetglint.cli:main`;
  `python -m fleetglint` works too.
- The web UI source lives in `ui/` (React + Vite + TypeScript, pnpm). Its
  build output is copied into `src/fleetglint/web/` (gitignored) and shipped
  as package data. No Node at runtime.
- Release artefacts (GitHub Release, built by CI): an sdist and a wheel that
  both contain the built UI. Install paths for v0.1:
  - `brew install nurockplayer/fleetglint/fleetglint` (tap
    `nurockplayer/homebrew-fleetglint`, formula installs the sdist into a
    virtualenv); `brew services start fleetglint` runs `fleetglint serve`
    under launchd.
  - `pipx install https://github.com/nurockplayer/tachiko-fleetglint/releases/download/v0.1.0/fleetglint-0.1.0-py3-none-any.whl`
    (the release wheel, because a plain `git+https` install has no built UI).
  - No PyPI in v0.1.
- A checkout without built UI still runs: `/` serves a short page that says
  the UI is not built and how to build it (`pnpm -C ui build`); the API
  works.

## 3. Package layout

| Module | Owns | Depends on |
|---|---|---|
| `cli.py` | argparse entry point and subcommands (§8) | everything below |
| `config.py` | config file, defaults, paths (§7) | — |
| `schema.py` | stdlib validator for v1 records; returns error list | `data/record.schema.json` (package data copy of `schema/v1/`, a test keeps them equal) |
| `redact.py` | redaction of strings (port of tachiko-harness `share/redact.py`, same author) | — |
| `emit.py` | `fleetglint emit`: validate one record and append it per spec §6.3 | `schema`, `config` |
| `store.py` | SQLite connection, migrations, all SQL (§5) | — |
| `ingest.py` | segment scanning, checkpoints, quarantine, discontinuity, retention, rebuild (spec §7) | `schema`, `store` |
| `liveness.py` | display state and evidence (spec §8), process checks | — |
| `adapters/base.py` | adapter interface (§6) | — |
| `adapters/harness.py` | tachiko-harness adapter (§6.1) | `base` |
| `adapters/claude_code.py` | Claude Code transcript importer (§6.2) | `base` |
| `adapters/codex.py` | Codex rollout importer (§6.3) | `base` |
| `hooks.py` | `fleetglint hooks install/uninstall claude` (§6.4) | `emit` |
| `demo.py` | `fleetglint demo`: a separate, labelled sample source (§8.1) | `emit` |
| `query.py` | builds the API JSON (§4) from the store | `store`, `liveness`, `redact` |
| `files.py` | safe bounded reads of `log_path` / `result_path` / link `path` (spec §9) | `redact`, `config` |
| `server.py` | HTTP server, routing, safety headers, ETag, static files | `query`, `files` |
| `web/` | built UI (package data, not in git) | — |

Every module that needs "now" takes it as a parameter (or a `clock`
callable) so tests control time.

## 4. HTTP API

All endpoints are `GET`, under `http://127.0.0.1:<port>`, return
`application/json; charset=utf-8` (except static files) and carry the safety
headers in §4.5. Ids travel as query parameters because `id` may contain `/`.

### 4.1 `GET /api/snapshot`

The whole board in one response. The UI polls it every 3 s with
`If-None-Match`.

```json
{
  "api": 1,
  "generated_at": "2026-11-06T03:40:00+09:00",
  "server": {"version": "0.1.0", "host": "mbp", "read_only": true},
  "window_hours": 24,
  "sources": [
    {"source_id": "tachiko-harness@mbp", "kind": "adapter", "status": "ok",
     "detail": null, "last_scan_at": "…", "last_record_at": "…",
     "quarantine_count": 0, "records": 42}
  ],
  "counts": {"running": 3, "waiting": 1, "attention": 4, "stale_lost_unknown": 2,
             "sessions_recent": 5},
  "runs": [RunSummary, …],
  "jobs": [JobSummary, …],
  "inbox": [InboxSummary, …],
  "sessions": [SessionSummary, …],
  "attention": [AttentionEntry, …],
  "truncated": {"runs": false, "jobs": false, "inbox": false, "sessions": false},
  "demo": false
}
```

- `sources[].kind`: `ndjson` or `adapter`. `status`: `ok`,
  `discontinuity`, `unavailable`. `detail`: human text for a non-`ok`
  status (redacted), else `null`.
- Included records: every non-terminal run and job, every open inbox item,
  and terminal runs/jobs and acked items whose `updated_at` is within
  `window_hours` (config, default 24). At most 500 per list, newest
  `updated_at` first; `truncated` says if a list was cut.
- Sessions (spec §4.4): every session whose `last_activity_at` is within
  `window_hours`, at most 500, newest activity first.
- `counts.attention` is `len(attention)`. `counts.sessions_recent` counts
  sessions whose display state is `recent`; sessions never count as
  running.
- `demo` is `true` when any included record comes from a demo source
  (§8.1); the UI then shows a permanent DEMO DATA banner.

**Common summary fields** (every RunSummary, JobSummary, InboxSummary):

```json
{"ref": {"type": "run", "id": "cx.20552", "source_id": "tachiko-harness@mbp"},
 "state": "running", "display_state": "stale",
 "evidence": {"kind": "observed", "age_s": 2520, "detail": null},
 "updated_at": "…", "observed_at": "…", "project": "gteki", "title": "…",
 "links": [{"label": "worker log", "path": "/…", "readable": true}]}
```

- `ref` always has all three fields (resolved defaults).
- `display_state`: one of `queued running waiting done failed cancelled
  stale lost unknown open acked recent idle ended` (spec §8.1, §8.3).
- `evidence.kind`: `process` (a process check matched), `process_gone`
  (it did not: gives `lost`), `observed` (writer refresh within
  `stale_after_s`), `expired` (gives `stale`), `terminal`, `writer_unknown`,
  `source_problem` (discontinuity or unavailable). `age_s` = seconds since
  `observed_at` (integer, ≥ 0), `null` for terminal records.
- Links with a `path` carry `readable` (would `files.py` open it); the UI
  fetches the content only through `/api/file`.

**RunSummary** adds: `agent`, `model`, `provider`, `effort`, `role_id`,
`session_id`, `started_at`, `ended_at`, `exit_code`, `summary` (redacted,
first 300 chars), `parent_run`, `resume_of` (Ref or `null`), `waits_on`
(list of Ref), each record Ref extended with `"resolved": true|false` and,
when resolved, `"display_state"` and `"title"`.

**JobSummary** adds: `kind`, `command_summary` (redacted), `run` (Ref or
`null`, extended as above), `role_id`, `started_at`, `ended_at`,
`exit_code`, `signal`, `summary` (redacted, 300 chars), `log` and `result`
(`{"path": "…", "readable": bool}` or `null`).

**InboxSummary** adds: `role_id`, `kind`, `subject` (Ref, extended),
`outcome`, `action_required`, `created_at`, `acked_at`, `detail` (redacted,
first 300 chars), `blocks_retention` (bool, spec §7.5).

**SessionSummary** adds: `agent`, `model`, `models`, `provider`, `effort`,
`role_id`, `started_at`, `last_activity_at`, `ended_at`, `turn_open`,
`entries`, `parent_session` (Ref, extended, or `null`), `usage`. Its
`evidence.kind` is `activity` (`age_s` = seconds since `last_activity_at`)
or `terminal` / `source_problem`.

External refs are passed through as written (`type`, `kind`, `key`,
`url`); `resolved` is absent for them.

**AttentionEntry**, in this order (brief §6.3): open inbox items with
`action_required`, other open inbox items, `lost` runs/jobs, `stale` and
`unknown` runs/jobs, source problems.

```json
{"reason": "action_required" | "inbox" | "lost" | "stale" | "unknown" | "source",
 "who": "fleetglint-lead" | null,
 "subject": Ref | null,
 "source_id": "…",
 "text": "short line for the row"}
```

`who` is the inbox item's `role_id`; for a run/job it is its `role_id`, else
the owning run's `role_id`, else `null`.

### 4.1b `GET /api/board`

The viewer's first screen: a small answer organised by what the viewer asks,
instead of one list per record type. Same safety, ETag and redaction rules as
§4.5; the empty-database response has the same shape with empty lists and
zeros. `[ui]` settings: `viewer_roles` (default `["owner"]`),
`needs_you_hours` (24) and `inbox_old_after_s` (7200).

```json
{
  "api": 1, "generated_at": "…", "server": {…}, "window_hours": 24,
  "demo": false, "sources": [Source, …],
  "capabilities": {"execution": true, "requests": true},
  "counts": {"needs_you": 1, "waiting": 2, "running": 3, "lead_inbox_open": 4,
             "lead_inbox_old": 1, "process_gone": 0, "out_of_date": 1,
             "unverified_recent": 0, "failed_recent": 1, "older_unverified": 2,
             "sessions_recent": 3},
  "needs_you": [InboxSummary + "age_s", …],
  "lead_inbox": [{"role_id": "fleetglint-lead", "open": 3, "old": 1,
                  "oldest_age_s": 9000, "action_required": 2,
                  "items": [InboxSummary + "age_s", … newest 5]}],
  "waiting": [WorkSummary, …], "running": [WorkSummary, …],
  "exceptions": {"process_gone": [WorkSummary, …], "out_of_date": [WorkSummary, …],
                 "unverified_recent": [WorkSummary, …]},
  "recent": [WorkSummary, …],
  "sessions": [SessionSummary, …], "sessions_total": 12,
  "truncated": {"waiting": false, "running": false, "exceptions": false,
                "recent": false, "lead_inbox": false}
}
```

`InboxSummary` and `SessionSummary` are §4.1's; `age_s` is seconds since
`created_at` (null when absent). `WorkSummary` is a RunSummary or JobSummary
plus `started_age_s` (seconds since `started_at`, null when absent) and
`section_reason` (`waits_on` or `lead_wait`, else null). `capabilities` is
false when the store has no run/job (resp. inbox) row at all, so the UI can
say "not observable" instead of 0. Lists are capped at 200 (exceptions 50
each, `recent` 20, `sessions` 30); counts reflect the full set.

Each run or job lands in exactly one place, in this order; `older` means
`updated_ts` before `now - window_hours`.

1. An open inbox item with `action_required` and a `role_id` in
   `viewer_roles` is `needs_you` when `created_at` is within
   `needs_you_hours`, otherwise dropped (no acknowledged state exists).
2. Other open inbox items group by `role_id` in `lead_inbox`; `old` counts
   items older than `inbox_old_after_s`. Roles sort by `action_required`
   count, then oldest first.
3. Display `waiting`: `waiting`, `section_reason: "waits_on"`.
4. A job in display `running` with kind `wait`: `waiting`,
   `section_reason: "lead_wait"`.
5. A job in display `running` with kind `wait-worker` is hidden (no list, no
   count) when a run in display running or waiting has the same `role_id` and
   started no earlier; otherwise `waiting`, `section_reason: "lead_wait"`.
6. Display `running`: `running`, newest `started_at` first, nulls last.
7. Display `lost` / `stale`: `exceptions.process_gone` / `out_of_date` when
   not `older`; when `older`, only `counts.older_unverified`.
8. Display `unknown`: not `older` goes to `exceptions.unverified_recent`;
   `older` only counts into `older_unverified`, without building a summary.
9. Display `failed`, `done` or `cancelled` and not `older`: `recent` (`failed`
   also counts into `failed_recent`); `wait-worker` jobs are skipped; older
   terminal rows are skipped entirely.
10. Sessions within the window, as §4.1; `sessions_total` counts them all,
    `sessions_recent` is §4.1's recent count.

`/api/snapshot` attention follows rule 7/8's window: `lost`, `stale` and
`unknown` rows older than the window (and `counts.stale_lost_unknown`) are
dropped there too.

### 4.2 `GET /api/record?source_id=…&type=run|job|inbox_item&id=…`

One record in full, for Run detail (and job / inbox detail).

```json
{
  "api": 1, "generated_at": "…",
  "record": RunSummary | JobSummary | InboxSummary,
  "full": {…},                 // the latest record as written, redacted (raw view)
  "relations": {
    "parent": Ref | null,      // this run's parent_run
    "resume_of": Ref | null,   // the run this run continues
    "children": [Ref, …],      // runs whose parent_run is this run
    "resumed_by": [Ref, …],    // runs whose resume_of is this run
    "jobs": [Ref, …],          // jobs whose run is this run
    "inbox": [Ref, …],         // inbox items whose subject is this record
    "waited_on_by": [Ref, …]   // runs whose waits_on contains this record
  },
  "history": [{"seq": 2, "byte_offset": 1832, "updated_at": "…", "state": "running"}, …],
  "usage": {…} | null
}
```

All Refs in `relations` are extended Refs (§4.1). For a job or inbox item
the run-only keys are `null` / empty. `history` is at most the last 50
versions, newest first. 404 with an error body if the record is unknown.

### 4.3 `GET /api/file?source_id=…&type=…&id=…&field=log_path|result_path|link&index=N`

Tail of a file the record points at, read under the spec §9 rules by
`files.py`. The client never sends a path; the server looks the path up in
the record. Response:

```json
{"api": 1, "readable": true, "path": "/…", "size": 81234, "truncated": true,
 "text": "…last 64 KiB, redacted…", "redactions": 2}
```

or `{"api": 1, "readable": false, "reason": "outside_allowed_roots" |
"not_regular_file" | "missing" | "not_utf8" | "no_path"}`. Never 5xx for a
bad path.

### 4.4 Other endpoints

- `GET /api/sources/<source_id>/quarantine` → last 100 quarantined lines
  (position, reason, redacted excerpt).
- `GET /api/healthz` → `{"ok": true, "version": "0.1.0"}`.
- `GET /` and static assets from `web/`; unknown non-`/api` paths serve
  `index.html` (client-side routes `/`, `/attention`, `/run/...`).

### 4.5 Rules for every response (spec §9)

- Bind `127.0.0.1` only; the server refuses to start with any other host.
- Methods other than `GET`/`HEAD` → 405. A request whose `Host` header is not
  `127.0.0.1:<port>` or `localhost:<port>` → 421 (DNS rebinding guard).
- Headers: `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`,
  `Content-Security-Policy: default-src 'self'; img-src 'self' data:;
  style-src 'self' 'unsafe-inline'; frame-ancestors 'none'`. No CORS
  headers ever.
- ETag on `/api/snapshot` and `/api/record`: a weak tag over the store's
  change counter and `floor(now / 5 s)` (display states depend on time);
  `If-None-Match` match → 304.
- Errors: `{"api": 1, "error": {"code": "…", "message": "…"}}` with a 4xx/5xx
  status. The UI treats any failure (network, non-2xx/304, bad JSON) as
  **Unavailable** and never shows the last snapshot as current (it may show
  it greyed out under the Unavailable banner, labelled with its time).
- Request handling is bounded: no request body is read, query strings over
  2 KiB → 414.

## 5. SQLite read model

File: `$XDG_STATE_HOME/fleetglint/fleetglint.sqlite` (WAL, `synchronous =
NORMAL`, `foreign_keys = ON`). Schema version in `PRAGMA user_version`;
migrations are forward-only functions in `store.py`. The database is
disposable (spec §1.5): `fleetglint rebuild` deletes and replays.

Writers: only the ingest thread writes. The HTTP threads open read-only
connections (`mode=ro` URI) per request.

```sql
sources(source_id TEXT PRIMARY KEY, kind TEXT NOT NULL,          -- ndjson | adapter
        root TEXT, status TEXT NOT NULL DEFAULT 'ok', detail TEXT,
        discontinuity_at TEXT, last_scan_at TEXT, last_record_at TEXT)
segments(source_id TEXT, seq INTEGER, length INTEGER, fingerprint TEXT,
         inode INTEGER, closed INTEGER NOT NULL, compressed INTEGER NOT NULL DEFAULT 0,
         PRIMARY KEY(source_id, seq))
checkpoints(source_id TEXT PRIMARY KEY, seq INTEGER NOT NULL, byte_offset INTEGER NOT NULL)
records(source_id TEXT, type TEXT, id TEXT,                     -- latest record per identity
        seq INTEGER NOT NULL, byte_offset INTEGER NOT NULL,
        state TEXT NOT NULL, updated_at TEXT NOT NULL, updated_ts REAL NOT NULL,
        observed_ts REAL NOT NULL, stale_after_s INTEGER,
        role_id TEXT, project TEXT, json TEXT NOT NULL,
        PRIMARY KEY(source_id, type, id))
history(source_id TEXT, seq INTEGER, byte_offset INTEGER,
        type TEXT, id TEXT, state TEXT, updated_at TEXT, updated_ts REAL, json TEXT,
        ingested_ts REAL, PRIMARY KEY(source_id, seq, byte_offset))
refs(from_source TEXT, from_type TEXT, from_id TEXT,
     rel TEXT,                                                  -- parent_run | resume_of | waits_on | job_run | subject
     to_type TEXT, to_source TEXT, to_id TEXT,                  -- record refs
     ext_kind TEXT, ext_key TEXT, ext_url TEXT)                 -- external refs
quarantine(qid INTEGER PRIMARY KEY, source_id TEXT, seq INTEGER, byte_offset INTEGER,
           reason TEXT, detail TEXT, excerpt TEXT, at TEXT)
meta(key TEXT PRIMARY KEY, value TEXT)                          -- change counter, last rebuild
```

- Indexes: `records(type, state)`, `records(updated_ts)`,
  `refs(to_source, to_type, to_id)`, `refs(from_source, from_type, from_id)`,
  `history(source_id, type, id, seq, byte_offset)`.
- `refs` rows for a record are deleted and re-inserted whenever its latest
  version changes. Timestamps are stored as written (`*_at`) and as epoch
  seconds (`*_ts`) for comparisons.
- Adapter records use `seq = 0` (segments start at 1) and `byte_offset` = a
  per-source counter stored in `checkpoints`, so the history key stays
  unique and ordering stays "the order the adapter produced them".
- `meta.change_counter` increments in every committing transaction; the
  ETag uses it.

### 5.1 Ingest loop

Every `poll_s` (default 2 s) the ingest thread, for each NDJSON root:
lists source directories, stats segments, and for any source whose current
segment grew (or whose segment set changed) runs spec §7.3 for the new bytes,
batch size at most 1000 lines or 4 MiB per transaction. Discontinuities per
spec §7.4 set `sources.status = 'discontinuity'` and stop ingesting that
source until `fleetglint source reset <id>` (acknowledge and rebuild that
source from its remaining segments). Every `adapter_poll_s` (default 5 s)
it runs each enabled adapter (§6). Retention (spec §7.5) runs once an hour
and at start.

`.gz` segments: read with `gzip`; a fully ingested `.ndjson` that becomes
`.ndjson.gz` is checked once against the stored length and fingerprint
(SHA-256 of the content).

## 6. Adapters

```python
class Adapter(Protocol):
    source_id: str                       # e.g. "tachiko-harness@<hostname -s>"
    allowed_roots: list[Path]            # dirs whose files its records may point at (spec §9)
    def available(self) -> bool: ...     # is the tool present on this machine
    def scan(self, now: datetime) -> ScanResult: ...

@dataclass
class ScanResult:
    status: Literal["ok", "unavailable"]
    detail: str | None                   # why unavailable, short
    records: list[dict]                  # full v1 records, complete current state of everything it sees
```

The adapter is pure: it reads its inputs and returns full records; it
never writes anywhere. `ingest.py` validates each record with
`schema.py` (failures go to quarantine like NDJSON lines), compares it to
the stored latest version (`json` equality after dropping
`observed_at`-only changes from history, see below), and upserts only
changes, in one transaction per scan. A record the adapter no longer
returns is left as it is (no inference); the adapter itself must emit the
terminal or `unknown` state when it can tell.

Observation refreshes (same record, only `observed_at` changed) update
`records` but do not add a history row.

Adapters for other tools' history files (§6.2, §6.3) must also:
- read incrementally: remember per file `(inode, size, mtime, offset)` in
  memory and in `meta` so a rescan of an unchanged file costs one `stat`;
  re-read a file from the start when it shrank or its inode changed;
- copy **metadata only** into records (ids, times, model names, counts,
  token usage); never prompts, model output, tool input/output, file
  contents or full commands (spec §4.4);
- skip a line they cannot parse (count it in `detail`), never fail the scan;
- not add their history directories to `allowed_roots`: transcripts are
  never served through `/api/file`.

### 6.1 tachiko-harness adapter (`adapters/harness.py`)

Read-only over `~/.local/state` (configurable `state_dir`); enabled
automatically when `<state_dir>/worker-ledger/runs.tsv` exists. Sources
(file formats: read them on a real machine and in the fixtures):

- `worker-ledger/runs.tsv` (finished worker runs) and
  `worker-ledger/running/<tool>.<pid>` (live ones) → `run` records.
  Identity `<tool>.<pid>` (e.g. `cx.22194`) plus the start epoch where
  needed to keep pids unique over time. `process = {host, pid,
  start_time}` for live ones so §8.2 checks liveness. Model, project,
  worker, lead pane, log path from the columns.
- `job-run/<name>/` (`cmd`, `cwd`, `log`, `pid`, `result.json`) → `job`
  records; `command_summary` = first word of `cmd` + at most the next two
  arguments, never the full argv.
- `lead-wait/<role>/<job id>` markers → `job` records of kind `wait` with
  `role_id = <role>`.
- `lead-inbox/<role>.tsv` → `inbox_item` records (`id`, `time` →
  `created_at`, `kind`, `ref` → external or record ref only when it is
  unambiguous, `state`/`detail`, `acked` → `acked_at`).
- Times like `2026-11-05 06:10 JST` are parsed with their zone; a time
  without a zone is not guessed: the field is left out (or the record goes
  to quarantine if the field is required).
- No links between records unless a file states them (spec §1.3).

### 6.2 Claude Code transcripts (`adapters/claude_code.py`)

Source id `claude-code@<hostname -s>`. Reads
`$CLAUDE_CONFIG_DIR/projects/**/*.jsonl` (default `~/.claude/projects`),
including `<session>/subagents/agent-*.jsonl`. One `session` record per
file: `id` = the entries' `sessionId` (main file) or the file stem
`agent-…` (subagent file); `parent_session` = the directory's session id
for a subagent file (the path states it); `project` = last path component
of the entries' `cwd`; `title` from an `ai-title` entry when present;
`started_at` / `last_activity_at` from the oldest / newest `timestamp`;
`model`/`models` from assistant entries' `message.model`; `usage` summed
from assistant entries' `message.usage` (`basis: measured`); `entries` =
lines counted; `state: unknown` (a transcript has no end marker);
`turn_open: null`. No runs, jobs or inbox items.

### 6.3 Codex rollouts (`adapters/codex.py`)

Source id `codex-cli@<hostname -s>`. Reads
`$CODEX_HOME/sessions/**/rollout-*.jsonl` and
`$CODEX_HOME/archived_sessions/**` (default `~/.codex`). One `session` per
file: `id` from `session_meta.payload.id`; `project` from its `cwd`'s last
component; `provider` from `session_meta`; `model`/`effort` from the newest
`turn_context`; `models` from all of them; `turn_open` = the newest of
`task_started` vs `task_complete`/`turn_aborted` events is a start;
`usage` from the newest `token_count` event's totals; `state: unknown`.
Archived files: same, plus nothing else (archiving is not an end).

### 6.4 Claude Code hooks (`hooks.py`, opt-in)

`fleetglint hooks install claude` adds hook entries to
`~/.claude/settings.json` (after printing the diff and asking, `--yes` to
skip the prompt; a backup is written next to it) that pipe
`SessionStart`, `SessionEnd`, `SubagentStart` and `SubagentStop` payloads
into `fleetglint hooks record claude`, which writes `session` records to
source `claude-hooks@<hostname -s>` via `emit`: `SessionStart` → `open`
(the hook's `source` field says startup / resume / clear / compact; it is
kept in `summary`, it is not a new process), `SessionEnd` → `ended`.
`Stop` is a turn end, not a session end, and is not used.
`fleetglint hooks uninstall claude` removes exactly the entries it added.
Hooks never block Claude: `hooks record` always exits 0 and has a 2 s
budget.

## 7. Configuration and paths

`$XDG_CONFIG_HOME/fleetglint/config.toml` (`~/.config/...`), optional;
every key has a default. `--config` overrides the path.

```toml
[server]
port = 8765                # host is always 127.0.0.1

[ingest]
roots = ["~/.local/state/fleetglint/sources"]
poll_s = 2
default_stale_after_s = 900
window_hours = 24

[retention]
segment_days = 30
abandon_days = 90
history_days = 30

[files]
allowed_roots = []         # plus each adapter's allowed_roots and each NDJSON root
max_tail_kib = 64

[adapters.tachiko_harness]
enabled = "auto"           # auto | true | false
state_dir = "~/.local/state"

[adapters.claude_code]
enabled = "auto"           # auto = on when the projects dir exists
dir = "~/.claude/projects" # $CLAUDE_CONFIG_DIR/projects when set

[adapters.codex]
enabled = "auto"
dir = "~/.codex"           # $CODEX_HOME when set
```

Paths follow XDG on every platform (spec §6.2): state
`$XDG_STATE_HOME/fleetglint/` (`sources/`, `fleetglint.sqlite`), config
`$XDG_CONFIG_HOME/fleetglint/`.

## 8. CLI

| Command | Does |
|---|---|
| `fleetglint serve [--port N] [--open]` | ingest thread + HTTP server; prints the URL |
| `fleetglint ingest [--once]` | run the ingest loop without the server (`--once`: one pass, then exit) |
| `fleetglint check [FILE…]` | validate NDJSON files (or stdin); prints `file:line: reason`; exit 1 on any invalid line |
| `fleetglint emit [--source-id ID] [--root DIR]` | one full record as JSON on stdin → validate → append per spec §6.3 |
| `fleetglint status` | sources, status, quarantine counts, database path and size |
| `fleetglint source reset ID` | acknowledge a discontinuity and rebuild that source |
| `fleetglint rebuild` | delete and rebuild the database from what is retained |
| `fleetglint doctor` | paths, permissions, what each adapter found (files, sessions, unreadable lines), quarantine, source health; exit 1 if something is wrong |
| `fleetglint demo [--clear]` | write a labelled sample source `demo@fleetglint` (§8.1); `--clear` removes it |
| `fleetglint hooks install\|uninstall\|record claude` | opt-in Claude Code hooks (§6.4) |
| `fleetglint version` | version, record format version, paths |

Exit codes: 0 ok, 1 invalid input / check failed, 2 usage, 3 runtime error.

### 8.1 Demo data

`fleetglint demo` writes the brief's sample chain (lead → worker → job →
inbox → resumed lead, plus stale / lost / unknown examples) with
`fleetglint emit` into source `demo@fleetglint` under the normal root, with
times relative to now. Records of a source whose id starts with `demo@` set
`snapshot.demo = true`. Demo data is only ever there because the user ran
`fleetglint demo`; the server never falls back to it.

## 9. Tests and CI

- Python tests use the standard library's `unittest` (no pytest), in
  `tests/`, one file per module (`tests/test_ingest.py`, …), fixtures under
  `tests/fixtures/`. Run: `python3 -m unittest discover -s tests -t .`
  (locally: `orb-test -- sh -c 'PYTHONPATH=src python3 -m unittest discover -s tests -t .'`).
- `tests/test_schema_conformance.py` runs `schema.py` over
  `examples/v1/valid` and `invalid`; CI additionally runs
  `scripts/check_examples.py` (jsonschema) so the stdlib validator and the
  JSON Schema cannot drift.
- Release-gate tests (`tests/gate/`) cover the gate list in §10 end to end
  with a real server on an ephemeral port and a temporary state dir.
- UI: `pnpm -C ui typecheck`, `pnpm -C ui test` (Vitest + Testing Library,
  against fixture JSON in `ui/src/fixtures/`), `pnpm -C ui build`.
- CI (GitHub Actions): `schema` (existing), `python` (3.11 and 3.13 on
  ubuntu, 3.13 on macos for process checks), `ui`. A `release` workflow on
  tag `v*` builds the UI, the sdist and the wheel and attaches them to the
  GitHub Release.

## 10. Release gate for v0.1

From research round 4 (2026-11-06): a stranger must see their own existing
work on first run. Add to the list below: first run on a machine with only
Claude Code, only Codex, and neither, each works and explains what it found
(`doctor`, empty state); re-scans are idempotent; no transcript-derived
record is ever shown as running, done or needing action; no prompt or tool
content reaches SQLite, the API or logs.


From the research rounds (02/03). Each item is an automated test or a
scripted check:

1. Clean environment: install, `fleetglint serve`, append a few NDJSON
   lines with `fleetglint emit` → they show up without a restart.
2. A detached job shows its owning run, and the run's `waits_on` the job;
   the job's terminal record updates the board without a restart.
3. A non-terminal record without fresh evidence shows `stale`; a vanished
   local pid shows `lost`; a discontinuity shows `unknown`.
4. Malformed lines, oversize lines, a symlink out of the allowed roots, a
   huge log and a secret in a log or field are all safe (quarantined,
   refused, bounded, redacted).
5. Kill the server mid-batch and restart: no duplicate history, no lost
   lines.
6. API down → the UI shows Unavailable, never demo or stale data as
   current.
7. Non-GET, foreign `Host`, cross-origin requests are refused.
