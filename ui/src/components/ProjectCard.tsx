import type { BoardInboxItem, BoardWork, ProjectCard as Project } from "../api/types";
import { ageSince, formatAgo } from "../format";
import { detailHref, projectHref } from "../router";
import { StateBadge } from "./StateBadge";

function band(project: Project): string {
  if (project.needs_you.length) {
    for (const [state, token] of [["failed", "failed"], ["lost", "gone"], ["stale", "stale"], ["unknown", "unverified"]]) {
      if (project.needs_you.some(item => item.display_state === state)) return token;
    }
    return "needs";
  }
  if (project.in_progress.some(item => item.display_state === "running")) return "running";
  if (project.in_progress.some(item => item.display_state === "waiting" || item.display_state === "queued")) return "waiting";
  return project.recent.done.length ? "done" : "idle";
}

function title(item: BoardWork | BoardInboxItem) {
  return item.title ?? ("command_summary" in item ? item.command_summary : null) ?? item.ref.id;
}
function key(item: BoardWork | BoardInboxItem) { return `${item.ref.source_id}/${item.ref.type}/${item.ref.id}`; }
function More({ count, truncated, href }: { count: number; truncated: boolean; href: string }) {
  if (!count && !truncated) return null;
  return <p className="project-more"><a href={href}>{count ? `${count}${truncated ? "+" : ""} more` : "More"} on the project page</a></p>;
}

export function ProjectCard({ project, now, full = false }: { project: Project; now: number; full?: boolean }) {
  const href = projectHref(project.project);
  const recent = [...project.recent.done.slice(0, full ? undefined : 3), ...project.recent.failed.slice(0, full ? undefined : 3)].sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at));
  const recentMore = full ? 0 : Math.max(0, project.recent.done.length - 3) + Math.max(0, project.recent.failed.length - 3);
  return <article className="project-card" data-band={band(project)} style={{ borderTopColor: `var(--state-${band(project)}-border)` }}>
    <header className="project-header"><div><h2><a href={href}>{project.project ?? "Global"}</a></h2>
      {project.project === null ? <span className="quiet">No project</span> : null}</div>
      <div className="project-meta">{project.last_activity_at ? `last activity ${formatAgo(ageSince(project.last_activity_at, now))} · ` : ""}{project.lead_inbox_open} lead inbox open · {project.sessions_recent} recent sessions</div></header>
    {project.needs_you.length > 0 && <section><h3>Needs you</h3>{project.needs_you.map(item => <div className="project-item" key={key(item)}><StateBadge state={item.display_state} /> <a href={detailHref(item.ref)}>{title(item)}</a> <span className="quiet">{"section_reason" in item ? item.section_reason : item.detail}</span></div>)}<More count={0} truncated={project.truncated.needs_you} href={href} /></section>}
    {project.in_progress.length > 0 && <section><h3>In progress</h3>{project.in_progress.map(item => <div className="project-item" key={key(item)} data-record-id={item.ref.id}><StateBadge state={item.display_state} /> <a href={detailHref(item.ref)}>{title(item)}</a><div className="quiet">{"agent" in item ? [item.worker ?? item.agent, item.model].filter(Boolean).join(" · ") : [item.kind, item.command_summary].filter(Boolean).join(" · ")}</div>{item.jobs?.map(job => <div className="project-job" key={key(job)}><StateBadge state={job.display_state} /> <a href={detailHref(job.ref)}>{title(job)}</a>{"command_summary" in job && <span className="quiet"> · {[job.kind, job.command_summary].filter(Boolean).join(" · ")}</span>}</div>)}</div>)}<More count={0} truncated={project.truncated.in_progress} href={href} /></section>}
    {project.decisions.length > 0 && <section><h3>Recent decisions</h3>{project.decisions.map(d => <div className="project-item" key={`${d.ref.source_id}/${d.ref.id}`}>{d.links[0]?.url ? <a href={d.links[0].url} target="_blank" rel="noreferrer noopener">{d.text}</a> : d.text}<div className="quiet">{d.role_id} · {formatAgo(ageSince(d.decided_at, now))}</div></div>)}<More count={0} truncated={project.truncated.decisions} href={href} /></section>}
    {recent.length > 0 && <section><h3>Recent</h3>{recent.map(item => <div className="project-item" key={key(item)}><StateBadge state={item.display_state} /> <a href={detailHref(item.ref)}>{title(item)}</a></div>)}<More count={recentMore} truncated={project.truncated.recent.done || project.truncated.recent.failed} href={href} /></section>}
  </article>;
}
