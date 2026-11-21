// Display fields from plan-check's JSON report; harness owns validation and status.
export interface PlanLink { label: string; url: string }
export interface Criterion {
  id: string;
  status: string;
  requirement?: string;
  judge?: string;
  reason?: string | null;
  changed_files?: string[];
  status_detail?: string;
  context?: string;
  verified_at?: string;
  verified_sha?: string;
  evidence?: PlanLink[];
  references?: PlanLink[];
}
export interface Workstream {
  id: string;
  title?: string;
  outcome?: string;
  lead?: string;
  phases?: { id: string; title: string }[];
  current_phase?: string;
  next_step?: string;
  context?: string[];
  references?: PlanLink[];
  criteria: Criterion[];
}
export interface OwnerDecision {
  id: string;
  question: string;
  options: string[];
  recommendation: string;
  deadline: string;
  state: string;
  answer?: string;
  answer_ref?: string;
}
export interface PlanResult {
  path: string;
  state: "pending" | "ok" | "invalid" | "unavailable" | "failed";
  checked_at: string | null;
  file_modified_at: string | null;
  refreshing: boolean;
  project?: string;
  plan_state?: string;
  counts?: Record<string, number>;
  errors?: string[];
  text_available?: boolean;
  workstreams?: Workstream[];
  owner_decisions?: OwnerDecision[];
}
export interface PlansResponse { api: 1; refresh_s: number; plans: PlanResult[] }
