import type {
  InboxSummary,
  JobSummary,
  RunSummary,
  SessionSummary,
} from "../api/types";
import { detailHref } from "../router";
import { ageSince, formatAbsolute, formatAge } from "../format";
import type { BadgeState } from "../states";
import { StateBadge } from "./StateBadge";
import { EvidenceLabel, refText } from "./Refs";

const AGE_SUFFIX_STATES: ReadonlySet<string> = new Set(["stale", "lost", "unknown"]);

function rowAge(updatedAt: string, evidenceAge: number | null): string {
  return formatAge(evidenceAge ?? ageSince(updatedAt));
}

export function RunRow({ run }: { run: RunSummary }) {
  const age = rowAge(run.updated_at, run.evidence.age_s);
  const badgeAge = AGE_SUFFIX_STATES.has(run.display_state) ? age : null;
  const firstWait = run.waits_on[0];
  return (
    <a
      className="row run-row"
      href={detailHref(run.ref)}
      data-state={run.display_state}
      data-record-id={run.ref.id}
    >
      <span className="cell-badge">
        <StateBadge state={run.display_state} age={badgeAge} />
      </span>
      <span className="cell-title">{run.title ?? run.ref.id}</span>
      <span className="cell-model">
        {run.agent}
        {run.model ? ` · ${run.model}` : ""}
      </span>
      <span className="cell-role">{run.role_id ?? "—"}</span>
      <span className="cell-project">{run.project ?? "—"}</span>
      <span className="cell-age" title={formatAbsolute(run.updated_at)}>
        {age}
      </span>
      <span className="cell-note">
        {run.display_state === "waiting" && firstWait ? (
          <span className="waits-on">waits on → {refText(firstWait)}</span>
        ) : (
          <EvidenceLabel evidence={run.evidence} />
        )}
      </span>
    </a>
  );
}

export function exitText(job: JobSummary): string {
  if (job.exit_code != null) return `exit ${job.exit_code}`;
  if (job.signal) return `signal ${job.signal}`;
  return "—";
}

export function JobRow({ job }: { job: JobSummary }) {
  const age = rowAge(job.updated_at, job.evidence.age_s);
  return (
    <a
      className="row job-row"
      href={detailHref(job.ref)}
      data-state={job.display_state}
      data-record-id={job.ref.id}
    >
      <span className="cell-badge">
        <StateBadge
          state={job.display_state}
          age={AGE_SUFFIX_STATES.has(job.display_state) ? age : null}
        />
      </span>
      <span className="cell-title mono">{job.command_summary}</span>
      <span className="cell-kind">{job.kind ?? "—"}</span>
      <span className="cell-run">
        {job.run ? `run · ${job.run.title ?? job.run.id}` : "—"}
      </span>
      <span className="cell-exit">{exitText(job)}</span>
    </a>
  );
}

export function inboxTone(item: InboxSummary): "action" | "normal" | "acked" {
  if (item.state === "acked") return "acked";
  return item.action_required ? "action" : "normal";
}

export function inboxBadgeState(item: InboxSummary): BadgeState {
  const tone = inboxTone(item);
  if (tone === "action") return "attention";
  if (tone === "acked") return "acked";
  return "open";
}

export function InboxItem({ item }: { item: InboxSummary }) {
  const tone = inboxTone(item);
  const subject = item.subject;
  const title = (
    <span className="inbox-subject">{refText(subject)}</span>
  );

  const body = (
    <>
      <span className="cell-badge">
        <StateBadge state={inboxBadgeState(item)} />
      </span>
      <span className="inbox-main">
        <span className="inbox-line">
          <span className="inbox-role">{item.role_id}</span>
          <span className="inbox-kind">
            {item.kind}
            {item.outcome ? ` · ${item.outcome}` : ""}
          </span>
          {title}
        </span>
        {item.detail ? <span className="inbox-detail">{item.detail}</span> : null}
      </span>
      <span className="inbox-age" title={formatAbsolute(item.created_at)}>
        {formatAge(ageSince(item.created_at))}
      </span>
    </>
  );

  const className = `inbox-item tone-${tone}`;

  if (subject.type === "external") {
    if (subject.url) {
      return (
        <a
          className={className}
          href={subject.url}
          target="_blank"
          rel="noreferrer noopener"
        >
          {body}
        </a>
      );
    }
    return <div className={className}>{body}</div>;
  }

  return (
    <a className={className} href={detailHref(subject)}>
      {body}
    </a>
  );
}

function sessionActivity(session: SessionSummary): string {
  const age = formatAge(session.evidence.age_s ?? ageSince(session.last_activity_at));
  switch (session.display_state) {
    case "recent":
      return `recent ${age}`;
    case "idle":
      return `idle ${age}`;
    case "ended":
      return "ended";
    default:
      return session.display_state;
  }
}

export function SessionRow({ session }: { session: SessionSummary }) {
  return (
    <a
      className="session-row"
      href={detailHref(session.ref)}
      data-state={session.display_state}
    >
      <StateBadge state={session.display_state} />
      <span className="session-meta">
        <span>{session.agent}</span>
        <span>· {session.model ?? "—"}</span>
        <span>· {session.project ?? "—"}</span>
        {session.title ? <span className="session-title">{session.title}</span> : null}
      </span>
      <span className="session-activity" title={formatAbsolute(session.last_activity_at)}>
        {sessionActivity(session)}
      </span>
    </a>
  );
}

export interface CountTileProps {
  label: string;
  value: number;
  states: BadgeState[];
  href: string;
}

export function CountTile({ label, value, states, href }: CountTileProps) {
  return (
    <a className="tile" href={href} data-tile={label}>
      <span className="tile-number mono">{value}</span>
      <span className="tile-label">{label}</span>
      <span className="tile-badges">
        {states.map((state) => (
          <StateBadge key={state} state={state} />
        ))}
      </span>
    </a>
  );
}
