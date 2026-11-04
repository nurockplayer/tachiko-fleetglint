# Fleetglint record format, version 1

Status: draft (2026-11-05). Nothing here is frozen until the v0.1 release.

Fleetglint is a read-only board. Workflows tell it what happened by writing
**records**; Fleetglint stores them in a local SQLite read model and shows
them. This document defines the records (§2–§5), how they are written to
NDJSON files (§6), how Fleetglint reads them (§7) and how it decides what to
show when the evidence is old or missing (§8).

The key words MUST, MUST NOT, SHOULD and MAY are used as in RFC 2119.

Machine-readable schema: [`schema/v1/record.schema.json`](../schema/v1/record.schema.json)
(JSON Schema 2020-12). Examples: [`examples/v1/`](../examples/v1/).

## 1. Principles

1. **Fleetglint observes; it never decides.** A record is a claim made by
   its writer. Fleetglint never schedules, dispatches, retries, merges or
   reviews, and never writes back to a workflow.
2. **Full records, not patches.** Every line carries the complete current
   state of one record. A later line with the same identity replaces the
   earlier one. There are no partial updates in v1.
3. **No guessing.** Relationships come only from explicit typed references
   (§3). Fleetglint never links records by time, name or working directory,
   and never infers success: a run without a terminal record is not done.
4. **Old evidence is shown as old.** "Running" with no recent evidence is
   shown as stale, lost or unknown (§8), never as running, done or failed.
5. **The SQLite database is disposable.** It can be deleted and rebuilt from
   the NDJSON segments and adapters that are still retained (§7.5).

## 2. Common fields

Every record is one JSON object. These fields are common to all types.

| Field | Type | Required | Meaning |
|---|---|---|---|
| `v` | integer | yes | Format version. This document defines `1`. |
| `type` | string | yes | `run`, `job` or `inbox_item` (§4). |
| `id` | string | yes | Writer-chosen id, unique within `(source_id, type)`. |
| `source_id` | string | yes | The source that wrote the record (§6.1). |
| `updated_at` | timestamp | yes | When the writer produced this version of the record. |
| `observed_at` | timestamp | no | When the writer last confirmed that `state` is still true (§8). Defaults to `updated_at`. |
| `stale_after_s` | integer | no | How long, in seconds after `observed_at`, the writer's claim of a non-terminal state stays valid (§8). |
| `project` | string | no | Free-form project or repository name, for grouping. |
| `title` | string | no | One-line human summary, at most 200 characters. |
| `links` | array of Link | no | At most 16 related links (§3.3). |

**Identity.** A record is identified by `(source_id, type, id)`. Two sources
may use the same `id` without colliding.

**Ids.** `id` and `source_id` are 1–200 characters with no whitespace or
control characters. `source_id` is further restricted (§6.1).

**Timestamps** are RFC 3339 strings with an explicit offset
(`2026-11-05T05:50:26+09:00` or `2026-11-05T20:50:26Z`). A timestamp without
an offset is invalid, and so is a date or time that does not exist
(`2026-02-30`, `25:00`); the schema's `pattern` checks the shape and its
`format: date-time` the calendar, so validators MUST enable format checks.
Timestamps are displayed, compared against the current
time for staleness (§8) and used for retention; they are **never** used to
order versions of a record (§7.2).

**Unknown fields.** A reader MUST keep fields it does not understand and MAY
show them in a raw view (redacted, §9). Writers that add their own fields
SHOULD prefix them with `x_`; the spec will never define a field starting
with `x_`.

**Size.** A record serialized as one line, including the newline, MUST NOT
exceed 64 KiB.

## 3. References and links

### 3.1 Record references

A reference to another record is an object:

```json
{"type": "job", "id": "lw-store-blink-20261105-053128"}
{"type": "run", "id": "cx.20552", "source_id": "tachiko-harness@mbp"}
```

| Field | Required | Meaning |
|---|---|---|
| `type` | yes | The referenced record's `type`. |
| `id` | yes | The referenced record's `id`. |
| `source_id` | no | Defaults to the referencing record's `source_id`. |

A reference to a record Fleetglint has not seen is kept and shown as
unresolved; it is not an error. The referenced record may arrive later.

### 3.2 External references

A reference to something outside Fleetglint (a pull request, a CI run, an
issue) is an object with `type: "external"`:

```json
{"type": "external", "kind": "github_pr", "key": "nurockplayer/eddington-1919#175",
 "url": "https://github.com/nurockplayer/eddington-1919/pull/175"}
```

| Field | Required | Meaning |
|---|---|---|
| `type` | yes | Always `"external"`. |
| `kind` | yes | What it is. v1 names `github_pr`, `github_issue`, `ci_run` and `url`; other values are allowed and shown as text. |
| `key` | no | A stable, human-readable key (`owner/repo#175`). Two external references are the same thing if `kind` and `key` are equal. |
| `url` | no | `http` or `https` URL. |

At least one of `key` and `url` MUST be present.

### 3.3 Links

A link is something a person may want to open. It is not a relationship.

```json
{"label": "worker log", "path": "/Users/me/.local/state/cx-exec/step2c.log"}
{"label": "PR", "url": "https://github.com/nurockplayer/fleetglint/pull/3"}
```

Exactly one of `url` (http/https) or `path` (absolute local path) is
present; `label` is required (at most 80 characters). Fleetglint shows the
contents of a `path` only under the read rules in §9.

## 4. Record types

### 4.1 `run`: one execution of an agent

A run is one continuous execution of an AI agent or a human-driven session
segment: a Codex worker, a Claude Code subagent, a review by another model.
A session that is paused and later resumed produces a **new** run with
`resume_of` pointing to the previous one.

| Field | Type | Required | Meaning |
|---|---|---|---|
| `state` | RunState | yes | See below. |
| `agent` | string | yes | The tool that runs it: `codex-cli`, `claude-code`, `gemini-cli`, `aider`, `human`, … |
| `model` | string | no | Model id as the tool reports it: `gpt-6.1-terra`, `claude-opus-5-5`. |
| `provider` | string | no | Who serves the model: `openai`, `anthropic`, `deepseek`, `ollama`, … |
| `effort` | string | no | Reasoning effort or similar setting, as the tool names it. |
| `role_id` | string | no | The role responsible for this run, usually the one that dispatched it (§4.4). |
| `session_id` | string | no | The tool's own session or conversation id, if it has one. Runs that share a `session_id` are segments of one conversation. |
| `parent_run` | RecordRef | no | The run that **spawned** this run. |
| `resume_of` | RecordRef | no | The run this run **continues** (same conversation, later segment). |
| `waits_on` | array of Ref | no | At most 32 record or external references this run is currently blocked on. Meaningful only while `state` is `waiting`. |
| `started_at` | timestamp | no | Required when `state` is `running`, `waiting` or terminal. |
| `ended_at` | timestamp | no | Required when `state` is terminal. |
| `exit_code` | integer or null | no | Process exit status, if the run was a process. |
| `process` | Process | no | Lets Fleetglint check liveness itself (§8.2). |
| `usage` | Usage | no | Token and cost figures (§5.2). |
| `summary` | string | no | Short result or status text, at most 2000 characters. |

**RunState**

| Value | Terminal | Meaning |
|---|---|---|
| `queued` | no | Accepted but not started. |
| `running` | no | Executing. |
| `waiting` | no | Started, blocked on `waits_on` (a job, a review, a person). |
| `done` | yes | Finished and the writer considers it successful. |
| `failed` | yes | Finished unsuccessfully (non-zero exit, error, rejected). |
| `cancelled` | yes | Stopped on purpose before finishing. |
| `unknown` | no | The writer itself cannot tell (for example an adapter that lost track of a process). |

`done` means the writer said so. A zero `exit_code` without `state: "done"`
does not make a run done.

`parent_run` and `resume_of` are different relationships and MUST NOT be
used for each other. A run may have both (a resumed worker segment still has
the lead that spawned the worker as its parent).

### 4.2 `job`: a detached command

A job is a long command a run handed off so it could stop waiting in its own
process: a test suite, a build, a review chain, a "wait for this PR" helper.

| Field | Type | Required | Meaning |
|---|---|---|---|
| `state` | JobState | yes | See below. |
| `command_summary` | string | yes | A short description of the command, at most 200 characters. MUST NOT be the full argv; writers SHOULD drop arguments that may hold secrets. |
| `kind` | string | no | `test`, `build`, `review`, `wait`, … free-form. |
| `run` | RecordRef | no | The run that started the job and owns its result. |
| `role_id` | string | no | The role that should act on the result, if different from the owning run's role. |
| `started_at` | timestamp | no | Required when `state` is `running`, `waiting` or terminal. |
| `ended_at` | timestamp | no | Required when `state` is terminal. |
| `exit_code` | integer or null | no | Exit status. |
| `signal` | string or null | no | Signal name if the job was killed (`SIGTERM`, `SIGKILL`). |
| `process` | Process | no | §8.2. |
| `log_path` | string | no | Absolute path of the job's output log (§9). |
| `result_path` | string | no | Absolute path of a result file the job wrote. |
| `summary` | string | no | At most 2000 characters. |

**JobState**: `queued`, `running`, `done`, `failed`, `cancelled`, `unknown`,
with the same meaning and terminality as RunState. A job has no `waiting`
state.

### 4.3 `inbox_item`: something a role should look at

An inbox item says "role R should look at subject S". It is mutable: it
starts `open` and becomes `acked` when the role has seen it. It is not an
immutable event log entry.

| Field | Type | Required | Meaning |
|---|---|---|---|
| `role_id` | string | yes | Who should act. |
| `state` | InboxState | yes | `open` or `acked`. |
| `kind` | string | yes | What happened: `run_finished`, `job_finished`, `review_finished`, `needs_decision`, … free-form. |
| `subject` | Ref | yes | The record or external thing it is about. |
| `outcome` | string | no | The subject's outcome as the writer reports it, at most 80 characters: `done`, `failed`, `merged-armed`. Shown as text; Fleetglint does not interpret it. |
| `action_required` | boolean | no | `true` if the role must do something (decide, fix, approve), not only take note. Default `false`. |
| `created_at` | timestamp | yes | When the item was raised. |
| `acked_at` | timestamp | no | Required when `state` is `acked`. |
| `detail` | string | no | At most 4000 characters, redacted before display (§9). |

Inbox items are never stale (§8): they describe a notification, not a
live process.

### 4.4 Roles

`role_id` names who is responsible: a lead session (`fleetglint-lead`), a
human (`owner`), a team. It is a free-form string in v1; a `role` record type
that describes roles is reserved for a later version (§10).

## 5. Shared objects

### 5.1 Process

```json
{"host": "mbp", "pid": 20552, "start_time": "2026-11-04T20:45:04+09:00"}
```

| Field | Required | Meaning |
|---|---|---|
| `host` | yes | Host name as `hostname -s` prints it. |
| `pid` | yes | Process id (positive integer). |
| `start_time` | no | The process start time. Strongly recommended: without it a reused pid cannot be told apart. |

### 5.2 Usage

```json
{"basis": "measured", "input_tokens": 182340, "cached_input_tokens": 120000,
 "output_tokens": 9120, "cost": {"amount": 0.42, "currency": "USD", "basis": "estimated"}}
```

| Field | Required | Meaning |
|---|---|---|
| `basis` | yes | `measured` (the tool reported these numbers) or `estimated` (computed by the writer). Applies to the token counts. |
| `input_tokens`, `cached_input_tokens`, `output_tokens` | no | Non-negative integers. `cached_input_tokens` is a part of `input_tokens`, not added to it. |
| `cost` | no | `amount` (number ≥ 0), `currency` (ISO 4217), `basis`: `billed` (an invoice amount), `api_equivalent` (list price for the tokens, for example on a subscription plan) or `estimated` (any other estimate). |

Fleetglint never adds up costs of different `cost.basis` values into one
number.

## 6. Writing records

### 6.1 Sources

A **source** is one logical writer, with one ordered sequence of records.
`source_id` matches `^[a-z0-9][a-z0-9._-]*(@[a-z0-9][a-z0-9._-]*)?$`, at most
128 characters. The convention is `<tool>@<host>`: `tachiko-harness@mbp`,
`my-ci-script@buildbox`.

All records in one source share one order (§7.2). If several processes write
to the same source, they MUST coordinate through the source lock (§6.3).
Processes that cannot coordinate MUST use different sources.

### 6.2 Files

The default root is `$XDG_STATE_HOME/fleetglint/sources/`
(`~/.local/state/fleetglint/sources/` when `XDG_STATE_HOME` is unset).
Fleetglint may be configured to read other roots.

```
sources/
  tachiko-harness@mbp/
    .lock
    0000000001.ndjson.gz
    0000000002.ndjson
```

- Each source has one directory named exactly its `source_id`.
- Records are stored in **segments** named `<seq>.ndjson`, where `<seq>` is
  a 10-digit, zero-padded decimal sequence number starting at
  `0000000001`. Segments are read in increasing `<seq>` order.
- Only the segment with the highest `<seq>` is open for appending. A writer
  rotates by creating the next segment; it never appends to an older one.
- A closed segment MAY be compressed in place to `<seq>.ndjson.gz` after
  Fleetglint has ingested it completely (§7.4).
- Every line in a source directory MUST have `source_id` equal to the
  directory name; other lines are quarantined (§7.3).
- Files are UTF-8, one JSON object per line, each line ending in `\n`
  (LF). No byte order mark, no blank lines.

### 6.3 Appending

A writer appends one complete record per line:

1. Take an exclusive `flock` on `<source dir>/.lock` (shared writers only;
   a single-writer source MAY skip it).
2. Open the current segment with `O_APPEND`, write the line including its
   trailing `\n` in a single `write`, then release the lock.
3. Never truncate, rewrite or reorder bytes already written.

The bundled `fleetglint emit` command (non-normative) reads a full record
as JSON on stdin, validates it against the schema, and appends it this way.
It does not accept partial updates.

## 7. Reading records

This section binds Fleetglint itself and any other reader that wants the
same results.

### 7.1 Checkpoints

The reader keeps, per source, the last committed position
`(seq, byte_offset)`: the segment and the offset just past the last
complete line it has ingested.

### 7.2 Ordering and the latest record

Within a source, records are ordered by `(seq, byte_offset)`. For each
identity, the **latest record** is the last one in that order. Timestamps do
not affect the order. Records of different sources are never ordered against
each other; each source is authoritative only for its own identities.

### 7.3 Ingesting a batch

1. Read new bytes from the checkpoint onwards. Bytes after the last `\n`
   are an incomplete line: leave them for the next read.
2. For each complete line: parse JSON, check `v`, `type`, `source_id` and
   the schema for that type.
3. A line that fails is put in the **quarantine** with its position and a
   reason (`invalid_json`, `too_large`, `unsupported_version`,
   `unsupported_type`, `schema`, `source_mismatch`). Quarantined lines never
   enter the read model and never stop the other lines of the batch. The
   quarantine is bounded (default: the last 1000 entries, each with at most
   the first 1 KiB of the line).
4. In **one SQLite transaction**: append the valid records to history,
   replace the latest record for each identity, record the quarantined
   lines and advance the checkpoint. A crash before the commit leaves the
   previous checkpoint, so the batch is read again; history rows are unique
   on `(source_id, seq, byte_offset)`, so a replay adds nothing twice.

### 7.4 Discontinuity

The reader reports a **discontinuity** for a source, and shows that
source's records as `unknown` (§8) until it is resolved, when:

- the current segment is shorter than the checkpoint offset (truncated), or
  was replaced (different inode or a changed prefix fingerprint);
- a segment with a lower `<seq>` than the checkpoint appears or changes;
- a segment is missing between two present ones before it was ingested.

The reader never skips data silently. Resolving a discontinuity
(acknowledging the loss, or rebuilding from the remaining segments) is an
explicit user action.

### 7.5 Retention

- A segment may be deleted only after it is fully ingested, closed, and
  older than the retention period (default 30 days, configurable).
- History in SQLite has its own retention (default 30 days). Latest records
  in a terminal state, and acked inbox items, are dropped with their
  history. Non-terminal latest records are kept while their source exists.
- Rebuilding the database replays the segments still present; history older
  than the oldest retained segment is gone, which is expected.

### 7.6 Adapters

An adapter reads another tool's own state (files, databases) read-only and
produces records with its own `source_id`. It follows the same identity,
full-record and no-guessing rules. Instead of byte offsets, an adapter's
order is the order in which it produces records; it re-reads its inputs on
each scan and emits a record only when it differs from the previous one. An
adapter MUST NOT write to the tool it reads.

## 8. Liveness and what is shown

The writer's `state` is kept as written. Fleetglint shows a **display
state** next to it, computed when the read model is queried.

### 8.1 Display states

For a terminal `state` (`done`, `failed`, `cancelled`) the display state is
the same value. For an inbox item it is its `state`. For non-terminal
states:

| Display state | When |
|---|---|
| the record's `state` (`queued`, `running`, `waiting`) | There is current evidence: a process check succeeded (§8.2), or `now < observed_at + stale_after_s`. |
| `lost` | A process check shows the process is gone, but no terminal record arrived. |
| `stale` | No current evidence: `observed_at + stale_after_s` has passed and no process check is possible. |
| `unknown` | The writer wrote `unknown`, or the source has an unresolved discontinuity (§7.4) or is reported unavailable by its adapter. |

When `stale_after_s` is absent the reader uses a default (900 seconds,
configurable). `lost`, `stale` and `unknown` are never shown as `done` or
`failed`, and never counted as either.

### 8.2 Process checks

If a non-terminal record has `process.host` equal to the local host name,
Fleetglint MAY check the process: the pid exists and, if `start_time` is
given, the running process started within 2 seconds of it. A matching
process is current evidence; a missing or different process gives `lost`.
Records from other hosts fall back to `observed_at`/`stale_after_s`.

## 9. Safety rules for readers

- Fleetglint binds to `127.0.0.1` only, accepts only `GET`, checks the
  `Host` header, sends no CORS headers and sends `Cache-Control: no-store`.
- Every string shown, including the raw view of unknown fields and log
  tails, passes redaction first: values of secret-looking environment
  variables, token shapes and PEM blocks are replaced.
- `log_path`, `result_path` and link `path` are opened only if they resolve,
  after following symlinks, inside a configured allowed root; only regular
  files; at most the last 64 KiB (configurable) is read. Anything else is
  shown as "not readable", never as an error page with the path's contents.
- A record can make Fleetglint read a file but never run a command, follow
  a URL or contact a network host.

## 10. Versioning and compatibility

- `v` is the format version, independent of the Fleetglint package version.
- Within `v: 1`, changes are additive only: new optional fields, new record
  types, new values of free-form strings. Readers MUST accept unknown
  fields.
- New values of the closed enums (RunState, JobState, InboxState, usage and
  cost `basis`) are a breaking change and need `v: 2`; in a `v: 1` line
  they fail the schema.
- Reserved for later versions: record types `review` (one review of a given
  `head_sha`), `gate` (the merge gate's changing state), `quota`, `role`,
  `session`. Writers MUST NOT use these type names until they are defined.
- A reader that meets a `v` it does not support quarantines the line with
  `unsupported_version`.
