# Privacy and security

Fleetglint is a local, read-only board. It has no account, no telemetry and no
outbound network connection. Everything it reads and stores stays on this
machine, under the state and config directories described below.

## What Fleetglint reads

Fleetglint reads only these places:

- **NDJSON sources.** Every source directory under the configured roots. The
  default root is `$XDG_STATE_HOME/fleetglint/sources/`
  (`~/.local/state/fleetglint/sources/` when `XDG_STATE_HOME` is unset).
- **tachiko-harness state**, when `worker-ledger/runs.tsv` exists under its
  state directory (default `~/.local/state`): the worker ledger, live worker
  marker files, detached job directories (`cmd`, `cwd`, `log`, `pid`,
  `result.json`), wait markers and inbox files.
- **Claude Code transcripts**, when the projects directory exists:
  `$CLAUDE_CONFIG_DIR/projects/**/*.jsonl` (default `~/.claude/projects`),
  including subagent files under `<session>/subagents/`.
- **Codex rollouts**, when the Codex directory exists:
  `$CODEX_HOME/sessions/**/rollout-*.jsonl` and
  `$CODEX_HOME/archived_sessions/**` (default `~/.codex`).
- **Files a record points at**, but only when you open them in the board:
  `log_path`, `result_path` and link `path`. The server looks the path up in
  the record; the client never sends a path. A path is opened only if it
  resolves, after following symlinks, inside a configured allowed root, and
  only if it is a regular file. At most the last 64 KiB is read.

If you install the optional Claude Code hooks, Claude Code sends hook payloads
to `fleetglint hooks record claude` on standard input. Those payloads carry the
session id, event name, working directory and similar fields; Fleetglint turns
them into session records. Installing or uninstalling hooks also reads and
writes `~/.claude/settings.json`.

Fleetglint never asks a tool to do anything. Adapters are read-only: they do
not write to the tools they read.

## What is stored, and where

The state directory is `$XDG_STATE_HOME/fleetglint/`
(`~/.local/state/fleetglint/` by default). It contains:

- `fleetglint.sqlite` — the local read model: the latest record for each
  identity, record history, relationships, source status and quarantine
  entries. Its contents come from the records and from adapter metadata.
- `sources/<source_id>/<seq>.ndjson` — the record lines themselves, including
  any text a writer put in `title`, `summary`, `detail` or other fields.
- `hooks-state.json` and `hooks.log` — state used by the optional hooks, and
  one-line error messages. Hook payload contents are not written to the log.
- Lock and marker files used by the writer and the ingest loop.

Quarantine is local too: an invalid line is kept with its position, a reason
and at most the first 1 KiB of the line. It is stored in the same state
directory and shown redacted.

The config file is `$XDG_CONFIG_HOME/fleetglint/config.toml`
(`~/.config/fleetglint/config.toml` by default). It holds settings only.

A hook install writes a backup of the previous `settings.json` next to it, named
`settings.json.fleetglint-backup-<timestamp>-<pid>`.

Nothing in any of these places is sent to another machine by Fleetglint.

## What is never copied

Adapters copy metadata only: identifiers, timestamps, model and provider names,
projects, roles, titles, short command summaries, counts and token usage. They
never copy:

- prompts or instructions,
- model output,
- tool input or tool output,
- file contents,
- full commands.

The tachiko-harness adapter reads a job's `cmd` file only to produce a short
`command_summary`: the first word plus at most the next two arguments. The full
argument list is not stored. Job and run `log_path` and `result_path` values
are stored as paths; the file contents are read on demand under the rules
above, not copied into the database or the NDJSON segments.

Record text that a writer chooses to include — `title`, `summary`, `detail`,
`outcome`, unknown `x_` fields — is stored as written and may be shown in the
raw view. Do not put secrets in those fields.

## Redaction and its limits

Every string Fleetglint displays passes redaction first, including the raw view
of a record, log tails and quarantine excerpts. Redaction replaces:

- values of environment variables whose names look like credentials (names
  containing `TOKEN`, `SECRET`, `PASSWORD`, `PASSWD`, `API_KEY`, `CREDENTIAL`
  or `AUTH`, or ending in `_KEY`) when the value is at least 8 characters;
- common token shapes: Anthropic, GitHub, OpenAI-style, Google, npm, AWS,
  Slack, GitLab and JWT tokens;
- `Authorization: Bearer …` and `Authorization: Basic …` values;
- PEM private key blocks, including an unterminated block.

This is best effort, not a guarantee. It is pattern-based, so it can miss a
secret in an unfamiliar format, a secret split across lines, or a value that
does not match a known shape. Treat redaction as a safety net and keep secrets
out of records, logs and transcripts in the first place.

## The local API's protections

The HTTP API is small and closed by default:

- It binds to `127.0.0.1` only and refuses to start on any other host.
- Only `GET` and `HEAD` are accepted; other methods get 405.
- The `Host` header must be `127.0.0.1:<port>` or `localhost:<port>`;
  anything else gets 421. This blocks DNS-rebinding attempts.
- It sends no CORS headers. Responses carry `Cache-Control: no-store`,
  `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`,
  `X-Frame-Options: DENY` and a restrictive Content-Security-Policy.
- Request bodies are not read, and query strings over 2 KiB are refused.
- File access goes through the record lookup and allowed-root checks described
  above. A bad path is shown as "not readable", never as an error page with
  the path's contents.
- A record can make Fleetglint read a file, but never run a command, follow a
  URL or contact a network host.

There is no telemetry, no crash reporting and no update check.

## Deleting everything

1. Stop the service: press Ctrl-C in the terminal running `fleetglint serve`,
   or run `brew services stop fleetglint` if you started it as a service.
2. If you installed hooks, run `fleetglint hooks uninstall claude`.
3. Remove the demo source if you created it: `fleetglint demo --clear`.
4. Remove the state and config directories:

   ```sh
   rm -rf "${XDG_STATE_HOME:-$HOME/.local/state}/fleetglint" \
          "${XDG_CONFIG_HOME:-$HOME/.config}/fleetglint"
   ```

5. Remove any `settings.json.fleetglint-backup-*` files next to
   `~/.claude/settings.json` if you no longer want them.

Deleting the state directory removes the SQLite read model, the NDJSON
segments, hook state and quarantine. The database is disposable and rebuilds
from retained segments and enabled adapters; imported records are re-created
on the next start from the tools' own files. NDJSON records whose segments you
deleted are gone.

Uninstalling the package removes the program, not the state or config
directories, so run the steps above as well.
