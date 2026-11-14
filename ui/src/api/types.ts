/*
 * Mirrors docs/architecture.md §4 (HTTP API). Field names are identical.
 */

export type RecordType = "run" | "job" | "inbox_item" | "session";

export type DisplayState =
  | "queued"
  | "running"
  | "waiting"
  | "done"
  | "failed"
  | "cancelled"
  | "stale"
  | "lost"
  | "unknown"
  | "open"
  | "acked"
  | "recent"
  | "idle"
  | "ended";

export type EvidenceKind =
  | "process"
  | "process_gone"
  | "observed"
  | "expired"
  | "terminal"
  | "writer_unknown"
  | "source_problem"
  | "activity";

export interface Evidence {
  kind: EvidenceKind;
  age_s: number | null;
  detail: string | null;
}

export interface Link {
  label: string;
  path?: string;
  url?: string;
  readable?: boolean;
}

export interface RecordRef {
  type: RecordType;
  id: string;
  source_id: string;
}

export interface ExtendedRef extends RecordRef {
  resolved: boolean;
  display_state?: DisplayState;
  title?: string;
}

export interface ExternalRef {
  type: "external";
  kind: string;
  key?: string;
  url?: string;
}

export type Ref = RecordRef | ExtendedRef | ExternalRef;

export interface Source {
  source_id: string;
  kind: "ndjson" | "adapter";
  status: "ok" | "discontinuity" | "unavailable" | "quarantine";
  detail: string | null;
  last_scan_at: string | null;
  last_record_at: string | null;
  quarantine_count: number;
  records: number;
}

export interface SummaryBase {
  ref: RecordRef;
  state: string;
  display_state: DisplayState;
  evidence: Evidence;
  updated_at: string;
  observed_at: string;
  project: string | null;
  title: string | null;
  links: Link[];
}

export interface RunSummary extends SummaryBase {
  agent: string;
  worker?: string;
  model: string | null;
  provider: string | null;
  effort: string | null;
  role_id: string | null;
  session_id: string | null;
  started_at: string | null;
  ended_at: string | null;
  exit_code: number | null;
  summary: string | null;
  parent_run: ExtendedRef | null;
  resume_of: ExtendedRef | null;
  waits_on: Ref[];
}

export interface FileRef {
  path: string;
  readable: boolean;
}

export interface JobSummary extends SummaryBase {
  kind: string | null;
  command_summary: string;
  run: ExtendedRef | null;
  role_id: string | null;
  started_at: string | null;
  ended_at: string | null;
  exit_code: number | null;
  signal: string | null;
  summary: string | null;
  log: FileRef | null;
  result: FileRef | null;
}

export interface InboxSummary extends SummaryBase {
  role_id: string;
  kind: string;
  subject: Ref;
  outcome: string | null;
  action_required: boolean;
  created_at: string;
  acked_at: string | null;
  detail: string | null;
  blocks_retention: boolean;
}

export interface UsageCost {
  amount: number;
  currency: string;
  basis: "billed" | "api_equivalent" | "estimated";
}

export interface Usage {
  basis: "measured" | "estimated";
  input_tokens?: number;
  cached_input_tokens?: number;
  output_tokens?: number;
  cost?: UsageCost;
}

export interface SessionSummary extends SummaryBase {
  agent: string;
  model: string | null;
  models: string[];
  provider: string | null;
  effort: string | null;
  role_id: string | null;
  started_at: string | null;
  last_activity_at: string;
  ended_at: string | null;
  turn_open: boolean | null;
  entries: number | null;
  parent_session: ExtendedRef | null;
  usage: Usage | null;
}

export type Summary = RunSummary | JobSummary | InboxSummary | SessionSummary;

export interface Counts {
  running: number;
  waiting: number;
  attention: number;
  stale_lost_unknown: number;
  sessions_recent: number;
}

export type AttentionReason =
  | "action_required"
  | "inbox"
  | "lost"
  | "stale"
  | "unknown"
  | "source";

export interface AttentionEntry {
  reason: AttentionReason;
  who: string | null;
  subject: Ref | null;
  source_id: string;
  text: string;
}

export interface Snapshot {
  api: 1;
  generated_at: string;
  server: { version: string; host: string; read_only: boolean };
  window_hours: number;
  sources: Source[];
  counts: Counts;
  runs: RunSummary[];
  jobs: JobSummary[];
  inbox: InboxSummary[];
  sessions: SessionSummary[];
  attention: AttentionEntry[];
  truncated: {
    runs: boolean;
    jobs: boolean;
    inbox: boolean;
    sessions: boolean;
  };
  demo: boolean;
}

export type SectionReason = string;

/** A run or job on the board, with the per-section fields of architecture §4.1b. */
export type BoardWork = (RunSummary | JobSummary) & {
  started_age_s: number | null;
  section_reason: SectionReason | null;
};

export interface BoardInboxItem extends InboxSummary {
  age_s: number | null;
}

export interface BoardInboxRole {
  role_id: string;
  by_project: { project: string | null; open: number; old: number; action_required: number }[];
  open: number;
  old: number;
  oldest_age_s: number | null;
  action_required: number;
  items: BoardInboxItem[];
}

export interface BoardCounts {
  needs_you: number;
  queued: number;
  waiting: number;
  running: number;
  lead_inbox_open: number;
  lead_inbox_old: number;
  process_gone: number;
  out_of_date: number;
  unverified_recent: number;
  failed_recent: number;
  older_unverified: number;
  sessions_recent: number;
}

export interface BoardExceptions {
  process_gone: BoardWork[];
  out_of_date: BoardWork[];
  unverified_recent: BoardWork[];
}

export interface Decision {
  ref: { type: "decision"; id: string; source_id: string };
  project: string | null;
  role_id: string;
  text: string;
  decided_at: string;
  links: Link[];
}

export interface ProjectCard {
  project: string | null;
  needs_you: (BoardWork | BoardInboxItem)[];
  in_progress: (BoardWork & { jobs?: BoardWork[] })[];
  decisions: Decision[];
  recent: { done: BoardWork[]; failed: BoardWork[] };
  lead_inbox_open: number;
  sessions_recent: number;
  last_activity_at: string | null;
  truncated: { needs_you: boolean; in_progress: boolean; decisions: boolean; recent: { done: boolean; failed: boolean } };
}

export interface Board {
  api: 1;
  generated_at: string;
  server: { version: string; host: string; read_only: boolean };
  window_hours: number;
  inbox_old_after_s: number;
  demo: boolean;
  sources: Source[];
  capabilities: { execution: boolean; requests: boolean };
  counts: BoardCounts;
  needs_you: BoardInboxItem[];
  projects: ProjectCard[];
  lead_inbox: BoardInboxRole[];
  queued: BoardWork[];
  waiting: BoardWork[];
  running: BoardWork[];
  exceptions: BoardExceptions;
  recent: BoardWork[];
  sessions: SessionSummary[];
  sessions_total: number;
  truncated: {
    queued: boolean;
    waiting: boolean;
    running: boolean;
    exceptions: boolean;
    recent: boolean;
    lead_inbox: boolean;
  };
}

export interface Relations {
  parent: ExtendedRef | null;
  resume_of: ExtendedRef | null;
  children: ExtendedRef[];
  resumed_by: ExtendedRef[];
  jobs: ExtendedRef[];
  inbox: ExtendedRef[];
  waited_on_by: ExtendedRef[];
}

export interface HistoryEntry {
  seq: number;
  byte_offset: number;
  updated_at: string;
  state: string;
}

export interface RecordResponse {
  api: 1;
  generated_at: string;
  record: Summary;
  full: Record<string, unknown>;
  relations: Relations;
  history: HistoryEntry[];
  usage: Usage | null;
}

export interface FileReadable {
  api: 1;
  readable: true;
  path: string;
  size: number;
  truncated: boolean;
  text: string;
  redactions: number;
}

export interface FileNotReadable {
  api: 1;
  readable: false;
  reason:
    | "outside_allowed_roots"
    | "not_regular_file"
    | "missing"
    | "not_utf8"
    | "no_path";
}

export type FileResponse = FileReadable | FileNotReadable;
