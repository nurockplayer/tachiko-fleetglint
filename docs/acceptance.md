# Acceptance

Rows a person or a script can judge on a running board. A PR names the row it
moves, or says none. Re-score after a change lands and record the date and how
it was checked.

A2 and A3 re-scored 2026-11-22 04:49 JST against `main` a14f069,
`fleetglint serve` on :8791 with fresh isolated state and data and the host
config (15 rendered cards); other row statuses are carried forward. Previously
re-scored 2026-11-22 03:54 JST at b182350 (19 cards). First scored
2026-11-17 22:50 JST at 78b3808 (5/8, 18 cards).

**Pass: 7 / 8**

| # | Row | How to check | Status | Evidence |
|---|-----|--------------|--------|----------|
| A1 | The server is read-only and local: `/api/healthz` 200, any `POST` 405, a foreign `Host` 421. | `curl` the three requests. | pass | 200 / 405 / 421 on 2026-11-17. |
| A2 | Every overview card is a real project. No card is named after a role, a worktree or branch directory, or a placeholder. | List `projects[].project` in `/api/board`. | fail | 2026-11-22 04:49 JST, `main` a14f069: 15 rendered cards. GitHub remotes under `nurockplayer/`: `tachiko-fleetglint`, `eddington-1919`, `gteki`, `tachiko-noren`, `tachiko-sheet`, `tachiko-work`, `tachiko-harness`, `tailbox-updater`, `tokyo-mogu-mogu`, `tachinas-media`, `oracle-ego`, `quota-advisor`. `business-japanese-hub` is configured in host role mappings. `Global` is the allowed catch-all. `tachinas` fails: no matching host configuration or local repo found; its two items are harness lead-inbox entries for `tachinas-ops` and `tachinas-lead` on `heavy-window-presence-20261119`. |
| A3 | No Overview card is empty: each has at least one needs-you, in-progress, decision, recent or lead-inbox item. Session-only groups are not Overview cards; they remain in `/api/board` for the project page. | Apply the Overview rendering rule to `/api/board`, excluding session-only groups, and count needs-you, in-progress, decision, recent and lead-inbox items per rendered card. | pass | 2026-11-22 04:49 JST, `main` a14f069: 15 rendered cards; none empty. `business-japanese-hub` and `tachinas` had lead-inbox items only (1 and 2 respectively). |
| A4 | In progress shows each running item with a readable title (the brief heading, or the command summary for CI and jobs) and the model for runs; jobs a run waits on sit under it. | Read `in_progress` on each card. | pass | 24 items: every job has a title or command summary, every run a model. Some harness runs show the brief file name, which is the harness ledger's data. |
| A5 | Recent decisions cover 7 days and link to their GitHub comment when one exists. | Check `decisions[].links`. | pass | 74 of 76 link; the two without are a repo with no remote and a decision recorded without a ref. |
| A6 | Needs you holds only what someone must act on now: what is asked, of whom, and since when. | Read `needs_you` on each card. | pass | 2026-11-18 00:25 JST after #116: 36 work items + 8 owner items (was 94). Role-less failures older than 4 h moved to Recent failed (unresolved); the 21 left are under 4 h old. |
| A7 | OrbStack (`tachi-run`) and GitHub CI runs show on their project's card. | Look for `tachi-run` and `github-actions` items. | pass | 2 `tachi-run` and 6 `github-actions` items in progress on 2026-11-17. |
| A8 | A fresh install works: the empty state lists where it looked; `fleetglint demo` shows the DEMO DATA banner. | Isolated HOME, released package. | pass | Verified on 0.1.1 from the public release, 2026-11-08 JST. |
