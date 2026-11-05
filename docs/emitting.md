# Emitting records

Fleetglint is fed by **records**. A record is one JSON object that states the
complete current condition of one run, job, inbox item or session. There are no
partial updates in v1: every line replaces the previous line with the same
identity.

The format is specified in [spec.md](spec.md). This page shows the shortest
useful examples and the rules that are easy to get wrong. Every JSON example
below passes `fleetglint check`.

## The minimum run, job and inbox item

A record is identified by `(source_id, type, id)`. Pick ids that stay stable
for the lifetime of the thing they describe, and pick one `source_id` per
writer. The convention is `<tool>@<host>`; the host part must be lowercase.

### Shell

A run that is currently executing:

```sh
fleetglint emit <<'JSON'
{"v":1,"type":"run","id":"run-20261106-101500","source_id":"my-workflow@workstation","updated_at":"2026-11-06T10:15:00+09:00","state":"running","agent":"codex-cli","project":"payments-api","title":"Fix the retry loop","started_at":"2026-11-06T10:15:00+09:00","stale_after_s":900}
JSON
```

A job that a run started, with an explicit link back to that run:

```sh
fleetglint emit <<'JSON'
{"v":1,"type":"job","id":"job-20261106-102000","source_id":"my-workflow@workstation","updated_at":"2026-11-06T10:20:00+09:00","state":"running","command_summary":"pytest tests/test_api.py","kind":"test","run":{"type":"run","id":"run-20261106-101500"},"started_at":"2026-11-06T10:20:00+09:00","stale_after_s":900}
JSON
```

An inbox item that asks a role to look at the finished job:

```sh
fleetglint emit <<'JSON'
{"v":1,"type":"inbox_item","id":"inbox-20261106-103000","source_id":"my-workflow@workstation","updated_at":"2026-11-06T10:30:00+09:00","role_id":"payments-reviewer","state":"open","kind":"job_finished","subject":{"type":"job","id":"job-20261106-102000"},"outcome":"done","action_required":true,"created_at":"2026-11-06T10:30:00+09:00","detail":"Tests passed; review the change."}
JSON
```

`fleetglint emit` validates the record against the v1 schema and appends it to
the current segment for its source. It reads one complete record from standard
input.

### Python

The same three records, using the standard library to avoid shell quoting:

```python
import json
import subprocess

SOURCE = "my-workflow@workstation"


def emit(record):
    subprocess.run(["fleetglint", "emit"], input=json.dumps(record) + "\n",
                   text=True, check=True)


run = {
    "v": 1, "type": "run", "id": "run-20261106-101500", "source_id": SOURCE,
    "updated_at": "2026-11-06T10:15:00+09:00", "state": "running",
    "agent": "codex-cli", "project": "payments-api", "title": "Fix the retry loop",
    "started_at": "2026-11-06T10:15:00+09:00", "stale_after_s": 900,
}
job = {
    "v": 1, "type": "job", "id": "job-20261106-102000", "source_id": SOURCE,
    "updated_at": "2026-11-06T10:20:00+09:00", "state": "running",
    "command_summary": "pytest tests/test_api.py", "kind": "test",
    "run": {"type": "run", "id": "run-20261106-101500"},
    "started_at": "2026-11-06T10:20:00+09:00", "stale_after_s": 900,
}
inbox = {
    "v": 1, "type": "inbox_item", "id": "inbox-20261106-103000",
    "source_id": SOURCE, "updated_at": "2026-11-06T10:30:00+09:00",
    "role_id": "payments-reviewer", "state": "open", "kind": "job_finished",
    "subject": {"type": "job", "id": "job-20261106-102000"},
    "outcome": "done", "action_required": True,
    "created_at": "2026-11-06T10:30:00+09:00",
    "detail": "Tests passed; review the change.",
}

for record in (run, job, inbox):
    emit(record)
```

## Full records, not patches

Every line carries the complete current state. To change anything, send the
whole record again with the same `(source_id, type, id)`. Do not send only the
field that changed.

```sh
fleetglint emit <<'JSON'
{"v":1,"type":"run","id":"run-20261106-101500","source_id":"my-workflow@workstation","updated_at":"2026-11-06T10:30:00+09:00","state":"done","agent":"codex-cli","project":"payments-api","title":"Fix the retry loop","started_at":"2026-11-06T10:15:00+09:00","ended_at":"2026-11-06T10:30:00+09:00","exit_code":0}
JSON
```

The latest line for an identity wins. Order comes from the position in the
source's segment files, not from `updated_at`, so an older timestamp in a later
line still wins. Two sources may use the same `id` without colliding.

## `updated_at`, `observed_at` and `stale_after_s`

| Field | Required | Meaning |
|---|---|---|
| `updated_at` | yes | When you produced this version of the record. |
| `observed_at` | no | When you last confirmed that `state` is still true. Defaults to `updated_at`. |
| `stale_after_s` | no | How many seconds after `observed_at` a non-terminal claim stays current. Default 900. |

A non-terminal record stays `running` or `waiting` only while there is current
evidence: a local process check matched, or `now < observed_at + stale_after_s`.
Without either, the board shows `stale` (or `lost` when a local process was
checked and is gone).

A long-running process should re-emit its full record periodically with a fresh
`updated_at` and `observed_at`. This is a heartbeat, not a patch:

```sh
fleetglint emit <<'JSON'
{"v":1,"type":"run","id":"run-20261106-101500","source_id":"my-workflow@workstation","updated_at":"2026-11-06T10:25:00+09:00","observed_at":"2026-11-06T10:25:00+09:00","state":"running","agent":"codex-cli","project":"payments-api","title":"Fix the retry loop","started_at":"2026-11-06T10:15:00+09:00","stale_after_s":900}
JSON
```

If you include a `process` object and the process runs on the same host,
Fleetglint can check the pid itself. That keeps a silent process from looking
stale, but a vanished process becomes `lost`; it never becomes `done`.

## Marking terminal states

A run or job is terminal when its `state` is `done`, `failed` or `cancelled`.
Terminal runs and jobs must include `started_at` and `ended_at`. `done` means
you said so: a zero `exit_code` without `"state":"done"` does not make a record
done. `failed` is for a non-zero exit, an error or a rejected result.
`cancelled` is for a deliberate stop.

```sh
fleetglint emit <<'JSON'
{"v":1,"type":"job","id":"job-20261106-102000","source_id":"my-workflow@workstation","updated_at":"2026-11-06T10:30:00+09:00","state":"done","command_summary":"pytest tests/test_api.py","kind":"test","run":{"type":"run","id":"run-20261106-101500"},"started_at":"2026-11-06T10:20:00+09:00","ended_at":"2026-11-06T10:30:00+09:00","exit_code":0}
JSON
```

An inbox item is not a run: it starts `open` and becomes `acked` when the role
has seen it. An `acked` record needs `acked_at`.

```sh
fleetglint emit <<'JSON'
{"v":1,"type":"inbox_item","id":"inbox-20261106-103000","source_id":"my-workflow@workstation","updated_at":"2026-11-06T10:35:00+09:00","role_id":"payments-reviewer","state":"acked","kind":"job_finished","subject":{"type":"job","id":"job-20261106-102000"},"outcome":"done","action_required":true,"created_at":"2026-11-06T10:30:00+09:00","acked_at":"2026-11-06T10:35:00+09:00","detail":"Tests passed; review the change."}
JSON
```

## Linking a job to its run, and `waits_on`

Relationships are explicit, never inferred from names, times or directories.
A job points at the run that owns its result with `run`. A run that is blocked
on that job lists it in `waits_on` and uses `state: "waiting"`:

```sh
fleetglint emit <<'JSON'
{"v":1,"type":"run","id":"run-20261106-101500","source_id":"my-workflow@workstation","updated_at":"2026-11-06T10:20:02+09:00","state":"waiting","agent":"codex-cli","project":"payments-api","title":"Fix the retry loop","started_at":"2026-11-06T10:15:00+09:00","waits_on":[{"type":"job","id":"job-20261106-102000"}],"stale_after_s":900}
JSON
```

`waits_on` is meaningful only while the run is `waiting`. Remove the entry, or
replace the run with a non-waiting state, when the job finishes. References may
point at a record Fleetglint has not seen yet; it shows the reference as
unresolved and keeps it until the record arrives.

## Sessions

A session is a conversation history found on disk, not an execution. One
history file may span several runs, and a history file is not proof that a
process is running. Importers that can only see history files write `session`
records, not `run` records.

```sh
fleetglint emit <<'JSON'
{"v":1,"type":"session","id":"session-20261106-101500","source_id":"my-workflow@workstation","updated_at":"2026-11-06T10:40:00+09:00","state":"unknown","agent":"claude-code","project":"web-app","started_at":"2026-11-06T09:00:00+09:00","last_activity_at":"2026-11-06T10:38:00+09:00","model":"claude-sonnet-5-5","models":["claude-sonnet-5-5"],"entries":42}
JSON
```

Use `state: "ended"` only when the tool itself recorded an end; include
`ended_at` in that case. `unknown` is the normal state for an importer that
reads history files. `open` needs evidence that the session has not ended.
Sessions carry metadata only: never copy prompts, model output, tool input or
tool output into one.

## Validating with `fleetglint check`

`fleetglint check` validates NDJSON files, or standard input when no file is
named:

```sh
fleetglint check records.ndjson
fleetglint check < records.ndjson
```

It prints `file:line: reason: detail` for each bad line, then a summary such as
`7 line(s), 0 invalid`. A line must end in a newline; an incomplete last line
is reported. The exit status is 1 when any line is invalid, 3 when a file
cannot be read, and 0 otherwise.

## Writing segment files directly

`fleetglint emit` is the bundled writer. It validates the record, creates the
source directory, takes the source lock, appends one line and rotates the
segment when needed. Use it unless you already have a writer that follows the
file format.

If you write the files yourself, follow [spec.md §6](spec.md#6-writing-records):

- The default root is `$XDG_STATE_HOME/fleetglint/sources/`
  (`~/.local/state/fleetglint/sources/` when `XDG_STATE_HOME` is unset).
- One directory per source, named exactly its `source_id`.
- Segments are named `<seq>.ndjson` with a 10-digit zero-padded sequence number
  starting at `0000000001`. Only the highest segment is open for appending.
- Every line is one complete record, UTF-8, ending in a single `\n`. No BOM,
  no blank lines, at most 64 KiB per line including the newline.
- Every line's `source_id` must equal its directory name. Other lines are
  quarantined.
- Take an exclusive `flock` on `<source dir>/.lock`, open the segment with
  `O_APPEND`, write the whole line, and release the lock. Never truncate,
  rewrite or reorder bytes already written. Start a new segment instead of
  appending to an older one.

A minimal direct writer looks like this:

```python
import fcntl
import json
import os
from pathlib import Path


def append(record, root):
    directory = Path(root) / record["source_id"]
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    line = (json.dumps(record, separators=(",", ":")) + "\n").encode()
    with open(directory / ".lock", "a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        seqs = sorted(int(path.name[:10]) for path in directory.glob("*.ndjson*"))
        seq = seqs[-1] if seqs else 1
        segment = directory / f"{seq:010d}.ndjson"
        if not segment.exists():  # the highest segment was compressed: start the next one
            segment = directory / f"{seq + 1:010d}.ndjson"
        fd = os.open(segment, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, line)
        finally:
            os.close(fd)
```

Validate before you write, or check the segment afterwards:

```sh
fleetglint check "${XDG_STATE_HOME:-$HOME/.local/state}/fleetglint/sources/my-workflow@workstation/0000000001.ndjson"
```

Writing directly skips the schema check that `fleetglint emit` performs. A bad
line is quarantined by the reader and does not stop the rest of the batch.
