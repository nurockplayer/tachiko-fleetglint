/*
 * Synthetic /api/board fixtures (architecture §4.1b). Hand-built, not copied
 * from any real store: every source id, project, role and title is invented.
 */
import type {
  Board,
  BoardCounts,
  BoardInboxItem,
  BoardInboxRole,
  BoardWork,
  Evidence,
  JobSummary,
  RunSummary,
  SessionSummary,
  Source,
} from "../api/types";

const NOW = "2026-11-07T10:00:00+09:00";

const processCheck: Evidence = { kind: "process", age_s: 6, detail: null };

const sources: Source[] = [
  {
    source_id: "claude-code@demo-host",
    kind: "ndjson",
    status: "ok",
    detail: null,
    last_scan_at: "2026-11-07T09:59:50+09:00",
    last_record_at: "2026-11-07T09:58:10+09:00",
    quarantine_count: 0,
    records: 42,
  },
  {
    source_id: "codex-cli@demo-host",
    kind: "ndjson",
    status: "discontinuity",
    detail: "scan gap of 12m",
    last_scan_at: "2026-11-07T09:59:50+09:00",
    last_record_at: "2026-11-07T09:57:40+09:00",
    quarantine_count: 2,
    records: 88,
  },
];

function run(
  partial: Partial<BoardWork> & Pick<RunSummary, "ref" | "state" | "display_state">,
): BoardWork {
  return {
    evidence: processCheck,
    updated_at: "2026-11-07T09:58:00+09:00",
    observed_at: "2026-11-07T09:59:54+09:00",
    project: null,
    title: null,
    links: [],
    agent: "claude-code",
    model: null,
    provider: null,
    effort: null,
    role_id: null,
    session_id: null,
    started_at: null,
    ended_at: null,
    exit_code: null,
    summary: null,
    parent_run: null,
    resume_of: null,
    waits_on: [],
    started_age_s: null,
    section_reason: null,
    ...partial,
  } as BoardWork;
}

function job(
  partial: Partial<BoardWork> & Pick<JobSummary, "ref" | "state" | "display_state" | "command_summary">,
): BoardWork {
  return {
    evidence: processCheck,
    updated_at: "2026-11-07T09:58:00+09:00",
    observed_at: "2026-11-07T09:59:54+09:00",
    project: null,
    title: null,
    links: [],
    kind: "shell",
    run: null,
    role_id: null,
    started_at: null,
    ended_at: null,
    exit_code: null,
    signal: null,
    summary: null,
    log: null,
    result: null,
    started_age_s: null,
    section_reason: null,
    ...partial,
  } as BoardWork;
}

const reviewJob = job({
  ref: { type: "job", id: "review-pr-43", source_id: "codex-cli@demo-host" },
  state: "running",
  display_state: "running",
  kind: "wait",
  command_summary: "claude-code review pr 43",
  title: "PR #43 review",
  project: "fleetglint",
  role_id: "fleetglint-lead",
  started_at: "2026-11-07T07:30:00+09:00",
  evidence: { kind: "process", age_s: 12, detail: null },
  started_age_s: 9000,
  section_reason: "lead_wait",
});

const waitRun = run({
  ref: { type: "run", id: "run-909", source_id: "codex-cli@demo-host" },
  state: "waiting",
  display_state: "waiting",
  title: "Rebuild the viewer board",
  project: "fleetglint",
  agent: "codex-cli",
  model: "gpt-6.1-terra",
  provider: "codex",
  effort: "medium",
  role_id: "fleetglint-ui",
  started_at: "2026-11-07T08:00:00+09:00",
  waits_on: [{ type: "job", id: "job-317", source_id: "codex-cli@demo-host" }],
  started_age_s: 7200,
  section_reason: "waits_on",
});

const externalWaitRun = run({
  ref: { type: "run", id: "run-910", source_id: "claude-code@demo-host" },
  state: "waiting",
  display_state: "waiting",
  title: "Design the exception table",
  project: "edd",
  agent: "claude-code",
  model: "opus-5-5",
  provider: "anthropic",
  role_id: "edd-art",
  started_at: "2026-11-07T09:20:00+09:00",
  waits_on: [
    {
      type: "external",
      kind: "ticket",
      key: "FG-1180",
      url: "https://example.invalid/FG-1180",
    },
  ],
  started_age_s: 2400,
  section_reason: "waits_on",
});

const runningJob = job({
  ref: { type: "job", id: "job-317", source_id: "codex-cli@demo-host" },
  state: "running",
  display_state: "running",
  command_summary: "pnpm test --run",
  project: "fleetglint",
  role_id: "fleetglint-ui",
  started_at: "2026-11-07T09:10:00+09:00",
  started_age_s: 3000,
  section_reason: null,
});

const runningLeadRun = run({
  ref: { type: "run", id: "run-901", source_id: "claude-code@demo-host" },
  state: "running",
  display_state: "running",
  title: "Run the review gate",
  project: "fleetglint",
  agent: "claude-code",
  model: "opus-5-5",
  provider: "anthropic",
  role_id: "fleetglint-lead",
  started_at: "2026-11-07T09:30:00+09:00",
  started_age_s: 1800,
  section_reason: null,
});

const runningArtRun = run({
  ref: { type: "run", id: "run-902", source_id: "codex-cli@demo-host" },
  state: "running",
  display_state: "running",
  title: "Draw the cover",
  project: "edd",
  agent: "codex-cli",
  model: "gpt-6.1-terra",
  provider: "codex",
  role_id: "edd-art",
  started_at: "2026-11-07T09:40:00+09:00",
  evidence: { kind: "process", age_s: 120, detail: null },
  started_age_s: 1200,
  section_reason: null,
});

const runningSpacingRun = run({
  ref: { type: "run", id: "run-903", source_id: "claude-code@demo-host" },
  state: "running",
  display_state: "running",
  title: "Check the panel spacing",
  project: "fleetglint",
  agent: "claude-code",
  model: "sonnet-5-5",
  provider: "anthropic",
  role_id: "fleetglint-ui",
  started_at: "2026-11-07T09:55:00+09:00",
  evidence: { kind: "process", age_s: 3, detail: null },
  started_age_s: 300,
  section_reason: null,
});

const queuedJob = job({
  ref: { type: "job", id: "job-401", source_id: "codex-cli@demo-host" },
  state: "queued",
  display_state: "queued",
  command_summary: "pnpm build",
  project: "fleetglint",
  role_id: "fleetglint-ui",
  evidence: { kind: "terminal", age_s: null, detail: null },
  started_age_s: null,
  section_reason: null,
});

const queuedRun = run({
  ref: { type: "run", id: "run-904", source_id: "claude-code@demo-host" },
  state: "queued",
  display_state: "queued",
  title: "Test the history page",
  project: "edd",
  agent: "codex-cli",
  model: "gpt-6-luna",
  provider: "codex",
  role_id: "edd-art",
  evidence: { kind: "terminal", age_s: null, detail: null },
  started_age_s: null,
  section_reason: null,
});

const goneJob = job({
  ref: { type: "job", id: "job-388", source_id: "codex-cli@demo-host" },
  state: "running",
  display_state: "lost",
  command_summary: "pnpm e2e",
  project: "fleetglint",
  role_id: "fleetglint-ui",
  started_at: "2026-11-07T06:00:00+09:00",
  evidence: { kind: "process_gone", age_s: null, detail: "no process with this id" },
  started_age_s: 14400,
  section_reason: null,
});

const staleRun = run({
  ref: { type: "run", id: "run-880", source_id: "claude-code@demo-host" },
  state: "running",
  display_state: "stale",
  title: "Refresh the screenshots",
  project: "edd",
  agent: "claude-code",
  model: "opus-5-5",
  role_id: "edd-art",
  started_at: "2026-11-07T05:00:00+09:00",
  evidence: { kind: "expired", age_s: 5400, detail: "last update 1h 30m ago" },
  started_age_s: 18000,
  section_reason: null,
});

const unknownJob = job({
  ref: { type: "job", id: "job-390", source_id: "codex-cli@demo-host" },
  state: "unknown",
  display_state: "unknown",
  command_summary: "pnpm lint",
  project: "fleetglint",
  role_id: "fleetglint-ui",
  started_at: "2026-11-07T09:00:00+09:00",
  evidence: { kind: "writer_unknown", age_s: null, detail: null },
  started_age_s: 3600,
  section_reason: null,
});

const failedRun = run({
  ref: { type: "run", id: "run-870", source_id: "claude-code@demo-host" },
  state: "failed",
  display_state: "failed",
  title: "Install UI dependencies",
  project: "fleetglint",
  agent: "claude-code",
  model: "sonnet-5-5",
  role_id: "fleetglint-ui",
  started_at: "2026-11-07T07:00:00+09:00",
  ended_at: "2026-11-07T07:03:00+09:00",
  exit_code: 1,
  evidence: { kind: "terminal", age_s: 10620, detail: null },
  updated_at: "2026-11-07T07:03:00+09:00",
  started_age_s: 10800,
  section_reason: null,
});

const failedJob = job({
  ref: { type: "job", id: "job-360", source_id: "codex-cli@demo-host" },
  state: "failed",
  display_state: "failed",
  command_summary: "pnpm typecheck",
  project: "fleetglint",
  role_id: "fleetglint-ui",
  started_at: "2026-11-07T07:10:00+09:00",
  ended_at: "2026-11-07T07:12:00+09:00",
  exit_code: 2,
  evidence: { kind: "terminal", age_s: 10320, detail: null },
  updated_at: "2026-11-07T07:12:00+09:00",
  started_age_s: 10200,
  section_reason: null,
});

const doneRun = run({
  ref: { type: "run", id: "run-871", source_id: "codex-cli@demo-host" },
  state: "done",
  display_state: "done",
  title: "Update the board API",
  project: "fleetglint",
  agent: "codex-cli",
  model: "gpt-6.1-terra",
  role_id: "fleetglint-lead",
  started_at: "2026-11-07T06:00:00+09:00",
  ended_at: "2026-11-07T06:40:00+09:00",
  exit_code: 0,
  evidence: { kind: "terminal", age_s: 12000, detail: null },
  updated_at: "2026-11-07T06:40:00+09:00",
  started_age_s: 14400,
  section_reason: null,
});

const cancelledRun = run({
  ref: { type: "run", id: "run-872", source_id: "claude-code@demo-host" },
  state: "cancelled",
  display_state: "cancelled",
  title: "Draft the history page",
  project: "edd",
  agent: "claude-code",
  role_id: "edd-art",
  started_at: "2026-11-07T05:30:00+09:00",
  ended_at: "2026-11-07T05:35:00+09:00",
  evidence: { kind: "terminal", age_s: 15900, detail: null },
  updated_at: "2026-11-07T05:35:00+09:00",
  started_age_s: 16200,
  section_reason: null,
});

function inboxItem(
  partial: Partial<BoardInboxItem> &
    Pick<BoardInboxItem, "ref" | "role_id" | "kind" | "subject" | "created_at" | "age_s">,
): BoardInboxItem {
  return {
    state: "open",
    display_state: "open",
    evidence: { kind: "activity", age_s: partial.age_s, detail: null },
    updated_at: partial.created_at,
    observed_at: "2026-11-07T09:59:54+09:00",
    project: null,
    title: null,
    links: [],
    outcome: null,
    action_required: false,
    acked_at: null,
    detail: null,
    blocks_retention: false,
    ...partial,
  };
}

const notifiedDecision = inboxItem({
  ref: { type: "inbox_item", id: "inbox-a", source_id: "claude-code@demo-host" },
  role_id: "owner",
  kind: "decision",
  subject: { type: "external", kind: "message", key: "dot-1180" },
  created_at: "2026-11-07T09:30:00+09:00",
  age_s: 1800,
  action_required: true,
  detail: "Should the board call the retry an exception?",
});

const notifiedReview = inboxItem({
  ref: { type: "inbox_item", id: "inbox-b", source_id: "codex-cli@demo-host" },
  role_id: "owner",
  kind: "review",
  subject: { type: "run", id: "run-909", source_id: "codex-cli@demo-host" },
  created_at: "2026-11-07T09:00:00+09:00",
  age_s: 3600,
  action_required: true,
  detail: "Review finished: two blockers fixed in PR #43.",
});

const leadOld = inboxItem({
  ref: { type: "inbox_item", id: "inbox-c", source_id: "codex-cli@demo-host" },
  role_id: "fleetglint-lead",
  kind: "wait",
  subject: { type: "job", id: "review-pr-43", source_id: "codex-cli@demo-host" },
  created_at: "2026-11-07T05:00:00+09:00",
  age_s: 18000,
  detail: "One worker is waiting on a decision.",
});

const leadNew = inboxItem({
  ref: { type: "inbox_item", id: "inbox-d", source_id: "codex-cli@demo-host" },
  role_id: "fleetglint-lead",
  kind: "info",
  subject: { type: "external", kind: "ticket", key: "oracle-1" },
  created_at: "2026-11-07T09:50:00+09:00",
  age_s: 600,
  detail: "Review request sent to oracle.",
});

const artLead = inboxItem({
  ref: { type: "inbox_item", id: "inbox-e", source_id: "claude-code@demo-host" },
  role_id: "edd-art",
  kind: "info",
  subject: { type: "run", id: "run-902", source_id: "codex-cli@demo-host" },
  created_at: "2026-11-07T09:45:00+09:00",
  age_s: 900,
  detail: "Cover draft is ready for a look.",
});

const leadInbox: BoardInboxRole[] = [
  {
    role_id: "fleetglint-lead",
    open: 2,
    old: 1,
    oldest_age_s: 18000,
    action_required: 0,
    items: [leadNew, leadOld],
  },
  {
    role_id: "edd-art",
    open: 1,
    old: 0,
    oldest_age_s: 900,
    action_required: 0,
    items: [artLead],
  },
];

const sessions: SessionSummary[] = [
  {
    ref: { type: "session", id: "sess-a", source_id: "claude-code@demo-host" },
    state: "recent",
    display_state: "recent",
    evidence: { kind: "activity", age_s: 120, detail: "last entry 2m ago" },
    updated_at: "2026-11-07T09:58:00+09:00",
    observed_at: "2026-11-07T09:59:54+09:00",
    project: "fleetglint",
    title: "Fleetglint lead session",
    links: [],
    agent: "claude-code",
    model: "opus-5-5",
    models: ["opus-5-5"],
    provider: "anthropic",
    effort: "high",
    role_id: "fleetglint-lead",
    started_at: "2026-11-07T08:55:00+09:00",
    last_activity_at: "2026-11-07T09:58:00+09:00",
    ended_at: null,
    turn_open: true,
    entries: 42,
    parent_session: null,
    usage: null,
  },
  {
    ref: { type: "session", id: "sess-b", source_id: "codex-cli@demo-host" },
    state: "idle",
    display_state: "idle",
    evidence: { kind: "activity", age_s: 10800, detail: null },
    updated_at: "2026-11-07T07:00:00+09:00",
    observed_at: "2026-11-07T09:59:54+09:00",
    project: "edd",
    title: "Cover drawing session",
    links: [],
    agent: "codex-cli",
    model: "gpt-6.1-terra",
    models: ["gpt-6.1-terra"],
    provider: "codex",
    effort: "medium",
    role_id: "edd-art",
    started_at: "2026-11-07T06:30:00+09:00",
    last_activity_at: "2026-11-07T07:00:00+09:00",
    ended_at: null,
    turn_open: false,
    entries: 18,
    parent_session: null,
    usage: null,
  },
  {
    ref: { type: "session", id: "sess-c", source_id: "claude-code@demo-host" },
    state: "ended",
    display_state: "ended",
    evidence: { kind: "activity", age_s: 18000, detail: null },
    updated_at: "2026-11-07T05:10:00+09:00",
    observed_at: "2026-11-07T09:59:54+09:00",
    project: "fleetglint",
    title: "Dependency repair session",
    links: [],
    agent: "claude-code",
    model: "sonnet-5-5",
    models: ["sonnet-5-5"],
    provider: "anthropic",
    effort: "medium",
    role_id: "fleetglint-ui",
    started_at: "2026-11-07T04:30:00+09:00",
    last_activity_at: "2026-11-07T05:00:00+09:00",
    ended_at: "2026-11-07T05:10:00+09:00",
    turn_open: false,
    entries: 9,
    parent_session: null,
    usage: null,
  },
];

const counts: BoardCounts = {
  needs_you: 2,
  queued: 2,
  waiting: 3,
  running: 4,
  lead_inbox_open: 3,
  lead_inbox_old: 1,
  process_gone: 1,
  out_of_date: 1,
  unverified_recent: 1,
  failed_recent: 2,
  older_unverified: 4,
  sessions_recent: 1,
};

export const board: Board = {
  api: 1,
  generated_at: NOW,
  server: { version: "0.1.1", host: "demo-host", read_only: true },
  window_hours: 24,
  inbox_old_after_s: 14400,
  demo: false,
  sources,
  capabilities: { execution: true, requests: true },
  counts,
  needs_you: [notifiedDecision, notifiedReview],
  lead_inbox: leadInbox,
  queued: [queuedJob, queuedRun],
  waiting: [reviewJob, waitRun, externalWaitRun],
  running: [runningJob, runningLeadRun, runningArtRun, runningSpacingRun],
  exceptions: {
    process_gone: [goneJob],
    out_of_date: [staleRun],
    unverified_recent: [unknownJob],
  },
  recent: [failedRun, failedJob, doneRun, cancelledRun],
  sessions,
  sessions_total: 8,
  truncated: {
    queued: false,
    waiting: false,
    running: false,
    exceptions: false,
    recent: false,
    lead_inbox: false,
  },
};

const zeroCounts: BoardCounts = {
  needs_you: 0,
  queued: 0,
  waiting: 0,
  running: 0,
  lead_inbox_open: 0,
  lead_inbox_old: 0,
  process_gone: 0,
  out_of_date: 0,
  unverified_recent: 0,
  failed_recent: 0,
  older_unverified: 0,
  sessions_recent: 0,
};

const noTruncation: Board["truncated"] = {
  queued: false,
  waiting: false,
  running: false,
  exceptions: false,
  recent: false,
  lead_inbox: false,
};

/** A source that carries sessions and inbox items but no process evidence. */
export const boardSessions: Board = {
  api: 1,
  generated_at: NOW,
  server: { version: "0.1.1", host: "demo-host", read_only: true },
  window_hours: 24,
  inbox_old_after_s: 14400,
  demo: false,
  sources: [sources[0]],
  capabilities: { execution: false, requests: true },
  counts: {
    ...zeroCounts,
    needs_you: 1,
    lead_inbox_open: 0,
    sessions_recent: 1,
  },
  needs_you: [notifiedReview],
  lead_inbox: [],
  queued: [],
  waiting: [],
  running: [],
  exceptions: { process_gone: [], out_of_date: [], unverified_recent: [] },
  recent: [],
  sessions,
  sessions_total: 3,
  truncated: noTruncation,
};

/** The empty database: same shape, empty lists, zeros. */
export const boardEmpty: Board = {
  api: 1,
  generated_at: NOW,
  server: { version: "0.1.1", host: "demo-host", read_only: true },
  window_hours: 24,
  inbox_old_after_s: 14400,
  demo: false,
  sources: [],
  capabilities: { execution: false, requests: false },
  counts: zeroCounts,
  needs_you: [],
  lead_inbox: [],
  queued: [],
  waiting: [],
  running: [],
  exceptions: { process_gone: [], out_of_date: [], unverified_recent: [] },
  recent: [],
  sessions: [],
  sessions_total: 0,
  truncated: noTruncation,
};
