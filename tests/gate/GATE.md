# Release gate (docs/architecture.md §10)

Every item is an automated test in `tests/gate/test_gate.py` (standard-library
`unittest`). The tests drive the real program: `python -m fleetglint serve --port 0`
with `PYTHONPATH=src` and a `HOME`, `XDG_STATE_HOME`, `XDG_CONFIG_HOME`,
`CLAUDE_CONFIG_DIR` and `CODEX_HOME` that all live inside one `tempfile` directory, so
the machine's real data is never read.

Run just the gate (from the repository root):

```
PYTHONPATH=src python3 -m unittest tests.gate.test_gate -v
```

CI runs them with the normal discovery (`python -m unittest discover -s tests -t .`).
The whole directory stays well under 60 s.

| §10 | Gate item | Test |
|---|---|---|
| 1 | Clean environment: `serve`, then `fleetglint emit` records show up without a restart | `CleanEnvironmentGateTest.test_clean_environment_emit_shows_without_restart` |
| 2 | A detached job shows its owning run, the run's `waits_on` the job, and the job's terminal record updates the board without a restart | `JobRelationsGateTest.test_detached_job_relations_and_terminal_update` |
| 3 | An old non-terminal record is `stale`; a vanished local pid is `lost`; a segment gap turns the source into a discontinuity and its records into `unknown` | `LivenessGateTest.test_stale_lost_and_discontinuity` |
| 4 | Malformed and oversize lines are quarantined and later lines still ingest; a symlinked `log_path` out of the allowed roots is not readable; a 10 MiB log returns at most the 64 KiB tail; a secret in a field, a log and a quarantined line never appears in an API response | `SafetyGateTest.test_malformed_oversize_symlink_tail_and_secrets` |
| 5 | `kill -9` the server mid-ingest of a 20,000-line segment, restart, and compare with an uninterrupted run: same latest records, same history rows per id, no duplicates, nothing lost (read-only SQLite) | `KillMidBatchGateTest.test_kill_during_ingest_loses_nothing` |
| 6 | API down → the UI shows Unavailable and never presents stale data as current | covered by `ui/src/App.test.tsx`: "shows Unavailable on a network failure and keeps old data marked old" and "shows Unavailable on HTTP 500 and does not present old data as current" (no new test here) |
| 7 | Non-GET → 405, a foreign `Host` → 421 (architecture §4.5's DNS-rebinding guard), no `Access-Control-Allow-Origin` on a cross-origin request, `Origin`-bearing requests behave normally, API responses carry `Cache-Control: no-store` | `RequestSafetyGateTest.test_request_safety_methods_host_origin_and_cache` |
| §10 round 4 | First run with only a Claude Code transcript, only a Codex rollout, and neither: `fleetglint doctor` exits 0 and names what it found (or nothing found); the snapshot holds the expected sessions and an otherwise empty board; no session is running/waiting/done/failed or needs attention; re-scans are idempotent (`records`, `history`, `change_counter` stop moving); the canary is absent from the SQLite file (and `-wal`), every API response and the server's stdout/stderr | `FirstRunGateTest.test_first_run_with_only_claude_code`, `test_first_run_with_only_codex`, `test_first_run_with_neither` |

`scripts/smoke_wheel.py <path to fleetglint>` smoke-tests an installed wheel (the
release workflow runs it after `pip install dist/*.whl`): `GET /` is 200 and mentions
Fleetglint, a hashed asset it links is 200, an emitted record reaches
`/api/snapshot`, and SIGTERM exits 0.
