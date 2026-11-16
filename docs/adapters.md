# Adapter capabilities and accuracy

Fleetglint reads local evidence. A file, a live process and a successful
result prove different things. This page describes the current readers;
[spec.md §8](spec.md#8-liveness-and-what-is-shown) defines display states.

Quality means:

- **exact**: a direct field, result or check establishes the stated signal.
  It does not prove that the work is correct.
- **heuristic**: a marker, recent observation or board rule stands in for
  what is happening now or who should act.
- **unavailable**: this reader does not supply that signal.

`needs-you` is a board section, not a record state. Tables also include
session and inbox display states. Code references are relative to the repo.
A bare `liveness.py` means `src/fleetglint/liveness.py`; `query.py` means
`src/fleetglint/query.py`. Terminal records keep their state even when their
source is unavailable. Other records become `unknown` on a source problem.
Current evidence for runs and jobs means a matching local process, or an
unexpired `observed_at` (defaulting to `updated_at`). The default expiry is
900 seconds, configurable in `[ingest].default_stale_after_s`.

Adapters are read-only. Reading a transcript to extract metadata is different
from copying its contents into records. The importers do not copy prompts,
model output or tool input/output, and do not make transcript directories
available through `/api/file`. See [privacy.md](privacy.md) for storage,
redaction and the rules for opening record-linked files on demand.

## tachiko-harness

### Inputs and records

`src/fleetglint/config.py:HarnessAdapterConfig` defaults `state_dir` to
`~/.local/state`, independently of `XDG_STATE_HOME`. Override it with
`[adapters.tachiko_harness].state_dir`. Auto-enable requires
`worker-ledger/runs.tsv`. All paths below are relative to that state directory:

- `worker-ledger/runs.tsv` and non-hidden regular files matching
  `worker-ledger/running/<tool>.<pid>[.<key>]` (`tool` is lowercase letters;
  `key` is letters, digits, `_` or `-`).
- `job-run/<non-hidden job id>/cmd`, `cwd`, `pid`, `result.json`.
  `cmd` supplies a short, scrubbed command summary. `log` is checked for
  existence and stored as a path; a result can name another log path.
- `lead-wait/<non-hidden role>/<non-hidden job id>` marker files;
  roles contain lowercase letters, digits or hyphens.
- `lead-inbox/*.tsv`, `owner-notify/log.tsv`, `lead-decision/log.tsv`.
- `ci-watch/runs.tsv`.
- `orb-test/runs.tsv`, `orb-test/queue/*`, `orb-test/waiting/*`,
  `orb-test/holder/*`, `orb-test/active/*`, and `orb-test/heavy.holder`
  (preferred over `holder/*` when present). Hidden files and `.why` entries
  are skipped; a queue entry's adjacent `<entry>.why` is read as its reason.
  No test jobs are imported without `orb-test/runs.tsv`.
- The log path in each live worker marker: at most the last 8192 bytes of a
  regular, non-symlink file, solely to find wrapper `waiting on job` /
  `job ... finished` lines (`src/fleetglint/adapters/harness.py:_wait_from_log`).
  Those log contents are not copied into records.

The adapter does not read Claude Code transcripts, Codex rollouts or files
inside a job's working directory. It does not read job log bodies to decide
success. Log/result links can be opened separately under the privacy rules.

Produces `run`, `job`, `inbox_item` and `decision` records, not `session`.
CI polls are also `job` records. Wait markers annotate existing jobs;
they do not create a job without a `job-run` entry. References below use
`harness.py` for `src/fleetglint/adapters/harness.py`.

### Display signals

| Display state / section | Signal used | Quality | Code reference |
|---|---|---|---|
| running | Live worker marker, job PID without a result, CI `in_progress`, or test active/holder marker; needs current evidence. Keyed worker markers have no process check. | heuristic | `harness.py:HarnessAdapter._running_record`, `harness.py:HarnessAdapter._running_job`, `harness.py:HarnessAdapter._scan_ci`, `harness.py:HarnessAdapter._scan_orb_test`; `liveness.py:display` |
| waiting | Newest wrapper wait line in a live worker's log tail; also running jobs of kind `wait` or uncovered `wait-worker` go in the waiting section. | heuristic | `harness.py:_wait_from_log`, `harness.py:HarnessAdapter._apply_lead_wait`, `harness.py:HarnessAdapter._link_waits`; `query.py:_board_work` |
| queued | CI `queued` / `waiting` / `pending` / `requested`; test queue or memory-wait marker, with current evidence. | heuristic | `harness.py:HarnessAdapter._scan_ci`, `harness.py:HarnessAdapter._scan_orb_test`; `liveness.py:display` |
| needs-you | Inbox outcomes `failed`, `blocked`, `needs_decision`, `changes`, `checks-timeout` set `action_required`; owner notifications always set it. Viewer-role and age rules apply. Project cards also select recent failed/lost/stale/unknown work, with suppression rules. | heuristic | `harness.py:HarnessAdapter._inbox_record`, `harness.py:HarnessAdapter._scan_owner_notify`; `query.py:_board_inbox`, `query.py:_board_projects` |
| done | Worker/test exit 0; job result `status: ok`; CI completed with success/neutral/skipped; successful CI poll. Decisions are terminal and map to done in liveness, shown as decisions. | exact | `harness.py:HarnessAdapter._ledger_record`, `harness.py:HarnessAdapter._job_from_result`, `harness.py:HarnessAdapter._scan_ci`, `harness.py:HarnessAdapter._scan_orb_test`, `harness.py:HarnessAdapter._scan_decisions`; `liveness.py:display` |
| failed | Nonzero worker/test exit; job result `status: failed`; CI completed with failure/timed_out/startup_failure. | exact | `harness.py:HarnessAdapter._ledger_record`, `harness.py:HarnessAdapter._job_from_result`, `harness.py:HarnessAdapter._scan_ci`, `harness.py:HarnessAdapter._scan_orb_test` |
| lost | Local process missing or start time differs by more than 2 seconds, without a terminal result. | exact | `liveness.py:ProcessChecker.check`, `liveness.py:display` |
| stale | Observation expired without a conclusive process check. Worker expiry is 3600 seconds, or 21600 for keyed markers; CI 1800; live tests 600; jobs use the configured default. | exact | `harness.py:HarnessAdapter._running_record`, `harness.py:HarnessAdapter._scan_ci`, `harness.py:HarnessAdapter._scan_orb_test`; `liveness.py:display` |
| unknown | Nonnumeric worker exit (including ledger `lost`), missing job PID, unrecognized/invalid job result, unmapped CI status/conclusion or failed CI poll; unavailable source overrides non-terminal displays. | exact | `harness.py:HarnessAdapter._ledger_record`, `harness.py:HarnessAdapter._running_job`, `harness.py:HarnessAdapter._job_from_result`, `harness.py:HarnessAdapter._scan_ci`, `harness.py:HarnessAdapter.scan`; `liveness.py:display` |
| cancelled | CI completed/cancelled; test finish row with exit `-` (exit status not recorded). | exact | `harness.py:HarnessAdapter._scan_ci`, `harness.py:HarnessAdapter._scan_orb_test` |
| open | Inbox row without acknowledgement; owner notification. | exact | `harness.py:HarnessAdapter._inbox_record`, `harness.py:HarnessAdapter._scan_owner_notify` |
| acked | Inbox row with a parseable acknowledgement time. | exact | `harness.py:HarnessAdapter._inbox_record` |
| recent | No session records. | unavailable | `harness.py:HarnessAdapter.scan` |
| idle | No session records. | unavailable | `harness.py:HarnessAdapter.scan` |
| ended | No session records. | unavailable | `harness.py:HarnessAdapter.scan` |

### Known gaps

A live PID proves existence, not progress. Keyed subagent markers carry the
parent PID, so the adapter omits process evidence and ages them from their
start time. A removed marker does not establish completion. A ledger `lost`
row becomes writer `unknown`, not a failed result or a process-check `lost`.
A wait line outside the retained tail is not determined.

The adapter does not inspect GitHub itself; CI state is only as fresh as
`ci-watch`. Test finish rows are limited to the last 24 hours. Malformed or
unreadable optional inputs may be skipped without making the whole source
unavailable. Owner notifications have no acknowledgement signal. Role/project
inference follows harness naming conventions; ambiguous relationships are not
proof of ownership. Successful exit/result fields do not establish acceptance
or review approval.

## Claude Code transcripts

### Inputs and records

`src/fleetglint/config.py:ClaudeCodeAdapterConfig` uses
`$CLAUDE_CONFIG_DIR/projects`, or `~/.claude/projects` when unset/empty.
Override with `[adapters.claude_code].dir`. Auto-enable requires that directory.
The exact candidates are:

- `<projects dir>/<project>/*.jsonl` (one project-directory level).
- `<projects dir>/<project>/<session>/subagents/**/agent-*.jsonl`.

`src/fleetglint/adapters/claude_code.py:ClaudeCodeAdapter._candidates` skips
symlinked project directories, nested subdirectories and candidate files.
It does not read arbitrary JSONL at other depths, `settings.json`, Codex
rollouts or workspace files named by `cwd`. It does read transcript lines to
extract metadata, without copying their conversation bodies or serving them.

Produces only `session`, with stored `state: unknown`, no `turn_open` field,
and an id from the file stem. Subagent paths supply `parent_session`.
Timestamps, cwd-derived project, `ai-title`, models, entry counts and usage
come from parsed entries. Usage keeps the last counts per assistant message
id, then sums those and id-less entries.

### Display signals

| Display state / section | Signal used | Quality | Code reference |
|---|---|---|---|
| running | A transcript is not process evidence; no runs/jobs. | unavailable | `src/fleetglint/adapters/claude_code.py:ClaudeCodeAdapter._record` |
| waiting | No wait signal. | unavailable | `src/fleetglint/adapters/claude_code.py:ClaudeCodeAdapter._record` |
| queued | No queue signal. | unavailable | `src/fleetglint/adapters/claude_code.py:ClaudeCodeAdapter._record` |
| needs-you | No inbox or work records. | unavailable | `src/fleetglint/adapters/claude_code.py:ClaudeCodeAdapter._record` |
| done | No execution result. | unavailable | `src/fleetglint/adapters/claude_code.py:ClaudeCodeAdapter._record` |
| failed | No execution result. | unavailable | `src/fleetglint/adapters/claude_code.py:ClaudeCodeAdapter._record` |
| lost | Sessions do not use process checks. | unavailable | `liveness.py:display` |
| stale | Sessions use idle rather than stale. | unavailable | `liveness.py:display` |
| unknown | Source unavailable/discontinuous; stored session unknown alone still displays recent/idle. | exact | `src/fleetglint/adapters/claude_code.py:ClaudeCodeAdapter.scan`; `liveness.py:display` |
| cancelled | No execution result. | unavailable | `src/fleetglint/adapters/claude_code.py:ClaudeCodeAdapter._record` |
| open | No inbox records or stored open session state. | unavailable | `src/fleetglint/adapters/claude_code.py:ClaudeCodeAdapter._record` |
| acked | No inbox records. | unavailable | `src/fleetglint/adapters/claude_code.py:ClaudeCodeAdapter._record` |
| recent | Newest parseable entry timestamp is within the configured expiry; activity only. | exact | `src/fleetglint/adapters/claude_code.py:_Agg.add`; `liveness.py:display` |
| idle | Last activity has reached the configured expiry; activity only. | exact | `liveness.py:display` |
| ended | Importer does not supply session-end evidence. | unavailable | `src/fleetglint/adapters/claude_code.py:ClaudeCodeAdapter._record` |

### Known gaps

Execution, turn completion, session end and success are not determined.
Only complete lines count; invalid lines are skipped, and files without a
parseable timestamp produce no session. Each scan returns at most 5000
sessions, newest file modification time first. A differing entry `sessionId`
is reported but does not replace the file-stem id. Activity does not show
whether a person is waiting or whether a process is still alive.

## Codex rollouts

### Inputs and records

`src/fleetglint/config.py:CodexAdapterConfig` uses `$CODEX_HOME`, or `~/.codex`
when unset/empty. Override with `[adapters.codex].dir`. Auto-enable requires
`sessions/` or `archived_sessions/` under that directory. Both trees are walked
recursively; regular, non-symlink files must match `rollout-*.jsonl` or
`rollout-*.jsonl.gz`. Other `rollout-*` suffixes are reported as unsupported;
symlinked nested directories are skipped
(`src/fleetglint/adapters/codex.py:CodexAdapter._candidates`,
`src/fleetglint/adapters/codex.py:_is_rollout`).

It does not read arbitrary files in `archived_sessions`, Codex databases,
config/auth files, Claude transcripts or workspace files named by `cwd`.
Rollout bodies are parsed for metadata, not copied into records or served.

Produces only `session`, with stored `state: unknown`, id from
`session_meta.payload.id`, project/provider from metadata, model/effort from
turn contexts, and newest entry timestamp as activity. The last recognized
turn event sets `turn_open`: `task_started` is true;
`task_complete`/`turn_aborted` is false. Usage is the last reported
`token_count` totals, not a sum of every event.

### Display signals

| Display state / section | Signal used | Quality | Code reference |
|---|---|---|---|
| running | Rollout activity/turn_open is not process evidence; no runs/jobs. | unavailable | `src/fleetglint/adapters/codex.py:CodexAdapter._record` |
| waiting | No wait signal. | unavailable | `src/fleetglint/adapters/codex.py:CodexAdapter._record` |
| queued | No queue signal. | unavailable | `src/fleetglint/adapters/codex.py:CodexAdapter._record` |
| needs-you | No inbox or work records. | unavailable | `src/fleetglint/adapters/codex.py:CodexAdapter._record` |
| done | Turn completion is not an execution result. | unavailable | `src/fleetglint/adapters/codex.py:_Agg._add_event` |
| failed | Turn abort is not a failed execution result. | unavailable | `src/fleetglint/adapters/codex.py:_Agg._add_event` |
| lost | Sessions do not use process checks. | unavailable | `liveness.py:display` |
| stale | Sessions use idle rather than stale. | unavailable | `liveness.py:display` |
| unknown | Source unavailable/discontinuous; stored session unknown alone still displays recent/idle. | exact | `src/fleetglint/adapters/codex.py:CodexAdapter.scan`; `liveness.py:display` |
| cancelled | No execution result. | unavailable | `src/fleetglint/adapters/codex.py:CodexAdapter._record` |
| open | No inbox records or stored open session state. | unavailable | `src/fleetglint/adapters/codex.py:CodexAdapter._record` |
| acked | No inbox records. | unavailable | `src/fleetglint/adapters/codex.py:CodexAdapter._record` |
| recent | Newest parseable entry timestamp is within the configured expiry; activity only. | exact | `src/fleetglint/adapters/codex.py:_Agg.add`; `liveness.py:display` |
| idle | Last activity has reached the configured expiry; activity only. | exact | `liveness.py:display` |
| ended | Neither archive placement nor turn completion sets ended. | unavailable | `src/fleetglint/adapters/codex.py:CodexAdapter._record` |

### Known gaps

Execution, waits, session end and success are not determined. `turn_open`
reflects file order of recognized events, not a live process check. Files
without session metadata or a parseable activity timestamp are skipped;
invalid/incomplete lines do not supply evidence. Duplicate session ids keep
the rollout with newest activity (then modification time). Each scan returns
at most 5000 sessions, ordered by file modification time after deduplication.
Archiving does not establish completion.

## Records from `fleetglint emit` / NDJSON

### Inputs and records

`src/fleetglint/emit.py:run` reads one JSON object from stdin and validates it.
It writes to `--root`, or the first configured `[ingest].roots` entry. The
default root is `$XDG_STATE_HOME/fleetglint/sources`, falling back to
`~/.local/state/fleetglint/sources` (`src/fleetglint/config.py:Config`).
The reader scans all configured roots, direct child source directories, and
`<root>/<source_id>/<10-digit positive seq>.ndjson[.gz]`. Symlinked source
directories and segments are skipped
(`src/fleetglint/ingest.py:Ingestor.scan_roots`,
`src/fleetglint/ingest.py:_list_segments`).

`emit` does not inspect the tool behind a record, read transcripts, execute
commands or open referenced log/result files. The ingest reader does not
search arbitrary files outside these segments. Referenced files are a
separate, on-demand read under the privacy rules. Unlike the history
importers, a writer can supply text that is stored as written; keep secrets
out of record fields. See [emitting.md](emitting.md) for the writer contract.

Accepts `run`, `job`, `inbox_item`, `session` and `decision`
(`src/fleetglint/schema.py:validate`). `emit` does not infer record types or
states; writers send full replacements with stable identities.

### Display signals

| Display state / section | Signal used | Quality | Code reference |
|---|---|---|---|
| running | Writer's run/job running state with current process or observation evidence. | heuristic | `liveness.py:display`, `liveness.py:ProcessChecker.check` |
| waiting | Writer's run waiting state with current evidence; board also places running wait-kind jobs in waiting. | heuristic | `liveness.py:display`; `query.py:_board_work` |
| queued | Writer's run/job queued state with current evidence. | heuristic | `liveness.py:display` |
| needs-you | Open action-required inbox for a viewer role within the configured age; project cards also classify recent failed/lost/stale/unknown work, with suppression rules. | heuristic | `query.py:_board_inbox`, `query.py:_board_projects` |
| done | Explicit run/job done; decisions are terminal and map to done in liveness. Exit 0 alone is insufficient. | exact | `liveness.py:is_terminal`, `liveness.py:display` |
| failed | Explicit run/job failed. | exact | `liveness.py:display` |
| lost | Local process is missing or its recorded start time mismatches by more than 2 seconds. | exact | `liveness.py:ProcessChecker.check`, `liveness.py:display` |
| stale | Observation expiry reached without a conclusive process check; runs/jobs only. | exact | `liveness.py:display` |
| unknown | Writer's run/job unknown, or source problem for a non-terminal record; session unknown alone uses recent/idle. | exact | `liveness.py:display` |
| cancelled | Explicit run/job cancelled. | exact | `liveness.py:display` |
| open | Non-terminal inbox item with healthy source; an open session uses recent/idle instead. | exact | `liveness.py:display` |
| acked | Explicit inbox acked. | exact | `liveness.py:is_terminal`, `liveness.py:display` |
| recent | Non-ended session activity is within its expiry. | exact | `liveness.py:display` |
| idle | Non-ended session activity has reached its expiry. | exact | `liveness.py:display` |
| ended | Explicit session ended. | exact | `liveness.py:is_terminal`, `liveness.py:display` |

### Known gaps

Validation proves record shape, not the truth of a writer's claim. No terminal
result is inferred from silence, disappearance or exit_code alone. Remote
processes and OS-denied checks fall back to timestamps. A PID without a start
time cannot detect PID reuse. A matching PID cannot prove useful progress.
An unresolved segment discontinuity makes non-terminal evidence unknown.
Invalid records are quarantined rather than supplying state. Session activity
never becomes execution evidence. Optional Claude hooks arrive through this
record path; they are separate from the transcript importer.
