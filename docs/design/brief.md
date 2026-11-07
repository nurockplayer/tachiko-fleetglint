# Fleetglint design brief (v0.1)

Status: from v0.1.1 the visual authority is [visual-spec.md](visual-spec.md), and the
dark cyber direction below no longer applies. This brief stays the authority for what the UI
must mean, except where visual-spec.md changes the first screen.

## 1. Job of the UI

Answer three questions at a glance, for someone running many agents at once:

1. **What is running?** (and is that claim still backed by evidence)
2. **Why is it waiting?** (on which job, review, PR or person)
3. **Who must act?** (which role, about what)

The UI is read-only. There are no buttons that change a workflow: no
dispatch, retry, merge, ack or drag. Links open things (a PR, a log view);
nothing else.

## 2. Priorities, in order

1. **State legibility.** Every display state in [spec §8](../spec.md) is
   distinguishable without color (shape or glyph + text label), at row
   density, in a screenshot, for a color-blind reader.
2. **Evidence and provenance.** Every live claim shows where it came from
   (`source_id`), how old the evidence is (`observed_at` age) and what kind
   of evidence it is (process check, writer refresh, none).
3. **Relationships.** Spawned-by (`parent_run`), continues (`resume_of`),
   waits on (`waits_on`), owned job (`job.run`), inbox subject. Unresolved
   references are shown as such, never hidden.
4. **Density.** Many rows visible; quiet chrome; data in monospace.
5. **Style.** Dark, "cyber / terminal" mood: near-black surfaces, one
   phosphor accent, monospace data. Style never overrides 1–4.

## 3. Display states (the core of the system)

Writer states and display states come from spec §4 and §8. When the display
state differs from the writer's state, show both: `running → stale 42m`.

| Display state | Meaning | Required encoding (color is extra, never alone) |
|---|---|---|
| `queued` | accepted, not started | hollow circle, label "queued" |
| `running` | executing, evidence current | filled circle with a slow pulse (static under reduced motion), accent color |
| `waiting` | blocked on `waits_on` | hourglass or link glyph, warm amber; the row shows "waits on →" and the first reference |
| `done` | writer said done | check glyph, quiet green; low visual weight (done work should recede) |
| `failed` | writer said failed | cross glyph, red; exit code or signal next to it when present |
| `cancelled` | stopped on purpose | slash glyph, neutral grey |
| `stale` | non-terminal claim, evidence expired | **dashed** outline of the original state's glyph, desaturated, plus age ("stale 42m"); must not look like running or failed |
| `lost` | process verified gone, no terminal record | broken-link glyph, distinct hue (not the failed red), label "lost"; this is an attention item |
| `unknown` | writer said unknown, or source discontinuity / unavailable | question glyph on a hatched or striped background, grey |
| inbox `open` + `action_required` | someone must act | strongest attention treatment in the system (bar + glyph + label "action") |
| inbox `open` | worth a look | normal weight |
| inbox `acked` | seen | muted |

Contrast: text at least 4.5:1, state glyphs and boundaries at least 3:1
against their surface (WCAG 2.1 AA). Test with a deuteranopia/protanopia
simulation: the table above must still read.

Source-level states for the top bar: `ok`, `discontinuity` (needs the user),
`unavailable` (adapter cannot read), `quarantine N` (bad lines count).
API failure shows an **Unavailable** state for the whole board; it never
shows sample or cached data as if current.

## 4. Token families

Reuse only the *categories* of tachiko-sheet's
[UI quality contract §3](https://github.com/nurockplayer/tachiko-sheet/blob/main/docs/design/ui-quality-contract.md);
no values are copied. Figma variables, two layers:

- **Primitives** (one collection): color ramps (neutral, accent, green,
  amber, red, the `lost` hue, grey), spacing scale on a 4 px base
  (2, 4, 8, 12, 16, 24, 32, 48), radius (0, 2, 4, 8), font sizes.
- **Semantic** (one collection, mode `dark`; leave room for a `light` mode
  later, do not build it now):
  - surface: `canvas`, `chrome`, `panel`, `raised`, `overlay`, `row-hover`,
    `row-selected`
  - text: `primary`, `secondary`, `meta`, `disabled`, `mono-data`, `link`
  - line: `divider`, `boundary`, `focus`, `relationship`, `unresolved`
  - state: one family per display state (`fg`, `bg`, `border`), plus
    `attention`
  - provenance: `source-chip-bg`, `source-chip-fg`, `age-fresh`, `age-old`
- **Typography** styles: a sans for UI and a monospace for ids, times,
  numbers, paths and log lines (choose freely available fonts, e.g. Inter
  and JetBrains Mono or IBM Plex Sans/Mono). Sizes for density: row text
  13 px, meta 12 px, headings 16/20 px.
- **Motion**: two durations (fast ~120 ms for hover/focus, base ~200 ms for
  panels) and one ambient loop (running pulse, ~1.6 s). All motion has a
  reduced-motion fallback.
- **Geometry**: row heights 28 (compact) and 32 (default); radius only for
  chips, badges and panels; shadow only for overlays (tooltip, popover).

## 5. Components (with variants)

- `StateBadge`: every display state in §3; sizes `sm` (row) and `md`
  (header); optional age suffix.
- `StateTransition`: writer state → display state, e.g. `running → stale 42m`.
- `SourceChip`: `source_id`, with source status dot.
- `EvidenceLabel`: `pid ✓ 12s`, `refresh 3m`, `no evidence`.
- `RefLink`: record ref (type icon + id), external ref (kind icon + key),
  unresolved (dashed underline + "not seen").
- `RunRow`: state, title, agent · model, role, project, started / age,
  waits-on, source; hover and selected states; compact and default.
- `JobRow`: state, command summary (mono), kind, owning run, exit/signal.
- `InboxItem`: role, kind, subject ref, outcome, action-required treatment,
  created age, detail preview (2 lines).
- `CountTile`: number + label + state glyph (Running, Waiting, Needs
  attention, Stale/Lost/Unknown).
- `TopBar`: product mark, source health strip, last refresh time, "read-only"
  indicator.
- `Banner`: `unavailable`, `discontinuity`, `quarantine`.
- `RelationshipTree`: parent / children / resume chain / waits-on edges.
- `LogTail`: monospace, redacted spans visibly marked `[redacted]`, size cap
  notice, "not readable" variant.
- `Tooltip`, `EmptyState`.

## 6. Screens (desktop 1440 × 900; Overview also at 390 wide)

Use realistic data: the lead → worker → detached job → inbox → resumed lead
chain from [`examples/v1/valid/lead-worker-job.ndjson`](../../examples/v1/valid/lead-worker-job.ndjson),
plus a few more runs across 3 projects, 4 agents/models, one `stale`, one
`lost`, one `unknown` and one source with a discontinuity.

1. **Overview**: count tiles; runs grouped by project (or by role, show
   the toggle) with waiting runs showing what they wait on; recent
   terminal runs collapsed and quiet; source health in the top bar.
2. **Run detail**: header (title, `StateTransition`, agent · model ·
   effort, role, source, evidence); relationships (`RelationshipTree`);
   owned jobs; version history of the record (each line seen, with
   `updated_at` and position); usage (tokens, cost with its basis label);
   `LogTail`; raw fields (redacted).
3. **Needs attention**: open inbox items with `action_required` first, then
   other open items; then `lost`, then `stale`/`unknown` runs and jobs;
   then source problems (discontinuity, unavailable, quarantine count).
   Each entry says who must act and links to the subject.

Plus one frame showing the board-wide **Unavailable** state and one
**empty** state (no sources yet, with the one-line "write NDJSON here" hint).

## 7. Out of scope for v0.1

Kanban, cost charts, timeline view, light theme, settings UI, any write
action.
