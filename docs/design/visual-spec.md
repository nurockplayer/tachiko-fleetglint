# Fleetglint visual spec

The design contract for the UI since v0.1.1. It replaces the dark cyber direction in
`brief.md`; that brief's priorities (state legibility, evidence, relationships) stay.
The Figma file is not updated for this version: this document and the code are the source.

Fleetglint is a board for supervising delegated work. It should read like a calm
professional work tool, not like a terminal or a monitoring wall. The viewer is one expert
glancing at it for five seconds between other work, often on a second monitor.

## 1. Principles

Each one can be checked on a screenshot.

1. **Decisions before telemetry.** What the viewer was notified about, what waits and what
   runs are all visible at 1440×900 without scrolling or opening a page.
2. **Neutral by default.** At least 90% of the surface is neutral. State tint covers at most
   8%. No list gets a coloured background.
3. **Amber means you.** Amber appears only on items addressed to the human. Normal work never
   uses it: waiting is blue, because waiting is not an alarm.
4. **Say a thing once.** A section heading states what its rows share. A row shows only what
   differs from its neighbours. No repeated state words, project names or check times.
5. **State is explicit and honest.** Every state has a glyph and words, and never relies on
   colour alone. Unknown is not zero. Not observable is not zero. Never fabricate a duration,
   an owner or a task description.
6. **Density without compression.** Rows are 36–40 px, ordinary text is at least 13 px, and
   there is no horizontal scrolling at 390 px.

## 2. Colour

Tokens live in `ui/src/tokens.css` under these names. Light is the default; dark applies under
`@media (prefers-color-scheme: dark)`, following the system, with no toggle. Set
`color-scheme: light dark`, and a `theme-color` meta tag for each scheme.

### Foundation

| Token | Light | Dark | Use |
|---|---|---|---|
| `surface-canvas` | `#F5F7F5` | `#14191A` | Page background |
| `surface-chrome` | `#FFFFFF` | `#1A2022` | Top bar |
| `surface-panel` | `#FFFFFF` | `#1B2123` | Panels |
| `surface-raised` | `#F0F3F1` | `#232A2C` | Log viewer, secondary surfaces |
| `surface-row-hover` | `#F2F6F4` | `#232A2C` | Row hover |
| `text-primary` | `#17231F` | `#E7ECE9` | Main content |
| `text-secondary` | `#43514B` | `#BCC6C1` | Secondary content |
| `text-meta` | `#5F6C65` | `#9AA5A0` | Metadata |
| `text-mono-data` | `#263832` | `#D0D9D4` | Identifiers, paths, logs |
| `text-link` | `#155E75` | `#7CC4DB` | Links |
| `line-divider` | `#DCE3DE` | `#2C3437` | Decorative separators only |
| `line-boundary` | `#7F8B84` | `#6F7C76` | Meaningful boundaries, relationship lines |
| `line-focus` | `#176B87` | `#5FB7D4` | Keyboard focus |
| `line-unresolved` | `#9A5B13` | `#D39A4E` | Unresolved relationship |

### State

Foreground / background / border.

| State | Light | Dark | Glyph |
|---|---|---|---|
| Notified (`state-needs`) | `#754000` `#FFF1DC` `#B76516` | `#F2B76B` `#33261A` `#B8803F` | `!` |
| Running | `#155D4B` `#E8F4EF` `#3D856D` | `#6FCFB0` `#15302A` `#3F9C80` | filled circle |
| Waiting | `#1B5A82` `#E7F1F8` `#4B8BB5` | `#8CC6EE` `#17293A` `#4E87B0` | hourglass |
| Failed | `#942B2B` `#FCEBEC` `#BE4B4B` | `#F29A9A` `#3A1F22` `#C25E5E` | × |
| Process gone (`state-gone`) | `#5A4787` `#F0ECF8` `#8069AF` | `#BFA9F0` `#2A2440` `#8A74BD` | broken link |
| Out of date (`state-stale`) | `#65552F` `#F3F0E6` `#94804F` | `#CDBB86` `#2B271B` `#8F8052` | dashed circle |
| Unverified | `#4D5961` `#EDF1F3` `#74838D` | `#AEBBC4` `#252B30` `#76858F` | `?` |
| Done | `#315F43` `#EAF3EC` `#6C9277` | `#92C7A5` `#1C2C22` `#5F9070` | check |
| Recent | `#365A73` `#EDF3F7` `#607F95` | `#98C0DC` `#1C2A35` `#5F88A5` | clock |
| Idle | `#56615B` `#F0F2F0` `#7F8B84` | `#A7B2AC` `#252A28` `#707C76` | crescent |

Computed with the WCAG formula, in both themes: every text token and state foreground is at
least 4.5:1 on canvas, panel and raised surfaces (state foregrounds also on their own state
background); every border is at least 3:1 on its state background and on the panel. A test in
`ui/src/tokens.test.ts` keeps this true.

Rules:

- Never red for waiting. Never green for a session: a session is not proof of execution.
- Never a state-coloured fill on a whole row or card. Notifications use a 4 px leading edge.
- No gradients, glows, or decorative shadows. Shadows only on overlays.
- The dark theme uses a neutral dark grey canvas, not near-black.

## 3. Type

No external font requests.

- UI: `Inter, "PingFang TC", "Noto Sans TC", "Noto Sans CJK TC", "Noto Sans CJK JP",
  "Microsoft JhengHei UI", "Hiragino Sans", "Yu Gothic UI", system-ui, sans-serif`
- Mono: `ui-monospace, "SFMono-Regular", "Cascadia Code", "Noto Sans Mono CJK TC", Menlo,
  Consolas, monospace`

| Role | Size / line | Weight |
|---|---|---|
| Detail title | 24 / 32 | 650 |
| Section heading | 17 / 24 | 650 |
| Group heading | 14 / 20 | 650 |
| Body | 14 / 21 | 400 |
| Work row title | 14 / 20 | 550 |
| Compact row | 13 / 18 | 400 |
| Metadata | 12 / 16 | 450 |

All numbers use `font-variant-numeric: tabular-nums`. Avoid uppercase labels.

Monospace only for job ids in metadata, paths, command summaries, log output and raw fields.
Row titles and the detail title use the UI font even when they are slugs: they are names to read.
Project, role, model and agent names, durations, counts, messages and explanations use the UI
font too.

## 4. Space and layout

Base unit 4 px: 4, 8, 12, 16, 20, 24, 32, 40, 48. Panel radius 8, small radius 6. Content
maximum width 1320 px, centred. Row height 36 px, 40 px when a row has two lines at 1440.

| Width | Layout |
|---|---|
| ≥ 1280 | Waiting 5 columns, Running 7 columns, side by side. Other sections full width. |
| 768–1279 | Waiting and Running stacked, full width |
| < 768 | 16 px gutters, one column, row content wraps onto a second line, no horizontal scroll |

## 5. First screen

Order from the top, and nothing else. No page title and no KPI tiles.

```
Fleetglint   ● Claude Code  ● Codex CLI  ● Tachiko Harness     updated 8s ago   Read only
3 notified · 8 waiting · 14 running · 12 lead inbox · 4 exceptions
You were notified                                              last 24 hours
▌ 外部審查服務失敗，已改走備援，需要你重新登入。           lead-a · review-login · 18m ago
▌ An approval is needed before task-12 proceeds.             lead-b · repo-access · 2h ago
Waiting 8                         Running 14                       process checks 6s ago
worker-962       lead-a           project-a                                  3
  waits on job scan-3      12m    ● feature-import    lead-a      Claude Opus 5.5    47m
PR #301 review   lead-b           ● worker-engine     lead-c      DeepSeek Flash     31m
  waits on review           8m    project-b                                  2
Lead inbox  12 open · 3 waiting over 4 h                           [show]
  lead-c 4 · lead-d 4 · lead-b 2 · lead-a 1
4 exceptions                                                       [show]
  2 process gone · 1 out of date · 1 unverified · 700 older records unverified, in history
Recent  3 failed · 17 done                                         [show]
```

The content is illustrative. Rules for each part:

- **Top bar.** 56 px, `surface-chrome`; under 768 px the source names move to a second line, in full.
  Friendly source names from the adapter kind (Claude Code,
  Codex CLI, Tachiko Harness; an NDJSON source shows its own name). A dot plus words when not
  connected: Data gap, Unavailable, N quarantined. The machine id goes in a tooltip and on the
  source's detail, never in the bar.
- **Summary line.** One line, not tiles. Each number links to its section. A count states its unit
  in words. Zero sections stay in the line. A missing capability shows `running: not observable`.
- **You were notified.** The heading says it once; items do not repeat it. Message first, regular
  weight, at most two lines with the rest on hover and in detail. Sender, key and age in `text-meta`:
  in a right-hand column at 1280 and wider, on a line below otherwise. Never print the viewer's own
  role or a `from:` prefix.
  4 px amber leading edge, no fill. Never call them open or unacknowledged, and show no checkbox:
  the source has no acknowledged state. They leave after 24 hours. When empty, the section collapses
  to `Nothing notified you in the last 24 hours.` in `text-meta`.
- **Waiting.** Title, role when recorded, what it waits on in words, how long. The section heading
  carries the state, so a row shows the glyph without the word, and never the bare word `waiting`:
  when nothing says what it waits on, the row has one line. Sort longest first.
- **Running.** Grouped by project, group heading once with a count. Row: glyph, title, role when
  recorded, model or agent (a job: its command summary, mono), `47m` right-aligned. A job's title is
  its `title`, else its id, never its command: many jobs share one command. Column headings once at
  the top of the list.
  The heading carries `process checks 6s ago` once. A row shows its own check time only when it
  differs by more than 60 s. A row with no process evidence says `no process check`.
- **Queued.** Work accepted but not started is never waiting. Only when non-zero: `N queued` in the
  summary line and a small `Queued N` group at the end of the Running list.
- **Lead inbox.** Collapsed to one summary line with per-role counts. Items older than the configured
  threshold get `text-secondary` plus `over 4 h`, not amber: these are addressed to AI leads, not the
  viewer. Expanding shows role groups with their messages.
- **Exceptions.** Collapsed line with separate counts. Never one combined number. Old unverified
  records stay one aggregate that links to history; they are never rendered one by one here.
- **Recent.** Collapsed line. Expanding lists failures first, then the newest done.
- **Sessions.** When execution is observable, a collapsed line at the bottom. In the sessions-only
  case they are the main list; see below.

### Sessions-only first run

When `capabilities.execution` is false, the summary line says `running: not observable · waiting: not
observable`, followed by one sentence: `Session history shows recent activity, not whether a process
is running. Connect a source with process evidence to see running work.` Recent sessions, then idle,
fill the page with last activity, agent, model and project. Sessions are never green and never count
as running.

### Other states

- No sources: explain how to add one and offer `fleetglint demo`.
- Loading: keep the top bar and the layout geometry with neutral skeletons, no spinner, no placeholder
  numbers. Only on first load; a background refresh never shows skeletons.
- API failure: one restrained banner, `Unavailable · last successful refresh 08:14 · current state
  cannot be verified`, and keep the last data visibly marked out of date. Never show demo data.

## 6. Detail page

One column, at most 960 px. In order:

1. Breadcrumb: Overview / project / title.
2. Glyph and state word. Title (mono if it is a slug). Model and agent, role when recorded.
3. **What is happening**: one panel saying it in words. `Waiting on job scan-3. The worker has
   handed off and resumes when the job ends. The wrapper process is alive, checked 6s ago.` Job state
   comes from the job's own record; when it cannot be found say `job status not found`, never infer it.
4. **Relationships**: a vertical chain. Solid line for confirmed, dashed `line-unresolved` for a
   reference that does not resolve. Each edge has words.
5. **Evidence**: process check, writer state, source and observation age, each on its own line.
6. **Log**: the tail, mono 12/18, `surface-raised`, at most 360 px tall, long lines wrap,
   `[redacted]` explicit. Unavailable is a stated condition.
7. Collapsed by default with native `<details>`: usage, version history, raw fields. Absolute times with
   their zone belong here and in tooltips.

## 7. Words

UI vocabulary only; the API and record format keep their names.

| Instead of | Say |
|---|---|
| run | worker (or the title alone) |
| job | job; a lead's wait says what it waits on |
| lost | process gone, no result recorded |
| stale | out of date |
| unknown, writer_unknown | unverified |
| pid ok 6s | process checked 6s ago |
| inbox | lead inbox |
| action / needs attention | you were notified |
| `—` for a missing value | leave it out, or say `not recorded` where the absence matters |

Time: `Started` means start time, `checked` means observation age, `waiting 12m` means duration.
Never show a bare `6s`. Relative: seconds under a minute, minutes under an hour, `1h 4m` under a day,
then days. A list column may drop the word when its heading states it.

## 8. Motion and refresh

Poll every 15 s while the tab is visible, pause while hidden, refresh once on return. Counters change
instantly. Rows keep their DOM identity. Project order is stable: first seen, then alphabetical; no
reordering on refresh. A refresh never resets scroll, collapses an open section or flashes. Hover and
focus 120 ms. No pulsing or animated running indicator. Honour `prefers-reduced-motion`.

## 9. Anti-patterns

Reject in review: terminal styling, monospace prose, status pills everywhere, KPI tiles, a card around
each row, repeated project names or state words, a check time on every row, unexplained dashes, invented
task descriptions, merging work by title or command, calling a notification a request, lead inbox items
presented as the human's to-do, one combined exception counter, hundreds of old records rendered
individually, zero where the truth is not observable, cached data shown as current, the log as the page's
first thing, colour without glyph and words, reordering on refresh.

## 10. Screenshot review

Run on real data and on the demo, at 1440, 1024 and 390, in light and dark, before calling it done.

1. In five seconds a person can say what they were notified about, what waits and what runs.
2. It reads as a work tool, not a terminal, in both themes.
3. Notifications: who, which key, how old; no invented open state; none older than 24 h.
4. Lead inbox is visibly below and quieter than notifications.
5. Every waiting row names what it waits on, and none is amber.
6. Every running row can be told apart from its neighbours, and shows its lead when recorded.
7. A live wrapper waiting on a job shows as waiting, never as process gone (permanent regression).
8. Started and checked times are never confused, and no bare `6s`.
9. Old unverified records appear as one aggregate; process gone, out of date and unverified are separate.
10. Every state is distinguishable in greyscale.
11. Long Traditional Chinese messages render well and do not break the layout.
12. 1440×900 shows notifications, waiting and running without scrolling.
13. 390 px has no horizontal overflow and hides nothing essential.
14. A refresh causes no movement, reordering or flash.
15. No dispatch, retry, merge or acknowledge action exists.
16. The sessions-only first run says not observable, not zero.
