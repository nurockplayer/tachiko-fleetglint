# Acceptance

Rows a person or a script can judge on a running board. A PR names the row it
moves, or says none. Re-score after a change lands and record the date and how
it was checked.

Scored 2026-11-17 22:50 JST against `main` 78b3808, `fleetglint serve` on
:8791 with an isolated database and the real `~/.local/state` (18 cards).

**Pass: 5 / 8**

| # | Row | How to check | Status | Evidence |
|---|-----|--------------|--------|----------|
| A1 | The server is read-only and local: `/api/healthz` 200, any `POST` 405, a foreign `Host` 421. | `curl` the three requests. | pass | 200 / 405 / 421 on 2026-11-17. |
| A2 | Every overview card is a real project. No card is named after a role, a worktree or branch directory, or a placeholder. | List `projects[].project` in `/api/board`. | fail | 2026-11-17 23:30 JST after #113: `harness`, `ops`, `(local, no remote)`, `shift_app-demo`, `light-predict-revert-c4f0a5b` gone. Left: `bjh` (role prefix), `gteki-ad-1117` (job cwd in a scratch dir, not a repo). Both need a known project from the producer or a configured alias. |
| A3 | No overview card is empty: each has at least one needs-you, in-progress, decision or recent item. | Count those sections per card in `/api/board`. | fail | 2026-11-17 23:30 JST after #113: only `bjh` (one open lead-inbox item, nothing else); fixed with A2's attribution. |
| A4 | In progress shows each running item with a readable title (the brief heading, or the command summary for CI and jobs) and the model for runs; jobs a run waits on sit under it. | Read `in_progress` on each card. | pass | 24 items: every job has a title or command summary, every run a model. Some harness runs show the brief file name, which is the harness ledger's data. |
| A5 | Recent decisions cover 7 days and link to their GitHub comment when one exists. | Check `decisions[].links`. | pass | 74 of 76 link; the two without are a repo with no remote and a decision recorded without a ref. |
| A6 | Needs you holds only what someone must act on now: what is asked, of whom, and since when. | Read `needs_you` on each card. | fail | 94 items, 83 with no role: 65 are failed detached jobs from hours earlier, mostly already handled by their lead. |
| A7 | OrbStack (`orb-test`) and GitHub CI runs show on their project's card. | Look for `orb-test` and `github-actions` items. | pass | 2 `orb-test` and 6 `github-actions` items in progress on 2026-11-17. |
| A8 | A fresh install works: the empty state lists where it looked; `fleetglint demo` shows the DEMO DATA banner. | Isolated HOME, released package. | pass | Verified on 0.1.1 from the public release, 2026-11-08 JST. |
