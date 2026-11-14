# Changelog

All notable changes to Fleetglint are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- The harness adapter reads GitHub Actions and orb-test jobs, including recent
  orb-test finishes when its finish log is available.

### Changed

- Role-based project inference removes the last hyphen segment.

### Fixed

- Overview project cards show at most five needs-you items and link to the project page for the remaining total.
- Project cards no longer come from the `~/Developer` folder itself or duplicate records of adapter sources whose host name changed.
- Project needs-you cards omit unknown oracle dot-ci runs and superseded GitHub
  Actions failures, and collapse repeated work failures with a quiet repeat count.
- Review bundles use their repository's project name; filesystem boundaries and
  Claude scratchpad directories no longer create stray project cards.
- Successful ci-watch polls are marked done and clear earlier poll errors without
  appearing in project cards' recent results. Empty successful polls no longer
  count as ci-watch errors.
- orb-test labels containing only environment assignments use a safe `orb-test`
  command summary so their job records remain valid.
- Untitled work on project cards uses record IDs, with job commands shown quietly.
- Project pages use backend inbox totals even when messages are truncated, and
  omit links to more content on the same project page.

## [0.1.1] - 2026-11-08

### Changed

- The board is rebuilt for the person watching the work, not for the tools
  that write it. The first screen answers, in order: what notified you, what
  is waiting and on what, what is running, then the lead inbox, exceptions,
  recent results and sessions in collapsed sections. One line of counts
  replaces the tiles.
- Light and dark themes follow the system setting.
- States read as words: `process gone`, `out of date`, `unverified`. The raw
  `lost`, `stale` and `unknown` values no longer appear.
- The old attention screen is gone; `/attention` opens the board. The full
  record list moves to `/history`.

### Added

- `GET /api/board`, the data behind the first screen, and a `[ui]` config
  table (`viewer_roles`, `needs_you_hours`, `inbox_old_after_s`).
- tachiko-harness adapter: runs that wait on a job show as waiting, with what
  they wait on; lead-wait jobs get a title and kind; a run takes its role from
  the job that started it; owner-notify messages show as items for the owner.

### Fixed

- tachiko-harness adapter: live runs no longer show as lost. The process
  start time came from the ledger write time, a few seconds late.
- A job's project is its git repository, not the folder of its worktree.
- Session rows no longer link to a detail page that cannot load.
- A source with quarantined records no longer shows the healthy dot.

## [0.1.0] - 2026-11-06

### Added

- A local, read-only board on `127.0.0.1` that shows what is running, what is
  waiting and what needs attention.
- Record format v1 for runs, jobs, inbox items and sessions, with a JSON
  Schema, a validator and an `emit` command.
- Read-only adapters for tachiko-harness state, Claude Code transcripts and
  Codex rollouts. Imported sessions are metadata only and are never shown as
  running.
- Optional Claude Code hooks that record session starts and ends.
- Labelled sample data with `fleetglint demo`, and path and source diagnostics
  with `fleetglint doctor`.
- Homebrew and pipx installs. No runtime dependencies beyond Python 3.11 or
  later.
