import type { ReactNode } from "react";
import type { BoardWork, JobSummary, RunSummary } from "../api/types";
import { ageSince, formatAge, formatAgo } from "../format";
import { detailHref } from "../router";

type Work = BoardWork | RunSummary | JobSummary;

/** A job's title, falling back to its command; a run's title, falling back to its id. */
export function workTitle(work: Work): string {
  if (work.ref.type === "job") {
    return work.title ?? (work as JobSummary).command_summary;
  }
  return work.title ?? work.ref.id;
}

/** A job's command summary, shown under its title. */
export function workCommand(work: Work): string | null {
  if (work.ref.type !== "job") return null;
  const command = (work as JobSummary).command_summary;
  return command && command !== workTitle(work) ? command : null;
}

export function workRole(work: Work): string | null {
  if (work.ref.type === "run") return (work as RunSummary).role_id;
  if (work.ref.type === "job") return (work as JobSummary).role_id;
  return null;
}

/** The model a run records, otherwise its agent; jobs carry neither. */
export function workModel(work: Work): string | null {
  if (work.ref.type !== "run") return null;
  const run = work as RunSummary;
  return run.model ?? run.agent ?? null;
}

/** What a waiting row says it waits on, in words (visual spec §5, §7). */
export function waitWords(work: BoardWork): string {
  if (work.section_reason === "lead_wait") {
    if (work.ref.type === "job") {
      const job = work as JobSummary;
      if (job.kind === "wait" && (work.title ?? "").startsWith("PR #")) {
        return "waits on review";
      }
    }
    return "waiting";
  }
  if (work.ref.type === "run") {
    const waits = (work as RunSummary).waits_on[0];
    if (waits) {
      if (waits.type === "external") return `waits on ${waits.key ?? waits.kind}`;
      return `waits on ${waits.type} ${waits.id}`;
    }
  }
  return "waiting";
}

export function workDuration(work: BoardWork): string | null {
  return formatAge(work.started_age_s) || null;
}

/** Latest process-check age across the running rows, for the section heading. */
export function freshestProcessCheck(rows: BoardWork[]): number | null {
  let freshest: number | null = null;
  for (const row of rows) {
    if (row.evidence.kind !== "process" || row.evidence.age_s == null) continue;
    freshest = freshest == null ? row.evidence.age_s : Math.min(freshest, row.evidence.age_s);
  }
  return freshest;
}

/**
 * A row's own check time: shown only when it differs from the section heading
 * by more than 60 s. A row with no process evidence says `no process check`.
 */
export function checkText(work: Work, referenceAge: number | null): string | null {
  const evidence = work.evidence;
  if (evidence.kind === "process" && evidence.age_s != null) {
    if (referenceAge != null && Math.abs(evidence.age_s - referenceAge) <= 60) return null;
    return `checked ${formatAgo(evidence.age_s)}`;
  }
  if (evidence.kind === "process_gone") return null;
  return "no process check";
}

/** Age since the record last changed, preferring the evidence's own age. */
export function updatedAgo(work: Work, now: number): string {
  return formatAgo(work.evidence.age_s ?? ageSince(work.updated_at, now));
}

export interface WorkRowProps {
  work: Work;
  className: string;
  children: ReactNode;
  glyph?: ReactNode;
}

/** One linked work row; identity is the record ref, so a refresh keeps the DOM node. */
export function WorkRow({ work, className, children, glyph }: WorkRowProps) {
  return (
    <a
      className={`work-row ${className}`}
      href={detailHref(work.ref)}
      data-state={work.display_state}
      data-record-id={work.ref.id}
    >
      {glyph ? <span className="row-glyph">{glyph}</span> : null}
      {children}
    </a>
  );
}
