# Changelog

All notable changes to Fleetglint are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
